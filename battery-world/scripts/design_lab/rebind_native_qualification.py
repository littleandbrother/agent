#!/usr/bin/env python3
"""Requalify an isolated executor using exact already-computed native evidence.

This is an explicit code-version migration, not a second physical solve. The
original producer, failed checks, native logs and archives remain immutable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab import coupled_c,native_witness,case_c,qualification
from bfworld.agentlab.design_lab.contracts import sha,sealed
from bfworld.agentlab.door_selfpower import contracts as d5
from bfworld.agentlab.store import identity

parser=argparse.ArgumentParser();parser.add_argument('--producer',type=Path,required=True)
parser.add_argument('--producer-code',type=Path,required=True);args=parser.parse_args()
producer=args.producer.resolve();code=args.producer_code.resolve()
q=json.loads((producer/'qualification.json').read_text())
if not q['passed']:raise ValueError('SUCCESSFUL_ORIGINAL_NATIVE_QUALIFICATION_REQUIRED')
if d5.template_hash()!='e2f4b26558cdea18f6017ef93dce00fa63ea58e82c33449399ec6baaa4bf4d5d':
    raise ValueError('RESTORE_FROZEN_HISTORICAL_D5_FIRST')
old_env=json.loads((producer/'environment.json').read_text())
old_task=json.loads((producer/'task.json').read_text())
code_record=json.loads((code/'identity.json').read_text())
if any(sha(code/name)!=digest for name,digest in code_record['hashes'].items()):
    raise ValueError('PRODUCER_CODE_ARCHIVE_DRIFT')
old_validation='Venv-'+identity({'version':old_env['schema_version'],
    'code':code_record['hashes'],'D5_executor':old_env['solver_version']})
if old_validation!=old_task['validation_id'] or q['validation_id']!=old_validation:
    raise ValueError('EXACT_PRODUCER_CODE_IDENTITY_REQUIRED')
if native_witness.kernel_identity(code/'solver.py')!=native_witness.kernel_identity():
    raise ValueError('NATIVE_KERNEL_SEMANTICS_CHANGED')
env=coupled_c.environment(old_env['root']);task=coupled_c.contract(env)
start_validation=coupled_c.validation_id()
out=APP/'docs/agentlab/executable-lab-20261012'/('qualified-release-'+str(time.time_ns()))
out.mkdir(parents=True)
sealed(out/'environment.json',env);sealed(out/'task.json',task)
snapshot=json.loads((producer/'changed-TX-6ms/snapshot.json').read_text())
physical=json.loads((producer/'changed-TX-6ms/candidate-device.json').read_text())
if native_witness.model_identity(old_env,physical)!=native_witness.model_identity(env,physical):
    raise ValueError('NATIVE_MODEL_OR_INPUT_CHANGED')
if sha(producer/'changed-TX-6ms/trusted-runner.c')!=hashlib.sha256(case_c.RUNNER.encode()).hexdigest():
    raise ValueError('ORIGINAL_RUNNER_SOURCE_CHANGED')
certificate={'schema_version':native_witness.VERSION,'issuer':'operator-no-agent-qualification',
    'environment_id':env['environment_id'],'validation_id':task['validation_id'],
    'producer_root':str(producer),'producer_files':{name:sha(producer/name) for name in (
        'qualification.json','environment.json','task.json','changed-TX-6ms/execution.json',
        'changed-TX-6ms/snapshot.json','changed-TX-6ms/build.json','changed-TX-6ms/check.json',
        'changed-TX-6ms/candidate-device.json')},
    'producer_kernel':{'path':str(code/'solver.py'),'sha256':sha(code/'solver.py')},
    'kernel_identity':native_witness.kernel_identity(),
    'model_identity':native_witness.model_identity(env,physical),
    'migration':'Identical solve body and unchanged deck/native reader/gate helper functions; frozen legacy default executor restored. New model-domain guards and dependency-plan metadata do not alter this physical input. New qualification replays the actual current build and verifies original native artifacts; it does not claim the producer used the later wrapper.',
    'physical_verified':False,'target_execution_qualified':False,'created':time.time()}
sealed(out/'native-witness.json',certificate)
descriptor={'path':str(out/'native-witness.json'),'sha256':sha(out/'native-witness.json')}
native_witness.original(certificate)  # full actual files/archive readback
controls=[]
for name,sources in [('unchanged',qualification.sources(env,True)),
                     ('changed-TX-6ms',snapshot['sources'])]:
    design=coupled_c.snapshot(task,sources,env);folder=out/name
    build=coupled_c.build(design,folder,env)
    execution=coupled_c.execute(task,design,build,folder,env,trusted_witness=descriptor)
    check=coupled_c.evaluate(task,design,build,execution,env)
    for n,value in [('snapshot.json',design),('build.json',build),('execution.json',execution),('check.json',check)]:
        sealed(folder/n,value)
    controls.append({'name':name,'matched':all(v=='PASS' for v in check['gates'].values()),
                     'native_solve':execution['native_solve'],'new_native_solver_calls':execution['new_native_solver_calls']})
    if name=='changed-TX-6ms':
        for stem,event in [('port-id',{'time_s':2.5,'event_id':65591,'kind':1}),
                           ('port-kind',{'time_s':2.5,'event_id':4294967239,'kind':2})]:
            probe=coupled_c.probe(task,design,build,folder,env,execution,event,stem)
            checked=case_c.evaluate(task,design,build,probe,env,event_truth=event)
            sealed(folder/(stem+'.json'),{'execution':probe,'check':checked})
            controls.append({'name':stem,'matched':all(v=='PASS' for v in checked['gates'].values())})
        loss=case_c.evaluate(task,design,build,execution,env,link_loss=True)
        controls.append({'name':'actual-virtual-receiver-loss-rejected','matched':loss['gates']['deadline_receive']=='FAIL'})
controls.append({'name':'producer-exact-code-and-kernel-isolation','matched':True})
controls.append({'name':'current-environment-code-stable','matched':start_validation==coupled_c.validation_id()})
report={'schema_version':'bf-native-C-environment-qualification-v3',
    'environment_id':env['environment_id'],'validation_id':task['validation_id'],'scope':task['scope'],
    'passed':all(c['matched'] for c in controls),'controls':controls,
    'native_witness':descriptor,'producer_qualification':{'path':str(producer/'qualification.json'),'sha256':sha(producer/'qualification.json')},
    'source_migration':certificate['migration'],'model_calls':0,'old_D5_native_solves':0,
    'new_native_solver_calls':sum(c.get('new_native_solver_calls',0) for c in controls),
    'original_native_solver_calls':q['new_native_solver_calls'],
    'physical':'NOT_TESTED','target_peripherals':'NOT_QUALIFIED','full_product_passed':False,'created':time.time()}
sealed(out/'qualification.json',report)
print(json.dumps({'passed':report['passed'],'qualification':str(out/'qualification.json'),
                  'new_native_solver_calls':report['new_native_solver_calls']}))
raise SystemExit(0 if report['passed'] else 1)
