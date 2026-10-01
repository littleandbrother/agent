"""Offline negative controls; synthetic archives and one retained-archive replay."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
import warnings
import audit_pilot as p

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def archive(self, manifest_hash=None, extra=False):
        path = self.root / 'tiny.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('data', b'fixture')
            z.writestr('manifest.json', json.dumps({'data': manifest_hash or p.sha(b'fixture')}))
            if extra:
                z.writestr('unlisted', b'extra')
        return path

    def test_corrupt_external_archive_hash(self):
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_SHA'):
            p.Archive(self.archive())

    def test_manifest_hash_and_member_set(self):
        path = self.archive('0'*64)
        with self.assertRaisesRegex(ValueError, 'MEMBER_HASH'):
            p.Archive(path, p.sha(path.read_bytes()))
        path = self.archive(extra=True)
        with self.assertRaisesRegex(ValueError, 'MEMBER_SET'):
            p.Archive(path, p.sha(path.read_bytes()))

    def test_duplicate_and_traversal_members(self):
        for name in ['../outside', '/absolute']:
            path = self.root / 'unsafe.zip'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr(name, b'x')
            with self.assertRaisesRegex(ValueError, 'UNSAFE_MEMBER'):
                p.Archive(path, p.sha(path.read_bytes()))

    def test_duplicate_member_rejected(self):
        path = self.root / 'duplicate.zip'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('same', b'a')
                z.writestr('same', b'b')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_MEMBER'):
            p.Archive(path, p.sha(path.read_bytes()))

    def test_cold_grid_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'COLD_TIME'):
            p.relative_channels({'time_s':[0,1],'x':[1,2]}, {'time_s':[0,2],'x':[1,2]})

    def test_cold_channel_difference(self):
        self.assertEqual(p.relative_channels({'time_s':[0,1],'x':[1,2]}, {'time_s':[0,1],'x':[1,3]}), {'x':.5})

    def test_existing_output_preserved(self):
        out = self.root/'existing.json'
        out.write_text('original')
        r = subprocess.run([sys.executable,'-B',p.__file__,'--archive',str(self.archive()),'--out',str(out)],capture_output=True)
        self.assertEqual(r.returncode,2)
        self.assertEqual(out.read_text(),'original')

    def test_missing_archive_yields_blocked_report(self):
        out = self.root/'new.json'
        r = subprocess.run([sys.executable,'-B',p.__file__,'--archive',str(self.root/'absent'),'--out',str(out)],capture_output=True)
        self.assertEqual(r.returncode,1)
        self.assertEqual(json.loads(out.read_text())['status'],'BLOCKED_OR_FAILED')

    def test_retained_archive_and_committed_report(self):
        repo = Path(__file__).resolve().parents[4]
        report = p.audit(repo/'release/evidence/door-design-pilot-v1.zip')
        self.assertEqual(report,json.loads(Path(__file__).with_name('AUDIT.json').read_text()))
        self.assertEqual(report['cohort']['all_attempt_statuses'],{'completed':10,'out_of_domain':4,'tool_fail':3})
        self.assertFalse(report['missing_artifacts']['hash_verified'])
        self.assertEqual(report['runs']['gap40']['observed_channels'],'MISSING_RESULT_AND_RAW')
        self.assertEqual(report['execution']['new_trajectories'],0)

if __name__=='__main__':
    unittest.main()
