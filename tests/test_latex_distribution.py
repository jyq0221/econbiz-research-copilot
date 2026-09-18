"""Exercise the actual exported runtime, including PDF when a native engine is configured."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_execution import HAS_ANALYSIS, study
import test_distribution


@unittest.skipUnless(HAS_ANALYSIS,'analysis extra missing')
class LatexDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_distribution.DistributionTests.setUpClass()
        cls.package=test_distribution.DistributionTests.package
        cls.addClassCleanup(test_distribution.DistributionTests.temporary.cleanup)

    def test_runtime_package_exports_and_reopens_latex(self):
        self.assertTrue((self.package/'docs/research-handbook/latex-delivery.md').is_file())
        with tempfile.TemporaryDirectory(prefix='中文 LaTeX ') as directory:
            w=study(Path(directory))
            from econbiz.execution import execute_analysis
            execute_analysis(w,'r1','p1')
            code='''
import os,sys
from pathlib import Path
import econbiz
from econbiz.workspace import Workspace
from econbiz.latex_report import write_latex_report
from econbiz.latex_runtime import compile_latex_report
from econbiz.latex_checks import read_latex_report,read_latex_build
assert Path(econbiz.__file__).resolve().is_relative_to(Path.cwd())
w=Workspace.open(sys.argv[1]);key=sys.argv[2]
write_latex_report(w,key,run_id='r1')
assert read_latex_report(Workspace.open(w.root),key)['content']['source_check']['status']=='passed'
if os.environ.get('ECONBIZ_TEST_XELATEX'):
 a=compile_latex_report(w,key+'-pdf',key,executable=os.environ['ECONBIZ_TEST_XELATEX'])
 assert a['content']['compile_check']=='passed',a['content']['error']
 assert read_latex_build(Workspace.open(w.root),key+'-pdf')==a
'''
            import shutil
            published=Path(directory)/'published';shutil.copytree(self.package,published)
            subprocess.run(['git','init','-q','-b','main',str(published)],check=True)
            subprocess.run(['git','-C',str(published),'add','.'],check=True)
            subprocess.run(['git','-C',str(published),'-c','user.name=Test','-c','user.email=test@example.invalid',
                            '-c','commit.gpgsign=false','commit','-qm','runtime'],check=True)
            clone=Path(directory)/'clone';subprocess.run(['git','clone','-q',str(published),str(clone)],check=True)
            for root,key in [(self.package,'zip-tex'),(clone,'clone-tex')]:
                r=subprocess.run([sys.executable,'-c',code,str(w.root),key],cwd=root,capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
