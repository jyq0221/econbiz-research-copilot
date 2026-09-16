"""Execute a frozen custom script in a fresh working directory."""

import argparse
import os
import sys
import traceback
import uuid
from pathlib import Path

from .processes import run_process
from .run_worker import load_json, save_json
from .script_contracts import check_script_environment, regular_bytes, verify_manifest
from .state import WorkflowError
from .workspace import require_id


PYTHON_ENTRY = '''import runpy, sys
from pathlib import Path
entrypoint, tool = sys.argv[1:]
sys.path.insert(0, tool)
sys.path.insert(0, str(Path(entrypoint).resolve().parent))
sys.argv = [entrypoint]
runpy.run_path(entrypoint, run_name='__main__')
'''


def main(package):
    parser = argparse.ArgumentParser(description='重跑冻结项目脚本；输出始终使用新目录')
    parser.add_argument('--output', default='outputs')
    parser.add_argument('--managed-group', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    require_id(args.output)
    package = Path(package).resolve()
    manifest = load_json(package / 'manifest.json')
    verify_manifest(package, manifest)
    config = load_json(package / 'script.json')
    env = load_json(package / 'environment.json')
    check_script_environment(env)
    output = package / args.output
    output.mkdir(exist_ok=False)
    work = output / 'work'
    work.mkdir()
    try:
        frozen = {}
        for category in ('code', 'inputs'):
            for name in config[category]:
                raw = regular_bytes(package, category + '/' + name)
                target = work / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                frozen[name] = raw
        process_env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        process_env.pop('PYTHONPATH', None)
        if config['backend'] == 'python':
            process = run_process([sys.executable] + (['-S'] if sys.flags.no_site else []) + ['-B', '-c', PYTHON_ENTRY,
                                   str(work / config['entrypoint']), str(package / 'tool')],
                                  cwd=work, timeout=config['timeout'], env=process_env,
                                  new_group=not args.managed_group, log_path=output / 'child.log')
        else:
            from .stata_runtime import run_stata
            token = uuid.uuid4().hex
            wrapper = work / '_econbiz_run.do'
            wrapper.write_text('version 19.0\nset more off\nglobal S_ADO "BASE;."\n'
                               f'do "{config["entrypoint"]}"\n'
                               'file open ebcomplete using "_econbiz_done.txt", write replace\n'
                               f'file write ebcomplete "{token}"\nfile close ebcomplete\n', encoding='utf-8')
            process = run_stata(dict(env['stata'], _managed_group=args.managed_group),
                                wrapper, work, timeout=config['timeout'], log_path=output / 'child.log')
        with (output / 'child.log').open('a', encoding='utf-8') as log:
            log.write(f'\nExit code: {process.returncode}\n')
        if process.returncode:
            raise WorkflowError('项目脚本执行失败，详见 child.log')
        if config['backend'] == 'stata' and regular_bytes(work, '_econbiz_done.txt').decode() != token:
            raise WorkflowError('Stata 未完成本次脚本，不能按退出码认定成功')
        for name, raw in frozen.items():
            if regular_bytes(work, name) != raw:
                raise WorkflowError(f'执行期间修改了输入或代码：{name}')
        for name in config['expected_outputs']:
            if not regular_bytes(work, name):
                raise WorkflowError(f'预期输出为空：{name}')
        verify_manifest(package, manifest)
        check_script_environment(env)
        save_json(output / 'receipt.json', dict(token=config['token'], execution_status='completed',
                  statistical_verification='not_performed', expected_outputs=config['expected_outputs']))
        return 0
    except Exception as exc:
        save_json(output / 'error.json', dict(type=type(exc).__name__, message=str(exc)))
        traceback.print_exc()
        return 1
