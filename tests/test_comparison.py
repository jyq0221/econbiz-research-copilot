import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from test_execution import HAS_ANALYSIS, study
from econbiz.state import WorkflowError
from econbiz.workspace import Workspace


def comparison_args(run_ids=('r1', 'r2')):
    return dict(title='基准与稳健性比较', reason='合成验收',
        columns=[dict(run_id=r, title='模型 '+str(i+1), role='baseline' if i == 0 else 'robustness')
                 for i, r in enumerate(run_ids)],
        variables=[dict(id=f, label=f, definition='原值', unit=u, transform='原值',
                        members={r: f for r in run_ids}, evidence_refs=[])
                   for f, u in [('x', '指数'), ('y', '比例'), ('c', '指数')]])


class SampleComparisonTests(unittest.TestCase):
    def test_equal_counts_different_keys(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.comparison'))
        from econbiz.comparison import compare_sample_keys
        d = compare_sample_keys([['001','2020'],['002','2020']], [['001','2020'],['003','2020']])
        self.assertFalse(d['same_sample'])
        self.assertEqual(d['intersection_count'], 1)
        self.assertEqual(d['left_only'], [['002','2020']])
        with self.assertRaises(WorkflowError): compare_sample_keys([['001','2020']]*2, [])

@unittest.skipUnless(HAS_ANALYSIS, 'analysis extra not installed')
class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.w = study(Path(self.temp.name))
        from econbiz.execution import execute_analysis
        execute_analysis(self.w, 'r1', 'p1')
        execute_analysis(self.w, 'r2', 'p1')

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.comparison'))
        from econbiz.comparison import write_model_comparison, read_model_comparison
        return write_model_comparison, read_model_comparison

    def test_order_content_reopen_and_invalidation(self):
        write, read = self.api()
        a = write(self.w, 'cmp', **comparison_args(('r2','r1')))
        self.assertEqual([m['run']['id'] for m in a['content']['models']], ['r2','r1'])
        self.assertEqual(len(a['content']['models'][0]['parameters']), 2)
        self.assertTrue(a['content']['differences'][0]['same_sample'])
        self.assertEqual(read(Workspace.open(self.w.root), 'cmp'), a)
        self.w.project.mark('r1', 'completed', 'failed', 'test')
        with self.assertRaises(WorkflowError): read(self.w, 'cmp')

    def test_unknown_and_conflicting_identity_rejected(self):
        write, _ = self.api()
        for mutate in [lambda a: a['variables'][0].update(unit='元'),
                       lambda a: a['variables'][0].update(definition=None),
                       lambda a: a['variables'][0]['members'].update(r2='absent'),
                       lambda a: a['columns'].append(a['columns'][0])]:
            args = comparison_args()
            mutate(args)
            with self.assertRaises(WorkflowError): write(self.w, 'cmp', **args)

    def test_comparison_content_tamper_rejected(self):
        write, read = self.api()
        write(self.w, 'cmp', **comparison_args())
        self.w.project._state['artifacts']['cmp']['content']['models'][0]['parameters'][0]['coefficient'] = 900
        with self.assertRaises(WorkflowError): read(self.w, 'cmp')

    def test_real_filters_same_count_different_keys_and_omission(self):
        from econbiz.plans import register_plan
        from econbiz.execution import execute_analysis
        from econbiz.comparison_display import build_display
        p = copy.deepcopy(self.w.project.artifact('p1')['content'])
        p.update(purpose='exploratory', exploration_reason='合成样本比较测试，保留先前运行')
        p['execution']['sample_filters'] = [{'field':'year','op':'le','value':2022}]
        register_plan(self.w.project,'p2',p,'inventory')
        self.w.project.approve('p2','test','synthetic','decision2.md'); self.w.save()
        execute_analysis(self.w,'r3','p2')
        p['execution']['sample_filters'] = [{'field':'year','op':'ge','value':2019}]
        register_plan(self.w.project,'p3',p,'inventory')
        self.w.project.approve('p3','test','synthetic','decision3.md'); self.w.save()
        execute_analysis(self.w,'r4','p3')
        write, _ = self.api()
        args = comparison_args(('r3','r4')); args['display_terms']=['x']
        a=write(self.w,'cmp',**args)
        diff=a['content']['differences'][0]
        self.assertFalse(diff['same_sample'])
        self.assertEqual(diff['intersection_count'],48)
        self.assertEqual(len(diff['left_only']),12)
        self.assertEqual(diff['left_only_reasons']['unresolved_keys'],[])
        self.assertEqual(len(a['content']['models'][0]['parameters']),2)
        display=build_display(a['content'])
        self.assertNotIn('c',[r[0] for r in display['tables'][0]['rows']])

    def test_actual_control_list_is_visible(self):
        write,_=self.api()
        a=write(self.w,'cmp',**comparison_args())
        from econbiz.comparison_display import build_display
        rows=build_display(a['content'])['tables'][0]['rows']
        self.assertIn(['控制变量','c','c'],rows)
