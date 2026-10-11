#!/usr/bin/env python3
"""No paid calls, no rerun of old D5. New A/B synthetic-domain controls."""
import json
import shutil
from pathlib import Path
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab import finite_cases as f
from bfworld.agentlab.design_lab.contracts import sealed,sha

APP=Path(__file__).resolve().parents[2]
out=APP/'docs/agentlab/refactor-r3-r5-20261012'/('environment-'+str(time.time_ns()))
out.mkdir(parents=True)
controls=[]
for case in ('A','B'):
    env=f.manifest(case);sealed(out/case/'environment.json',env)
    variants=[('reference',{}, {}, 'PASS'),('zero-source',{}, {'source_scale':0},'FAIL'),
              ('wrong-identity',{'wrong_id':True},{},'FAIL'),('receive-loss',{}, {},'FAIL')]
    if case=='A':variants += [('wrong-diagnosis',{'wrong_class':True},{},'FAIL'),
                            ('aliasing',{'fs':64},{},'FAIL'),('long-TX',{'tx_s':.6},{},'FAIL'),
                            ('depleting-source',{}, {'source_scale':.1},'FAIL')]
    else:variants += [('slow-start',{}, {'delay_s':1.1},'FAIL'),
                      ('window-short',{'tx_s':1.},{},'FAIL'),('insufficient-single-action',{}, {'source_scale':.1},'FAIL')]
    for name,program,inputs,expected in variants:
        folder=out/case/name;sources=f.reference_source(case,**program)
        build=f.build(env,sources,folder);x=f.execute(env,sources,build,folder,**inputs)
        native=f.native_energy_check(x,folder)
        check=f.evaluate(env,build,x,link_loss=name=='receive-loss',native=native)
        for n,v in [('build.json',build),('execution.json',x),('check.json',check)]:sealed(folder/n,v)
        controls.append({'case':case,'name':name,'expected':expected,'observed':check['scoped_status'],
                         'matched':expected==check['scoped_status'],'check_id':check['check_id'],
                         'files':{n:sha(folder/n) for n in ('build.json','execution.json','check.json')}})
        print(json.dumps({'case':case,'control':name,'status':check['scoped_status'],'matched':controls[-1]['matched']}),flush=True)
        if name=='reference':
            if case=='A':
                swapped=f.execute(env,sources,build,folder,truth_shift=1,stem='label-permutation')
                replay=folder/'label-permutation-numeric';replay.mkdir()
                shutil.copyfile(folder/swapped['trace_name'],replay/swapped['trace_name'])
                shifted_native=f.native_energy_check(swapped,replay)
                c=f.evaluate(env,build,swapped,native=shifted_native)
                sealed(folder/'label-permutation-execution.json',swapped);sealed(folder/'label-permutation-check.json',c)
                controls.append({'case':case,'name':'independent-label-permutation','matched':c['scoped_status']=='PASS',
                                 'observed':c['scoped_status'],'meaning':'Truth is not a participant input; classes must follow sample waveform'})
            fine=f.execute(env,sources,build,folder,dt=.00025,stem='fine')
            same=[(t['request_id'],t['class']) for t in x['tx']]==[(t['request_id'],t['class']) for t in fine['tx']]
            margin=max((abs(a['time_s']-b['time_s']) for a,b in zip(x['tx'],fine['tx'])),default=0)
            step={'same_receives':same,'maximum_latency_difference_s':margin,
                  'passed':same and margin<.01,'coarse':x['execution_id'],'fine':fine['execution_id']}
            sealed(folder/'fine-execution.json',fine);sealed(folder/'step-check.json',step)
            controls.append({'case':case,'name':'time-step','matched':step['passed'],'observed':step})
            tampered={**build,'sources_sha256':'0'*64}
            try:f.execute(env,sources,tampered,folder);reject=False
            except ValueError:reject=True
            controls.append({'case':case,'name':'stale-build','matched':reject,'observed':'REJECT' if reject else 'ACCEPT'})
report={'schema_version':'bf-r3-environment-progress-v1','controls':controls,
        'model_domain_controls_passed':all(c['matched'] for c in controls),'paid_calls':0,
        'old_D5_native_solves':0,'new_native_numeric_replays':len([c for c in controls if 'check_id' in c])+1,
        'C':'Existing scoped C fixed point reused; changed-load recoupling remains RECHECK_REQUIRED',
        'R3_full_exit':'NOT_MET: calibrated A/B source/converter and changed-load C remain unqualified',
        'physical':'NOT_TESTED','claim':'A/B synthetic model-domain control qualification only'}
sealed(out/'qualification.json',report)
print(json.dumps({'report':str(out/'qualification.json'),'passed':report['model_domain_controls_passed']}))
if not report['model_domain_controls_passed']:raise SystemExit(1)
