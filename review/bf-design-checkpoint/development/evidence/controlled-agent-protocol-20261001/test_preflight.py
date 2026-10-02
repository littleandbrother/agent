import copy
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unittest
from preflight import *

ROOT = Path(__file__).resolve().parent

def H(s): return digest(s)

def complete_contract():
    """Synthetic populated contract; never a real qualification or authority."""
    model = dict(provider='synthetic', model_id='fixture', revision='fixture-v1',
                 fingerprint='fixture', reasoning='fixed', seed_policy='paired',
                 context_tokens=100, vision=False, temperature=0)
    budget = {k:1 for k in DIMENSIONS}; budget['currency']='USD'
    common = dict(model=model, facts_hash=H('facts'), history_hash=H('history'),
        tools_hash=H('tools'), retrieval_hash=H('retrieval'), clarifications_hash=H('clarifications'),
        edit_freedoms=sorted(FREEDOMS), budget=budget, selection_rule='last_public_submission',
        task_order_hash=H('order'), harness_frozen_during_episode=True)
    arms=[dict(common,id='strong_generic',harness_hash=H('generic'),intervention_hash=H('generic-intervention')),
          dict(common,id='bf_design',harness_hash=H('bf'),intervention_hash=H('bf-intervention'))]
    p = dict(schema_version=SCHEMA,status='prospective-owner-frozen',model=model,
        per_episode_budget=budget,global_budget_ledger_id='fixture-only',global_money_cap=100,
        unsettled_costs=0,assigned_episodes=['episode-1','episode-2'],
        denominator='all_assigned_episodes_including_failures_and_retries',
        task_manifest_hash=H('tasks'),world_id=H('world'),facts_hash=H('facts'),
        evaluator_hash=H('evaluator'),holdout_manifest_hash=H('holdout'),
        analysis_plan_hash=H('analysis'),reuse_source_manifest_hash=H('source'),
        world_freeze_receipt=dict(world_id=H('world'),requirements_owner_frozen=True,formal_trial_admitted=True),
        no_agent_reference=dict(world_id=H('world'),task_manifest_hash=H('tasks'),sealed=True,
            independently_feasible=True,required_acceptance_gates_passed=True,receipt_hash=H('reference'),
            evidence_kind='independent-computational-reference'),
        runtime=dict(runtime_id='fixture',platform='fixture',isolation_mechanism='fixture',
            implementation_hash=H('runtime'),qualification_receipt_hash=H('runtime-receipt'),
            qualified_on_actual_host=True,private_read_denied=True,external_write_denied=True,
            network_policy_verified=True,budget_authority_external=True,clean_process_load_verified=True,
            qualification_scope='participant-execution'),
        independence=dict(evaluator_immutable=True,holdout_inaccessible=True,
            separate_evaluator_authority=True,confirmation_after_all_submissions_frozen=True,
            no_confirmation_feedback_to_generation=True,parent_commission_split=True,
            known_development_evidence_excluded_from_holdout=True,
            participant_writable_objects=['design','candidate_model','declared_harness_sources']),
        d_loop=dict(arms=arms,primary_outcome='independent_joint_acceptance_of_publicly_selected_final_design'),
        h_loop=dict(enabled=True,h0_hash=H('h0'),mutation_scope_hash=H('mutation'),
            generation_plan_hash=H('generation'),rollback_policy_hash=H('rollback'),cost_allocation_hash=H('cost'),
            arms=['frozen_h0_total_budget_matched','participant_evolved_h'],author_kind='participant',
            external_manual_fixes_are_separate=True,later_generation_requires_actual_parent_load=True,
            cost_phases=list(COST_PHASES),total_budget_by_arm={
                'frozen_h0_total_budget_matched':copy.deepcopy(budget),'participant_evolved_h':copy.deepcopy(budget)},
            unused_budget_policy='report_actual_cost_and_equal_opportunity_envelope_no_synthetic_spend',
            required_negative_controls=sorted(CONTROLS),
            promotion_authority='independent_evaluator_after_frozen_confirmation'))
    return approve(p)

def approve(p):
    p['approval']={'source_id':'synthetic-fixture-no-user-approval','protocol_hash':digest({k:v for k,v in p.items() if k!='approval'})}
    return p

class ContractTests(unittest.TestCase):
    def assertBlocked(self,p,code):
        r=check_plan(approve(p)); self.assertFalse(r['contract_complete']); self.assertIn(code,r['blockers']); self.assertFalse(r['live_launch_allowed'])
    def test_populated_contract_never_authorizes_launch(self):
        r=check_plan(complete_contract());self.assertTrue(r['contract_complete'],r);self.assertFalse(r['live_launch_allowed'])
    def test_draft_blocks(self):
        p=complete_contract();p['status']='draft';self.assertBlocked(p,'PROTOCOL_NOT_FROZEN')
    def test_episode_limit_cannot_exceed_global(self):
        p=complete_contract();p['global_money_cap']=0.5;self.assertBlocked(p,'EPISODE_CAP_EXCEEDS_GLOBAL_CAP')
    def test_unknown_model_blocks(self):
        p=complete_contract();p['model']['fingerprint']=None;self.assertBlocked(p,'MODEL_UNKNOWN:fingerprint')
    def test_unknown_budget_and_nan_block(self):
        for v in (None,-1,True,float('inf')):
            p=complete_contract();p['per_episode_budget']['money']=v
            r=check_plan(p);self.assertFalse(r['contract_complete'])
    def test_budget_mismatch_blocks(self):
        p=complete_contract();p['d_loop']['arms'][1]['budget']=dict(p['per_episode_budget'],solver_calls=2)
        self.assertBlocked(p,'D_FAIRNESS_MISMATCH:budget')
    def test_generic_architecture_restriction_blocks(self):
        p=complete_contract();p['d_loop']['arms'][0]['edit_freedoms']=['firmware']
        self.assertBlocked(p,'D_FAIRNESS_MISMATCH:edit_freedoms')
    def test_same_model_different_tool_access_blocks(self):
        p=complete_contract();p['d_loop']['arms'][0]['tools_hash']=H('weakened')
        self.assertBlocked(p,'D_FAIRNESS_MISMATCH:tools_hash')
    def test_reference_must_be_current_and_feasible(self):
        p=complete_contract();p['no_agent_reference']['world_id']=H('old-world')
        self.assertBlocked(p,'REFERENCE_IDENTITY_MISMATCH')
        p=complete_contract();p['no_agent_reference']['independently_feasible']=False
        self.assertBlocked(p,'REFERENCE_UNKNOWN_OR_UNQUALIFIED:independently_feasible')
    def test_synthetic_or_external_power_reference_blocks(self):
        for kind in ('synthetic','externally-powered-diagnostic'):
            p=complete_contract();p['no_agent_reference']['evidence_kind']=kind
            self.assertBlocked(p,'REFERENCE_IS_NOT_QUALIFIED_COMPUTATIONAL_EVIDENCE')
    def test_freeze_alone_does_not_admit(self):
        p=complete_contract();p['world_freeze_receipt']['formal_trial_admitted']=False
        self.assertBlocked(p,'WORLD_GATE:formal_trial_admitted')
    def test_portable_fixture_is_not_qualified_runtime(self):
        p=complete_contract();p['runtime']['qualification_scope']='load-fixture'
        self.assertBlocked(p,'FIXTURE_IS_NOT_RUNTIME_QUALIFICATION')
    def test_no_unknown_runtime_or_isolation_bypass(self):
        p=complete_contract();p['runtime']['qualified_on_actual_host']=False
        self.assertBlocked(p,'RUNTIME_UNQUALIFIED:qualified_on_actual_host')
    def test_holdout_feedback_or_mutable_evaluator_blocks(self):
        for k in ('evaluator_immutable','holdout_inaccessible','no_confirmation_feedback_to_generation'):
            p=complete_contract();p['independence'][k]=False
            self.assertBlocked(p,'INDEPENDENCE_MISSING:'+k)
    def test_h_loop_is_additive_required(self):
        p=complete_contract();p['h_loop']['enabled']=False;self.assertBlocked(p,'H_LOOP_MISSING')
    def test_h_only_solve_budget_matching_is_insufficient(self):
        p=complete_contract();p['h_loop']['cost_phases']=['solve'];self.assertBlocked(p,'H_TOTAL_COST_INCOMPLETE')
    def test_h_total_budget_matching(self):
        p=complete_contract();p['h_loop']['total_budget_by_arm']['participant_evolved_h']['money']=2
        self.assertBlocked(p,'H_TOTAL_BUDGET_MISMATCH')
    def test_h_manual_authorship_blocks(self):
        p=complete_contract();p['h_loop']['author_kind']='operator'
        self.assertBlocked(p,'H_AUTHORSHIP_NOT_SEPARATED')
    def test_h_missing_rollback_control_blocks(self):
        p=complete_contract();p['h_loop']['required_negative_controls'].remove('rollback')
        self.assertBlocked(p,'H_NEGATIVE_CONTROLS_INCOMPLETE')
    def test_owner_binding_invalidated_by_edit(self):
        p=complete_contract();p['global_money_cap']=200
        self.assertIn('OWNER_APPROVAL_NOT_BOUND',check_plan(p)['blockers'])
    def test_malformed_fails_closed(self):
        self.assertFalse(check_plan([])['contract_complete'])
    def test_source_manifest_hash_mismatch_fails_closed(self):
        self.assertEqual(source_binding_errors(ROOT/'protocol-draft.json',{'reuse_source_manifest_hash':H('wrong')}),['SOURCE_MANIFEST_HASH_MISMATCH'])
    def test_fractional_call_caps_block(self):
        p=complete_contract();p['per_episode_budget']['model_calls']=1.5
        self.assertBlocked(p,'common:INTEGER_LIMIT_REQUIRED:model_calls')
    def test_all_attempts_and_failed_costs_retained(self):
        rows=[dict(episode_id='a',status='budget_exhausted',attempt_ids=['a0','a1'],cost_complete=True),
              dict(episode_id='b',status='crashed',attempt_ids=['b0'],cost_complete=True)]
        self.assertEqual(outcome_errors(['a','b'],rows),[])
        self.assertIn('ALL_ATTEMPT_DENOMINATOR_MISMATCH',outcome_errors(['a','b'],rows[:1]))
        rows[0]['cost_complete']=False;self.assertIn('COST_INCOMPLETE',outcome_errors(['a','b'],rows))

class LoadAndLineageTests(unittest.TestCase):
    def probe(self,name):
        nonce=secrets.token_hex(16)
        source_hash=file_digest(ROOT/'fixtures'/(name+'.py'))
        expected={'harness_source_hash':source_hash,'harness_build_hash':source_hash,
          'controller_hash':file_digest(ROOT/'fixture_load_probe.py'),'nonce':nonce,
          'entrypoint':'plan','loaded_modules':{'trusted_load_fixture':source_hash},'author_pid':os.getpid()}
        with tempfile.TemporaryDirectory() as temp:
            p=subprocess.run([sys.executable,'-I','-S',str(ROOT/'fixture_load_probe.py'),name,nonce],
                cwd=temp,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr); r=json.loads(p.stdout);r['exit_code']=p.returncode
        self.assertEqual(activation_errors(r,expected),[])
        return r,expected
    def test_actual_fresh_process_load_and_call(self):
        a,_=self.probe('h0');b,_=self.probe('h1')
        self.assertEqual(a['fixture_output']['value'],4);self.assertEqual(b['fixture_output']['value'],5)
        self.assertNotEqual(a['harness_source_hash'],b['harness_source_hash'])
        self.assertFalse(a['participant_runtime_qualified'])
    def test_preimport_event_is_insufficient(self):
        r,e=self.probe('h1');r['post_import']=False;r['invoked']=False
        self.assertIn('ACTIVATION_REQUIRED:post_import',activation_errors(r,e))
    def test_invalid_pid_and_boolean_exit_rejected(self):
        r,e=self.probe('h0');r['pid']=0;r['exit_code']=False
        self.assertIn('FRESH_PID_REQUIRED',activation_errors(r,e))
        self.assertIn('ACTIVATION_PROCESS_FAILED',activation_errors(r,e))
    def test_import_failure_never_emits_load_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            p=subprocess.run([sys.executable,'-I','-S',str(ROOT/'fixture_load_probe.py'),'broken','nonce'],cwd=temp,env={'PATH':'/usr/bin:/bin'},capture_output=True,text=True,timeout=5)
        self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'');self.assertIn('CONTROLLED_IMPORT_FAILURE',p.stderr)
    def test_actual_call_failure_never_emits_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            p=subprocess.run([sys.executable,'-I','-S',str(ROOT/'fixture_load_probe.py'),'call_failed','nonce'],cwd=temp,env={'PATH':'/usr/bin:/bin'},capture_output=True,text=True,timeout=5)
        self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'');self.assertIn('CONTROLLED_CALL_FAILURE',p.stderr)
    def test_stale_build_rejected(self):
        r,e=self.probe('h0');e['harness_build_hash']=H('h1')
        self.assertIn('ACTIVATION_BINDING:harness_build_hash',activation_errors(r,e))
    def test_rollback_restores_exact_prior_behavior(self):
        a,_=self.probe('h0');b,_=self.probe('h1');back,_=self.probe('h0')
        self.assertEqual(a['harness_build_hash'],back['harness_build_hash'])
        self.assertEqual(a['invocation_output_hash'],back['invocation_output_hash'])
        self.assertNotEqual(a['invocation_output_hash'],b['invocation_output_hash'])
    def lineage(self):
        return dict(parent_hash=H('h0'),child_hash=H('h1'),generation=1,author_kind='participant',
             external_manual_edits=[],generator_loaded_harness_hash=H('h0'),generator_invocation_receipt_hash=H('generator-invocation'),participant_trace_hash=H('trace'),patch_hash=H('patch'),
             build_receipt_hash=H('build'),load_receipt_hash=H('load'),public_history_hash=H('history'),
             changed_paths=['solver.ts'],allowed_paths=['solver.ts','improver.ts'])
    def test_noop_not_a_generation(self):
        r=self.lineage();r['child_hash']=r['parent_hash']
        self.assertIn('NO_NEW_HARNESS',lineage_errors([r],H('h0')))
    def test_external_fix_not_participant_lineage(self):
        r=self.lineage();r['external_manual_edits']=['operator-fix']
        self.assertIn('NOT_PARTICIPANT_AUTHORED',lineage_errors([r],H('h0')))
    def test_actual_parent_required_for_later_generation(self):
        r=self.lineage();self.assertEqual(lineage_errors([r],H('h0')),[])
        r2=dict(r,parent_hash=H('missing'),child_hash=H('h2'),generation=2)
        self.assertIn('GENERATION_LINEAGE_BREAK',lineage_errors([r,r2],H('h0')))
    def test_rollback_not_new_generation_and_bool_rejected(self):
        r=self.lineage();back=dict(r,parent_hash=H('h1'),child_hash=H('h0'),generation=2,generator_loaded_harness_hash=H('h1'))
        self.assertIn('PREVIOUS_HARNESS_IS_ROLLBACK_NOT_GENERATION',lineage_errors([r,back],H('h0')))
        r['generation']=True;self.assertIn('GENERATION_LINEAGE_BREAK',lineage_errors([r],H('h0')))
    def test_evaluator_edit_rejected(self):
        r=self.lineage();r['changed_paths']=['evaluator.py']
        self.assertIn('HARNESS_EDIT_SCOPE_VIOLATION',lineage_errors([r],H('h0')))

if __name__=='__main__': unittest.main(verbosity=2)
