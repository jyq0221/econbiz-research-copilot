"""Self-contained, escaped HTML for reading and discussing candidate drafts."""

from html import escape


GOAL_LABELS = {'description': '描述现象', 'association': '了解条件关联',
               'causal': '判断因果', 'prediction': '预测未来', 'undecided': '尚未确定'}


def render_comparison(comparison):
    def e(value):
        return escape(str(value), quote=True)

    def bullets(items):
        return '<ul>' + ''.join(f'<li>{e(item)}</li>' for item in items) + '</ul>'

    facts = comparison['facts']
    cards = []
    for key, label in [('total_rows', '原始企业年度观测'), ('focus_rows', '关注指标可用观测'),
                       ('pair_rows', '两指标共同可用观测')]:
        if key in facts:
            cards.append(f'<div class="fact"><strong>{e(facts[key])}</strong><span>{label}</span></div>')
    plans = comparison['plans']
    plan_cards = []
    for i, plan in enumerate(plans, 1):
        fields = '；'.join(f'{m.get("concept", role)} → {m["field"]}（{m["unit"]}）'
                           for role, m in plan['mapping'].items())
        details = [('对应数据', fields), ('怎样比较', plan['comparison']), ('拟用样本', plan['sample']),
                   ('为什么考虑', plan['priority_reason']), ('仍需核实', plan['conditions']),
                   ('能说明到哪里', plan['boundary'])]
        detail_html = ''.join(f'<dt>{e(label)}</dt><dd>{e(value)}</dd>' for label, value in details)
        provenance = '<p class="muted">结果之前记录的讨论草案</p>'
        if plan.get('purpose') == 'exploratory':
            provenance = f'<p class="relation"><strong>结果之后的探索</strong><br>提出原因：{e(plan["exploration_reason"])}</p>'
        plan_cards.append(f'<article class="plan"><div class="eyebrow">路线 {i} · {e(GOAL_LABELS[plan["goal"]])}</div>'
                          f'<h3>{e(plan["question"])}</h3><span class="tag">讨论草案 · 尚未确认</span>'
                          f'{provenance}<dl>{detail_html}</dl><p class="relation">{e(plan["relation"])}</p></article>')
    if plans:
        candidate_html = '<div class="plans">' + ''.join(plan_cards) + '</div>'
    else:
        candidate_html = '<div class="empty"><h3>暂时没有可以准备的方案</h3><p>先解决下面的信息缺口，原研究方向会保留。</p></div>'
    questions = comparison['questions'] or ['请核对描述方案的样本规则和指标含义，再决定是否继续。']
    phase = '可先讨论的路线' if plans else '先把问题说清楚'
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>研究路线对照 · 经管实证研究助手</title>
<style>
:root {{ color-scheme: light; --ink:#183734; --muted:#556b66; --line:#d6e0da; --paper:#f5f4ee; --accent:#1a685b; }}
* {{ box-sizing:border-box; }} body {{ margin:0;background:var(--paper);color:var(--ink);font:16px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; }}
main {{ max-width:1120px;margin:auto;padding:44px 32px 64px; }} header {{ border-top:4px solid var(--accent);padding-top:22px; }}
.eyebrow {{ font-size:13px;color:var(--accent);font-weight:650;letter-spacing:.08em; }} h1 {{ font-size:38px;line-height:1.3;margin:12px 0 16px; }}
h2 {{ font-size:24px;margin:32px 0 16px; }} h3 {{ font-size:21px;line-height:1.55;margin:10px 0 16px; }} p {{ margin:10px 0; }}
.direction {{ font-size:19px;max-width:850px;overflow-wrap:anywhere; }} .muted,footer {{ color:var(--muted);font-size:14px; }}
.next {{ border-left:4px solid var(--accent);background:#e8eee7;padding:18px 24px;margin:26px 0; }}
.facts {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px; }}
.fact {{ background:white;border:1px solid var(--line);padding:18px 22px; }} .fact strong {{ display:block;font-size:32px;line-height:1.4; }} .fact span {{ font-size:14px;color:var(--muted); }}
.plans {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:22px;align-items:start; }}
.plan {{ background:white;padding:26px;border:1px solid var(--line);border-radius:4px;overflow-wrap:anywhere; }}
.tag {{ display:inline-block;font-size:12px;border:1px solid #d1b873;background:#fbf5e4;padding:2px 9px;color:#66511e; }}
dl {{ margin:22px 0 0; }} dt {{ font-weight:650;font-size:14px;margin-top:17px; }} dd {{ margin:5px 0 0;color:#3e5550;font-size:15px; }}
.relation {{ border-top:1px solid var(--line);padding-top:14px;margin-top:22px;font-size:14px;color:var(--muted); }}
.empty {{ border:1px dashed var(--line);padding:18px 24px; }} .questions {{ background:white;border:1px solid var(--line);padding:4px 22px 12px; }}
li {{ margin:10px 0;overflow-wrap:anywhere; }} footer {{ margin-top:32px;border-top:1px solid var(--line);padding-top:18px;overflow-wrap:anywhere; }}
@media(max-width:600px) {{ main {{ padding:24px 18px; }} h1 {{ font-size:30px; }} .plans {{ grid-template-columns:1fr; }} .plan {{ padding:20px; }} }}
@media print {{ body {{ background:white; }} main {{ padding:0; }} .plans {{ display:block; }} .plan {{ break-inside:avoid;margin-bottom:18px; }} }}
</style></head><body><main>
<header><div class="eyebrow">经管实证研究助手 / 研究准备</div><h1>{phase}</h1>
<p class="direction">{e(comparison['direction'])}</p><p class="muted">当前目标：{e(GOAL_LABELS[comparison['goal']])} · 共 {len(plans)} 条讨论路线</p></header>
<section class="next"><strong>建议先做什么</strong><p>{e(comparison['recommendation'])}</p></section>
<section aria-label="数据覆盖"><h2>先看看手上的数据</h2><div class="facts">{''.join(cards)}</div>
<p class="muted">这里是数据覆盖计数，还不是回归结果。缺失标记保留，不自动填零。</p></section>
<section><h2>每条路线回答什么问题</h2>{candidate_html}</section>
<section><h2>接下来一起核实</h2><div class="questions">{bullets(questions)}</div></section>
<section><h2>这份报告的范围</h2>{bullets(comparison['limitations'])}</section>
<footer><p>这是生成时的快照；修改数据或字段含义后，请重新生成，并从项目状态核实是否仍有效。</p>
<p>生成时间：{e(comparison['generated_at'])} · 数据盘点第 {e(comparison['inventory_version'])} 版 · 记录：{e(comparison.get('comparison_id', '未保存'))}</p>
<p>草案未代表研究者确认，报告不包含已执行的统计估计。</p></footer>
</main></body></html>'''
