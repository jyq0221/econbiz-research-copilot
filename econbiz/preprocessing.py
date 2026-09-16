"""Bounded CSV preparation with explicit recipes and preserved source values.

Only the empty string is missing. Numeric source text is parsed strictly when an
operation consumes it; other labels must be resolved by a documented earlier
decision. These deterministic audit records are not independent verification.
"""

import csv
import io
import json
import math
import re
import statistics
from collections import Counter
from copy import deepcopy

from .execution_spec import read_csv
from .state import WorkflowError


_FIELDS = {
    'winsor': {'source', 'target', 'lower', 'upper', 'by'},
    'ln': {'source', 'target', 'invalid'},
    'log1p': {'source', 'target', 'invalid'},
    'ratio': {'numerator', 'denominator', 'target', 'zero'},
    'interaction': {'sources', 'target'},
    'indicator': {'source', 'target', 'value', 'missing'},
    'center': {'source', 'target', 'by'},
    'standardize': {'source', 'target', 'by', 'ddof', 'zero'},
    'lag': {'source', 'target', 'entity', 'time', 'interval'},
    'difference': {'source', 'target', 'entity', 'time', 'interval'},
}


def _names(value, label, *, empty=False):
    if (not isinstance(value, list) or (not value and not empty)
            or any(not isinstance(v, str) or not v.strip() for v in value)
            or len(set(value)) != len(value)):
        raise WorkflowError(f'{label} 须为不重复的字段名称列表')
    return value


def _finite(value):
    try:
        return type(value) in {int, float} and math.isfinite(value)
    except OverflowError:
        return False


def validate_recipe(recipe, columns=None):
    """Validate all options; with columns, also validate ordered dependencies."""
    if (not isinstance(recipe, dict) or set(recipe) != {'schema_version', 'keys', 'steps'}
            or type(recipe['schema_version']) is not int or recipe['schema_version'] != 1
            or not isinstance(recipe['steps'], list)):
        raise WorkflowError('预处理 recipe 必须仅含 schema_version=1、keys、steps')
    _names(recipe['keys'], 'keys')
    available = set(columns) if columns is not None else None
    targets = set(recipe['keys'])
    if available is not None and not set(recipe['keys']) <= available:
        raise WorkflowError('预处理 keys 不在 CSV 表头中')
    for index, step in enumerate(recipe['steps'], 1):
        if not isinstance(step, dict) or not isinstance(step.get('op'), str):
            raise WorkflowError(f'步骤 {index} 缺少有效 op')
        op = step['op']
        if op == 'filter':
            operator = step.get('operator')
            if operator not in ('eq', 'ne', 'in', 'not_in', 'gt', 'ge', 'lt', 'le', 'is_missing', 'not_missing'):
                raise WorkflowError('filter operator 不受支持')
            fields = {'source', 'operator'} | (set() if operator in {'is_missing', 'not_missing'} else {'value'})
        elif op in _FIELDS:
            fields = _FIELDS[op]
        else:
            raise WorkflowError(f'不支持的预处理 op: {op}')
        if set(step) != fields | {'op'}:
            raise WorkflowError(f'{op} 选项须恰好为 {sorted(fields)}')
        refs = []
        for key in ('source', 'numerator', 'denominator', 'time'):
            if key in step:
                if not isinstance(step[key], str) or not step[key].strip():
                    raise WorkflowError(f'{op}.{key} 须为字段名称')
                refs.append(step[key])
        for key in ('sources', 'by', 'entity'):
            if key in step:
                refs.extend(_names(step[key], f'{op}.{key}', empty=key == 'by'))
        if available is not None and not set(refs) <= available:
            raise WorkflowError(f'{op} 引用了尚不存在的字段: {sorted(set(refs) - available)}')
        if 'target' in step:
            target = step['target']
            if (not isinstance(target, str) or not target.strip() or target in targets
                    or target in refs or (available is not None and target in available)):
                raise WorkflowError('target 须为新的字段，不能覆盖原列、键或已有派生列')
            targets.add(target)
            if available is not None:
                available.add(target)
        if op == 'winsor' and (not _finite(step['lower']) or not _finite(step['upper'])
                               or not 0 <= step['lower'] <= step['upper'] <= 1):
            raise WorkflowError('winsor 须明确 0 <= lower <= upper <= 1')
        if op in {'ln', 'log1p'} and step['invalid'] not in ('error', 'missing'):
            raise WorkflowError('invalid 须为 error 或 missing')
        if op in {'ratio', 'standardize'} and step['zero'] not in ('error', 'missing'):
            raise WorkflowError('zero 须为 error 或 missing')
        if op == 'interaction' and len(step['sources']) < 2:
            raise WorkflowError('interaction 至少需要两个不同来源列')
        if op == 'indicator' and (not isinstance(step['value'], str) or step['value'] == ''
                                   or step['missing'] not in ('missing', 'zero', 'error')):
            raise WorkflowError('indicator 须明确非空文本类别 value，以及 missing/zero/error 缺失规则')
        if op == 'standardize' and (type(step['ddof']) is not int or step['ddof'] not in {0, 1}):
            raise WorkflowError('standardize ddof 须明确为 0 或 1')
        if op in {'lag', 'difference'}:
            if (type(step['interval']) is not int or not 0 < step['interval'] < 2 ** 53
                    or step['time'] in step['entity']):
                raise WorkflowError('面板须指定分开的 entity/time 及正整数 interval')
        if op == 'filter':
            operator = step['operator']
            value = step.get('value')
            if operator in {'eq', 'ne'} and not isinstance(value, str):
                raise WorkflowError('eq/ne 筛选使用精确文本值')
            if operator in {'in', 'not_in'} and (not isinstance(value, list) or not value
                    or any(not isinstance(v, str) for v in value) or len(set(value)) != len(value)):
                raise WorkflowError('in/not_in 筛选使用非空且不重复的文本列表')
            if operator in {'gt', 'ge', 'lt', 'le'} and not _finite(value):
                raise WorkflowError('数值筛选阈值须为有限数值')
    return deepcopy(recipe)


def _number(value, name):
    if value == '':
        return None
    if not re.fullmatch(r' *[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)? *', value):
        raise WorkflowError(f'{name} 包含未解释的数值文本: {value!r}')
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise WorkflowError(f'{name} 包含未解释的数值文本: {value!r}') from exc
    if not math.isfinite(result):
        raise WorkflowError(f'{name} 包含非有限数值: {value!r}')
    return result


def _text(number):
    if number is None:
        return ''
    if not math.isfinite(number):
        raise WorkflowError('预处理运算产生非有限值；拒绝保存结果')
    return '0' if number == 0 else format(number, '.17g')


def _csv(columns, rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def _key_counts(rows, keys, label):
    result = Counter()
    for row in rows:
        key = tuple(row[c] for c in keys)
        if any(v == '' for v in key):
            raise WorkflowError(f'{label} 存在缺失键')
        result[key] += 1
    return result


def _quantile(values, probability):
    position = (len(values) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def _keep(row, step):
    value, operator = row[step['source']], step['operator']
    target = step.get('value')
    if operator == 'is_missing':
        return value == ''
    if operator == 'not_missing':
        return value != ''
    if operator == 'eq':
        return value == target
    if operator == 'ne':
        return value != target
    if operator in {'in', 'not_in'}:
        return (value in target) == (operator == 'in')
    number = _number(value, step['source'])
    if number is None:
        return False
    return {'gt': number > target, 'ge': number >= target,
            'lt': number < target, 'le': number <= target}[operator]


def _group_transform(rows, step, report):
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(tuple(row[c] for c in step['by']), []).append(i)
    output = [None] * len(rows)
    report['groups'] = []
    for key, indices in groups.items():
        numbers = {i: _number(rows[i][step['source']], step['source']) for i in indices}
        values = sorted(v for v in numbers.values() if v is not None)
        info = dict(group=dict(zip(step['by'], key)), n_rows=len(indices), n_nonmissing=len(values))
        if step['op'] == 'winsor':
            lower = _quantile(values, step['lower']) if values else None
            upper = _quantile(values, step['upper']) if values else None
            info.update(lower_threshold=lower, upper_threshold=upper, quantile_method='linear_n_minus_1')
            for i, value in numbers.items():
                output[i] = None if value is None else min(max(value, lower), upper)
            info['affected'] = sum(output[i] != numbers[i] for i in indices)
        else:
            mean = statistics.mean(values) if values else None
            info['mean'] = mean
            sd = None
            if step['op'] == 'standardize':
                denominator = len(values) - step['ddof']
                if denominator > 0:
                    centered = [v - mean for v in values]
                    scale = max(abs(v) for v in centered)
                    if not math.isfinite(scale):
                        raise WorkflowError('standardize 中心化计算溢出')
                    sd = scale * math.sqrt(math.fsum((v / scale) ** 2 for v in centered) / denominator) if scale else 0.0
                    if not math.isfinite(sd) or (scale and sd == 0):
                        raise WorkflowError('standardize 标准差超出有限数值范围')
                info.update(sd=sd, ddof=step['ddof'])
                if values and (sd is None or sd == 0) and step['zero'] == 'error':
                    raise WorkflowError(f'standardize 分组 {key} 标准差为零或自由度不足')
            for i, value in numbers.items():
                if value is None:
                    continue
                if step['op'] == 'center':
                    output[i] = value - mean
                elif sd is not None and sd > 0:
                    output[i] = (value - mean) / sd
                else:
                    report['invalid_to_missing'] += 1
            info['affected'] = sum(output[i] != numbers[i] for i in indices)
        report['groups'].append(info)
    report['affected'] = sum(g['affected'] for g in report['groups'])
    return output


def _panel_transform(rows, step, report):
    lookup, periods = {}, []
    for row in rows:
        entity = tuple(row[c] for c in step['entity'])
        time = _number(row[step['time']], step['time'])
        if (any(v == '' for v in entity) or time is None or abs(time) >= 2 ** 53
                or not re.fullmatch(r' *[+-]?[0-9]+(?:\.0+)? *', row[step['time']])):
            raise WorkflowError('lag/difference 须有非缺失实体及可精确表示的整数时间')
        key = (entity, int(time))
        if key in lookup:
            raise WorkflowError('lag/difference entity/time 存在重复')
        lookup[key] = _number(row[step['source']], step['source'])
        periods.append(key)
    output, unmatched = [], 0
    for key in periods:
        previous = (key[0], key[1] - step['interval'])
        if previous not in lookup:
            unmatched += 1
        lag = lookup.get(previous)
        value = lookup[key]
        output.append(lag if step['op'] == 'lag' else
                      None if lag is None or value is None else value - lag)
    report['unmatched_periods'] = unmatched
    return output


def prepare_data(raw, recipe):
    """Return a derived CSV and audit; source columns are never overwritten."""
    columns, rows = read_csv(raw)
    recipe = validate_recipe(recipe, columns)
    if max(_key_counts(rows, recipe['keys'], '输入').values(), default=0) > 1:
        raise WorkflowError('预处理 keys 存在重复，须明确观测标识')
    audit = dict(schema_version=1, operation='prepare_data', recipe=recipe,
                 n_before=len(rows), n_after=None, original_columns=list(columns), steps=[],
                 missing_rule='empty_string_only', verification='not_independently_verified')
    for index, step in enumerate(recipe['steps'], 1):
        op = step['op']
        report = dict(index=index, op=op, parameters=deepcopy(step), n_before=len(rows),
                      affected=0, invalid_to_missing=0)
        if op == 'filter':
            rows = [row for row in rows if _keep(row, step)]
            report['affected'] = report['n_before'] - len(rows)
        else:
            if op in {'winsor', 'center', 'standardize'}:
                output = _group_transform(rows, step, report)
            elif op in {'lag', 'difference'}:
                output = _panel_transform(rows, step, report)
            else:
                output = []
                for row in rows:
                    result = None
                    if op == 'indicator':
                        value = row[step['source']]
                        if value == '' and step['missing'] == 'error':
                            raise WorkflowError('indicator 来源存在缺失值')
                        if value != '' or step['missing'] == 'zero':
                            result = int(value == step['value'])
                    else:
                        sources = (step['sources'] if op == 'interaction' else
                                   [step['numerator'], step['denominator']] if op == 'ratio' else [step['source']])
                        values = [_number(row[c], c) for c in sources]
                        if all(v is not None for v in values):
                            if op in {'ln', 'log1p'}:
                                valid = values[0] > (0 if op == 'ln' else -1)
                                if not valid and step['invalid'] == 'error':
                                    raise WorkflowError(f'{op} 定义域无效')
                                result = (math.log(values[0]) if op == 'ln' else math.log1p(values[0])) if valid else None
                            elif op == 'ratio':
                                if values[1] == 0 and step['zero'] == 'error':
                                    raise WorkflowError('ratio 分母为零')
                                result = values[0] / values[1] if values[1] != 0 else None
                            else:
                                result = math.prod(values)
                            if result is None:
                                report['invalid_to_missing'] += 1
                    output.append(result)
            for row, value in zip(rows, output):
                row[step['target']] = _text(value)
            columns.append(step['target'])
            report['output_nonmissing'] = sum(value is not None for value in output)
            report['output_missing'] = len(output) - report['output_nonmissing']
            if op not in {'winsor', 'center', 'standardize'}:
                report['affected'] = report['output_nonmissing'] + report['invalid_to_missing']
        report['n_after'] = len(rows)
        audit['steps'].append(report)
    audit['n_after'] = len(rows)
    audit['columns'] = columns
    # Reject accidental non-JSON/non-finite audit values before returning a result.
    try:
        json.dumps(audit, allow_nan=False)
    except (ValueError, OverflowError) as exc:
        raise WorkflowError('预处理审计产生非有限值') from exc
    return _csv(columns, rows), audit


def merge_data(left, right, *, keys, relationship, how):
    """Merge without deduplication, enforcing declared keys and cardinality."""
    _names(keys, 'merge keys')
    if relationship not in ('one_to_one', 'many_to_one') or how not in ('left', 'inner'):
        raise WorkflowError('merge 支持 one_to_one/many_to_one 和 left/inner')
    lc, lr = read_csv(left)
    rc, rr = read_csv(right)
    if not set(keys) <= set(lc) or not set(keys) <= set(rc):
        raise WorkflowError('merge keys 不在双方 CSV 表头中')
    if (set(lc) & set(rc)) - set(keys):
        raise WorkflowError('merge 非键同名列冲突；须先明确重命名')
    lcounts, rcounts = _key_counts(lr, keys, '左表'), _key_counts(rr, keys, '右表')
    if max(rcounts.values(), default=0) > 1 or (relationship == 'one_to_one' and max(lcounts.values(), default=0) > 1):
        raise WorkflowError('merge 键的实际基数不符合 relationship，禁止自动去重')
    additions = [c for c in rc if c not in keys]
    lookup = {tuple(row[k] for k in keys): row for row in rr}
    output = []
    for row in lr:
        match = lookup.get(tuple(row[k] for k in keys))
        if match is not None or how == 'left':
            output.append(dict(row, **{c: match[c] if match is not None else '' for c in additions}))
    audit = dict(schema_version=1, operation='merge_data', keys=list(keys), relationship=relationship,
                 how=how, left_rows=len(lr), right_rows=len(rr), n_after=len(output),
                 left_unmatched_rows=sum(n for key, n in lcounts.items() if key not in rcounts),
                 right_unmatched_rows=sum(n for key, n in rcounts.items() if key not in lcounts),
                 matched_left_rows=sum(n for key, n in lcounts.items() if key in rcounts),
                 verification='not_independently_verified')
    return _csv(lc + additions, output), audit
