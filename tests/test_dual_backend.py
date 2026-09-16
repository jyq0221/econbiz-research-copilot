import builtins
import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from econbiz.state import WorkflowError
from econbiz.workspace import Workspace
from test_execution import HAS_ANALYSIS, study


@unittest.skipUnless(HAS_ANALYSIS, 'analysis dependencies required')
class DualBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.w = study(self.root)

    def api(self):
        from econbiz.execution import execute_analysis
        self.assertIn('backend', inspect.signature(execute_analysis).parameters,
                      'explicit optional backend missing')
        return execute_analysis

    def test_default_python_blocks_all_stata_imports_and_discovery(self):
        execute = self.api()
        from econbiz.execution import ENTRY_SCRIPT
        guard = '''import builtins, shutil, subprocess
_import = builtins.__import__
def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split('.')[-1] in {'stata_runtime', 'stata_engine', 'stata_script', 'pystata', 'stata_setup'}:
        raise AssertionError('worker attempted Stata import')
    return _import(name, globals, locals, fromlist, level)
def no_discovery(*args, **kwargs):
    raise AssertionError('worker attempted executable discovery')
builtins.__import__ = guarded_import
shutil.which = no_discovery
_popen = subprocess.Popen
def guarded_popen(args, *rest, **kwargs):
    if 'stata' in str(args[0]).lower():
        raise AssertionError('worker attempted Stata launch')
    return _popen(args, *rest, **kwargs)
subprocess.Popen = guarded_popen
'''
        original = builtins.__import__
        def reject_stata(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split('.')[-1] in {'stata_runtime', 'stata_engine', 'stata_script', 'pystata', 'stata_setup'}:
                raise AssertionError('Python path loaded Stata')
            return original(name, globals, locals, fromlist, level)
        with patch('builtins.__import__', side_effect=reject_stata), patch('shutil.which', side_effect=AssertionError('discovery called')), patch('econbiz.execution.ENTRY_SCRIPT', guard + ENTRY_SCRIPT):
            run = execute(self.w, 'python-only', 'p1')
        self.assertEqual((run['execution_status'], run['check_status']), ('completed', 'passed'), run['content'].get('error'))
        self.assertEqual(run['content']['backend'], 'python')
        from econbiz.result_report import write_result_report
        report = write_result_report(self.w, 'python-report', 'python-only')
        self.assertEqual(report['content']['backend'], 'python')
        Workspace.open(self.w.root).project.require_usable('python-report')
        package = self.w.root / run['content']['package']
        replay = subprocess.run([sys.executable, '-B', str(package / 'run.py'), '--output', 'guarded-replay'],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(replay.returncode, 0, replay.stderr)

    def test_partial_native_outputs_survive_timeout_and_cancellation(self):
        execute = self.api()
        from econbiz.research_history import has_prior_results
        for run_id, error in [('timed-out', subprocess.TimeoutExpired('worker', 1)),
                              ('cancelled', KeyboardInterrupt())]:
            def interrupted(args, *, cwd, **kwargs):
                native = Path(cwd) / 'outputs/native'
                native.mkdir(parents=True)
                (native / 'coefficients.csv').write_text('0.1,0.2\n')
                raise error
            with patch('econbiz.stata_runtime.probe_stata', return_value={'synthetic': True}), patch('econbiz.processes.run_process', side_effect=interrupted):
                if isinstance(error, KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        execute(self.w, run_id, 'p1', backend='stata')
                    run = self.w.project.artifact(run_id)
                else:
                    run = execute(self.w, run_id, 'p1', backend='stata')
            self.assertEqual((run['execution_status'], run['check_status']), ('failed', 'failed'))
            self.assertTrue(run['content']['result_output_present'])
            self.assertTrue(has_prior_results(self.w.project))
            self.assertTrue(any(f['role'] == 'stata_native_output' for f in run['files']))
            reopened = Workspace.open(self.w.root)
            with self.assertRaises(WorkflowError):
                reopened.project.require_usable(run_id)

    def test_unreadable_native_evidence_still_finalizes_failure(self):
        execute = self.api()
        def failed(args, *, cwd, **kwargs):
            native = Path(cwd) / 'outputs/native'
            native.mkdir(parents=True)
            log = native / 'analysis.log'
            log.write_text('partial native log')
            log.chmod(0)
            self.addCleanup(log.chmod, 0o600)
            return subprocess.CompletedProcess(args, 1, '', 'synthetic failure')
        with patch('econbiz.stata_runtime.probe_stata', return_value={'synthetic': True}), patch('econbiz.processes.run_process', side_effect=failed):
            run = execute(self.w, 'unreadable-native', 'p1', backend='stata')
        self.assertEqual((run['execution_status'], run['check_status']), ('failed', 'failed'))
        self.assertTrue(run['content']['error'])
        self.assertIn('finished_at', run['content'])
        self.assertTrue((self.w.root / run['content']['package'] / 'process.log').is_file())

    def test_malformed_partial_verification_still_finalizes_failure(self):
        execute = self.api()
        def failed(args, *, cwd, **kwargs):
            output = Path(cwd) / 'outputs'
            output.mkdir()
            (output / 'verification.json').write_text('[]')
            return subprocess.CompletedProcess(args, 1, '', 'synthetic failure')
        with patch('econbiz.stata_runtime.probe_stata', return_value={'synthetic': True}), patch('econbiz.processes.run_process', side_effect=failed):
            run = execute(self.w, 'malformed-check', 'p1', backend='stata')
        self.assertEqual((run['execution_status'], run['check_status']), ('failed', 'failed'))
        self.assertIn('finished_at', run['content'])

    @unittest.skipUnless(os.environ.get('ECONBIZ_TEST_STATA'), 'real Stata opt-in')
    def test_previous_native_outputs_cannot_certify_new_attempt(self):
        execute = self.api()
        from econbiz.processes import run_process
        from econbiz.stata_runtime import probe_stata
        runtime = probe_stata(os.environ['ECONBIZ_TEST_STATA'])
        with patch('econbiz.stata_runtime.probe_stata', return_value=runtime):
            first = execute(self.w, 'earlier-native', 'p1', backend='stata')
        self.assertEqual(first['check_status'], 'passed', first['content'].get('error'))
        original_dir = self.w.root / first['content']['package']
        prior_outputs = {p.name: p.read_bytes() for p in (original_dir / 'outputs/native').iterdir()
                         if p.name not in {'input.csv', 'mapping.json', 'analysis.do', 'helpers.mata'}}
        def substitute(args, *, cwd, **kwargs):
            completed = run_process(args, cwd=cwd, **kwargs)
            for name, raw in prior_outputs.items():
                (Path(cwd) / 'outputs/native' / name).write_bytes(raw)
            return completed
        with patch('econbiz.processes.run_process', side_effect=substitute), patch('econbiz.stata_runtime.probe_stata', return_value=runtime):
            second = execute(self.w, 'reused-native', 'p1', backend='stata')
        self.assertEqual((second['execution_status'], second['check_status']), ('failed', 'failed'))
        first_config = json.loads((original_dir / 'execution.json').read_text())
        second_config = json.loads((self.w.root / second['content']['package'] / 'execution.json').read_text())
        self.assertNotEqual(first_config['run_token'], second_config['run_token'])
        self.w.project.require_usable('earlier-native')

    @unittest.skipUnless(os.environ.get('ECONBIZ_TEST_STATA'), 'real Stata opt-in')
    def test_parent_detects_native_change_after_worker_pass(self):
        execute = self.api()
        from econbiz.processes import run_process
        from econbiz.stata_runtime import probe_stata
        runtime = probe_stata(os.environ['ECONBIZ_TEST_STATA'])
        def corrupt(args, *, cwd, **kwargs):
            completed = run_process(args, cwd=cwd, **kwargs)
            path = Path(cwd) / 'outputs/native/core_covariance.csv'
            path.write_text('999,999\n999,999\n')
            return completed
        with patch('econbiz.processes.run_process', side_effect=corrupt), patch('econbiz.stata_runtime.probe_stata', return_value=runtime):
            run = execute(self.w, 'native-tampered', 'p1', backend='stata',
                          stata_executable=os.environ['ECONBIZ_TEST_STATA'])
        self.assertEqual((run['execution_status'], run['check_status']), ('failed', 'failed'))
        self.assertEqual(run['content']['verification']['check_status'], 'failed')
        self.assertIn('原生', run['content']['error'])
        with self.assertRaises(WorkflowError):
            self.w.project.require_usable('native-tampered')

    @unittest.skipUnless(os.environ.get('ECONBIZ_TEST_STATA'), 'real Stata opt-in')
    def test_output_directory_link_cannot_bypass_native_evidence_registration(self):
        execute = self.api()
        from econbiz.research_history import has_prior_results
        from econbiz.processes import run_process
        from econbiz.stata_runtime import probe_stata
        runtime = probe_stata(os.environ['ECONBIZ_TEST_STATA'])
        for relative, run_id in [('outputs', 'linked-output'), ('outputs/native', 'linked-native')]:
            def redirect(args, *, cwd, **kwargs):
                completed = run_process(args, cwd=cwd, **kwargs)
                output = Path(cwd) / relative
                output.rename(output.with_name('redirected'))
                output.symlink_to('redirected', target_is_directory=True)
                return completed
            with patch('econbiz.processes.run_process', side_effect=redirect), patch('econbiz.stata_runtime.probe_stata', return_value=runtime):
                run = execute(self.w, run_id, 'p1', backend='stata')
            self.assertEqual((run['execution_status'], run['check_status']), ('failed', 'failed'))
            with self.assertRaises(WorkflowError):
                self.w.project.require_usable(run_id)
            if relative == 'outputs/native':
                self.assertTrue(run['content']['result_output_present'])
                self.assertIn('result', run['content'])
                self.assertTrue(has_prior_results(self.w.project))

    def test_unknown_backend_and_missing_stata_do_not_create_run(self):
        execute = self.api()
        for backend in ('auto', 'stata', 'unknown'):
            with self.subTest(backend=backend), self.assertRaises(WorkflowError):
                execute(self.w, backend, 'p1', backend=backend, stata_executable='/not-installed/stata')
            self.assertNotIn(backend, self.w.project.snapshot()['artifacts'])

    def test_replication_reuses_approved_plan_and_keeps_original(self):
        execute = self.api()
        first = execute(self.w, 'original', 'p1')
        second = execute(self.w, 'replica', 'p1', backend='python', replication_of='original')
        self.assertEqual(second['content']['replication_of'], {'id': 'original', 'version': first['version']})
        self.assertEqual(second['content']['plan']['purpose'], 'planned')
        self.assertEqual(self.w.project.artifact('p1')['version'], 1)
        self.w.project.require_usable('original')
        with self.assertRaises(WorkflowError):
            execute(self.w, 'wrong-kind', 'p1', replication_of='inventory')

    @unittest.skipUnless(os.environ.get('ECONBIZ_TEST_STATA'), 'real Stata opt-in')
    def test_real_stata_runs_freezes_native_files_replays_and_reopens(self):
        execute = self.api()
        run = execute(self.w, 'stata-run', 'p1', backend='stata',
                      stata_executable=os.environ['ECONBIZ_TEST_STATA'])
        self.assertEqual((run['execution_status'], run['check_status']), ('completed', 'passed'), run['content'].get('error'))
        self.assertEqual(run['content']['backend'], 'stata')
        self.assertTrue(any(f['role'] == 'stata_native_output' for f in run['files']))
        package = self.w.root / run['content']['package']
        replay = subprocess.run([sys.executable, '-B', str(package / 'run.py'), '--output', 'replay-stata'],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        fresh = json.loads((package / 'replay-stata/result.json').read_text())
        self.assertEqual(fresh['parameters'], run['content']['result']['parameters'])
        from econbiz.result_report import write_result_report
        report = write_result_report(self.w, 'stata-report', 'stata-run')
        self.assertEqual(report['content']['backend'], 'stata')
        # Reading a checked Stata result must not require probing its runtime.
        with patch('econbiz.stata_runtime.probe_stata', side_effect=AssertionError('Stata needed to read')):
            Workspace.open(self.w.root).project.require_usable('stata-report')
        replica = execute(self.w, 'python-replica', 'p1', replication_of='stata-run')
        self.assertEqual(replica['check_status'], 'passed')
