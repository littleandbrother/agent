"""One prospective algebraic input-expression amendment; no scientific calls."""
import json,hashlib,math,datetime
from pathlib import Path
from copy import deepcopy
R=Path(__file__).resolve().parents[6]
M=Path(__file__).resolve().parent
A=M.parent
P=A.parent
MAX_SPEED=120.0
CAP=.99*MAX_SPEED

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def amend(original):
 task=deepcopy(original);pairs=[];previous_old=previous_new=0.
 for seg in original['motion']:
  gap=seg['start_s']-previous_old
  start=previous_new+gap
  distance=abs(seg['end_deg']-seg['start_deg'])
  duration=max(seg['end_s']-seg['start_s'],distance/CAP)
  end=start+duration
  # Directed endpoint rounding keeps the encoded derivative inside the cap.
  for _ in range(4):
   if end>start and distance/(end-start)<=CAP:break
   end=math.nextafter(end,math.inf)
  else:raise ValueError('BOUNDED_ENDPOINT_ROUNDING_FAILED')
  new={**seg,'start_s':start,'end_s':end};pairs.append((seg,new))
  previous_old,previous_new=seg['end_s'],end
 task['motion']=[new for old,new in pairs]
 old_anchor=original['selection_rule']['pulse_start_s']
 anchor=next(new['start_s'] for old,new in pairs if old['start_s']==old_anchor)
 # Gateway gaps were defined relative to the first pulse anchor; retain offsets.
 task['gateway_windows']=[[0. if left==0. else anchor+(left-old_anchor),86400. if right==86400. else anchor+(right-old_anchor)] for left,right in original['gateway_windows']]
 task['selection_rule']['pulse_start_s']=anchor
 task['selection_rule']['expression_amendment']={'version':'M2r-rate-interior-v1','rate_cap_deg_s':CAP,'original_task_sha256':digest(original),'rules':'same angle order and idle gaps; only speed-excess segments lengthened; gateway offsets from first pulse anchor retained'}
 task['family_id']=original['family_id'].replace('-M2','-M2r')
 task['task_id']=task['family_id']+':'+original['condition_id']
 # One bounded kinematic audit per exact task, including the two unexecuted holdouts.
 speeds=[abs((s['end_deg']-s['start_deg'])/(s['end_s']-s['start_s'])) for s in task['motion']]
 if max(speeds)>CAP:raise ValueError('AMENDED_RATE_NOT_INTERIOR')
 if task['motion'][-1]['end_s']>task['duration_s']:raise ValueError('HORIZON_CHANGED')
 for field in ['service','components','sensor','geometry','initial','initial_design','design_domain','duration_s']:
  if task[field]!=original[field]:raise ValueError('FORBIDDEN_INPUT_CHANGE:'+field)
 if [(s['start_deg'],s['end_deg']) for s in task['motion']]!=[(s['start_deg'],s['end_deg']) for s in original['motion']]:raise ValueError('ANGLE_SEQUENCE_CHANGED')
 return task,{'old_task_id':original['task_id'],'new_task_id':task['task_id'],'old_task_sha256':digest(original),'new_task_sha256':digest(task),'maximum_new_encoded_speed_deg_s':max(speeds),'cap_deg_s':CAP,'changed_segments':[{'index':i,'old':old,'new':new} for i,(old,new) in enumerate(pairs) if old!=new],'gateway_relation':'original offsets relative to first pulse anchor, with horizon edges unchanged','holdout':original['selection_rule']['is_isolated_holdout']}

def main():
 original_path=A/'qualification-private.json';old=json.loads(original_path.read_text());entry=next(x for x in old['profiles_in_order'] if x['profile']['id']=='M2');oldcounter=A/'counter.json';oldcount=json.loads(oldcounter.read_text());rules=json.loads((A/'qualification-rules.json').read_text())
 originals=entry['public_tasks']+entry['isolated_holdouts'];tasks=[];audits=[]
 for task in originals:
  new,audit=amend(task);tasks.append(new);audits.append(audit)
 # No private design editing: exact original five objects, and fixed original order.
 designs=deepcopy(entry['private_designs']);order=rules['design_order'];inputs=[];(M/'inputs').mkdir(exist_ok=False)
 source_root=R/'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src/bfworld/agentlab'
 source_files=[source_root/'pqe20261024debt'/n for n in ['consumer.py','holding.py','task.py','facts.py','bounds.py','adapter.py']]+[source_root/'pqe20261022'/n for n in ['door_model.py','door_program.py','executor.py','evaluator.py']]+[source_root/'pqe20261023bold'/n for n in ['consumer.py','firmware.py']]
 sources={str(p.relative_to(R)):sha(p) for p in source_files}
 for name in order:
  for task in tasks[:3]:
   original_row=next(r for r in oldcount['rows'] if r['profile']=='M2' and r['design_name']==name and r['condition_id']==task['condition_id'])
   decision={'actual_input':{'operation':'edit','design_patch':{k:deepcopy(v) for k,v in designs[name].items() if v!=task['initial_design'][k]}}}
   payload={'classification':'PRIVATE_DEVELOPER_REFERENCE','expression_amendment':'Exploratory post-qualification M2r; not original preregistered M2.','design_name':name,'task':task,'parent_design':task['initial_design'],'design':designs[name],'problem':task['initial_problem'],'decision':decision,'original_frozen_design_sha256':digest(entry['private_designs'][name]),'original_input_ref':str((A/original_row['folder']/'input.json').relative_to(R)),'original_input_sha256':sha(A/original_row['folder']/'input.json')}
   path=M/'inputs'/(str(len(inputs)+1).zfill(2)+'-'+name+'-'+task['condition_id']+'.json');write(path,payload);inputs.append({'order':len(inputs)+1,'design_name':name,'condition_id':task['condition_id'],'path':str(path.relative_to(R)),'sha256':sha(path)})
 write(M/'tasks-private.json',{'classification':'PRIVATE_DEVELOPER_REFERENCE','public_tasks':tasks[:3],'isolated_holdouts':tasks[3:],'holdouts_executed':0,'designs_unchanged_sha256':{k:digest(v) for k,v in designs.items()}})
 preserved=[A/'qualification-private.json',A/'qualification-rules.json',A/'mechanism-qualification.json',A/'counter.json',A/'independent-readback.json',A/'FINAL-EXIT.json']
 freeze={'schema':'M2r-input-expression-freeze-v1','classification':'PRIVATE_DEVELOPER_REFERENCE','package':'BF-PQE-PARTIAL-ANCESTOR-VALIDATION-20261026-001','frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'authority':'work order section9; one exploratory prospective expression amendment after original M2 UNKNOWN','corrector_ref':str(Path(__file__).relative_to(R)),'corrector_sha256':sha(Path(__file__)),'rule':'Every segment duration=max(original duration, angle distance/(0.99*original maximum speed)); rebuild in order preserving original encoded idle gaps; directed nextafter only ensures encoded speed<=118.8; same first-pulse-relative gateway offsets.','original_maximum_speed_deg_s':MAX_SPEED,'new_rate_cap_deg_s':CAP,'private_original_index_sha256':sha(original_path),'five_design_order':order,'sources_at_freeze':sources,'task_audits':audits,'tasks_private_ref':str((M/'tasks-private.json').relative_to(R)),'tasks_private_sha256':sha(M/'tasks-private.json'),'new_frozen_inputs':inputs,'qualification_full_cap_amended':63,'prior_actual_full':45,'new_full_cap':15,'max_actual_after_new':60,'original_A_consumer_wall_cap_s':900,'original_absolute_deadline_preserved':True,'global512_full_3600s_unchanged':True,'stop_rules':['Any model-invalid result or TOOL_ERROR stops affected M2r qualification immediately.','If identity-only passes all3, stop: no mechanism.','If complete reference has any non-PASS, stop: no mechanism.','If all main deletion neighbors pass, no finite interaction; no further task change.'],'admission_required':'shared/M2-expression-amendment-admission.json status READY_FOR_M2R_ONLY with exact freeze/source/input bindings','no_new_software_cases':True,'cheap_numeric_for_algebra_and_speed_audits':5,'old_records_preserved':{str(p.relative_to(R)):sha(p) for p in preserved},'no_holdout_execution_before_final_fixed_designs':True,'private_exposure':'A/S0 only; no B/controller private reference exposure.'}
 write(M/'INPUTS-FROZEN.json',freeze)
 write(M/'counter.json',{'package':freeze['package'],'scope':'M2r expression amendment only','prior_actual_full':45,'prior_actual_full_wall_s':oldcount['full_wall_s'],'prior_A_cheap_numeric':10,'full_attempts':0,'full_wall_s':0.,'cheap_numeric':5,'software_cases':0,'api_requests':0,'rows':[],'freeze_sha256':sha(M/'INPUTS-FROZEN.json')})
 print(json.dumps({'freeze':str(M/'INPUTS-FROZEN.json'),'freeze_sha256':sha(M/'INPUTS-FROZEN.json'),'inputs':15,'holdout_definitions':2,'new_full':0,'new_cheap':5,'A_cheap_cumulative':15,'max_speeds':[x['maximum_new_encoded_speed_deg_s'] for x in audits]},indent=2))
if __name__=='__main__':main()
