import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from bfworld.control.broker import Broker

class BrokerTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.b=Broker(self.root,budget=3)
    def tearDown(self):self.tmp.cleanup()
    def test_repeat_commit_and_conflict(self):
        a=self.b.request({'idempotency_key':'same','design':{}});b=self.b.request({'idempotency_key':'same','design':{}})
        self.assertEqual(a['run']['content_hash'],b['run']['content_hash']);self.assertTrue(b['reused_committed_result']);self.assertEqual(self.b.status()['attempts'],1)
        with self.assertRaisesRegex(ValueError,'conflict'):self.b.request({'idempotency_key':'same','design':{'esr_ohm':20}})
    def test_boundaries(self):
        for request in [{'reference':{}},{'design':{'ground_truth':'normal'}},{'profile':'sealed-future'},{'design':{'capacitance_f':float('nan')}}]:
            with self.assertRaises(ValueError):self.b.request({'idempotency_key':'test',**request})
        self.assertEqual(self.b.status()['reserved_experiments'],0)
    def test_budget_is_persistent(self):
        for i in range(3):self.b.request({'idempotency_key':str(i)})
        other=Broker(self.root,budget=999)
        with self.assertRaisesRegex(ValueError,'exhausted'):other.request({'idempotency_key':'extra'})
    def test_no_self_qualification(self):
        r=self.b.request({'idempotency_key':'pass'})
        self.assertFalse(self.b.submit('pass',r['run']['content_hash'])['verified_mission_success'])
        with self.assertRaisesRegex(ValueError,'identity'):self.b.submit('pass','sha256:fake')
    def test_replication_is_distinct(self):
        with self.assertRaises(ValueError):self.b.request({'idempotency_key':'rep','update_type':'replication'})
        a=self.b.request({'idempotency_key':'r1','update_type':'replication','replication_id':'1'})
        b=self.b.request({'idempotency_key':'r2','update_type':'replication','replication_id':'2'})
        self.assertEqual(a['run']['content_hash'],b['run']['content_hash']);self.assertEqual(self.b.status()['reserved_experiments'],2)
    def test_kill_and_recover(self):
        for index,stage in enumerate(('reservation','seal')):
            script='from pathlib import Path;from bfworld.control.broker import Broker;import sys;Broker(Path(sys.argv[1]),3).request({"idempotency_key":sys.argv[2]},crash_at=sys.argv[3])'
            process=subprocess.run([sys.executable,'-c',script,str(self.root),f'kill{index}',stage],timeout=30)
            self.assertEqual(process.returncode,91 if stage=='reservation' else 92)
            recovered=self.b.recover();self.assertEqual(len(recovered),1)
            self.assertEqual(self.b.read(f'kill{index}')['attempts'],1 if stage=='reservation' else 2)
        self.assertEqual(self.b.status()['reserved_experiments'],2)
