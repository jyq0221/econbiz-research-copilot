import importlib.util
import unittest
from pathlib import Path
import test_latex_runtime as runtime_tests
from econbiz.state import WorkflowError
from econbiz.workspace import Workspace


@unittest.skipUnless(runtime_tests.HAS_ANALYSIS and importlib.util.find_spec('PIL') and importlib.util.find_spec('pypdf'), 'analysis/latex dependencies missing')
class LatexReviewTests(unittest.TestCase):
    setUp=runtime_tests.LatexRuntimeTests.setUp
    fake=runtime_tests.LatexRuntimeTests.fake

    def api(self):
        import econbiz.latex_checks as c
        self.assertTrue(hasattr(c,'record_latex_review'))
        return c.record_latex_review,c.read_latex_review

    def build(self):
        from econbiz.latex_runtime import compile_latex_report
        return compile_latex_report(self.w,'pdf','tex',executable=self.fake())

    def pages(self):
        from PIL import Image
        p=Path(self.temp.name)/'page-1.png';Image.new('RGB',(30,40),'white').save(p)
        return [str(p)]

    def test_actual_review_reopen_and_tamper(self):
        write,read=self.api();b=self.build()
        r=write(self.w,'review','pdf',pages=self.pages(),inspected_pages=[1],findings=[],reason='synthetic image test')
        self.assertEqual(r['content']['pdf_sha256'],b['content']['pdf_sha256'])
        self.assertEqual(read(Workspace.open(self.w.root),'review'),r)
        image=self.w.root/next(f['path'] for f in r['files'] if f['path'].endswith('.png'))
        image.write_bytes(b'wrong')
        with self.assertRaises(WorkflowError): read(self.w,'review')

    def test_invalid_pages_failed_build_and_findings(self):
        write,_=self.api();self.build()
        for pages,inspected in [(self.pages(),[]),(self.pages(),[1,1]),([], [1]),(self.pages(),[True])]:
            with self.assertRaises(WorkflowError): write(self.w,'review','pdf',pages=pages,inspected_pages=inspected,findings=[],reason='test')
        r=write(self.w,'review','pdf',pages=self.pages(),inspected_pages=[1],findings=['clipped text'],reason='test')
        self.assertEqual(r['content']['visual_check'],'failed')
        from econbiz.latex_runtime import compile_latex_report
        compile_latex_report(self.w,'bad','tex',executable='/nonexistent')
        with self.assertRaises(WorkflowError): write(self.w,'badreview','bad',pages=self.pages(),inspected_pages=[1],findings=[],reason='test')

    def test_progress_resume_and_revision_invalidate_review(self):
        write,read=self.api();self.build()
        write(self.w,'review','pdf',pages=self.pages(),inspected_pages=[1],findings=[],reason='test')
        from econbiz.progress import resume_context
        summary=resume_context(Workspace.open(self.w.root))
        self.assertEqual(set(summary['deliveries']),{'tex','pdf','review'})
        progress=(self.w.root/'研究进展.md').read_text()
        self.assertIn('main.tex',progress);self.assertIn('report.pdf',progress)
        from econbiz.latex_report import write_latex_report
        write_latex_report(self.w,'tex',run_id='r1')
        with self.assertRaises(WorkflowError): read(self.w,'review')
