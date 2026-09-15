import copy
import csv
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
from econbiz.state import WorkflowError
from econbiz.workspace import Workspace
from test_execution_spec import executable_plan

HAS_ANALYSIS = all(importlib.util.find_spec(name) for name in ['numpy', 'scipy', 'pandas', 'linearmodels'])


def is_worker(args):
    return bool(args) and any(isinstance(part, str) and part.endswith('/run.py') for part in args[0])


def study(root):
    w = Workspace.create(root / 'study', 'study', '合成面板运行验收')
    source = root / 'panel.csv'
    with source.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['firm', 'year', 'x', 'y', 'c'])
        for i in range(1, 13):
            for t in range(6):
                x = (i * 7 + t * t + 3 * i * t) % 23 / 10
                c = (i * i + 5 * t + i * t * t) % 17 / 10
                error = ((i * 13 + t * 7 + i * t) % 19 - 9) / 13
                writer.writerow([f'{i:06d}', 2018 + t, x, 1.2 * x + 0.3 * c + i / 3 + t / 7 + error, c])
    w.import_file('raw', source, role='raw_data', reason='合成测试输入')
    w.audit('inventory', 'raw', entity='firm', time='year', numeric=['x', 'y', 'c'])
    plan = executable_plan()
    plan['controls'] = ['c']
    register_plan(w.project, 'p1', plan, 'inventory')
    w.project.approve('p1', '合成测试', '测试中明确确认规则', 'synthetic-decision.md')
    w.save()
    return w


@unittest.skipUnless(HAS_ANALYSIS, 'analysis extra not installed')
class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.w = study(self.root)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.execution'), 'formal execution missing')
        from econbiz.execution import execute_analysis
        return execute_analysis

    def test_runs_real_estimation_and_replays_from_frozen_package(self):
        execute = self.api()
        result = execute(self.w, 'run1', 'p1')
        self.assertEqual((result['execution_status'], result['check_status']), ('completed', 'passed'))
        self.assertEqual(result['content']['result']['nobs'], 72)
        self.assertEqual(result['content']['verification']['check_status'], 'passed')
        package = self.w.root / result['content']['package']
        for filename in ['input.csv', 'plan.json', 'spec.json', 'environment.json', 'manifest.json', 'run.py',
                         'outputs/result.json', 'outputs/sample.json', 'outputs/verification.json', 'process.log']:
            self.assertTrue((package / filename).is_file(), filename)
        replay = subprocess.run([sys.executable, '-B', str(package / 'run.py'), '--output', 'replay-001'],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        first = json.loads((package / 'outputs/result.json').read_text())
        second = json.loads((package / 'replay-001/result.json').read_text())
        self.assertEqual(first['parameters'], second['parameters'])
        self.assertEqual(Workspace.open(self.w.root).project.require_usable('run1')['check_status'], 'passed')
        with self.assertRaises(WorkflowError):
            execute(self.w, 'run1', 'p1')

    def test_unapproved_old_plan_and_changed_input_do_not_run(self):
        execute = self.api()
        plan = executable_plan()
        register_plan(self.w.project, 'pending', plan, 'inventory')
        with self.assertRaises(WorkflowError): execute(self.w, 'unapproved', 'pending')
        old = executable_plan()
        old.pop('execution')
        register_plan(self.w.project, 'old', old, 'inventory')
        self.w.project.approve('old', '测试', '旧方案', 'old.md')
        with self.assertRaises(WorkflowError): execute(self.w, 'old-run', 'old')
        ref = self.w.project.artifact('raw')['files'][0]
        (self.w.root / ref['path']).write_text('changed')
        with self.assertRaises(WorkflowError): execute(self.w, 'changed', 'p1')
        self.assertFalse((self.w.path('research_runs') / 'changed').exists())

    def test_absorbed_model_failure_is_preserved_and_unusable(self):
        execute = self.api()
        ref = self.w.project.artifact('raw')['files'][0]
        with (self.w.root / ref['path']).open() as f:
            rows = list(csv.DictReader(f))
        source = self.root / 'absorbed.csv'
        with source.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['firm', 'year', 'x', 'y', 'c'])
            writer.writeheader()
            for r in rows:
                r['x'] = str(int(r['firm']))
                writer.writerow(r)
        self.w.import_file('absorbed', source, role='raw_data', reason='完全吸收错误')
        self.w.audit('inv2', 'absorbed', entity='firm', time='year', numeric=['x', 'y'])
        register_plan(self.w.project, 'p2', executable_plan(), 'inv2')
        self.w.project.approve('p2', '测试', '测试吸收', 'p2.md')
        failed = execute(self.w, 'bad', 'p2')
        self.assertEqual(failed['execution_status'], 'failed')
        self.assertTrue((self.w.root / failed['content']['package'] / 'process.log').is_file())
        with self.assertRaises(WorkflowError): self.w.project.require_usable('bad')

    def test_result_tamper_and_plan_revision_invalidate_consumption(self):
        execute = self.api()
        result = execute(self.w, 'run1', 'p1')
        path = self.w.root / result['content']['package'] / 'outputs/result.json'
        raw = path.read_bytes()
        path.write_text('{}')
        with self.assertRaises(WorkflowError): self.w.project.require_usable('run1')
        path.write_bytes(raw)
        p = copy.deepcopy(self.w.project.artifact('p1')['content'])
        p['exploration_reason'] = '看到完整结果后核对替代样本口径'
        p['execution']['sample_filters'] = [{'field': 'year', 'op': 'ge', 'value': 2020}]
        revise_plan(self.w.project, 'p1', p, '修改样本', 'inventory')
        self.assertEqual(self.w.project.artifact('run1')['execution_status'], 'stale')
        with self.assertRaises(WorkflowError): execute(self.w, 'run2', 'p1')
        self.w.project.approve('p1', '测试', '确认新样本', 'revision.md')
        self.w.save()
        new = execute(self.w, 'run2', 'p1')
        self.assertEqual(new['content']['result']['nobs'], 48)
        self.assertEqual(new['content']['plan']['purpose'], 'exploratory')

    def test_declared_output_changes_cannot_pass_validation(self):
        self.api()
        from econbiz.execution import validate_outputs
        model = {'model': 'linear_fe', 'x': ['x']}
        data = dict(result={'actual_spec': {'model': 'descriptive'}, 'sample_keys': [['1', '2020']]},
                    sample={'sample_keys': [['1', '2020']]}, verification={'check_status': 'passed'})
        with self.assertRaises(WorkflowError):
            validate_outputs(data, {'estimation': model})

    def test_interrupted_or_timeout_attempt_cannot_be_consumed(self):
        execute = self.api()
        original_run = subprocess.run
        def timeout_worker(*args, **kwargs):
            if is_worker(args):
                raise subprocess.TimeoutExpired('worker', 1)
            return original_run(*args, **kwargs)
        with patch('econbiz.execution.subprocess.run', side_effect=timeout_worker):
            result = execute(self.w, 'timeout', 'p1', timeout=1)
        self.assertEqual(result['execution_status'], 'failed')
        self.assertIn('timeout', result['content']['error'].lower())
        self.assertEqual(Workspace.open(self.w.root).project.artifact('timeout')['execution_status'], 'failed')

    def test_source_change_during_execution_keeps_final_failure_evidence(self):
        execute = self.api()
        original_run = subprocess.run
        source = self.w.root / self.w.project.artifact('raw')['files'][0]['path']
        def changed_after_run(*args, **kwargs):
            completed = original_run(*args, **kwargs)
            if is_worker(args):
                source.write_text('externally changed after frozen computation')
            return completed
        with patch('econbiz.execution.subprocess.run', side_effect=changed_after_run):
            run = execute(self.w, 'changed-during', 'p1')
        self.assertEqual((run['execution_status'], run['check_status']), ('failed', 'failed'))
        self.assertIn('dependency_error', run['content'])
        self.assertTrue((self.w.root / run['content']['package'] / 'process.log').is_file())
        self.assertTrue(any(f['role'] == 'analysis_output' for f in run['files']))
        reopened = Workspace.open(self.w.root).project.artifact('changed-during')
        self.assertEqual(reopened['execution_status'], 'failed')
        self.assertTrue(reopened['has_completed_result'])

    def test_numeric_tamper_after_worker_is_not_certified(self):
        execute = self.api()
        original_run = subprocess.run
        def tamper_after_run(*args, **kwargs):
            completed = original_run(*args, **kwargs)
            if not is_worker(args):
                return completed
            path = Path(kwargs['cwd']) / 'outputs/result.json'
            value = json.loads(path.read_text())
            value['parameters'][0]['coefficient'] += 100
            path.write_text(json.dumps(value))
            return completed
        with patch('econbiz.execution.subprocess.run', side_effect=tamper_after_run):
            run = execute(self.w, 'tampered', 'p1')
        self.assertEqual(run['check_status'], 'failed')
        with self.assertRaises(WorkflowError): self.w.project.require_usable('tampered')

    def test_timeout_after_result_preserves_exposure_and_partial_output(self):
        execute = self.api()
        from econbiz.research_history import has_prior_results
        original_run = subprocess.run
        def timeout_after_result(*args, **kwargs):
            completed = original_run(*args, **kwargs)
            if is_worker(args):
                raise subprocess.TimeoutExpired('worker after estimation', 1)
            return completed
        with patch('econbiz.execution.subprocess.run', side_effect=timeout_after_result):
            run = execute(self.w, 'timeout-output', 'p1')
        self.assertEqual(run['execution_status'], 'failed')
        self.assertTrue(has_prior_results(self.w.project))
        self.assertIn('result', run['content'])
        self.assertTrue(run['content']['result_output_present'])

    def test_plan_revision_during_execution_finalizes_stale_attempt_as_failed(self):
        execute = self.api()
        original_run = subprocess.run
        def revise_after_run(*args, **kwargs):
            completed = original_run(*args, **kwargs)
            if not is_worker(args):
                return completed
            p = copy.deepcopy(self.w.project.artifact('p1')['content'])
            p['sample'] = '新版本，仅用于上游失效测试'
            revise_plan(self.w.project, 'p1', p, '运行期间修改上游', 'inventory')
            self.w.save()
            return completed
        with patch('econbiz.execution.subprocess.run', side_effect=revise_after_run):
            run = execute(self.w, 'stale-during', 'p1')
        self.assertEqual(run['execution_status'], 'failed')
        self.assertEqual(run['dependencies']['p1'], 1)
        self.assertTrue((self.w.root / run['content']['package'] / 'process.log').is_file())
        with self.assertRaises(WorkflowError):
            self.w.project.finish_result('stale-during', {}, [], 'completed', 'passed', '不得二次收尾')

    def test_parent_reference_capacity_failure_is_saved(self):
        execute = self.api()
        with patch('econbiz.numerical_check.lsmr', side_effect=MemoryError('reference capacity exhausted')):
            run = execute(self.w, 'reference-capacity', 'p1')
        self.assertEqual(run['check_status'], 'failed')
        self.assertTrue((self.w.root / run['content']['package'] / 'process.log').is_file())
        self.assertTrue(run['content']['result_output_present'])
        with self.assertRaises(WorkflowError): self.w.project.require_usable('reference-capacity')

    def test_candidate_guidance_connects_to_description_and_association(self):
        execute = self.api()
        from econbiz.candidates import build_candidates
        from econbiz.result_report import write_result_report
        from test_candidates import brief
        candidates = build_candidates(self.w.project, 'inventory', brief())
        self.assertEqual([p['model'] for p in candidates['plans']], ['descriptive', 'linear_fe'])
        for index, plan in enumerate(candidates['plans']):
            plan['execution'] = executable_plan()['execution']
            plan['standard_errors'] = {'method': 'classical', 'rationale': '合成验收的已知同方差设定'}
            register_plan(self.w.project, f'candidate-{index}', plan, 'inventory')
            self.w.project.approve(f'candidate-{index}', '合成验收', '确认本合成案例范围', 'synthetic.md')
        self.w.save()
        for index in range(2):
            result = execute(self.w, f'journey-{index}', f'candidate-{index}')
            self.assertEqual(result['check_status'], 'passed', result['content'].get('error'))
            report = write_result_report(self.w, f'journey-report-{index}', f'journey-{index}')
            self.assertTrue(report['content']['descriptive'])
            self.assertEqual(Workspace.open(self.w.root).project.require_usable(report['id'])['check_status'], 'passed')

    def test_unreadable_partial_output_keeps_failure_record(self):
        execute = self.api()
        original_run = subprocess.run
        def nested_output(*args, **kwargs):
            completed = original_run(*args, **kwargs)
            if is_worker(args):
                (Path(kwargs['cwd']) / 'outputs/result.json').write_text('[' * 2000 + '0' + ']' * 2000)
            return completed
        with patch('econbiz.execution.subprocess.run', side_effect=nested_output):
            run = execute(self.w, 'unreadable-output', 'p1')
        self.assertEqual(run['execution_status'], 'failed')
        self.assertTrue((self.w.root / run['content']['package'] / 'process.log').is_file())
        self.assertTrue(run['content']['result_output_present'])

    def test_unexpected_parent_reference_error_cannot_reuse_worker_pass(self):
        execute = self.api()
        with patch('econbiz.numerical_check.lsmr', side_effect=RuntimeError('unexpected reference failure')):
            run = execute(self.w, 'unexpected-reference', 'p1')
        self.assertEqual(run['execution_status'], 'failed')
        check = json.loads((self.w.root / run['content']['package'] / 'outputs/parent-verification.json').read_text())
        self.assertEqual(check['check_status'], 'failed')
        self.assertEqual(run['content']['verification']['check_status'], 'failed')
