"""Software gate tests only; synthetic success is never scientific evidence."""
import copy,json,tempfile,unittest
from pathlib import Path
import admission as a
TASKS=json.loads((a.ROOT/'TASKS.json').read_text())['tasks']
class AdmissionTests(unittest.TestCase):
 def setUp(self):self.task=copy.deepcopy(TASKS[0])
 def errors(self):return a.validate_contract(self.task)
 def test_drafts_valid_but_blocked(self):
  for t in TASKS:
   r=a.evaluate_task(t);self.assertTrue(r['contract_valid']);self.assertFalse(r['admitted_for_development_participants']);self.assertFalse(r['formal_launch_allowed'])
 def test_rail_static_counterexamples(self):
  d=json.loads((a.ROOT/'STARTUP-MODEL-ANALYSIS.json').read_text())['existing_topology_rail_analysis']['sub_UVLO_invariant_counterexample'];self.assertIsNone(d['settling_time_s']);self.assertEqual([17.8125,57.7125],[round(x['datasheet_ideal_settled_bypass_uJ'],7) for x in d['test_points']]);self.assertTrue(all(x['old_aux_uJ']==0 and x['Vin_V']<d['UVLO_rise_V'] for x in d['test_points']))
 def test_source_derived_firmware_totals(self):
  f=json.loads((a.ROOT/'STARTUP-MODEL-ANALYSIS.json').read_text())['frozen_firmware_assumptions'];self.assertAlmostEqual(f['historical_behavioral']['charge_uC'],30.96);self.assertAlmostEqual(f['pinned_native']['charge_uC'],61.101);self.assertAlmostEqual(f['historical_behavioral']['energy_at_constant_3p3V_uJ'],102.168);self.assertAlmostEqual(f['pinned_native']['energy_at_constant_3p3V_uJ'],201.6333)
 def test_numerical_threshold_relaxation(self):
  self.task['acceptance']['inherited_numerical_targets']['mesh_delta_pct']=20;self.assertIn('INHERITED_NUMERICAL_TARGETS_CHANGED',self.errors())
 def test_nonfinite_evaluation_fails_closed(self):
  self.task['world']['opening_s']=float('nan');self.assertFalse(a.evaluate_task(self.task)['admitted_for_development_participants'])
 def test_bool_cannot_replace_mission_count(self):
  self.task['mission']['minimum_received_events']=True;self.assertIn('MISSION_CONTRACT_CHANGED:minimum_received_events',self.errors())
 def test_false_cannot_replace_duplicate_count(self):
  self.task['mission']['maximum_duplicate_events']=False;self.assertIn('MISSION_CONTRACT_CHANGED:maximum_duplicate_events',self.errors())
 def test_number_cannot_replace_boolean_flag(self):
  self.task['mission']['single_open_cold_start_required']=1;self.assertIn('MISSION_CONTRACT_CHANGED:single_open_cold_start_required',self.errors())
 def test_fractional_type_cannot_replace_integer_count(self):
  self.task['mission']['minimum_received_events']=1.0;self.assertIn('MISSION_CONTRACT_CHANGED:minimum_received_events',self.errors())
 def test_false_cannot_replace_zero_world_energy(self):
  self.task['world']['external_electrical_work_J']=False;self.assertIn('WORLD_CONTRACT_CHANGED:external_electrical_work_J',self.errors())
 def test_float_cannot_replace_operation_count(self):
  self.task['world']['repeat_operations_per_trial']=1.0;self.assertIn('WORLD_CONTRACT_CHANGED:repeat_operations_per_trial',self.errors())
 def test_reference_missing(self):self.assertIn('NO_FEASIBLE_REFERENCE_WITNESS',a.evaluate_task(self.task)['blockers'])
 def test_weak_motion_missing(self):self.assertIn('WEAK_MOTION_UNDEFINED',a.evaluate_task(self.task)['blockers'])
 def test_precharge_forbidden(self):self.task['world']['electrical_initial_V']=1;self.assertIn('WORLD_CONTRACT_CHANGED:electrical_initial_V',self.errors())
 def test_external_power_forbidden(self):self.task['world']['external_electrical_work_J']=1e-9;self.assertIn('WORLD_CONTRACT_CHANGED:external_electrical_work_J',self.errors())
 def test_stronger_motion_forbidden(self):self.task['world']['opening_s']=.1;self.assertIn('WORLD_CONTRACT_CHANGED:opening_s',self.errors())
 def test_extra_operation_forbidden(self):self.task['world']['repeat_operations_per_trial']=2;self.assertIn('WORLD_CONTRACT_CHANGED:repeat_operations_per_trial',self.errors())
 def test_lowered_service_forbidden(self):self.task['mission']['minimum_received_events']=0;self.assertIn('MISSION_CONTRACT_CHANGED:minimum_received_events',self.errors())
 def test_deadline_relaxation_forbidden(self):self.task['mission']['receiver_deadline_s']=5;self.assertIn('MISSION_CONTRACT_CHANGED:receiver_deadline_s',self.errors())
 def test_baseline_architecture_restriction_forbidden(self):self.task['allowed_design']['permissions_per_arm']['Generic Agent']['architecture_changes']=False;self.assertIn('UNEQUAL_OR_RESTRICTED_MAIN_ARMS',self.errors())
 def test_hardware_claim_forbidden(self):self.task['acceptance']['hardware_or_product_acceptance']=True;self.assertIn('HARDWARE_CLAIM_FORBIDDEN',self.errors())
 def test_nonfinite_contract(self):self.task['world']['opening_s']=float('nan');self.assertIn('NONFINITE_OR_NONJSON_CONTRACT',self.errors())
 def test_launch_cannot_be_granted(self):self.task['formal_trials_authorized']=True;self.assertIn('FORMAL_TRIALS_NOT_AUTHORIZED',self.errors())
 def test_dynamics_cannot_be_granted(self):self.task['new_dynamic_solves_authorized']=True;self.assertIn('DYNAMIC_RUNS_NOT_AUTHORIZED',self.errors())
 def test_current_sources_are_development_only(self):self.task['holdout']['all_current_sources_are_development_exposed']=False;self.assertIn('DEVELOPMENT_LEAKAGE_BOUNDARY_LOST',self.errors())
 def test_source_integrity_real_files(self):self.assertEqual([],a.check_sources(json.loads((a.ROOT/'SOURCE-MANIFEST.json').read_text())))
 def test_source_hash_mismatch(self):
  m=json.loads((a.ROOT/'SOURCE-MANIFEST.json').read_text());m['sources']['historical_design']['sha256']='0'*64;self.assertIn('SOURCE_IDENTITY_MISMATCH:historical_design',a.check_sources(m))
 def test_source_missing(self):self.assertEqual(['SOURCE_MISSING:x'],a.check_sources({'sources':{'x':{'path':'/nonexistent/bf-task-test','bytes':0,'sha256':'0'*64}}}))
 def test_evidence_integrity_and_traversal(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'e.json';p.write_text('{}');ref={'path':'e.json','sha256':a.file_hash(p)};self.assertIsNone(a.check_evidence_file(ref,d));p.write_text('[]');self.assertEqual('EVIDENCE_HASH_MISMATCH',a.check_evidence_file(ref,d));ref['path']='../e.json';self.assertEqual('EVIDENCE_PATH_DENIED',a.check_evidence_file(ref,d))
 def witness(self):
  return {'schema':'bf-independent-feasible-witness-v1','synthetic':True,'task_contract_id':a.task_identity(self.task),'world':self.task['world'],'mission':self.task['mission'],'origin':'independent_no_agent_reference','design_space_id':a.digest(self.task['allowed_design']),'diagnostic_only':False,'run_status':'completed','applicability':'in_domain','initial_electrical_energy_J':0,'external_electrical_work_J':0,'metrics':{'correct_nonduplicated_received_events':1,'first_correct_event_s':1,'duplicate_events':0},'checks':{k:True for k in a.WITNESS_CHECKS},'model_version_id':'0'*64,'evidence':{}}
 def test_synthetic_reference_rejected(self):self.assertIn('SYNTHETIC_OR_UNKNOWN_REFERENCE',a.check_witness(self.task,self.witness(),a.ROOT))
 def test_powered_reference_rejected(self):
  w=self.witness();w['diagnostic_only']=True;w['external_electrical_work_J']=1e-6;r=a.check_witness(self.task,w,a.ROOT);self.assertIn('DIAGNOSTIC_NOT_FEASIBLE_REFERENCE',r);self.assertIn('UNAUTHORIZED_ENERGY:external_electrical_work_J',r)
 def test_reference_changes_world_rejected(self):
  w=copy.deepcopy(self.witness());w['world']['opening_s']=.1;self.assertIn('REFERENCE_WORLD_OR_MISSION_MISMATCH',a.check_witness(self.task,w,a.ROOT))
 def test_reference_must_pass_events_and_deadline(self):
  w=self.witness();w['metrics']['correct_nonduplicated_received_events']=0;w['metrics']['first_correct_event_s']=5;r=a.check_witness(self.task,w,a.ROOT);self.assertIn('REFERENCE_EVENT_FAIL',r);self.assertIn('REFERENCE_DEADLINE_FAIL',r)
 def test_out_of_domain_reference_rejected(self):
  w=self.witness();w['applicability']='out_of_domain';self.assertIn('REFERENCE_NOT_IN_DOMAIN',a.check_witness(self.task,w,a.ROOT))
 def test_participant_reference_rejected(self):
  w=self.witness();w['origin']='BF-Design participant';self.assertIn('REFERENCE_NOT_INDEPENDENT',a.check_witness(self.task,w,a.ROOT))
 def test_reference_needs_all_artifact_roles(self):
  self.assertEqual(7,len([x for x in a.check_witness(self.task,self.witness(),a.ROOT) if x.startswith('REFERENCE_EVIDENCE_MISSING:')]))
 def test_coupling_intervention_not_yet_proven(self):
  self.assertIn('QUALIFICATION_MISSING:independent_successful_intervention',a.evaluate_task(TASKS[1])['blockers'])
 def test_analytic_old_cohort_is_twenty(self):
  c=json.loads((a.ROOT/'ANALYTIC-CHECKS.json').read_text());self.assertEqual(c['unique_fine_designs'],20);self.assertEqual(c['mission_successes'],0);self.assertEqual(c['halfstep_passes'],20);self.assertTrue(all(x['all_identical'] for x in c['Cout_invariance']));self.assertAlmostEqual(c['assumed_aux_target_uJ'],65.664)
if __name__=='__main__':unittest.main(verbosity=2)
