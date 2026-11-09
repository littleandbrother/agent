"""Exactly frozen M2r inputs; original full adapter/consumer/evaluator, no API."""
import json,sys,time,signal,gzip,hashlib,traceback,math,os
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parents[6]
M=Path(__file__).resolve().parent
A=M.parent
P=A.parent
sys.path.insert(0,str(R/'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src'))

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clean(x):
 if isinstance(x,float) and not math.isfinite(x):return None
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [clean(v) for v in x]
 return x
def write(p,x):p.write_text(json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def alarm(signum,frame):raise TimeoutError('M2R_PER_RUN_CAP')
def finish(status,reason,c):
 write(M/'mechanism-qualification.json',{'schema':'M2r-exploratory-qualification-v1','classification':'PRIVATE_DEVELOPER_REFERENCE','status':status,'reason':reason,'post_original_result_amendment':True,'original_results_unchanged':'../mechanism-qualification.json','frozen_input_index':'INPUTS-FROZEN.json','rows':c['rows'],'new_cost':{k:c[k] for k in ['full_attempts','full_wall_s','cheap_numeric','software_cases','api_requests']},'cumulative_A':{'full_attempts':45+c['full_attempts'],'full_wall_s':c['prior_actual_full_wall_s']+c['full_wall_s'],'cheap_numeric':10+c['cheap_numeric'],'software_cases':3},'holdouts_executed':0,'no_extra_input_or_third_revision':True,'claim_boundary':'Exploratory finite constructed interaction; no global necessity, physical qualification, method/ancestor benefit or original preregistered M2 result.'})
 print(json.dumps({'status':status,'reason':reason,'new_full':c['full_attempts'],'new_full_wall_s':c['full_wall_s'],'new_cheap':c['cheap_numeric']}),flush=True)

def main():
 gate_path=P/'shared/M2-expression-amendment-admission.json'
 if not gate_path.exists():raise RuntimeError('M2R_NOT_ADMITTED')
 gate=read(gate_path)
 if gate.get('status')!='READY_FOR_M2R_ONLY':raise RuntimeError('M2R_NOT_READY')
 freeze=read(M/'INPUTS-FROZEN.json');c=read(M/'counter.json');pre=read(P/'s0/preflight.json');deadline=pre['absolute_deadline_epoch']
 if sha(M/'INPUTS-FROZEN.json')!=c['freeze_sha256']:raise RuntimeError('M2R_FREEZE_CHANGED')
 if sha(M/'amend_inputs.py')!=freeze['corrector_sha256']:raise RuntimeError('M2R_CORRECTOR_CHANGED')
 if sha(R/freeze['tasks_private_ref'])!=freeze['tasks_private_sha256']:raise RuntimeError('M2R_TASKS_CHANGED')
 for path,h in freeze['old_records_preserved'].items():
  if sha(R/path)!=h:raise RuntimeError('ORIGINAL_RECORD_CHANGED:'+path)
 for path,h in freeze['sources_at_freeze'].items():
  if sha(R/path)!=h:raise RuntimeError('M2R_FROZEN_SOURCE_CHANGED:'+path)
 from bfworld.agentlab.pqe20261024debt import adapter,task as tasks
 sources=adapter.source_identity()
 if gate.get('sources')!=freeze['sources_at_freeze']:raise RuntimeError('M2R_ADMITTED_PATH_SOURCES_MISMATCH')
 if gate['freeze']['sha256']!=sha(M/'INPUTS-FROZEN.json'):raise RuntimeError('M2R_GATE_FREEZE_MISMATCH')
 if gate['frozen_inputs']!=freeze['new_frozen_inputs']:raise RuntimeError('M2R_GATE_INPUT_INDEX_MISMATCH')
 admitted_aliases={}
 for path,h in gate['sources'].items():
  parts=Path(path).parts
  prefix='codebt/' if 'pqe20261024debt' in parts else ('bold/' if 'pqe20261023bold' in parts else '')
  admitted_aliases[prefix+parts[-1]]=h
 for name,h in admitted_aliases.items():
  if sources.get(name)!=h:raise RuntimeError('M2R_ADMITTED_ALIAS_MISMATCH:'+name)
 original_admission=read(P/'shared/science-admission.json')
 for name,h in sources.items():
  if name not in admitted_aliases and original_admission['sources'].get(name)!=h:raise RuntimeError('M2R_ORIGINAL_KERNEL_SOURCE_MISMATCH:'+name)

 write(M/'admission-used.json',{'gate_ref':str(gate_path.relative_to(R)),'gate_sha256':sha(gate_path),'freeze_sha256':sha(M/'INPUTS-FROZEN.json'),'runner_sha256':sha(Path(__file__)),'sources':sources,'started_epoch':time.time(),'absolute_deadline_epoch':deadline})
 signal.signal(signal.SIGALRM,alarm)
 for item in freeze['new_frozen_inputs']:
  if sha(R/item['path'])!=item['sha256']:raise RuntimeError('M2R_INPUT_CHANGED')
  previous=next((r for r in c['rows'] if r['order']==item['order']),None)
  if previous:
   if previous['status']=='RUNNING':raise RuntimeError('UNRESOLVED_ATTEMPT_NO_RETRY')
   continue
  remaining=min(120.,900-c['prior_actual_full_wall_s']-c['full_wall_s'],deadline-time.time())
  if remaining<=0 or c['full_attempts']>=15:raise RuntimeError('M2R_BUDGET_EXHAUSTED')
  if adapter.source_identity()!=sources:raise RuntimeError('M2R_APPARATUS_CHANGED')
  stat=os.statvfs(R)
  if stat.f_bavail*stat.f_frsize<11500000000:raise RuntimeError('STORAGE_RESERVE_NOT_MET')
  inp=read(R/item['path']);task=inp['task'];folder=M/'runs'/(str(46+c['full_attempts']).zfill(2)+'-'+item['design_name']+'-'+item['condition_id']);folder.mkdir(parents=True,exist_ok=False)
  write(folder/'input-reference.json',{'path':item['path'],'sha256':item['sha256'],'sources':sources})
  row={'order':item['order'],'design_name':item['design_name'],'condition_id':item['condition_id'],'folder':str(folder.relative_to(M)),'input_ref':item['path'],'input_sha256':item['sha256'],'status':'RUNNING','wall_cap_s':remaining,'started_epoch':time.time()};c['rows'].append(row);c['full_attempts']+=1;write(M/'counter.json',c)
  cache_before=set(tasks._STATIC_GEOMETRY_CACHE);start=time.monotonic();signal.setitimer(signal.ITIMER_REAL,remaining)
  try:
   public=adapter.execute(task,inp['parent_design'],inp['problem'],inp['decision'],folder/'result',task_resolver=lambda tid:task if tid==task['task_id'] else None)
   row['status']='COMPLETE'
  except Exception as exc:
   row['status']='TOOL_ERROR';row['error']=str(exc);write(folder/'tool-error.json',{'status':'TOOL_ERROR','type':type(exc).__name__,'message':str(exc),'diagnostic':getattr(exc,'diagnostic',None),'traceback':traceback.format_exc(limit=8),'no_service_verdict':True})
  finally:
   signal.setitimer(signal.ITIMER_REAL,0);row['elapsed_s']=time.monotonic()-start;c['full_wall_s']+=row['elapsed_s'];misses=len(set(tasks._STATIC_GEOMETRY_CACHE)-cache_before);c['cheap_numeric']+=misses;row['static_geometry_real_misses']=misses
  if row['status']=='COMPLETE':
   raw=json.load(gzip.open(folder/'result/raw.json.gz','rt'));ass=json.load(gzip.open(folder/'result/assessment.json.gz','rt'));events=Counter(e['action'] for e in raw['activity'])
   if raw['design']!=inp['design'] or raw['task_sha256']!=adapter.digest(task):raise RuntimeError('M2R_EXECUTION_BINDING')
   row.update(model_valid=raw['model_valid'],domain_errors=raw['domain_errors'],verdict=ass['verdict'],failures=ass['failures'],unknown=ass['unknown'],activity_counts=dict(events),received=len(ass['receiver_records']),truth_events_private=len(ass['truth']),missed_private=len(ass['missed_event_ids']),sequence_reuse_private=len(ass['receiver_identity']['different_saved_record_sequence_reuse']),energy=raw['energy'],holding_loads=raw.get('holding_loads'),steps=raw.get('solver_diagnostics',{}).get('iterations'),raw_sha256=sha(folder/'result/raw.json.gz'),assessment_sha256=sha(folder/'result/assessment.json.gz'))
  write(folder/'summary-private.json',row);write(M/'counter.json',c)
  print(json.dumps({'order':item['order'],'status':row['status'],'elapsed_s':row['elapsed_s']}),flush=True)
  if row['status']!='COMPLETE':finish('NOT_ESTABLISHED','TOOL_ERROR_STOP',c);return
  if not row['model_valid']:finish('NOT_ESTABLISHED','MODEL_DOMAIN_UNKNOWN_STOP',c);return
  if item['design_name']=='identity-only' and len([r for r in c['rows'] if r['design_name']=='identity-only'])==3 and all(r['verdict']=='PASS' for r in c['rows'] if r['design_name']=='identity-only'):
   finish('NOT_ESTABLISHED','PERSISTENT_BUNDLE_SUFFICES_ALL_THREE_STOP',c);return
  if item['design_name']=='complete-reference' and row['verdict']!='PASS':finish('NOT_ESTABLISHED','COMPLETE_REFERENCE_NOT_ALL_PASS_STOP',c);return
  if 10+c['cheap_numeric']>32:raise RuntimeError('A_CHEAP_CAP_EXHAUSTED')
 def group(name):return [r for r in c['rows'] if r['design_name']==name]
 qualified=all(r['model_valid'] for r in c['rows']) and all(r['verdict']=='PASS' for r in group('complete-reference')) and all(any(r['verdict']=='FAIL' for r in group(name)) for name in ['parent','identity-only','holder-only','clear-never-neighbor'])
 finish('QUALIFIED' if qualified else 'NOT_ESTABLISHED','ORIGINAL_FINITE_GATE_MET' if qualified else 'NO_FINITE_INTERACTION_IN_FIXED_NEIGHBORS',c)
if __name__=='__main__':main()
