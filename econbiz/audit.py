"""Read-only CSV inventory. A passed check certifies only these structural checks."""

import csv
import hashlib
import io
import math
from collections import Counter, defaultdict
from pathlib import Path

MISSING = {'', '未披露', '不适用', '匹配失败', '不确定', 'NA', 'N/A', 'NULL', 'null'}


def audit_csv(path, entity, time, numeric=()):
    path = Path(path)
    raw = path.read_bytes()
    report = dict(input_path=str(path.resolve()), input_sha256=hashlib.sha256(raw).hexdigest(),
                  key={'entity': entity, 'time': time},
                  columns=[], rows=0, entities=0,
                  periods=[], missing={}, numeric={}, issues=[], check_status='passed')
    def issue(code, message, **evidence):
        report['issues'].append(dict(category='execution_error', code=code, message=message, **evidence))
        report['check_status'] = 'failed'
    rows, source_lines = [], []
    try:
        reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
        while True:
            start = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            rows.append(row)
            source_lines.append(start)
    except (UnicodeDecodeError, csv.Error) as exc:
        report.update(columns=rows[0] if rows else [], rows=max(0, len(rows) - 1), partial=True)
        issue('csv_parse_error', '无法完整解析 UTF-8 CSV；不使用部分数据', detail=str(exc))
        return report
    report.update(columns=rows[0] if rows else [], rows=max(0, len(rows) - 1), partial=False)
    columns = report['columns']
    if not columns or any(not c.strip() for c in columns) or len(set(columns)) != len(columns):
        issue('invalid_header', '表头为空、列名为空或列名重复')
        return report
    numeric = list(dict.fromkeys(numeric))
    absent = sorted(set([entity, time] + numeric) - set(columns))
    if absent:
        issue('missing_columns', '请求字段不存在', fields=absent)
        return report
    if entity == time:
        issue('invalid_key', '主体列与期间列必须不同')
        return report
    if not report['rows']:
        issue('empty_data', '文件不包含数据行')
    missing = {c: Counter() for c in columns}
    values = {c: [] for c in numeric}
    keys = defaultdict(list)
    entities, periods = set(), set()
    for line, row in zip(source_lines[1:], rows[1:]):
        if len(row) != len(columns):
            issue('row_width', '数据行列数与表头不一致', lines=[line], expected=len(columns), actual=len(row))
            continue
        record = dict(zip(columns, row))
        for c, value in record.items():
            if value.strip() in MISSING:
                missing[c][value] += 1
        key = (record[entity], record[time])
        if any(v.strip() in MISSING for v in key):
            issue('missing_key', '主体或期间为空/缺失标记', lines=[line], key=list(key))
        else:
            keys[key].append(line)
            entities.add(key[0])
            periods.add(key[1])
        for c in numeric:
            value = record[c].strip()
            if value in MISSING:
                continue
            try:
                number = float(value)
            except ValueError:
                issue('invalid_numeric', '声明为数值的字段包含未解释文本', lines=[line], field=c, raw=record[c])
                continue
            if not math.isfinite(number):
                issue('nonfinite_numeric', '数值包含 NaN 或无穷值', lines=[line], field=c, raw=record[c])
            else:
                values[c].append(number)
    for key, lines in keys.items():
        if len(lines) > 1:
            issue('duplicate_key', '企业年度键重复，不自动去重', key=list(key), lines=lines)
    report.update(entities=len(entities), periods=sorted(periods),
                  missing={c: dict(counts) for c, counts in missing.items()},
                  numeric={c: dict(count=len(v), min=min(v) if v else None,
                                   max=max(v) if v else None) for c, v in values.items()})
    report['scope'] = '仅核对结构、原始缺失标记和声明数值；字段含义、年度口径与模型条件仍需确认。'
    return report
