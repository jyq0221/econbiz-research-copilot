import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from econbiz.checkpoints import create_checkpoint, compare_checkpoints, restore_record
from econbiz.files import read_verified
from econbiz.state import WorkflowError
from econbiz.workspace import Workspace


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Workspace.create(Path(self.tmp.name) / 'study', 'study', '合成')
        self.source = Path(self.tmp.name) / 'input.csv'
        self.source.write_bytes(b'x\n1\n')
        self.ws.import_file('data', self.source, role='raw_data', reason='首批')

    def test_restoration_preserves_history_and_marks_downstream_stale(self):
        left = create_checkpoint(self.ws, '首版', '检查点')
        self.source.write_bytes(b'x\n2\n')
        self.ws.import_file('data', self.source, role='raw_data', reason='第二批')
        self.ws.project.add('note', 'note', {}, ['data'])
        self.ws.project.mark('note', 'completed', 'passed', 'saved')
        right = create_checkpoint(self.ws, '第二版', '检查点')
        delta = compare_checkpoints(self.ws, left['id'], right['id'])
        self.assertIn('data', delta['changed'])
        restored = restore_record(self.ws, 'data', 1, '恢复首批')
        self.assertEqual(restored['version'], 3)
        self.assertEqual(read_verified(self.ws.root, restored['files'][0]), b'x\n1\n')
        self.assertEqual(len(self.ws.project.snapshot()['history']['data']), 2)
        self.assertEqual(self.ws.project.artifact('note')['execution_status'], 'stale')
        self.assertEqual(len(list(self.ws.root.glob('data/raw/data/*/input.csv'))), 2)
        self.assertFalse(list((self.ws.root / 'research/history/checkpoints').rglob('*.csv')))

    def test_missing_or_tampered_old_file_blocks_restore(self):
        ref = self.ws.project.artifact('data')['files'][0]
        (self.ws.root / ref['path']).write_bytes(b'changed')
        point = create_checkpoint(self.ws, '损坏', '如实记录')
        self.assertFalse(point['complete'])
        with self.assertRaises(WorkflowError):
            restore_record(self.ws, 'data', 1, '不能恢复')
        (self.ws.root / ref['path']).unlink()
        point = create_checkpoint(self.ws, '缺失', '如实记录')
        self.assertFalse(point['complete'])

    def test_dependency_mismatch_and_invalid_checkpoint(self):
        self.ws.project.add('note', 'note', {}, ['data'])
        self.ws.project.mark('note', 'completed', 'passed', 'saved')
        self.source.write_bytes(b'x\n2\n')
        self.ws.import_file('data', self.source, role='raw_data', reason='更新')
        before = self.ws.project.snapshot()
        with self.assertRaises(WorkflowError):
            restore_record(self.ws, 'note', 1, '旧依赖')
        self.assertEqual(self.ws.project.snapshot(), before)
        point = create_checkpoint(self.ws, '备份', '检查')
        (self.ws.root / point['path']).write_bytes(b'{}')
        with self.assertRaises(WorkflowError):
            compare_checkpoints(self.ws, point['id'], point['id'])

    def test_interrupted_checkpoint_is_not_reported_as_complete(self):
        before = self.ws.project.snapshot()
        with patch('econbiz.checkpoints.write_version', side_effect=WorkflowError('disk full')):
            with self.assertRaises(WorkflowError):
                create_checkpoint(self.ws, '中断', '检查')
        self.assertEqual(self.ws.project.snapshot(), before)
