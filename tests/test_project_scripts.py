import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from econbiz.plans import register_plan, revise_plan
from econbiz.research_history import has_prior_results
from econbiz.state import Project, WorkflowError
from econbiz.workspace import Workspace
from test_plans import candidate


class ProjectScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.w = Workspace.create(self.root / 'study', 'script-study', '项目脚本验收')
        raw = self.root / 'data.csv'
        raw.write_text('firm,year,x,y\na,2020,1,3\na,2021,2,5\nb,2020,3,7\nb,2021,4,9\n')
        self.w.import_file('raw', raw, role='raw_data', reason='合成数据')
        self.w.audit('inventory', 'raw', entity='firm', time='year', numeric=['x', 'y'])
        self.plan = candidate()
        self.plan.update(model='ols', fixed_effects=[], execution_route='project_script')

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.project_scripts'), 'project script workflow missing')
        from econbiz import project_scripts
        return project_scripts

    def approved(self):
        register_plan(self.w.project, 'p', self.plan, 'inventory')
        self.w.project.approve('p', '测试用户', '按已授权设定自动编程运行', 'decision.md')
        self.w.save()

    def save(self, code=None, *, name='code', **kwargs):
        api = self.api()
        return api.save_project_script(self.w, name, 'p', files={'analysis.py': code or
            "from pathlib import Path\nPath('result.txt').write_text('actual execution')\n"},
            entrypoint='analysis.py', inputs={'input.csv': 'inventory'},
            expected_outputs=['result.txt'], reason='实现已确认方案', **kwargs)

    def test_generic_route_requires_explicit_intent_and_keeps_formal_gate(self):
        self.approved()
        from econbiz.execution_spec import compile_spec
        with self.assertRaises(WorkflowError):
            compile_spec(self.plan, self.w.project.artifact('inventory')['content'])
        self.assertEqual(self.w.project.require_usable('p')['content']['model'], 'ols')

    def test_real_execution_replay_and_no_self_certification(self):
        api = self.api()
        self.approved()
        code = "from pathlib import Path\nPath('result.txt').write_text('coef=2')\nPath('verification.json').write_text('{\"check_status\":\"passed\"}')\n"
        self.save(code)
        run = api.execute_project_script(self.w, 'run', 'code')
        self.assertEqual((run['execution_status'], run['check_status']), ('completed', 'pending'))
        self.assertEqual(run['content']['statistical_verification'], 'not_performed')
        with self.assertRaises(WorkflowError): self.w.project.require_usable('run')
        self.assertTrue(has_prior_results(self.w.project))
        package = self.w.root / run['content']['package']
        replay = subprocess.run([sys.executable] + (['-S'] if sys.flags.no_site else []) + ['-B', str(package / 'run.py'), '--output', 'replay'],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        self.assertEqual((package / 'replay/work/result.txt').read_text(), 'coef=2')
        self.assertIn('尚未独立数值复核', api.write_script_report(self.w, 'run').read_text())
        self.assertEqual(Workspace.open(self.w.root).project.artifact('run')['check_status'], 'pending')
        with self.assertRaises(WorkflowError): api.execute_project_script(self.w, 'run', 'code')

    def test_failure_retry_and_exposure_preserved(self):
        api = self.api()
        self.approved()
        self.save("from pathlib import Path\nPath('result.txt').write_text('partial coef=2')\nraise RuntimeError('technical error')\n")
        failed = api.execute_project_script(self.w, 'fail', 'code')
        self.assertEqual(failed['execution_status'], 'failed')
        self.assertTrue(has_prior_results(self.w.project))
        self.save()
        done = api.execute_project_script(self.w, 'fixed', 'code', retry_of='fail')
        self.assertEqual(done['execution_status'], 'completed')
        self.assertEqual(done['content']['retry_of']['id'], 'fail')
        old = self.w.root / failed['content']['package'] / 'outputs/work/result.txt'
        self.assertEqual(old.read_text(), 'partial coef=2')
        with self.assertRaises(WorkflowError):
            revise_plan(self.w.project, 'p', self.plan, '更改研究设定', 'inventory')

    def test_script_status_cannot_claim_statistical_verification(self):
        api = self.api()
        self.approved()
        self.save()
        api.execute_project_script(self.w, 'done', 'code')
        with self.assertRaises(WorkflowError):
            self.w.project.mark('done', 'completed', 'passed', '脚本声称通过')
        with self.assertRaises(WorkflowError): self.w.project.require_usable('done')
        self.assertEqual(self.w.project.require_executed_script('done')['check_status'], 'pending')
        # Older saved states can already contain the invalid outer label.
        snapshot = self.w.project.snapshot()
        snapshot['artifacts']['done']['check_status'] = 'passed'
        old = Project(snapshot, base_dir=self.w.root)
        with self.assertRaises(WorkflowError): old.require_usable('done')

    def test_failed_script_cannot_be_relabelled_as_completed(self):
        api = self.api()
        self.approved()
        self.save("from pathlib import Path\nPath('result.txt').write_bytes(Path('input.csv').read_bytes())\nraise RuntimeError('partial output')\n")
        run = api.execute_project_script(self.w, 'failed', 'code')
        self.assertEqual(run['execution_status'], 'failed')
        with self.assertRaises(WorkflowError):
            self.w.project.mark('failed', 'completed', 'pending', '已有部分输出')
        with self.assertRaises(WorkflowError): self.w.project.require_executed_script('failed')
        with self.assertRaises(WorkflowError):
            api.import_script_output(self.w, 'partial', 'failed', 'result.txt', reason='尝试消费失败输出')
        snapshot = self.w.project.snapshot()
        snapshot['artifacts']['failed'].update(execution_status='completed', check_status='pending')
        old = Project(snapshot, base_dir=self.w.root)
        with self.assertRaises(WorkflowError): old.require_executed_script('failed')

    def test_missing_output_timeout_and_symlink_are_failures(self):
        api = self.api()
        self.approved()
        for name, code, timeout in [
            ('missing', 'pass\n', 5),
            ('timeout', 'import time\ntime.sleep(5)\n', 0.1),
            ('link', "from pathlib import Path\nPath('result.txt').symlink_to('input.csv')\n", 5),
            ('overwrite', "from pathlib import Path\nPath('input.csv').write_text('changed')\nPath('result.txt').write_text('x')\n", 5),
        ]:
            with self.subTest(name=name):
                self.save(code, name=name)
                run = api.execute_project_script(self.w, name+'-run', name, timeout=timeout)
                self.assertEqual(run['execution_status'], 'failed')
                self.assertEqual(run['check_status'], 'failed')
                self.assertTrue((self.w.root / run['content']['package'] / 'process.log').exists())

    def test_inputs_paths_and_stale_scripts_rejected_before_execution(self):
        api = self.api()
        self.approved()
        for entry in ('../evil.py', '/evil.py', '_econbiz_state.py'):
            with self.assertRaises(WorkflowError):
                api.save_project_script(self.w, 'bad', 'p', files={entry: 'pass'}, entrypoint=entry,
                    inputs={'input.csv': 'inventory'}, expected_outputs=['result.txt'], reason='test')
        self.save()
        self.w.project.revise('inventory', self.w.project.artifact('inventory')['content'], '更新输入')
        with self.assertRaises(WorkflowError): api.execute_project_script(self.w, 'stale', 'code')

    def test_output_import_preserves_provenance_and_invalidation(self):
        api = self.api()
        self.approved()
        self.save("from pathlib import Path\nPath('result.txt').write_bytes(Path('input.csv').read_bytes())\n")
        api.execute_project_script(self.w, 'run', 'code')
        source = api.import_script_output(self.w, 'processed', 'run', 'result.txt', reason='处理后字节')
        self.assertEqual(source['content']['script_run']['id'], 'run')
        self.w.audit('processed-inventory', 'processed', entity='firm', time='year', numeric=['x', 'y'])
        self.w.project.mark('run', 'failed', 'failed', '实际执行证据被否定')
        with self.assertRaises(WorkflowError): self.w.project.require_usable('processed-inventory')

    def test_custom_script_requires_explicit_plan_route(self):
        self.api()
        self.plan.update(model='linear_fe', fixed_effects=['firm'], execution_route='builtin')
        self.approved()
        with self.assertRaises(WorkflowError): self.save()

    def test_timeout_retains_printed_result_and_original_failure(self):
        api = self.api()
        self.approved()
        self.save("import time\nprint('coef=2', flush=True)\ntime.sleep(10)\n")
        run = api.execute_project_script(self.w, 'partial', 'code', timeout=0.8)
        self.assertEqual(run['execution_status'], 'failed')
        self.assertIn('coef=2', (self.w.root / run['content']['package'] / 'outputs/child.log').read_text())

    def test_invalid_output_does_not_hide_other_evidence(self):
        api = self.api()
        self.approved()
        self.save("from pathlib import Path\nPath('aaa').symlink_to('input.csv')\nPath('result.txt').write_text('coef=2')\n")
        run = api.execute_project_script(self.w, 'bad-link', 'code')
        self.assertEqual(run['execution_status'], 'failed')
        refs = [ref for ref in run['files'] if ref['path'].endswith('/result.txt')]
        self.assertEqual(len(refs), 1)
        (self.w.root / refs[0]['path']).write_text('changed')
        with self.assertRaises(WorkflowError): api.write_script_report(self.w, 'bad-link')

    def test_host_interruption_keeps_exposure_and_allows_retry(self):
        api = self.api()
        self.approved()
        self.save()
        class HostDied(BaseException): pass
        with patch('econbiz.project_scripts.run_process', side_effect=HostDied):
            with self.assertRaises(HostDied): api.execute_project_script(self.w, 'interrupted', 'code')
        self.w = Workspace.open(self.w.root)
        self.assertTrue(has_prior_results(self.w.project))
        old = self.w.project.artifact('interrupted')
        self.assertEqual(old['execution_status'], 'failed')
        self.assertTrue(old['content']['finished_at'])
        run = api.execute_project_script(self.w, 'resumed', 'code', retry_of='interrupted')
        self.assertEqual(run['execution_status'], 'completed')

    def test_preparation_only_does_not_become_result_exposure(self):
        api = self.api()
        recipe = dict(schema_version=1, keys=['firm', 'year'], steps=[
            dict(op='ln', source='x', target='ln_x', invalid='error')])
        self.plan['preprocessing'] = recipe
        self.approved()
        api.save_preparation_script(self.w, 'prep', 'p', recipe=recipe,
                                    inventory_id='inventory', reason='已授权取 ln')
        run = api.execute_project_script(self.w, 'prepared', 'prep')
        self.assertEqual(run['execution_status'], 'completed')
        self.assertFalse(has_prior_results(self.w.project))

    def test_cancel_is_saved_and_report_checks_current_dependencies(self):
        api = self.api()
        self.approved()
        self.save()
        with patch('econbiz.project_scripts.run_process', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): api.execute_project_script(self.w, 'cancelled', 'code')
        self.assertEqual(self.w.project.artifact('cancelled')['execution_status'], 'failed')
        api.execute_project_script(self.w, 'done', 'code')
        ref = self.w.project.artifact('raw')['files'][0]
        (self.w.root / ref['path']).write_text('changed')
        self.assertIn('已失效', api.write_script_report(self.w, 'done').read_text())

    def test_processed_source_can_restore_current_execution_provenance(self):
        api = self.api()
        self.approved()
        self.save("from pathlib import Path\nPath('result.txt').write_bytes(Path('input.csv').read_bytes())\n")
        api.execute_project_script(self.w, 'run', 'code')
        for i in range(2):
            api.import_script_output(self.w, 'processed', 'run', 'result.txt', reason='同一运行版本材料')
        from econbiz.checkpoints import restore_record
        restored = restore_record(self.w, 'processed', 1, '恢复已保存的处理数据版本')
        self.assertEqual(restored['version'], 3)
        self.assertEqual(restored['dependencies']['run'], self.w.project.artifact('run')['version'])
        self.w.project.require_usable('processed')

    def test_python_script_receives_only_its_own_entry_argument(self):
        api = self.api()
        self.approved()
        self.save("import argparse\nfrom pathlib import Path\nargparse.ArgumentParser().parse_args()\nPath('result.txt').write_text('parsed')\n")
        run = api.execute_project_script(self.w, 'argparse', 'code')
        self.assertEqual(run['execution_status'], 'completed', run['content']['error'])

    def test_python_does_not_import_stata_runtime(self):
        api = self.api()
        self.approved()
        self.save()
        import builtins
        original = builtins.__import__
        def guarded(name, *args, **kwargs):
            if 'stata_runtime' in name: raise AssertionError('Python must not discover Stata')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=guarded):
            run = api.execute_project_script(self.w, 'only-python', 'code')
        self.assertEqual(run['execution_status'], 'completed')


if __name__ == '__main__':
    unittest.main()
