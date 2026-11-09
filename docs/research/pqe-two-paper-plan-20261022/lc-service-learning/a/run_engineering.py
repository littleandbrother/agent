"""Frozen sequential whole-design batch. No result-dependent edits or retries."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

A = Path(__file__).resolve().parent
ROOT = A.parents[4]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
SRC = CAN / 'packages/python/bfworld/src'
sys.path.insert(0, str(SRC))
from bfworld.agentlab.pqe20261024lc import engineering
from bfworld.agentlab.pqe20261023bold import lc_adapter, consumer
from bfworld.agentlab.pqe20261022 import e3lc_lc, lcpv20261023, executor

PACKAGE = 'BF-PQE-LC-SERVICE-LEARNING-20261024-001'
SCIENTIFIC = ('Task', 'Profile', 'Design', 'Program')


def now():
    return datetime.now(timezone.utc).isoformat()


def read(p):
    return json.loads(Path(p).read_text())


def ref(p):
    p = Path(p).resolve()
    data = p.read_bytes()
    return {'path': str(p), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def checked(r):
    actual = ref(r['path'])
    assert all(actual[k] == v for k, v in r.items()), ('REFERENCE_CHANGED', r['path'])
    return read(r['path'])


def save(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(value, f, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        f.write('\n')


def append(value):
    with (A / 'DISPATCH.jsonl').open('a') as f:
        f.write(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n')
        f.flush()
        os.fsync(f.fileno())


def rows():
    p = A / 'DISPATCH.jsonl'
    return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []


def retained(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


def capacity():
    free = shutil.disk_usage(ROOT).free
    sizes = {'a_bytes': retained(A), 'package_bytes': retained(A.parent)}
    assert free >= 11_000_000_000, ('CAPACITY', free)
    assert sizes['a_bytes'] < 100_000_000, sizes
    assert sizes['package_bytes'] < 150_000_000, sizes
    return {'free_bytes': free, **sizes}


def context(entry):
    return {k: checked(entry[k]) for k in ('public', 'host_task')}


def decision(case):
    return {'selected_id': case['id'], 'actual_input': {'operation': 'edit',
            'design_patch': deepcopy(case['design']), 'problem_patch': {}}}


def lc_readback(output):
    inp, raw, assessment, public = [read(output / name) for name in ('input.json', 'raw.json', 'assessment.json', 'public-result.json')]
    assert lcpv20261023.identity(inp) == raw['input_sha256'] == assessment['input_sha256']
    assert raw['result_sha256'] == lcpv20261023.identity({k:v for k,v in raw.items() if k != 'result_sha256'})
    assert assessment['raw_result_sha256'] == public['result_sha256'] == raw['result_sha256']
    assert raw['sources'] == lcpv20261023.dependency_identity()
    assert public['public_check']['verdict'] == assessment['verdict']
    assert public['model_valid'] is True
    assert checked_source(assessment['evaluation_source'])
    return {'at_utc': now(), 'stored_input_raw_result_assessment_bindings': True,
            'scientific_sources_current': True, 'evaluator_source_current': True,
            'independent_evaluation': 'Original stdlib reviewer executed by unchanged host.evaluate during full call; stored facts and hashes read back here.',
            'files': {n:ref(output/n) for n in ('input.json','raw.json','assessment.json','public-result.json')}}


def checked_source(r):
    actual = ref(r['path'])
    return all(actual[k] == v for k,v in r.items())


def freeze():
    assert not (A / 'ENGINEERING-FREEZE.json').exists()
    assert not rows(), 'Cannot freeze after dispatch'
    dev = read(A / 'DEVELOPMENT-TASKS.json')
    parent = context(dev['entries'][0])['public']['Design']
    cases = engineering.cases(parent)
    reuse = []
    for entry in dev['entries']:
        ctx = context(entry)
        assert ctx['public']['Design'] == parent
        task = engineering.participant_task(ctx['public'])
        for case in cases:
            lc_adapter.bind_inputs(task, case['design'], ctx)
        expected = lc_adapter.bind_inputs(task, parent, ctx)
        output = Path(entry['original_initial'])
        old = read(output / 'input.json')
        assert all(expected[k] == old[k] for k in SCIENTIFIC), 'No approximate reuse'
        raw, assessment, public = [read(output/n) for n in ('raw.json','assessment.json','public-result.json')]
        assert raw['sources'] == lcpv20261023.dependency_identity()
        host, _ = e3lc_lc.support()
        assert host.evaluate(old,raw) == assessment, 'Stored independent assessment mismatch'
        assert public['design'] == parent
        assert public['result_sha256'] == raw['result_sha256']
        assert all(public['sources'][k] == v for k,v in engineering.scientific_identity().items() if k in public['sources'])
        reuse.append({'entry_id':entry['id'], 'scientific_fields_exact':list(SCIENTIFIC),
            'scientific_identity':lcpv20261023.identity({k:old[k] for k in SCIENTIFIC}),
            'metadata_difference':{k:{'original':old.get(k),'current_binding':expected.get(k)} for k in expected if expected.get(k)!=old.get(k)},
            'original_unchanged':True,'new_full_inputs':0,'saved_fact_review_cheap_checks':1,
            'files':{n:ref(output/n) for n in ('input.json','raw.json','assessment.json','public-result.json')},
            'evaluation_source':assessment['evaluation_source']})
    save(A / 'ENGINEERING-FREEZE.json', {'schema':'lc-whole-design-freeze-v1','package':PACKAGE,
        'at_utc':now(),'development':ref(A/'DEVELOPMENT-TASKS.json'),'cases':cases,'reuse':reuse,
        'scientific_identity':engineering.scientific_identity(),'door_consumer_identity':consumer.source_identity(),
        'engineering_module':ref(engineering.__file__),'runner':ref(__file__),
        'necessary_bounds':ref(A/'NECESSARY-BOUNDS.json'),'storage':capacity(),
        'new_full_engineering_cap':8,'engineering_cells':8,'planned_reused_cells':2,
        'planned_new_engineering_full':6,'new_initial_cap_each':1,'A_new_full_cap':10,
        'per_full_wall_cap_s':120,'A_total_full_wall_cap_s':1200,
        'A_retained_cap_bytes':100_000_000,'package_retained_cap_bytes':150_000_000,
        'cheap_checks':10,'model_requests':0,'unused_quota_transfer':False,
        'change_after_results':False,'scientific_semantics_change':False,
        'reuse_equality':'Exact Task/Profile/Design/Program, raw source hashes, saved independent assessment replay. Original name/schema/purpose remain attached; descriptive purpose is not a scientific parameter.'})
    print(json.dumps({'frozen':ref(A/'ENGINEERING-FREEZE.json'),'new_full':0,'cheap_checks':10}))


def frozen():
    f = read(A / 'ENGINEERING-FREEZE.json')
    assert checked_source(f['engineering_module']) and checked_source(f['runner'])
    assert engineering.scientific_identity() == f['scientific_identity']
    assert consumer.source_identity() == f['door_consumer_identity']
    checked(f['development']); checked(f['necessary_bounds'])
    return f


def child(spec_path):
    spec=read(spec_path); frozen()
    output=Path(spec['output'])
    if spec['world']=='LC-PV':
        ctx=context(spec['entry']); pub=ctx['public'];task=engineering.participant_task(pub)
        engineering.execute_lc(task,pub['Design'],pub['Problem'],decision(spec['case']),output,
                              lambda identifier: task if identifier==task['task_id'] else None,ctx)
        save(output/'readback.json',lc_readback(output))
    else:
        task=checked(spec['task']);d=task['initial_design'];p=task['initial_problem']
        consumer.execute(task,d,p,{'actual_input':{'operation':'verify','design_patch':{},'problem_patch':{}}},
                         output,task_resolver=lambda identifier:task if identifier==task['task_id'] else None)
        # Keep canonical facts but remove pretty-print expansion before refs are sealed.
        for name in ('decision.json','raw.json','assessment.json','public-result.json'):
            path=output/name;value=read(path)
            path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
        save(output/'input.json',{'Task':task,'Design':d,'Problem':p,'consumer_sources':consumer.source_identity()})
        raw,assessment,public=[read(output/n) for n in ('raw.json','assessment.json','public-result.json')]
        assert raw['result_sha256']==executor.identity({k:v for k,v in raw.items() if k!='result_sha256'})
        assert public['result_sha256']==raw['result_sha256'] and public['public_check']['verdict']==assessment['verdict']
        assert public['sources']==consumer.source_identity()
        save(output/'readback.json',{'at_utc':now(),'stored_raw_and_public_binding':True,'independent_assessment_during_full':True,
            'files':{n:ref(output/n) for n in ('input.json','raw.json','assessment.json','public-result.json')}})


def dispatch(spec,stage):
    f=frozen(); previous=rows(); ident=spec['id']
    assert not any(r['id']==ident for r in previous), ('NO_RETRY',ident)
    reserves=[r for r in previous if r['state']=='RESERVED']
    assert len(reserves)<f['A_new_full_cap']
    assert sum(r['stage']==stage for r in reserves)<(8 if stage=='engineering' else 2)
    used=sum(r.get('wall_s',0) for r in previous if r['state'] in ('FINISHED','STOPPED'))
    assert used+120 <= f['A_total_full_wall_cap_s']
    cap=capacity(); spec_path=A/('dispatch' if stage=='engineering' else 'host/dispatch')/(ident+'.json')
    save(spec_path,spec)
    append({'at_utc':now(),'id':ident,'stage':stage,'state':'RESERVED','reserved_full_inputs':1,
            'reserved_wall_s':120,'spec':ref(spec_path),'storage':cap})
    start=time.monotonic();result=None;error=None
    try:
        result=subprocess.run([sys.executable,'-B',__file__,'_child',str(spec_path)],cwd=ROOT,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=120)
        if result.returncode: error={'kind':'CHILD_FAILED','returncode':result.returncode,'stderr':result.stderr[-8000:]}
    except subprocess.TimeoutExpired:
        error={'kind':'FULL_TIMEOUT','limit_s':120}
    elapsed=time.monotonic()-start
    receipt={'at_utc':now(),'id':ident,'stage':stage,'state':'STOPPED' if error else 'FINISHED',
            'new_full_inputs':1,'wall_s':elapsed,'error':error,'output':spec['output'],'storage':capacity()}
    append(receipt)
    assert not error,error
    return receipt


def cell_record(entry,case,output,reused,receipt=None):
    ass=read(output/'assessment.json');pub=read(output/'public-result.json')
    return {'id':case['id']+'--'+entry['id'],'case_id':case['id'],'entry_id':entry['id'],
        'design':case['design'],'reused':reused,'new_full_inputs':0 if reused else 1,
        'verdict':ass['verdict'],'model_valid':pub['model_valid'],'gates':ass['gates'],
        'service_facts':ass['facts'],'independent_checks':ass['independent_checks'],
        'files':{n:ref(output/n) for n in ('input.json','raw.json','assessment.json','public-result.json')},
        'dispatch':receipt,'full_service_conjunction':all(ass['gates'].values()),
        'sample_count_is_not_cross_period_service_score':True}


def engineering_batch():
    f=frozen();dev=checked(f['development']);records=[]
    assert not (A/'ENGINEERING-RESULTS.json').exists()
    for case in f['cases']:
        for entry in dev['entries']:
            ident=case['id']+'--'+entry['id'];reused=case['id']=='original-parent';receipt=None
            if reused:
                proof=next(r for r in f['reuse'] if r['entry_id']==entry['id'])
                for r in proof['files'].values(): checked(r)
                output=Path(entry['original_initial'])
            else:
                output=A/'engineering'/ident
                receipt=dispatch({'id':ident,'world':'LC-PV','entry':entry,'case':case,'output':str(output)},'engineering')
            record=cell_record(entry,case,output,reused,receipt);records.append(record)
            save(A/'public-results'/(ident+'.json'), {'package':PACKAGE,'training_allowed_in_current_package':True,
                'public_task':entry['training_public'],'public_result':record['files']['public-result.json'],
                'original_learning_flags_preserved':True,'design':case['design'],'service_gates':record['gates'],
                'service_facts':record['service_facts'],'energy':record['independent_checks']['energy_totals_j'],
                'verdict':record['verdict'],'claim_boundary':'Fixed qualified constructed LC model and complete stated services; no hardware or general-domain conclusion.'})
            print(json.dumps({'cell':ident,'reused':reused,'verdict':record['verdict'],'failures':[k for k,v in record['gates'].items() if not v]}),flush=True)
    save(A/'ENGINEERING-RESULTS.json',{'package':PACKAGE,'at_utc':now(),'freeze':ref(A/'ENGINEERING-FREEZE.json'),
        'cells':records,'new_full_inputs':sum(r['new_full_inputs'] for r in records),'reused_full_results':2,
        'cheap_checks':10,'model_requests':0,'storage':capacity(),
        'public_training_index':[ref(p) for p in sorted((A/'public-results').glob('*.json'))],
        'claim_boundary':'Eight frozen whole-design/condition cells; no result-dependent tuning. Unused two engineering full slots retired, not transferable. Original model and service thresholds unchanged.'})
    print(json.dumps({'engineering_results':ref(A/'ENGINEERING-RESULTS.json')}))


def initials():
    f=frozen();definition=read(A/'host/TASK-DEFINITION-FREEZE.json')
    for key in ('rules','door','door_public','lc','lc_public'): checked(definition[key])
    assert not (A/'host/TASK-FREEZE.json').exists()
    door=checked(definition['door']);lcpub=checked(definition['lc_public'])
    lctask=engineering.participant_task(lcpub)
    save(A/'host/lc-driver-task.json',lctask)
    specs=[{'id':'isolated-door-initial','world':'DOOR','task':definition['door'],'output':str(A/'host/door-initial')},
           {'id':'isolated-lc-initial','world':'LC-PV','entry':{'public':definition['lc_public'],'host_task':definition['lc']},
            'case':{'id':'fixed-original-lc-initial','design':lcpub['Design']},'output':str(A/'host/lc-initial')}]
    entries=[]
    for spec in specs:
        receipt=dispatch(spec,'initial-tests');output=Path(spec['output']);public=read(output/'public-result.json')
        entry={'role':'t1' if spec['world']=='DOOR' else 't2','world':spec['world'],
            'task':definition['door'] if spec['world']=='DOOR' else ref(A/'host/lc-driver-task.json'),
            'initial':{n:ref(output/n) for n in ('input.json','raw.json','assessment.json','public-result.json','readback.json')},
            'initial_design':door['initial_design'] if spec['world']=='DOOR' else lcpub['Design'],
            'initial_problem':door['initial_problem'] if spec['world']=='DOOR' else lcpub['Problem'],
            'initial_public_verdict':public['public_check']['verdict'],'dispatch':receipt,
            'task_resolver':'Load this exact task; compare requested task_id; no alternative task resolution.',
            'initial_no_repeat':True,'allowed_for_training_or_selection':False}
        if spec['world']=='LC-PV':entry['context']={'public':definition['lc_public'],'host_task':definition['lc']}
        entries.append(entry)
        print(json.dumps({'initial':spec['world'],'verdict':entry['initial_public_verdict'],'received':public['public_check'].get('received_count')}),flush=True)
    save(A/'host/TASK-FREEZE.json',{'schema':'lc-learning-isolated-test-freeze-v1','package':PACKAGE,'at_utc':now(),
        'definition_freeze':ref(A/'host/TASK-DEFINITION-FREEZE.json'),'definitions_unchanged':True,
        'initial_execution_owner':'campaign-a','entries':entries,'initial_full_inputs':2,
        'no_replacement':True,'exposure':'A/S0 only until both methods and selection are frozen. B must not read this directory.',
        'consumer_sources':{'LC-PV':f['scientific_identity'],'DOOR':f['door_consumer_identity']}})
    ledger=rows();reserves=[r for r in ledger if r['state']=='RESERVED'];done=[r for r in ledger if r['state']=='FINISHED']
    save(A/'RESOURCE-RECEIPT.json',{'package':PACKAGE,'at_utc':now(),'new_full_inputs':len(reserves),
        'engineering_new_full':sum(r['stage']=='engineering' for r in reserves),
        'initial_new_full':sum(r['stage']=='initial-tests' for r in reserves),
        'reused_prior_full_results':2,'completed_full':len(done),'cheap_checks':10,
        'cheap_breakdown':{'necessary_bound_condition_configurations':8,'saved_parent_independent_review':2},
        'model_requests':0,'model_cost_usd':0,'new_full_wall_s':sum(r['wall_s'] for r in done),
        'dispatch_ledger':ref(A/'DISPATCH.jsonl'),'engineering':ref(A/'ENGINEERING-RESULTS.json'),
        'private_test_freeze_path':str(A/'host/TASK-FREEZE.json'),'storage':capacity(),
        'new_environments_worktrees_backups':0,'new_commits_or_pushes':0,'unused_two_A_engineering_inputs_retired':True})
    print(json.dumps({'test_freeze':ref(A/'host/TASK-FREEZE.json'),'resource_receipt':ref(A/'RESOURCE-RECEIPT.json')}))


if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='freeze':freeze()
    elif mode=='engineering':engineering_batch()
    elif mode=='initial-tests':initials()
    elif mode=='_child':child(Path(sys.argv[2]))
    else:raise ValueError(mode)
