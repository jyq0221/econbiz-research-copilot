"""Bounded Stage B estimation; policy choices are explicit in ``actual_spec``.

The primary fit uses linearmodels.PanelOLS, retaining singletons and counting
the full fixed-effect design in the covariance correction. Inputs are already
complete cases; this module never drops observations or regressors.
"""

import copy
from collections import Counter

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS
from scipy import stats

from .state import WorkflowError, json_copy


_SPEC_KEYS = {'model', 'y', 'x', 'fixed_effects', 'entity', 'time',
              'standard_errors', 'confidence'}
_MAX_DUMMY_CELLS = 10_000_000
_CONDITION_LIMIT = 1e8


def _prepare(rows, spec):
    if not isinstance(spec, dict) or set(spec) != _SPEC_KEYS:
        raise WorkflowError('数值方案字段不完整或包含不支持的字段')
    if spec['model'] not in ('linear_fe', 'descriptive') or spec['confidence'] != .95:
        raise WorkflowError('阶段 B 仅支持 linear_fe/descriptive 和 95% 置信区间')
    x, effects = spec['x'], spec['fixed_effects']
    if not isinstance(x, list) or not x or any(not isinstance(v, str) or not v.strip() for v in x):
        raise WorkflowError('必须提供非空、明确的数值字段列表')
    if len(x) != len(set(x)):
        raise WorkflowError('解释变量不能重复')
    if any(not isinstance(spec[k], str) or not spec[k].strip() for k in ('entity', 'time')):
        raise WorkflowError('必须提供实体和时间字段')
    if spec['entity'] == spec['time']:
        raise WorkflowError('实体和时间字段不能相同')
    if (not isinstance(effects, list) or any(e not in (spec['entity'], spec['time']) for e in effects)
            or len(effects) != len(set(effects))):
        raise WorkflowError('固定效应必须使用实际实体或时间字段名，且不能重复')
    se = spec['standard_errors']
    if (not isinstance(se, dict) or set(se)-{'method', 'field', 'rationale'}
            or se.get('method') not in ('classical', 'hc1', 'cluster')
            or not isinstance(se.get('rationale'), str) or not se['rationale'].strip()):
        raise WorkflowError('标准误方法及其理由必须明确')
    if se['method'] == 'cluster' and (not isinstance(se.get('field'), str) or not se['field'].strip()):
        raise WorkflowError('聚类标准误必须指定聚类字段')
    if se['method'] != 'cluster' and se.get('field') is not None:
        raise WorkflowError('非聚类标准误不能带有聚类字段')
    linear = spec['model'] == 'linear_fe'
    if linear and (not effects or not isinstance(spec['y'], str) or not spec['y'].strip()
                   or spec['y'] in x):
        raise WorkflowError('固定效应模型必须指定因变量、独立解释变量和至少一个固定效应')
    if not linear and (spec['y'] is not None or effects):
        raise WorkflowError('描述统计不使用因变量或固定效应')
    if not isinstance(rows, list) or not rows:
        raise WorkflowError('估计样本不能为空')
    fields = x + ([spec['y']] if linear else [])
    keys = []
    values = []
    clusters = []
    for row in rows:
        if not isinstance(row, dict):
            raise WorkflowError('样本行必须是字段字典')
        pair = [row.get(spec['entity']), row.get(spec['time'])]
        if any(not isinstance(v, str) or not v.strip() for v in pair):
            raise WorkflowError('实体和时间键必须是非空文本')
        keys.append(pair)
        try:
            if any(not isinstance(row[f], str) for f in fields):
                raise ValueError('numerical inputs must be source strings')
            numeric = [float(row[f]) for f in fields]
            if not np.isfinite(numeric).all():
                raise ValueError('nonfinite value')
            values.append(numeric)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise WorkflowError('样本含缺失、非数值或非有限数值') from exc
        if se['method'] == 'cluster':
            value = row.get(se['field'])
            if not isinstance(value, str) or not value.strip():
                raise WorkflowError('聚类字段必须完整且为非空文本')
            clusters.append(value)
    if len({tuple(k) for k in keys}) != len(keys):
        raise WorkflowError('估计样本的实体—时间键重复')
    if linear and clusters and len(set(clusters)) < 2:
        raise WorkflowError('聚类推断至少需要两个聚类')
    return np.asarray(values, dtype=float), keys, clusters


def _effect_metadata(keys, effects):
    entity_counts = Counter(k[0] for k in keys)
    time_counts = Counter(k[1] for k in keys)
    rank = ((len(entity_counts) if 'entity' in effects else 0)
            + (len(time_counts) if 'time' in effects else 0) - (len(effects) == 2))
    components = None
    if len(effects) == 2:
        # Connectivity gives the actual rank E + T - 1 of a two-way design.
        links = {}
        for entity, time in keys:
            a, b = ('e', entity), ('t', time)
            links.setdefault(a, set()).add(b)
            links.setdefault(b, set()).add(a)
        unseen, components = set(links), 0
        while unseen:
            stack = [unseen.pop()]
            components += 1
            while stack:
                for neighbour in links[stack.pop()]:
                    if neighbour in unseen:
                        unseen.remove(neighbour)
                        stack.append(neighbour)
        if components != 1:
            raise WorkflowError('双向固定效应的实体—时间图不连通，当前实现不支持该自由度结构')
        if len(keys)*min(len(entity_counts), len(time_counts)) > _MAX_DUMMY_CELLS:
            raise WorkflowError('双向固定效应超出当前有界稠密消元容量（1000 万单元）')
    return dict(fixed_effect_rank=int(rank), fixed_effect_components=components,
                singleton_entity_count=sum(v == 1 for v in entity_counts.values()) if 'entity' in effects else 0,
                singleton_time_count=sum(v == 1 for v in time_counts.values()) if 'time' in effects else 0)


def _descriptive(values, fields):
    summary = {}
    for j, field in enumerate(fields):
        raw = values[:, j]
        scale = float(np.max(np.abs(raw))) or 1.0
        z = raw/scale
        quantiles = np.quantile(z, [.25, .5, .75])*scale
        summary[field] = dict(count=len(raw), mean=float(np.mean(z)*scale),
                              std=float(np.std(z, ddof=1)*scale) if len(raw) > 1 else None,
                              min=float(raw.min()), p25=float(quantiles[0]),
                              median=float(quantiles[1]), p75=float(quantiles[2]), max=float(raw.max()))
    return summary


def estimate(rows, spec):
    """Estimate one declared specification or raise ``WorkflowError``.

    HC1 correction is n/(n-K); clustered correction is
    G/(G-1)*(n-1)/(n-K), where K includes all identified fixed effects.
    Clustered p-values/intervals use t(G-1); others use t(n-K).
    """
    values, keys, clusters = _prepare(rows, spec)
    base = dict(model=spec['model'], parameters=[], nobs=len(rows), df_resid=None,
                inference_df=None, rank=None, sample_keys=keys, actual_spec=copy.deepcopy(spec),
                descriptive={}, diagnostics={}, warnings=[])
    numeric_fields = spec['x'] + ([spec['y']] if spec['model'] == 'linear_fe' else [])
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            base['descriptive'] = _descriptive(values, numeric_fields)
    except FloatingPointError as exc:
        raise WorkflowError('描述统计结果超出有限浮点数范围') from exc
    if spec['model'] == 'descriptive':
        base['diagnostics'] = dict(engine='numpy descriptive statistics')
        return json_copy(base)
    effects = ['entity' if field == spec['entity'] else 'time' for field in spec['fixed_effects']]
    metadata = _effect_metadata(keys, effects)
    p, n = len(spec['x']), len(rows)
    rank = p + metadata['fixed_effect_rank']
    df = n-rank
    if df <= 0:
        raise WorkflowError('计入全部固定效应后残差自由度必须为正')
    scales = np.max(np.abs(values), axis=0)
    scales[scales == 0] = 1.0
    normalized = values/scales
    # Codes preserve original string keys (including leading zeroes) in output.
    entities, _ = pd.factorize(np.asarray([key[0] for key in keys]), sort=False)
    times, _ = pd.factorize(np.asarray([key[1] for key in keys]), sort=False)
    index = pd.MultiIndex.from_arrays([entities, times], names=['entity', 'time'])
    xframe = pd.DataFrame(normalized[:, :p], index=index, columns=spec['x'])
    yframe = pd.Series(normalized[:, p], index=index, name=spec['y'])
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            model = PanelOLS(yframe, xframe, entity_effects='entity' in effects,
                             time_effects='time' in effects, drop_absorbed=False,
                             singletons=True, check_rank=True)
            group = 'both' if len(effects) == 2 else effects[0]
            within_x = model.exog.demean(group, low_memory=False).values2d
            singular = np.linalg.svd(within_x, compute_uv=False)
            if (singular[-1] <= 1e-12*np.sqrt(n)
                    or singular[0]/singular[-1] > _CONDITION_LIMIT):
                raise WorkflowError('解释变量被固定效应吸收、共线或条件数过高，不能可靠估计')
            fit_options = dict(cov_type={'classical': 'unadjusted', 'hc1': 'robust', 'cluster': 'clustered'}[spec['standard_errors']['method']],
                               auto_df=False, count_effects=True, debiased=True, low_memory=False)
            if clusters:
                fit_options.update(clusters=pd.DataFrame({'cluster': clusters}, index=index), group_debias=True)
            fitted = model.fit(**fit_options)
            residual = fitted.resids.to_numpy()
            residual_ss = float(residual @ residual)
            within_y = model.dependent.demean(group, low_memory=False).values2d[:, 0]
            if residual_ss <= 1e-24*max(float(within_y @ within_y), np.finfo(float).tiny):
                raise WorkflowError('残差方差为零或数值上无法区别于零，推断未定义')
            coefficients = fitted.params.to_numpy()*(scales[p]/scales[:p])
            errors = fitted.std_errors.to_numpy()*(scales[p]/scales[:p])
            if (not np.isfinite(coefficients).all() or not np.isfinite(errors).all()
                    or np.any(errors <= 0)):
                raise WorkflowError('估计量或标准误非有限，或标准误为零，推断未定义')
            if int(fitted.nobs) != n or int(fitted.df_resid) != df:
                raise WorkflowError('数值引擎实际样本或自由度与声明不一致')
            inference_df = len(set(clusters))-1 if clusters else df
            critical = stats.t.ppf(.975, inference_df)
            for term, coefficient, error in zip(spec['x'], coefficients, errors):
                base['parameters'].append(dict(term=term, coefficient=float(coefficient), std_error=float(error),
                                               p_value=float(2*stats.t.sf(abs(coefficient/error), inference_df)),
                                               ci_low=float(coefficient-critical*error), ci_high=float(coefficient+critical*error)))
            original_rss = float((residual_ss*scales[p])*scales[p])
    except WorkflowError:
        raise
    except (ValueError, TypeError, ZeroDivisionError, FloatingPointError, np.linalg.LinAlgError) as exc:
        raise WorkflowError(f'固定效应估计失败：{exc}') from exc
    base.update(rank=rank, df_resid=df, inference_df=inference_df)
    correction = n/df if spec['standard_errors']['method'] == 'hc1' else 1.0
    if clusters:
        g = len(set(clusters))
        correction = g/(g-1)*(n-1)/df
    base['diagnostics'] = dict(metadata, engine='linearmodels.PanelOLS',
                               covariance=spec['standard_errors']['method'], cluster_count=len(set(clusters)) if clusters else None,
                               covariance_correction=correction, residual_sum_squares=original_rss,
                               scaled_condition_number=float(singular[0]/singular[-1]), singletons='retained',
                               auto_df=False, count_effects=True, debiased=True, group_debias=bool(clusters),
                               inference_distribution='Student t')
    if metadata['singleton_entity_count'] or metadata['singleton_time_count']:
        base['warnings'].append('单例固定效应组已保留；计入样本数及全部固定效应自由度。')
    return json_copy(base)
