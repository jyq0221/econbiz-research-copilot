"""Versioned agent-authored scripts, real execution, and honest result status."""

import hashlib
import os
import subprocess
import sys
import traceback
import uuid
from pathlib import Path

from .files import describe_file, mutable_project_path, read_verified, write_version
from .plans import require_approved_plan
from .processes import run_process
from .run_worker import load_json
from .script_contracts import nonoverlapping, regular_bytes, script_environment, script_path
from .state import WorkflowError, now, require_text
from .workspace import encode_json, require_id


ENTRY = '''from pathlib import Path
import sys
package = Path(__file__).resolve().parent
sys.path.insert(0, str(package / 'tool'))
from econbiz.script_worker import main
raise SystemExit(main(package))
'''


def _input_bytes(workspace, artifact_id):
    artifact = workspace.project.require_usable(artifact_id)
    if artifact['kind'] == 'inventory':
        return workspace.project.read_inventory_bytes(artifact_id)
    if artifact['kind'] == 'source' and len(artifact.get('files', [])) == 1:
        return read_verified(workspace.root, artifact['files'][0])
    raise WorkflowError('脚本输入必须是已登记的单文件来源或数据盘点')


def save_project_script(workspace, script_id, plan_id, *, files, entrypoint, inputs,
                        expected_outputs, reason, backend='python', preparation_recipe=None):
    """Register actual project code. Passing here checks bindings, not statistics."""
    require_id(script_id)
    plan = require_approved_plan(workspace.project, plan_id)
    if plan['content'].get('execution_route') != 'project_script':
        raise WorkflowError('项目脚本须在方案中明确 execution_route=project_script')
    require_text(reason, '编程或技术修复依据')
    if backend not in {'python', 'stata'}:
        raise WorkflowError('项目脚本引擎须为 python 或 stata')
    if not isinstance(files, dict) or not files or not isinstance(inputs, dict) or not inputs:
        raise WorkflowError('必须提供实际代码及已登记输入')
    if not isinstance(expected_outputs, list) or not expected_outputs:
        raise WorkflowError('必须明确预期输出文件列表')
    for name in list(files) + list(inputs) + expected_outputs:
        script_path(name)
    nonoverlapping(list(files) + list(inputs) + expected_outputs)
    if entrypoint not in files or not entrypoint.endswith('.py' if backend == 'python' else '.do'):
        raise WorkflowError('入口文件须存在且与所选语言一致')
    if preparation_recipe is not None:
        from .preprocessing_script import render_preparation_script
        generated = render_preparation_script(preparation_recipe, backend=backend)
        if (files != {entrypoint: generated} or list(inputs) != ['input.csv']
                or expected_outputs != ['processed.csv', 'preparation-audit.json']
                or plan['content'].get('preprocessing') != preparation_recipe):
            raise WorkflowError('纯处理标记仅适用于绑定方案规则、未修改的内置处理脚本')
    inventory_ids = [key for key in plan['dependencies'] if workspace.project.artifact(key)['kind'] == 'inventory']
    if not set(inventory_ids) <= set(inputs.values()):
        raise WorkflowError('项目脚本必须包含方案所绑定的数据盘点输入')
    input_hashes = {name: hashlib.sha256(_input_bytes(workspace, key)).hexdigest() for name, key in inputs.items()}
    version = workspace._version_number(script_id)
    prefix = f'{workspace.layout["research_code"]}/{script_id}/v{version:04d}'
    writes = []
    for name, source in files.items():
        require_text(source, '实际源码')
        writes.append((prefix + '/' + name, source.encode('utf-8')))
    refs = [workspace._file(path, raw, 'project_script_source') for path, raw in writes]
    content = dict(plan_id=plan_id, plan_version=plan['version'], backend=backend,
                   entrypoint=entrypoint, code=list(files), inputs=inputs, input_hashes=input_hashes,
                   expected_outputs=expected_outputs, code_prefix=prefix, reason=reason,
                   preparation_only=preparation_recipe is not None,
                   check_scope='仅源码保存、输入及方案版本绑定；未执行，未认证研究设定或统计数值')
    dependencies = list(dict.fromkeys([plan_id] + list(inputs.values())))
    staged = workspace._stage(script_id, 'project_script', content, dependencies, refs, reason)
    staged.mark(script_id, 'completed', 'passed', content['check_scope'])
    workspace._publish(staged, writes)
    return workspace.project.artifact(script_id)


def save_preparation_script(workspace, script_id, plan_id, *, recipe, inventory_id,
                             reason, backend='python'):
    from .preprocessing_script import render_preparation_script
    entrypoint = 'prepare.py' if backend == 'python' else 'prepare.do'
    return save_project_script(workspace, script_id, plan_id,
        files={entrypoint: render_preparation_script(recipe, backend=backend)}, entrypoint=entrypoint,
        inputs={'input.csv': inventory_id}, expected_outputs=['processed.csv', 'preparation-audit.json'],
        reason=reason, backend=backend, preparation_recipe=recipe)


def execute_project_script(workspace, run_id, script_id, *, timeout=300,
                           stata_executable=None, retry_of=None):
    """Execute trusted project code under host permissions, not in a sandbox.

    A successful attempt remains completed/pending: no statistical reference is
    inferred from exit status, file names, or script-authored verification JSON.
    """
    require_id(run_id)
    if run_id in workspace.project.snapshot()['artifacts']:
        raise WorkflowError('运行标识已存在；请使用新标识保留旧记录')
    if type(timeout) not in {int, float} or not 0 < timeout <= 3600:
        raise WorkflowError('运行时限须为 0 到 3600 秒')
    script = workspace.project.require_usable(script_id)
    if script['kind'] != 'project_script':
        raise WorkflowError('所选记录不是项目脚本')
    config = dict(script['content'])
    plan = require_approved_plan(workspace.project, config['plan_id'])
    if plan['version'] != config['plan_version']:
        raise WorkflowError('脚本对应的方案版本已改变')
    if config['backend'] == 'python' and stata_executable is not None:
        raise WorkflowError('Python 路径不使用 Stata 入口')
    retry = None
    if retry_of is not None:
        previous = workspace.project.artifact(retry_of)
        if previous['kind'] != 'script_run' or not previous['content'].get('finished_at'):
            raise WorkflowError('重试来源必须是已结束的项目脚本运行')
        for key in ('plan_id', 'plan_version', 'input_hashes', 'backend'):
            if previous['content'][key] != config[key]:
                raise WorkflowError('技术重跑必须使用同一方案版本、输入和引擎')
        retry = dict(id=retry_of, version=previous['version'])
    prefix = f'{workspace.layout["research_runs"]}/{run_id}'
    directory = mutable_project_path(workspace.root, prefix)
    if directory.exists():
        raise WorkflowError('运行位置已有文件；请使用新标识')
    environment = script_environment()
    if config['backend'] == 'stata':
        from .stata_runtime import probe_stata
        environment['stata'] = probe_stata(stata_executable)
    config.update(timeout=timeout, token=uuid.uuid4().hex)
    bundle = {'run.py': ENTRY.encode(), 'script.json': encode_json(config),
              'plan.json': encode_json(plan['content']), 'environment.json': encode_json(environment)}
    for name, ref in zip(config['code'], script['files']):
        bundle['code/' + name] = read_verified(workspace.root, ref)
    for name, key in config['inputs'].items():
        raw = _input_bytes(workspace, key)
        if hashlib.sha256(raw).hexdigest() != config['input_hashes'][name]:
            raise WorkflowError('输入内容与脚本保存时不符')
        bundle['inputs/' + name] = raw
    for source in sorted(Path(__file__).resolve().parent.glob('*.py')):
        bundle['tool/econbiz/' + source.name] = source.read_bytes()
    bundle['manifest.json'] = encode_json({'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in bundle.items()}})
    writes = [(prefix + '/' + name, raw) for name, raw in bundle.items()]
    refs = [workspace._file(path, raw, 'frozen_script_input') for path, raw in writes]
    content = dict(package=prefix, script_id=script_id, script_version=script['version'],
                   plan_id=config['plan_id'], plan_version=config['plan_version'],
                   input_hashes=config['input_hashes'], backend=config['backend'],
                   expected_outputs=config['expected_outputs'], environment=environment,
                   started_at=now(), retry_of=retry, statistical_verification='not_performed',
                   preparation_only=config.get('preparation_only', False),
                   result_output_present=not config.get('preparation_only', False), checks=[],
                   reproducibility_scope='declared_files_and_recorded_environment')
    staged = workspace._stage(run_id, 'script_run', content, [script_id], refs, '冻结项目脚本运行材料')
    staged.mark(run_id, 'running', 'pending', '开始执行项目脚本；统计复核独立记录')
    workspace._publish(staged, writes)
    status, error, log, cancelled = 'failed', None, '', False
    try:
        process_env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
        process_env.pop('PYTHONPATH', None)
        command = [sys.executable] + (['-S'] if sys.flags.no_site else []) + ['-B', str(directory / 'run.py'), '--managed-group']
        process = run_process(command, cwd=directory, env=process_env, timeout=timeout)
        log = f'Exit code: {process.returncode}\nSTDOUT\n{process.stdout}\nSTDERR\n{process.stderr}'
        for ref in refs:
            read_verified(workspace.root, ref)
        if process.returncode:
            raise WorkflowError('项目脚本未完成，详见进程及子进程日志')
        receipt = load_json(mutable_project_path(directory, 'outputs/receipt.json'))
        if receipt != dict(token=config['token'], execution_status='completed',
                           statistical_verification='not_performed', expected_outputs=config['expected_outputs']):
            raise WorkflowError('运行回执未匹配本次冻结配置')
        for name in config['expected_outputs']:
            if not regular_bytes(directory, 'outputs/work/' + name):
                raise WorkflowError('预期输出为空')
        for category in ('code', 'inputs'):
            for name in config[category]:
                if regular_bytes(directory, 'outputs/work/' + name) != bundle[category + '/' + name]:
                    raise WorkflowError('脚本修改了本次输入或代码')
        content['checks'] = [dict(name='execution_and_frozen_files', passed=True)]
        status = 'completed'
    except KeyboardInterrupt:
        cancelled, error = True, '执行已取消，保留已有证据'
    except subprocess.TimeoutExpired:
        error = f'运行超过 {timeout} 秒，已终止进程组并保留证据'
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        log += '\n' + traceback.format_exc()
    # Preserve all readable partial files, including native logs and failures.
    output = directory / 'outputs'
    if output.exists():
        try:
            mutable_project_path(directory, 'outputs')
            for path in sorted(output.rglob('*')):
                try:
                    relative = path.relative_to(workspace.root).as_posix()
                    mutable_project_path(workspace.root, relative)
                    if path.is_dir():
                        continue
                    regular_bytes(workspace.root, relative)
                    refs.append(describe_file(workspace.root, path, scope='project', role='project_script_output'))
                except (OSError, WorkflowError) as exc:
                    status, error = 'failed', error or str(exc)
                    log += '\n' + str(exc)
        except (OSError, WorkflowError) as exc:
            status, error = 'failed', error or str(exc)
            log += '\n' + str(exc)
    # Conservatively count every started execution: statistics may be printed to
    # a log, written under arbitrary names, or observed before a later failure.
    content.update(finished_at=now(), error=error)
    if error:
        log += '\n' + error
        content['checks'].append(dict(name='execution_evidence', passed=False, detail=error))
    log_raw = log.encode('utf-8')
    refs.append(workspace._file(prefix + '/process.log', log_raw, 'execution_log'))
    staged = workspace.project.clone()
    staged.finish_script_run(run_id, content, refs, status, '保留实际执行证据；尚未独立数值复核')
    workspace._publish(staged, [(prefix + '/process.log', log_raw)])
    if cancelled:
        raise KeyboardInterrupt()
    return workspace.project.artifact(run_id)


def _read_run(workspace, run_id):
    run = workspace.project.artifact(run_id)
    if run['kind'] != 'script_run' or not run['content'].get('finished_at'):
        raise WorkflowError('需要已结束的项目脚本运行')
    for ref in run['files']:
        read_verified(workspace.root, ref)
    return run


def write_script_report(workspace, run_id):
    run = _read_run(workspace, run_id)
    data = run['content']
    current = '当前证据有效' if run['execution_status'] == 'completed' else '失败或过期记录，仅供核查'
    if run['execution_status'] == 'completed':
        try:
            workspace.project.require_executed_script(run_id)
        except WorkflowError as exc:
            current = '当前证据已失效：' + str(exc)
    text = '\n'.join(['# 项目脚本执行说明', '', f'运行：{run_id} v{run["version"]}',
        f'本次原始执行状态：{data["execution_status"]}', f'当前记录状态：{run["execution_status"]}',
        current, '统计状态：尚未独立数值复核', '',
        f'引擎：{data["backend"]}；方案：{data["plan_id"]} v{data["plan_version"]}',
        '程序退出及文件检查只说明执行情况，不认证模型设定、统计数值或因果关系。', '',
        f'错误：{data.get("error") or "无"}', '', '## 保存的材料', ''] +
        [f'- {ref["path"]}' for ref in run['files'] if ref['role'] != 'frozen_script_input']) + '\n'
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]
    relative = f'{workspace.layout["research_reports"]}/{run_id}/v{run["version"]:04d}/script-execution-{digest}.md'
    return write_version(workspace.root, relative, text.encode('utf-8'))


def import_script_output(workspace, artifact_id, run_id, output, *, reason):
    """Register processed bytes with provenance, without numerical certification."""
    run = workspace.project.require_executed_script(run_id)
    data = run['content']
    script = workspace.project.require_usable(data['script_id'])
    if script['version'] != data['script_version'] or output not in data['expected_outputs']:
        raise WorkflowError('输出不在当前脚本版本的已声明产物中')
    raw = regular_bytes(workspace.root, data['package'] + '/outputs/work/' + script_path(output))
    version = workspace._version_number(artifact_id)
    relative = f'{workspace.layout["data_processed"]}/{artifact_id}/v{version:04d}/{Path(output).name}'
    ref = workspace._file(relative, raw, 'processed_data')
    content = dict(filename=Path(output).name, role='processed_data', recovery='included',
                   script_run=dict(id=run_id, version=run['version']),
                   statistical_verification='not_performed')
    staged = workspace._stage(artifact_id, 'source', content, [run_id], [ref], reason)
    staged.mark(artifact_id, 'completed', 'passed', '处理后字节及来源版本已登记；不是处理或统计数值认证')
    workspace._publish(staged, [(relative, raw)])
    return workspace.project.artifact(artifact_id)
