import unittest

from econbiz.reports import render_comparison


class ReportTests(unittest.TestCase):
    def test_student_report_escapes_text_and_shows_scope(self):
        r = dict(direction='<script>alert(1)</script>', goal='undecided', plans=[],
                 facts={'total_rows': 4}, questions=['核实字段 <x>'], limitations=['尚无估计'],
                 recommendation='先核实', generated_at='2026-09-15', inventory_version=1,
                 comparison_id='demo-comparison')
        html = render_comparison(r)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertIn('生成时的快照', html)
        self.assertIn('暂时没有', html)
        self.assertNotIn('https://', html)

    def test_exploratory_label_and_reason_visible_and_escaped(self):
        from test_plans import candidate
        plan = candidate()
        plan.update(purpose='exploratory', exploration_reason='看到结果后提出 <新问题>')
        r = dict(direction='研究方向', goal='association', plans=[plan], facts={}, questions=[],
                 limitations=[], recommendation='继续讨论', generated_at='2026-09-15', inventory_version=1)
        html = render_comparison(r)
        self.assertIn('结果之后的探索', html)
        self.assertIn('看到结果后提出 &lt;新问题&gt;', html)
