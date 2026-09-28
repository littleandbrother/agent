import copy
import tempfile
import unittest
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from bfworld.kernel.canonical import canonical_hash
from bfworld.coupled.engine import Design,Reference
from bfworld.coupled.profiled import LoadProfile,VERSION as REF_VERSION
from bfworld.campaign.task_context import physics_for,public_context
from bfworld.campaign.splits import task_record
from bfworld.campaign.compiler import compile_candidate
from bfworld.campaign.scientific import VERSION,execute_qualification,public_feedback,component_receipt

CODE='''def plan(ctx):
    if not isinstance(ctx,dict) or ctx.get('source_family') != 'rotary' or not isinstance(ctx.get('conditions'),dict) or not ctx.get('candidates'):
        return {'scope_ok':False,'predictions':{}}
    return {'scope_ok':True,'predictions':{c['id']:{'verdict':'feasible' if c['capacitance_f']>=.0022 else 'infeasible'} for c in ctx['candidates']}}
'''

def fixture():
    designs={'small':replace(Design(),capacitance_f=.00033,esr_ohm=18),'large':Design()}
    a=task_record('explain-fixture','development',physics_for(designs,Reference(),LoadProfile()),prior_exposure='public')
    b=task_record('use-fixture','development',physics_for(designs,replace(Reference(),source_phase_rad=1.57),LoadProfile()),prior_exposure='public')
    r=task_record('regression-fixture','regression',a['physics'],prior_exposure='public',regression_of=a['task_id'])
    tasks=[a,b,r];c=public_context(a);c['source_family']='solar'
    plan={'schema_version':VERSION,'purpose':'engineering-controls','task_manifest_hash':canonical_hash(tasks),'reference_version':REF_VERSION,
        'explanation_ids':[a['task_id']],'use_ids':[b['task_id']],'regression_ids':[r['task_id']],
        'thresholds':{'min_agreement':1.,'min_coverage':1.,'max_false_feasible':0,'min_median_probe_reduction':1.,'retain_all_solvable':True},
        'candidate_order_rule':'stable-capacitance-ascending','regression_probe_ceiling':{r['task_id']:1},
        'oos_contexts':[c],'max_reference_runs':6,'max_predictor_calls':4,'exposed_environment_hashes':[]}
    candidate={'schema_version':'world-model-patch-v1','kind':'world-model','scope':{'source_families':['rotary']},'code':CODE}
    return tasks,plan,candidate

class ScientificTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.tasks,self.plan,self.candidate=fixture()
    def tearDown(self):self.tmp.cleanup()
    def run_fixture(self,**kw):
        c=kw.pop('candidate',self.candidate)
        kw.setdefault('acquisition_cost_complete',True) # explicit hand-authored unpaid fixture
        m=compile_candidate(c,[public_context(self.tasks[0])],self.root/'compile')
        return execute_qualification(c,m,self.tasks,self.plan,self.root/'qualification',**kw)
    def test_complete_control_is_never_promoted_as_scientific_knowledge(self):
        r=self.run_fixture();self.assertTrue(r['controls_pass'],r['checks']);self.assertFalse(r['qualified'])
        self.assertFalse(r['blind_transfer']);self.assertFalse(r['agent_use_benefit_measured'])
        self.assertEqual(r['cost']['reference_runs'],6);self.assertEqual(r['cost']['predictor_calls'],4)
        self.assertEqual(r,self.run_fixture(observer=Mock(side_effect=AssertionError('cached execution'))))
    def test_mechanical_and_incomplete_cost_fail_before_reference(self):
        observer=Mock(side_effect=AssertionError('reference reached'))
        r=self.run_fixture(candidate={**self.candidate,'code':'bad syntax'},observer=observer)
        self.assertFalse(r['qualified']);self.assertEqual(r['cost']['reference_runs'],0);observer.assert_not_called()
        m=compile_candidate(self.candidate,[public_context(self.tasks[0])],self.root/'compile')
        r=execute_qualification(self.candidate,m,self.tasks,self.plan,self.root/'cost-negative',acquisition_cost_complete=False,observer=observer)
        self.assertFalse(r['controls_pass']);self.assertEqual(r['cost']['reference_runs'],0)
    def test_false_feasible_and_abstain_controls_fail(self):
        for name,code in [('false',CODE.replace("c['capacitance_f']>=.0022","True")),('abstain',"def plan(ctx):\n    return {'scope_ok':False,'predictions':{}}")]:
            c={**self.candidate,'code':code};m=compile_candidate(c,[public_context(self.tasks[0])],self.root/'compile')
            r=execute_qualification(c,m,self.tasks,self.plan,self.root/name,acquisition_cost_complete=True)
            self.assertFalse(r['checks']['explanation']);self.assertFalse(r['qualified'])
        self.assertEqual(r['metrics']['coverage'],0)
    def test_regression_ceiling_is_independent_of_use_gain(self):
        self.plan['regression_probe_ceiling']['regression-fixture']=0
        r=self.run_fixture();self.assertTrue(r['checks']['use']);self.assertFalse(r['checks']['regression'])
    def test_formal_observed_and_blind_tasks_cannot_be_laundered(self):
        self.plan['purpose']='formal-qualification'
        with self.assertRaisesRegex(ValueError,'owner-approved'):self.run_fixture()
        self.tasks,self.plan,self.candidate=fixture()
        p=physics_for({'x':Design()},replace(Reference(),source_phase_rad=.9),LoadProfile())
        blind=task_record('blind-fixture','blind-transfer',p)
        self.tasks.append(blind);self.plan['task_manifest_hash']=canonical_hash(self.tasks);self.plan['use_ids']=['blind-fixture']
        with self.assertRaisesRegex(ValueError,'blind'):self.run_fixture()
    def test_feedback_excludes_regression_and_scope(self):
        r=self.run_fixture();feedback=public_feedback(r,self.tasks)
        self.assertEqual(len(feedback['feedback']),4)
        self.assertEqual({x['task_id'] for x in feedback['feedback']},{'explain-fixture','use-fixture'})
    def test_missing_threshold_budget_and_changed_plan_stop(self):
        self.plan['thresholds'].pop('min_coverage')
        with self.assertRaises(ValueError):self.run_fixture()
        self.tasks,self.plan,self.candidate=fixture();self.plan['max_reference_runs']=1
        with self.assertRaisesRegex(ValueError,'reference budget'):self.run_fixture()
    def test_interruption_retains_cost_uncertainty_instead_of_reexecuting(self):
        with self.assertRaisesRegex(RuntimeError,'interruption'):
            self.run_fixture(observer=Mock(side_effect=RuntimeError('injected interruption')))
        with self.assertRaisesRegex(RuntimeError,'incomplete local cost'):self.run_fixture()
    def test_provider_to_scientific_receipt_and_independent_activation(self):
        sys.path.insert(0,str(Path(__file__).parent))
        from test_b2_repair_bridge import INITIAL,FakeTransport,fixture_protocol
        from bfworld.campaign.budget import Ledger
        from bfworld.campaign.repair_bridge import ProviderRepairAdapter,run_provider_repair
        from bfworld.campaign.qualification import qualify_workflow,activated_components
        import json
        ctx=[public_context(self.tasks[0])];protocol=fixture_protocol(INITIAL,ctx)
        ledger=Ledger(self.root/'.bfworld/paid-campaign/cost.sqlite')
        try:
            fake=FakeTransport(ledger,[json.dumps(self.candidate)])
            adapter=ProviderRepairAdapter(protocol,self.root,INITIAL,ctx,fake,self.root/'provider','integration-fixture')
            repaired=run_provider_repair(INITIAL,ctx,self.root/'repair',adapter)
            candidate=repaired['mechanical_result']['final_candidate'];mechanical=repaired['mechanical_result']['attempts'][-1]['compile']
            report=execute_qualification(candidate,mechanical,self.tasks,self.plan,self.root/'science',acquisition_cost_complete=repaired['local_cost_complete'])
            self.assertTrue(report['controls_pass']);world_receipt=component_receipt(report,candidate)
            self.assertFalse(world_receipt['passed']) # engineering controls are not qualification
            workflow={'schema_version':'harness-patch-v1','kind':'workflow','policy':{'order_by':'capacitance_f','descending':False,'require_transient_before_submit':True,'stop_after_verified':True}}
            active=activated_components(candidate,world_receipt,workflow,qualify_workflow(workflow))
            self.assertIsNone(active['world-model']);self.assertEqual(active['workflow'],workflow)
            self.assertEqual(fake.requests,1);self.assertFalse(world_receipt['transfer_validated'])
            bad=copy.deepcopy(report);bad['qualified']=True;bad.pop('content_hash');bad['content_hash']=canonical_hash(bad)
            with self.assertRaises(ValueError):component_receipt(bad,candidate)
        finally:ledger.db.close()

if __name__=='__main__':unittest.main()
