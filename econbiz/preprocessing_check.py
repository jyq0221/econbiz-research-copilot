"""Independent NumPy/pandas preparation reference with fixed comparison rules.

Only recipe validation is shared with the primary implementation. CSV parsing,
numeric conversion, transformations, panel alignment and comparisons are local.
"""

import csv
import io
import operator as comparison
from decimal import Decimal, localcontext

from .preprocessing import validate_recipe
from .state import WorkflowError


RTOL = 1e-9
ATOL = 1e-12
_DECIMAL = r' *[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)? *'


def _frame(raw, pd, *, allow_empty=False):
    try:
        table = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True))
    except (UnicodeError, csv.Error, AttributeError) as exc:
        raise WorkflowError('独立预处理复核无法读取 UTF-8 CSV') from exc
    if (not table or not table[0] or any(not value.strip() for value in table[0])
            or len(set(table[0])) != len(table[0]) or (len(table) < 2 and not allow_empty)
            or any(len(row) != len(table[0]) for row in table[1:])):
        raise WorkflowError('独立预处理复核 CSV 表头、行宽或观测数无效')
    return pd.DataFrame(table[1:], columns=table[0], dtype=str)


def _numeric(series, pd, np):
    missing = series.eq('')
    if (~missing & ~series.str.fullmatch(_DECIMAL)).any():
        raise WorkflowError('独立预处理复核发现未解释的数值文本')
    try:
        # NumPy's string-to-double conversion preserves tiny fixed-point input;
        # pandas.to_numeric can truncate such literals before conversion.
        values = np.asarray(series.mask(missing, np.nan).tolist(), dtype=float)
    except (ValueError, TypeError, OverflowError) as exc:
        raise WorkflowError('独立预处理复核数值转换失败') from exc
    if not np.isfinite(values[~missing.to_numpy()]).all():
        raise WorkflowError('独立预处理复核发现非有限数值')
    return values


def _filter(frame, step, pd, np):
    source, operator = frame[step['source']], step['operator']
    threshold = step.get('value')
    if operator == 'is_missing':
        keep = source.eq('')
    elif operator == 'not_missing':
        keep = source.ne('')
    elif operator in {'eq', 'ne'}:
        keep = source.eq(threshold) if operator == 'eq' else source.ne(threshold)
    elif operator in {'in', 'not_in'}:
        keep = source.isin(threshold)
        if operator == 'not_in':
            keep = ~keep
    else:
        values = _numeric(source, pd, np)
        # Python scalar comparison retains exact integral thresholds beyond 2^53;
        # NumPy would first round them to the array's floating-point dtype.
        comparator = getattr(comparison, operator)
        keep = np.fromiter((comparator(value, threshold) for value in values.tolist()), dtype=bool)
        keep &= np.isfinite(values)
    return frame.loc[keep].reset_index(drop=True)


def _groups(frame, step, pd, np):
    values = _numeric(frame[step['source']], pd, np)
    result = np.full(len(frame), np.nan)
    groups = (frame.groupby(step['by'], sort=False, dropna=False).indices.values()
              if step['by'] else [np.arange(len(frame))])
    for positions in groups:
        positions = np.asarray(positions, dtype=int)
        positions = positions[np.isfinite(values[positions])]
        if not len(positions):
            continue
        sample = values[positions]
        if step['op'] == 'winsor':
            thresholds = np.quantile(sample, [step['lower'], step['upper']], method='linear')
            result[positions] = np.clip(sample, *thresholds)
        else:
            # Exact conversion of binary floats and a high precision accumulator
            # preserve small within-group variation and large cancellation.
            with localcontext() as context:
                context.prec = 1100
                mean = float(sum(Decimal.from_float(float(v)) for v in sample) / Decimal(len(sample)))
            centered = sample - mean
            if step['op'] == 'center':
                result[positions] = centered
            else:
                scale = np.max(np.abs(centered))
                sd = (scale * (np.linalg.norm(centered / scale) / np.sqrt(len(sample) - step['ddof']))
                      if scale and len(sample) > step['ddof'] else 0 if len(sample) > step['ddof'] else np.nan)
                if not np.isfinite(sd) or sd == 0:
                    if scale and len(sample) > step['ddof']:
                        raise WorkflowError('独立预处理复核标准差超出有限数值范围')
                    if step['zero'] == 'error':
                        raise WorkflowError('独立预处理复核标准差为零或自由度不足')
                    continue
                result[positions] = centered / sd
    return result


def _panel(frame, step, pd, np):
    times = frame[step['time']]
    if not times.str.fullmatch(r' *[+-]?[0-9]+(?:\.0+)? *').all():
        raise WorkflowError('独立预处理复核面板时间必须是十进制整数')
    periods = _numeric(times, pd, np)
    if not np.isfinite(periods).all() or (np.abs(periods) >= 2 ** 53).any():
        raise WorkflowError('独立预处理复核时间超出精确整数范围')
    if frame[step['entity']].eq('').any().any():
        raise WorkflowError('独立预处理复核面板实体缺失')
    periods = periods.astype('int64')
    values = _numeric(frame[step['source']], pd, np)
    entities = {f'key{i}': frame[name].to_numpy() for i, name in enumerate(step['entity'])}
    right = pd.DataFrame(dict(entities, period=periods, previous=values))
    keys = list(entities) + ['period']
    if right.duplicated(keys).any():
        raise WorkflowError('独立预处理复核面板实体时间重复')
    left = pd.DataFrame(dict(entities, period=periods - step['interval'], position=np.arange(len(frame))))
    aligned = left.merge(right, on=keys, how='left', sort=False, validate='many_to_one').sort_values('position')
    lag = aligned['previous'].to_numpy(dtype=float)
    return lag if step['op'] == 'lag' else values - lag


def _reference(frame, recipe, pd, np):
    for step in recipe['steps']:
        op = step['op']
        if op == 'filter':
            frame = _filter(frame, step, pd, np)
            continue
        if op in {'winsor', 'center', 'standardize'}:
            output = _groups(frame, step, pd, np)
        elif op in {'lag', 'difference'}:
            output = _panel(frame, step, pd, np)
        elif op == 'indicator':
            source = frame[step['source']]
            missing = source.eq('').to_numpy()
            if missing.any() and step['missing'] == 'error':
                raise WorkflowError('独立预处理复核 indicator 缺失策略不满足')
            output = source.eq(step['value']).to_numpy(dtype=float)
            if step['missing'] == 'missing':
                output[missing] = np.nan
        else:
            columns = (step['sources'] if op == 'interaction' else [step['numerator'], step['denominator']]
                       if op == 'ratio' else [step['source']])
            numbers = np.column_stack([_numeric(frame[column], pd, np) for column in columns])
            complete = np.isfinite(numbers).all(axis=1)
            output = np.full(len(frame), np.nan)
            if op == 'interaction':
                output[complete] = np.prod(numbers[complete], axis=1)
            elif op == 'ratio':
                zero = complete & (numbers[:, 1] == 0)
                if zero.any() and step['zero'] == 'error':
                    raise WorkflowError('独立预处理复核 ratio 分母为零')
                valid = complete & ~zero
                output[valid] = numbers[valid, 0] / numbers[valid, 1]
            else:
                domain = numbers[:, 0] > (0 if op == 'ln' else -1)
                if (complete & ~domain).any() and step['invalid'] == 'error':
                    raise WorkflowError('独立预处理复核对数定义域无效')
                valid = complete & domain
                output[valid] = (np.log if op == 'ln' else np.log1p)(numbers[valid, 0])
        if np.isinf(output).any():
            raise WorkflowError('独立预处理计算产生非有限数值')
        frame[step['target']] = pd.Series(['' if np.isnan(value) else '0' if value == 0 else format(value, '.17g')
                                           for value in output], index=frame.index, dtype=str)
    return frame


def verify_preparation(raw, recipe, actual_csv):
    """Compare all cells against an independent reference, with exact raw text.

    Invalid source/recipe or unavailable dependencies raise WorkflowError.
    Invalid or mismatched actual output returns check_status='failed'.
    """
    try:
        import numpy as np
        import pandas as pd
    except ImportError as exc:
        raise WorkflowError('独立预处理复核需要安装 analysis 依赖 numpy/pandas') from exc
    original = _frame(raw, pd)
    recipe = validate_recipe(recipe, list(original.columns))
    if original[recipe['keys']].eq('').any().any() or original.duplicated(recipe['keys']).any():
        raise WorkflowError('独立预处理复核原始键缺失或重复')
    try:
        with np.errstate(over='raise', divide='raise', invalid='raise'):
            expected = _reference(original.copy(), recipe, pd, np)
    except (FloatingPointError, OverflowError, ValueError) as exc:
        raise WorkflowError('独立预处理参考计算无法完成') from exc
    result = dict(check_status='failed', checks=[], reference=dict(engine='independent_numpy_pandas',
                  numpy=np.__version__, pandas=pd.__version__, rtol=RTOL, atol=ATOL, n_expected=len(expected)))

    def check(name, passed, **details):
        result['checks'].append(dict(name=name, passed=bool(passed), **details))

    try:
        actual = _frame(actual_csv, pd, allow_empty=True)
    except WorkflowError as exc:
        check('output_csv', False, detail=str(exc))
        return result
    check('headers', list(actual.columns) == list(expected.columns))
    check('row_count', len(actual) == len(expected), expected=len(expected), actual=len(actual))
    if not all(item['passed'] for item in result['checks']):
        return result
    check('keys_and_order', actual[recipe['keys']].equals(expected[recipe['keys']]))
    check('original_cells', actual[list(original.columns)].equals(expected[list(original.columns)]))
    for name in expected.columns:
        if name in original.columns:
            continue
        expected_missing, actual_missing = expected[name].eq(''), actual[name].eq('')
        check(f'{name}:missing', expected_missing.equals(actual_missing))
        try:
            actual_values = _numeric(actual[name], pd, np)
            expected_values = _numeric(expected[name], pd, np)
            check(f'{name}:zero_pattern', np.array_equal(actual_values == 0, expected_values == 0))
            close = np.isclose(actual_values, expected_values, rtol=RTOL, atol=ATOL, equal_nan=True)
            check(f'{name}:values', close.all(), mismatches=int((~close).sum()))
        except WorkflowError as exc:
            check(f'{name}:values', False, detail=str(exc))
    result['check_status'] = 'passed' if all(item['passed'] for item in result['checks']) else 'failed'
    return result
