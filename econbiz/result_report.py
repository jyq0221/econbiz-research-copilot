"""Traceable tables and bounded explanations consuming only verified results."""

import csv
import html
import io

from .state import WorkflowError
from .workspace import encode_json


def describe_interval(low, high):
    if low <= 0 <= high:
        return '95% 区间包含零，仍兼容区间内的负向与正向关联；需结合有意义的幅度判断精度，不能据此认定没有关系。'
    direction = '正向' if low > 0 else '负向'
    return f'95% 区间位于零的同一侧，支持该设定下的{direction}条件关联；其实际意义仍需结合变量单位与研究背景。'


def _fmt(value):
    return '—' if value is None else format(value, '.6g')


def _md(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def render_markdown(content):
    sample = content['sample']
    lines = ['# 分析结果与证据', '', f'研究问题：{_md(content["question"])}', '',
             f'正式执行：{_md(content.get("backend", "python"))}；独立复核：Python 独立参考算法。', '',
             f'运行前判断：{_md(content["judgment"])}', '',
             f'分析样本：{sample["final_rows"]} 个观测，{sample["entities"]} 个主体。'
             f'加入控制变量的额外完整案例损失：{sample["control_additional_loss"]} 个观测。', '',
             f'固定效应：{_md("、".join(content["fixed_effects"]) or "无（描述统计）")}；'
             f'标准误：{_md(content["standard_errors"]["method"])}。', '',
             '## 回归结果', '', '| 变量 | 系数 | 标准误 | p 值 | 95% 区间 |',
             '| --- | ---: | ---: | ---: | --- |']
    for item in content['evidence']:
        lines.append(f'| {_md(item["term"])} | {_fmt(item["coefficient"])} | {_fmt(item["std_error"])} | '
                     f'{_fmt(item["p_value"])} | [{_fmt(item["ci_low"])}, {_fmt(item["ci_high"])}] |')
    if not content['evidence']:
        lines.append('本次为描述统计，无回归系数。')
    lines += ['', '## 判断与数值依据', '']
    for item in content['evidence']:
        lines.extend([f'- **{_md(item["term"])}**：{_md(item["interpretation"])} '
                      f'{_md(item["interval_interpretation"])}',
                      f'  来源：{_md(item["source_field"])}。'])
    lines += ['', '## 描述统计（同一分析样本）', '',
              '| 字段 | N | 均值 | 标准差 | 最小值 | 中位数 | 最大值 |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for field, values in content['descriptive'].items():
        lines.append('| ' + _md(field) + ' | ' + ' | '.join(_fmt(values.get(k)) for k in
                     ['count', 'mean', 'std', 'min', 'median', 'max']) + ' |')
    lines += ['', '## 检查范围与下一步', '',
              '独立数值核验通过：已核对样本、模型设定、关键数值及适用的秩与标准误。',
              '数值核验不认证聚类层级是否适合研究设计，也不认证因果识别假设。',
              f'原方案结论边界：{_md(content["boundary"])}',
              '下一步：结合变量含义、比较对象和诊断评估原判断；如需改变设定，记录理由并确认新版本。']
    lines += ['- ' + _md(w) for w in content['warnings']]
    lines += ['', f'来源：方案 {_md(content["plan_id"])} v{content["plan_version"]}；运行 {_md(content["run_id"])}。',
              '本文件为生成时的版本快照；继续研究前从项目接口检查该结果是否仍有效。', '']
    return '\n'.join(lines)


def render_html(content):
    esc = html.escape
    sample = content['sample']
    rows = ''.join('<tr><td>' + esc(item['term']) + '</td>' + ''.join(
        '<td>' + esc(_fmt(item[key])) + '</td>' for key in
        ['coefficient', 'std_error', 'p_value', 'ci_low', 'ci_high']) + '</tr>' for item in content['evidence'])
    details = ''.join('<article><h3>' + esc(item['term']) + '</h3><p>' + esc(item['interpretation']) +
                      '</p><p>' + esc(item['interval_interpretation']) + '</p><small>' + esc(item['source_field']) +
                      '</small></article>' for item in content['evidence'])
    descriptions = ''.join('<tr><td>' + esc(field) + '</td>' + ''.join('<td>' + esc(_fmt(values.get(k))) +
                          '</td>' for k in ['count', 'mean', 'std', 'min', 'median', 'max']) + '</tr>'
                          for field, values in content['descriptive'].items())
    warnings = ''.join('<li>' + esc(str(w)) + '</li>' for w in content['warnings'])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>分析结果与证据</title><style>
body{{margin:0;background:#f4f5f1;color:#1d3333;font:16px/1.75 system-ui,-apple-system,sans-serif}}
main{{max-width:1050px;margin:40px auto;padding:0 28px}}header{{border-top:5px solid #246a62;padding:22px 0}}
h1{{font-size:34px;margin:10px 0}}h2{{margin-top:38px;font-size:23px}}small,.muted{{color:#556a69}}
.cards{{display:flex;gap:16px;flex-wrap:wrap}}.card,article{{background:white;border:1px solid #dce4df;border-radius:10px;padding:18px 22px}}
.card{{flex:1;min-width:170px}}.number{{display:block;font-size:30px;font-weight:650}}article{{margin:12px 0}}
table{{width:100%;border-collapse:collapse;background:white;font-variant-numeric:tabular-nums}}th,td{{padding:12px;text-align:right;border-bottom:1px solid #e0e5e1}}
th:first-child,td:first-child{{text-align:left}}th{{border-top:2px solid #246a62;border-bottom:1px solid #246a62}}tr:last-child td{{border-bottom:2px solid #246a62}}
.scroll{{overflow-x:auto}}footer{{margin:36px 0;border-top:1px solid #b9cbc6;padding-top:20px;font-size:14px}}
@media print{{body{{background:white}} main{{margin:0;max-width:none}} article{{break-inside:avoid}}}}
</style><main><header><small>经管研究助手 · 已核对的运行结果</small><h1>分析结果与证据</h1>
<p>{esc(content['question'])}</p><p class="muted">运行前判断：{esc(content['judgment'])}</p>
<p class="muted">正式执行：{esc(content.get('backend', 'python'))} · 独立复核：Python 独立参考算法</p></header>
<section class="cards"><div class="card">分析观测<span class="number">{sample['final_rows']}</span></div>
<div class="card">研究主体<span class="number">{sample['entities']}</span></div>
<div class="card">控制变量带来的额外样本损失<span class="number">{sample['control_additional_loss']}</span></div></section>
<h2>回归结果</h2><p>固定效应：{esc('、'.join(content['fixed_effects']) or '无（描述统计）')}；标准误：{esc(content['standard_errors']['method'])}。</p>
<div class="scroll"><table><thead><tr><th>变量</th><th>系数</th><th>标准误</th><th>p 值</th><th>95% 下限</th><th>95% 上限</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>判断与证据</h2>{details or '<p>本次为描述统计，无回归系数。</p>'}
<h2>描述统计 · 同一分析样本</h2><div class="scroll"><table><thead><tr><th>字段</th><th>N</th><th>均值</th><th>标准差</th><th>最小值</th><th>中位数</th><th>最大值</th></tr></thead><tbody>{descriptions}</tbody></table></div>
<h2>检查范围与下一步</h2><p>独立数值核验通过。核对范围包括样本、模型设定和关键数值；推断条件与因果识别仍需结合研究设计判断。</p>
<p>{esc(content['boundary'])}</p><ul>{warnings}</ul><p>下一步：评估变量含义、比较对象、区间精度和原判断；改变设定时记录理由并确认新版本。</p>
<footer>方案 {esc(content['plan_id'])} v{content['plan_version']} · 运行 {esc(content['run_id'])}<br>
生成时的版本快照。继续使用前通过项目接口检查结果是否仍有效。</footer></main></html>'''


def write_result_report(workspace, report_id, run_id):
    run = workspace.project.require_usable(run_id)
    if run['kind'] != 'result' or run['content'].get('verification', {}).get('check_status') != 'passed':
        raise WorkflowError('报告需要本项目正式执行并通过独立核验的结果')
    data = run['content']
    plan, result = data['plan'], data['result']
    evidence = []
    for index, parameter in enumerate(result['parameters']):
        term = parameter['term']
        mapping = next((m for m in plan['mapping'].values() if m['field'] == term), {})
        x_unit = mapping.get('unit', '未提供，需结合变量说明')
        y_unit = plan['mapping'].get('y', {}).get('unit', '未提供')
        text = (f'在本模型的其他变量与固定效应条件下，{term} 每增加 1 个记录单位（{x_unit}），'
                f'因变量的条件关联变化为 {_fmt(parameter["coefficient"])}（{y_unit}）。')
        evidence.append(dict(parameter, x_unit=x_unit, y_unit=y_unit, interpretation=text,
                             interval_interpretation=describe_interval(parameter['ci_low'], parameter['ci_high']),
                             source_field=f'{data["package"]}/outputs/result.json:parameters[{index}]'))
    content = dict(run_id=run_id, run_version=run['version'], plan_id=data['plan_id'], plan_version=data['plan_version'],
                   backend=data.get('backend', 'python'), replication_of=data.get('replication_of'),
                   question=plan['question'], judgment=plan['judgment'], boundary=plan['boundary'],
                   purpose=plan['purpose'], scope='描述统计或条件关联', evidence=evidence,
                   descriptive=result['descriptive'], sample=data['sample'],
                   fixed_effects=result['actual_spec']['fixed_effects'], standard_errors=result['actual_spec']['standard_errors'],
                   diagnostics=result['diagnostics'], warnings=result['warnings'])
    version = workspace._version_number(report_id)
    prefix = f'{workspace.layout["research_reports"]}/{report_id}/v{version:04d}'
    csv_stream = io.StringIO(newline='')
    writer = csv.writer(csv_stream, lineterminator='\n')
    fields = ['term', 'coefficient', 'std_error', 'p_value', 'ci_low', 'ci_high']
    writer.writerow(fields)
    for row in evidence:
        term = row['term']
        safe_term = "'" + term if term.startswith(('=', '+', '-', '@')) else term
        writer.writerow([safe_term] + [row[k] for k in fields[1:]])
    writes = [(prefix + '/report.json', encode_json(content)),
              (prefix + '/report.md', render_markdown(content).encode('utf-8')),
              (prefix + '/report.html', render_html(content).encode('utf-8')),
              (prefix + '/coefficients.csv', csv_stream.getvalue().encode('utf-8'))]
    files = [workspace._file(path, raw, 'checked_result_report') for path, raw in writes]
    staged = workspace._stage(report_id, 'result_report', content, [run_id], files, '生成可追溯表格和条件关联解释')
    staged.mark(report_id, 'completed', 'passed', '报告数值来自当前已核验运行，保留全部系数与区间')
    workspace._publish(staged, writes)
    return workspace.project.artifact(report_id)
