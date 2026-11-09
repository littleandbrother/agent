"""A-only preregistered initial qualification: max two original full inputs."""
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from bfworld.agentlab.pqe20261022 import adapter,pilot as p
from bfworld.agentlab.pqe20261022.executor import identity
ROOT=Path('/Users/depengsu/Documents/Long-Horizon AI Agent')
A=ROOT/'docs/research/pqe-two-paper-plan-20261022/f1-conditional-learning/a'

def now():return datetime.now(timezone.utc).isoformat()
def rd(path):return json.loads(Path(path).read_text())
def bind(path):
 b=Path(path).read_bytes();return {'path':str(path),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
def checked(ref):
 assert bind(ref['path'])==ref,('HASH_GATE',ref['path'])
 return rd(ref['path'])
def wr(path,value,exclusive=True):
 with Path(path).open('x' if exclusive else 'w') as h:json.dump(value,h,ensure_ascii=False,indent=2,allow_nan=False);h.write('\n')
def capacity():
 f=os.statvfs(ROOT);available=f.f_bavail*f.f_frsize
 retained=sum(x.stat().st_size for x in A.rglob('*') if x.is_file())
 assert available>=11000000000 and retained<8000000,'STORAGE_GATE'
 return {'available_bytes':available,'A_retained_bytes':retained,'A_retained_cap_bytes':8000000,'peak_additional_cap_bytes':1000000000}
def validate():
 freeze=rd(A/'TASK-FREEZE.json')
 checked(freeze['rules']);assert bind(freeze['generator']['path'])==freeze['generator']
 assert adapter.source_identity()==freeze['apparatus_source'],'SOURCE_GATE'
 assert bind(freeze['public_task_source']['path'])==freeze['public_task_source']
 for entry in freeze['tasks']:
  catalog=checked(entry['task']);task=catalog[entry['task_key']]
  packet=checked(entry['public_input'])
  assert identity(task)==entry['task_canonical_sha256']
  assert packet['task']==p.public_task(task)
  assert packet['initial_design']==task['initial_design']
 return freeze

def child(role):
 freeze=validate();entry=next(e for e in freeze['tasks'] if e['id']==role)
 task=checked(entry['task'])[entry['task_key']]
 decision={'status':'READY','selected_id':'shared-initial-qualification-'+role,'actual_input':{'operation':'verify'},'origin':'PREREGISTERED_COMMON_INITIAL_NOT_AGENT_SELECTED'}
 out=A/'qualification'/role/'01'
 result=adapter.execute(task,task['initial_design'],task['initial_problem'],decision,out,
     task_resolver=lambda ident:deepcopy(task) if ident==task['task_id'] else None)
 validate()
 print(json.dumps({'id':role,'model_valid':result['model_valid'],'public_check':result['public_check'],'numerical_inputs':result['usage']['numerical_inputs']}),flush=True)

def qualify():
 assert not (A/'qualification-ledger.json').exists(),'NO_QUALIFICATION_RETRY'
 freeze=validate();pre=capacity()
 wr(A/'QUALIFICATION-FREEZE.json',{'schema':'f1-A-qualification-executor-freeze-v1','at_utc':now(),'task_freeze':bind(A/'TASK-FREEZE.json'),'executor':bind(Path(__file__)),'preflight':pre,'max_inputs':2,'outer_authorized_cap':4,'max_seconds_each':120,'outer_wall_cap_s':480,'no_fallback':True,'new_cheap_model_provider_native_calls':0})
 ledger={'schema':'f1-A-qualification-ledger-v1','package':freeze['package'],'new_full_dynamic_inputs':0,'authorized_outer_cap':4,'declared_input_cap':2,'wall_s':0,'consumer_wall_s':0,'new_cheap_calls':0,'new_model_provider_native_hardware_calls':0,'attempts':[]}
 wr(A/'qualification-ledger.json',ledger)
 entries=[]
 for entry0 in freeze['tasks']:
  entry=deepcopy(entry0);capacity();validate()
  assert ledger['new_full_dynamic_inputs']<2 and ledger['wall_s']<360
  role=entry['id'];folder=A/'qualification'/role/'01'
  attempt={'id':role,'status':'STARTED','claimed_at':now(),'input_task_sha256':entry['task_canonical_sha256'],'initial_design_sha256':entry['initial_design_sha256'],'reserved_seconds':120,'new_full_dynamic_input':1}
  ledger['new_full_dynamic_inputs']+=1;ledger['attempts'].append(attempt);wr(A/'qualification-ledger.json',ledger,False)
  started=time.monotonic()
  try:
   proc=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'_execute',role],timeout=120,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
   elapsed=time.monotonic()-started;ledger['wall_s']+=elapsed
   attempt.update(returncode=proc.returncode,wall_s=elapsed,stdout=proc.stdout,stderr=proc.stderr)
   if proc.returncode:
    attempt['status']='TOOL_ERROR_NOT_SCIENTIFIC_FAILURE';entry.update(status='NOT_INCLUDED',eligible=False,reason='Original-consumer tool error; no rerun/replacement',qualification_error=deepcopy(attempt))
   else:
    public=rd(folder/'public-result.json');raw=rd(folder/'raw.json');assessment=rd(folder/'assessment.json')
    task=checked(entry['task'])[entry['task_key']]
    assert raw['task_sha256']==public['task_sha256']==identity(task)==entry['task_canonical_sha256']
    assert raw['design_sha256']==public['input_sha256']==entry['initial_design_sha256']
    assert raw['result_sha256']==public['result_sha256']==identity({k:v for k,v in raw.items() if k!='result_sha256'})
    assert public['sources']==freeze['apparatus_source']
    for name in ('trace','activity','records','packets','energy','program_state'):assert public['facts'][name]==raw[name],name
    assert public['facts']['receiver_records']==assessment['receiver_records']
    integrity=(raw['execution_status']=='COMPLETE' and raw['model_valid'] is True and not raw['domain_errors'] and not assessment['unknown'])
    original_constraints=(raw['peak_handle_force_n']<=task['service']['handle_force_max_n'] and abs(assessment['mechanical_residual_j'])<=assessment['energy_tolerance_j'] and abs(assessment['storage_residual_j'])<=assessment['energy_tolerance_j'])
    eligible=(integrity and original_constraints and assessment['verdict']=='FAIL' and len(assessment['truth'])==6 and bool(set(assessment['failures'])&{'MISSED_OR_LATE_EVENT','SPURIOUS_OR_DUPLICATE_EVENT_ID','SEQUENCE_PAYLOAD_CONFLICT','EVENT_ORDER'}))
    ledger['consumer_wall_s']+=public['usage']['wall_s']
    counts=dict(Counter(x['action'] for x in raw['activity']))
    readback={'schema':'f1-A-initial-qualification-readback-v1','at':now(),'category':'A_INITIAL_QUALIFICATION','task':role,'task_key':entry['task_key'],'task_sha256':raw['task_sha256'],'design_sha256':raw['design_sha256'],'cache_key':p.execution_cache_key(task,task['initial_design'],raw['dt_s'],freeze['apparatus_source']),'reused':False,'full_dynamic_inputs':1,'wall_s':elapsed,'consumer_wall_s':public['usage']['wall_s'],'public_result':bind(folder/'public-result.json'),'raw':bind(folder/'raw.json'),'assessment':bind(folder/'assessment.json'),'decision':bind(folder/'decision.json'),'model_valid':raw['model_valid'],'domain_errors':raw['domain_errors'],'public_check':public['public_check'],'truth_events':len(assessment['truth']),'timely_matches':len(assessment['matches']),'activity_counts':counts,'records':len(raw['records']),'packets':len(raw['packets']),'remaining_queue':raw['remaining_queue'],'minimum_tx_terminal_v':raw['minimum_tx_terminal_v'],'peak_handle_force_n':raw['peak_handle_force_n'],'original_constraints_intact':original_constraints,'eligible':eligible,'source_identity':freeze['apparatus_source'],'no_private_reference_or_method_execution':True}
    wr(folder/'readback.json',readback)
    entry.update(status='READY' if eligible else 'NOT_INCLUDED',eligible=eligible,initial_public_result=readback['public_result'],initial_qualification=bind(folder/'readback.json'),initial_full_result=readback['raw'],initial_assessment=readback['assessment'],qualification_summary={k:readback[k] for k in ('model_valid','public_check','truth_events','timely_matches','activity_counts','records','packets','original_constraints_intact','eligible')})
    attempt.update(status='QUALIFIED_VALID_FAIL' if eligible else 'NOT_INCLUDED_NO_REPLACEMENT',eligible=eligible,readback=bind(folder/'readback.json'))
  except subprocess.TimeoutExpired as exc:
   elapsed=time.monotonic()-started;ledger['wall_s']+=elapsed
   attempt.update(status='TIMEOUT_UNKNOWN_NOT_SERVICE_FAILURE',wall_s=elapsed,stdout=(exc.stdout or b'').decode(errors='replace') if isinstance(exc.stdout,bytes) else exc.stdout,stderr=(exc.stderr or b'').decode(errors='replace') if isinstance(exc.stderr,bytes) else exc.stderr)
   entry.update(status='NOT_INCLUDED',eligible=False,reason='Qualification timeout; no rerun/replacement',qualification_error=deepcopy(attempt))
  except Exception as exc:
   attempt.update(status='AUDIT_OR_HASH_GATE_STOP',error=repr(exc));wr(A/'qualification-ledger.json',ledger,False);raise
  wr(A/'qualification-ledger.json',ledger,False)
  entries.append(entry)
  print(json.dumps({'role':role,'status':entry['status'],'eligible':entry['eligible'],'summary':entry.get('qualification_summary'),'attempt_wall_s':attempt['wall_s']}),flush=True)
 assert ledger['wall_s']<=480
 validate();post=capacity()
 manifest={'schema':'f1-A-task-manifest-v1','package':freeze['package'],'at_utc':now(),'status':'TWO_ROLES_QUALIFIED' if all(e['eligible']for e in entries) else 'PARTIAL_OR_NO_ELIGIBLE_ROLES_EXPLICITLY_NOT_INCLUDED','isolation':freeze['isolation'],'task_freeze':bind(A/'TASK-FREEZE.json'),'qualification_freeze':bind(A/'QUALIFICATION-FREEZE.json'),'tasks':entries,'apparatus_source':freeze['apparatus_source'],'qualification_ledger':bind(A/'qualification-ledger.json'),'actual_qualification_inputs':ledger['new_full_dynamic_inputs'],'qualification_wall_s':ledger['wall_s'],'qualification_consumer_wall_s':ledger['consumer_wall_s'],'new_cheap_model_provider_native_calls':0,'postflight':post,'exact_reuse_rule':'S0 reads these exact full/public/assessment/initial inputs; never rerun unchanged initial qualification. Qualifying FAIL remains immutable independent of any method performance.','claim_boundary':'Prospective package repair/adoption inputs; no full solution/reference, post-adoption final test, hardware/statistical/general transfer claim.'}
 wr(A/'TASK-MANIFEST.json',manifest)
 print(json.dumps({'status':manifest['status'],'manifest':bind(A/'TASK-MANIFEST.json'),'new_full_inputs':ledger['new_full_dynamic_inputs'],'new_cheap_or_model':0,'postflight':post}),flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['qualify','_execute']);parser.add_argument('role',nargs='?');args=parser.parse_args()
 child(args.role) if args.phase=='_execute' else qualify()
