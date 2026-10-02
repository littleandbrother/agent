"""Immutable capsule files and append-only, hash-linked lifecycle decisions.

The qualifier role is an API boundary, not authentication on the developer host.
Formal deployment must place the qualifier in a separate trusted process.
"""
import json
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash,file_hash,write_canonical_json

TRANSITIONS={'PROPOSED':{'EXPLANATION_VALIDATED','REJECTED'},'EXPLANATION_VALIDATED':{'USE_VALIDATED','REJECTED'},
 'USE_VALIDATED':{'PROMOTED','REJECTED'},'PROMOTED':{'RESTRICTED','SUPERSEDED'},'RESTRICTED':{'SUPERSEDED','REJECTED'},'REJECTED':set(),'SUPERSEDED':set()}

def create_capsule(root:Path,parameters:dict,sources:list[str])->dict:
    if not sources or not all(s.startswith('sha256:') for s in sources):raise ValueError('source run identities required')
    program=Path(__file__).with_name('burst_program.py').read_text()
    manifest={'schema_version':'executable-knowledge-v1','id':'empirical-burst-guard','version':1,
      'knowledge_type':'prediction-model','program':'program.py','program_hash':canonical_hash(program),
      'parameters':parameters,'source_experiments':sources,
      'input_contract':{'design':['capacitance_f','esr_ohm','tx_power_w','release_s'],
         'condition':['initial_v','off_v','harvest_during_burst','signal_program']},
      'applicability_domain':'precharged no-harvest burst; C 300–4700 µF, ESR 0–18 Ω, initial 2.6–3.1 V, TX 20–65 mW, release 20–100 ms, fixed action program',
      'uncertainty':{'explanation_tolerance_v':.08,'admission_margin_v':.02,'not_calibrated_probability':True},
      'known_failures':['active harvesting not supported','different model/sampling programs not supported','not a correctness or receiver predictor'],
      'acquisition_method':'classical action-load estimation from executed reference trace; template authored by developer coding agent',
      'claim_boundary':'computational-reference qualification only; not autonomous scientific discovery or hardware law'}
    manifest['content_hash']=canonical_hash(manifest)
    destination=root/manifest['content_hash'].split(':')[1]
    if destination.exists():verify_capsule(destination);return {'path':str(destination),'manifest':manifest}
    destination.mkdir(parents=True)
    (destination/'program.py').write_text(program)
    write_canonical_json(destination/'parameters.json',parameters)
    write_canonical_json(destination/'manifest.json',manifest)
    verify_capsule(destination)
    return {'path':str(destination),'manifest':manifest}

def verify_capsule(root:Path)->dict:
    manifest=json.loads((root/'manifest.json').read_text())
    if canonical_hash({k:v for k,v in manifest.items() if k!='content_hash'})!=manifest['content_hash']:raise ValueError('capsule manifest tamper')
    if canonical_hash((root/'program.py').read_text())!=manifest['program_hash']:raise ValueError('capsule program tamper')
    if json.loads((root/'parameters.json').read_text())!=manifest['parameters']:raise ValueError('capsule parameter tamper')
    return manifest

def transition(log:list[dict],candidate_hash:str,state:str,evidence:dict,*,role:str='participant')->list[dict]:
    if role!='qualifier':raise ValueError('participant cannot promote knowledge')
    prior=[e for e in log if e['candidate_hash']==candidate_hash]
    before=prior[-1]['state'] if prior else 'PROPOSED'
    if state not in TRANSITIONS[before]:raise ValueError('invalid lifecycle transition')
    if state in ('EXPLANATION_VALIDATED','USE_VALIDATED','PROMOTED') and not evidence.get('passed'):raise ValueError('passing independent receipt required')
    if evidence.get('candidate_hash')!=candidate_hash:raise ValueError('qualification identity mismatch')
    if state=='PROMOTED' and (not evidence.get('explanation_hash') or not evidence.get('use_hash')):raise ValueError('dual validation receipts required')
    event={'sequence':len(log),'previous_hash':log[-1]['event_hash'] if log else None,'candidate_hash':candidate_hash,
           'state':state,'evidence':evidence,'authority':'reference qualifier; not participant','scope':'computational reference only'}
    event['event_hash']=canonical_hash(event)
    return [*log,event]

def verify_lifecycle(log:list[dict])->None:
    previous=None
    for index,event in enumerate(log):
        if event['sequence']!=index or event['previous_hash']!=previous or canonical_hash({k:v for k,v in event.items() if k!='event_hash'})!=event['event_hash']:raise ValueError('lifecycle chain tamper')
        previous=event['event_hash']
