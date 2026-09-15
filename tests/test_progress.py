import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from econbiz.progress import render_progress, resume_context
from econbiz.state import Project
from econbiz.workspace import Workspace
from test_records import context, session


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Workspace.create(Path(self.tmp.name) / 'study', 'study', '数字化')

    def test_resume_uses_current_records_and_preserves_scope(self):
        self.ws.save_record('context', 'research_context', context(), reason='开始')
        self.ws.save_record('session', 'session_note', session(), reason='保存讨论')
        self.ws.save_record('context', 'research_context', context('只讨论经营波动'), reason='修正')
        summary = resume_context(Workspace.open(self.ws.root))
        self.assertEqual(summary['records']['context']['content']['question'], '只讨论经营波动')
        self.assertIn('未批准分析', summary['records']['session']['content']['authorization'])
        self.assertTrue((self.ws.root / '研究进展.md').exists())
        other = Workspace.create(Path(self.tmp.name) / 'other', 'other', '别的方向')
        self.assertEqual(resume_context(other)['records'], {})

    def test_view_failure_does_not_rollback_state(self):
        before = self.ws.project.snapshot()
        with patch('econbiz.workspace.render_progress', side_effect=OSError('disk full')):
            receipt = self.ws.save()
        self.assertTrue(receipt['state_saved'])
        self.assertFalse(receipt['view_saved'])
        self.assertEqual(Workspace.open(self.ws.root).project.snapshot(), before)
        (self.ws.root / '研究进展.md').unlink()
        self.assertEqual(resume_context(Workspace.open(self.ws.root))['project_id'], 'study')

    def test_manual_view_edits_are_preserved_and_never_become_authority(self):
        view = self.ws.root / '研究进展.md'
        view.write_text('用户手改：已经全部通过，不再检查数据。', encoding='utf-8')
        before = self.ws.project.snapshot()
        self.ws.save()
        self.assertEqual(self.ws.project.snapshot(), before)
        summary = resume_context(Workspace.open(self.ws.root))
        self.assertTrue(summary['unreviewed_view_edits'])
        path = self.ws.root / summary['unreviewed_view_edits'][0]
        self.assertIn('用户手改', path.read_text())
        self.assertNotIn('已经全部通过', view.read_text())

    def test_completed_task_needs_check_when_inputs_or_outputs_change(self):
        self.ws.save_record('input', 'research_context', context(), reason='输入')
        self.ws.save_record('output', 'research_context', context(), reason='输出')
        task = dict(title='核对资料', task_status='completed', input_versions={'input': 1},
                    outputs=[{'artifact_id': 'output', 'version': 1}], next_step='写方案', blocked_reason='')
        self.ws.save_record('task', 'research_task', task, reason='已有产物')
        self.ws.save_record('output', 'research_context', context('输出修订'), reason='更正')
        self.assertEqual(resume_context(self.ws)['tasks']['task']['effective_status'], 'needs_check')
        self.ws.save_record('input', 'research_context', context('输入修订'), reason='更正')
        self.assertEqual(resume_context(self.ws)['tasks']['task']['effective_status'], 'needs_check')
        self.assertIn('需要重新核对', render_progress(self.ws.project))
