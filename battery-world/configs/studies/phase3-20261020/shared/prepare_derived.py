"""One preregistered no-Agent baseline; no parameter search or provider call."""
from pathlib import Path
import importlib.util
import json
import sys
import time
import zlib

APP=Path(__file__).resolve().parents[4]
ROOT=APP.parents[2]
PLAN=ROOT/'docs/research/phase-plan-20261019/phase3'
OUT=Path.home()/'.local/share/bf-phase3-20261020'
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.campaign20261019.common import digest,file_hash,seal
from bfworld.agentlab.campaign20261019.phase1 import encoded
from bfworld.agentlab.campaign20261019.b import simulate_b

if __name__=='__main__':
    admission=json.loads((Path(__file__).parent/'derived-admission.json').read_text())
    if file_hash(PLAN/'matrix-preregistration.json')!=admission['matrix_preregistration_sha256']:
        raise ValueError('MATRIX_CHANGED_BEFORE_BASELINE')
    dest=OUT/'derived-baseline'
    if dest.exists():raise FileExistsError('ONE_BASELINE_NO_AUTOMATIC_RETRY')
    dest.mkdir();started=time.monotonic();task=admission['input'];seal(dest/'input.json',task)
    run=simulate_b(task)
    spec=importlib.util.spec_from_file_location('phase3_derived_reference',APP/'scripts/campaign_reference.py')
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    energy=checker.energy_reference(task,run['trace'],'b');reference=checker.reference_b(task,run,energy)
    integral=sum(s['power_w']*(s['end_s']-s['start_s']) for s in task['source_segments'])
    if energy['verdict']!='PASS' or abs(energy['source_integral_j']-integral)>1e-12:
        raise ValueError('DERIVED_NO_AGENT_ENERGY_GATE')
    (dest/'response.json.zlib').write_bytes(zlib.compress(encoded(run)))
    seal(dest/'observations.json',{k:v for k,v in run.items() if k!='trace'})
    frozen=json.loads((APP/'configs/studies/phase2-20261020/shared/case-registry.json').read_text())['frozen_scientific_files']
    key=digest({'task':task,'model':frozen,'checker_sha256':file_hash(APP/'scripts/campaign_reference.py')})
    value={'input_sha256':digest(task),'execution_key':key,'world':'clite-query-window-derived-v1',
           'design':{k:task['device'][k] for k in ('capacitance_f','tx_not_before_s')},
           'origin':'new-full-feedback-response','energy':energy,'reference':reference,
           'complete_service':'PASS' if all(reference['verdicts'][k]=='PASS' for k in
                ('independent_energy','independent_receiver','event_receive','deduplication','transient_voltage')) else 'FAIL',
           'physical_qualification':'UNKNOWN','raw_path':str(dest/'response.json.zlib')}
    seal(dest/'result.json',value)
    initial=json.loads((Path.home()/'.local/share/bf-phase2-20261020/cases/index.json').read_text())
    initial[key]={'origin':value['origin'],'result_path':str(dest/'result.json'),'result_sha256':file_hash(dest/'result.json'),
                  'input_sha256':value['input_sha256'],'artifacts':{str(p):file_hash(p) for p in dest.iterdir() if p.is_file()}}
    (OUT/'initial-cache.json').write_bytes(encoded(initial)+b'\n')
    derived=json.loads((APP/'configs/studies/phase3-20261020/interfaces/derived-case.json').read_text())
    tasks={w:{'legal_design_ranges':{'capacitance_f':[4e-6,22e-6],'tx_not_before_s':[0,.045]}}
           for w in ('b-pulse-fast','b-volatile-reset','b-latched-reset')}
    tasks['clite-query-window-derived-v1']={
        'legal_design_ranges':{k:[v['minimum'],v['maximum']] for k,v in derived['legal_design_space'].items()},
        'derived_assets':{p.name:{'path':str(p),'sha256':file_hash(p)} for p in dest.iterdir() if p.is_file()},
        'query_protocol':admission['query_wire_contract'],
        'claim_boundary':derived['claim_boundary'],'missing_measurements':derived['missing_measurements']}
    seal(Path(__file__).parent/'tasks.json',{'schema_version':'bf-phase3-task-registry-v1','tasks':tasks})
    seal(PLAN/'baseline-preparation.json',{'status':'PASS','provider_requests':0,'new_scientific_executions':1,
        'wall_s':time.monotonic()-started,'source_integral_j':energy['source_integral_j'],
        'initial_cache_sha256':file_hash(OUT/'initial-cache.json'),'initial_entries':len(initial),
        'raw_response_sha256':file_hash(dest/'response.json.zlib'),'baseline_service':value['complete_service'],
        'nonce_scope':'Predeclared virtual single-query seq mapping only; no multiquery nonce security',
        'preparation_source_sha256':file_hash(Path(__file__))})
    print('No-Agent derived baseline sealed; energy PASS; one new digital simulation; zero provider calls.')
