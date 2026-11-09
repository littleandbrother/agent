"""Bounded local full-consumer runner; no old owner/gate or provider capability."""
import sys, json, time, os, subprocess, gzip, hashlib, traceback, math
from pathlib import Path
from collections import Counter
from copy import deepcopy
R=Path(__file__).resolve().parents[5]
A=Path(__file__).resolve().parent
BASE=A.parents[1]
SRC=R/'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src'
sys.path.insert(0,str(SRC))
PY=sys.executable

def finite(x):
 if isinstance(x,float) and not math.isfinite(x): return None
 if isinstance(x,dict): return {k:finite(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)): return [finite(v) for v in x]
 return x
def write(p,x): x=finite(x); p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def summarize(folder):
 raw=json.load(gzip.open(folder/'raw.json.gz','rt')); assessment=json.load(gzip.open(folder/'assessment.json.gz','rt'))
 events=Counter(x.get('action',x.get('kind',x.get('event',x.get('type','UNKNOWN')))) for x in raw['activity'])
 return dict(execution_status=raw['execution_status'],model_valid=raw['model_valid'],domain_errors=raw['domain_errors'],verdict=assessment['verdict'],failures=assessment['failures'],unknown=assessment['unknown'],activity_counts=dict(events),saved_records=len(raw['records']),packets=len(raw['packets']),accepted_receive=len(assessment['receiver_records']),duplicate_wire_frames=len(assessment['duplicate_wire_frames']),actual_sequence_reuse=len(assessment['receiver_identity']['different_saved_record_sequence_reuse']),boot_count=raw['boot_count'],consumer_version=raw['schema_version'],program_version=raw['program_version'],holding_loads=raw.get('holding_loads'),energy=raw['energy'],steps=raw.get('solver_diagnostics',{}).get('iterations'),solver_diagnostics=raw.get('solver_diagnostics'),raw_sha256=sha(folder/'raw.json.gz'),assessment_sha256=sha(folder/'assessment.json.gz'))
def child(inp,out):
 from bfworld.agentlab.pqe20261024debt import adapter
 x=read(Path(inp)); task=x['task']; resolver=lambda task_id: task if task_id==task['task_id'] else None
 try:
  adapter.execute(task,x['parent_design'],x['problem'],x['decision'],Path(out),task_resolver=resolver)
 except Exception as exc:
  write(Path(out).parent/'error.json',dict(status='TOOL_ERROR',type=type(exc).__name__,message=str(exc),diagnostic=getattr(exc,'diagnostic',None),traceback=traceback.format_exc(limit=6)))
  raise
if __name__=='__main__':
 if sys.argv[1]=='child': child(sys.argv[2],sys.argv[3]); sys.exit(0)
 stage=sys.argv[1]
 pre=read(A.parent/'s0/preflight.json'); deadline=pre['wall_start_epoch']+pre['wall_cap_s']
 counter_path=A/'counter.json'
 counter=read(counter_path) if counter_path.exists() else dict(full_attempts=0,full_wall_s=0.,cheap_numeric=0,software_cases=0,api_requests=0,rows=[])
 family=read(BASE/'codebt-idea/a/TASKS.json')['conditions']
 if stage=='P1': tasks=family
 elif stage.startswith('DIAG') or stage=='P2': tasks=family[:1] if stage.startswith('DIAG') else family
 else: raise ValueError(stage)
 debt=read(BASE/'codebt-idea/s0/science/09-debt_agent-scheduler-fixed-short-cold/input.json') if stage!='P1' else None
 for task in tasks:
  label=stage+'-'+task['condition_id']
  if any(r['label']==label for r in counter['rows']): continue
  remaining=min(120.,1920-counter['full_wall_s'],deadline-time.time())
  if remaining<=0 or counter['full_attempts']>=16: raise RuntimeError('NEW_PACKAGE_BUDGET_EXHAUSTED')
  folder=A/(str(counter['full_attempts']+1).zfill(2)+'-'+label);folder.mkdir(exist_ok=False)
  parent=deepcopy(task['initial_design'])
  if stage=='P1': decision={'actual_input':{'operation':'edit','design_patch':{'persistent_queue':True}}}
  else:
   selected=debt.get('design')
   action=debt.get('action',{})
   decision=deepcopy(action.get('decision',action))
   if 'actual_input' not in decision: raise ValueError(('ORIGINAL_DEBT_ACTION_SHAPE',list(debt),list(action)))
  inp=dict(package='BF-PQE-CODEBT-ZEROAPI-CHECK-20261024-001',stage=stage,task=task,parent_design=parent,problem=deepcopy(task['initial_problem']),decision=decision)
  write(folder/'input.json',inp)
  counter['full_attempts']+=1; row=dict(label=label,status='RUNNING',folder=str(folder.relative_to(R)),timeout_s=remaining,started_epoch=time.time());counter['rows'].append(row);write(counter_path,counter)
  started=time.monotonic()
  try:
   with (folder/'stdout').open('w') as stdout,(folder/'stderr').open('w') as stderr:
    result=subprocess.run([PY,'-B',str(Path(__file__).resolve()),'child',str(folder/'input.json'),str(folder/'result')],stdout=stdout,stderr=stderr,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=remaining)
   row['status']='COMPLETE' if result.returncode==0 else 'TOOL_ERROR';row['returncode']=result.returncode
  except subprocess.TimeoutExpired: row['status']='TOOL_ERROR';row['error']='WALL_TIMEOUT'
  row['elapsed_s']=time.monotonic()-started;counter['full_wall_s']+=row['elapsed_s']
  if row['status']=='COMPLETE': row.update(summarize(folder/'result'))
  elif (folder/'error.json').exists(): row['error_record']=read(folder/'error.json')
  write(counter_path,counter);write(folder/'summary.json',row); print(json.dumps(row,ensure_ascii=False),flush=True)
 write(A/(stage+'-RESULTS.json'),dict(stage=stage,rows=[x for x in counter['rows'] if x['label'].startswith(stage+'-')],counter=counter_path.name))
