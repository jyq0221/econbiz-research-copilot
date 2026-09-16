"""Approved analysis -> immutable package -> real process -> checked result."""

import hashlib
import json
import os
import subprocess
import sys
import traceback
import uuid
from pathlib import Path

from .analysis_environment import environment
from .execution_spec import compile_spec, prepare_sample
from .files import describe_file, project_path, mutable_project_path, read_verified
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


def execute_analysis(workspace, run_id, plan_id, *, timeout=300, backend='python',
                     stata_executable=None, replication_of=None):
    """Save an attempt and return its actual artifact, including failed checks.

    Prerequisite errors raise before creating a run. Computation/check errors are
    recorded with evidence; require_usable/report gates reject these artifacts.
    This interface executes the fixed worker, not arbitrary untrusted scripts.
    """
    require_id(run_id)
    if backend not in ('python', 'stata'):
        raise WorkflowError('执行引擎须明确为 python 或 stata；默认使用 python')
    if backend == 'python' and stata_executable is not None:
        raise WorkflowError('stata_executable 仅适用于显式 Stata 执行')
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
    env['backend'] = backend
    replication = None
    if replication_of is not None:
        previous = workspace.project.require_usable(replication_of)
        data = previous['content']
        if (previous['kind'] != 'result' or data.get('plan_id') != plan_id
                or data.get('plan_version') != plan['version'] or data.get('spec') != spec
                or data.get('input_sha256') != hashlib.sha256(raw).hexdigest()):
            raise WorkflowError('复现来源须为同一当前方案及输入的已核验运行')
        replication = dict(id=previous['id'], version=previous['version'])
    native_bundle = {}
    run_token = uuid.uuid4().hex if backend == 'stata' else None
    if backend == 'stata':
        from .stata_runtime import probe_stata
        from .stata_engine import build_bundle
        env['stata'] = probe_stata(stata_executable)
        rows, _ = prepare_sample(raw, spec)
        native_bundle = {'stata/' + name: value for name, value in
                         build_bundle(rows, spec['estimation'], run_token=run_token).items()}
    execution = dict(backend=backend, replication_of=replication, timeout=timeout)
    if run_token is not None:
        execution['run_token'] = run_token
    prefix = f'{workspace.layout["research_runs"]}/{run_id}'
    directory = project_path(workspace.root, prefix)
    if directory.exists():
        raise WorkflowError('运行目录已有材料；请检查孤立记录并使用新运行标识')
    bundle = {'input.csv': raw, 'plan.json': encode_json(plan['content']),
              'inventory.json': encode_json(inventory['content']), 'spec.json': encode_json(spec),
              'environment.json': encode_json(env), 'execution.json': encode_json(execution),
              'run.py': ENTRY_SCRIPT.encode('utf-8'), **native_bundle}
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
                   backend=backend, replication_of=replication,
                   manifest_sha256=hashlib.sha256(bundle['manifest.json']).hexdigest(),
                   spec=spec, started_at=now(), scope='描述统计或条件关联；数值核验不认证因果或推断假设')
    staged = workspace._stage(run_id, 'result', content, [plan_id], files, '按已确认版本冻结运行')
    staged.mark(run_id, 'running', 'pending', '输入、方案、代码及环境已冻结，开始独立进程')
    workspace._publish(staged, writes)
    outputs, log, error, cancelled = {}, '', None, False
    execution_status, check_status = 'failed', 'failed'
    try:
        process_env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1',
                           OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1')
        process_env.pop('PYTHONPATH', None)
        process_env.pop('ECONBIZ_WORKER_GROUP', None)
        args = [sys.executable, '-B', str(directory / 'run.py')]
        if backend == 'stata':
            from .processes import run_process
            completed = run_process(args + ['--managed-group'], cwd=directory,
                                    env=process_env, timeout=timeout)
        else:
            completed = subprocess.run(args, cwd=directory, env=process_env,
                                       capture_output=True, text=True, timeout=timeout)
        log = f'Exit code: {completed.returncode}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}'
        # Validate frozen code/input after execution; worker cannot silently replace it.
        for ref in files:
            read_verified(workspace.root, ref)
        mutable_project_path(workspace.root, prefix + '/outputs')
        if backend == 'stata':
            mutable_project_path(workspace.root, prefix + '/outputs/native')
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
        if (outputs['environment'].get('backend', 'python') != backend
                or outputs['environment'].get('stata') != env.get('stata')
                or outputs['status'].get('backend', 'python') != backend):
            raise WorkflowError('实际执行引擎或 Stata 环境与冻结配置不一致')
        # Bind the freshly loaded bytes to a new independent computation, rather
        # than trusting the worker's earlier pass labels after output changes.
        from .numerical_check import verify_numerics
        outputs['worker_verification'] = outputs['verification']
        outputs['verification'] = dict(check_status='failed', rtol=1e-6, atol=1e-8, reference=None,
                                       checks=[dict(name='reference_execution', passed=False,
                                                    detail='接收方独立复核未完成；详见进程日志')])
        if backend == 'stata':
            from .stata_engine import read_result
            native_result = read_result(expected_rows, spec['estimation'], directory / 'outputs/native',
                                        run_token=run_token)
            if native_result != outputs['result']:
                raise WorkflowError('结构化结果与实际 Stata 原生输出不一致')
        outputs['verification'] = verify_numerics(expected_rows, spec['estimation'], outputs['result'], backend=backend)
        if outputs['worker_verification']['check_status'] != 'passed':
            outputs['verification']['check_status'] = 'failed'
            outputs['verification']['checks'].append(dict(name='worker_verification', passed=False,
                                                          detail='工作进程核验未通过，保留该失败'))
        execution_status, check_status = 'completed', outputs['verification']['check_status']
    except subprocess.TimeoutExpired as exc:
        error = f'Timeout：运行超过 {timeout} 秒，保留已生成材料'
        log = error + '\n' + str(exc.stdout or '') + '\n' + str(exc.stderr or '')
    except KeyboardInterrupt:
        cancelled = True
        error = 'Cancelled：本次执行已取消，保留失败与部分输出'
        log += '\n' + error
    except Exception as exc:
        # This boundary owns the saved attempt. Unexpected parser/library errors
        # must leave failure evidence too.
        error = f'{type(exc).__name__}: {exc}'
        log += '\n' + traceback.format_exc()
    # A timeout can occur after estimation but before numerical verification.
    # Preserve partial JSON and result exposure without upgrading failed status.
    safe_outputs = True
    try:
        mutable_project_path(workspace.root, prefix + '/outputs')
    except WorkflowError as exc:
        safe_outputs = False
        execution_status, check_status = 'failed', 'failed'
        error = error or str(exc)
        log += '\n' + str(exc)
    safe_native = safe_outputs
    if backend == 'stata' and safe_outputs:
        try:
            mutable_project_path(workspace.root, prefix + '/outputs/native')
        except WorkflowError as exc:
            safe_native = False
            execution_status, check_status = 'failed', 'failed'
            error = error or str(exc)
            log += '\n' + str(exc)
    for name in ('sample', 'result', 'verification', 'environment', 'status', 'error'):
        path = directory / 'outputs' / (name + '.json')
        if safe_outputs and name not in outputs and path.is_file() and not path.is_symlink():
            try:
                outputs[name] = load_json(path)
            except Exception as exc:
                log += f'\n部分输出不可解析：{name}：{exc}'
    result_path = directory / 'outputs/result.json'
    exposed = [result_path]
    if backend == 'stata' and safe_native:
        exposed += [directory / 'outputs/native' / name for name in
                    ('descriptive.csv', 'coefficients.csv', 'covariance.csv', 'table.csv')]
    content['result_output_present'] = bool(safe_outputs and any(
        p.is_file() and not p.is_symlink() and p.stat().st_size for p in exposed))
    final_files, final_writes = list(files), []
    output_dir = directory / 'outputs'
    if safe_outputs and output_dir.is_dir():
        try:
            for path in sorted(output_dir.rglob('*')):
                try:
                    relative = path.relative_to(workspace.root)
                    mutable_project_path(workspace.root, relative)
                    if path.is_file():
                        role = 'stata_native_output' if path.is_relative_to(output_dir / 'native') else 'analysis_output'
                        final_files.append(describe_file(workspace.root, path, scope='project', role=role))
                except (OSError, WorkflowError) as exc:
                    execution_status, check_status = 'failed', 'failed'
                    error = error or str(exc)
                    log += f'\n输出证据登记失败：{path.name}：{exc}'
        except OSError as exc:
            execution_status, check_status = 'failed', 'failed'
            error = error or str(exc)
            log += f'\n输出目录不可遍历：{exc}'
    final_check = outputs.get('verification')
    if execution_status == 'failed' and isinstance(final_check, dict) and final_check.get('check_status') == 'passed':
        outputs.setdefault('worker_verification', outputs['verification'])
        outputs['verification'] = dict(check_status='failed', rtol=1e-6, atol=1e-8, reference=None,
                                       checks=[dict(name='execution_evidence', passed=False,
                                                    detail='执行或证据保存未完成；详见进程日志')])
    content.update(outputs, finished_at=now(), error=error)
    content['execution_status'] = execution_status
    content['check_status'] = check_status
    log_relative = prefix + '/process.log'
    log_raw = log.encode('utf-8')
    final_files.append(workspace._file(log_relative, log_raw, 'execution_log'))
    final_writes.append((log_relative, log_raw))
    if 'worker_verification' in outputs:
        relative = prefix + '/outputs/parent-verification.json'
        check_raw = encode_json(outputs['verification'])
        final_writes.append((relative, check_raw))
        final_files.append(workspace._file(relative, check_raw, 'final_numerical_check'))
    staged = workspace.project.clone()
    staged.finish_result(run_id, content, final_files, execution_status, check_status,
                         '保存实际执行及独立核验记录，失败证据不依赖上游仍有效')
    workspace._publish(staged, final_writes)
    if cancelled:
        raise KeyboardInterrupt()
    return workspace.project.artifact(run_id)
