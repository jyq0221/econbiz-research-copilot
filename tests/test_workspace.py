import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from econbiz.files import read_verified
from econbiz.state import Project, WorkflowError
from econbiz.workspace import Workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / '研究 项目'
        self.source = Path(self.tmp.name) / 'panel.csv'
        self.source.write_bytes(b'firm,year,x\na,2024,1\n')
        self.ws = Workspace.create(self.root, 'study', '合成方向')

    def test_versions_and_move(self):
        first = self.ws.import_file('panel', self.source, role='raw_data', reason='首批')
        self.source.write_bytes(b'firm,year,x\na,2024,2\n')
        second = self.ws.import_file('panel', self.source, role='raw_data', reason='第二批')
        self.ws.audit('inventory', 'panel', entity='firm', time='year', numeric=['x'])
        moved = self.root.rename(self.root.parent / '移动后')
        ws = Workspace.open(moved)
        self.assertEqual(read_verified(ws.root, ws.project.version('panel', 1)['files'][0]), b'firm,year,x\na,2024,1\n')
        self.assertEqual(read_verified(ws.root, second['files'][0]), self.source.read_bytes())
        self.assertEqual(ws.project.read_inventory_bytes('inventory'), self.source.read_bytes())
        self.assertEqual(first['version'], 1)
        for folder in ('literature', 'data', 'research'):
            self.assertTrue((moved / folder).is_dir())
        with self.assertRaises(WorkflowError):
            Workspace.create(moved, 'study', '拒绝覆盖')

    def test_import_failure_preserves_authority_and_retries(self):
        before = self.ws.project.snapshot()
        with patch('econbiz.state.write_json', side_effect=OSError('disk full')):
            with self.assertRaises(WorkflowError):
                self.ws.import_file('panel', self.source, role='raw_data', reason='首批')
        self.assertEqual(Workspace.open(self.root).project.snapshot(), before)
        self.assertEqual(self.ws.project.snapshot(), before)
        self.assertTrue(list(self.root.glob('data/raw/panel/v0001/*')))
        self.assertEqual(self.ws.import_file('panel', self.source, role='raw_data', reason='重试')['version'], 1)

    def test_failed_audit_and_source_change_invalidate(self):
        self.ws.import_file('panel', self.source, role='raw_data', reason='首批')
        good = self.ws.audit('inventory', 'panel', entity='firm', time='year', numeric=['x'])
        self.assertEqual(good['check_status'], 'passed')
        self.source.write_bytes(b'firm,year,x\na,2024,1\na,2024,2\n')
        self.ws.import_file('panel', self.source, role='raw_data', reason='第二批')
        with self.assertRaises(WorkflowError):
            self.ws.project.require_usable('inventory')
        bad = self.ws.audit('inventory', 'panel', entity='firm', time='year', numeric=['x'])
        self.assertEqual(bad['check_status'], 'failed')
        self.assertTrue(bad['files'])
        self.assertEqual(Workspace.open(self.root).project.artifact('inventory')['version'], 2)

    def test_legacy_open_does_not_move_or_hide_corruption(self):
        old = self.root.parent / 'old'
        old.mkdir()
        (old / 'reports').mkdir()
        Project.create('old', '历史').save(old / 'research_state.json')
        ws = Workspace.open(old)
        self.assertEqual(ws.path('research_reports'), (old / 'reports').resolve())
        self.assertFalse((old / 'research').exists())
        (old / 'research_state.json').write_text('{bad', encoding='utf-8')
        with self.assertRaises(WorkflowError):
            Workspace.open(old)
        self.assertEqual((old / 'research_state.json').read_text(), '{bad')

    def test_external_relocation_requires_identical_content(self):
        self.ws.import_file('panel', self.source.resolve(), role='raw_data', copy=False, reason='外部索引')
        moved = self.source.rename(self.source.parent / 'moved.csv')
        self.ws.relocate_source('panel', moved.resolve(), reason='移动来源')
        self.ws.project.require_usable('panel')
        moved.write_bytes(b'new')
        with self.assertRaises(WorkflowError):
            self.ws.relocate_source('panel', moved.resolve(), reason='不能当作移动')

    def test_invalid_import_and_escaped_layout_write_nothing(self):
        before = self.ws.project.snapshot()
        with self.assertRaises(WorkflowError):
            self.ws.import_file('../bad', self.source, role='raw_data', reason='bad')
        self.assertEqual(self.ws.project.snapshot(), before)
        outside = self.root.parent / 'outside'
        outside.mkdir()
        (self.root / 'data' / 'raw').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(WorkflowError):
            self.ws.import_file('panel', self.source, role='raw_data', reason='bad')
        self.assertEqual(list(outside.iterdir()), [])
