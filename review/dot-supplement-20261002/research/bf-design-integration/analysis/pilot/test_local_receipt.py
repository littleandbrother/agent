import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import check_local_receipt as c

ROOT=Path(__file__).resolve().parent
ARCHIVE=ROOT.parents[3]/'release/evidence/door-design-pilot-v1.zip'
RECEIPT=ROOT/'source-receipts/LOCAL-INTEGRITY-20261001.json'

class LocalReceiptTests(unittest.TestCase):
    def test_crosscheck_and_prior_audit_unchanged(self):
        before=(ROOT/'AUDIT.json').read_bytes()
        report=c.check(ARCHIVE,RECEIPT)
        self.assertEqual(report,json.loads((ROOT/'source-receipts/CROSSCHECK.json').read_text()))
        self.assertEqual((ROOT/'AUDIT.json').read_bytes(),before)
        self.assertFalse(report['raw_artifact_hashes_independently_verified_here'])
        self.assertEqual(report['dataset_count'],1)

    def test_tampered_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_bytes(RECEIPT.read_bytes().replace(b'688230224',b'688230225'))
            with self.assertRaisesRegex(ValueError,'RECEIPT_IDENTITY'):c.check(ARCHIVE,p)

    def test_output_cannot_replace_receipt(self):
        before=RECEIPT.read_bytes()
        r=subprocess.run([sys.executable,'-B',c.__file__,'--archive',str(ARCHIVE),'--receipt',str(RECEIPT),'--out',str(RECEIPT)],capture_output=True)
        self.assertEqual(r.returncode,2);self.assertEqual(RECEIPT.read_bytes(),before)

if __name__=='__main__':unittest.main()
