"""Research record contracts. Structural validity never certifies a claim."""

from datetime import datetime

from .state import WorkflowError, json_copy, require_text


AREAS = {'research_context': 'research_sessions', 'literature_evidence': 'literature_notes',
         'concept_plan': 'research_plans', 'session_note': 'research_sessions',
         'user_decision': 'research_decisions', 'research_task': 'research_tasks'}
FIELDS = {
    'research_context': ('question', 'known', 'unknown', 'constraints', 'next_step'),
    'literature_evidence': ('source_id', 'read_scope', 'locator', 'claim', 'support', 'limits'),
    'concept_plan': ('question', 'goal', 'rationale', 'data_gaps', 'next_step'),
    'session_note': ('summary', 'facts', 'decisions', 'outputs', 'open_questions', 'next_step', 'authorization'),
    'user_decision': ('plan_id', 'plan_version', 'quote', 'scope', 'recorded_at'),
    'research_task': ('title', 'task_status', 'input_versions', 'outputs', 'next_step', 'blocked_reason'),
}


def text_list(value, label):
    if not isinstance(value, list):
        raise WorkflowError(f'{label} 必须是文本列表')
    for text in value:
        require_text(text, label)


def reference(project, ref, *, usable=True):
    if not isinstance(ref, dict):
        raise WorkflowError('产物版本引用必须是字典')
    require_text(ref.get('artifact_id'), '产物标识')
    old = project.version(ref['artifact_id'], ref.get('version'))
    current = project.artifact(ref['artifact_id'])
    if current['version'] != old['version']:
        raise WorkflowError(f'引用版本已变化：{ref["artifact_id"]}')
    if usable:
        project.require_usable(ref['artifact_id'])
    return current


def _references(project, refs):
    if not isinstance(refs, list):
        raise WorkflowError('产物引用必须是列表')
    for ref in refs:
        reference(project, ref)


def validate_record(kind, content, project):
    content = json_copy(content)
    if kind not in FIELDS or not isinstance(content, dict):
        raise WorkflowError('未知记录类型或内容结构')
    permitted = set(FIELDS[kind]) | {'notes'}
    if kind == 'literature_evidence':
        permitted |= {'source_version', 'evidence_status'}
    if kind == 'session_note':
        permitted |= {'platform_thread_id', 'platform_locator_evidence'}
    if kind == 'research_task':
        permitted |= {'priority', 'authorization', 'checks'}
    if set(content) - permitted:
        raise WorkflowError(f'未定义的记录字段：{sorted(set(content) - permitted)}')
    if not set(FIELDS[kind]) <= set(content):
        raise WorkflowError(f'记录缺少字段：{sorted(set(FIELDS[kind]) - set(content))}')
    if 'notes' in content:
        require_text(content['notes'], '备注')
    if kind == 'research_context':
        for key in ('question', 'next_step'):
            require_text(content[key], key)
        for key in ('known', 'unknown', 'constraints'):
            text_list(content[key], key)
    elif kind == 'concept_plan':
        for key in ('question', 'goal', 'rationale', 'next_step'):
            require_text(content[key], key)
        if content['goal'] not in {'description', 'association', 'causal', 'prediction', 'undecided'}:
            raise WorkflowError('概念方案需明确研究目标或待确定')
        text_list(content['data_gaps'], '数据缺口')
    elif kind == 'literature_evidence':
        source = project.require_usable(content['source_id'])
        if source['kind'] != 'source' or not source.get('files'):
            raise WorkflowError('文献证据必须引用实际材料来源')
        if content.get('source_version', source['version']) != source['version']:
            raise WorkflowError('文献来源版本不匹配')
        if content['read_scope'] not in {'metadata', 'abstract', 'excerpt', 'full_text'}:
            raise WorkflowError('未知文献阅读范围')
        for key in ('locator', 'limits'):
            require_text(content[key], key)
        if content['read_scope'] == 'metadata':
            if content['claim'] != '' or content['support'] != '':
                raise WorkflowError('只读元数据不能填写经验发现；claim/support 应留空')
        else:
            for key in ('claim', 'support'):
                require_text(content[key], key)
        if content.get('evidence_status', 'reported') not in {'reported', 'needs_check', 'source_supported'}:
            raise WorkflowError('未知证据状态；记录校验不能证明经验主张')
    elif kind == 'session_note':
        for key in ('summary', 'next_step', 'authorization'):
            require_text(content[key], key)
        for key in ('decisions', 'open_questions'):
            text_list(content[key], key)
        _references(project, content['outputs'])
        if not isinstance(content['facts'], list):
            raise WorkflowError('事实必须是列表')
        for fact in content['facts']:
            if not isinstance(fact, dict):
                raise WorkflowError('每条事实必须包含来源')
            for key in ('id', 'claim', 'source_kind', 'locator', 'excerpt', 'evidence_status'):
                require_text(fact.get(key), f'事实 {key}')
            if fact['source_kind'] not in {'user_quote', 'source_excerpt', 'program_output', 'agent_proposal'}:
                raise WorkflowError('未知事实来源种类')
            if fact['evidence_status'] not in {'reported', 'needs_check', 'source_supported', 'proposed'}:
                raise WorkflowError('未知事实证据状态')
            if fact['source_kind'] == 'agent_proposal' and fact['evidence_status'] != 'proposed':
                raise WorkflowError('Agent 建议必须标为 proposed')
            if fact['source_kind'] in {'source_excerpt', 'program_output'}:
                reference(project, fact.get('source_ref'))
            if fact['source_kind'] == 'user_quote' and fact['evidence_status'] not in {'reported', 'needs_check'}:
                raise WorkflowError('用户说明不自动成为已核实事实')
        if 'platform_thread_id' in content:
            require_text(content['platform_thread_id'], '平台消息标识')
            require_text(content.get('platform_locator_evidence'), '平台实际提供标识的可见依据')
    elif kind == 'user_decision':
        for key in ('plan_id', 'quote', 'scope', 'recorded_at'):
            require_text(content[key], key)
        plan = reference(project, {'artifact_id': content['plan_id'], 'version': content['plan_version']}, usable=False)
        if plan['kind'] != 'plan':
            raise WorkflowError('确认摘录必须绑定正式方案具体版本')
        try:
            at = datetime.fromisoformat(content['recorded_at'])
            if at.tzinfo is None:
                raise ValueError('记录时间需要时区')
        except ValueError as exc:
            raise WorkflowError('记录时间必须是实际带时区 ISO 时间') from exc
    elif kind == 'research_task':
        for key in ('title', 'next_step'):
            require_text(content[key], key)
        if content['task_status'] not in {'queued', 'in_progress', 'waiting', 'needs_check', 'completed'}:
            raise WorkflowError('未知研究任务状态')
        if not isinstance(content['blocked_reason'], str):
            raise WorkflowError('等待原因必须是文本')
        if content['task_status'] == 'waiting':
            require_text(content['blocked_reason'], '等待原因')
        if not isinstance(content['input_versions'], dict):
            raise WorkflowError('输入版本必须是字典')
        for key, version in content['input_versions'].items():
            reference(project, {'artifact_id': key, 'version': version})
        _references(project, content['outputs'])
        if content['task_status'] == 'completed' and not content['outputs']:
            raise WorkflowError('已完成任务必须引用可用实际产物')
    return content


def record_dependencies(kind, content):
    if kind == 'literature_evidence':
        return [content['source_id']]
    if kind == 'research_task':
        return list(content['input_versions'])
    if kind == 'session_note':
        return list(dict.fromkeys(f['source_ref']['artifact_id'] for f in content['facts'] if 'source_ref' in f))
    return []


def render_record(kind, content):
    import json
    rows = [f'# {kind}', '', '此记录已保存并通过格式检查；证据程度和任务进展见各字段。', '']
    for key, value in content.items():
        rows += [f'## {key}', '']
        if isinstance(value, str):
            rows += [value or '（未填写）', '']
        else:
            rows += ['```json', json.dumps(value, ensure_ascii=False, indent=2), '```', '']
    return '\n'.join(rows)
