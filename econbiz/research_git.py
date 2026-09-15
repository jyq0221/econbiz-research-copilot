"""Opt-in, local-only Git for one research workspace and explicit text paths."""

import shutil
import subprocess
from pathlib import Path

from .files import mutable_project_path
from .state import WorkflowError, require_text


TEXT_SUFFIXES = {'.md', '.txt', '.json', '.py', '.do', '.r', '.R', '.tex', '.bib', '.csv', '.tsv', '.yaml', '.yml'}
CONFIG_ID = 'research-git-config'


def _git(workspace, *args):
    executable = shutil.which('git')
    if executable is None:
        raise WorkflowError('Git 不可用；本地文件历史仍可使用')
    result = subprocess.run([executable, '--literal-pathspecs', '-C', str(workspace.root), *args], capture_output=True, text=True)
    if result.returncode:
        raise WorkflowError(f'Git 操作未完成：{result.stderr.strip() or result.stdout.strip()}')
    return result.stdout.strip()


def _safe_path(workspace, relative):
    if not isinstance(relative, str) or not relative.strip() or relative == '.':
        raise WorkflowError('必须提供明确研究文件路径')
    path = mutable_project_path(workspace.root, relative)
    parts = Path(relative).parts
    if any(part.startswith('.') or part.lower() in {'credentials', 'secrets', 'id_rsa', 'id_ed25519'} for part in parts):
        raise WorkflowError('隐藏配置或凭据不属于此工具跟踪范围')
    allowed = [workspace.path(area) for area in workspace.layout if area not in
               {'data_raw', 'data_interim', 'data_processed', 'literature_sources', 'research_runs'}]
    allowed += [workspace.root / 'research_state.json', workspace.root / '研究进展.md']
    if not any(path == parent or parent in path.parents for parent in allowed):
        raise WorkflowError(f'路径不在代码、文字和元数据范围：{relative}')
    return path


def _repository(workspace):
    git_path = workspace.root / '.git'
    if git_path.is_symlink() or not git_path.is_dir():
        raise WorkflowError('当前研究没有独立 Git 仓库；禁止使用父级工具仓库')
    if Path(_git(workspace, 'rev-parse', '--show-toplevel')).resolve() != workspace.root:
        raise WorkflowError('Git 根目录不等于当前研究根目录')


def enable_git(workspace, tracked_paths):
    if not isinstance(tracked_paths, (list, tuple)) or not tracked_paths:
        raise WorkflowError('启用研究 Git 需明确跟踪范围')
    normalized = []
    for relative in tracked_paths:
        path = _safe_path(workspace, relative)
        normalized.append(path.relative_to(workspace.root).as_posix())
    if len(set(normalized)) != len(normalized):
        raise WorkflowError('跟踪范围重复')
    if not (workspace.root / '.git').exists():
        _git(workspace, 'init', '-q', '.')
    _repository(workspace)
    staged = workspace._stage(CONFIG_ID, 'research_git', {'tracked_paths': normalized, 'local_only': True}, [], [],
                              '用户选择启用单项研究 Git 及此跟踪范围')
    staged.mark(CONFIG_ID, 'completed', 'passed', '研究根与选择范围已检查；未设置远端')
    workspace._publish(staged)
    return {'enabled': True, 'tracked_paths': normalized, 'remote_added': False}


def preview_changes(workspace, paths):
    _repository(workspace)
    config = workspace.project.require_usable(CONFIG_ID)
    if config['kind'] != 'research_git':
        raise WorkflowError('缺少已登记的 Git 范围')
    if not isinstance(paths, (list, tuple)) or not paths:
        raise WorkflowError('提交前需明确文件列表')
    allowed = [_safe_path(workspace, path) for path in config['content']['tracked_paths']]
    collected = set()
    for relative in paths:
        path = _safe_path(workspace, relative)
        if not any(path == parent or parent in path.parents for parent in allowed):
            raise WorkflowError(f'路径超出已选择范围：{relative}')
        if not path.exists():
            raise WorkflowError(f'文件不存在；删除提交需另行核实：{relative}')
        candidates = list(path.rglob('*')) if path.is_dir() else [path]
        for candidate in candidates:
            name = candidate.relative_to(workspace.root).as_posix()
            _safe_path(workspace, name)
            if not candidate.is_file():
                continue
            if candidate.suffix not in TEXT_SUFFIXES or candidate.stat().st_size > 1024 * 1024:
                raise WorkflowError(f'首版研究 Git 仅支持单个不超过 1 MiB 的文本/代码：{name}')
            try:
                candidate.read_text('utf-8')
            except UnicodeError as exc:
                raise WorkflowError(f'非 UTF-8 文本未纳入 Git：{name}') from exc
            collected.add(name)
    if not collected:
        raise WorkflowError('所选范围没有可提交文件')
    return {'paths': sorted(collected), 'local_only': True}


def commit_changes(workspace, paths, message):
    require_text(message, '提交说明')
    preview = preview_changes(workspace, paths)
    if _git(workspace, 'diff', '--cached', '--name-only', '-z'):
        raise WorkflowError('研究仓库已有暂存内容；先核实归属，不顺带提交')
    # Fail on absent identity before touching the index; never fabricate user identity.
    _git(workspace, 'var', 'GIT_AUTHOR_IDENT')
    _git(workspace, 'var', 'GIT_COMMITTER_IDENT')
    _git(workspace, 'add', '--', *preview['paths'])
    if not _git(workspace, 'diff', '--cached', '--name-only', '-z'):
        return dict(preview, committed=False, reason='所选文件没有变化')
    try:
        _git(workspace, 'commit', '-m', message)
    except WorkflowError as exc:
        raise WorkflowError(f'{exc}；所选文件可能仍在暂存区，请核对后重试') from exc
    return dict(preview, committed=True, commit=_git(workspace, 'rev-parse', 'HEAD'))
