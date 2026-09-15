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
        for prefix in ('tests/', 'examples/', 'scripts/', '.github/', 'docs/developer/', 'docs/superpowers/'):
            with self.subTest(prefix=prefix):
                self.assertFalse(any(name.startswith(prefix) for name in self.names), prefix)
        self.assertNotIn('docs/research-handbook/teaching-cases.md', self.names)
        self.assertNotIn('docs/agent-entry-validation.md', self.names)
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
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=self.package,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), {'question': '已保存的材料能否独立接续？', 'view': True})
