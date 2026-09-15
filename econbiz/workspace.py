"""Single-writer research workspace. Files first, authoritative state second."""

import hashlib
import json
import re
from pathlib import Path

from .audit import audit_csv
from .files import describe_file, project_path, read_verified, resolve_reference, write_version
from .state import Project, WorkflowError, json_copy, require_text
from .progress import render_progress
from .state import write_json


LAYOUT = {
    **{f'literature_{name}': f'literature/{name}' for name in ('sources', 'notes', 'evidence')},
    **{f'data_{name}': f'data/{name}' for name in ('raw', 'interim', 'processed', 'metadata')},
    **{f'research_{name}': f'research/{name}' for name in
       ('plans', 'tasks', 'decisions', 'sessions', 'code', 'runs', 'reports', 'drafts', 'history')},
}
SOURCE_AREAS = {'raw_data': 'data_raw', 'literature_source': 'literature_sources',
                'data_metadata': 'data_metadata', 'external_result': 'research_reports',
                'research_material': 'research_drafts'}


def require_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise WorkflowError('标识只可包含字母、数字、连字符和下划线')


def encode_json(content):
    return (json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


class Workspace:
    def __init__(self, root, project):
        self.root = Path(root).resolve()
        self.project = project
        self.last_receipt = None
        state = project.snapshot()
        layout = state['artifacts'].get('workspace-layout')
        if layout is not None:
            if layout['kind'] != 'workspace_layout' or set(layout['content']) != set(LAYOUT):
                raise WorkflowError('目录映射损坏')
            self.layout = json_copy(layout['content'])
        else:
            self.layout = dict(LAYOUT, research_reports='reports')
        for path in self.layout.values():
            if not isinstance(path, str):
                raise WorkflowError('目录映射必须是相对路径')
            project_path(self.root, path)

    @classmethod
    def create(cls, root, project_id, direction):
        root = Path(root).absolute()
        if root.exists() or root.is_symlink():
            raise WorkflowError(f'项目位置已存在，不能覆盖：{root}')
        project = Project.create(project_id, direction, base_dir=root)
        project.add('workspace-layout', 'workspace_layout', LAYOUT)
        project.mark('workspace-layout', 'completed', 'passed', '三类目录约定已保存')
        try:
            root.mkdir(parents=True, exist_ok=False)
            for folder in ('literature', 'data', 'research'):
                (root / folder).mkdir()
            workspace = cls(root, project)
            workspace.save()
            return workspace
        except OSError as exc:
            raise WorkflowError(f'建项未完成：{root}：{exc}；已写内容保留供核查') from exc

    @classmethod
    def open(cls, root):
        root = Path(root).resolve()
        state_path = project_path(root, 'research_state.json')
        return cls(root, Project.load(state_path))

    def path(self, area):
        if area not in self.layout:
            raise WorkflowError(f'未知项目目录：{area}')
        return project_path(self.root, self.layout[area])

    def _version_number(self, artifact_id):
        require_id(artifact_id)
        return self.project.snapshot()['artifacts'].get(artifact_id, {}).get('version', 0) + 1

    def _file(self, relative, raw, role):
        project_path(self.root, relative)
        return dict(scope='project', path=relative, sha256=hashlib.sha256(raw).hexdigest(),
                    size_bytes=len(raw), role=role)

    def _stage(self, artifact_id, kind, content, dependencies, files, reason):
        require_id(artifact_id)
        require_text(reason, '保存原因')
        staged = self.project.clone()
        if artifact_id in staged.snapshot()['artifacts']:
            if staged.artifact(artifact_id)['kind'] != kind:
                raise WorkflowError('修订不能改变记录种类')
            staged.revise(artifact_id, content, reason, dependencies=dependencies, files=files)
        else:
            staged.add(artifact_id, kind, content, dependencies, files=files)
        return staged

    def _publish(self, staged, writes=()):
        try:
            for relative, raw in writes:
                write_version(self.root, relative, raw)
            staged.save(project_path(self.root, 'research_state.json'))
        except (OSError, WorkflowError) as exc:
            raise WorkflowError(f'状态保存未完成，旧状态及已写版本文件保留：{exc}') from exc
        self.project = staged
        self.last_receipt = self._update_view()
        return self.last_receipt

    def _update_view(self):
        receipt = {'state_saved': True, 'view_saved': False}
        try:
            raw = render_progress(self.project).encode('utf-8')
            view = project_path(self.root, '研究进展.md')
            meta = project_path(self.root, self.layout['research_history'] + '/progress-view.json')
            previous_hash = None
            if meta.exists():
                try:
                    previous_hash = json.loads(meta.read_text('utf-8')).get('sha256')
                except (ValueError, AttributeError):
                    pass
            if view.exists():
                old = view.read_bytes()
                digest = hashlib.sha256(old).hexdigest()
                if digest != previous_hash and old != raw:
                    relative = f'{self.layout["research_history"]}/view-edits/{digest}.md'
                    write_version(self.root, relative, old)
                    receipt['unreviewed_edit'] = relative
            # View replacement is atomic, like authoritative state, but independently fallible.
            from .state import write_text
            write_text(view, raw.decode('utf-8'))
            write_json(meta, {'sha256': hashlib.sha256(raw).hexdigest()})
            receipt['view_saved'] = True
        except (OSError, WorkflowError, ValueError) as exc:
            receipt['view_error'] = str(exc)
        return receipt

    def save(self):
        return self._publish(self.project.clone())

    def import_file(self, artifact_id, source, *, role, copy=True, reason):
        version = self._version_number(artifact_id)
        require_text(reason, '材料登记原因')
        if role not in SOURCE_AREAS or type(copy) is not bool:
            raise WorkflowError('未知材料用途或复制选项')
        source = Path(source)
        if not copy and not source.is_absolute():
            raise WorkflowError('外部索引需显式绝对路径')
        original = describe_file(self.root, source.absolute(), scope='external', role=role)
        raw = read_verified(self.root, original) if copy else None
        writes = []
        ref = original
        if copy:
            relative = f'{self.layout[SOURCE_AREAS[role]]}/{artifact_id}/v{version:04d}/{source.name}'
            ref = self._file(relative, raw, role)
            writes.append((relative, raw))
        content = dict(filename=source.name, role=role, recovery='included' if copy else 'external_required')
        staged = self._stage(artifact_id, 'source', content, [], [ref], reason)
        staged.mark(artifact_id, 'completed', 'passed', '来源字节已登记；不认证材料主张')
        self._publish(staged, writes)
        return self.project.artifact(artifact_id)

    def relocate_source(self, artifact_id, new_path, *, reason):
        old = self.project.artifact(artifact_id)
        if old['kind'] != 'source' or len(old.get('files', [])) != 1 or old['files'][0]['scope'] != 'external':
            raise WorkflowError('只可重新定位显式外部来源；项目内材料随整个目录移动')
        ref = describe_file(self.root, new_path, scope='external', role=old['files'][0]['role'])
        if any(ref[key] != old['files'][0][key] for key in ('sha256', 'size_bytes')):
            raise WorkflowError('来源内容不同，必须导入新版本并重新盘点')
        staged = self._stage(artifact_id, 'source', old['content'], list(old['dependencies']), [ref], reason)
        staged.mark(artifact_id, 'completed', 'passed', '相同内容已重新定位；下游需重新核对引用')
        self._publish(staged)
        return self.project.artifact(artifact_id)

    def audit(self, artifact_id, source_id, *, entity, time, numeric=()):
        version = self._version_number(artifact_id)
        source = self.project.require_usable(source_id)
        if source['kind'] != 'source' or len(source.get('files', [])) != 1:
            raise WorkflowError('盘点需要单个已登记来源')
        ref = source['files'][0]
        report = audit_csv(resolve_reference(self.root, ref), entity, time, numeric)
        if report['input_sha256'] != ref['sha256']:
            raise WorkflowError('来源在盘点期间改变；未登记盘点结果')
        report.pop('input_path')
        report['input_ref'] = ref
        relative = f'{self.layout["research_reports"]}/{artifact_id}/v{version:04d}/inventory.json'
        raw = encode_json(report)
        files = [self._file(relative, raw, 'inventory_report')]
        staged = self._stage(artifact_id, 'inventory', report, [source_id], files, 'CSV 结构盘点')
        staged.mark(artifact_id, 'completed', report['check_status'], '结构检查结果，失败证据同样保存')
        self._publish(staged, [(relative, raw)])
        return self.project.artifact(artifact_id)

    def save_record(self, artifact_id, kind, content, *, dependencies=(), reason):
        from .records import AREAS, record_dependencies, render_record, validate_record
        version = self._version_number(artifact_id)
        content = validate_record(kind, content, self.project)
        if not isinstance(dependencies, (tuple, list)) or len(set(dependencies)) != len(dependencies):
            raise WorkflowError('依赖必须是无重复标识列表')
        deps = list(dict.fromkeys(list(dependencies) + record_dependencies(kind, content)))
        if artifact_id in deps:
            raise WorkflowError('记录不能依赖自身')
        if kind == 'research_task' and any(r['artifact_id'] == artifact_id for r in content['outputs']):
            raise WorkflowError('任务不能以自己作为完成产物')
        prefix = f'{self.layout[AREAS[kind]]}/{artifact_id}/v{version:04d}'
        writes = [(prefix + '/record.json', encode_json(content)),
                  (prefix + '/record.md', render_record(kind, content).encode('utf-8'))]
        refs = [self._file(path, raw, kind) for path, raw in writes]
        staged = self._stage(artifact_id, kind, content, deps, refs, reason)
        staged.mark(artifact_id, 'completed', 'passed', '记录格式与引用检查；主张和任务状态分别保存')
        self._publish(staged, writes)
        return self.project.artifact(artifact_id)
