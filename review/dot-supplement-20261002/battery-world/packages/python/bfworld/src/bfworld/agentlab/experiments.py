"""Trusted task selection, immutable uploads and public result projection."""
import hashlib
import json
import os
from dataclasses import asdict, replace
from pathlib import Path

from bfworld.campaign.sandbox import execute as sandbox_policy
from bfworld.coupled.engine import Design, Reference
from bfworld.coupled.profiled import LoadProfile
from . import programmed
from .store import canonical, identity

BASELINE_POLICY = '''def plan(obs):
    if obs['time_s'] < obs['requirements']['release_s']:
        return {'action':'wait','duration_s':0.02}
    for action in ['sense','infer','report']:
        if action not in obs['completed_actions']:
            return {'action':action}
    return {'action':'wait','duration_s':0.1}
'''
BASELINE_DESIGN = asdict(Design(capacitance_f=.001, clamp_v=None))

# Explicitly declared variants of the existing computational task. Labels and
# future source values stay in this service; participants get requirements only.
VARIANTS = {
    'dev-01': ({}, {}),
    'dev-02': ({'source_peak_a':.0024}, {}),
    'dev-03': ({'source_phase_rad':1.2}, {}),
    'dev-04': ({'receiver_loss':True}, {}),
    'dev-05': ({'deadline_s':.15}, {'infer_power_w':.012}),
    'dev-06': ({'initial_v':2.4}, {}),
    'dev-07': ({'source_peak_a':.0045,'surge_after_s':.7,'surge_multiplier':2.}, {}),
    'dev-08': ({'rpm':85.,'dt_s':.0005}, {'sense_duration_s':.12}),
    'transfer-01': ({'source_peak_a':.0028,'source_phase_rad':.6,'rpm':100.}, {'infer_duration_s':.045}),
    'transfer-02': ({'source_phase_rad':2.1,'initial_v':2.5,'deadline_s':.85}, {'tx_duration_s':.05}),
}


def task(task_id):
    if task_id not in VARIANTS:
        raise ValueError('UNKNOWN_TASK')
    baseline={**BASELINE_DESIGN}
    if task_id=='dev-02':baseline['clamp_v']=3.4
    if task_id=='dev-03':baseline.update({'model_threshold':10000,'clamp_v':3.4})
    return {'task_id':task_id, 'family':'programmable-computational-bfaiot-v3','contract_version':'bf-task-20260917-v1',
            'requirements':{'receiver_delivery':True,'quality_min':.7,'deadline_s':VARIANTS[task_id][0].get('deadline_s',1.1),
                            'max_voltage_v':3.6,'flash_limit_bytes':65536,'sram_limit_bytes':16384,'max_capacitance_f':.0047},
            'fidelity':'F1-synthetic-declared-state-load', 'hardware':False, 'trained_model':False,
            'design_fields':list(BASELINE_DESIGN),'baseline_design':baseline,'baseline_policy':BASELINE_POLICY,
            'design_domain':{'tx_power_w':[.018,.06],'esr_ohm':[.1,20.],'flash_bytes':8192,'sram_bytes':2048},
            'required_assets': [{'kind':'TFLite-trained-model','status':'NOT_AVAILABLE','artifact_hash':None}] if task_id=='dev-07' else [],
            'policy_contract':'Python plan(obs) returns action wait/sense/infer/report; wait duration_s >= .001. Each invocation is isolated and stateless. Only completed actions, current energy/voltage, timing and public requirements enter obs. Maximum 96 decisions.',
            'claim_boundary':'Existing synthetic signal/classifier and profiled electrical model; no TFLite, ELF, measured replay or hardware claim.'}


def validate_files(files):
    if not isinstance(files,dict) or set(files)!={'design.json','policy.py'}:
        raise ValueError('EXACT_DESIGN_AND_POLICY_FILES_REQUIRED')
    if any(not isinstance(v,str) for v in files.values()) or sum(len(v.encode()) for v in files.values())>30000:
        raise ValueError('UPLOAD_SIZE')
    design=json.loads(files['design.json'])
    if not isinstance(design,dict) or set(design)!=set(BASELINE_DESIGN):
        raise ValueError('DESIGN_SCHEMA_FIELDS')
    obj=Design(**design)
    if not .018<=obj.tx_power_w<=.06 or not .1<=obj.esr_ohm<=20. or obj.flash_bytes!=8192 or obj.sram_bytes!=2048:
        raise ValueError('DESIGN_OUTSIDE_DECLARED_TASK_DOMAIN')
    programmed.validate_inputs(obj,Reference(),LoadProfile())
    compile(files['policy.py'],'policy.py','exec')
    return obj


def snapshot(root,files):
    validate_files(files)
    digest=identity(files); dest=Path(root)/'snapshots'/digest
    if not dest.exists():
        dest.mkdir(parents=True)
        for name,value in files.items():
            path=dest/name;path.write_text(value);path.chmod(0o444)
        (dest/'manifest.json').write_text(canonical({'snapshot_id':digest,'files':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items()}}))
        (dest/'manifest.json').chmod(0o444)
    read_snapshot(root,digest)
    return digest


def read_snapshot(root,digest):
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('INVALID_SNAPSHOT_ID')
    dest=Path(root)/'snapshots'/digest
    files={name:(dest/name).read_text() for name in ['design.json','policy.py']}
    if identity(files)!=digest:raise ValueError('SNAPSHOT_HASH_MISMATCH')
    return files


def run(root,task_id,snapshot_id,cancel=lambda:False):
    task(task_id)
    files=read_snapshot(root,snapshot_id);design=validate_files(files)
    if task_id=='dev-07':
        raise ValueError('NOT_EVALUATED_REQUIRED_TFLITE_ASSET_UNAVAILABLE_NO_SYNTHETIC_FALLBACK')
    ref_fields,load_fields=VARIANTS[task_id]
    ref=replace(Reference(),**ref_fields);load=replace(LoadProfile(),**load_fields)
    def policy(obs):
        if cancel():raise InterruptedError()
        return sandbox_policy(files['policy.py'],obs,Path(root)/'policy-workers')
    result=programmed.execute(design,ref,load,policy)
    programmed.verify(result,reproduce=True)
    run_id='run-'+identity({'snapshot_id':snapshot_id,'task_id':task_id,'content_hash':result['content_hash']})
    dest=Path(root)/'runs'/run_id;dest.mkdir(parents=True,exist_ok=True)
    facts=result['physical_mission_pass']
    public={'schema_version':'bf-agent-public-result-v1','task_id':task_id,'run_id':run_id,
        'snapshot_id':snapshot_id,'execution_status':'SUCCEEDED','design_status':'PASS' if facts['value'] else 'FAIL',
        'fidelity':'F1-synthetic-declared-state-load','hardware_result':False,'agent_result':False,
        'checks':facts,'summary':result['summary'],'energy_ledger':result['energy_ledger'],
        'request':{'sample_count':len(result['request']['samples']),'prediction':result['request']['prediction'],
          'transmit_s':result['request']['transmit_s'],'receive_s':result['request']['receive_s']},
        'decisions':result['policy_decisions'],'channels':result['rows'][::8],
        'design':asdict(design),'policy':files['policy.py'],
        'description':result['claim_boundary'],'model_calls':0,
        'artifacts':['public-result.json','policy-decisions.json','design.json','policy.py']}
    public['bundle_hash']=identity(public)
    artifacts={name:canonical(value) for name,value in [('run.private.json',result),('public-result.json',public),('policy-decisions.json',result['policy_decisions'])]}
    artifacts.update(files)
    for name,value in artifacts.items():
        artifact=dest/name
        if artifact.exists():
            if artifact.read_text()!=value:raise ValueError('IMMUTABLE_RUN_ARTIFACT_MISMATCH')
        else:
            artifact.write_text(value);artifact.chmod(0o444)
    return public


def main():
    import sys
    root,task_id,snapshot_id=sys.argv[1:]
    print(canonical(run(root,task_id,snapshot_id)))


if __name__=='__main__':main()
