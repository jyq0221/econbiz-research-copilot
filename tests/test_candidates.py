import copy
import tempfile
import unittest
from pathlib import Path

from econbiz.audit import audit_csv
from econbiz.candidates import build_candidates, store_candidates
from econbiz.plans import validate_plan
from econbiz.state import Project, WorkflowError


def measurement(field, concept):
    return dict(field=field, concept=concept, definition='合成指标原值', unit='指数',
                time='会计年度', source='合成数据', missing_meaning='未披露保持未知',
                measurement_limit='只用于教学，不对应真实企业概念', confirmed=True)


def brief():
    return dict(goal='association', focus=measurement('y', '经营风险'),
                explanatory=measurement('x', '数字化程度'))


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'data.csv'
        self.panel = 'firm,year,x,y\na,2023,1,2\na,2024,2,3\nb,2023,2,4\nb,2024,4,未披露\n'
        self.p = self.project(self.panel)

    def project(self, text):
        self.path.write_text(text)
        p = Project.create('demo', '了解数字化程度与经营风险的关系')
        report = audit_csv(self.path, 'firm', 'year', ['x', 'y'])
        p.add('inventory', 'inventory', report)
        p.mark('inventory', 'completed', report['check_status'], '结构检查')
        return p

    def test_two_different_questions_from_real_data(self):
        before = self.path.read_bytes()
        r = build_candidates(self.p, 'inventory', brief())
        self.assertEqual([p['goal'] for p in r['plans']], ['description', 'association'])
        self.assertEqual(r['facts']['total_rows'], 4)
        self.assertEqual(r['facts']['focus_rows'], 3)
        self.assertEqual(r['facts']['pair_rows'], 3)
        for p in r['plans']:
            validate_plan(p, ['firm', 'year', 'x', 'y'])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIn('不代表', r['plans'][1]['conditions'])

    def test_description_only_one_plan(self):
        b = brief()
        b['goal'] = 'description'
        b['explanatory'] = None
        self.assertEqual(len(build_candidates(self.p, 'inventory', b)['plans']), 1)

    def test_unsupported_or_unknown_goal_preserved_without_downgrading(self):
        for goal in ['causal', 'prediction', 'undecided']:
            b = brief()
            b['goal'] = goal
            r = build_candidates(self.p, 'inventory', b)
            self.assertEqual(r['goal'], goal)
            self.assertEqual(r['plans'], [])
            self.assertTrue(r['questions'])

    def test_unconfirmed_or_missing_meaning_no_fabrication(self):
        for key, value in [('confirmed', False), ('unit', ''), ('source', '待核实')]:
            b = brief()
            b['focus'][key] = value
            r = build_candidates(self.p, 'inventory', b)
            self.assertEqual(r['plans'], [])
            self.assertTrue(r['questions'])

    def test_absent_field_rejected_without_mutating_project(self):
        b = brief()
        b['focus']['field'] = 'invented'
        before = self.p.snapshot()
        with self.assertRaises(WorkflowError):
            store_candidates(self.p, 'inventory', b, 'session')
        self.assertEqual(self.p.snapshot(), before)

    def test_no_known_focus_returns_questions(self):
        b = brief()
        b['focus'] = None
        r = build_candidates(self.p, 'inventory', b)
        self.assertEqual(r['plans'], [])
        self.assertTrue(r['questions'])

    def test_no_usable_values_returns_zero(self):
        p = self.project('firm,year,x,y\na,2023,1,未披露\nb,2024,2,\n')
        self.assertEqual(build_candidates(p, 'inventory', brief())['plans'], [])

    def test_no_within_variation_keeps_only_descriptive(self):
        p = self.project('firm,year,x,y\na,2023,1,2\na,2024,1,3\nb,2023,2,4\nb,2024,2,5\n')
        r = build_candidates(p, 'inventory', brief())
        self.assertEqual(len(r['plans']), 1)
        self.assertIn('企业内', ' '.join(r['questions']))

    def test_variation_checked_on_joint_sample(self):
        p = self.project('firm,year,x,y\na,2023,1,2\na,2024,2,\nb,2023,2,4\nb,2024,3,\n')
        r = build_candidates(p, 'inventory', brief())
        self.assertEqual(len(r['plans']), 1)
        self.assertEqual(r['facts']['pair_rows'], 2)

    def test_joint_sample_loss_explained(self):
        p = self.project('firm,year,x,y\na,2023,1,2\na,2024,2,3\nb,2023,未披露,4\nb,2024,3,5\n')
        r = build_candidates(p, 'inventory', brief())
        self.assertEqual(r['facts']['additional_missing_x'], 1)
        self.assertIn('1', r['plans'][1]['sample'])

    def test_same_field_does_not_create_association(self):
        b = brief()
        b['explanatory'] = copy.deepcopy(b['focus'])
        self.assertEqual(len(build_candidates(self.p, 'inventory', b)['plans']), 1)

    def test_store_versions_dependencies_and_no_auto_approval(self):
        updated, r = store_candidates(self.p, 'inventory', brief(), 'session')
        self.assertEqual(self.p.snapshot()['decisions'], [])
        self.assertEqual(updated.snapshot()['decisions'], [])
        self.assertEqual(updated.artifact('session-plan-1')['execution_status'], 'needs_decision')
        with self.assertRaises(WorkflowError):
            updated.approve('session-plan-2', '测试者', '测试', 'test.md')
        updated.revise('session-intake', brief(), '修改字段含义')
        self.assertEqual(updated.artifact('session-plan-1')['execution_status'], 'stale')
        self.assertEqual(updated.artifact('session-comparison')['execution_status'], 'stale')

    def test_changed_source_blocks_generation(self):
        self.path.write_text(self.panel.replace('1,2', '9,2'))
        with self.assertRaises(WorkflowError):
            build_candidates(self.p, 'inventory', brief())

    def test_post_result_requires_exploration_reason(self):
        self.p.add('old-result', 'result', {'coefficient': 0})
        self.p.mark('old-result', 'completed', 'passed', '测试结果')
        b = brief()
        self.assertEqual(build_candidates(self.p, 'inventory', b)['plans'], [])
        b['exploration_reason'] = '看到旧结果后提出不同问题'
        r = build_candidates(self.p, 'inventory', b)
        self.assertTrue(all(p['purpose'] == 'exploratory' for p in r['plans']))

    def test_post_result_status_survives_revision_or_failed_recheck(self):
        for action in ['revise', 'fail', 'invalidate']:
            p = self.project(self.panel)
            p.add('old-result', 'result', {'coefficient': 0}, ['inventory'])
            p.mark('old-result', 'completed', 'passed', '测试结果')
            if action == 'revise':
                p.revise('old-result', {'coefficient': 1}, '准备重跑')
            elif action == 'fail':
                p.mark('old-result', 'failed', 'failed', '复查不通过')
            else:
                p.mark('inventory', 'completed', 'failed', '重新检查数据')
                p.mark('inventory', 'completed', 'passed', '数据复查通过')
            b = brief()
            self.assertEqual(build_candidates(p, 'inventory', b)['plans'], [], action)
            b['exploration_reason'] = '看到以前结果后重新提出问题'
            self.assertTrue(all(plan['purpose'] == 'exploratory' for plan in build_candidates(p, 'inventory', b)['plans']))

    def test_legacy_completed_result_recheck_preserves_exposure(self):
        self.p.add('old-result', 'result', {'coefficient': 0})
        self.p.mark('old-result', 'completed', 'passed', '旧版本产生结果')
        legacy = self.p.snapshot()
        legacy['artifacts']['old-result'].pop('has_completed_result')
        p = Project(legacy)
        p.mark('old-result', 'failed', 'failed', '旧结果复查失败')
        self.assertEqual(build_candidates(p, 'inventory', brief())['plans'], [])
