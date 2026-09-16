"""Bounded native Stata adapter with byte-frozen input and raw-output auditing.

Estimates and descriptive statistics come only from Stata. Python encodes source
strings, reverses unit normalization, and checks evidence consistency; independent
numerical verification is performed separately by the execution layer.
"""

import copy
import csv
import io
import json
import math
import re
import stat
from collections import Counter
from decimal import Decimal, localcontext
from pathlib import Path

import numpy as np
from scipy import stats

from .state import WorkflowError, json_copy
from .stata_script import MATA_HELPERS, analysis_script, regression_command


_SPEC_KEYS = {'model', 'y', 'x', 'fixed_effects', 'entity', 'time',
              'standard_errors', 'confidence'}
_BUNDLE_NAMES = {'input.csv', 'mapping.json', 'analysis.do', 'helpers.mata'}


def _prepare(rows, spec):
    if not isinstance(spec, dict) or set(spec) != _SPEC_KEYS:
        raise WorkflowError('Stata 数值方案字段不完整或包含不支持的字段')
    if spec['model'] not in ('descriptive', 'linear_fe') or spec['confidence'] != .95:
        raise WorkflowError('Stata 仅支持已声明的模型和 95% 置信区间')
    x, effects, se = spec['x'], spec['fixed_effects'], spec['standard_errors']
    if (not isinstance(x, list) or not x or any(not isinstance(v, str) or not v.strip() for v in x)
            or len(set(x)) != len(x)):
        raise WorkflowError('Stata 数值字段必须明确且不重复')
    if (any(not isinstance(spec[k], str) or not spec[k].strip() for k in ('entity', 'time'))
            or spec['entity'] == spec['time']):
        raise WorkflowError('Stata 实体和时间字段必须有效且不同')
    if (not isinstance(effects, list) or any(e not in (spec['entity'], spec['time']) for e in effects)
            or len(set(effects)) != len(effects)):
        raise WorkflowError('Stata 固定效应字段必须使用实际实体或时间字段名')
    if (not isinstance(se, dict) or set(se)-{'method', 'field', 'rationale'}
            or se.get('method') not in ('classical', 'hc1', 'cluster')
            or not isinstance(se.get('rationale'), str) or not se['rationale'].strip()):
        raise WorkflowError('Stata 标准误方法及理由必须明确')
    if ((se['method'] == 'cluster' and (not isinstance(se.get('field'), str) or not se['field'].strip()))
            or (se['method'] != 'cluster' and se.get('field') is not None)):
        raise WorkflowError('Stata 聚类字段与标准误方法不一致')
    linear = spec['model'] == 'linear_fe'
    if ((linear and (not effects or not isinstance(spec['y'], str) or not spec['y'].strip() or spec['y'] in x))
            or (not linear and (effects or spec['y'] is not None))):
        raise WorkflowError('Stata 模型和数值字段冲突')
    if not isinstance(rows, list) or not rows:
        raise WorkflowError('Stata 估计样本不能为空')
    fields = x + ([spec['y']] if linear else [])
    keys, numbers, clusters = [], [], []
    try:
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('source row must be a dictionary')
            pair = [row[spec['entity']], row[spec['time']]]
            if any(not isinstance(v, str) or not v.strip() for v in pair):
                raise ValueError('empty key')
            keys.append(pair)
            if any(not isinstance(row[f], str) for f in fields):
                raise ValueError('source numbers must be strings')
            numeric = [float(row[f]) for f in fields]
            if any(not math.isfinite(v) for v in numeric):
                raise ValueError('nonfinite number')
            if any(v == 0 and not Decimal(row[f]).is_zero() for f, v in zip(fields, numeric)):
                raise ValueError('nonzero source value underflows binary64')
            numbers.append(numeric)
            if se['method'] == 'cluster':
                cluster = row[se['field']]
                if not isinstance(cluster, str) or not cluster.strip():
                    raise ValueError('missing cluster')
                clusters.append(cluster)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise WorkflowError('Stata 样本含缺失、非数值、非有限数值或无效键') from exc
    if len({tuple(k) for k in keys}) != len(keys):
        raise WorkflowError('Stata 样本的实体—时间键重复')
    if linear and clusters and len(set(clusters)) < 2:
        raise WorkflowError('Stata 聚类推断至少需要两个聚类')
    return fields, keys, numbers, clusters


def _codes(values):
    labels = dict.fromkeys(values)
    labels = {value: i+1 for i, value in enumerate(labels)}
    return [labels[value] for value in values], list(labels)


def _effect_metadata(keys, effects):
    counts = [Counter(k[j] for k in keys) for j in (0, 1)]
    rank = sum(len(counts[j]) for j, alias in enumerate(('ec', 'tc')) if alias in effects)
    components = None
    if len(effects) == 2:
        rank -= 1
        if len(keys)*min(map(len, counts)) > 10_000_000:
            raise WorkflowError('双向固定效应超出当前有界稠密消元容量（1000 万单元）')
        links = {}
        for e, t in keys:
            a, b = ('e', e), ('t', t)
            links.setdefault(a, set()).add(b)
            links.setdefault(b, set()).add(a)
        remaining, components = set(links), 0
        while remaining:
            todo = [remaining.pop()]
            components += 1
            while todo:
                for neighbour in links[todo.pop()]:
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        todo.append(neighbour)
        if components != 1:
            raise WorkflowError('双向固定效应的实体—时间图不连通')
    return dict(fixed_effect_rank=rank, fixed_effect_components=components,
                singleton_entity_count=sum(v == 1 for v in counts[0].values()) if 'ec' in effects else 0,
                singleton_time_count=sum(v == 1 for v in counts[1].values()) if 'tc' in effects else 0)


def build_bundle(rows, spec, *, run_token='standalone'):
    """Return deterministic, fixed-name, alias-only inputs for parent freezing."""
    if not isinstance(run_token, str) or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', run_token) is None:
        raise WorkflowError('Stata 运行标识必须是 1–128 位安全字母、数字、下划线或连字符')
    fields, keys, numbers, clusters = _prepare(rows, spec)
    effects = [alias for field, alias in ((spec['entity'], 'ec'), (spec['time'], 'tc'))
               if field in spec['fixed_effects']]
    metadata = _effect_metadata(keys, effects)
    if spec['model'] == 'linear_fe' and len(rows)-metadata['fixed_effect_rank']-len(spec['x']) <= 0:
        raise WorkflowError('计入全部固定效应后残差自由度必须为正')
    scales = [max(abs(row[j]) for row in numbers) or 1.0 for j in range(len(fields))]
    ec, entities = _codes([k[0] for k in keys])
    tc, times = _codes([k[1] for k in keys])
    cc, groups = _codes(clusters) if clusters else ([0]*len(rows), [])
    aliases = [f'n{j+1}' for j in range(len(fields))]
    mapping = dict(format_version=1, run_token=run_token, spec=copy.deepcopy(spec), fields=fields, aliases=aliases,
                   effects=effects, scales=scales, sample_keys=keys,
                   entities=entities, times=times, clusters=groups,
                   effect_metadata=metadata)
    data = io.StringIO(newline='')
    writer = csv.writer(data, lineterminator='\n')
    writer.writerow(['rowid', 'ec', 'tc', 'cc']+aliases)
    for i, values in enumerate(numbers):
        normalized = []
        for j, value in enumerate(values):
            scaled = value/scales[j]
            restored = float(np.longdouble(scaled)*np.longdouble(scales[j]))
            if not math.isclose(restored, value, rel_tol=3e-15, abs_tol=0):
                raise WorkflowError(f'Stata 数值缩放不能保真恢复原值，已停止：{fields[j]}')
            normalized.append(repr(scaled))
        writer.writerow([i+1, ec[i], tc[i], cc[i]]+normalized)
    return {'input.csv': data.getvalue().encode('ascii'),
            'mapping.json': (json.dumps(mapping, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n').encode('utf-8'),
            'analysis.do': analysis_script(mapping), 'helpers.mata': MATA_HELPERS.encode('ascii')}


def _same_bundle(directory, expected):
    for name, data in expected.items():
        path = directory/name
        if path.is_symlink() or path.read_bytes() != data:
            raise WorkflowError(f'Stata 冻结文件与声明不一致：{name}')


def run_estimation(rows, spec, bundle_dir, output_dir, runtime, timeout=240, *, run_token='standalone'):
    """Run an already frozen bundle in newly created ``output_dir/native``."""
    from .stata_runtime import run_stata
    expected = build_bundle(rows, spec, run_token=run_token)
    bundle_dir, native = Path(bundle_dir), Path(output_dir)/'native'
    try:
        _same_bundle(bundle_dir, expected)
        native.mkdir(parents=True, exist_ok=False)
        for name in sorted(_BUNDLE_NAMES):
            (native/name).write_bytes((bundle_dir/name).read_bytes())
        completed = run_stata(runtime, native/'analysis.do', native, timeout=timeout)
        _same_bundle(bundle_dir, expected)
        _same_bundle(native, expected)
        if completed.returncode != 0:
            raise WorkflowError('Stata 子进程未正常完成；请查看本次原生日志')
        return read_result(rows, spec, native, run_token=run_token)
    except WorkflowError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise WorkflowError(f'Stata 运行或原始证据读取失败：{exc}') from exc


def _matrix(native, filename, shape, allow_missing=False):
    with (native/filename).open(newline='', encoding='ascii') as handle:
        cells = list(csv.reader(handle))
    if len(cells) != shape[0] or any(len(row) != shape[1] for row in cells):
        raise WorkflowError(f'Stata 原生矩阵尺寸不符：{filename}')
    value = np.array([[math.nan if cell.strip() == '.' else float(cell) for cell in row] for row in cells])
    if np.isinf(value).any() or (not allow_missing and not np.isfinite(value).all()):
        raise WorkflowError(f'Stata 原生矩阵含无效数值：{filename}')
    return value


def _require(condition, message):
    if not condition:
        raise WorkflowError(f'Stata 原生证据不一致：{message}')


def _close(actual, expected):
    return np.allclose(actual, expected, rtol=2e-12, atol=1e-14, equal_nan=False)


def _inference_close(actual, expected):
    # Stata's invttail and SciPy's ppf differ by 5.4e-11 at df=2.
    # Keep the original r(table); this only audits internal consistency.
    return np.allclose(actual, expected, rtol=1e-10, atol=1e-12, equal_nan=False)


def _unscale(value, *multipliers, divisors=()):
    """Apply units without first forming a potentially unrepresentable factor.

    On macOS arm64, longdouble has the same range as binary64. Decimal keeps
    intermediate scale products and ratios out of that range limitation; the
    final public float must still be finite and retain the nonzero result.
    """
    operands = (value,)+multipliers+tuple(divisors)
    _require(all(math.isfinite(float(v)) for v in operands), '反向缩放输入非有限')
    _require(all(v != 0 for v in divisors), '反向缩放除数为零')
    with localcontext() as context:
        context.prec = 80
        exact = Decimal.from_float(float(value))
        for multiplier in multipliers:
            exact *= Decimal.from_float(float(multiplier))
        for divisor in divisors:
            exact /= Decimal.from_float(float(divisor))
        output = float(exact)
        _require(math.isfinite(output), '反向缩放结果超出有限浮点数范围')
        if not exact.is_zero():
            _require(output != 0, '反向缩放的非零结果下溢，无法保真保存')
            error = abs(Decimal.from_float(output)-exact)
            _require(error <= abs(exact)*Decimal('3e-15'), '反向缩放结果精度不足，无法保真保存')
        return output


def read_result(rows, spec, native_dir, *, run_token='standalone'):
    """Re-read raw Stata evidence without trusting an earlier parsed result."""
    try:
        return _read_result(rows, spec, Path(native_dir), run_token)
    except WorkflowError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        raise WorkflowError(f'Stata 原始输出缺失或格式无效：{exc}') from exc


def _validate_native_files(native, linear):
    """Validate the flat evidence directory before opening any evidence file.

    Resolve the parent so macOS's /var -> /private/var convention is harmless,
    while rejecting a symlink for the native directory itself or any child.
    The execution layer separately validates containment within its run root.
    """
    _require(not native.is_symlink() and native.is_dir(), '原生证据目录必须为实际目录')
    native = native.parent.resolve()/native.name
    required = _BUNDLE_NAMES | {'analysis.log', 'complete.txt', 'metadata.json',
                                'roundtrip.csv', 'descriptive.csv'}
    if linear:
        required |= {'coefficients.csv', 'covariance.csv', 'core_covariance.csv',
                     'table.csv', 'omitted.csv', 'stripes.csv', 'within_y_ss.csv'}
    observed = {}
    for path in native.iterdir():
        info = path.lstat()
        _require(stat.S_ISREG(info.st_mode), f'原生证据必须为普通文件，不能使用链接：{path.name}')
        observed[path.name] = info
    _require(required <= observed.keys(), '必需原生文件或 analysis.log 缺失')
    _require(observed['analysis.log'].st_size > 0, 'analysis.log 为空')
    return native


def _read_result(rows, spec, native, run_token):
    expected = build_bundle(rows, spec, run_token=run_token)
    native = _validate_native_files(native, spec['model'] == 'linear_fe')
    _same_bundle(native, expected)
    _require((native/'complete.txt').read_text().strip() == f'completed:{run_token}',
             '本次运行标识不符或未完成全部原生导出')
    mapping = json.loads(expected['mapping.json'])
    metadata = json.loads((native/'metadata.json').read_text('utf-8'))
    _require(isinstance(metadata, dict), '原生元数据必须为 JSON 对象')
    _require(metadata.get('run_token') == run_token, '原生元数据未绑定本次运行标识')
    _require(metadata.get('complete') is True and metadata.get('nobs') == len(rows), '样本数或完成标记')
    input_rows = list(csv.DictReader(io.StringIO(expected['input.csv'].decode('ascii'))))
    with (native/'roundtrip.csv').open(encoding='ascii', newline='') as handle:
        reader = csv.DictReader(handle)
        roundtrip = list(reader)
        _require(reader.fieldnames == list(input_rows[0])+['sample'], '回读字段与顺序')
    _require(len(roundtrip) == len(rows), '实际样本行数')
    for source, observed in zip(input_rows, roundtrip):
        _require(float(observed['sample']) == 1, 'e(sample) 排除了声明样本')
        for name, value in source.items():
            actual, wanted = float(observed[name]), float(value)
            matched = actual == wanted if name in ('rowid', 'ec', 'tc', 'cc') else math.isclose(actual, wanted, rel_tol=3e-15, abs_tol=0)
            _require(math.isfinite(actual) and matched,
                     f'输入数值、行号或类别编码改变：{name}')
    result = dict(model=spec['model'], parameters=[], nobs=len(rows), df_resid=None,
                  inference_df=None, rank=None, sample_keys=mapping['sample_keys'],
                  actual_spec=copy.deepcopy(spec), descriptive={}, diagnostics={}, warnings=[],
                  covariance_matrix=[])
    summary = _matrix(native, 'descriptive.csv', (len(mapping['fields']), 9), allow_missing=True)
    for j, field in enumerate(mapping['fields']):
        row = summary[j]
        _require(row[0] == len(rows) and row[8] == j+1, '描述统计字段或计数')
        _require(np.isfinite(row[[0, 1, 3, 4, 5, 6, 7, 8]]).all(), '描述统计非有限')
        _require((len(rows) == 1 and math.isnan(row[2])) or (len(rows) > 1 and math.isfinite(row[2]) and row[2] >= 0),
                 '样本标准差')
        _require(row[3] <= row[4] <= row[5] <= row[6] <= row[7], '分位数顺序')
        names = ('mean', 'std', 'min', 'p25', 'median', 'p75', 'max')
        result['descriptive'][field] = dict(count=len(rows), **{
            name: None if name == 'std' and len(rows) == 1 else _unscale(row[k+1], mapping['scales'][j])
            for k, name in enumerate(names)})
    if spec['model'] == 'descriptive':
        _require(metadata.get('cmd') == 'mata: eb_describe' and set(metadata) == {'nobs', 'cmd', 'complete', 'run_token'},
                 '描述统计原生命令')
        result['diagnostics'] = dict(engine='stata.descriptive')
        return json_copy(result)

    n, p = len(rows), len(spec['x'])
    effects, method = mapping['effects'], spec['standard_errors']['method']
    absorb = 'ec' if 'ec' in effects else 'tc'
    group_count = len(mapping['entities'] if absorb == 'ec' else mapping['times'])
    expected_terms = [f'n{j+1}' for j in range(p)]
    explicit = [effect for effect in effects if effect != absorb]
    for effect in explicit:
        count = len(mapping['entities'] if effect == 'ec' else mapping['times'])
        expected_terms.extend([f'1b.{effect}']+[f'{i}.{effect}' for i in range(2, count+1)])
    expected_terms.append('_cons')
    with (native/'stripes.csv').open(encoding='ascii', newline='') as handle:
        stripes = list(csv.DictReader(handle))
    _require(stripes == [{'position': str(j+1), 'name': name} for j, name in enumerate(expected_terms)],
             '系数名称、固定效应基准组或解释变量被省略')
    m = len(expected_terms)
    b = _matrix(native, 'coefficients.csv', (1, m))[0]
    covariance = _matrix(native, 'covariance.csv', (m, m))
    core = _matrix(native, 'core_covariance.csv', (p, p))
    table = _matrix(native, 'table.csv', (9, m), allow_missing=True)
    omitted = _matrix(native, 'omitted.csv', (1, m))[0]
    expected_omitted = np.array([int('b.' in term) for term in expected_terms])
    _require(np.array_equal(omitted, expected_omitted), '未预期的变量省略或吸收')
    for j in np.flatnonzero(omitted):
        _require(b[j] == 0 and np.all(covariance[j] == 0) and np.all(covariance[:, j] == 0), '被省略项的系数或协方差')
    _require(_close(covariance, covariance.T) and np.array_equal(core, covariance[:p, :p]), '协方差对称性或核心矩阵')
    eigenvalues = np.linalg.eigvalsh(covariance)
    _require(eigenvalues.min() >= -1e-10*max(float(np.max(np.abs(covariance))), np.finfo(float).tiny), '协方差矩阵非半正定')
    fe = mapping['effect_metadata']
    rank = int(m-np.sum(omitted)+metadata['absorbed_df'])
    df = n-rank
    clusters = len(mapping['clusters']) if method == 'cluster' else None
    inference_df = clusters-1 if clusters else df
    _require(metadata['cmd'] == 'areg' and metadata['cmdline'] == regression_command(mapping), '实际估计命令或选项')
    _require(metadata['depvar'] == f'n{p+1}' and metadata['absvar'] == absorb, '因变量或吸收维度')
    _require(metadata['vce'] == {'classical': 'ols', 'hc1': 'robust', 'cluster': 'cluster'}[method]
             and metadata['clustvar'] == ('cc' if clusters else ''), '实际标准误或聚类字段')
    _require(metadata['estimation_nobs'] == n and metadata['absorbed_categories'] == group_count
             and metadata['absorbed_df'] == group_count-1, '实际估计样本或吸收秩')
    _require(rank == p+fe['fixed_effect_rank'] and df > 0 and metadata['inference_df'] == inference_df
             and metadata['cluster_count'] == clusters, '完整设计秩、推断自由度或聚类数')
    rss = float(metadata['rss'])
    within_y_ss = _matrix(native, 'within_y_ss.csv', (1, 1))[0, 0]
    _require(math.isfinite(rss) and rss > 1e-24*max(within_y_ss, np.finfo(float).tiny),
             '残差方差为零或数值上无法区别于零')
    active = np.flatnonzero(omitted == 0)
    _require(np.isfinite(table[:, active]).all(), '原生推断表含缺失')
    errors = np.sqrt(np.diag(covariance))
    _require(np.all(errors[:p] > 0) and _close(table[0], b) and _close(table[1, active], errors[active]),
             '原生系数、推断表及协方差对角线')
    _require(np.all(table[6] == inference_df) and np.all(table[8] == 0), '原生推断分布')
    t = b[:p]/errors[:p]
    critical = stats.t.ppf(.975, inference_df)
    _require(_inference_close(table[2, :p], t) and _inference_close(table[3, :p], 2*stats.t.sf(np.abs(t), inference_df))
             and _inference_close(table[4, :p], b[:p]-critical*errors[:p])
             and _inference_close(table[5, :p], b[:p]+critical*errors[:p])
             and _inference_close(table[7, :p], critical), '原生 t 检验或置信区间')
    yscale, xscales = mapping['scales'][-1], mapping['scales'][:p]
    for j, term in enumerate(spec['x']):
        result['parameters'].append(dict(term=term, coefficient=_unscale(table[0, j], yscale, divisors=(xscales[j],)),
            std_error=_unscale(table[1, j], yscale, divisors=(xscales[j],)), p_value=float(table[3, j]),
            ci_low=_unscale(table[4, j], yscale, divisors=(xscales[j],)),
            ci_high=_unscale(table[5, j], yscale, divisors=(xscales[j],))))
    result['covariance_matrix'] = [[_unscale(core[i, j], yscale, yscale,
        divisors=(xscales[i], xscales[j])) for j in range(p)] for i in range(p)]
    correction = n/df if method == 'hc1' else 1.0
    if clusters:
        correction = clusters/(clusters-1)*(n-1)/df
    result.update(rank=rank, df_resid=df, inference_df=inference_df)
    result['diagnostics'] = dict(fe, engine='stata.areg', covariance=method,
        cluster_count=clusters, covariance_correction=correction,
        residual_sum_squares=_unscale(rss, yscale, yscale),
        singletons='retained', inference_distribution='Student t')
    if fe['singleton_entity_count'] or fe['singleton_time_count']:
        result['warnings'].append('单例固定效应组已保留；计入样本数及全部固定效应自由度。')
    return json_copy(result)
