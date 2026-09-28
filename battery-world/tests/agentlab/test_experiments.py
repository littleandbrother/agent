import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import asdict
from bfworld.agentlab import experiments as ex
from bfworld.agentlab import programmed as pr
from bfworld.coupled import profiled as v2
from bfworld.coupled.engine import Design,Reference
from bfworld.campaign.sandbox import preflight
from bfworld.agentlab.store import Store,canonical

class Experiments(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def files(self,code=None):return {'design.json':canonical(ex.BASELINE_DESIGN),'policy.py':code or ex.BASELINE_POLICY}
    def test_actual_policy_actions_change_result(self):
        sid=ex.snapshot(self.root,self.files())
        original=ex.run(self.root,'dev-01',sid)
        self.assertEqual(original,ex.run(self.root,'dev-01',sid))
        wait=ex.snapshot(self.root,self.files("def plan(obs): return {'action':'wait','duration_s':1.0}"))
        absent=ex.run(self.root,'dev-01',wait)
        self.assertTrue(original['checks']['delivered']);self.assertFalse(absent['checks']['delivered'])
        self.assertNotEqual(original['bundle_hash'],absent['bundle_hash'])
        self.assertNotIn('ground_truth',canonical(original))
        for d in original['decisions']:
            self.assertNotIn('fault',d['observation']);self.assertNotIn('future',d['observation'])
    def test_original_integrator_parity_for_identical_actions(self):
        def policy(obs):
            if obs['time_s']<.25:return {'action':'wait','duration_s':.25-obs['time_s']}
            return {'action':next(a for a in ['sense','infer','report'] if a not in obs['completed_actions'])}
        new=pr.execute(policy=policy);old=v2.execute()
        for a,b in zip(old['rows'],new['rows']):
            # v3 adds explicit sampled/inferred application states. Every
            # electrical value, interval load, MCU state and delivery stays equal.
            self.assertEqual({k:v for k,v in a.items() if k!='request_state'},
                             {k:v for k,v in b.items() if k!='request_state'})
        self.assertEqual(old['energy_ledger'],new['energy_ledger'])
        self.assertEqual(old['physical_mission_pass'],new['physical_mission_pass'])
        pr.verify(new,reproduce=True)
    def test_snapshot_tamper_and_bad_assets(self):
        sid=ex.snapshot(self.root,self.files())
        (self.root/'snapshots'/sid/'policy.py').chmod(0o644)
        (self.root/'snapshots'/sid/'policy.py').write_text('bad')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):ex.read_snapshot(self.root,sid)
        with self.assertRaises(ValueError):ex.snapshot(self.root,{'model.tflite':'missing'})
        with self.assertRaises(ValueError):ex.read_snapshot(self.root,'../../secret')
    def test_os_boundary(self):
        protected=Path('/Users/depengsu/Documents/bf-agent-workbench/secrets/deepseek.key')
        self.assertTrue(all(preflight(self.root/'worker',protected)['checks'].values()))

class Jobs(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name))
        self.store.grant('alice',['dev-01'],1,99999999999)
        self.store.grant('bob',['dev-01'],1,99999999999)
        self.store.upload('alice','a'*64)
        self.request={'task_id':'dev-01','snapshot_id':'a'*64}
    def tearDown(self):self.tmp.cleanup()
    def test_idempotent_ownership_restart_and_budget(self):
        s=self.store;j=s.enqueue('alice','op',self.request)
        self.assertEqual(j['id'],s.enqueue('alice','op',self.request)['id'])
        with self.assertRaises(ValueError):s.enqueue('alice','op',{**self.request,'snapshot_id':'b'*64})
        with self.assertRaises(PermissionError):s.get('bob',j['id'])
        with self.assertRaises(PermissionError):s.enqueue('bob','op',self.request)
        with self.assertRaisesRegex(ValueError,'BUDGET'):s.enqueue('alice','new',self.request)
        s.update('alice',j['id'],'RUNNING');s.reconcile()
        self.assertEqual('UNKNOWN',s.get('alice',j['id'])['status'])
        self.assertEqual('UNKNOWN',s.enqueue('alice','op',self.request)['status'])
        self.assertFalse(s.cancel('alice',j['id'])['terminal_confirmed'])
    def test_stale_submission(self):
        s=self.store;j=s.enqueue('alice','op',self.request)
        s.update('alice',j['id'],'SUCCEEDED',{'snapshot_id':'a'*64,'run_id':'r','design_status':'FAIL'})
        with self.assertRaises(ValueError):s.submit('alice',j['id'],'b'*64)
        self.assertTrue(s.submit('alice',j['id'],'a'*64)['sealed'])

if __name__=='__main__':unittest.main()
