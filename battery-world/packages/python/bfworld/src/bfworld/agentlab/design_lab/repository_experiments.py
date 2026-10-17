"""Frozen method studies; independent public calibration precedes model runs."""
import copy
import json
from pathlib import Path
from ..store import canonical,identity
from .repository import file_hash
from .repository_actions import object_save
from .repository_contracts import check,VERSION

CONDITIONS=("generic-agent","single-bf","fixed-specialists","contract-integration","adaptive-decomposition")
POLICIES={
 "generic-agent":{"initial_roles":["generalist"],"method":"generic engineering instructions"},
 "single-bf":{"initial_roles":["BF"],"method":"domain skills and state recovery"},
 "fixed-specialists":{"initial_roles":["Lead","Power","Firmware"],"method":"fixed domain handoff"},
 "contract-integration":{"initial_roles":["Lead","Power","Firmware"],"method":"immutable commits and interface dependencies"},
 "adaptive-decomposition":{"initial_roles":["Lead","Power","Firmware"],"method":"contracts with public failure-driven scope revision"}}


def register(repo,owner,body,operator):
    if not operator:raise PermissionError('INDEPENDENT_EXPERIMENT_REGISTRATION_REQUIRED')
    p=repo.leader(body['project_id'],owner);s=repo.system(p['id'],body['system_id'])
    if not body.get('hypothesis') or not body.get('falsifier'):raise ValueError('EXPERIMENT_HYPOTHESIS_FALSIFIER_REQUIRED')
    from .repository_controller import freeze
    harness,method=freeze(repo.lab)
    from ..model_profile import for_owner
    with repo.store.connect() as db:model=for_owner(db,owner)
    source_paths=[Path(__file__).with_name(n) for n in ('repository.py','repository_actions.py','repository_controller.py','repository_execution.py','repository_contracts.py')]
    apparatus={'code':{q.name:file_hash(q) for q in source_paths},'environment':repo.profile['sha256'],
      'model':model,'input':identity({k:v['sha256'] for k,v in s['files'].items()}),
      'evaluator':{'version':VERSION,'sha256':file_hash(Path(__file__).with_name('repository_contracts.py'))},
      'tools':method['tools'],'harness':method['harness_id'],'required_gates':p['requirements']['required_gates']}
    value={'project_id':p['id'],'target':s['id'],'title':body.get('title','P01 V2 fixed-environment method comparison'),
        'hypothesis':body['hypothesis'],'falsifier':body['falsifier'],'status':'PLANNED',
        'conditions':[{'id':k,**POLICIES[k],'same_apparatus':identity(apparatus)} for k in CONDITIONS],
        'apparatus':apparatus,'cost_policy':'user-authorized unbounded; every request and intervention recorded',
        'metrics':['full_system_completion','invalid_experiments','cross_domain_rework','external_interventions','total_cost'],
        'paired_seeds':[1,2,3],'results':[],'scope':'full product comparison; no results until real qualified runs',
        'adoption':'independent comparison required','physical':'NOT_TESTED'}
    return repo.mutate(owner,body,lambda db:object_save(repo,db,'design_method_experiments','EXP',value,['project_id','status']))


def qualify(repo,owner,body,operator):
    if not operator:raise PermissionError('INDEPENDENT_EVALUATOR_REQUIRED')
    p=repo.leader(body['project_id'],owner)
    with repo.store.connect() as db:experiment=repo._object(db,'design_method_experiments',body['experiment_id'],p['id'])
    s=repo.system(p['id'],experiment['target'])
    if experiment['apparatus']['environment']!=repo.profile['sha256']:raise ValueError('EXPERIMENT_ENVIRONMENT_DRIFT')
    checker=Path(__file__).with_name('repository_contracts.py')
    if experiment['apparatus']['evaluator']['sha256']!=file_hash(checker):raise ValueError('EXPERIMENT_EVALUATOR_DRIFT')
    texts={}
    for path in ('project-fw-s132/main.c','project-chain/load-timeline.json','project-chain/interface-params.json'):
        file,ref=repo.artifact(p['id'],owner,s['id'],path);texts[path]=file.read_text()
    refs=s['files'];controls=[]
    actual=check(lambda path:texts[path],refs)
    controls.append({'name':'exact-current-source','observed':actual['status'],'expected':'PASS'})
    for field,value in [('advertising_period_ms',5000),('connection_period_ms_used',5000),('sample_period_ms',1)]:
        changed=dict(texts);load=json.loads(changed['project-chain/load-timeline.json']);load['actual_radio_timing'][field]=value
        changed['project-chain/load-timeline.json']=canonical(load)
        r=check(lambda path:changed[path],refs)
        controls.append({'name':'injected-'+field,'observed':r['status'],'expected':'FAIL','input_sha256':identity(changed)})
    r=check(lambda path:'unsupported source',refs)
    controls.append({'name':'unsupported-firmware-expression','observed':r['status'],'expected':'UNEVALUABLE'})
    bad={'interface':actual['facts']['firmware'],'sources':[{'path':'project-fw-s132/main.c','sha256':'stale'}]}
    r=check(lambda path:texts[path],refs,{'firmware':bad})
    controls.append({'name':'stale-source-hash','observed':r['status'],'expected':'FAIL'})
    result={'project_id':p['id'],'target':s['id'],'kind':'experiment-apparatus-calibration',
        'experiment_id':experiment['id'],'status':'PASS' if all(c['observed']==c['expected'] for c in controls) else 'FAIL',
        'controls':controls,'input_sha256':experiment['apparatus']['input'],'evaluator':experiment['apparatus']['evaluator'],
        'model_calls':0,'native_jobs':0,'scope':'independent evaluator calibration','method_results':[]}
    return repo.mutate(owner,body,lambda db:object_save(repo,db,'design_repository_validations','RV',result,['project_id','target','kind']))


def handle(repo,owner,body,operator):
    if body['action']=='repository_experiment_register':return register(repo,owner,body,operator)
    if body['action']=='repository_experiment_qualify':return qualify(repo,owner,body,operator)
    return None
