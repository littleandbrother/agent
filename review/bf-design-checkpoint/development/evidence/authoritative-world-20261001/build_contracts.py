"""Build a NEW owned candidate; never write any original or sealed input."""
import copy, hashlib, json, pathlib, shutil, sys
ROOT=pathlib.Path(__file__).resolve().parent
if (ROOT/'FREEZE-RECEIPT.json').exists():
 raise SystemExit('Refusing to overwrite a frozen package; create a new owned version directory.')
sys.path.insert(0,str(ROOT/'src'))
from authoritative_world import digest, file_hash, write_json
UP=pathlib.Path('/workspace/shared/current-cache-integration-20261001/working/battery-world')
AL=pathlib.Path('/workspace/shared/simulation-model-alignment-20261001')
TG=pathlib.Path('/workspace/shared/bf-development-task-gates-20261001')
SC=UP/'packages/python/bfworld/src/bfworld/agentlab/simulation_chain'
sources={
 'upstream_contracts':(SC/'contracts.py','computational_defaults_and_parameter_support'),
 'upstream_native':(SC/'native.py','geometry_force_program_build_semantics'),
 'upstream_solver':(SC/'solver.py','native_coupling_initial_state_numerical_semantics'),
 'upstream_program':(SC/'program.c','shared_C_application_policy_not_device_timing'),
 'upstream_receiver':(UP/'scripts/pluck_receiver.py','receiver_decoder_source_rewritten_BFP1_to_BFD2_by_native_builder'),
 'upstream_build_cad':(UP/'scripts/door_case/build_cad.py','declared_CAD_construction'),
 'upstream_build_product':(UP/'scripts/build_pluck_product.py','declared_CAD_definition'),
 'alignment_upstream':(AL/'contracts/upstream-default.json','recovered_source_semantics'),
 'alignment_legacy':(AL/'contracts/cloud-default.json','distinct_legacy_world_semantics'),
 'alignment_geometry':(AL/'contracts/canonical-geometry-fixtures.json','declaration_coordinate_crosscheck'),
 'alignment_lock':(AL/'contracts/source-lock.json','prior_exact_source_identity'),
 'legacy_tasks':(TG/'TASKS.json','historical_unadmitted_task_templates'),
 'transition_readme':(pathlib.Path('/workspace/shared/mainline-transition-delivery-20261001/README.zh.md'),'latest_delivery_limits'),
 'upstream_agents':(UP/'AGENTS.md','repository_constitution'),
 'upstream_project':(UP/'PROJECT.yaml','active_feature_null_prior_feature_complete'),
 'upstream_feature':(UP/'project/features/BFA-030-closed-simulation/feature.yaml','prior_feature_ownership_and_claim_boundary'),
}
# Use recovered exact supplement if the checkout did not fetch this root script.
if not sources['upstream_build_product'][0].exists():
 sources['upstream_build_product']=(AL/'source-supplement/build_pluck_product.py','pinned_recovered_CAD_definition')
registry={'schema':'bf-authoritative-source-registry-v1','upstream_commit':'338d60384d5805abf1e02252a4513860066a2c39','sources':{}}
for name,(path,role) in sources.items():
 suffix=path.suffix; dest=ROOT/'sources'/(name+suffix)
 shutil.copyfile(path,dest)
 registry['sources'][name]={'snapshot_path':str(dest.relative_to(ROOT)),'original_path':str(path),'sha256':file_hash(path),'bytes':path.stat().st_size,'role':role}
write_json(ROOT/'contracts/source-registry.json',registry)
u=json.loads((AL/'contracts/upstream-default.json').read_text())
authority={
 'schema':'bf-authority-registry-v1','version':1,
 'computational_semantics':{'owner':'world_maintainer','sources':['upstream_contracts','upstream_native','upstream_solver','upstream_program','upstream_receiver'],'participant_mutable':False},
 'task_requirements':{'owner':'requirement_owner','state':'not_owner_frozen','participant_mutable':False,'sources':['legacy_tasks']},
 'candidate_design':{'owner':'participant','participant_mutable':True,'never_controls':['world_id','task_contract_id','qualification','source_registry','reference_model']},
 'candidate_world_model':{'owner':'participant','participant_mutable':True,'qualification_authority':False},
 'reference_model':{'owner':'independent_evaluator','participant_mutable':False,'physical_qualified':False},
 'evidence':{'owner':'runtime','immutable_after_seal':True,'participant_mutable':False},
 'presentation':{'owner':'viewer','scientific_identity_effect':'none'},
 'qualification':{'owner':'independent_reviewer','world_freeze_is_sufficient':False},
 'conflict_policy':'new semantics require a new version and identity; source authority does not convert assumptions to user requirements',
 'ranking_policy':'never pool legacy world, canonical world, independent runs and same-state continuations',
}
write_json(ROOT/'contracts/authority-registry.json',authority)
unknowns=[
 ('installation_limits','Allowed volume, placement, clearance and peak actuation force have not been requirement-owner frozen.'),
 ('weak_motion','Exact weak-motion angle, duration and trajectory are not frozen.'),
 ('material_component_catalog','Allowed physical materials/components and architecture implementation coverage remain incomplete.'),
 ('mechanical_preparation_reset','Closed magnetic equilibrium is a computational initial condition; physical first-operation preparation and reset work are unknown.'),
 ('initial_mechanical_energy_J','Requires design-specific qualified stiffness and equilibrium; no fabricated scalar.'),
 ('auxiliary_initial_energy_J','Native CAP/VIN2 initial/internal stores lack retained observation and cannot be presumed zero.'),
 ('native_pin_port_order','Current native deck is preserved source semantics; independently verified vendor pin/port binding is absent.'),
 ('native_auxiliary_dynamics','CAP/VIN2 readiness/settling and encrypted internal losses are not fully observed or qualified.'),
 ('magnetic_full_domain','Prior sparse unrotated magnetic mesh result 11.3% exceeds 5%; rotation/full-trajectory validation absent.'),
 ('mechanical_nonlinearity','Inherited +/-8mm ROM support is not a measured safety bound or nonlinear qualification.'),
 ('binary_power_timing','Phase-average currents/durations derive from author prototype assumptions, not measured execution of this C binary.'),
 ('receiver_action_identity','BFD2 has no sequence, reboot or physical action identity; silence grouping cannot establish true direction or dedup radio events.'),
 ('independent_feasible_reference','No admitted in-space no-Agent feasible witness is available.'),
 ('private_holdout','Existing sources are development-exposed; independently frozen confirmation holdout absent.'),
]
world={
 'schema': 'bf-authoritative-development-world-v1','version':1,
 'name':'door-magnetic-upstream-development-v1',
 'semantics_status':'computational_spec_frozen_physical_qualification_blocked',
 'upstream_commit':registry['upstream_commit'],
 'units':{'length':'m','time':'s','angle':'rad','force':'N','voltage':'V','current':'A','capacitance':'F','energy':'J'},
 'source_bindings':{k:v['sha256'] for k,v in registry['sources'].items()},
 'authority_registry_id':digest(authority),
 'geometry':{'family':'upstream-moving-driver','gap_operation':'move_rotating_driver_keep_stationary_tip_fixed','nominal_gap_m':.048,
             'nominal_tip_world_m':[.904,.075265,2.14],'nominal_driver_world_m':[.856,.045,2.14],
             'pivot_world_m':[0.,0.,0.],'rotation_axis_world':[0,0,1],'positive_q_world':[0,1,0],
             'force_from_world':[[-1,0,0],[0,0,1],[0,1,0]],'tip_size_m':[.01]*3,'driver_size_m':[.02]*3,
             'parameter_support_gap_m':[.028,.070],'rom_absolute_deflection_limit_m':.008,
             'support_is_physical_qualification':False,'initial_magnetization_force_axis':[1,0,0]},
 'input':{'kind':'single_prescribed_door_open','angle_profile':'linear_then_hold','opening_s':2.,'opening_angle_rad':u['source_trajectory']['angle_rad'],
          'observation_s':4.,'repeat_operations':1,'external_electrical_input_A':0.,'external_electrical_work_J':0.,
          'no_motion_control':'same initial-state recipe; angle fixed at zero; initial stored mechanical energy must still be accounted',
          'weak_motion_case':None,'status':'development_assumption_not_owner_frozen_user_requirement'},
 'initial_state':{'piezo_V':0.,'vin_V':0.,'vout_V':0.,'qdot_m_s':0.,'q0_rule':'solve k*q0=interpolated_F(angle=0,q0) within declared ROM','mechanical_J':None,
                  'auxiliary_J':None,'preparation_reset_work_J':None,'all_electrical_stores_proven_zero':False,
                  'scope':'declared primary electrical ICs; unknown auxiliary/native stores and physical preparation remain unresolved'},
 'force':u['force'],
 'circuit':u['circuit'],
 'program':{**u['firmware'],'states':['RESET','BOOT','WAIT','INIT','TX','SLEEP'],
            'source_id':registry['sources']['upstream_program']['sha256'],
            'time_step_input_unit':'ms','current_output_unit':'mA','supply_sampling':'minimum includes subgrid brownout and PGOOD loss',
            'completion_priority':'supply brownout, then inflight PGOOD abort, then timer completion','load_calibration':'prototype_phase_average_assumption_not_this_binary_measured',
            'target_claim':'shared_application_C_SIL_only_not_SoC_SoftDevice_RF_or_hardware'},
 'receiver':{**u['receiver'],'packet':u['packet'],'source_rewrite':{'from':'BFP1','to':'BFD2'},'event_identity':'silence-group-estimate',
             'radio_duplicates_resolved':False,'reboot_identity_available':False,'correct_action_attribution_qualified':False,'physical_receiver_qualified':False},
 'mission':{'receiver_deadline_s':4.,'minimum_received_groups':1,'minimum_correct_attributed_events':1,'maximum_duplicate_events':0,
            'single_open_cold_start':True,'no_motion_energy_max_J':1e-9,'legacy_cold_start_proxy_peak_vout_V':3.2,
            'legacy_proxy_is_mission_acceptance':False,'diagnostic_energy_cannot_be_feasible_reference':True},
 'numerics':{'source_provider':'native-LTC3588-1-encrypted-macro','source_maxstep_s':.00005,'firmware_grid_s':.0001,'reltol':.0001,
             'same_step_comparison_required':True,'peak_before_intervention_is_causal_evidence':False,
             'max_mechanical_piezo_energy_residual_strictly_below':.01,'mesh_delta_max':.05,'rom_limit_is_physical_safety_limit':False},
 'development_assumptions':[
    {'id':'source_geometry','description':'Nominal dimensions and installation from upstream code; not measured user requirements.','source':'upstream_native'},
    {'id':'input_deadline','description':'65 degree in 2 seconds; 4 second observation/deadline retained from published development settings.','source':'alignment_upstream'},
    {'id':'force_material','description':'Uniform remanence 1.25T and recoil permeability one; damping ratio inherited, not calibrated.','source':'upstream_contracts'},
    {'id':'program_phase_load','description':'ViPSN-Pluck SP-SSHI/LTC3588-1/MIC841 author prototype phase energies converted to average currents; not SP-SECE nor measured binary.','source':'transition_readme'},
    {'id':'virtual_link','description':'Full scan, zero loss and deterministic seed are virtual development assumptions.','source':'upstream_solver'}],
 'user_requirement_status':{'numerical_and_physical_requirements_owner_frozen':False,'inherited_values_are_not_user_requirements':True},
 'unresolved_facts':[{'id':key,'status':'unknown','value':None,'reason':reason} for key,reason in unknowns],
 'qualification':{'computational_spec_frozen':True,'requirements_owner_frozen':False,'physical_qualified':False,'formal_trial_admitted':False,'all_sources_development_exposed':True},
}
write_json(ROOT/'contracts/world-v1.json',world)
legacy=copy.deepcopy(world);legacy['name']='door-magnetic-legacy-cloud-development-v1';legacy['geometry']['family']='cloud-moving-product';legacy['geometry']['gap_operation']='move_stationary_product_keep_rotating_driver_fixed'
l=json.loads((AL/'contracts/cloud-default.json').read_text());legacy['program']={**legacy['program'],'legacy_semantic_contract':l['firmware'],'policy':l['firmware']['policy'],'canonical_program_not_used':True};legacy['initial_state']['auxiliary_J']=0.;legacy['initial_state']['scope']='legacy behavioral declared zero auxiliary state; no equivalence to native';legacy['circuit']=l['circuit'];legacy['receiver']['legacy_semantic_contract']=l['receiver'];legacy['receiver']['packet']=l['packet'];legacy['numerics']['source_provider']=l['version']['model'];legacy['numerics']['legacy_numerical_semantics']=l['version']['numerical_semantics']
legacy['legacy_semantic_contract']=l
legacy['program']=l['firmware'];legacy['receiver']={**l['receiver'],'packet':l['packet']}
legacy['numerics']={'source_provider':l['version']['model'],'numerical_semantics':l['version']['numerical_semantics']}
legacy['mission']=l['mission']
write_json(ROOT/'contracts/legacy-world-v1.json',legacy)
# This version is an immutable specification, not an open schema for editing facts.
# New semantics must be registered in a new version/schema rather than accepted here.
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:bf:authoritative-development-world:v1','title':'Frozen computational specification, with unresolved physical facts','oneOf':[{'const':world},{'const':legacy}]}
write_json(ROOT/'contracts/world.schema.json',schema)
wid=digest(world);oldid=digest(legacy)
oldtasks=json.loads((TG/'TASKS.json').read_text())['tasks'];tasks=[]
for original in oldtasks:
 t=copy.deepcopy(original);t['schema']='bf-authoritative-development-task-v2';t['revision']=2;t['world_id']=wid;t['status']='development_spec_bound_admission_blocked';t['legacy_task_contract_id']=digest({k:v for k,v in original.items() if k not in ['reference_witness','qualification','status']})
 t['migration']={'source_world_id':oldid if t['task_id']=='DEV-COUPLING-01' else None,'acceptance_results_reused':False,'status':'requires_new_canonical_failure_snapshot' if t['task_id']=='DEV-COUPLING-01' else 'request_only_migrated_no_feasible_reference','forbidden':'Do not relabel legacy trajectories, outcomes or source-world design semantics as canonical evidence.'}
 t['computational_world_frozen']=True;t['requirements_owner_frozen']=False
 t['legacy_world_settings']=t['world'];t['world']={'world_id':wid,'input_id':digest(world['input']),'geometry_family':world['geometry']['family']}
 t.pop('new_dynamic_solves_authorized',None);t['execution_authority']='This scientific contract grants no execution permission; consult current user authorization.'
 if t['task_id']=='DEV-COUPLING-01':
  t['qualification']['cross_domain_bottleneck_observed']=False
  t['legacy_starting_state']={**t['starting_state'],'cross_domain_bottleneck_observed_in_legacy_world':True};t['starting_state']={'type':'canonical_failure_snapshot_required','case':None,'source_world_id':oldid,'legacy_case':'g42_ci0p1_co100_dt0125us','is_feasible':None}
 tasks.append(t)
write_json(ROOT/'contracts/tasks-v2.json',{'schema':'bf-authoritative-development-task-set-v2','world_id':wid,'formal_trial_admitted':False,'tasks':tasks})
write_json(ROOT/'contracts/identity.schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object','additionalProperties':False,'required':['schema','world_id','design_id','task_contract_id','model_id','solver_id','program_id','source_id','input_id','initial_state_id','initial_state_binding','continuation_checkpoint_id','experimental_unit','run_identity'],'properties':{'schema':{'const':'bf-run-identity-v1'},'continuation_checkpoint_id':{'type':['string','null'],'pattern':'^[0-9a-f]{64}$'},'initial_state_binding':{'enum':['realized_computational_state','recipe_only_not_run_evidence']},'experimental_unit':{'enum':['independent_design_run','same_state_continuation']},**{k:{'type':'string','pattern':'^[0-9a-f]{64}$'} for k in ['world_id','design_id','task_contract_id','model_id','solver_id','program_id','source_id','input_id','initial_state_id','run_identity']}}})
print(json.dumps({'world_id':wid,'legacy_world_id':oldid,'sources':len(registry['sources'])},indent=2))
