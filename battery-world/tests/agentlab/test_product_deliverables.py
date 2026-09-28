"""Run source-bound product projection checks as part of the application gate."""
from pathlib import Path
import shutil
import subprocess
import unittest

class ProductDeliverablesTests(unittest.TestCase):
    def test_product_projection_boundaries(self):
        root = Path(__file__).resolve().parents[2]
        node = shutil.which('node')
        self.assertIsNotNone(node)
        result = subprocess.run([node, '--test', 'tests/agentlab/test_product_graph.cjs',
                                 'tests/agentlab/test_product_deliverables.cjs'],
                                cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
