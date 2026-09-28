import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import io
import contextlib
from pathlib import Path
from unittest.mock import Mock
from bfworld.kernel.canonical import canonical_hash,file_hash,write_canonical_json
from bfworld.campaign.budget import Ledger,BudgetStop
from bfworld.campaign.compiler import compile_candidate
from bfworld.campaign.provider import Provider,MODEL
from bfworld.campaign.repair_bridge import ProviderRepairAdapter,run_provider_repair,check_authority
import bfworld.campaign.repair_bridge as bridge

CTX={'source_family':'rotary','conditions':{'initial_v':2.6,'off_v':1.8,'duration_s':1.6},
     'candidates':[{'id':'a','capacitance_f':.0022,'esr_ohm':4.,'tx_power_w':.036,'start_v':2.35}]}
INITIAL={'schema_version':'world-model-patch-v1','kind':'world-model','scope':{'source_families':['rotary']},'code':'def plan(ctx):\n    pass = True'}
VALID={**INITIAL,'code':"def plan(ctx):\n    return {'scope_ok': False, 'predictions': {}}"}

def fixture_protocol(initial=INITIAL,contexts=None):
    contexts=[CTX] if contexts is None else contexts;module=Path(bridge.__file__)
    p={'status':'owner-approved','paid_dispatch_enabled':True,'task_manifest_hash':'sha256:fixture-only',
       'thresholds':{'fixture':True},'baselines':['fixture-only'],'model_identity':MODEL,
       'success_metric':'isolated transport fixture, no scientific result','statistical_unit':'fixture',
       'candidate_order_rule':'fixture','owner_approval':None,
       'shared_budget':{'ledger':'.bfworld/paid-campaign/cost.sqlite','user_trial_cny':2,'user_total_strictly_less_than_cny':20,
         'reset_or_extension_authorized':False,'new_campaign_execution_window':{'starts_unix_s':time.time()-5,'ends_unix_s':time.time()+600}},
       'repair_execution':{'initial_candidate_hash':canonical_hash(initial),'contexts_hash':canonical_hash(contexts),
         'compiler_hash':file_hash(module.with_name('compiler.py')),'provider_hash':file_hash(module.with_name('provider.py')),
         'ledger_implementation_hash':file_hash(module.with_name('budget.py')),'adapter_hash':file_hash(module),
         'model_fingerprint':'fixture-fingerprint'}}
    p['owner_approval']={'protocol_hash':canonical_hash({k:v for k,v in p.items() if k!='owner_approval'}),'approval_id':'TEST-FIXTURE-NOT-PRODUCTION-AUTHORITY'}
    return p

class FakeTransport(Provider):
    """Uses the actual reserve/settle implementation; never constructs HTTP/key state."""
    def __init__(self,ledger,outputs=None):self.ledger=ledger;self.requests=0;self.outputs=list(outputs or [json.dumps(VALID)]);self.fingerprint='fixture-fingerprint';self.failure=None
    def request(self,path,body=None):
        self.requests+=1
        if self.failure:raise self.failure
        content=self.outputs[min(self.requests-1,len(self.outputs)-1)]
        return {'id':'fixture-call-'+str(self.requests),'model':MODEL,'system_fingerprint':self.fingerprint,
          'usage':{'prompt_tokens':100,'completion_tokens':50,'total_tokens':150},
          'choices':[{'finish_reason':'stop','message':{'content':content}}]}

class RepairBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.repo=Path(self.tmp.name)
        self.ledger=Ledger(self.repo/'.bfworld/paid-campaign/cost.sqlite');self.provider=FakeTransport(self.ledger)
        self.protocol=fixture_protocol()
    def tearDown(self):self.ledger.db.close();self.tmp.cleanup()
    def adapter(self,**kwargs):return ProviderRepairAdapter(self.protocol,self.repo,INITIAL,[CTX],self.provider,self.repo/'adapter','repair-fixture',**kwargs)
    def request(self):
        return {'attempt_id':'fixture-attempt','candidate':INITIAL,'compile_feedback':compile_candidate(INITIAL,[CTX],self.repo/'compile'),
                'repairs_remaining':2,'scientific_feedback':None}
    def test_real_ledger_single_effect_and_cached_parent(self):
        a=self.adapter();r=run_provider_repair(INITIAL,[CTX],self.repo/'parent',a)
        self.assertEqual(r['mechanical_result']['status'],'mechanically-ready');self.assertTrue(r['local_cost_complete'])
        self.assertEqual(self.provider.requests,1);self.assertEqual(self.ledger.summary()['calls'],1)
        self.assertEqual(r['mechanical_result']['cost']['paid_cny'],.00075)
        self.assertEqual(run_provider_repair(INITIAL,[CTX],self.repo/'parent',a),r);self.assertEqual(self.provider.requests,1)
    def test_draft_wrong_pins_expired_window_and_wrong_budget_never_dispatch(self):
        variants=[]
        p=copy.deepcopy(self.protocol);p['status']='draft-not-authorized';variants.append(p)
        p=copy.deepcopy(self.protocol);p['repair_execution']['compiler_hash']='bad';variants.append(p)
        p=copy.deepcopy(self.protocol);p['shared_budget']['new_campaign_execution_window']['ends_unix_s']=1;variants.append(p)
        for p in variants:
            p['owner_approval']['protocol_hash']=canonical_hash({k:v for k,v in p.items() if k!='owner_approval'})
            with self.assertRaises(BudgetStop):check_authority(p,self.repo,INITIAL,[CTX])
        self.assertEqual(self.provider.requests,0);self.assertEqual(self.ledger.summary()['calls'],0)
        self.ledger.max_calls=121
        with self.assertRaises(BudgetStop):self.adapter()
    def test_unknown_reservation_keeps_budget_and_never_retries(self):
        self.provider.failure=BudgetStop('simulated network interruption')
        a=self.adapter();request=self.request()
        with self.assertRaises(BudgetStop):a(request)
        before=self.ledger.summary()
        for callback in (a,a.reconcile):
            with self.assertRaisesRegex(BudgetStop,'uncertain reserved'):callback(request)
        self.assertEqual(self.provider.requests,1);self.assertEqual(self.ledger.summary(),before);self.assertEqual(before['unsettled'],1)
    def test_identity_drift_is_paid_but_not_candidate_admission(self):
        self.provider.fingerprint='unexpected-model-version';a=self.adapter();request=self.request()
        with self.assertRaisesRegex(BudgetStop,'fingerprint drift'):a(request)
        self.assertEqual(self.ledger.summary()['unsettled'],0)
        with self.assertRaises(BudgetStop):a.reconcile(request)
        self.assertEqual(self.provider.requests,1)
    def test_malformed_output_gets_bounded_mechanical_repair_not_science(self):
        self.provider.outputs=['{truncated',json.dumps(VALID)]
        r=run_provider_repair(INITIAL,[CTX],self.repo/'parent',self.adapter())
        self.assertEqual(len(r['mechanical_result']['attempts']),3);self.assertEqual(self.provider.requests,2)
        self.assertFalse(r['scientific_qualified']);self.assertEqual(r['mechanical_result']['scientific_probes'],0)
    def test_reject_scientific_feedback_and_unbound_request(self):
        a=self.adapter();request=self.request();request['scientific_feedback']={'blind_result':'leak'}
        with self.assertRaises(BudgetStop):a(request)
        request=self.request();request['candidate']=VALID
        with self.assertRaises(BudgetStop):a(request)
        self.assertEqual(self.provider.requests,0)
    def test_real_process_exit_after_settlement_recovers_without_second_call(self):
        write_canonical_json(self.repo/'protocol.json',self.protocol)
        script='''import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[2])
sys.path.insert(0,sys.argv[3])
from test_b2_repair_bridge import *
repo=Path(sys.argv[1]);p=json.loads((repo/'protocol.json').read_text())
l=Ledger(repo/'.bfworld/paid-campaign/cost.sqlite');provider=FakeTransport(l)
def fault(stage):
    if stage=='after-settlement':os._exit(71)
a=ProviderRepairAdapter(p,repo,INITIAL,[CTX],provider,repo/'adapter','repair-fixture',fault=fault)
run_provider_repair(INITIAL,[CTX],repo/'parent',a)
'''
        proc=subprocess.run([sys.executable,'-c',script,str(self.repo),str(Path(__file__).parent),str(Path(bridge.__file__).parents[2])],capture_output=True,text=True)
        self.assertEqual(proc.returncode,71,proc.stderr)
        before=self.ledger.summary();self.assertEqual(before['calls'],1);self.assertEqual(before['unsettled'],0)
        self.provider.request=Mock(side_effect=AssertionError('duplicate external effect'))
        recovered=run_provider_repair(INITIAL,[CTX],self.repo/'parent',self.adapter())
        self.assertEqual(recovered['mechanical_result']['status'],'mechanically-ready')
        self.assertFalse(recovered['local_cost_complete']);self.assertEqual(self.ledger.summary(),before)
        self.assertEqual(run_provider_repair(INITIAL,[CTX],self.repo/'parent',self.adapter()),recovered)
    def test_settled_reconciliation_does_not_need_a_new_window(self):
        a=self.adapter();request=self.request();first=a(request)
        # Same pinned protocol, time has passed. No new authorization is manufactured.
        from unittest.mock import patch
        with patch('bfworld.campaign.repair_bridge.time.time',return_value=time.time()+99999):
            self.assertEqual(a.reconcile(request),first)
            self.assertEqual(a(request),first)
        self.assertEqual(self.provider.requests,1)
    def test_rehashed_parent_cost_tamper_is_rejected_by_ledger_reconciliation(self):
        a=self.adapter();run_provider_repair(INITIAL,[CTX],self.repo/'parent',a)
        path=self.repo/'parent/replacement-0.json';r=json.loads(path.read_text())
        r['cost_receipt']['paid_cny']=0.;r.pop('content_hash');r['content_hash']=canonical_hash(r);write_canonical_json(path,r)
        with self.assertRaisesRegex(BudgetStop,'settled provider receipt'):run_provider_repair(INITIAL,[CTX],self.repo/'parent',a)
        self.assertEqual(self.provider.requests,1)
    def test_known_no_reservation_can_resume_but_cost_uncertainty_remains(self):
        def stop(stage):
            if stage=='before-provider':raise RuntimeError('before-reservation interruption')
        with self.assertRaises(RuntimeError):run_provider_repair(INITIAL,[CTX],self.repo/'parent',self.adapter(fault=stop))
        self.assertEqual(self.ledger.summary()['calls'],0)
        r=run_provider_repair(INITIAL,[CTX],self.repo/'parent',self.adapter())
        self.assertEqual(self.provider.requests,1);self.assertFalse(r['local_cost_complete'])
    def test_cli_draft_gate_precedes_any_credential_or_output_access(self):
        initial=self.repo/'initial.json';contexts=self.repo/'contexts.json'
        write_canonical_json(initial,INITIAL);write_canonical_json(contexts,[CTX])
        script=Path(__file__).resolve().parents[2]/'scripts/run_b2_repair.py'
        proc=subprocess.run([sys.executable,str(script),'--initial',str(initial),'--contexts',str(contexts),
            '--trial-id','unpaid-negative','--output',str(self.repo/'no-output'),'--execute',
            '--key-file',str(self.repo/'credential-does-not-exist')],capture_output=True,text=True)
        self.assertEqual(proc.returncode,2,proc.stderr)
        data=json.loads(proc.stdout);self.assertEqual(data['status'],'not-authorized');self.assertFalse(data['credentials_loaded'])
        self.assertFalse((self.repo/'no-output').exists())
    def test_reconcile_cli_uses_readonly_ledger_and_no_credentials(self):
        scripts=Path(__file__).resolve().parents[2]/'scripts';sys.path.insert(0,str(scripts))
        import run_b2_repair as cli
        output=self.repo/'cli-output'
        a=ProviderRepairAdapter(self.protocol,self.repo,INITIAL,[CTX],self.provider,output/'provider','repair-fixture')
        expected=run_provider_repair(INITIAL,[CTX],output/'repair',a)
        for name,obj in [('protocol.json',self.protocol),('initial.json',INITIAL),('contexts.json',[CTX])]:write_canonical_json(self.repo/name,obj)
        before=file_hash(self.repo/'.bfworld/paid-campaign/cost.sqlite')
        argv=['run_b2_repair','--protocol',str(self.repo/'protocol.json'),'--initial',str(self.repo/'initial.json'),
            '--contexts',str(self.repo/'contexts.json'),'--trial-id','repair-fixture','--output',str(output),'--reconcile-only']
        from unittest.mock import patch
        stream=io.StringIO()
        with patch.object(cli,'REPO',self.repo),patch.object(sys,'argv',argv),contextlib.redirect_stdout(stream):
            self.assertEqual(cli.main(),0)
        self.assertEqual(json.loads(stream.getvalue())['result_hash'],expected['content_hash'])
        self.assertEqual(file_hash(self.repo/'.bfworld/paid-campaign/cost.sqlite'),before)

if __name__=='__main__':unittest.main()
