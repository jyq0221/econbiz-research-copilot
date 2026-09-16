"""Real pipeline acceptance on synthetic data; no personal research project."""

import copy
import csv
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from econbiz.plans import register_plan
from econbiz.state import WorkflowError
from econbiz.workspace import Workspace
from test_execution import study, HAS_ANALYSIS


@unittest.skipUnless(HAS_ANALYSIS, 'analysis extra required')
class AgentAnalysisWorkflowTests(unittest.TestCase):
    def test_preparation_formal_regression_and_custom_method_keep_distinct_checks(self):
        from econbiz.project_scripts import (save_preparation_script, execute_project_script,
            import_script_output, save_project_script, write_script_report)
        self.assertIsNotNone(importlib.util.find_spec('econbiz.preprocessing_check'))
        from econbiz.preprocessing_check import verify_preparation
        from econbiz.execution import execute_analysis
        from econbiz.result_report import write_result_report
        import numpy as np
        with tempfile.TemporaryDirectory() as temporary:
            w = study(Path(temporary))
            raw = w.project.read_inventory_bytes('inventory')
            recipe = dict(schema_version=1, keys=['firm', 'year'], steps=[
                dict(op='winsor', source='x', target='x_w', lower=.01, upper=.99, by=['year']),
                dict(op='log1p', source='x_w', target='ln1p_x_w', invalid='error')])
            prep_plan = copy.deepcopy(w.project.artifact('p1')['content'])
            prep_plan.update(execution_route='project_script', preprocessing=recipe)
            register_plan(w.project, 'prep-plan', prep_plan, 'inventory')
            w.project.approve('prep-plan', '合成测试用户', '已授权缩尾及 ln(1+x)，自动运行', 'synthetic-prep.md')
            w.save()
            save_preparation_script(w, 'preparation', 'prep-plan', recipe=recipe,
                                     inventory_id='inventory', reason='落实已授权处理')
            preparation = execute_project_script(w, 'prep-run', 'preparation')
            self.assertEqual(preparation['execution_status'], 'completed', preparation['content']['error'])
            actual = (w.root / preparation['content']['package'] / 'outputs/work/processed.csv').read_bytes()
            check = verify_preparation(raw, recipe, actual)
            self.assertEqual(check['check_status'], 'passed', check)
            import_script_output(w, 'prepared-data', 'prep-run', 'processed.csv', reason='处理字节登记')
            w.audit('prepared-inventory', 'prepared-data', entity='firm', time='year', numeric=['x_w', 'ln1p_x_w', 'y', 'c'])
            model = copy.deepcopy(w.project.artifact('p1')['content'])
            model['mapping']['x']['field'] = 'ln1p_x_w'
            model['mapping']['x']['definition'] = '按年缩尾 x，再按已确认口径取 ln(1+x)'
            register_plan(w.project, 'fe-plan', model, 'prepared-inventory')
            w.project.approve('fe-plan', '合成测试用户', '沿用已授权处理后的固定效应设定', 'synthetic-fe.md')
            custom = copy.deepcopy(model)
            custom.update(model='ols', fixed_effects=[], execution_route='project_script')
            register_plan(w.project, 'ols-plan', custom, 'prepared-inventory')
            w.project.approve('ols-plan', '合成测试用户', '另行预定的 OLS 关联比较', 'synthetic-ols.md')
            w.save()
            formal = execute_analysis(w, 'formal-fe', 'fe-plan')
            self.assertEqual((formal['execution_status'], formal['check_status']), ('completed', 'passed'))
            report = write_result_report(w, 'formal-report', 'formal-fe')
            self.assertTrue(report['files'])
            # This method is not in the fixed estimator registry. The Agent's
            # actual script still runs; the test supplies a separate reference.
            code = '''import pandas as pd
import statsmodels.api as sm
frame = pd.read_csv('input.csv', dtype={'firm': str})
fit = sm.OLS(frame.y, sm.add_constant(frame[['ln1p_x_w', 'c']])).fit()
fit.params.to_csv('coefficients.csv', header=['coefficient'])
frame[['firm','year']].to_csv('sample.csv', index=False)
'''
            save_project_script(w, 'ols-code', 'ols-plan', files={'analysis.py': code}, entrypoint='analysis.py',
                inputs={'input.csv': 'prepared-inventory'}, expected_outputs=['coefficients.csv', 'sample.csv'],
                reason='实现预定 OLS 关联比较')
            custom_run = execute_project_script(w, 'ols-run', 'ols-code')
            self.assertEqual((custom_run['execution_status'], custom_run['check_status']), ('completed', 'pending'))
            directory = w.root / custom_run['content']['package'] / 'outputs/work'
            with (directory / 'coefficients.csv').open() as f:
                coefficients = [float(row['coefficient']) for row in csv.DictReader(f)]
            rows = list(csv.DictReader(io.StringIO(actual.decode())))
            matrix = np.array([[1, float(row['ln1p_x_w']), float(row['c'])] for row in rows])
            outcome = np.array([float(row['y']) for row in rows])
            reference = np.linalg.lstsq(matrix, outcome, rcond=None)[0]
            np.testing.assert_allclose(coefficients, reference, rtol=1e-10, atol=1e-10)
            with (directory / 'sample.csv').open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), len(rows))
            self.assertIn('尚未独立数值复核', write_script_report(w, 'ols-run').read_text())
            reopened = Workspace.open(w.root)
            self.assertEqual(reopened.project.require_usable('formal-fe')['check_status'], 'passed')
            with self.assertRaises(WorkflowError): reopened.project.require_usable('ols-run')
            reopened.project.mark('prep-run', 'failed', 'failed', '处理运行证据失效')
            with self.assertRaises(WorkflowError): reopened.project.require_usable('formal-fe')


if __name__ == '__main__':
    unittest.main()
