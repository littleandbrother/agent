"""Predeclare four unseen tasks and initial designs; no science/model execution."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,shutil,sys
A=Path(__file__).resolve().parent
OUT=A.parent
BASE=A.parents[1]
ROOT=A.parents[4]
SRC=ROOT/'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src'
sys.path.insert(0,str(SRC))
from bfworld.agentlab.pqe20261023bold import consumer,lc_adapter
PACKAGE='BF-PQE-ACTION-POLICY-20261024-001'

def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();b=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
def checked(r):
 v=ref(r['path']);assert all(v[k]==x for k,x in r.items()),('REFERENCE_CHANGED',r['path'])
 return read(r['path'])
def save(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def identity(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
features=read(ROOT/'feature_list.json')
feature=next(v for v in features.values() if isinstance(v,dict) and v.get('package')==PACKAGE)
assert feature['status']=='in-progress'
ownership=ref(OUT/'shared/OWNERSHIP.json')
free=shutil.disk_usage(A).free;assert free>=11_200_000_000
prior=read(BASE/'training-execution/shared/protocol.json')
door_entry=next(e for e in prior['training_tasks'] if e['world']=='DOOR')
door_base=checked(door_entry['task'])
# Original default LC public profile/initial design, not any successful solution.
dev=read(BASE/'lc-service-learning/a/DEVELOPMENT-TASKS.json')['entries'][1]
lc_public_base=checked(dev['public']);lc_host_base=checked(dev['host_task'])
initial_door=deepcopy(door_base['initial_design']);initial_lc=deepcopy(lc_public_base['Design'])
# All four definitions and order are written before task validation/results.
rules={'package':PACKAGE,'at_utc':now(),'selection':'One fixed deterministic rule per case, chosen before new-parent implementation, formation and all outcomes. No sweep, private oracle or replacement.',
 'order':['t1','t2','t3','t4'],'initial_design_policy':'Both DOOR tasks use the exact original Task initial_design; both LC tasks use the original default flat Design. No engineering winner or tested private solution chosen.',
 'shared_boundary':'Original24h/zero initial energy, consumers, loads, domains, physical dimensions, service thresholds, fixed firmware choices and observer capabilities retained.',
 'door':[
  {'role':'t1','id':'DOOR-AP-ASYMMETRIC-BURSTS-20261024-v1','starts_s':[75.0,89.0,31000.0,61000.0],
   'segments_angle_duration_pause':[[0,35,.5,.6],[35,70,1.4,0],[70,90,.4,.3],[90,55,.35,0],[55,15,1.2,0],[15,0,.25,0]],
   'gateway_windows':[[0,86400]],
   'mechanism_rule':'Four full cycles: one warm pair and two isolated cold opportunities. Interrupted early opening, slow middle opening and faster early closing alter when source work arrives relative to the original stable contact events. Link is continuously available.'},
  {'role':'t3','id':'DOOR-AP-PAIRED-REVERSALS-20261024-v1','starts_s':[150.0,43100.0],
   'segments_angle_duration_pause':[[0,88,1.1,.3],[88,5,.9,.25],[5,86,1.35,.4],[86,0,1.1,0]],
   'gateway_windows':[[0,152.1],[152.9,43102.1],[43102.9,86400]],
   'mechanism_rule':'Two four-event bursts with intermediate closed/open endpoints and asymmetric half-stroke rates. Link briefly drops during the first closing of each burst; event and mechanical-work timing also change, not just gateway position.'}],
 'lc':[
  {'role':'t2','id':'LC-PV-AP-LIGHT-BEFORE-LINK-20261024-v1','dark_interval_s':[18000,61200],
   'gateway_windows_s':[[0,10800],[62400,86400]],'recovery_at_s':62400,
   'light_blocks_s':[600,1800,900,1500],'irradiance_before':[.3,.85,.45,.95],'irradiance_after':[.3,.85,.45,.95],
   'shade_blocks_s':[2100,900,3000],'shade_before':[.65,.4,.9],'shade_after':[.65,.4,.9],
   'clock_error_ppm':9.0,'tau_s':18.0,'bias_c':.05,
   'thermal_knots':[[0,5],[12000,5],[12900,8],[14700,8],[15600,5],[35000,5],[36200,8.75],[38000,8.75],[39200,5],[86400,5]],
   'mechanism_rule':'Irregular light/shading blocks, then12h darkness. Light returns1200s before connectivity, so post-dark powered sampling and old/fresh queue work precede delivery recovery.'},
  {'role':'t4','id':'LC-PV-AP-LINK-IN-DARK-20261024-v1','dark_interval_s':[27000,70200],
   'gateway_windows_s':[[0,19800],[68400,86400]],'recovery_at_s':68400,
   'light_blocks_s':[1200,600,2400],'irradiance_before':[.65,.2,.9],'irradiance_after':[.4,.95,.3],
   'shade_blocks_s':[1800,3600],'shade_before':[.75,.5],'shade_after':[.9,.45],
   'clock_error_ppm':-13.0,'tau_s':30.0,'bias_c':.1,
   'thermal_knots':[[0,5],[7200,5],[8400,8.5],[10200,8.5],[11400,5],[48000,5],[49200,8],[51000,8],[52200,5],[86400,5]],
   'mechanism_rule':'New unequal light/shading blocks with different post-dark intensities. Connectivity returns1800s before the12h darkness ends, requiring any recovery service to be paid by retained stored energy rather than renewed harvest.'}],
 'privacy':'All rule/task/design/initial/manifest content is A/S0 host-only. Not for B, parent implementation, formation, training, selection or paper-development summaries.',
 'initial_execution':{'owner':'campaign-s0','maximum_per_task':1,'total_cap':4,'A_full_calls':0,'no_replacement':True},
 'checks_cap':4,'models':0,'no_extra_fields_or_model_branches':True}
save(A/'host/RULES.json',rules)
checks=[]
# CHECK1: consumer/profile/source and inherited initial contract only.
lc_sources=lc_adapter.source_identity();door_sources=consumer.source_identity()
assert lc_sources==prior['apparatus_source']['lc']
assert door_sources==prior['apparatus_source']['door']
assert initial_door==door_base['initial_design'] and initial_lc==lc_public_base['Design']
checks.append({'id':1,'name':'original_consumer_source_profile_and_initial_bindings','status':'PASS','full_inputs':0,'models':0})
entries=[]
for config in rules['door']:
 task=deepcopy(door_base)
 task.update(task_id=config['id'],family_id='AP-PREFROZEN-DOOR-20261024',
  exposure='Private prospective case fixed before the common new parent and formation.',
  description=config['mechanism_rule'])
 task['motion']=[]
 for start in config['starts_s']:
  t=start
  for lo,hi,duration,pause in config['segments_angle_duration_pause']:
   task['motion'].append({'start_s':t,'end_s':t+duration,'start_deg':lo,'end_deg':hi})
   t+=duration+pause
 task['gateway_windows']=deepcopy(config['gateway_windows'])
 task['initial_design']=deepcopy(initial_door)
 task['material_sources'].pop('bold_lineage',None)
 task['material_sources']['action_policy_generation']={'rules_ref':ref(A/'host/RULES.json'),
    'rule_role':config['role'],'base_task':door_entry['task'],'selected_before_parent_implementation':True}
 folder=A/'host'/config['role']
 save(folder/'task.json',task);save(folder/'initial-design.json',initial_door);save(folder/'initial-problem.json',task['initial_problem'])
 entries.append({'role':config['role'],'world':'DOOR','task':ref(folder/'task.json'),
   'initial_design':ref(folder/'initial-design.json'),'initial_problem':ref(folder/'initial-problem.json'),
   'task_id':task['task_id'],'status':'SEALED_NOT_EXECUTED','consumer':'bfworld.agentlab.pqe20261023bold.consumer.execute'})
# CHECK2: both DOOR schedules and unchanged original legal design/service.
for e in entries:
 task=checked(e['task']);consumer.validate_design(task,checked(e['initial_design']))
 assert task['service']==door_base['service'] and task['initial']==door_base['initial']
 assert task['design_domain']==door_base['design_domain'] and task['integration']==door_base['integration']
 last_time=0.0;last_angle=task['initial']['angle_deg']
 for seg in task['motion']:
  assert last_time<=seg['start_s']<seg['end_s']<=86400
  assert seg['start_deg']==last_angle and 0<=seg['start_deg']<=90 and 0<=seg['end_deg']<=90
  assert abs(seg['end_deg']-seg['start_deg'])/(seg['end_s']-seg['start_s'])<=120+1e-8
  last_time,last_angle=seg['end_s'],seg['end_deg']
 assert last_angle==0
 for i,(start,end) in enumerate(task['gateway_windows']):
  assert 0<=start<end<=86400 and (i==0 or task['gateway_windows'][i-1][1]<=start)
checks.append({'id':2,'name':'two_DOOR_static_motion_link_domain_and_original_service','status':'PASS','full_inputs':0,'models':0})

def blocks(start,end,lengths,values):
 result=[];t=start;i=0
 while t<end:
  stop=min(t+lengths[i%len(lengths)],end);result.append([t,stop,values[i%len(values)]]);t=stop;i+=1
 return result
for config in rules['lc']:
 host=deepcopy(lc_host_base);public=deepcopy(lc_public_base);start,end=config['dark_interval_s'];recovery=config['recovery_at_s']
 host.update(instance_id=config['id'],allowed_for_learning=False,description=config['mechanism_rule'])
 host['service'].update(dark_interval_s=[start,end],recovery_at_s=recovery,
  recovery_old_history_deadline_s=recovery+120,
  history=f'Every committed record retained without corruption; receive all pre-recovery unacknowledged records by{recovery+120} in acquisition order without duplicate logical samples.',
  new_sample_receive_scope='Every sample acquired while gateway is available must be received within10s of actual acquisition; no frame-label exemption.')
 host['gateway_windows_s']=deepcopy(config['gateway_windows_s'])
 light=blocks(0,start,config['light_blocks_s'],config['irradiance_before'])+[[start,end,0.0]]+blocks(end,86400,config['light_blocks_s'],config['irradiance_after'])
 shade=blocks(0,start,config['shade_blocks_s'],config['shade_before'])+[[start,end,.8]]+blocks(end,86400,config['shade_blocks_s'],config['shade_after'])
 host['optical_environment'].update(irradiance_schedule_w_m2=light,uniform_shading_transmission=shade)
 host['thermal_reference'].update(nominal_tau_s=config['tau_s'],nominal_bias_c=config['bias_c'],air_truth_piecewise_linear_knots_s_c=config['thermal_knots'])
 host['clock_reference']['nominal_rate_error_ppm']=config['clock_error_ppm']
 host['generation_receipt']={'rule_ref':ref(A/'host/RULES.json'),'role':config['role'],'selected_before_common_parent_and_formation':True,'science_or_private_solution_used':False}
 host['next_owner']='S0 executes exactly one common initial; no replacement or task-dependent revision.'
 pt=public['Task']
 pt.update(task_id=config['id'],instance_id=config['id'],description=config['mechanism_rule'],
  exposure='Private prospective case fixed before common new parent and formation.',
  service=deepcopy(host['service']),gateway_windows_s=deepcopy(host['gateway_windows_s']),
  optical_environment=deepcopy(host['optical_environment']),
  thermal_contract={k:deepcopy(v) for k,v in host['thermal_reference'].items() if k!='air_truth_piecewise_linear_knots_s_c'},
  clock_contract=deepcopy(host['clock_reference']))
 public['package']=PACKAGE
 task=lc_adapter.participant_task(public)
 folder=A/'host'/config['role']
 save(folder/'task.json',task);save(folder/'lc-public.json',public);save(folder/'lc-host-task.json',host)
 save(folder/'initial-design.json',initial_lc);save(folder/'initial-problem.json',public['Problem'])
 entries.append({'role':config['role'],'world':'LC-PV','task_id':task['task_id'],'task':ref(folder/'task.json'),
  'lc_public':ref(folder/'lc-public.json'),'lc_host_task':ref(folder/'lc-host-task.json'),
  'initial_design':ref(folder/'initial-design.json'),'initial_problem':ref(folder/'initial-problem.json'),
  'status':'SEALED_NOT_EXECUTED','consumer':'bfworld.agentlab.pqe20261023bold.lc_adapter.execute'})
# CHECK3: both LC bindings/one-sided domain assertions only, no PV/simulation call.
changed_service={'dark_interval_s','recovery_at_s','recovery_old_history_deadline_s','history','new_sample_receive_scope'}
for e in entries:
 if e['world']!='LC-PV':continue
 task=checked(e['task']);public=checked(e['lc_public']);host=checked(e['lc_host_task']);design=checked(e['initial_design'])
 assert public['Profile']==lc_public_base['Profile'] and design==lc_public_base['Design']
 assert public['Task']['design_domain']==lc_public_base['Task']['design_domain']
 assert public['Task']['fixed_program_semantics']==lc_public_base['Task']['fixed_program_semantics']
 assert {k:v for k,v in host['service'].items() if k not in changed_service}=={k:v for k,v in lc_host_base['service'].items() if k not in changed_service}
 assert host['initial']==lc_host_base['initial']
 inp=lc_adapter.bind_inputs(task,design,{'public':public,'host_task':host})
 assert inp['Profile']==lc_public_base['Profile']
 for field in ('irradiance_schedule_w_m2','uniform_shading_transmission'):
  schedule=host['optical_environment'][field];assert schedule[0][0]==0 and schedule[-1][1]==86400
  for i,(lo,hi,value) in enumerate(schedule):
   assert lo<hi and (i==0 or schedule[i-1][1]==lo)
   assert value>=0 and (field!='uniform_shading_transmission' or value<=1)
 dark=host['service']['dark_interval_s'];assert dark[1]-dark[0]==43200
 assert host['service']['recovery_old_history_deadline_s']-host['service']['recovery_at_s']==120
 assert any(lo==host['service']['recovery_at_s'] for lo,hi in host['gateway_windows_s'])
 for (ta,ya),(tb,yb) in zip(host['thermal_reference']['air_truth_piecewise_linear_knots_s_c'],host['thermal_reference']['air_truth_piecewise_linear_knots_s_c'][1:]):
  assert ta<tb and abs((yb-ya)/(tb-ta))<=host['thermal_reference']['max_abs_air_slew_c_s']
 assert abs(host['clock_reference']['nominal_rate_error_ppm'])<=host['clock_reference']['rate_bound_ppm']
checks.append({'id':3,'name':'two_LC_static_binding_light_thermal_clock_and_original_service','status':'PASS','full_inputs':0,'models':0})
entries.sort(key=lambda e:rules['order'].index(e['role']))
for e in entries:
 e['initial_execution_owner']='campaign-s0';e['initial_full_cap']=1;e['initial_status']='NOT_EXECUTED'
 e['suggested_initial_output']=str(OUT/'s0/host/initial'/e['role'])
 e['allowed_for_parent_implementation_formation_training_selection']=False
# CHECK4: all manifests references read back; all new task payloads host-only.
assert [e['role'] for e in entries]==rules['order'] and len({e['task_id'] for e in entries})==4
for e in entries:
 for value in e.values():
  if isinstance(value,dict) and 'path' in value:
   assert Path(value['path']).is_relative_to(A/'host');checked(value)
assert all(p.is_relative_to(A/'host') for p in A.rglob('*.json'))
checks.append({'id':4,'name':'all_four_order_ref_hash_readback_and_host_only_storage','status':'PASS','full_inputs':0,'models':0})
save(A/'host/CHECKS.json',{'package':PACKAGE,'at_utc':now(),'checks':checks,'cheap_checks':4,
 'scientific_dynamic_calls':0,'model_calls':0,'no_sampled_solutions_or_evaluator_runs':True,
 'meaning':'Static legality and artifact binding only; initial model-validity/service outcomes remain UNKNOWN until S0 single execution.'})
manifest={'schema':'action-policy-private-test-manifest-v1','package':PACKAGE,'at_utc':now(),
 'status':'FOUR_TASKS_AND_INITIAL_DESIGNS_SEALED_NO_EXECUTION','visibility':'A_S0_TEST_HOST_ONLY',
 'order':rules['order'],'entries':entries,'rules':ref(A/'host/RULES.json'),'checks':ref(A/'host/CHECKS.json'),
 'generator':ref(__file__),'interface':ref(A/'INTERFACE.md'),'ownership':ownership,
 'original_initial_design_sources':{'DOOR':{'container':door_entry['task'],'json_pointer':'/initial_design'},
   'LC':{'container':dev['public'],'json_pointer':'/Design'}},
 'original_consumer_sources':{'door':door_sources,'lc':lc_sources},
 'whole_design_oracle_or_scan':False,'private_success_answer':False,'fallback_tasks':[],
 'selected_before_common_parent_implementation_and_formation':True,
 'consumer_binding':'DOOR pass exact full task and trusted resolver to original BOLD consumer; LC pass task plus context(public=lc_public,host_task=lc_host_task). All initial_design/initial_problem refs are exact fixed defaults.',
 'execution_contract':{'unique_initial_owner':'campaign-s0','initial_calls_cap_total':4,'per_initial_cap':1,
  'A_scientific_calls':0,'A_models':0,'no_retry_or_task_replacement':True,
  'S0_saves_initials_in_own_path_and_adds_results_to_own_protocol':True,
  'no_task_or_initial_to_B_parent_design_formation_training_selection_or_paper_development':True},
 'checks_used':4,'checks_cap':4,
 'storage':{'free_before_bytes':free,'peak_additional_bytes_cap':1_200_000_000,'required_free_bytes':11_200_000_000,
   'A_manifest_task_retained_cap_bytes':2_000_000,'new_backups_env_worktrees':0}}
save(A/'host/MANIFEST.json',manifest)
print(json.dumps({'status':manifest['status'],'manifest':ref(A/'host/MANIFEST.json'),'rules':ref(A/'host/RULES.json'),
 'checks':ref(A/'host/CHECKS.json'),'checks_used':4,'new_science':0,'models':0,
 'A_logical_bytes':sum(p.stat().st_size for p in A.rglob('*') if p.is_file()),'free_bytes':shutil.disk_usage(A).free},ensure_ascii=False))
