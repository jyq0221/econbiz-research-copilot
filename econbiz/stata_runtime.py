"""Opt-in Stata discovery and identity; never imported by the Python path."""

import hashlib
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path

from .processes import run_process
from .state import WorkflowError


PROBE = '''version 19.0
clear all
set more off
file open probe using "probe.tsv", write replace
file write probe "version" _tab "`c(stata_version)'" _n
file write probe "build_date" _tab "`c(born_date)'" _n
file write probe "flavor" _tab "`c(flavor)'" _n
file write probe "os" _tab "`c(os)'" _n
file write probe "complete" _tab "1" _n
file close probe
exit, clear
'''


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _ado_identity(executable):
    # The validated macOS console resides inside the application bundle. Include
    # all shipped ado/Mata implementation files, not manuals or license material.
    base = Path(executable).parents[3] / 'ado' / 'base'
    if not base.is_dir():
        raise WorkflowError('找不到 Stata 安装中的官方 ado/base，无法冻结命令环境')
    digest = hashlib.sha256()
    for path in sorted(base.rglob('*')):
        if path.is_file() and path.suffix in {'.ado', '.mo', '.mlib', '.mata', '.matah',
                                           '.class', '.py', '.jar', '.plugin', '.dll', '.dylib', '.so'}:
            digest.update(path.relative_to(base).as_posix().encode('utf-8') + b'\0')
            digest.update(bytes.fromhex(_digest(path)))
    return dict(path=str(base), sha256=digest.hexdigest())


def check_stata_identity(runtime):
    try:
        if _digest(runtime['executable']) != runtime['executable_sha256']:
            raise WorkflowError('Stata 可执行文件与冻结环境不一致')
        if _ado_identity(runtime['executable']) != runtime['ado_identity']:
            raise WorkflowError('Stata 官方命令与冻结环境不一致')
    except (OSError, KeyError, IndexError, TypeError) as exc:
        raise WorkflowError('无法核对冻结的 Stata 环境') from exc


def run_stata(runtime, do_file, cwd, *, timeout=240, log_path=None):
    check_stata_identity(runtime)
    do_file, cwd = Path(do_file).resolve(), Path(cwd).resolve()
    if do_file.parent != cwd or not do_file.is_file():
        raise WorkflowError('Stata do-file 必须位于本次运行目录')
    args = [runtime['executable'], '-b', '-q', 'do', do_file.name]
    nested = runtime.get('_managed_group') is True
    if nested and (os.name != 'posix' or os.getpgrp() != os.getpid()):
        raise WorkflowError('嵌套 Stata 执行需要拥有进程组的受控工作进程')
    # When nested, the outer worker owns the one process group and its deadline.
    result = run_process(args, cwd=cwd, timeout=None if nested else timeout,
                         new_group=not nested, **({'log_path': log_path} if log_path else {}))
    check_stata_identity(runtime)
    return result


def probe_stata(executable=None):
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise WorkflowError('当前 Stata 接入仅验收 macOS arm64；其他平台需单独验收')
    requested = executable or os.environ.get('ECONBIZ_STATA_EXECUTABLE')
    if requested is None:
        requested = next((p for name in ('stata-mp', 'stata-se', 'stata')
                          if (p := shutil.which(name))), None)
    if not requested or not Path(requested).is_file() or not os.access(requested, os.X_OK):
        raise WorkflowError('未找到可执行的 Stata；可选择 Python 完成同样的受支持分析')
    path = str(Path(requested).resolve())
    runtime = dict(executable=path, executable_sha256=_digest(path),
                   ado_identity=_ado_identity(path), platform=platform.platform())
    with tempfile.TemporaryDirectory(prefix='econbiz-stata-probe-') as directory:
        root = Path(directory)
        script = root / 'probe.do'
        script.write_text(PROBE, encoding='utf-8')
        try:
            completed = run_stata(runtime, script, root, timeout=20)
            pairs = [line.split('\t') for line in (root / 'probe.tsv').read_text('utf-8').splitlines()]
            values = dict(pairs)
        except Exception as exc:
            raise WorkflowError('Stata 启动探针失败；请检查安装、授权和启动环境') from exc
        if completed.returncode != 0 or values.pop('complete', None) != '1':
            raise WorkflowError('Stata 未完成启动探针')
        if set(values) != {'version', 'build_date', 'flavor', 'os'}:
            raise WorkflowError('Stata 启动信息不完整')
        # The macOS console build reports c(os)=Unix; the host platform was
        # checked separately, so do not infer it from the GUI bundle name.
        if values['version'] != '19' or values['os'] not in {'MacOSX', 'Unix'}:
            raise WorkflowError('当前只验收 Stata 19 / macOS，其他环境不能自动沿用')
    return dict(runtime, **values)
