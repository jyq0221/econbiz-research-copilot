"""Bounded, evidence-linked drafts from explicit researcher mappings."""

import csv
import hashlib
import io
import math
import re
from collections import defaultdict
from pathlib import Path

from .audit import MISSING
from .plans import validate_plan
from .state import Project, WorkflowError, json_copy, now


MEANINGS = ('concept', 'definition', 'unit', 'time', 'source', 'missing_meaning', 'measurement_limit')
UNKNOWN = {'', '待核实', '不知道', '不清楚', '未知'}
GOALS = {'description', 'association', 'causal', 'prediction', 'undecided'}


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


def _measurement(item, columns, numeric, label, questions):
    if item is None:
        questions.append(f'请先确认{label}对应哪一列；找不到时需补充指标及其说明。')
        return False
    if not isinstance(item, dict) or not isinstance(item.get('field'), str):
        raise WorkflowError(f'{label}的字段映射结构不完整')
    if item['field'] not in columns:
        raise WorkflowError(f'数据中不存在 {item["field"]}，不能编造字段')
    missing = [key for key in MEANINGS if not isinstance(item.get(key), str) or item[key].strip() in UNKNOWN]
    if item.get('confirmed') is not True or missing:
        questions.append(f'请核实{label}的含义、单位、时间、来源、缺失含义及指标与概念的距离；当前说明尚未确认完整。')
        return False
    if item['field'] not in numeric:
        questions.append(f'{label}列 {item["field"]} 尚未按数值检查，请先补做数值盘点。')
        return False
    return True


def _value(raw):
    if raw.strip() in MISSING:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise WorkflowError('待分析字段含未解释文本，请重新盘点') from exc
    if not math.isfinite(value):
        raise WorkflowError('待分析字段含非有限数值，请重新盘点')
    return value


def _mapping(item):
    return {key: item[key] for key in ('field', 'definition', 'unit', 'time', 'source')} | {
        'version': '1', 'concept': item['concept'], 'missing_meaning': item['missing_meaning'],
        'measurement_limit': item['measurement_limit']}


def _base(focus, facts, purpose, reason):
    plan = dict(
        question=f'{focus["concept"]}在现有企业与年份中呈现什么分布和变化？',
        goal='description', judgment='先了解分布和变化，不预设应当出现的方向',
        competing_explanations='样本构成与测量口径也可能影响观察到的分布和变化',
        mapping={'y': _mapping(focus)},
        sample=f'原始 {facts["total_rows"]} 行；关注指标可用 {facts["focus_rows"]} 行，'
               f'缺失 {facts["focus_missing"]} 行。拟按指标可用观测描述，待确认样本规则。',
        comparison='对现有企业年度观测进行分布与按年度汇总，不作因果比较',
        missing_rule=f'保留原始缺失标记，不填零。已提供说明：{focus["missing_meaning"]}；'
                     '拟按可用观测分析，缺失可能改变样本代表性，须在执行前确认。',
        model='descriptive', controls=[], fixed_effects=[],
        standard_errors={'method': 'not_applicable', 'rationale': '当前草案只描述样本，不进行总体参数推断'},
        conditions='确认指标定义和时间口径；若比较年度，需核对各年企业构成是否变化。',
        feasibility='可准备描述方案；尚未计算统计表，也未完成研究者确认',
        data_gaps=[], priority_reason='关注指标已有核实映射，可先了解数据覆盖和基本分布',
        boundary=f'仅描述现有样本；{focus["measurement_limit"]}',
        relation='独立的描述问题；不作为关联结果的稳健性检验', purpose=purpose)
    if purpose == 'exploratory':
        plan['exploration_reason'] = reason
    return plan


def build_candidates(project, inventory_id, brief):
    """Never modifies the project or source; informational gaps return questions."""
    inventory = project.require_usable(inventory_id)
    if inventory['kind'] != 'inventory':
        raise WorkflowError('请使用数据盘点记录')
    report = inventory['content']
    if not isinstance(brief, dict) or brief.get('goal') not in GOALS:
        raise WorkflowError('请明确研究目标，或选择尚未确定')
    brief = json_copy(brief)
    key = report.get('key')
    if not isinstance(key, dict) or not {'entity', 'time'} <= key.keys():
        raise WorkflowError('此旧盘点缺少主体与期间信息，请重新执行数据盘点')
    if key['entity'] not in report['columns'] or key['time'] not in report['columns']:
        raise WorkflowError('盘点记录中的主体或期间字段无效')
    result = dict(direction=project.snapshot()['direction'], goal=brief['goal'], plans=[],
                  questions=[], limitations=['当前为固定规则生成的讨论草案，未检索文献、未执行估计。',
                                             '指标含义由研究者提供；程序不能认证测量有效性。'],
                  facts={'total_rows': report['rows']}, generated_at=now(),
                  inventory_id=inventory_id, inventory_version=inventory['version'],
                  recommendation='先补齐下列信息，再比较研究路线。')
    q = result['questions']
    if brief['goal'] in {'causal', 'prediction', 'undecided'}:
        q.append({'causal': '请保留因果问题，并补充比较对象、制度背景与识别依据；当前不生成替代的关联方案。',
                  'prediction': '请补充预测对象、预测时点及训练/验证设计；当前尚不支持预测方案。',
                  'undecided': '请先区分：描述现象、了解关联、判断因果，还是预测未来？'}[brief['goal']])
        return result
    prior_results = has_prior_results(project)
    reason = brief.get('exploration_reason', '')
    if prior_results and (not isinstance(reason, str) or reason.strip() in UNKNOWN):
        q.append('项目已有结果；请记录现在提出这组问题的原因，新草案将标为结果之后的探索。')
        return result
    purpose = 'exploratory' if prior_results else 'planned'
    focus, explanatory = brief.get('focus'), brief.get('explanatory')
    columns = report['columns']
    numeric = report['numeric']
    focus_ok = _measurement(focus, columns, numeric, '关注现象', q)
    explanatory_ok = False
    if brief['goal'] == 'association':
        explanatory_ok = _measurement(explanatory, columns, numeric, '可能的解释因素', q)
    if not focus_ok:
        return result
    raw = Path(report['input_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != report['input_sha256']:
        raise WorkflowError('原文件已改变，请重新盘点')
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True))
    y_rows = [row for row in rows if _value(row[focus['field']]) is not None]
    facts = result['facts']
    facts.update(focus_rows=len(y_rows), focus_missing=len(rows) - len(y_rows),
                 focus_entities=len({row[key['entity']] for row in y_rows}),
                 focus_periods=sorted({row[key['time']] for row in y_rows}))
    if not y_rows:
        q.append('关注指标没有可用数值，需补充有效数据或重新核实缺失含义。')
        return result
    description = _base(focus, facts, purpose, reason)
    result['plans'].append(description)
    result['recommendation'] = '先审阅描述路线的测量和样本规则，确认它能回答你关心的问题。'
    if brief['goal'] == 'description':
        return result
    result['limitations'].append('描述路线回答缩小后的问题，不能替代原来关于两个指标关联的问题。')
    if not explanatory_ok:
        return result
    if focus['field'] == explanatory['field']:
        q.append('关注现象与解释因素指向同一列，不能据此生成两个指标的关联方案。')
        return result
    pairs = [row for row in y_rows if _value(row[explanatory['field']]) is not None]
    groups = defaultdict(set)
    for row in pairs:
        groups[row[key['entity']]].add(_value(row[explanatory['field']]))
    periods = sorted({row[key['time']] for row in pairs})
    facts.update(pair_rows=len(pairs), pair_entities=len(groups), pair_periods=periods,
                 additional_missing_x=len(y_rows) - len(pairs),
                 raw_within_varying_entities=sum(len(v) > 1 for v in groups.values()))
    if len(groups) < 2 or len(periods) < 2 or not facts['raw_within_varying_entities']:
        q.append('共同样本缺少至少两个企业、两个时期或解释指标的企业内变化；'
                 '请补充覆盖/指标或重新讨论问题，当前不准备企业固定效应路线。')
        return result
    association = _base(focus, facts, purpose, reason)
    association.update(
        question=f'{explanatory["concept"]}与{focus["concept"]}在企业内跨期变化中有何条件关联？',
        goal='association', judgment='非定向草案；关系方向及理论理由仍需进一步讨论',
        competing_explanations='遗漏混杂、反向关系、共同冲击与测量误差仍可能解释观察到的关联',
        mapping={'x': _mapping(explanatory), 'y': _mapping(focus)},
        sample=f'原始 {len(rows)} 行 → 关注指标可用 {len(y_rows)} 行 → 两指标共同可用 {len(pairs)} 行；'
               f'进一步因解释指标缺失减少 {facts["additional_missing_x"]} 行。'
               '这是候选完整案例样本，尚未执行删除，需核对流失影响。',
        comparison='候选企业与年度固定效应，用企业内跨期变化比较条件关联；控制变量角色待论证',
        missing_rule=description['missing_rule'] + f' 解释指标缺失说明：{explanatory["missing_meaning"]}。',
        model='linear_fe', fixed_effects=[key['entity'], key['time']],
        standard_errors={'method': 'needs_decision', 'rationale': '请结合误差相关结构和有效簇的信息量选择，不能机械默认企业聚类'},
        conditions='已检查共同样本内的原始企业内变化；这不代表吸收企业和年度固定效应后仍有变化。'
                   '估计前还需检查共线性、剩余变化、控制变量角色与推断条件。',
        feasibility='可讨论关联草案；推断方式及控制条件待论证，尚不能确认用于执行',
        data_gaps=['标准误方式及其理由待确定', '控制变量角色待论证', '测量与理论依据尚需文献或制度证据'],
        priority_reason='两个指标映射已核实，共同样本具有基础覆盖；可进一步讨论原关联问题',
        boundary=f'仅条件关联，不作因果解释；{focus["measurement_limit"]}；{explanatory["measurement_limit"]}',
        relation='与描述路线回答不同问题；不是替代测量或稳健性检验')
    result['plans'].append(association)
    result['recommendation'] = '先用描述路线理解数据；若要回答两个指标的关联问题，再核对关联路线的测量、控制条件和推断方式。'
    q.append('关联草案尚需讨论理论依据、控制变量角色和标准误；不要把结构检查通过当作研究设计已验证。')
    return result


def store_candidates(project, inventory_id, brief, prefix):
    """Return a staged Project and report. Caller saves only after full success."""
    if not isinstance(prefix, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', prefix):
        raise WorkflowError('方案包标识只能包含字母、数字、连字符和下划线')
    comparison = build_candidates(project, inventory_id, brief)
    candidate_project = Project(project.snapshot())
    intake_id, comparison_id = prefix + '-intake', prefix + '-comparison'
    ids = [intake_id, comparison_id] + [f'{prefix}-plan-{i}' for i in range(1, len(comparison['plans']) + 1)]
    if set(ids) & candidate_project.snapshot()['artifacts'].keys():
        raise WorkflowError('方案包已存在；请使用新标识保留原方案')
    columns = candidate_project.artifact(inventory_id)['content']['columns']
    for plan in comparison['plans']:
        validate_plan(plan, columns)
    comparison.update(comparison_id=comparison_id, intake_id=intake_id,
                      plan_ids=ids[2:])
    candidate_project.add(intake_id, 'intake', brief, [inventory_id])
    candidate_project.mark(intake_id, 'completed', 'passed', '已记录输入；仅结构检查，不认证测量假设')
    candidate_project.add(comparison_id, 'candidate_comparison', comparison, [intake_id])
    candidate_project.mark(comparison_id, 'completed', 'passed', '草案与样本事实对应检查，不代表研究设计已确认')
    for plan_id, plan in zip(ids[2:], comparison['plans']):
        candidate_project.add(plan_id, 'plan', plan, [inventory_id, comparison_id])
        candidate_project.mark(plan_id, 'needs_decision', 'needs_decision', '待研究者理解并确认具体方案')
    return candidate_project, comparison
