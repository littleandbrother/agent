import copy
import json
import unittest
from pathlib import Path
from bfworld.campaign.audit import audit
from bfworld.kernel.canonical import canonical_hash
class AuditTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  p=Path(__file__).resolve().parents[2]/'docs/campaign/report.json'
  if not p.exists():raise unittest.SkipTest('Paid pilot not run; unit tests never make model calls')
  cls.report=json.loads(p.read_text())
 def modified(self):return copy.deepcopy(self.report)
 def reseal(self,r):r.pop('content_hash');r['content_hash']=canonical_hash(r)
 def test_report_recomputes(self):self.assertEqual(audit(self.report)['status'],'pass')
 def test_cost_tamper(self):
  r=self.modified();r['budget']['accounted_upper_bound_cny']=0;self.reseal(r)
  with self.assertRaises(ValueError):audit(r)
 def test_false_success_tamper(self):
  r=self.modified();r['outcomes'][0]['computational_verified_success']=not r['outcomes'][0]['computational_verified_success'];self.reseal(r)
  with self.assertRaises(ValueError):audit(r)
 def test_unqualified_program_injection(self):
  r=self.modified();t=r['trials'][0];t['program_used']=True;self.reseal(t);self.reseal(r)
  with self.assertRaises(ValueError):audit(r)
