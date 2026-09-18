import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_execution import HAS_ANALYSIS, study
from econbiz.state import WorkflowError
from econbiz.workspace import Workspace


@unittest.skipUnless(HAS_ANALYSIS and importlib.util.find_spec('pypdf'), 'analysis/latex dependencies missing')
class LatexRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.w=study(Path(self.temp.name))
        from econbiz.execution import execute_analysis
        from econbiz.latex_report import write_latex_report
        execute_analysis(self.w,'r1','p1'); write_latex_report(self.w,'tex',run_id='r1')

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.latex_runtime'))
        from econbiz.latex_runtime import compile_latex_report
        from econbiz.latex_checks import read_latex_build
        return compile_latex_report,read_latex_build

    def fake(self, mode='ok'):
        path=Path(self.temp.name)/('fake-'+mode)
        path.write_text('#!'+sys.executable+'\n'+'''import sys,time
from pathlib import Path
if '--version' in sys.argv:
 print('XeTeX synthetic test compiler'); sys.exit(0)
assert '-no-shell-escape' in sys.argv
assert Path('main.tex').exists()
'''+{'ok':'''from pypdf import PdfWriter
w=PdfWriter(); w.add_blank_page(width=595,height=842)
with open('report.pdf','wb') as f:w.write(f)
Path('report.aux').write_text('stable')
Path('report.log').write_text('synthetic compiler log')
''','error':"print('missing package test.sty',flush=True); sys.exit(2)\n",
'bad':"Path('report.pdf').write_bytes(b'bad pdf')\n",'empty':"print('no output')\n",
'sleep':"print('started',flush=True); time.sleep(10)\n",
'warn':"from pypdf import PdfWriter\nw=PdfWriter();w.add_blank_page(width=595,height=842)\nw.write('report.pdf')\nPath('report.aux').write_text('stable')\nPath('report.log').write_text('Missing character: test glyph')\n",
'unstable':"from pypdf import PdfWriter\nw=PdfWriter();w.add_blank_page(width=595,height=842)\nw.write('report.pdf')\nPath('report.aux').write_text(str(time.time()))\n"}[mode])
        path.chmod(0o700); return str(path)

    def test_missing_engine_preserves_source_and_failure_readable(self):
        build,read=self.api()
        a=build(self.w,'pdf','tex',executable='/nonexistent/xelatex')
        self.assertEqual(a['content']['compile_check'],'failed')
        self.assertEqual(read(Workspace.open(self.w.root),'pdf'),a)
        self.assertTrue(any(f['path'].endswith('/compile.log') for f in a['files']))
        self.assertEqual(self.w.project.require_usable('tex')['kind'],'latex_report')

    def test_success_reopen_retry_and_pdf_tamper(self):
        build,read=self.api()
        a=build(self.w,'pdf','tex',executable=self.fake())
        self.assertEqual(a['content']['compile_check'],'passed')
        self.assertEqual(a['content']['passes'],2)
        self.assertEqual(read(Workspace.open(self.w.root),'pdf'),a)
        failed=build(self.w,'pdf','tex',executable=self.fake('error'))
        self.assertEqual(failed['version'],2)
        self.assertEqual(failed['content']['compile_check'],'failed')
        old=next(f for f in a['files'] if f['path'].endswith('.pdf'))
        self.assertTrue((self.w.root/old['path']).exists())
        a=build(self.w,'other','tex',executable=self.fake())
        pdf=self.w.root/next(f['path'] for f in a['files'] if f['path'].endswith('.pdf'))
        pdf.write_bytes(b'tampered')
        with self.assertRaises(WorkflowError): read(self.w,'other')

    def test_failure_and_timeout_logs(self):
        build,_=self.api()
        for mode in ['error','bad','empty','sleep','unstable']:
            with self.subTest(mode=mode):
                a=build(self.w,mode,'tex',executable=self.fake(mode),timeout=.3 if mode=='sleep' else 20)
                self.assertEqual(a['content']['compile_check'],'failed')
                self.assertTrue(a['content']['error'])
        log=self.w.root/next(f['path'] for f in a['files'] if f['path'].endswith('/compile.log'))
        self.assertTrue(log.exists())

    def test_warnings_require_visual_review(self):
        build,_=self.api()
        a=build(self.w,'pdf','tex',executable=self.fake('warn'))
        self.assertEqual(a['content']['compile_check'],'passed')
        self.assertTrue(a['content']['warnings'])
        self.assertEqual(a['content']['visual_check'],'not_performed')

    def test_source_change_during_build_and_no_unsaved_overwrite(self):
        build,_=self.api()
        from econbiz.latex_runtime import run_process
        touched=[]
        def change(*args,**kwargs):
            result=run_process(*args,**kwargs)
            if not touched:
                other=Workspace.open(self.w.root)
                other.project.mark('r1','completed','failed','changed during build');other.save()
                touched.append(True)
            return result
        with patch('econbiz.latex_runtime.run_process',side_effect=change):
            a=build(self.w,'pdf','tex',executable=self.fake())
        self.assertEqual(a['content']['compile_check'],'failed')
        self.assertEqual(Workspace.open(self.w.root).project.artifact('r1')['check_status'],'failed')

    @unittest.skipUnless(os.environ.get('ECONBIZ_TEST_XELATEX'), 'native XeLaTeX not configured')
    def test_native_xelatex(self):
        build,read=self.api()
        a=build(self.w,'native','tex',executable=os.environ['ECONBIZ_TEST_XELATEX'])
        self.assertEqual(a['content']['compile_check'],'passed',a['content']['error'])
        self.assertEqual(read(Workspace.open(self.w.root),'native'),a)
