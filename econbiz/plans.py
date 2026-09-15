"""Candidate-plan contracts; no automatic hypothesis search or estimator."""

from .state import WorkflowError, require_text


TEXT_FIELDS = ('question', 'goal', 'judgment', 'competing_explanations', 'sample',
               'comparison', 'missing_rule', 'model', 'conditions', 'feasibility',
               'priority_reason', 'boundary', 'relation', 'purpose')
SUPPORTED = {('description', 'descriptive'), ('association', 'linear_fe')}


def validate_plan(content, columns, require_supported=False):
    try:
        for key in TEXT_FIELDS:
            require_text(content[key], key)
        if content['goal'] not in {'description', 'association', 'causal', 'prediction'}:
            raise WorkflowError('研究目标必须显式区分描述、关联、因果、预测')
        if content['purpose'] not in {'planned', 'exploratory'}:
            raise WorkflowError('分析目的必须标明 planned 或 exploratory')
        if content['purpose'] == 'exploratory':
            require_text(content['exploration_reason'], '结果后探索原因')
        if not isinstance(content['mapping'], dict) or not content['mapping']:
            raise WorkflowError('必须提供概念到实际字段的映射')
        if content['goal'] == 'association' and not {'x', 'y'} <= set(content['mapping']):
            raise WorkflowError('关联方案必须明确 x 和 y')
        fields = []
        for item in content['mapping'].values():
            for key in ('field', 'definition', 'unit', 'time', 'source', 'version'):
                require_text(item[key], f'测量映射 {key}')
            fields.append(item['field'])
        for key in ('controls', 'fixed_effects', 'data_gaps'):
            if not isinstance(content[key], list) or any(not isinstance(v, str) or not v.strip() for v in content[key]):
                raise WorkflowError(f'{key} 必须是文本列表（可以为空）')
        fields += content['controls'] + content['fixed_effects']
        se = content['standard_errors']
        require_text(se['method'], '标准误方式')
        require_text(se['rationale'], '标准误理由')
        if se['method'] == 'cluster':
            require_text(se['field'], '聚类字段')
            fields.append(se['field'])
        absent = sorted(set(fields) - set(columns))
        if absent:
            raise WorkflowError(f'方案引用不存在的字段：{absent}')
        if require_supported and (content['goal'], content['model']) not in SUPPORTED:
            raise WorkflowError('该目标/模型超出首版执行范围；保留需求，不转换研究目标')
        if require_supported and content['model'] == 'linear_fe':
            if not content['fixed_effects']:
                raise WorkflowError('固定效应模型必须明确固定效应字段')
            if se['method'] not in {'cluster', 'hc1', 'classical'}:
                raise WorkflowError('当前模型未支持该标准误选项')
    except (KeyError, TypeError, AttributeError) as exc:
        raise WorkflowError(f'方案字段缺失或类型错误：{exc}') from exc


def register_plan(project, plan_id, content, inventory_id):
    inventory = project.require_usable(inventory_id)
    if inventory['kind'] != 'inventory':
        raise WorkflowError('方案必须引用数据盘点产物')
    validate_plan(content, inventory['content']['columns'])
    project.add(plan_id, 'plan', content, [inventory_id])
    project.mark(plan_id, 'needs_decision', 'needs_decision', '方案已登记，待研究者核对设计和规则')
    return project.artifact(plan_id)


def require_approved_plan(project, plan_id):
    plan = project.require_usable(plan_id)
    if plan['kind'] != 'plan':
        raise WorkflowError('所选产物不是分析方案')
    decisions = project.snapshot()['decisions']
    if not any(d['artifact_id'] == plan_id and d['version'] == plan['version'] for d in decisions):
        raise WorkflowError('当前方案版本尚未获得研究者确认')
    return plan
