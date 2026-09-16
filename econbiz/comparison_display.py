"""One display model for editable Word and readable Markdown; no estimation."""

import math
from .state import WorkflowError


def significance_marks(p, rules):
    previous, labels = 0, set()
    if not isinstance(rules, (list, tuple)):
        raise WorkflowError('星号规则须为阈值与标记列表')
    for pair in rules:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise WorkflowError('星号规则格式错误')
        threshold, label = pair
        if (type(threshold) not in {int,float} or not math.isfinite(threshold) or
                not previous < threshold <= 1 or not isinstance(label, str) or not label.strip() or label in labels):
            raise WorkflowError('星号阈值须递增且标记唯一')
        previous = threshold
        labels.add(label)
    if p is None:
        return ''
    if type(p) not in {int,float} or not math.isfinite(p) or not 0 <= p <= 1:
        raise WorkflowError('p 值无效')
    return next((label for t, label in rules if p < t), '')


def format_number(value, digits=3):
    if value is None:
        return '未提供'
    if type(value) not in {int,float} or not math.isfinite(value):
        raise WorkflowError('表格数值须有限')
    text = format(value, f'.{digits}f')
    return text[1:] if text.startswith('-') and float(text) == 0 else text


def describe_sample_rule(rule):
    if 'complete_case' in rule:
        return '剔除 '+rule['complete_case']+' 缺失的观测'
    operators = dict(eq='等于', ne='不等于', ge='不小于', le='不大于', **{'in':'属于'})
    value = rule['value']
    value = '、'.join(map(str,value)) if isinstance(value,list) else str(value)
    return rule['field']+' '+operators[rule['op']]+' '+value


def build_display(c):
    groups = {}
    for i, m in enumerate(c['models']):
        r = m['run']['id']
        y = next(v for v in c['variables'] if v['members'].get(r) == m['actual_spec']['y'])
        groups.setdefault(y['id'], (y, []))[1].append((i, m))
    tables, paragraphs = [], []
    for y, group in groups.values():
        # Bound widths while preserving original column numbers across split tables.
        for start in range(0, len(group), 6):
            subset = group[start:start+6]
            header = ['变量'] + [f'({i+1}) {m["title"]}' for i,m in subset]
            rows = []
            for v in c['variables']:
                if c['display_terms'] is not None and v['id'] not in c['display_terms']:
                    continue
                if not any(v['members'].get(m['run']['id']) in m['actual_spec']['x'] for _,m in group):
                    continue
                cells = []
                for _,m in subset:
                    field = v['members'].get(m['run']['id'])
                    parameter = next((p for p in m['parameters'] if p['term'] == field), None)
                    cells.append('未纳入' if parameter is None else
                        format_number(parameter['coefficient']) + significance_marks(parameter['p_value'], c['stars']) +
                        '\n(' + format_number(parameter['std_error']) + ')')
                rows.append([v['label']] + cells)
            stats = [
                ('观测数', lambda m: str(m['sample']['final_rows'])),
                ('主体数', lambda m: str(m['sample']['entities'])),
                ('实际年份', lambda m: '、'.join(m['sample']['periods'])),
                ('解释变量', lambda m: '、'.join(m['actual_spec']['x'])),
                ('控制变量', lambda m: '、'.join(m['controls']) or '无'),
                ('固定效应', lambda m: '、'.join(m['actual_spec']['fixed_effects'])),
                ('标准误', lambda m: m['actual_spec']['standard_errors']['method']),
                ('聚类字段', lambda m: m['actual_spec']['standard_errors'].get('field') or '不适用'),
                ('聚类数', lambda m: str(m['diagnostics'].get('cluster_count') or '不适用')),
                ('引擎', lambda m: m['backend']),
                ('用途', lambda m: {'baseline':'基准','robustness':'稳健性','other':'其他'}[m['role']]),
                ('统计核验', lambda m: '已独立核验')]
            rows.extend([label]+[fn(m) for _,m in subset] for label,fn in stats)
            notes = ['括号内为标准误。系数表示条件关联。精确 p 值、置信区间和完整参数保存在比较记录。']
            if c['stars']:
                notes.append('；'.join(f'{label} p < {t}' for t,label in c['stars'])+'，按未舍入 p 值判断。')
            if c['display_terms'] is not None:
                notes.append('仅展示指定变量：'+ '、'.join(c['display_terms'])+'；其余参数保留在完整记录。')
            tables.append(dict(title='因变量 '+ y['label']+'（'+(y['unit'] or '单位未提供')+'）',
                               header=header, rows=rows, notes=notes, kind='models'))
    for d in c['differences']:
        paragraphs.append(f'{d["left"]} 与 {d["right"]}：共同观测 {d["intersection_count"]}，'
            f'仅前者 {len(d["left_only"])}，仅后者 {len(d["right_only"])}；'
            f'数据版本{"不同" if d["input_changed"] else "相同"}；变化设定：'+
            ('、'.join(dict(y='因变量', x='解释变量组合', fixed_effects='固定效应', standard_errors='标准误', entity='主体字段', time='时间字段')[k] for k in d['changed_settings']) or '无')+'。')
        for side in ('left_only_reasons','right_only_reasons'):
            info = d[side]
            for e in info['evidence']:
                paragraphs.append(f'运行 {e["source_run"]["id"]} 按“{describe_sample_rule(e["rule"])}” 排除对应观测 {len(e["keys"])} 条。')
            if info['unresolved_keys']:
                paragraphs.append(f'尚未定位排除原因的观测 {len(info["unresolved_keys"])} 条，不能从数量推断原因。')
    if any(d['input_changed'] for d in c['differences']):
        paragraphs.append('跨数据版本的代码体系与观察单位仍须核实；键的文本交集不自动证明研究对象相同。')
    definitions = [[v['label'], v['definition'] or '未提供', v['unit'] or '未提供',
                    v['transform'] or '未提供', '；'.join(r+':'+f for r,f in v['members'].items())]
                   for v in c['variables']]
    tables.append(dict(title='变量定义', header=['变量','定义','单位','变换','运行字段'], rows=definitions,
                       notes=['定义映射由研究材料与调用者明确声明；未知项保留未知。'], kind='definitions'))
    for i,m in enumerate(c['models']):
        rows = [[f]+[format_number(s.get(k)) for k in ('count','mean','std','min','median','max')]
                for f,s in m['descriptive'].items()]
        tables.append(dict(title=f'模型 ({i+1}) 同样本描述统计',
            header=['字段','N','均值','标准差','最小值','中位数','最大值'], rows=rows,
            notes=['仅对应本模型的实际分析样本，不代表其他列。'], kind='descriptive'))
    paragraphs.append('模型与样本同时变化时，不能把系数变化单独归因于新增控制变量；数值核验不认证因果关系。')
    sources = [f'({i+1}) {m["run"]["id"]} v{m["run"]["version"]}；方案 {m["plan"]["id"]} v{m["plan"]["version"]}；'
               f'输入 SHA-256 {m["input_sha256"]}' for i,m in enumerate(c['models'])]
    return dict(title=c['title'], created_at=c['created_at'], tables=tables, paragraphs=paragraphs, sources=sources)


def render_comparison_markdown(display):
    def esc(v):
        return str(v).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('\n','<br>')
    lines = ['# '+esc(display['title']), '', '生成时间：'+display['created_at'], '']
    for table in display['tables']:
        lines += ['## '+esc(table['title']), '', '| '+' | '.join(map(esc,table['header']))+' |',
                  '| '+' | '.join(['---']*len(table['header']))+' |']
        lines += ['| '+' | '.join(map(esc,row))+' |' for row in table['rows']]
        lines += ['']+table['notes']+['']
    lines += ['## 样本与设定差异','']+display['paragraphs']+['','## 来源','']+display['sources']
    return '\n'.join(lines)+'\n'
