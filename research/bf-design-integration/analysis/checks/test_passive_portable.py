"""Synthetic portability checks only; requires installed NumPy, no raw replay."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'passive'
spec = importlib.util.spec_from_file_location('passive', ROOT / 'analyze_passive.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PortableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.archives = self.root / 'archives'
        self.archives.mkdir()
        self.out = self.root / 'output.json'

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self):
        return subprocess.run([sys.executable, '-B', str(ROOT / 'analyze_passive.py'),
            '--archive-dir', str(self.archives), '--out', str(self.out)], capture_output=True, text=True)

    def test_delivered_bytes(self):
        for name, entry in json.loads((ROOT / 'DELIVERY-MANIFEST.json').read_text())['files'].items():
            raw = (ROOT / name).read_bytes()
            self.assertEqual(len(raw), entry['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry['sha256'])

    def test_missing_archives_explicitly_block(self):
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertEqual(json.loads(self.out.read_text())['status'], 'BLOCKED_OR_FAILED')

    def test_corrupt_archive_rejected_before_unpacking(self):
        (self.archives / next(iter(module.ARCHIVES))).write_bytes(b'synthetic invalid archive')
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertIn('SHA mismatch', json.loads(self.out.read_text())['error'])

    def test_existing_output_preserved(self):
        self.out.write_text('original')
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.out.read_text(), 'original')

    def test_output_inside_archive_directory_rejected(self):
        self.out = self.archives / 'output.json'
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertFalse(self.out.exists())

    def test_synthetic_numeric_functions(self):
        self.assertEqual(module.limits([0, 1, -1]), (0, .25))
        self.assertEqual(module.same_numeric([1., 2.], [1., 2.], 'fixture'), 0)
        with self.assertRaises(ValueError):
            module.same_numeric([1, 2], [1], 'shape')

if __name__ == '__main__':
    unittest.main()
