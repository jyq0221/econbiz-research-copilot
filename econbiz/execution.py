"""Approved analysis -> immutable package -> real process -> checked result."""

import hashlib
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

from .analysis_environment import environment
from .execution_spec import compile_spec, prepare_sample
from .files import describe_file, project_path, read_verified
from .plans import require_approved_plan
from .run_worker import load_json
from .state import WorkflowError, now
from .workspace import encode_json, require_id


ENTRY_SCRIPT = '''"""Generated entry point; uses only the frozen econbiz code beside this file."""
import sys
from pathlib import Path
package = Path(__file__).resolve().parent
sys.path.insert(0, str(package / 'tool'))
from econbiz.run_worker import main
raise SystemExit(main(package))
'''


def validate_outputs(outputs, spec):
    try:
        result, sample, check = outputs['result'], outputs['sample'], outputs['verification']
        if result['actual_spec'] != spec['estimation']:
            raise WorkflowError('实际执行模型与方案不一致')
        if result['sample_keys'] != sample['sample_keys'] or result['nobs'] != sample['final_rows']:
            raise WorkflowError('估计样本与样本处理记录不一致')
        if result['model'] != spec['estimation']['model']:
            raise WorkflowError('实际估计方法与方案不一致')
        if check['check_status'] not in {'passed', 'failed'} or not check['checks']:
            raise WorkflowError('缺少有效独立数值核验')
        if check['check_status'] == 'passed' and not all(c['passed'] is True for c in check['checks']):
            raise WorkflowError('数值核验状态与具体检查不一致')
        # Also reject any NaN/Infinity carried through nested output structures.
        json.dumps(outputs, allow_nan=False)
    except (KeyError, TypeError, ValueError) as exc:
        raise WorkflowError(f'输出结构或数值不合法：{exc}') from exc


def execute_analysis(workspace, run_id, plan_id, *, timeout=300):
    """Save an attempt and return its actual artifact, including failed checks.

    Prerequisite errors raise before creating a run. Computation/check errors are
    recorded with evidence; require_usable/report gates reject these artifacts.
    This interface executes the fixed worker, not arbitrary untrusted scripts.
    """
    require_id(run_id)
    if run_id in workspace.project.snapshot()['artifacts']:
        raise WorkflowError('运行标识已存在；重跑须使用新的标识，保留全部旧运行')
    if type(timeout) not in {int, float} or not 0 < timeout <= 3600:
        raise WorkflowError('运行时限须在 0 到 3600 秒之间')
    plan = require_approved_plan(workspace.project, plan_id)
    inventories = [workspace.project.require_usable(dep) for dep in plan['dependencies']
                   if workspace.project.artifact(dep)['kind'] == 'inventory']
    if len(inventories) != 1:
        raise WorkflowError('正式执行需要唯一数据盘点版本')
    inventory = inventories[0]
    raw = workspace.project.read_inventory_bytes(inventory['id'])
    spec = compile_spec(plan['content'], inventory['content'])
    env = environment()
    prefix = f'{workspace.layout["research_runs"]}/{run_id}'
    directory = project_path(workspace.root, prefix)
    if directory.exists():
        raise WorkflowError('运行目录已有材料；请检查孤立记录并使用新运行标识')
    bundle = {'input.csv': raw, 'plan.json': encode_json(plan['content']),
              'inventory.json': encode_json(inventory['content']), 'spec.json': encode_json(spec),
              'environment.json': encode_json(env), 'run.py': ENTRY_SCRIPT.encode('utf-8')}
    # Snapshot the small project package, not dependency binaries or user scripts.
    source = Path(__file__).resolve().parent
    for path in sorted(source.glob('*.py')):
        bundle['tool/econbiz/' + path.name] = path.read_bytes()
    manifest = {'files': {path: hashlib.sha256(value).hexdigest() for path, value in bundle.items()},
                'plan_id': plan_id, 'plan_version': plan['version'], 'inventory_id': inventory['id'],
                'inventory_version': inventory['version'], 'created_at': now()}
    bundle['manifest.json'] = encode_json(manifest)
    writes = [(prefix + '/' + path, value) for path, value in bundle.items()]
    files = [workspace._file(path, value, 'frozen_analysis_input') for path, value in writes]
    content = dict(package=prefix, plan_id=plan_id, plan_version=plan['version'], plan=plan['content'],
                   inventory_id=inventory['id'], inventory_version=inventory['version'],
                   input_sha256=hashlib.sha256(raw).hexdigest(), environment=env,
                   manifest_sha256=hashlib.sha256(bundle['manifest.json']).hexdigest(),
                   spec=spec, started_at=now(), scope='描述统计或条件关联；数值核验不认证因果或推断假设')
    staged = workspace._stage(run_id, 'result', content, [plan_id], files, '按已确认版本冻结运行')
    staged.mark(run_id, 'running', 'pending', '输入、方案、代码及环境已冻结，开始独立进程')
    workspace._publish(staged, writes)
    outputs, log, error = {}, '', None
    execution_status, check_status = 'failed', 'failed'
    try:
        process_env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1',
                           OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1')
        process_env.pop('PYTHONPATH', None)
        completed = subprocess.run([sys.executable, '-B', str(directory / 'run.py')], cwd=directory,
                                   env=process_env, capture_output=True, text=True, timeout=timeout)
        log = f'Exit code: {completed.returncode}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}'
        # Validate frozen code/input after execution; worker cannot silently replace it.
        for ref in files:
            read_verified(workspace.root, ref)
        for name in ('sample', 'result', 'verification', 'environment', 'status', 'error'):
            path = directory / 'outputs' / (name + '.json')
            if path.exists():
                if path.is_symlink():
                    raise WorkflowError('输出不能是符号链接')
                outputs[name] = load_json(path)
        if completed.returncode != 0:
            raise WorkflowError(outputs.get('error', {}).get('message', '执行进程失败，详见日志'))
        validate_outputs(outputs, spec)
        expected_rows, expected_sample = prepare_sample(raw, spec)
        if expected_sample != outputs['sample']:
            raise WorkflowError('实际样本与冻结输入及筛选规则不一致')
        if outputs['environment']['packages'] != env['packages']:
            raise WorkflowError('实际分析依赖与冻结环境不一致')
        # Bind the freshly loaded bytes to a new independent computation, rather
        # than trusting the worker's earlier pass labels after output changes.
        from .numerical_check import verify_numerics
        outputs['worker_verification'] = outputs['verification']
        outputs['verification'] = dict(check_status='failed', rtol=1e-6, atol=1e-8, reference=None,
                                       checks=[dict(name='reference_execution', passed=False,
                                                    detail='接收方独立复核未完成；详见进程日志')])
        outputs['verification'] = verify_numerics(expected_rows, spec['estimation'], outputs['result'])
        if outputs['worker_verification']['check_status'] != 'passed':
            outputs['verification']['check_status'] = 'failed'
            outputs['verification']['checks'].append(dict(name='worker_verification', passed=False,
                                                          detail='工作进程核验未通过，保留该失败'))
        execution_status, check_status = 'completed', outputs['verification']['check_status']
    except subprocess.TimeoutExpired as exc:
        error = f'Timeout：运行超过 {timeout} 秒，保留已生成材料'
        log = error + '\n' + str(exc.stdout or '') + '\n' + str(exc.stderr or '')
    except Exception as exc:
        # This boundary owns the saved attempt. Unexpected parser/library errors
        # must leave failure evidence too; process cancellation is not caught.
        error = f'{type(exc).__name__}: {exc}'
        log += '\n' + traceback.format_exc()
    # A timeout can occur after estimation but before numerical verification.
    # Preserve partial JSON and result exposure without upgrading failed status.
    for name in ('sample', 'result', 'verification', 'environment', 'status', 'error'):
        path = directory / 'outputs' / (name + '.json')
        if name not in outputs and path.is_file() and not path.is_symlink():
            try:
                outputs[name] = load_json(path)
            except Exception as exc:
                log += f'\n部分输出不可解析：{name}：{exc}'
    result_path = directory / 'outputs/result.json'
    content['result_output_present'] = result_path.is_file() and not result_path.is_symlink()
    content.update(outputs, finished_at=now(), error=error)
    content['execution_status'] = execution_status
    content['check_status'] = check_status
    log_relative = prefix + '/process.log'
    log_raw = log.encode('utf-8')
    final_files = list(files) + [workspace._file(log_relative, log_raw, 'execution_log')]
    final_writes = [(log_relative, log_raw)]
    if 'worker_verification' in outputs:
        relative = prefix + '/outputs/parent-verification.json'
        check_raw = encode_json(outputs['verification'])
        final_writes.append((relative, check_raw))
        final_files.append(workspace._file(relative, check_raw, 'final_numerical_check'))
    output_dir = directory / 'outputs'
    if output_dir.is_dir() and not output_dir.is_symlink():
        for path in sorted(output_dir.glob('*.json')):
            if not path.is_symlink():
                final_files.append(describe_file(workspace.root, path, scope='project', role='analysis_output'))
    staged = workspace.project.clone()
    staged.finish_result(run_id, content, final_files, execution_status, check_status,
                         '保存实际执行及独立核验记录，失败证据不依赖上游仍有效')
    workspace._publish(staged, final_writes)
    return workspace.project.artifact(run_id)
