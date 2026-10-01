"""Fail-closed development-task admission. No simulation or participant execution.

This verifies source binding and trusted-operator evidence contracts. It cannot
prove reviewer independence, model adequacy or authenticity from a JSON boolean;
those claims require the separately bound independent audit artifacts.
"""
import argparse, hashlib, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ARMS=['Generic Agent','Domain-Guided Agent','Budget-Matched Search','BF-Design']
QUALIFICATION=['facts_frozen','allowed_design_space_complete','evaluator_qualified','reference_independently_feasible','numerical_and_native_evidence_complete','mechanical_boundary_resolved']
WITNESS_CHECKS=['design_in_allowed_space','numerical_convergence','energy_balance','native_artifact_binding','full_model_applicability','no_motion_control','weak_motion_case_pass','mechanical_initial_and_reset_accounting','complete_firmware_execution','action_attributed_receiver_event','no_parameter_only_firmware_energy_improvement']
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def file_hash(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def finite(x):return type(x) in (int,float) and math.isfinite(x)
def task_identity(task):
    # Stable scientific contract identity; attestation insertion cannot alter it.
    return digest({k:v for k,v in task.items() if k not in ['reference_witness','qualification','status']})
def check_sources(manifest):
    errors=[]
    for key,v in manifest.get('sources',{}).items():
        p=Path(v.get('path',''))
        if not p.is_file():errors.append('SOURCE_MISSING:'+key);continue
        if p.stat().st_size!=v.get('bytes') or file_hash(p)!=v.get('sha256'):errors.append('SOURCE_IDENTITY_MISMATCH:'+key)
    if not manifest.get('sources'):errors.append('SOURCE_MANIFEST_EMPTY')
    return errors
def check_evidence_file(ref,root):
    if not isinstance(ref,dict) or set(ref)!={'path','sha256'}:return 'EVIDENCE_REF_SCHEMA'
    p=Path(ref['path']);base=Path(root).resolve()
    if p.is_absolute() or '..' in p.parts:return 'EVIDENCE_PATH_DENIED'
    p=base/p
    if not p.resolve().is_relative_to(base) or p.is_symlink():return 'EVIDENCE_PATH_DENIED'
    if not p.is_file():return 'EVIDENCE_MISSING'
    if file_hash(p)!=ref['sha256']:return 'EVIDENCE_HASH_MISMATCH'
    return None
def validate_contract(task):
    errors=[]
    try:canonical(task)
    except (ValueError,TypeError):return ['NONFINITE_OR_NONJSON_CONTRACT']
    if task.get('schema')!='bf-development-task-contract-v1':errors.append('TASK_SCHEMA')
    if task.get('task_id') not in ['DEV-FEASIBLE-01','DEV-COUPLING-01']:errors.append('UNRECOGNIZED_TASK_ID')
    w=task.get('world',{});m=task.get('mission',{})
    expected={'excitation':'single_prescribed_door_open','opening_s':2.0,'open_angle_deg':65.0,'observation_s':4.0,'electrical_initial_V':0.0,'external_electrical_work_J':0.0,'repeat_operations_per_trial':1,'door_driver_closed_world_mm':[856,45,2140],'angle_profile':'linear_0_to_65_degrees_over_2_seconds_then_hold'}
    for k,v in expected.items():
        if w.get(k)!=v or (type(v) in (int,float) and not finite(w.get(k))) or (k=='repeat_operations_per_trial' and type(w.get(k))!=int):errors.append('WORLD_CONTRACT_CHANGED:'+k)
    expected_m={'minimum_received_events':1,'receiver_deadline_s':4.0,'single_open_cold_start_required':True,'no_motion_energy_max_J':1e-9,'correct_action_identity_required':True,'maximum_duplicate_events':0}
    for k,v in expected_m.items():
        bad_type=(type(v)==bool and type(m.get(k))!=bool) or (type(v)==int and type(m.get(k))!=int) or (type(v)==float and not finite(m.get(k)))
        if m.get(k)!=v or bad_type:errors.append('MISSION_CONTRACT_CHANGED:'+k)
    ad=task.get('allowed_design',{})
    if ad.get('all_main_arms')!=ARMS:errors.append('ARM_SET_CHANGED')
    rights=ad.get('permissions_per_arm',{})
    fields=['architecture_changes','mechanical_changes','circuit_changes','firmware_changes','cross_domain_changes','same_tool_access']
    if set(rights)!=set(ARMS) or any(any(rights.get(a,{}).get(f) is not True for f in fields) for a in ARMS):errors.append('UNEQUAL_OR_RESTRICTED_MAIN_ARMS')
    if task.get('acceptance',{}).get('inherited_numerical_targets')!={'max_rom_deflection_mm':8.0,'mesh_delta_pct':5.0,'time_step_energy_delta_pct':5.0}:errors.append('INHERITED_NUMERICAL_TARGETS_CHANGED')
    if task.get('evidence_tier')!='computational_development_only':errors.append('CLAIM_TIER_CHANGED')
    if task.get('formal_trials_authorized') is not False:errors.append('FORMAL_TRIALS_NOT_AUTHORIZED')
    if task.get('new_dynamic_solves_authorized') is not False:errors.append('DYNAMIC_RUNS_NOT_AUTHORIZED')
    if task.get('acceptance',{}).get('hardware_or_product_acceptance') is not False:errors.append('HARDWARE_CLAIM_FORBIDDEN')
    hold=task.get('holdout',{})
    if hold.get('all_current_sources_are_development_exposed') is not True:errors.append('DEVELOPMENT_LEAKAGE_BOUNDARY_LOST')
    return errors
def check_witness(task,witness,root):
    errors=[]
    if not isinstance(witness,dict):return ['NO_FEASIBLE_REFERENCE_WITNESS']
    if witness.get('schema')!='bf-independent-feasible-witness-v1':errors.append('WITNESS_SCHEMA')
    if witness.get('synthetic') is not False:errors.append('SYNTHETIC_OR_UNKNOWN_REFERENCE')
    if witness.get('task_contract_id')!=task_identity(task):errors.append('REFERENCE_CONTRACT_MISMATCH')
    if witness.get('world')!=task.get('world') or witness.get('mission')!=task.get('mission'):errors.append('REFERENCE_WORLD_OR_MISSION_MISMATCH')
    if witness.get('origin')!='independent_no_agent_reference':errors.append('REFERENCE_NOT_INDEPENDENT')
    if witness.get('design_space_id')!=digest(task['allowed_design']):errors.append('REFERENCE_DESIGN_SPACE_MISMATCH')
    if witness.get('diagnostic_only') is not False:errors.append('DIAGNOSTIC_NOT_FEASIBLE_REFERENCE')
    if witness.get('run_status')!='completed':errors.append('REFERENCE_RUN_NOT_COMPLETE')
    if witness.get('applicability')!='in_domain':errors.append('REFERENCE_NOT_IN_DOMAIN')
    for k in ['initial_electrical_energy_J','external_electrical_work_J']:
        v=witness.get(k)
        if not finite(v) or v!=0:errors.append('UNAUTHORIZED_ENERGY:'+k)
    metrics=witness.get('metrics',{})
    count=metrics.get('correct_nonduplicated_received_events')
    if type(count)!=int or count<task['mission']['minimum_received_events']:errors.append('REFERENCE_EVENT_FAIL')
    latency=metrics.get('first_correct_event_s')
    if not finite(latency) or not 0<=latency<=task['mission']['receiver_deadline_s']:errors.append('REFERENCE_DEADLINE_FAIL')
    if type(metrics.get('duplicate_events'))!=int or metrics.get('duplicate_events')!=0:errors.append('REFERENCE_DUPLICATE_FAIL')
    for k in WITNESS_CHECKS:
        if witness.get('checks',{}).get(k) is not True:errors.append('REFERENCE_CHECK_MISSING:'+k)
    refs=witness.get('evidence',{})
    for k in ['design','model_version','raw_run','independent_replay','reviewer_qualification','initial_reset_ledger','acceptance_result']:
        if k not in refs:errors.append('REFERENCE_EVIDENCE_MISSING:'+k)
        else:
            err=check_evidence_file(refs[k],root)
            if err:errors.append(err+':'+k)
    if not isinstance(witness.get('model_version_id'),str) or len(witness['model_version_id'])!=64:errors.append('MODEL_VERSION_ID_MISSING')
    return errors

def evaluate_task(task,root=ROOT):
    structural=validate_contract(task);blockers=[]
    if task.get('facts_status')!='frozen':blockers.append('FACTS_NOT_FROZEN')
    if task.get('scope_status')!='architecture_open_implemented_and_qualified':blockers.append('ARCHITECTURE_OPEN_PROVIDER_UNQUALIFIED')
    if task.get('mission',{}).get('weak_motion_case') is None:blockers.append('WEAK_MOTION_UNDEFINED')
    for k in QUALIFICATION:
        if task.get('qualification',{}).get(k) is not True:blockers.append('QUALIFICATION_MISSING:'+k)
    if task.get('task_id') in ['DEV-FEASIBLE-01','DEV-COUPLING-01']:
        specific=['ordinary_reference_feasible','not_constructed_to_require_recomposition'] if task['task_id']=='DEV-FEASIBLE-01' else ['cross_domain_bottleneck_observed','independent_successful_intervention','matched_patch_evidence_without_forced_synergy']
        for k in specific:
            if task.get('qualification',{}).get(k) is not True:blockers.append('QUALIFICATION_MISSING:'+k)
    blockers+=check_witness(task,task.get('reference_witness'),root)
    try:contract_id=task_identity(task)
    except (ValueError,TypeError):contract_id=None
    return {'task_id':task.get('task_id'),'contract_id':contract_id,'contract_valid':not structural,'structural_errors':structural,'admitted_for_development_participants':not structural and not blockers,'formal_launch_allowed':False,'blockers':blockers}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--output',type=Path);args=p.parse_args()
    tasks=json.loads((args.root/'TASKS.json').read_text());manifest=json.loads((args.root/'SOURCE-MANIFEST.json').read_text())
    source_errors=check_sources(manifest)
    receipts=[evaluate_task(t,args.root) for t in tasks['tasks']]
    report={'schema':'bf-development-admission-receipt-v1','source_identity_errors':source_errors,'admission_implementation':'trusted-operator evidence gate; no authenticity or physical-validity claim','source_integrity_pass':not source_errors,'contracts_valid':all(x['contract_valid'] for x in receipts),'admitted_task_count':sum(x['admitted_for_development_participants'] and not source_errors for x in receipts),'formal_launch_allowed':False,'new_scientific_solves':0,'tasks':receipts}
    if source_errors:
        for r in report['tasks']:r['admitted_for_development_participants']=False;r['blockers']+=source_errors
    s=json.dumps(report,indent=2,allow_nan=False)+'\n'
    if args.output:args.output.write_text(s)
    print(s,end='')
    # Honest blocked task readiness uses 2; 1 is malformed or changed source.
    return 1 if source_errors or not report['contracts_valid'] else (0 if report['admitted_task_count']==len(receipts) else 2)
if __name__=='__main__':raise SystemExit(main())
