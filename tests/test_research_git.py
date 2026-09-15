import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from econbiz.research_git import enable_git, preview_changes, commit_changes
from econbiz.state import WorkflowError
from econbiz.workspace import Workspace


@unittest.skipUnless(shutil.which('git'), 'Git is unavailable')
class ResearchGitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tool = Path(self.tmp.name) / 'tool'
        self.tool.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.tool)], check=True)
        self.ws = Workspace.create(self.tool / 'research-projects' / 'study', 'study', '合成')
        self.code = self.ws.path('research_code') / 'analysis.py'
        self.code.parent.mkdir(parents=True)
        self.code.write_text('print("synthetic")\n')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.ws.root), *args], capture_output=True, text=True, check=True).stdout.strip()

    def enable(self):
        enable_git(self.ws, ['research/code'])
        self.git('config', '--local', 'user.name', 'Synthetic Test')
        self.git('config', '--local', 'user.email', 'synthetic@example.invalid')

    def test_commit_cannot_fall_back_to_parent_tool_repository(self):
        with self.assertRaises(WorkflowError):
            commit_changes(self.ws, ['research/code/analysis.py'], '不能提交到父仓库')
        staged = subprocess.run(['git', '-C', str(self.tool), 'diff', '--cached', '--name-only'], capture_output=True, text=True)
        self.assertEqual(staged.stdout, '')

    def test_explicit_paths_and_literal_message(self):
        self.enable()
        preview = preview_changes(self.ws, ['research/code'])
        self.assertEqual(preview['paths'], ['research/code/analysis.py'])
        result = commit_changes(self.ws, ['research/code/analysis.py'], '测试 $(touch malicious) `command`')
        self.assertTrue(result['committed'])
        self.assertEqual(self.git('ls-files'), 'research/code/analysis.py')
        self.assertEqual(self.git('remote'), '')
        self.assertFalse((self.ws.root / 'malicious').exists())

    def test_existing_staging_and_out_of_scope_are_rejected(self):
        self.enable()
        unrelated = self.ws.root / 'unrelated.txt'
        unrelated.write_text('user file')
        self.git('add', '--', 'unrelated.txt')
        with self.assertRaises(WorkflowError):
            commit_changes(self.ws, ['research/code/analysis.py'], '不能带入其他内容')
        self.assertEqual(self.git('diff', '--cached', '--name-only'), 'unrelated.txt')
        for path in ('../escape', 'research_state.json', 'data/raw', '.'):
            with self.assertRaises(WorkflowError):
                preview_changes(self.ws, [path])

    def test_raw_files_secret_and_symlink_ranges_are_rejected(self):
        for paths in (['data/raw'], ['literature/sources'], ['.git'], ['research/code/.env']):
            with self.assertRaises(WorkflowError):
                enable_git(self.ws, paths)
        self.enable()
        (self.code.parent / 'linked.py').symlink_to(self.tool / '.git/config')
        with self.assertRaises(WorkflowError):
            preview_changes(self.ws, ['research/code'])

    def test_missing_git_does_not_prevent_local_history(self):
        with patch('econbiz.research_git.shutil.which', return_value=None):
            with self.assertRaises(WorkflowError):
                enable_git(self.ws, ['research/code'])
        self.assertTrue(self.ws.save()['state_saved'])

    def test_identity_failure_leaves_index_empty(self):
        self.enable()
        self.git('config', '--local', 'user.name', '')
        self.git('config', '--local', 'user.email', '')
        with self.assertRaises(WorkflowError):
            commit_changes(self.ws, ['research/code/analysis.py'], '缺身份')
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')

    def test_pattern_characters_in_filename_do_not_expand_scope(self):
        selected = self.code.parent / 'analysis[1].py'
        unrelated = self.code.parent / 'analysis1.py'
        selected.write_text('selected = True\n')
        unrelated.write_text('unrelated = True\n')
        path = 'research/code/analysis[1].py'
        enable_git(self.ws, [path])
        self.git('config', '--local', 'user.name', 'Synthetic Test')
        self.git('config', '--local', 'user.email', 'synthetic@example.invalid')
        self.assertEqual(preview_changes(self.ws, [path])['paths'], [path])
        commit_changes(self.ws, [path], '仅提交指定文件')
        self.assertEqual(self.git('ls-files').splitlines(), [path])
