"""Current LC host binding and public projection; no execution on import.

S0 may call bind_inputs -> unchanged lcpv.simulate -> evaluate -> public_result.
Only current public Design/Profile and current private Task are consumed. The
generic independent evaluator contains no old qualification configurations.
"""
from copy import deepcopy
import math
from pathlib import Path
import json
from common import HERE,STUDY,SRC,digest,identity,module

PRIVATE=STUDY/'lcpv-private'
PUBLIC=STUDY/'shared/lcpv-task-public.json'
REVIEW=HERE.parents[1]/'stage3-e2main/a/readback_lcpv.py'


def load_public():
    frozen=json.loads((PRIVATE/'freeze.json').read_text())
    if digest(PUBLIC)!=frozen['public_file_sha256']:
        raise ValueError('LC_PUBLIC_TASK_BINDING_STOP')
    return json.loads(PUBLIC.read_text())


def validate_flat(public,design):
    domain=public['Task']['design_domain']
    if set(design)!=set(domain):
        raise ValueError('LC_DESIGN_FIELDS_OUTSIDE_CONTRACT')
    for key,spec in domain.items():
        value=design[key]
        if spec['kind']=='boolean':
            if type(value) is not bool:
                raise ValueError('LC_DESIGN_BOOLEAN:'+key)
        else:
            if type(value) not in (int,float) or not math.isfinite(value) or not spec['min']<=value<=spec['max']:
                raise ValueError('LC_DESIGN_DOMAIN:'+key)
            if spec['kind']=='integer' and type(value) is not int:
                raise ValueError('LC_DESIGN_INTEGER:'+key)
    if design['brownout_v']>=design['startup_v']:
        raise ValueError('LC_POWER_THRESHOLD_ORDER')


def bind_inputs(flat_design,public=None):
    public=load_public() if public is None else deepcopy(public)
    if identity(public)!=identity(load_public()):
        raise ValueError('LC_CURRENT_PUBLIC_TASK_REQUIRED')
    validate_flat(public,flat_design)
    frozen=json.loads((PRIVATE/'freeze.json').read_text())
    task_path=Path(frozen['host_task_path'])
    if digest(task_path)!=frozen['host_task_file_sha256'] or digest(SRC/'lcpv20261023.py')!=frozen['source_model_sha256']:
        raise ValueError('LC_FROZEN_WORLD_CHANGED_STOP')
    task=json.loads(task_path.read_text())
    # Low-level task_id denotes the original fixed consumer contract; the new
    # instance identity and full Task hash distinguish this scenario publicly.
    if task['instance_id']!=public['Task']['task_id'] or task['allowed_for_learning']:
        raise ValueError('LC_INSTANCE_OR_LEARNING_BOUNDARY')
    return {'schema':'pqe-lcpv-constructed-input-v1','name':public['Task']['task_id'],
            'Task':task,'Profile':deepcopy(public['Profile']),
            'Design':{k:deepcopy(flat_design[k]) for k in public['design_fields']},
            'Program':{**deepcopy(public['Task']['fixed_program_semantics']),
                       **{k:deepcopy(flat_design[k]) for k in public['program_fields']}},
            'purpose':'Current fixed LC development episode, allowed_for_learning=false; no old qualification or reference design.'}


def evaluate(inputs,raw):
    checker=module('e3lc_generic_independent_semantics',REVIEW)
    result=checker.review(inputs,raw)
    return {**result,'failures':sorted(k.upper() for k,v in result['gates'].items() if not v),
            'unknown':[],'allowed_for_learning':False,
            'evaluation_source':{'path':str(REVIEW),'sha256':digest(REVIEW)},
            'scope':'Current fixed LC development input; all unchanged service gates conjunctive in the constructed 1s world.'}


def scientific_sources():
    from bfworld.agentlab.pqe20261022 import lcpv20261023
    return lcpv20261023.dependency_identity()


def exact_cache_key(flat_design):
    return identity({'inputs':bind_inputs(flat_design),'scientific_sources':scientific_sources()})


def public_result(flat_design,inputs,raw,assessment,*,problem=None,wall_s=0.0):
    public=load_public()
    if raw['input_sha256']!=identity(inputs) or assessment['raw_result_sha256']!=raw['result_sha256']:
        raise ValueError('LC_PUBLIC_RESULT_BINDING_STOP')
    def record_view(record):
        return {k:deepcopy(v) for k,v in record.items() if k not in ('created_s','sample_index')}
    state=raw['final_state']
    state_view={k:deepcopy(state[k]) for k in ('powered','energy_j','sequence','pending','clock_synchronized')}
    state_view['phase']=state['phase']['kind'] if state['phase'] else None
    state_view['memory']=[record_view(r) for r in state['memory']]
    # There is no ideal air trajectory, latent sensor state or per-truth final
    # diagnostic here. Host-labeled event times do not add a device clock.
    return {'schema_version':'pqe-public-result-v2','world_kind':'LC-PV',
        'execution_status':raw['execution_status'],'task_id':public['Task']['task_id'],
        'task_sha256':identity(public['Task']),'input_sha256':identity(flat_design),
        'consumer_input_sha256':identity(inputs),'design':deepcopy(flat_design),
        'problem':deepcopy(problem if problem is not None else public['Problem']),
        'sources':{Path(k).name:v for k,v in scientific_sources().items()},'model_valid':True,'domain_errors':[],
        'program_version':raw['schema'],'engineering_model_sha256':identity(public['Profile']),
        'facts':{'trace':deepcopy(raw['energy_bins']),'activity':deepcopy(raw['activity']),
            'records':[record_view(r) for r in raw['records']],
            'packets':[{k:deepcopy(v) for k,v in p.items() if k!='sample_index'} for p in raw['packets']],
            'receiver_records':[{k:deepcopy(v) for k,v in r.items() if k!='sample_index'} for r in raw['receiver'] if r['accepted']],
            'samples':[{'host_observation_time_s':s['time_s'],'reading_c':s['reading_c']} for s in raw['samples']],
            'energy':deepcopy(assessment['independent_checks']['energy_totals_j']),
            'program_state':state_view,'reported_gap_markers':deepcopy(raw['gaps']),
            'observation_scope':'Powered quantized acquisition and host-labeled activity/supply/receiver facts only. Host observation time is not a retained unpowered device clock.'},
        'public_check':{'verdict':assessment['verdict'],'failures':assessment['failures'],'unknown':assessment['unknown'],
            'received_count':assessment['facts']['unique_accepted_samples']},
        'usage':{'paid_model_requests':0,'numerical_inputs':1,'wall_s':wall_s},
        'result_sha256':raw['result_sha256'],'allowed_for_learning':False}
