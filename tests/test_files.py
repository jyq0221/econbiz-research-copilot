import tempfile
import unittest
from pathlib import Path

from econbiz.files import describe_file, read_verified, write_version
from econbiz.state import Project, WorkflowError


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / '研究 项目'
        self.root.mkdir()
        self.source = self.root / 'input.csv'
        self.source.write_bytes(b'firm,year,x\na,2024,1\n')

    def test_move_and_content_check(self):
        ref = describe_file(self.root, self.source, scope='project', role='raw_data')
        moved = self.root.rename(self.root.parent / '新的位置')
        self.assertEqual(read_verified(moved, ref), b'firm,year,x\na,2024,1\n')
        (moved / 'input.csv').write_bytes(b'changed')
        with self.assertRaises(WorkflowError):
            read_verified(moved, ref)
        (moved / 'input.csv').unlink()
        with self.assertRaises(WorkflowError):
            read_verified(moved, ref)

    def test_external_and_escape(self):
        outside = self.root.parent / 'outside.csv'
        outside.write_bytes(b'x\n1\n')
        ref = describe_file(self.root, outside, scope='external', role='raw_data')
        self.assertEqual(read_verified(self.root, ref), b'x\n1\n')
        (self.root / 'link').symlink_to(outside)
        for path in (outside, self.root / 'link', '../outside.csv'):
            with self.assertRaises(WorkflowError):
                describe_file(self.root, path, scope='project', role='raw_data')
        with self.assertRaises(WorkflowError):
            describe_file(self.root, 'input.csv', scope='external', role='raw_data')

    def test_version_write_is_immutable_and_retryable(self):
        path = write_version(self.root, 'data/raw/a/v0001/input.csv', b'one')
        self.assertEqual(write_version(self.root, 'data/raw/a/v0001/input.csv', b'one'), path)
        with self.assertRaises(WorkflowError):
            write_version(self.root, 'data/raw/a/v0001/input.csv', b'two')
        self.assertEqual(path.read_bytes(), b'one')
        with self.assertRaises(WorkflowError):
            write_version(self.root, '../escape', b'x')

    def test_project_roundtrip_clone_history_and_portable_inventory(self):
        ref = describe_file(self.root, self.source, scope='project', role='raw_data')
        p = Project.create('study', '方向', base_dir=self.root)
        p.add('data', 'inventory', {'input_ref': ref, 'input_sha256': ref['sha256']}, files=[ref])
        p.mark('data', 'completed', 'passed', '结构核查')
        p.save(self.root / 'research_state.json')
        p = Project.load(self.root / 'research_state.json').clone()
        self.assertEqual(p.read_inventory_bytes('data'), self.source.read_bytes())
        p.revise('data', {'input_ref': ref}, '说明更正')
        self.assertEqual(p.version('data', 1)['files'], [ref])
        for version in (0, 3, True):
            with self.assertRaises(WorkflowError):
                p.version('data', version)
        damaged = p.snapshot()
        damaged['history']['data'][0]['files'][0]['size_bytes'] = -1
        with self.assertRaises(WorkflowError):
            Project(damaged)

    def test_dependencies_are_transactional_and_can_be_rebound(self):
        p = Project.create('study', '方向')
        for key in ('a', 'b'):
            p.add(key, 'note', {})
            p.mark(key, 'completed', 'passed', 'saved')
        p.add('child', 'note', {}, ['a'])
        p.mark('child', 'completed', 'passed', 'saved')
        before = p.snapshot()
        for deps in (['missing'], ['a', 'a'], ['child']):
            with self.assertRaises(WorkflowError):
                p.revise('child', {}, 'changed', dependencies=deps)
            self.assertEqual(p.snapshot(), before)
        with self.assertRaises(WorkflowError):
            p.revise('a', {}, 'cycle', dependencies=['child'])
        self.assertEqual(p.snapshot(), before)
        p.revise('child', {}, 'rebound', dependencies=['b'])
        self.assertEqual(p.artifact('child')['dependencies'], {'b': 1})
        self.assertEqual(p.version('child', 1)['dependencies'], {'a': 1})
