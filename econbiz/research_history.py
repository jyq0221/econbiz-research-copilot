"""Shared result-exposure rules for every plan entry path."""

from .state import WorkflowError, json_copy, require_text


def has_prior_results(project):
    """Keep exposure to results across revisions and subsequent failed checks."""
    state = project.snapshot()
    for key, artifact in state['artifacts'].items():
        if artifact['kind'] != 'result':
            continue
        versions = [artifact] + state['history'].get(key, [])
        if any(v.get('has_completed_result') is True or v['execution_status'] in {'completed', 'stale'} for v in versions):
            return True
    return False


def prepare_plan_content(project, content):
    content = json_copy(content)
    if not isinstance(content, dict):
        raise WorkflowError('方案内容必须是字典')
    if has_prior_results(project):
        reason = content.get('exploration_reason')
        require_text(reason, '结果后探索原因')
        if reason.strip() in {'待核实', '不知道', '不清楚', '未知'}:
            raise WorkflowError('结果后探索需要实际研究理由')
        content['purpose'] = 'exploratory'
    return content
