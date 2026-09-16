"""Derived progress and recovery context, always checked against live artifacts."""

import hashlib
import json

from .files import project_path
from .records import reference
from .state import WorkflowError


TASK_LABELS = {'queued': '待开展', 'in_progress': '进行中', 'waiting': '等待材料或决定',
               'needs_check': '需要重新核对', 'completed': '已完成'}


def project_context(project):
    state = project.snapshot()
    records, tasks, plans, issues, deliveries = {}, {}, {}, {}, {}
    for key, artifact in state['artifacts'].items():
        if artifact['kind'] == 'workspace_layout':
            continue
        problem = None
        try:
            project.require_usable(key)
            if artifact['kind'] in {'model_comparison', 'word_report', 'document_review'}:
                from types import SimpleNamespace
                from .comparison import read_model_comparison
                from .document_checks import read_word_report, read_document_review
                if project.base_dir is None:
                    raise WorkflowError('交付记录需要实际项目文件核对')
                readers = dict(model_comparison=read_model_comparison,
                               word_report=read_word_report, document_review=read_document_review)
                readers[artifact['kind']](SimpleNamespace(project=project, root=project.base_dir), key)
        except WorkflowError as exc:
            problem = str(exc)
            issues[key] = problem
        if artifact['kind'] in {'model_comparison', 'word_report', 'document_review'}:
            deliveries[key] = dict(version=artifact['version'], content=artifact['content'],
                                   files=artifact['files'], usable=problem is None, problem=problem)
        if artifact['kind'] == 'plan':
            plans[key] = dict(version=artifact['version'], content=artifact['content'],
                              execution_status=artifact['execution_status'], usable=problem is None)
        elif artifact['kind'] == 'research_task':
            content = artifact['content']
            if problem is None:
                try:
                    for output in content['outputs']:
                        reference(project, output)
                except WorkflowError as exc:
                    problem = str(exc)
                    issues[key] = problem
            tasks[key] = dict(version=artifact['version'], content=content,
                              effective_status='needs_check' if problem else content['task_status'],
                              record_status=artifact['execution_status'], problem=problem)
        elif artifact['kind'] in {'research_context', 'session_note', 'user_decision', 'literature_evidence', 'concept_plan'}:
            if artifact['kind'] == 'user_decision' and problem is None:
                content = artifact['content']
                try:
                    reference(project, {'artifact_id': content['plan_id'], 'version': content['plan_version']}, usable=False)
                except WorkflowError as exc:
                    problem = str(exc)
                    issues[key] = problem
            if problem is None:
                records[key] = artifact
    return dict(project_id=state['project_id'], direction=state['direction'], records=records, tasks=tasks,
                plans=plans, issues=issues, deliveries=deliveries, decisions=state['decisions'],
                next_steps=[a['content']['next_step'] for a in records.values() if 'next_step' in a['content']])


def render_progress(project):
    summary = project_context(project)
    lines = ['# 研究进展', '', f'项目：{summary["project_id"]}', f'方向：{summary["direction"]}', '',
             '本概览由状态生成；记录保存、研究完成与证据核实分别判断。', '']
    for key, record in summary['records'].items():
        lines += [f'## {key} · v{record["version"]}', '']
        for field in ('question', 'summary', 'claim', 'quote', 'authorization', 'next_step'):
            if field in record['content']:
                lines.append(f'- {field}：{record["content"][field]}')
        for ref in record.get('files', []):
            if ref['path'].endswith('.md'):
                lines.append(f'- 文件：[{key}]({ref["path"]})')
        lines.append('')
    if summary['plans']:
        lines += ['## 方案', '']
        for key, plan in summary['plans'].items():
            status = '当前已确认' if plan['usable'] else '待确认或需核对'
            lines.append(f'- {key} v{plan["version"]}：{status}；{plan["content"].get("question", "")}')
        lines.append('')
    if summary['tasks']:
        lines += ['## 任务', '']
        for key, task in summary['tasks'].items():
            content = task['content']
            lines.append(f'- {content["title"]}（{key}）：任务 {TASK_LABELS[task["effective_status"]]}；记录 {task["record_status"]}')
            lines.append(f'  下一步：{content["next_step"]}；等待原因：{content["blocked_reason"] or "无"}')
        lines.append('')
    if summary['deliveries']:
        lines += ['## 结果交付', '']
        for key, item in summary['deliveries'].items():
            c = item['content']
            lines.append(f'- {key} v{item["version"]}：' + ('当前有效' if item['usable'] else '需要重新核对'))
            if 'visual_check' in c:
                lines.append(f'  渲染：{c.get("render_check", "not_performed")}；视觉检查：{c["visual_check"]}')
            for ref in item['files']:
                if ref['path'].endswith(('.docx', '.md')):
                    lines.append(f'  文件：[{key}]({ref["path"]})')
        lines.append('')
    if summary['issues']:
        lines += ['## 待处理', ''] + [f'- {key}：{issue}' for key, issue in summary['issues'].items()] + ['']
    return '\n'.join(lines)


def resume_context(workspace):
    summary = project_context(workspace.project)
    edits = []
    directory = workspace.path('research_history') / 'view-edits'
    if directory.exists():
        for path in sorted(directory.glob('*.md')):
            # Return locations as unreviewed input, never merge their prose into state.
            project_path(workspace.root, path.relative_to(workspace.root))
            edits.append(path.relative_to(workspace.root).as_posix())
    view = project_path(workspace.root, '研究进展.md')
    summary['unreviewed_view_edits'] = edits
    summary['view_present'] = view.exists()
    summary['next_step'] = summary['next_steps'][-1] if summary['next_steps'] else '继续核实研究问题和现有材料'
    return summary
