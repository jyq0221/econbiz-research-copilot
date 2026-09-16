import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import unquote


class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        source = Path(__file__).resolve().parents[1]
        snapshot = cls.root / 'source'
        snapshot.mkdir()
        paths = subprocess.check_output(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=source
        ).decode().split('\0')
        for relative in set(filter(None, paths)):
            path = source / relative
            if path.is_file():
                target = snapshot / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        subprocess.run(['git', 'init', '-q', str(snapshot)], check=True)
        subprocess.run(['git', '-C', str(snapshot), 'add', '.'], check=True)
        subprocess.run([
            'git', '-C', str(snapshot), '-c', 'user.name=Archive Test',
            '-c', 'user.email=archive@example.invalid', '-c', 'commit.gpgsign=false',
            'commit', '-qm', 'Synthetic working-tree snapshot'
        ], check=True)
        raw = subprocess.check_output(['git', '-C', str(snapshot), 'archive', '--format=zip', 'HEAD'])
        cls.package = cls.root / '研究使用包 with spaces'
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            cls.names = set(archive.namelist())
            archive.extractall(cls.package)

    def test_download_omits_development_material_and_keeps_runtime(self):
        for prefix in ('tests/', 'examples/', 'scripts/', 'docs/developer/', 'docs/superpowers/'):
            with self.subTest(prefix=prefix):
                self.assertFalse(any(name.startswith(prefix) for name in self.names), prefix)
        self.assertNotIn('docs/research-handbook/teaching-cases.md', self.names)
        self.assertNotIn('docs/agent-entry-validation.md', self.names)
        self.assertIn('.github/ISSUE_TEMPLATE/trial-feedback.md', self.names)
        for path in ('AGENTS.md', 'CLAUDE.md', 'README.md', 'pyproject.toml', 'econbiz/workspace.py',
                     'docs/research-handbook/tool-contracts.md', 'docs/research-handbook/project-records.md'):
            self.assertIn(path, self.names)
        for name in ('research', 'design', 'analysis', 'evidence', 'interpret'):
            source = f'.agents/skills/econbiz-{name}/SKILL.md'
            mirror = source.replace('.agents/', '.claude/')
            self.assertEqual((self.package / source).read_bytes(), (self.package / mirror).read_bytes())

    def test_download_has_no_broken_local_markdown_links(self):
        errors = []
        for path in self.package.rglob('*.md'):
            for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text('utf-8')):
                link = unquote(link.strip('<>').split('#')[0])
                if link and not re.match(r'^[a-z]+:', link) and not (path.parent / link).exists():
                    errors.append(f'{path.relative_to(self.package)} -> {link}')
        self.assertEqual(errors, [])

    def test_unpacked_runtime_saves_and_resumes_without_test_data(self):
        self.assert_runtime(self.package)

    def test_clean_main_clone_matches_download_and_runs_independently(self):
        # Publish the same archived runtime tree as main, then make a real clone.
        published = self.root / 'published-main'
        published.mkdir()
        for name in self.names:
            source = self.package / name
            if source.is_file():
                target = published / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(published)], check=True)
        subprocess.run(['git', '-C', str(published), 'add', '.'], check=True)
        subprocess.run([
            'git', '-C', str(published), '-c', 'user.name=Archive Test',
            '-c', 'user.email=archive@example.invalid', '-c', 'commit.gpgsign=false',
            'commit', '-qm', 'Runtime distribution'
        ], check=True)
        clone = self.root / '默认 clone with spaces'
        subprocess.run(['git', 'clone', '-q', str(published), str(clone)], check=True)
        paths = subprocess.check_output(['git', '-C', str(clone), 'ls-files', '-z']).decode().split('\0')
        expected = {name for name in self.names if (self.package / name).is_file()}
        self.assertEqual(set(filter(None, paths)), expected)
        for name in expected:
            self.assertEqual((clone / name).read_bytes(), (self.package / name).read_bytes())
        self.assert_runtime(clone)

    def assert_runtime(self, directory):
        code = '''
import json
from pathlib import Path
import econbiz
from econbiz.workspace import Workspace
from econbiz.progress import resume_context
assert Path(econbiz.__file__).resolve().is_relative_to(Path.cwd())
w = Workspace.create(Path('research-projects/archive-check'), 'archive-check', '下载包接续核验')
w.save_record('context', 'research_context', {
    'question': '已保存的材料能否独立接续？', 'known': [], 'unknown': ['尚无研究数据'],
    'constraints': [], 'next_step': '核实当前项目材料'
}, reason='独立验证下载包接口')
summary = resume_context(Workspace.open(w.root))
print(json.dumps({'question': summary['records']['context']['content']['question'],
                  'view': (w.root / '研究进展.md').is_file()}, ensure_ascii=False))
'''
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=directory,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), {'question': '已保存的材料能否独立接续？', 'view': True})

    @unittest.skipUnless(__import__('importlib').util.find_spec('docx') and __import__('importlib').util.find_spec('linearmodels'), 'analysis/documents extras missing')
    def test_packaged_stage_c_actual_outputs_reopen(self):
        from test_execution import study
        from econbiz.execution import execute_analysis
        from test_comparison import comparison_args
        with tempfile.TemporaryDirectory() as directory:
            w=study(Path(directory))
            execute_analysis(w,'r1','p1'); execute_analysis(w,'r2','p1')
            args=Path(directory)/'args.json'
            args.write_text(json.dumps(comparison_args()))
            code='''
import json,sys
from pathlib import Path
import econbiz
from econbiz.workspace import Workspace
from econbiz.comparison import write_model_comparison,read_model_comparison
from econbiz.word_report import write_word_report
from econbiz.document_checks import read_word_report
assert Path(econbiz.__file__).resolve().is_relative_to(Path.cwd())
w=Workspace.open(sys.argv[1])
write_model_comparison(w,sys.argv[3],**json.loads(Path(sys.argv[2]).read_text()))
write_word_report(w,sys.argv[3]+'-word',sys.argv[3])
a=read_word_report(Workspace.open(w.root),sys.argv[3]+'-word')
assert a['content']['numeric_text_check']['status']=='passed'
assert a['content']['visual_check']=='not_performed'
'''
            # Ordinary local clone of the runtime tree, independently of source checkout.
            published=Path(directory)/'published'; shutil.copytree(self.package,published)
            subprocess.run(['git','init','-q','-b','main',str(published)],check=True)
            subprocess.run(['git','-C',str(published),'add','.'],check=True)
            subprocess.run(['git','-C',str(published),'-c','user.name=Test','-c','user.email=test@example.invalid',
                            '-c','commit.gpgsign=false','commit','-qm','runtime'],check=True)
            clone=Path(directory)/'clone'
            subprocess.run(['git','clone','-q',str(published),str(clone)],check=True)
            for folder, name in [(self.package,'zip-cmp'),(clone,'clone-cmp')]:
                result=subprocess.run([sys.executable,'-c',code,str(w.root),str(args),name],cwd=folder,
                                      capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
