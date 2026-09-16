"""Real models -> comparison -> editable Word -> reopen; temporary synthetic inputs."""
import copy
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_execution import HAS_ANALYSIS, study
from test_comparison import comparison_args
from econbiz.plans import register_plan
from econbiz.execution import execute_analysis
from econbiz.workspace import Workspace

HAS_DOCX = importlib.util.find_spec('docx') is not None


def run_workflow(root, native=None):
    w=study(root)
    p=copy.deepcopy(w.project.artifact('p1')['content'])
    p['controls']=[]
    register_plan(w.project,'base',p,'inventory')
    w.project.approve('base','test','synthetic preplanned','base.md')
    p=copy.deepcopy(w.project.artifact('p1')['content'])
    p['execution']['sample_filters']=[{'field':'year','op':'ge','value':2020}]
    register_plan(w.project,'restricted',p,'inventory')
    w.project.approve('restricted','test','synthetic preplanned','restricted.md'); w.save()
    for run,plan in [('r1','base'),('r2','p1'),('r3','restricted')]:
        kwargs=dict(backend='stata',stata_executable=native) if native and run=='r2' else {}
        a=execute_analysis(w,run,plan,**kwargs)
        if a['check_status']!='passed': raise AssertionError(a['content'].get('error'))
    from econbiz.comparison import write_model_comparison
    from econbiz.word_report import write_word_report
    args=comparison_args(('r1','r2','r3'))
    args['variables'][2]['members'].pop('r1')
    write_model_comparison(w,'cmp',**args)
    write_word_report(w,'word','cmp')
    return w


@unittest.skipUnless(HAS_ANALYSIS and HAS_DOCX,'analysis/documents extra not installed')
class StageCWorkflowTests(unittest.TestCase):
    def test_python_only_three_models_reopen_and_state(self):
        import builtins
        original=builtins.__import__
        def guarded(name,*args,**kwargs):
            if name.startswith('econbiz.stata') or name in {'stata_engine','stata_runtime'}:
                raise AssertionError('Python-only must not import Stata runtime')
            return original(name,*args,**kwargs)
        with tempfile.TemporaryDirectory() as d, patch('builtins.__import__',side_effect=guarded):
            w=run_workflow(Path(d))
            from econbiz.comparison import read_model_comparison
            from econbiz.document_checks import read_word_report
            from econbiz.comparison_display import build_display
            reopened=Workspace.open(w.root)
            c=read_model_comparison(reopened,'cmp')['content']
            self.assertEqual([m['sample']['final_rows'] for m in c['models']],[72,72,48])
            rows=build_display(c)['tables'][0]['rows']
            self.assertEqual(next(r for r in rows if r[0]=='c')[1],'未纳入')
            self.assertEqual(read_word_report(reopened,'word')['content']['visual_check'],'not_performed')

    def test_nonclustered_standard_errors_export(self):
        from econbiz.comparison import write_model_comparison
        from econbiz.word_report import write_word_report
        with tempfile.TemporaryDirectory() as d:
            w=study(Path(d))
            for method in ('hc1','classical'):
                p=copy.deepcopy(w.project.artifact('p1')['content'])
                p['standard_errors']={'method':method,'field':None,'rationale':'合成验收'}
                register_plan(w.project,method,p,'inventory')
                w.project.approve(method,'test','synthetic preplanned',method+'.md')
            w.save()
            for method in ('hc1','classical'):
                a=execute_analysis(w,method+'run',method)
                self.assertEqual(a['check_status'],'passed')
            write_model_comparison(w,'cmp',**comparison_args(('hc1run','classicalrun')))
            a=write_word_report(w,'word','cmp')
            self.assertEqual(a['content']['numeric_text_check']['status'],'passed')
            self.assertIn(['聚类字段','不适用','不适用'],a['content']['display']['tables'][0]['rows'])

    def test_missing_control_and_different_outcome_units(self):
        import csv
        from econbiz.comparison import write_model_comparison
        from econbiz.comparison_display import build_display, render_comparison_markdown
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); w=study(root)
            with (root/'panel.csv').open() as f:
                rows=list(csv.DictReader(f))
            rows[0]['c']=''
            for row in rows: row['y_pct']=str(100*float(row['y']))
            source=root/'transformed.csv'
            with source.open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]))
                writer.writeheader();writer.writerows(rows)
            w.import_file('raw2',source,role='raw_data',reason='合成单位与缺失测试')
            w.audit('inventory2','raw2',entity='firm',time='year',numeric=['x','y','c','y_pct'])
            for name in ('base','control','percent'):
                p=copy.deepcopy(w.project.artifact('p1')['content'])
                if name=='base': p['controls']=[]
                if name=='percent':
                    p['mapping']['y'].update(field='y_pct',unit='百分比',definition='比例乘100')
                register_plan(w.project,name,p,'inventory2')
                w.project.approve(name,'test','synthetic preplanned',name+'.md')
            w.save()
            for name in ('base','control','percent'):
                self.assertEqual(execute_analysis(w,name+'run',name)['check_status'],'passed')
            args=comparison_args(('baserun','controlrun','percentrun'))
            args['variables'][2]['members'].pop('baserun')
            args['variables'][1]['members'].pop('percentrun')
            args['variables'].append(dict(id='ypct',label='y',definition='比例乘100',unit='百分比',
                transform='原值',members={'percentrun':'y_pct'},evidence_refs=[]))
            args['variables'][0]['label']='中文 | <变量>'
            a=write_model_comparison(w,'cmp',**args)
            diff=a['content']['differences'][0]
            self.assertEqual(len(diff['left_only']),1)
            self.assertEqual(diff['left_only_reasons']['unresolved_keys'],[])
            self.assertEqual(a['content']['models'][1]['sample']['control_additional_loss'],1)
            display=build_display(a['content'])
            model_tables=[t for t in display['tables'] if t['kind']=='models']
            self.assertEqual([len(t['header']) for t in model_tables],[3,2])
            self.assertIn('百分比',model_tables[1]['title'])
            self.assertIn(r'中文 \| &lt;变量&gt;',render_comparison_markdown(display))

    @unittest.skipUnless(os.environ.get('ECONBIZ_TEST_STATA'),'native Stata explicitly enabled only')
    def test_mixed_python_stata_sources(self):
        with tempfile.TemporaryDirectory() as d:
            w=run_workflow(Path(d),os.environ['ECONBIZ_TEST_STATA'])
            from econbiz.comparison import read_model_comparison
            models=read_model_comparison(w,'cmp')['content']['models']
            self.assertEqual([m['backend'] for m in models],['python','stata','python'])
