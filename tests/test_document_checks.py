import importlib.util
import io
import unittest

class DocumentChecksTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('docx'), 'documents extra not installed')
    def test_changed_cell_is_rejected(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.document_checks'))
        from econbiz.document_checks import check_word_content
        from econbiz.word_report import render_word
        from docx import Document
        display = dict(title='检验', created_at='2026-09-16', paragraphs=[], sources=[],
            tables=[dict(title='模型', header=['变量','(1)'], rows=[['x','1.234\n(0.500)']], notes=[], kind='models')])
        raw = render_word(display)
        self.assertEqual(check_word_content(raw, display)['status'], 'passed')
        doc = Document(io.BytesIO(raw))
        doc.tables[0].cell(1,1).text = '9.999'
        stream = io.BytesIO()
        doc.save(stream)
        self.assertEqual(check_word_content(stream.getvalue(), display)['status'], 'failed')

import test_word_report as word_tests
HAS_DOCX = word_tests.HAS_DOCX
from test_execution import HAS_ANALYSIS
from econbiz.state import WorkflowError
from pathlib import Path

@unittest.skipUnless(HAS_ANALYSIS and HAS_DOCX and importlib.util.find_spec('pypdf') and importlib.util.find_spec('PIL'), 'document review extras not installed')
class ReviewTests(unittest.TestCase):
    setUp = word_tests.WordReportTests.setUp
    def test_review_requires_all_pdf_pages_and_bound_docx(self):
        from econbiz import document_checks
        self.assertTrue(hasattr(document_checks, 'record_document_review'))
        from econbiz.word_report import write_word_report
        from pypdf import PdfWriter
        from PIL import Image
        report = write_word_report(self.w, 'word', 'cmp')
        folder = Path(self.temp.name)/'render'; folder.mkdir()
        pdf = PdfWriter(); pdf.add_blank_page(width=100,height=100); pdf.add_blank_page(width=100,height=100)
        with (folder/'report.pdf').open('wb') as f: pdf.write(f)
        for i in (1,2): Image.new('RGB',(20,20),'white').save(folder/f'page-{i}.png')
        files = dict(docx_sha256=report['content']['docx_sha256'], pdf=str(folder/'report.pdf'),
                     pages=[str(folder/f'page-{i}.png') for i in (1,2)])
        review = document_checks.record_document_review
        with self.assertRaises(WorkflowError):
            review(self.w,'review','word',render_files=files,inspected_pages=[1],findings=[],reason='test')
        bad = dict(files, docx_sha256='0'*64)
        with self.assertRaises(WorkflowError):
            review(self.w,'review','word',render_files=bad,inspected_pages=[1,2],findings=[],reason='test')
        a = review(self.w,'review','word',render_files=files,inspected_pages=[1,2],findings=['合成测试发现'],reason='test')
        self.assertEqual(a['content']['visual_check'],'failed')
        self.assertEqual(self.w.project.artifact('word')['content']['visual_check'],'not_performed')
        self.assertEqual(document_checks.read_document_review(self.w,'review'),a)
        self.w.project._state['artifacts']['review']['content']['visual_check']='passed'
        with self.assertRaises(WorkflowError): document_checks.read_document_review(self.w,'review')
        self.w.project._state['artifacts']['review']['content']=a['content']
        self.w.project.mark('r1','completed','failed','test')
        with self.assertRaises(WorkflowError): self.w.project.require_usable('review')

class ExactWordContentTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('docx'),'documents extra not installed')
    def test_unexpected_paragraph_and_reordered_content_fail(self):
        from econbiz.document_checks import check_word_content
        from econbiz.word_report import render_word
        from docx import Document
        display=dict(title='核对',created_at='2026-09-16',tables=[],paragraphs=['说明甲','说明乙'],sources=['来源'])
        raw=render_word(display)
        doc=Document(io.BytesIO(raw)); doc.add_paragraph('虚构系数 999')
        output=io.BytesIO(); doc.save(output)
        self.assertEqual(check_word_content(output.getvalue(),display)['status'],'failed')
