"""Portable references and immutable local files; no implicit external writes."""

import hashlib
import os
import re
import tempfile
from pathlib import Path

from .state import WorkflowError, require_text


def validate_reference(ref):
    if not isinstance(ref, dict):
        raise WorkflowError('文件引用必须是字典')
    for key in ('path', 'role', 'sha256'):
        require_text(ref.get(key), f'文件 {key}')
    if not re.fullmatch(r'[0-9a-f]{64}', ref['sha256']):
        raise WorkflowError('文件摘要必须是 SHA-256')
    if type(ref.get('size_bytes')) is not int or ref['size_bytes'] < 0:
        raise WorkflowError('文件长度必须是非负整数')
    scope = ref.get('scope')
    path = Path(ref['path'])
    if scope not in {'project', 'external'}:
        raise WorkflowError('未知文件范围')
    if scope == 'project' and (path.is_absolute() or '..' in path.parts or not path.parts):
        raise WorkflowError('项目文件必须是无上级跳转的相对路径')
    if scope == 'external' and not path.is_absolute():
        raise WorkflowError('外部来源必须显式提供绝对路径')


def project_path(root, relative):
    if root is None:
        raise WorkflowError('读取项目文件需要项目根目录')
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise WorkflowError(f'项目路径越界：{relative}')
    root = Path(root).resolve()
    try:
        resolved = (root / path).resolve()
        resolved.relative_to(root)
    except (ValueError, OSError, RuntimeError) as exc:
        raise WorkflowError(f'项目路径越界或不可解析：{relative}') from exc
    return resolved


def resolve_reference(root, ref):
    validate_reference(ref)
    return project_path(root, ref['path']) if ref['scope'] == 'project' else Path(ref['path'])


def describe_file(root, path, *, scope, role):
    require_text(role, '材料用途')
    original = Path(path)
    if scope == 'project':
        if root is None or '..' in original.parts:
            raise WorkflowError(f'项目路径越界：{path}')
        try:
            relative = original.resolve().relative_to(Path(root).resolve()) if original.is_absolute() else original
        except ValueError as exc:
            raise WorkflowError(f'项目路径越界：{path}') from exc
        actual = project_path(root, relative)
        stored = relative.as_posix()
    elif scope == 'external' and original.is_absolute():
        actual, stored = original, str(original)
    else:
        raise WorkflowError('外部来源必须显式提供绝对路径；项目来源使用受控路径')
    digest, size = hashlib.sha256(), 0
    try:
        with actual.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise WorkflowError(f'材料不可读取：{actual}：{exc}') from exc
    return dict(scope=scope, path=stored, sha256=digest.hexdigest(), size_bytes=size, role=role)


def verify_file(root, ref):
    actual = resolve_reference(root, ref)
    current = describe_file(root, actual, scope=ref['scope'], role=ref['role'])
    if any(current[key] != ref[key] for key in ('sha256', 'size_bytes')):
        raise WorkflowError(f'材料内容已改变：{ref["path"]}；需核实并重新盘点')
    return actual


def read_verified(root, ref):
    actual = resolve_reference(root, ref)
    try:
        raw = actual.read_bytes()
    except OSError as exc:
        raise WorkflowError(f'材料不可读取：{actual}：{exc}') from exc
    if len(raw) != ref['size_bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise WorkflowError(f'材料内容已改变：{ref["path"]}；需核实并重新盘点')
    return raw


def write_version(root, relative, raw):
    """Publish complete bytes without replacing an existing version (safe retry)."""
    target = project_path(root, relative)
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != raw:
                raise WorkflowError(f'版本文件已存在且内容不同：{target}；保留原文件')
        return target
    except OSError as exc:
        raise WorkflowError(f'版本保存失败：{target}：{exc}') from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
