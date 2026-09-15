"""Explicit, versioned execution rules; never infer sample rules from prose."""

import csv
import io
import math
import re
from collections import Counter

from .audit import MISSING
from .plans import validate_plan
from .state import WorkflowError, json_copy


def compile_spec(plan, inventory):
    """Compile an approved plan's machine-readable rules (approval checked by runner)."""
    try:
        columns = inventory['columns']
        validate_plan(plan, columns, require_supported=True)
        rules = plan['execution']
        if set(rules) != {'sample_filters', 'missing', 'singleton', 'confidence'}:
            raise WorkflowError('execution 必须明确 sample_filters/missing/singleton/confidence；不支持额外选项')
        if rules['missing'] != 'complete_case' or rules['singleton'] != 'keep' or rules['confidence'] != 0.95:
            raise WorkflowError('首版支持完整案例、保留单例及 95% 置信区间；其他规则须另行实现')
        entity, time = inventory['key']['entity'], inventory['key']['time']
        if entity == time or not {entity, time} <= set(columns):
            raise WorkflowError('企业年度键无效')
        y = plan['mapping']['y']['field'] if plan['model'] == 'linear_fe' else None
        x = ([plan['mapping']['x']['field']] + plan['controls'] if y is not None else
             [item['field'] for item in plan['mapping'].values()])
        if len(set(x)) != len(x) or y in x or {entity, time} & set(x + ([y] if y else [])):
            raise WorkflowError('数值变量不能重复、互为因变量与解释变量或充当企业年度键')
        fe = plan['fixed_effects']
        if len(set(fe)) != len(fe) or not set(fe) <= {entity, time}:
            raise WorkflowError('首版固定效应限企业、年度字段的一项或两项')
        if y is None and (plan['controls'] or fe):
            raise WorkflowError('描述统计不采用控制变量或固定效应')
        filters = rules['sample_filters']
        if not isinstance(filters, list):
            raise WorkflowError('sample_filters 必须是列表；无额外限制时用空列表')
        for rule in filters:
            if not isinstance(rule, dict) or set(rule) != {'field', 'op', 'value'}:
                raise WorkflowError('筛选项必须仅含 field/op/value')
            if rule['field'] not in columns or rule['op'] not in {'eq', 'ne', 'in', 'ge', 'le'}:
                raise WorkflowError('筛选字段或运算不支持')
            v = rule['value']
            if rule['op'] == 'in':
                if not isinstance(v, list) or not v or any(not isinstance(i, str) for i in v):
                    raise WorkflowError('in 筛选须使用非空文本列表，保留代码前导零')
            elif rule['op'] in {'eq', 'ne'}:
                if not isinstance(v, str):
                    raise WorkflowError('eq/ne 采用文本精确比较，筛选值须为文本')
            elif type(v) not in {int, float} or not math.isfinite(v):
                raise WorkflowError('ge/le 筛选值须为有限数值')
        return json_copy(dict(estimation=dict(model=plan['model'], y=y, x=x, fixed_effects=fe,
                              entity=entity, time=time, standard_errors=plan['standard_errors'], confidence=0.95),
                              sample_filters=filters, missing='complete_case', singleton='keep',
                              missing_markers=sorted(MISSING), columns=columns))
    except (KeyError, TypeError, AttributeError) as exc:
        raise WorkflowError(f'缺少可执行规则；请修订并确认具体方案版本：{exc}') from exc


def read_csv(raw):
    try:
        reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
        values = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise WorkflowError(f'无法完整读取 UTF-8 CSV：{exc}') from exc
    if not values or not values[0] or any(not c.strip() for c in values[0]) or len(set(values[0])) != len(values[0]):
        raise WorkflowError('CSV 表头为空或重复')
    if len(values) < 2 or any(len(row) != len(values[0]) for row in values[1:]):
        raise WorkflowError('CSV 无数据或存在列数不一致的行')
    return values[0], [dict(zip(values[0], row)) for row in values[1:]]


def _number(value, field):
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise WorkflowError(f'{field} 包含未解释的数值文本：{value!r}') from exc
    if not math.isfinite(number):
        raise WorkflowError(f'{field} 包含非有限数值：{value!r}')
    return number


def prepare_sample(raw, spec):
    columns, rows = read_csv(raw)
    if columns != spec['columns']:
        raise WorkflowError('输入列与绑定盘点不一致')
    model = spec['estimation']
    entity, time = model['entity'], model['time']
    keys, seen = [], set()
    numeric = ([model['y']] if model['y'] else []) + model['x']
    missing = set(spec['missing_markers'])
    for row in rows:
        key = (row[entity], row[time])
        if any(v.strip() in missing or v != v.strip() for v in key):
            raise WorkflowError('企业年度键存在缺失或首尾空白；须先明确修订')
        if not re.fullmatch(r'[0-9]{4}', row[time]):
            raise WorkflowError('年度字段须为四位整数年文本')
        if key in seen:
            raise WorkflowError(f'企业年度键重复，不自动去重：{key}')
        seen.add(key)
        keys.append(list(key))
        for field in numeric:
            if row[field].strip() not in missing:
                _number(row[field], field)
    audit = dict(input_rows=len(rows), steps=[], missing_by_field={})

    def apply(keep, label):
        nonlocal rows
        selected, dropped = [], []
        for row in rows:
            (selected if keep(row) else dropped).append(row)
        rows = selected
        audit['steps'].append(dict(rule=label, dropped=len(dropped), remaining=len(rows),
                                  dropped_keys=[[r[entity], r[time]] for r in dropped]))

    for rule in spec['sample_filters']:
        field, op, value = rule['field'], rule['op'], rule['value']
        def matches(row):
            actual = row[field]
            if op == 'eq': return actual == value
            if op == 'ne': return actual != value
            if op == 'in': return actual in value
            if actual.strip() in missing: return False
            number = _number(actual, field)
            return number >= value if op == 'ge' else number <= value
        apply(matches, json_copy(rule))
    audit['after_filters'] = len(rows)
    fields = list(numeric)
    se = model['standard_errors']
    if model['model'] == 'linear_fe' and se['method'] == 'cluster' and se['field'] not in fields:
        fields.append(se['field'])
    for field in fields:
        audit['missing_by_field'][field] = dict(Counter(r[field] for r in rows if r[field].strip() in missing))
    baseline_fields = numeric[:2] if model['y'] else numeric
    audit['baseline_complete_rows'] = sum(all(r[f].strip() not in missing for f in baseline_fields) for r in rows)
    all_numeric_complete = sum(all(r[f].strip() not in missing for f in numeric) for r in rows)
    audit['control_additional_loss'] = audit['baseline_complete_rows'] - all_numeric_complete
    for field in fields:
        apply(lambda r, f=field: r[f].strip() not in missing, {'complete_case': field})
    audit.update(final_rows=len(rows), sample_keys=[[r[entity], r[time]] for r in rows],
                 entities=len({r[entity] for r in rows}), periods=sorted({r[time] for r in rows}),
                 singleton_policy='keep', missing_policy='complete_case')
    if not rows:
        raise WorkflowError('按已确认规则筛选后没有可分析观测')
    return rows, audit
