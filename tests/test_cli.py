import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'econbiz', *map(str, args)], capture_output=True, text=True)

    def test_init_audit_status_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / 'study'
            self.assertEqual(self.run_cli('init', project, '--direction', '合成数据研究').returncode, 0)
            state = (project / 'research_state.json').read_bytes()
            self.assertNotEqual(self.run_cli('init', project, '--direction', '覆盖').returncode, 0)
            self.assertEqual((project / 'research_state.json').read_bytes(), state)
            data = Path(d) / 'data.csv'
            data.write_text('firm,year,x\na,2023,1\na,2024,2\n')
            result = self.run_cli('audit', project, data, '--entity', 'firm', '--time', 'year', '--numeric', 'x')
            self.assertEqual(result.returncode, 0, result.stderr)
            status = self.run_cli('status', project)
            self.assertEqual(status.returncode, 0)
            self.assertIn('inventory', status.stdout)
            self.assertEqual(len(list((project / 'research/reports').glob('*/v0001/*.json'))), 1)

    def test_failed_audit_persisted_with_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / 'study'
            self.run_cli('init', project, '--direction', '合成数据研究')
            data = Path(d) / 'data.csv'
            data.write_text('firm,year,x\na,2023,1\na,2023,2\n')
            r = self.run_cli('audit', project, data, '--entity', 'firm', '--time', 'year', '--numeric', 'x')
            self.assertEqual(r.returncode, 2, r.stderr)
            state = json.loads((project / 'research_state.json').read_text())
            self.assertEqual(next(a for a in state['artifacts'].values() if a['kind'] == 'inventory')['check_status'], 'failed')

    def test_candidate_and_explicit_approval_commands(self):
        from test_plans import candidate
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / 'study'
            self.run_cli('init', project, '--direction', '合成数据研究')
            data = Path(d) / 'data.csv'
            data.write_text('firm,year,x,y\na,2023,1,2\na,2024,2,3\n')
            self.run_cli('audit', project, data, '--entity', 'firm', '--time', 'year', '--numeric', 'x', 'y')
            state = json.loads((project / 'research_state.json').read_text())
            inventory = next(k for k, a in state['artifacts'].items() if a['kind'] == 'inventory')
            plan = Path(d) / 'plan.json'
            plan.write_text(json.dumps(candidate()))
            r = self.run_cli('plan', project, plan, '--id', 'p1', '--inventory', inventory)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = self.run_cli('approve', project, 'p1', '--actor', '测试研究者', '--reason', '测试确认记录', '--evidence', 'test-only.md')
            self.assertEqual(r.returncode, 0, r.stderr)
            state = json.loads((project / 'research_state.json').read_text())
            self.assertEqual(state['decisions'][0]['version'], 1)

    def test_malformed_csv_failure_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / 'study'
            self.run_cli('init', project, '--direction', '合成研究')
            data = Path(d) / 'bad.csv'
            data.write_text('firm,year,x\na,2023,"unterminated\n')
            r = self.run_cli('audit', project, data, '--entity', 'firm', '--time', 'year', '--numeric', 'x')
            self.assertEqual(r.returncode, 2)
            reports = list((project / 'research/reports').glob('*/v0001/*.json'))
            self.assertEqual(len(reports), 1)
            self.assertEqual(json.loads(reports[0].read_text())['check_status'], 'failed')

    def test_guided_candidates_saved_and_not_approved(self):
        from test_candidates import brief
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / 'study'
            self.run_cli('init', project, '--direction', '合成研究')
            data = Path(d) / 'data.csv'
            data.write_text('firm,year,x,y\na,2023,1,2\na,2024,2,3\nb,2023,2,3\nb,2024,3,4\n')
            self.run_cli('audit', project, data, '--entity', 'firm', '--time', 'year', '--numeric', 'x', 'y')
            state = json.loads((project / 'research_state.json').read_text())
            inventory = next(k for k, a in state['artifacts'].items() if a['kind'] == 'inventory')
            intake = Path(d) / 'brief.json'
            intake.write_text(json.dumps(brief()))
            result = self.run_cli('guide', project, '--inventory', inventory, '--brief', intake)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list((project / 'research/reports').glob('*.html'))), 1)
            state = json.loads((project / 'research_state.json').read_text())
            self.assertEqual(state['decisions'], [])
            self.assertEqual(sum(a['kind'] == 'plan' for a in state['artifacts'].values()), 2)

    def test_guidance_cancel_does_not_save_answers(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / 'study'
            self.run_cli('init', project, '--direction', '合成研究')
            data = Path(d) / 'data.csv'
            data.write_text('firm,year,x\na,2023,1\n')
            self.run_cli('audit', project, data, '--entity', 'firm', '--time', 'year', '--numeric', 'x')
            state_path = project / 'research_state.json'
            before = state_path.read_bytes()
            inventory = next(k for k, a in json.loads(before)['artifacts'].items() if a['kind'] == 'inventory')
            r = subprocess.run([sys.executable, '-m', 'econbiz', 'guide', str(project), '--inventory', inventory],
                               input='', capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('取消', r.stderr)
            self.assertEqual(state_path.read_bytes(), before)
