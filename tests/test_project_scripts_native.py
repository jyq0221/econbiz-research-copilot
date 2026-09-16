import os
import unittest
from pathlib import Path

import test_project_scripts as fixtures


STATA = os.environ.get('ECONBIZ_STATA_EXECUTABLE')


@unittest.skipUnless(STATA and Path(STATA).is_file(), 'native Stata explicitly enabled only')
class NativeProjectScriptTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.ProjectScriptTests(methodName='runTest')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.approved()
        self.w, self.api = self.case.w, self.case.api()

    def save(self, code, *, files=None):
        self.api.save_project_script(self.w, 'native', 'p', files=dict({'analysis.do': code}, **(files or {})),
            entrypoint='analysis.do', inputs={'input.csv': 'inventory'}, expected_outputs=['result.csv'],
            reason='实际原生脚本测试', backend='stata')

    def test_real_native_vendored_command_and_completion_marker(self):
        helper = 'program define ebcoef\nregress y x\nend\n'
        code = 'clear\nimport delimited "input.csv", clear\nebcoef\nexport delimited using "result.csv", replace\n'
        self.save(code, files={'ebcoef.ado': helper})
        run = self.api.execute_project_script(self.w, 'native-ok', 'native', stata_executable=STATA)
        self.assertEqual(run['execution_status'], 'completed', run['content']['error'])
        self.assertEqual(run['check_status'], 'pending')
        self.assertTrue(any(ref['path'].endswith('/_econbiz_run.log') for ref in run['files']))

    def test_native_error_after_output_is_failure(self):
        code = 'clear\nimport delimited "input.csv", clear\nexport delimited using "result.csv", replace\nunknown_command_for_test\n'
        self.save(code)
        run = self.api.execute_project_script(self.w, 'native-fail', 'native', stata_executable=STATA)
        self.assertEqual(run['execution_status'], 'failed')
        self.assertTrue(any(ref['path'].endswith('/result.csv') for ref in run['files']))

    def test_generated_preparation_returns_to_wrapper(self):
        from econbiz.plans import revise_plan
        recipe = dict(schema_version=1, keys=['firm', 'year'], steps=[
            dict(op='ln', source='x', target='ln_x', invalid='error')])
        plan = self.case.plan.copy()
        plan['preprocessing'] = recipe
        revise_plan(self.w.project, 'p', plan, '已授权处理规则', 'inventory')
        self.w.project.approve('p', '测试', '同一授权的实际规则', 'decision2.md')
        self.w.save()
        self.api.save_preparation_script(self.w, 'prep', 'p', recipe=recipe,
            inventory_id='inventory', reason='原生数据处理', backend='stata')
        run = self.api.execute_project_script(self.w, 'prepared', 'prep', stata_executable=STATA)
        self.assertEqual(run['execution_status'], 'completed', run['content']['error'])
