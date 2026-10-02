"""Read-only extraction and bounded arithmetic, never a scientific solver."""
import csv, hashlib, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SHARED=ROOT.parent
OLD=SHARED/'bf-simulation-chain/battery-world'
NEW=SHARED/'current-source-reconciliation-20261001/checkout'
GRID=SHARED/'bf-paper-campaigns/codesign-event-grid-20261001'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,v): (ROOT/name).write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
sources={
 'ADI_datasheet_research_only':SHARED/'primary-source-research-20261001/35881fc.pdf',
 'historical_design':OLD/'configs/reference_cases/door-magnetic-v1/design.json',
 'historical_baseline':OLD/'scripts/door_case/simchain/baseline-design.json',
 'historical_power':OLD/'scripts/door_case/simchain/physics_power.py',
 'historical_firmware':OLD/'scripts/door_case/simchain/firmware_receiver.py',
 'native_program':NEW/'battery-world/packages/python/bfworld/src/bfworld/agentlab/simulation_chain/program.c',
 'native_nominal':NEW/'battery-world/configs/reference_cases/closed-simulation/d2-nominal.json',
 'native_contracts':NEW/'battery-world/packages/python/bfworld/src/bfworld/agentlab/simulation_chain/contracts.py',
 'native_solver':NEW/'battery-world/packages/python/bfworld/src/bfworld/agentlab/simulation_chain/solver.py',
 'native_scope':NEW/'battery-world/docs/agentlab/CLOSED-SIMULATION.md',
 'source_reconciliation':SHARED/'current-source-reconciliation-20261001/REPORT.md',
 'paper_protocol':SHARED/'bf-paper-experiment-protocol-ledger.json',
 'grid_plan':GRID/'predeclared-plan.json',
 'grid_summary':GRID/'summary.json',
 'grid_rows':GRID/'results.csv',
 'grid_halfsteps':GRID/'halfstep-checks.json',
 'best_physics':GRID/'runs/g42_ci0p1_co100_dt0125us/physics.json',
 'best_design':GRID/'runs/g42_ci0p1_co100_dt0125us/design.json',
}
manifest={'schema':'bf-development-source-manifest-v1','native_source_commit':'338d60384d5805abf1e02252a4513860066a2c39','sources':{k:{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for k,p in sources.items()}}
write('SOURCE-MANIFEST.json',manifest)
baseline=read(sources['historical_baseline']); design=read(sources['historical_design'])
world={'excitation':'single_prescribed_door_open','opening_s':2.0,'open_angle_deg':65.0,'observation_s':4.0,'electrical_initial_V':0.0,'external_electrical_work_J':0.0,'door_driver_closed_world_mm':[856,45,2140], 'angle_profile':'linear_0_to_65_degrees_over_2_seconds_then_hold','repeat_operations_per_trial':1}
mission={'minimum_received_events':1,'receiver_deadline_s':4.0,'single_open_cold_start_required':True,'no_motion_energy_max_J':1e-9,'weak_motion_case':None,'correct_action_identity_required':True,'maximum_duplicate_events':0,'physical_receiver_claim':False}
common={
 'schema':'bf-development-task-contract-v1','revision':1,'status':'draft_blocked','evidence_tier':'computational_development_only',
 'world':world,'mission':mission,
 'facts_status':'source_recovered_not_requirement_owner_frozen',
 'scope_status':'architecture_open_api_incomplete',
 'public_assumptions':[
  'Nominal dimensions and installation are inherited design assumptions, not measured user requirements.',
  '65 degree / 2 second motion and 4 second deadline are recovered declared computational settings.',
  'Weak motion is required by inherited acceptance but its exact angle/time/trajectory is not frozen.',
  'Correct action attribution and deduplication need an acceptance implementation beyond silence-based grouping.',
  'The 8 mm bound is applicability of the inherited linear ROM, not a physical safety limit.',
  'Initial closed-door magnetic equilibrium has nonzero mechanical energy; preparation/reset provenance must be explicit.'
 ],
 'allowed_design':{
  'all_main_arms':['Generic Agent','Domain-Guided Agent','Budget-Matched Search','BF-Design'],
  'permissions_per_arm':{a:{'architecture_changes':True,'mechanical_changes':True,'circuit_changes':True,'firmware_changes':True,'cross_domain_changes':True,'same_tool_access':True} for a in ['Generic Agent','Domain-Guided Agent','Budget-Matched Search','BF-Design']},
  'candidate_components':['beam_and_piezo_geometry','magnet_geometry_and_mount','passive_mechanical_release','rectifier_and_power_topology','real_storage_components','firmware_policy_and_payload'],
  'implementation_rule':'Every candidate change requires artifact-bound model support and independent validation over its actual domain. Unsupported does not mean failed design; request model extension or return insufficient_evidence.',
  'hard_constraints_to_freeze':['allowed_installation_volume_and_placement','clearance_and_peak_actuation_force','material_and_component_catalog','weak_motion_case','receiver_protocol_and_action_identity','first_operation_mechanical_preparation_and_reset'],
  'forbidden':['external_power_as_feasible_reference','electrical_precharge','stronger_or_faster_excitation','extra_operations','lowered_event_or_deadline_requirement','silent_model_parameter_edit','unsupported_ROM_extrapolation','hidden_reference_access','architecture_restriction_on_strong_baselines']
 },
 'acceptance':{
  'mission_pass_never_sufficient_alone':True,
  'required_checks':['source_and_artifact_hashes','identical_world_and_mission','independent_design_space_membership','zero_external_electrical_energy','zero_initial_electrical_energy','mechanical_initial_state_and_reset_ledger','model_applicability','numerical_convergence','reciprocal_energy_balance','complete_firmware_tx','action_attributed_timely_receiver_event','no_motion_negative_control','weak_motion_defined_and_passed','native_CAD_EDA_binding','reference_independently_replayed'],
  'inherited_numerical_targets':{'max_rom_deflection_mm':8.0,'mesh_delta_pct':5.0,'time_step_energy_delta_pct':5.0},
  'behavioral_campaign_stricter_targets':{'energy_residual_strictly_below':0.01,'halfstep_energy_voltage_aux_relative':0.01,'displacement_relative':0.005},
  'target_rule':'Provider-specific thresholds are frozen before a witness; current code/test logic does not qualify a new provider or relax any old threshold.',
  'result_distinctions':['completed_unsatisfied','out_of_domain','numerical_fail','tool_fail','insufficient_evidence','qualified_model_mission_pass'],
  'hardware_or_product_acceptance':False
 },
 'reference_witness':None,
 'qualification':{'facts_frozen':False,'allowed_design_space_complete':False,'evaluator_qualified':False,'reference_independently_feasible':False,'numerical_and_native_evidence_complete':False,'mechanical_boundary_resolved':False},
 'holdout':{
  'state':'not_frozen','all_current_sources_are_development_exposed':True,
  'exposed_cohorts':['20_gap_cap_designs','gap_eligibility_41_42_43','spatial_addendum','historical_external_power_diagnostics','current_native_published_baseline_and_positive_diagnostic'],
  'rules':['New confirmation parent tasks must be distinct from these development states; paraphrases are clustered with their parent.', 'Reference solution and independent acceptance traces are stored separately from participant files.', 'All methods get the same initial request, fixed-facts answers, public sources and normal public checker feedback.', 'Independent final evaluation and held-out conditions never feed back to the same participant trial.', 'Freeze public design selection at budget slices; never select the best past candidate using hidden outcomes.', 'No reference from a participant trial or BF-Design-only privileged repair is admitted.'],
  'independent_reference_sha256':None,'private_holdout_manifest_sha256':None
 },
 'formal_trials_authorized':False,'new_dynamic_solves_authorized':False,
}
from copy import deepcopy
a=deepcopy(common);a.update(task_id='DEV-FEASIBLE-01',title='Commission a first-opening switch',experimental_unit='independent_design_run',purpose='Ordinary end-to-end commissioning with at least one independently feasible in-space reference; no architecture revision is required or rewarded by construction.',starting_state={'type':'request_and_common_public_assets','solution_hint':None},task_specific_gates=['ordinary_reference_feasible','not_constructed_to_require_recomposition'])
a['qualification']['ordinary_reference_feasible']=False
a['qualification']['not_constructed_to_require_recomposition']=False
b=deepcopy(common);b.update(task_id='DEV-COUPLING-01',title='Recover cold-start event delivery',experimental_unit='same_state_continuation',purpose='Resolve the naturally observed mechanical-source / storage / startup bottleneck while retaining the same mission; retain any valid single-domain repair if one exists.',starting_state={'type':'development_failure_snapshot','case':'g42_ci0p1_co100_dt0125us','design_source':'best_design','physics_source':'best_physics','is_feasible':False,'public_failure_feedback':'UVLO is reached repeatedly; auxiliary readiness, Vout, firmware boot and reception remain zero. Cout-only changes had no effect upstream.'},task_specific_gates=['cross_domain_bottleneck_observed','independent_successful_intervention','matched_patch_evidence_without_forced_synergy'])
b['qualification']['cross_domain_bottleneck_observed']=True
b['qualification']['independent_successful_intervention']=False
b['qualification']['matched_patch_evidence_without_forced_synergy']=False
write('TASKS.json',{'schema':'bf-development-task-set-v1','warning':'These are two blocked development task templates, not two admitted commissions. One is a full design run and one a continuation; never pool their denominators.','tasks':[a,b]})
rows=list(csv.DictReader(sources['grid_rows'].open()))
fine=[r for r in rows if r['run_status']=='completed' and float(r['dt_s'])==.000125 and not r['case'].startswith('selected_')]
assert len(fine)==20
best=max(fine,key=lambda r:float(r['derived__peak_auxiliary_energy_J']))
p=read(sources['best_physics']); E=p['energy_ledger_J']; met=p['metrics'];par=p['parameters']
state={k:v for k,v in p.items() if k in ['campaign_identity','metrics','energy_ledger_J','parameters']}
target=.5*5.7e-6*4.8**2
bound=.5*par['k']*.008**2
output_compare=[]
for ci in [.1,.22,.47,1]:
 cells=[r for r in fine if float(r['gap_mm'])==42 and float(r['input_cap_uF'])==ci]
 fields=['metrics__peak_auxiliary_energy_J','metrics__peak_vin_V','metrics__peak_vout_V','packets','grouped_events']
 output_compare.append({'input_cap_uF':ci,'Cout_uF':sorted(float(r['output_cap_uF']) for r in cells),'fields':fields,'all_identical':all(len({r[f] for r in cells})==1 for f in fields)})
write('ANALYTIC-CHECKS.json',{
 'schema':'bf-task-bounded-analytic-checks-v1','execution':'existing artifact extraction and arithmetic only; zero new scientific solves',
 'unique_fine_designs':len(fine),'mission_successes':sum(int(r['grouped_events'])>=1 for r in fine),
 'halfstep_passes':sum(x['pass'] for x in read(sources['grid_halfsteps'])),
 'best_peak_aux_uJ':met['peak_auxiliary_energy_J']*1e6,'assumed_aux_target_uJ':target*1e6,'peak_fraction_of_assumed_target':met['peak_auxiliary_energy_J']/target,
 'initial_mechanical_uJ':E['initial_mechanical']*1e6,'ROM_elastic_energy_at_8mm_uJ':bound*1e6,
 'net_piezo_electrical_work_uJ':float(best['derived__net_piezo_electrical_work_J'])*1e6,
 'best_case_uvlo_activations':met['pmic_enable_intervals'],'best_case_aux_ready':False,'best_case_boots':p['firmware_summary']['boots'],
 'capacitor_energy_at_5p05V_uJ':{str(ci):.5*ci*1e-6*5.05**2*1e6 for ci in [.1,.22,.47,1,47]},
 'Cout_invariance':output_compare,
 'interpretation':['pmic_started means at least one UVLO enable; it does not mean completed cold start.', 'The 2.790 mJ elastic-energy number is not harvestable electrical energy or a witness.', 'The 65.664 uJ target and 0.1 s decay are behavioral model assumptions, not established vendor cold-start facts.', '44 enables and 11.105 uJ peak do not establish that all architectures are infeasible.', 'No nonlinear release, contact or reset-cycle model is in the inherited solver.'],
 'best_case':state})
write('MINIMAL-EVIDENCE-AND-PLAN.json',{
 'schema':'bf-task-qualification-plan-v1','status':'proposed_not_executed','new_solver_runs_this_package':0,
 'required_before_any_dynamic_plan':['Choose/pin one model stack; do not pool vendor and behavioral chains.', 'Freeze actual installation, weak-motion, receiver semantics and initial/reset boundary; retain unresolved requirements rather than weaken them.', 'Import the already requested native baseline and positive-diagnostic evidence packet; it can qualify components but is not a feasible reference.', 'Compare actual internal CAP/VIN2 startup and decay to behavioral model with source-matched data.'],
 'minimal_model_extension':{
  'startup':['A versioned actual-rail model or imported native trace with VIN, VIN2, CAP-to-VIN, Vout, PGOOD, all rail initial conditions and port currents; bind real capacitor values, DC bias/ESR/leakage, component topology and PMIC macro-model hash.', 'If considering the datasheet low-input topology, model and qualify <6 V input protection, clamp loss/leakage, regulation target and firmware voltage compatibility. Do not merely set startup energy to zero.'],
  'mechanical_release':['Retain actual door trajectory and energy-accounted closed-door initial equilibrium.', 'A passive release/latch hypothesis needs geometry-derived engagement/disengagement/contact and force continuity or impulse/work accounting, and an independent dynamic comparison over the resulting deflection/rotation domain.', 'Prove how the initial state is prepared/reset within the declared battery-free operation boundary; do not add a free initial displacement or release waveform.'],
  'architecture_api':['Artifact-bound support for at least one independently feasible architecture in the allowed space; all methods must be able to invoke the same providers.', 'If only fixed inherited beam and fixed topology remain executable, label the work restricted engineering development and keep architecture-open task admission false.']},
 'finite_follow_on_proposal':{
  'status':'requires_parent_approval_and_exact_versioned_inputs_before_execution',
  'phase_1_read_only_import':{'new_scientific_solves':0,'purpose':'Review existing native baseline, positive diagnostic and supplier documentation, then decide actual-rail adequacy.'},
  'phase_2_candidate_qualification':{'max_new_joint_solves':8,'design_cells':['D','D+a','D+b','D+a+b'],'steps_per_cell':2,'retries':0,'scope':'Only after one exact qualified mechanical patch a and one exact qualified circuit/firmware patch b are independently justified and frozen, keep W fixed; coarse/fine each cell. Do not force both patches to be necessary.','stop':'At the finite cohort, an unsupported/out-of-domain result, or qualification failure; no adaptive grid expansion or threshold change.'},
  'required_plan_before_phase_2':['exact design/model/provider hashes','source-bound component choices','exact coarse/fine solver settings and numerical acceptance','per-solve wall/RHS budgets supported by chosen provider','initial/reset ledger','candidate-selection rule','independent evaluator and evidence destination'],
  'ordinary_reference_rule':'Freeze a successful independently developed reference before any task participant; if none passes, keep DEV-FEASIBLE-01 blocked.',
  'no_solver_run_is_authorized_by_this_plan':True},
 'external_primary_reference':{'url':'https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf','read_utc_date':'2026-10-01','locations':['p7 pin functions','p8 internal rail generation','p13 VIN2 and CAP capacitors'], 'claim':'Distinct rail dynamics and a conditional low-input alternative motivate qualification, not a new feasibility claim.'},
 'what_cannot_substitute':['externally powered diagnostic','hypothetical synthetic positive fixture','lowered auxiliary threshold','extra precharge','faster or repeated opening','bare mission flag without source and replay','physics source tests without qualified reference']})
print('Artifacts built; no scientific solver called.')
