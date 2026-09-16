"""File and environment contracts for trusted, agent-authored project code.

These are provenance checks, not an arbitrary-code security sandbox.
"""

import hashlib
import importlib.metadata
import platform
import re
import stat
import sys
from pathlib import PurePosixPath

from .files import mutable_project_path
from .state import WorkflowError


def script_path(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise WorkflowError('脚本文件路径须为明确相对路径')
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value or '..' in path.parts
            or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', p) or p.startswith('_econbiz') for p in path.parts)
            or value in {'.', 'tool', 'run.py', 'manifest.json'}):
        raise WorkflowError('脚本路径仅允许安全相对文件名，且不能占用运行器文件')
    return value


def nonoverlapping(paths):
    paths = [PurePosixPath(p) for p in paths]
    if len(set(paths)) != len(paths) or any(a in b.parents for a in paths for b in paths if a != b):
        raise WorkflowError('代码、输入和输出路径不能重叠')


def regular_bytes(root, relative):
    path = mutable_project_path(root, relative)
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise WorkflowError(f'证据文件不是普通文件：{relative}')
        return path.read_bytes()
    except OSError as exc:
        raise WorkflowError(f'证据文件无法读取：{relative}：{exc}') from exc


def script_environment():
    packages = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get('Name')
        if name:
            packages[re.sub(r'[-_.]+', '-', name).lower()] = distribution.version
    return dict(python=platform.python_version(), platform=platform.platform(),
                executable=sys.executable, packages=dict(sorted(packages.items())))


def check_script_environment(expected):
    actual = script_environment()
    for field in ('python', 'platform', 'packages'):
        if actual[field] != expected[field]:
            raise WorkflowError(f'项目脚本环境已变化：{field}；请新建运行记录')
    return actual


def verify_manifest(package, manifest):
    for relative, digest in manifest['files'].items():
        raw = regular_bytes(package, relative)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise WorkflowError(f'冻结输入或代码已改变：{relative}')
