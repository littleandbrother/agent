"""Complete public physics for v2; no modulo aliases or private truth feedback."""
from __future__ import annotations
from dataclasses import asdict
from bfworld.kernel.canonical import canonical_hash
from bfworld.coupled.engine import Design, Reference, MODEL
from bfworld.coupled.profiled import LoadProfile, VERSION, validate_inputs, execute
from .splits import task_record, validate_registry

SOURCE_FIELDS={'rpm','pole_pairs','source_peak_a','source_r_ohm','source_phase_rad','surge_after_s','surge_multiplier'}
INITIAL_FIELDS={'duration_s','dt_s','initial_v','leakage_r_ohm','efficiency','off_v','max_v'}

def physics_for(designs,ref:Reference,load:LoadProfile):
    for d in designs.values():validate_inputs(d,ref,load)
    r=asdict(ref)
    return {'source':{'family':'rotary',**{k:r[k] for k in sorted(SOURCE_FIELDS)}},
        'initial_state':{k:r[k] for k in sorted(INITIAL_FIELDS)},'load_profile':asdict(load),
        'receiver':{'loss':ref.receiver_loss,'device_session':ref.device_session},
        'model_card':MODEL,'label':ref.fault,'deadline_s':ref.deadline_s,
        'candidate_designs':[{'id':k,**asdict(v)} for k,v in designs.items()],
        'reference_version':VERSION}

def materialize(record):
    expected=task_record(record['task_id'],record['split'],record['physics'],
                         prior_exposure=record['prior_exposure'],regression_of=record['regression_of'])
    if expected!=record:raise ValueError('task identity mismatch')
    p=record['physics']
    if p['reference_version']!=VERSION or p['source'].get('family')!='rotary' or p['model_card']!=MODEL:
        raise ValueError('unsupported source/reference/information model')
    if set(p['source'])!={'family'}|SOURCE_FIELDS or set(p['initial_state'])!=INITIAL_FIELDS or set(p['receiver'])!={'loss','device_session'}:
        raise ValueError('exact explicit component fields required')
    if set(p['load_profile'])!=set(asdict(LoadProfile())):
        raise ValueError('all load-profile fields must be explicit')
    ids=[x.get('id') for x in p['candidate_designs']]
    if any(not isinstance(x,str) or not x for x in ids) or len(ids)!=len(set(ids)):
        raise ValueError('unique public candidate IDs required')
    if any(set(x)!={'id'}|set(asdict(Design())) for x in p['candidate_designs']):
        raise ValueError('all design fields must be explicit')
    ref=Reference(**{k:p['source'][k] for k in SOURCE_FIELDS},**p['initial_state'],deadline_s=p['deadline_s'],
                  fault=p['label'],receiver_loss=p['receiver']['loss'],device_session=p['receiver']['device_session'])
    load=LoadProfile(**p['load_profile'])
    designs={x['id']:Design(**{k:v for k,v in x.items() if k!='id'}) for x in p['candidate_designs']}
    for d in designs.values():validate_inputs(d,ref,load)
    return designs,ref,load

def public_context(record):
    materialize(record)
    p=record['physics']
    # Ground-truth label and receiver outcome are deliberately not exposed to the
    # electrical predictor. Public protocol exposes the receiver model, not its result.
    return {'schema_version':'profiled-predictor-context-v2','source_family':'rotary',
        'task_id':record['task_id'],'environment_hash':record['environment_hash'],
        'conditions':{**p['initial_state'],'deadline_s':p['deadline_s']},'source':p['source'],
        'load_profile':p['load_profile'],'model_card':p['model_card'],'candidates':p['candidate_designs']}

def execute_candidate(record,candidate_id):
    designs,ref,load=materialize(record)
    if candidate_id not in designs:raise ValueError('unknown candidate')
    return execute(designs[candidate_id],ref,load)

def verify_record(record):
    materialize(record)
    return {'status':'pass','task_hash':record['content_hash'],'public_context_hash':canonical_hash(public_context(record))}
