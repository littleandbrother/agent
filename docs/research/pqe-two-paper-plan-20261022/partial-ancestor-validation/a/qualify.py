"""Private finite qualification, canonical original consumer/evaluator only."""
import sys,json,time,signal,math,gzip,hashlib,os,traceback
from pathlib import Path
from copy import deepcopy
from collections import Counter
R=Path(__file__).resolve().parents[5]
A=Path(__file__).resolve().parent
P=A.parent
sys.path.insert(0,str(R/'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src'))

def read(p):return json.loads(p.read_text())
def digest_file(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clean(x):
 if isinstance(x,float) and not math.isfinite(x):return None
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [clean(v) for v in x]
 return x
def write(p,x):p.write_text(json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def limit(signum,frame):raise TimeoutError('A_QUALIFICATION_PER_RUN_WALL_CAP')

def main():
 admission_path=P/'shared/science-admission.json'
 if not admission_path.exists():raise RuntimeError('WAITING_FOR_SCIENCE_ADMISSION')
 admission=read(admission_path)
 if admission.get('status')!='READY_FOR_A_QUALIFICATION':raise RuntimeError('SCIENCE_NOT_ADMITTED:'+str(admission.get('status')))
 pre=read(P/'s0/preflight.json');deadline=pre['absolute_deadline_epoch']
 if time.time()>=deadline:raise RuntimeError('PACKAGE_DEADLINE_EXHAUSTED')
 rules=read(A/'qualification-rules.json');freeze=read(A/'SOURCE-FROZEN.json');private=read(A/'qualification-private.json');count=read(A/'counter.json')
 if digest_file(A/'qualification-rules.json')!=count['rules_sha256']:raise RuntimeError('RULE_BINDING')
 if digest_file(A/'qualification-private.json')!=rules['private_input_sha256']:raise RuntimeError('PRIVATE_INPUT_BINDING')
 for path in freeze['A_files_frozen']:
  if digest_file(R/path)!=freeze['sources'][path]:raise RuntimeError('A_SOURCE_NOT_FROZEN:'+path)
 from bfworld.agentlab.pqe20261024debt import adapter,task as task_module,facts
 sources=adapter.source_identity()
 if sources!=admission['sources']:raise RuntimeError('ADMITTED_APPARATUS_SOURCE_MISMATCH')
 for binding in ('A_source_freeze','qualification_rules','qualification_private','provider_binding'):
  item=admission[binding]
  if digest_file(Path(item['path']))!=item['sha256']:raise RuntimeError('ADMISSION_BINDING:'+binding)
 write(A/'gate-used.json',{'admission_ref':str(admission_path.relative_to(R)),'admission_sha256':digest_file(admission_path),'status':admission['status'],'used_at_epoch':time.time(),'sources':sources,'runner_sha256':digest_file(Path(__file__)),'source_frozen_sha256':digest_file(A/'SOURCE-FROZEN.json')})
 signal.signal(signal.SIGALRM,limit)
 selected=None
 private_rows=[]
 for entry in private['profiles_in_order']:
  profile=entry['profile']['id'];profile_rows=[]
  for design_name in rules['design_order']:
   for task in entry['public_tasks']:
    row=run_one(profile,design_name,task,entry['private_designs'][design_name],sources,count,deadline,adapter,task_module,facts)
    profile_rows.append(row);private_rows.append(row)
    if row['status']!='COMPLETE':
     finish('TOOL_INCOMPLETE',None,private_rows,count,'Actual tool error stops dependent qualification; no same-stall repeat.')
     return
  def group(name):return [r for r in profile_rows if r['design_name']==name]
  all_valid=all(r['model_valid'] for r in profile_rows)
  ref_pass=all(r['verdict']=='PASS' for r in group('complete-reference'))
  partial_fail=all(any(r['verdict']=='FAIL' for r in group(name)) for name in ['parent','identity-only','holder-only','clear-never-neighbor'])
  produced=any(r['activity_counts'].get('holding_capture_commit',0)>0 for r in group('holder-only'))
  never_visible=any(r['activity_counts'].get('holding_read_commit',0)>0 for r in group('clear-never-neighbor'))
  gate={'profile':profile,'all_model_valid':all_valid,'reference_all_pass':ref_pass,'partial_controls_have_failure':partial_fail,'holder_production_observed':produced,'never_read_observed':never_visible,'qualified':all_valid and ref_pass and partial_fail and produced and never_visible}
  write(A/(profile+'-qualification-gate.json'),gate)
  print(json.dumps({'profile':profile,'qualification_status':'QUALIFIED' if gate['qualified'] else 'NOT_ESTABLISHED','full_attempts':count['full_attempts'],'full_wall_s':count['full_wall_s']}),flush=True)
  if gate['qualified']:
   selected=profile
   for task in entry['public_tasks']:
    row=run_one(profile,'identity-deletion-neighbor',task,entry['optional_selected_profile_identity_deletion'],sources,count,deadline,adapter,task_module,facts)
    private_rows.append(row)
    if row['status']!='COMPLETE':
     finish('QUALIFIED_WITH_EXTRA_TOOL_ERROR',selected,private_rows,count,'Selected profile qualified; identity deletion extra tool incomplete.');return
   break
 finish('QUALIFIED' if selected else 'NOT_ESTABLISHED',selected,private_rows,count,'Finite table exhausted or first qualified profile; no holdout or method execution.')

def run_one(profile,design_name,task,design,sources,count,deadline,adapter,task_module,facts):
 label=profile+'-'+design_name+'-'+task['condition_id']
 existing=next((r for r in count['rows'] if r['label']==label),None)
 if existing is not None:
  if existing['status']=='RUNNING':raise RuntimeError('UNRESOLVED_PRIOR_ATTEMPT_NO_AUTOMATIC_RETRY')
  return existing
 if adapter.source_identity()!=sources:raise RuntimeError('SOURCE_CHANGED_BETWEEN_INPUTS')
 remaining=min(120.,900-count['full_wall_s'],deadline-time.time())
 if remaining<=0 or count['full_attempts']>=48:raise RuntimeError('A_QUALIFICATION_BUDGET_EXHAUSTED')
 stat=os.statvfs(R)
 if stat.f_bavail*stat.f_frsize<11500000000:raise RuntimeError('STORAGE_RESERVE_NOT_MET')
 folder=A/'runs'/(str(count['full_attempts']+1).zfill(2)+'-'+label);folder.mkdir(parents=True,exist_ok=False)
 decision={'actual_input':{'operation':'edit','design_patch':{k:deepcopy(v) for k,v in design.items() if v!=task['initial_design'][k]}}}
 inp={'classification':'PRIVATE_DEVELOPER_REFERENCE','profile':profile,'design_name':design_name,'task':task,'parent_design':task['initial_design'],'design':design,'problem':task['initial_problem'],'decision':decision,'sources':sources}
 write(folder/'input.json',inp)
 count['full_attempts']+=1
 row={'label':label,'profile':profile,'design_name':design_name,'condition_id':task['condition_id'],'status':'RUNNING','folder':str(folder.relative_to(A)),'input_sha256':digest_file(folder/'input.json'),'started_epoch':time.time(),'wall_cap_s':remaining}
 count['rows'].append(row);write(A/'counter.json',count)
 cache_before=set(task_module._STATIC_GEOMETRY_CACHE)
 start=time.monotonic();signal.setitimer(signal.ITIMER_REAL,remaining)
 try:
  public=adapter.execute(task,task['initial_design'],task['initial_problem'],decision,folder/'result',task_resolver=lambda task_id:task if task_id==task['task_id'] else None)
  row['status']='COMPLETE'
 except Exception as exc:
  row['status']='TOOL_ERROR';row['error_type']=type(exc).__name__;row['error_message']=str(exc)
  write(folder/'tool-error.json',{'status':'TOOL_ERROR','type':type(exc).__name__,'message':str(exc),'diagnostic':getattr(exc,'diagnostic',None),'traceback':traceback.format_exc(limit=8),'sources':sources,'no_service_verdict':True})
 finally:
  signal.setitimer(signal.ITIMER_REAL,0)
  row['elapsed_s']=time.monotonic()-start;count['full_wall_s']+=row['elapsed_s']
  new_cache=set(task_module._STATIC_GEOMETRY_CACHE)-cache_before
  row['static_geometry_real_misses']=len(new_cache);count['cheap_numeric']+=len(new_cache)
 if row['status']=='COMPLETE':
  raw=json.load(gzip.open(folder/'result/raw.json.gz','rt'));assessment=json.load(gzip.open(folder/'result/assessment.json.gz','rt'))
  counts=Counter(e['action'] for e in raw['activity']);view=facts.public_record_relations(public)
  write(folder/'public-relationship-view.json',view)
  row.update(model_valid=raw['model_valid'],domain_errors=raw['domain_errors'],verdict=assessment['verdict'],failures=assessment['failures'],unknown=assessment['unknown'],activity_counts=dict(counts),saved_records=len(raw['records']),wire_frames=len(raw['packets']),accepted_receive=len(assessment['receiver_records']),truth_events_private=len(assessment['truth']),missed_private=len(assessment['missed_event_ids']),same_record_retransmissions_private=len(assessment['receiver_identity']['same_record_wire_retransmissions']),sequence_reuse_private=len(assessment['receiver_identity']['different_saved_record_sequence_reuse']),boot_count=raw['boot_count'],energy=raw['energy'],holding_loads=raw.get('holding_loads'),steps=raw.get('solver_diagnostics',{}).get('iterations'),raw_sha256=digest_file(folder/'result/raw.json.gz'),assessment_sha256=digest_file(folder/'result/assessment.json.gz'),public_relation_sha256=digest_file(folder/'public-relationship-view.json'))
  assert raw['design']==design and raw['task_sha256']==adapter.digest(task)
  # Readback identity and original evaluator already ran through the adapter.
 write(folder/'summary-private.json',row);write(A/'counter.json',count)
 print(json.dumps({k:row[k] for k in ['label','status','elapsed_s']}),flush=True)
 if count['cheap_numeric']>32:raise RuntimeError('A_CHEAP_CAP_EXHAUSTED')
 return row

def finish(status,selected,rows,count,note):
 write(A/'mechanism-qualification.json',{'schema':'partial-ancestor-mechanism-qualification-v1','classification':'PRIVATE_DEVELOPER_REFERENCE','status':status,'selected_profile':selected,'package':'BF-PQE-PARTIAL-ANCESTOR-VALIDATION-20261026-001','frozen_rules':'qualification-rules.json','full_input_index':'qualification-private.json','results':rows,'cost':{k:count[k] for k in ['full_attempts','full_wall_s','cheap_numeric','software_cases','api_requests']},'note':note,'holdouts_executed':0,'method_performance_seen':False,'claim_boundary':'Finite candidate interaction only, no global necessity/physical/learning/method superiority.','next':'S0 reviews private qualification and applies declared mechanism admission/stop gate; source/controllers remain frozen.'})
 print(json.dumps({'A_qualification_status':status,'selected_profile_private':selected,'full_attempts':count['full_attempts'],'full_wall_s':count['full_wall_s'],'cheap_numeric':count['cheap_numeric']}),flush=True)

if __name__=='__main__':main()
