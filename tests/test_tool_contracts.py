import re
import unittest
from pathlib import Path


class ToolContractTests(unittest.TestCase):
    def test_documented_examples_execute_and_restore_real_bytes(self):
        path = Path(__file__).resolve().parents[1] / 'docs/developer/tool-contract-examples.md'
        content = path.read_text('utf-8')
        namespace = {}
        try:
            blocks = re.findall(r'```python\n(.*?)\n```', content, flags=re.S)
            self.assertGreaterEqual(len(blocks), 8)
            for block in blocks:
                exec(compile(block, str(path), 'exec'), namespace)
            self.assertEqual(namespace['restored']['version'], 3)
            self.assertTrue(namespace['receipt']['state_saved'])
            self.assertEqual(namespace['summary']['project_id'], 'synthetic')
        finally:
            if 'temporary' in namespace:
                namespace['temporary'].cleanup()
