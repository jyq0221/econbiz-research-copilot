import importlib.util
import tempfile
import unittest
from pathlib import Path

from econbiz.state import WorkflowError
from test_execution import HAS_ANALYSIS, study


@unittest.skipUnless(HAS_ANALYSIS, 'analysis extra not installed')
class ResultReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.w = study(Path(self.temp.name))

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.result_report'), 'checked report missing')
        from econbiz.result_report import write_result_report
        return write_result_report

    def test_report_uses_actual_numbers_units_and_judgment(self):
        write = self.api()
        from econbiz.execution import execute_analysis
        result = execute_analysis(self.w, 'run1', 'p1')
        self.assertEqual(result['check_status'], 'passed', result['content'].get('error'))
        report = write(self.w, 'report1', 'run1')
        content = report['content']
        self.assertEqual(content['run_id'], 'run1')
        self.assertEqual(content['evidence'][0]['coefficient'], result['content']['result']['parameters'][0]['coefficient'])
        self.assertEqual(content['evidence'][0]['x_unit'], '指数')
        self.assertEqual(content['judgment'], '非定向探索')
        self.assertEqual(content['sample']['final_rows'], 72)
        md = next(f for f in report['files'] if f['path'].endswith('.md'))
        text = (self.w.root / md['path']).read_text()
        self.assertIn('条件关联', text)
        self.assertIn('95%', text)
        self.assertIn('独立数值', text)
        self.assertIn('72', text)
        self.assertEqual(len(content['evidence']), 2)
        self.w.project.mark('run1', 'completed', 'failed', '故意注入核验失败')
        with self.assertRaises(WorkflowError):
            write(self.w, 'report2', 'run1')
        with self.assertRaises(WorkflowError):
            self.w.project.require_usable('report1')

    def test_cross_zero_interval_explains_uncertainty_and_keeps_row(self):
        self.api()
        from econbiz.result_report import describe_interval
        text = describe_interval(-0.2, 0.8)
        self.assertIn('零', text)
        self.assertIn('负向', text)
        self.assertIn('正向', text)
        self.assertNotIn('没有影响', text)

    def test_html_escapes_research_text(self):
        self.api()
        from econbiz.result_report import render_html
        content = dict(question='<script>alert(1)</script>', judgment='待核对', run_id='run1',
                       plan_id='p1', plan_version=1, scope='条件关联', evidence=[],
                       sample={'final_rows': 2, 'entities': 1, 'control_additional_loss': 0},
                       fixed_effects=['firm'], standard_errors={'method': 'classical'},
                       diagnostics={}, warnings=[], descriptive={}, boundary='条件关联')
        rendered = render_html(content)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)
