import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from test_execution import HAS_ANALYSIS, study
from test_comparison import comparison_args
from econbiz.state import WorkflowError
from econbiz.workspace import Workspace


class LatexSyntaxTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.latex_syntax'))
        from econbiz.latex_syntax import escape_text, decode_text, validate_math
        return escape_text, decode_text, validate_math

    def test_text_roundtrip_and_injection(self):
        esc, dec, _ = self.api()
        for text in ['资产_比例 & 10% # $ {x} ~ ^ \\input{secret}', '0.000\n(0.001)', '中文\tEnglish', '']:
            self.assertEqual(dec(esc(text)), text)
        with self.assertRaises(WorkflowError): esc('bad\x00')
        with self.assertRaises(WorkflowError): dec(r'\input{secret}')

    def test_wide_heading_and_notes_have_no_orphan_page(self):
        from econbiz.latex_report import render_latex
        c=dict(language='zh-CN',generated_at='test',equations=[],display=dict(title='标题',paragraphs=[],sources=[],
            tables=[dict(kind='models',title='回归表',header=['变量']+['模型']*6,rows=[['x']+['1.000']*6],notes=['表注'])]))
        tex=render_latex(c)
        self.assertIn(r'\endlastfoot',tex['tables.tex'])
        self.assertLess(tex['tables.tex'].index(r'\begin{landscape}'),tex['tables.tex'].index(r'\EBReportHeading'))
        self.assertLess(tex['tables.tex'].index('表注'),tex['tables.tex'].index(r'\endlastfoot'))
        self.assertNotIn(r'\section*',tex['tables.tex'])

    def test_math_subset_and_braces(self):
        _, _, math = self.api()
        for text in [r'y_{it}=\alpha+\beta x_{it}+\mu_i+\lambda_t+\epsilon_{it}', r'\frac{1}{N}\sum_{i=1}^{N}x_i', r'\sqrt{x}+\log(x)', r'\left(x+y\right)']:
            self.assertEqual(math(text), text)
        for text in [r'\infinity',r'\input{file}', r'\def\x{1}', r'\write18{whoami}', r'\begin{matrix}1\end{matrix}', 'x$', 'x%note', 'x^^41', '{x', 'x}', '\\', '{'*40+'x'+'}'*40, 'x'*5000]:
            with self.subTest(text=text[:40]), self.assertRaises(WorkflowError): math(text)


@unittest.skipUnless(HAS_ANALYSIS, 'analysis extra not installed')
class LatexReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.w = study(Path(self.temp.name))
        from econbiz.execution import execute_analysis
        execute_analysis(self.w, 'r1', 'p1')

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.latex_report'))
        from econbiz.latex_report import write_latex_report
        from econbiz.latex_checks import read_latex_report
        return write_latex_report, read_latex_report

    def equation(self):
        return dict(id='model', title='模型公式', latex=r'y_{it}=\beta x_{it}+\gamma c_{it}+\mu_i+\lambda_t+\epsilon_{it}',
                    explanation='变量沿用实际方案。', source_refs=[dict(artifact_id='p1', version=1)])

    def test_single_reopen_actual_values_and_source(self):
        write, read = self.api()
        a = write(self.w, 'tex', run_id='r1', equations=[self.equation()])
        self.assertEqual(a['content']['source_check']['status'], 'passed')
        self.assertEqual(read(Workspace.open(self.w.root), 'tex'), a)
        rows = a['content']['display']['tables'][0]['rows']
        coef = self.w.project.artifact('r1')['content']['result']['parameters'][0]['coefficient']
        self.assertEqual(rows[0][1].split('\n')[0], f'{coef:.3f}')
        self.assertIn(['观测数', '72'], rows)
        self.assertEqual(len([f for f in a['files'] if f['path'].endswith('.tex')]), 5)
        self.assertEqual(a['content']['compile_check'], 'not_performed')
        self.w.project.mark('r1', 'completed', 'failed', 'test')
        with self.assertRaises(WorkflowError): read(self.w, 'tex')

    def test_comparison_order_and_english(self):
        from econbiz.execution import execute_analysis
        from econbiz.comparison import write_model_comparison
        execute_analysis(self.w, 'r2', 'p1')
        args = comparison_args(('r2', 'r1')); args['title'] = 'Baseline results'
        for c in args['columns']: c['title'] = c['run_id']
        write_model_comparison(self.w, 'cmp', **args)
        write, read = self.api()
        a = write(self.w, 'tex', comparison_id='cmp', language='en')
        self.assertEqual(a['content']['display']['tables'][0]['header'], ['Variable', '(1) r2', '(2) r1'])
        self.assertIn(['Observations', '72', '72'], a['content']['display']['tables'][0]['rows'])
        self.assertEqual(read(self.w, 'tex'), a)

    def test_exclusive_source_invalid_formula_and_version(self):
        write, _ = self.api()
        for kwargs in [{}, dict(run_id='r1',comparison_id='no'), dict(run_id='r1',language='de')]:
            with self.assertRaises(WorkflowError): write(self.w,'tex',**kwargs)
        eq = self.equation(); eq['source_refs'][0]['version'] = 99
        with self.assertRaises(WorkflowError): write(self.w,'tex',run_id='r1',equations=[eq])
        eq = self.equation(); eq['latex'] = r'\input{file}'
        with self.assertRaises(WorkflowError): write(self.w,'tex',run_id='r1',equations=[eq])

    def test_file_content_and_metadata_tamper(self):
        write, read = self.api()
        a = write(self.w,'tex',run_id='r1')
        path = self.w.root/next(f['path'] for f in a['files'] if f['path'].endswith('/tables.tex'))
        path.write_text(path.read_text().replace('72','999'))
        with self.assertRaises(WorkflowError): read(self.w,'tex')
        a = write(self.w,'second',run_id='r1')
        self.w.project._state['artifacts']['second']['content']['display']['tables'][0]['rows'][0][1]='999'
        with self.assertRaises(WorkflowError): read(self.w,'second')

    def test_independent_actual_cell_check(self):
        write, _ = self.api()
        a = write(self.w,'tex',run_id='r1')
        from econbiz.latex_checks import check_latex_content
        files={Path(f['path']).name:(self.w.root/f['path']).read_text() for f in a['files'] if f['path'].endswith('.tex')}
        self.assertEqual(check_latex_content(files,a['content'])['status'],'passed')
        files['tables.tex']=files['tables.tex'].replace(r'\EBCell{72}',r'\EBCell{999}',1)
        self.assertEqual(check_latex_content(files,a['content'])['status'],'failed')
