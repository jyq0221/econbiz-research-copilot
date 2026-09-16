"""Independent FE reference using sparse incidence projection and explicit covariance.

This module deliberately does not import the primary estimator or linearmodels.
Predetermined tolerances apply to estimates, standard errors, p-values and CIs;
sample identity and specification metadata must match exactly.
"""

import copy
import json
import math
from collections import Counter

import numpy as np
from scipy import linalg, sparse, stats
from scipy.sparse.linalg import lsmr

from .state import WorkflowError, json_copy


RTOL = 1e-6
ATOL = 1e-8


def _summaries(numbers, names):
    """Independent sorted quantiles and compensated sums in original units."""
    n = len(numbers)
    summaries = {}
    for j, name in enumerate(names):
        ordered = sorted(numbers[:, j].tolist())
        scale = max(abs(v) for v in ordered) or 1.0
        scaled = [v/scale for v in ordered]
        mean = math.fsum(scaled)/n
        def quantile(q):
            index = (n-1)*q
            lo = math.floor(index)
            hi = math.ceil(index)
            return ((1-(index-lo))*scaled[lo]+(index-lo)*scaled[hi])*scale
        summaries[name] = dict(count=n, mean=mean*scale,
            std=math.sqrt(math.fsum((v-mean)**2 for v in scaled)/(n-1))*scale if n > 1 else None,
            min=ordered[0], p25=quantile(.25), median=quantile(.5), p75=quantile(.75), max=ordered[-1])
    return summaries


def _reference(rows, spec, *, include_covariance=False):
    if not isinstance(rows, list) or not rows:
        raise WorkflowError('独立复核要求非空样本')
    if not isinstance(spec, dict) or set(spec) != {'model', 'y', 'x', 'fixed_effects', 'entity', 'time', 'standard_errors', 'confidence'}:
        raise WorkflowError('独立复核方案字段不完整')
    if spec['model'] not in ('descriptive', 'linear_fe') or spec['confidence'] != .95:
        raise WorkflowError('独立复核不支持该模型或置信水平')
    fields = spec['x']
    effects = spec['fixed_effects']
    if (not isinstance(fields, list) or not fields
            or any(not isinstance(f, str) or not f.strip() for f in fields)
            or len(fields) != len(set(fields))):
        raise WorkflowError('独立复核的数值字段必须明确且不重复')
    linear = spec['model'] == 'linear_fe'
    if (linear and (not effects or not spec['y'] or spec['y'] in fields)) or (not linear and (effects or spec['y'] is not None)):
        raise WorkflowError('独立复核模型字段冲突')
    if (any(not isinstance(spec[k], str) or not spec[k].strip() for k in ('entity', 'time'))
            or spec['entity'] == spec['time']):
        raise WorkflowError('独立复核要求不同的有效实体和时间字段')
    if (not isinstance(effects, list) or set(effects)-{spec['entity'], spec['time']}
            or len(effects) != len(set(effects))):
        raise WorkflowError('独立复核的固定效应必须使用实际实体或时间字段名')
    effects = [{spec['entity']: 'entity', spec['time']: 'time'}[field] for field in effects]
    se = spec['standard_errors']
    if (not isinstance(se, dict) or set(se)-{'method', 'field', 'rationale'}
            or se.get('method') not in ('classical', 'hc1', 'cluster')
            or not isinstance(se.get('rationale'), str) or not se['rationale'].strip()):
        raise WorkflowError('独立复核标准误方案无效或包含不支持的字段')
    if ((se['method'] == 'cluster' and (not isinstance(se.get('field'), str) or not se['field'].strip()))
            or (se['method'] != 'cluster' and se.get('field') is not None)):
        raise WorkflowError('独立复核聚类字段与标准误方法不一致')
    names = fields + ([spec['y']] if linear else [])
    keys = [[row[spec['entity']], row[spec['time']]] for row in rows]
    if (any(not isinstance(v, str) or not v.strip() for key in keys for v in key)
            or len({tuple(k) for k in keys}) != len(keys)):
        raise WorkflowError('独立复核样本键缺失或重复')
    if any(not isinstance(row[name], str) for row in rows for name in names):
        raise WorkflowError('独立复核数值输入必须保持原始文本')
    numbers = np.array([[float(row[name]) for name in names] for row in rows], dtype=float)
    if not np.isfinite(numbers).all():
        raise WorkflowError('独立复核输入包含非有限数值')
    method = se['method']
    clusters = [row[se['field']] for row in rows] if method == 'cluster' else []
    if clusters and any(not isinstance(c, str) or not c.strip() for c in clusters):
        raise WorkflowError('独立复核的聚类字段必须完整且有效')
    if linear and clusters and len(set(clusters)) < 2:
        raise WorkflowError('独立复核至少需要两个有效聚类')
    n, p = len(rows), len(fields)
    result = dict(model=spec['model'], parameters=[], nobs=n, rank=None, df_resid=None, inference_df=None,
                  sample_keys=keys, actual_spec=copy.deepcopy(spec), descriptive={}, diagnostics={}, warnings=[])
    if include_covariance:
        result['covariance_matrix'] = []
    result['descriptive'] = _summaries(numbers, names)
    if not linear:
        result['diagnostics'] = dict(engine='independent sorted summaries and compensated sums')
        return json_copy(result)
    categories = []
    code_vectors = []
    for effect in effects:
        values = [row[spec[effect]] for row in rows]
        labels = {label: i for i, label in enumerate(sorted(set(values)))}
        categories.append(len(labels))
        code_vectors.append(np.array([labels[label] for label in values], dtype=int))
    fe_rank = sum(categories)-(len(effects) == 2)
    components = None
    if len(effects) == 2:
        # Independent union-find rank audit, rather than the primary graph traversal.
        parent = list(range(sum(categories)))
        def root(i):
            while i != parent[i]:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for a, b in zip(code_vectors[0], code_vectors[1]):
            parent[root(int(a))] = root(int(b)+categories[0])
        components = len({root(i) for i in range(len(parent))})
        if components != 1:
            raise WorkflowError('独立复核拒绝不连通的双向固定效应图')
    rank = p+fe_rank
    df = n-rank
    if df <= 0:
        raise WorkflowError('独立复核残差自由度必须为正')
    observation_index = np.tile(np.arange(n), len(effects))
    dummy_index = np.concatenate([codes+sum(categories[:j]) for j, codes in enumerate(code_vectors)])
    incidence = sparse.csc_matrix((np.ones(len(observation_index)), (observation_index, dummy_index)),
                                  shape=(n, sum(categories)))
    scales = np.array([max(abs(v) for v in numbers[:, j]) or 1.0 for j in range(numbers.shape[1])])
    normalized = numbers/scales
    projected = np.empty_like(normalized)
    stops, iterations = [], []
    maxiter = min(20_000, max(100, 4*sum(categories)))
    for j in range(normalized.shape[1]):
        solution = lsmr(incidence, normalized[:, j], atol=1e-14, btol=1e-14,
                        conlim=1e10, maxiter=maxiter)
        residual = normalized[:, j]-incidence @ solution[0]
        orthogonality = np.linalg.norm(incidence.T @ residual)
        if (solution[1] not in (0, 1, 2, 4, 5)
                or orthogonality > 1e-10*max(np.linalg.norm(normalized[:, j]), 1.0)):
            raise WorkflowError('独立稀疏投影未在预设迭代数和正交性容差内收敛')
        projected[:, j] = residual
        stops.append(int(solution[1]))
        iterations.append(int(solution[2]))
    x, y = projected[:, :p], projected[:, p]
    singular = linalg.svdvals(x)
    if singular[-1] <= 1e-12*math.sqrt(n) or singular[0]/singular[-1] > 1e8:
        raise WorkflowError('独立复核检测到吸收、共线或过高条件数')
    coefficients, _, xrank, _ = linalg.lstsq(x, y, cond=None, lapack_driver='gelsd')
    if xrank != p:
        raise WorkflowError('独立复核的解释变量不满秩')
    residual = y-x @ coefficients
    rss = float(residual @ residual)
    if rss <= 1e-24*max(float(y @ y), np.finfo(float).tiny):
        raise WorkflowError('独立复核的残差方差为零或数值上无法区别于零')
    # QR-based bread avoids squaring the condition number during inversion.
    _, upper = linalg.qr(x, mode='economic')
    inverse_upper = linalg.solve_triangular(upper, np.eye(p))
    bread = inverse_upper @ inverse_upper.T
    correction = 1.0
    if method == 'classical':
        covariance = (rss/df)*bread
    else:
        scores = x*residual[:, None]
        if method == 'hc1':
            meat = scores.T @ scores
            correction = n/df
        else:
            labels = {label: i for i, label in enumerate(sorted(set(clusters)))}
            group_scores = np.zeros((len(labels), p))
            np.add.at(group_scores, [labels[label] for label in clusters], scores)
            meat = group_scores.T @ group_scores
            g = len(set(clusters))
            correction = g/(g-1)*(n-1)/df
        covariance = correction*(bread @ meat @ bread)
    errors = np.sqrt(np.diag(covariance))*(scales[p]/scales[:p])
    coefficients = coefficients*(scales[p]/scales[:p])
    if include_covariance:
        units = scales[p]/scales[:p]
        result['covariance_matrix'] = (covariance*units[:, None]*units[None, :]).tolist()
    if not np.isfinite(errors).all() or np.any(errors <= 0) or not np.isfinite(coefficients).all():
        raise WorkflowError('独立复核的标准误或系数无效')
    inference_df = len(set(clusters))-1 if clusters else df
    critical = float(stats.t.ppf(.975, inference_df))
    for term, coef, error in zip(fields, coefficients, errors):
        result['parameters'].append(dict(term=term, coefficient=float(coef), std_error=float(error),
            p_value=float(2*stats.t.sf(abs(coef/error), inference_df)),
            ci_low=float(coef-critical*error), ci_high=float(coef+critical*error)))
    ec, tc = Counter(k[0] for k in keys), Counter(k[1] for k in keys)
    single_e = sum(v == 1 for v in ec.values()) if 'entity' in effects else 0
    single_t = sum(v == 1 for v in tc.values()) if 'time' in effects else 0
    result.update(rank=int(rank), df_resid=int(df), inference_df=int(inference_df))
    result['diagnostics'] = dict(engine='scipy sparse LSMR projection and explicit covariance',
        fixed_effect_rank=int(fe_rank), fixed_effect_components=components,
        singleton_entity_count=single_e, singleton_time_count=single_t,
        covariance=method, cluster_count=len(set(clusters)) if clusters else None,
        covariance_correction=correction, residual_sum_squares=float((rss*scales[p])*scales[p]),
        scaled_condition_number=float(singular[0]/singular[-1]), singletons='retained',
        auto_df=False, count_effects=True, debiased=True, group_debias=bool(clusters),
        inference_distribution='Student t', projection_maxiter=maxiter,
        projection_stop_codes=stops, projection_iterations=iterations)
    if single_e or single_t:
        result['warnings'].append('单例固定效应组已保留；计入样本数及全部固定效应自由度。')
    return json_copy(result)


def verify_numerics(rows, spec, result, *, backend='python'):
    """Return a JSON-safe pass/fail report, including for malformed results.

    A failed reference calculation is a failed check, never evidence that a
    primary result was independently reproduced.
    """
    report = dict(check_status='failed', rtol=RTOL, atol=ATOL, checks=[], reference=None)
    if backend not in ('python', 'stata'):
        report['checks'].append(dict(name='backend', passed=False, detail='不支持的执行引擎'))
        return report
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            reference = _reference(rows, spec, include_covariance=backend == 'stata')
        report['reference'] = reference
    except (WorkflowError, ValueError, TypeError, KeyError, IndexError, ZeroDivisionError,
            FloatingPointError, OverflowError, MemoryError, np.linalg.LinAlgError) as exc:
        report['checks'].append(dict(name='reference_execution', passed=False, detail=str(exc)))
        return report
    checks = report['checks']
    checks.append(dict(name='reference_execution', passed=True, detail='独立稀疏投影和显式协方差计算完成' if spec['model'] == 'linear_fe' else '独立描述统计计算完成'))
    if not isinstance(result, dict):
        checks.append(dict(name='result_structure', passed=False, detail='主结果必须是字典'))
        return report
    if set(result) != set(reference):
        checks.append(dict(name='result_structure', passed=False, detail='主结果字段集合不符合约定'))
    try:
        json.dumps(result, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError):
        checks.append(dict(name='result_json', passed=False, detail='主结果必须是有限、可保存的 JSON'))
        return report

    def compare(name, actual, expected):
        if isinstance(expected, dict):
            if not isinstance(actual, dict) or set(actual) != set(expected):
                checks.append(dict(name=name, passed=False, detail='字段集合不一致'))
                return
            for key, value in expected.items():
                compare(f'{name}.{key}', actual[key], value)
        elif isinstance(expected, list):
            if not isinstance(actual, list) or len(actual) != len(expected):
                checks.append(dict(name=name, passed=False, detail='列表长度或结构不一致'))
                return
            for i, value in enumerate(expected):
                compare(f'{name}[{i}]', actual[i], value)
        else:
            numeric_detail = {}
            if isinstance(expected, float):
                try:
                    actual_number = float(actual) if type(actual) in (int, float) else None
                    if actual_number is not None and not math.isfinite(actual_number):
                        actual_number = None
                except (ValueError, TypeError, OverflowError):
                    actual_number = None
                delta = abs(actual_number-expected) if actual_number is not None else None
                if delta is not None and not math.isfinite(delta):
                    delta = None
                tolerance = ATOL+RTOL*abs(expected)
                passed = delta is not None and delta <= tolerance
                numeric_detail = dict(actual=actual_number, reference=expected, delta=delta, tolerance=tolerance)
                detail = '在预先设定的数值容差内' if passed else '数值缺失、非有限或超出容差'
            else:
                passed = type(actual) is type(expected) and actual == expected
                detail = '完全一致' if passed else '元数据不一致'
            checks.append(dict(name=name, passed=bool(passed), detail=detail, **numeric_detail))

    for field in ('model', 'nobs', 'rank', 'df_resid', 'inference_df', 'parameters', 'descriptive', 'warnings'):
        compare(field, result.get(field), reference[field])
    if backend == 'stata':
        compare('covariance_matrix', result.get('covariance_matrix'), reference['covariance_matrix'])
    exact_sample = result.get('sample_keys') == reference['sample_keys']
    checks.append(dict(name='sample_keys', passed=exact_sample,
                       detail='样本键及顺序完全一致' if exact_sample else '样本键或顺序不一致'))
    # The specification is an exact agreement check, including confidence and rationale.
    try:
        exact_spec = json.dumps(result.get('actual_spec'), sort_keys=True, allow_nan=False) == json.dumps(spec, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError):
        exact_spec = False
    checks.append(dict(name='actual_spec', passed=exact_spec, detail='声明方案完全一致' if exact_spec else '实际方案与声明不一致'))
    if spec['model'] == 'linear_fe':
        primary_diagnostics = result.get('diagnostics')
        diagnostic_fields = ('fixed_effect_rank', 'fixed_effect_components', 'singleton_entity_count', 'singleton_time_count',
                             'covariance', 'cluster_count', 'covariance_correction', 'residual_sum_squares',
                             'scaled_condition_number', 'singletons', 'auto_df', 'count_effects', 'debiased', 'group_debias', 'inference_distribution')
        if backend == 'stata':
            implementation_options = {'scaled_condition_number', 'auto_df', 'count_effects', 'debiased', 'group_debias'}
            diagnostic_fields = tuple(f for f in diagnostic_fields if f not in implementation_options)
        exact_diagnostics = isinstance(primary_diagnostics, dict) and set(primary_diagnostics) == set(diagnostic_fields) | {'engine'}
        checks.append(dict(name='diagnostics.structure', passed=exact_diagnostics,
                           detail='诊断字段完整一致' if exact_diagnostics else '诊断字段缺失或包含不支持的字段'))
        compare('diagnostics.engine', primary_diagnostics.get('engine') if isinstance(primary_diagnostics, dict) else None,
                'linearmodels.PanelOLS' if backend == 'python' else 'stata.areg')
        for field in diagnostic_fields:
            compare(f'diagnostics.{field}', primary_diagnostics.get(field) if isinstance(primary_diagnostics, dict) else None,
                    reference['diagnostics'][field])
    else:
        compare('diagnostics', result.get('diagnostics'),
                dict(engine='numpy descriptive statistics' if backend == 'python' else 'stata.descriptive'))
    report['check_status'] = 'passed' if all(c['passed'] for c in checks) else 'failed'
    return json_copy(report)
