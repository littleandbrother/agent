"""One-shot M2 input freeze. Stdlib metadata construction only; no scoring or simulation."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
SRC = CAN / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022'
BASE_PATH = CAN / 'studies/pqe20261022/e3lc/private/task.json'
PUBLIC_PATH = CAN / 'studies/pqe20261022/shared/public-materials.json'
PACKAGE = 'BF-PQE-DYNAMIC-DECISION-M2-20261023-001'
BASE_BYTES_SHA = 'b829230f558eac113ae42e6f090d76b183563f4079ff48ba743d6293e69fe29a'
BASE_ID = '718c8148709275018c00175833246c0fa40a72209e8366b746a1dc1f8a3b3b33'
PUBLIC_BYTES_SHA = '098c419025cc61cd846a686ca16a5f788e516928826a252177e5dcd64f6c4e8b'
EXPECTED = {
 'door_model.py':'eabc8a422ece68b36bcaf0d194a2332f1941a5bc24d541dd7d4ff1dac96e3d53',
 'door_program.py':'f5e05fde4534a09f61364cf6a7f37660781ca7fc497a008e488962b7358e8cc2',
 'engineering.py':'b21abc3fdd35768afb475cddc96a887123e6a0f2380e5289bcbd24505d51acec',
 'executor.py':'36803b22b9495e8cd9050b61795b95876f0ef801f7c0e7057444bdae8247b2b0',
 'evaluator.py':'5ca8799028fb2af212f62207bd00a868d3518aec37b2739f5a78121d3817cde3',
 'adapter.py':'fce8c5ff1dbc93b54cac1992224f24ee88b7f436e5042522ba0cb2b559990caf',
 'dynamic_relations.py':'a6e75e19511b90f08e645b549f62e2784d0ffc1167714b18199637b08d415cea',
 'dynamic_methods.py':'b14312f24bb3e0c0ac57036a68f54b2eb4930a432b85a5b0ee28bc89dc7f7033',
}
TASK_FIELDS = {'schema_version','task_id','description','service','services','design_domain',
 'components','integration','duration_s','budget','allowed_operations','model_domain',
 'public_inputs','initial','motion','sensor','geometry','gateway_windows','material_sources'}
IMMUTABLE_FIELDS = ('schema_version','duration_s','initial','geometry','sensor','service',
                    'components','integration','design_domain')

def digest(x):
 return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def sha(b):
 return hashlib.sha256(b).hexdigest()

def encode(x):
 return (json.dumps(x,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+chr(10)).encode()

def bound_read(p, expected):
 b=p.read_bytes()
 if sha(b)!=expected: raise RuntimeError('FROZEN_SOURCE_MISMATCH:'+str(p))
 return b

def motion_condition(base):
 # Retain original angle breakpoints/cold-cycle starts; reshape within each sweep.
 out=[]
 for c in range(0,len(base['motion']),6):
  block=base['motion'][c:c+6]
  t=block[0]['start_s']
  hold=block[3]['start_s']-block[2]['end_s']
  for j,s in enumerate(block):
   if j==3: t+=hold
   multiplier=(1.5,1.5,0.75)[j%3]
   length=(s['end_s']-s['start_s'])*multiplier
   out.append({'start_s':t,'end_s':t+length,'start_deg':s['start_deg'],'end_deg':s['end_deg']})
   t+=length
 return out

def gateway_condition(base):
 outages=[]
 for j,s in enumerate(base['motion']):
  if j%3==2: outages.append([s['start_s']-0.1,s['end_s']+0.65])
 windows=[]
 cursor=0.0
 for a,b in outages:
  if not cursor<=a<b<=base['duration_s']: raise RuntimeError('OUTAGE_ORDER')
  windows.append([cursor,a]);cursor=b
 windows.append([cursor,base['duration_s']])
 return windows,outages

def structural_check(base,task):
 for k in IMMUTABLE_FIELDS:
  if task[k]!=base[k]: raise RuntimeError('SCIENCE_CHANGED:'+k)
 angle=task['initial']['angle_deg'];end=0.0
 for s in task['motion']:
  if not 0<=end<=s['start_s']<s['end_s']<=task['duration_s']: raise RuntimeError('MOTION_ORDER')
  if s['start_deg']!=angle or not 0<=s['start_deg']<=90 or not 0<=s['end_deg']<=90: raise RuntimeError('MOTION_CONTINUITY')
  if abs((s['end_deg']-s['start_deg'])/(s['end_s']-s['start_s']))>120+1e-7: raise RuntimeError('MOTION_SPEED')
  angle=s['end_deg'];end=s['end_s']
 for a,b in task['gateway_windows']:
  if not 0<=a<b<=task['duration_s']: raise RuntimeError('GATEWAY_WINDOW')
 d=task['initial_design']
 if set(d)!=set(task['design_domain']): raise RuntimeError('INITIAL_FIELDS')
 for k,spec in task['design_domain'].items():
  v=d[k]
  if spec['kind']=='number' and not spec['min']<=v<=spec['max']: raise RuntimeError('INITIAL_DOMAIN:'+k)
  if spec['kind']=='boolean' and type(v) is not bool: raise RuntimeError('INITIAL_BOOL:'+k)
  if spec['kind']=='mechanism':
   if set(v)-set(spec['editable']):raise RuntimeError('INITIAL_MECHANISM')
   for name,value in v.items():
    if not spec['editable'][name][0]<=value<=spec['editable'][name][1]:raise RuntimeError('INITIAL_MECHANISM_RANGE')
 if not d['brownout_v']<d['startup_v']<=task['components']['max_v']:raise RuntimeError('INITIAL_THRESHOLDS')
 # No source_step, predictor, evaluator, engineering construction or feasibility check.
 return {'input_structure':True,'unchanged_science_fields':list(IMMUTABLE_FIELDS),
         'motion_segments':len(task['motion']),'maximum_speed_deg_s':max(abs((s['end_deg']-s['start_deg'])/(s['end_s']-s['start_s'])) for s in task['motion']),
         'initial_scalar_and_permission_bounds':True,'joint_dynamic_domain_and_service':'NOT_EVALUATED'}

def construct():
 base=json.loads(bound_read(BASE_PATH,BASE_BYTES_SHA))
 if digest(base)!=BASE_ID:raise RuntimeError('BASE_CANONICAL_ID')
 old_public=json.loads(bound_read(PUBLIC_PATH,PUBLIC_BYTES_SHA))['DOOR-DEV-D04-v1']['public_inputs']
 source={}
 for name,expected in EXPECTED.items():
  b=bound_read(SRC/name,expected)
  source[name]={'path':str(SRC/name),'sha256':sha(b),'bytes':len(b)}
 initial=deepcopy(base['initial_design'])
 # This is the old pre-repair initial point, never either M1 PASS design.
 problem={'active_variables':list(base['design_domain']),
          'groups':[list(base['design_domain'])],'fixed_choices':{},
          'assumptions':['Every variable in the complete Task design_domain is authorized for every condition.',
                         'Task motion, gateway windows, initial physical state, service, loads and evaluator are fixed.',
                         'A finite execution failure is not a whole-domain conclusion.'],
          'local_objective':'Meet every unchanged service constraint with legal design and problem edits.'}
 specs=[('DOOR-M2-START-TX-20261023-v1','startup_tx_tradeoff'),
        ('DOOR-M2-GATE-RECOVER-20261023-v1','source_gateway_recovery_offset')]
 catalog={};entries=[];payloads={}
 for ordinal,(task_id,mechanism) in enumerate(specs,1):
  task=deepcopy(base)
  task.update(task_id=task_id,exposure='Exposed M2 development mechanism instance, frozen before group solutions; not held-out transfer.',
              family_id='M2-DOOR-DEVELOPMENT',allowed_for_learning=False,
              description='Record every stable opening and closing in this prescribed 24-hour development trajectory and receive it independently within the original 2-second deadline. All legal design-domain edits are available.',
              initial_design=deepcopy(initial),initial_problem=deepcopy(problem),
              qualification_claim='Finite constructed computational mechanism task; no physical or population reliability qualification.',
              public_inputs=deepcopy(old_public))
  task['material_sources'].pop('e3_lineage',None)
  if ordinal==1:
   task['motion']=motion_condition(base)
   rationale={'mechanism':mechanism,'construction':'For every original three-segment opening/closing, multiply the first two segment durations by 3/2 and the terminal duration by 3/4. Retain angle breakpoints, cold-cycle starts and the original open-to-close hold. Gateway remains always available.',
              'purpose':'Alter source arrival before and near first effective contacts, exposing cold-start versus TX completion choices.',
              'not_assumed':'Total harvested energy is not held equal; feasibility and a complete solution are unknown.'}
  else:
   task['gateway_windows'],outages=gateway_condition(base)
   rationale={'mechanism':mechanism,'construction':'Retain the original piecewise motion. For each terminal opening/closing segment, close the gateway from segment.start_s-0.10 to segment.end_s+0.65; use the complement within 24h as the only gateway windows.',
              'outages_s':outages,'purpose':'Place gateway recovery after the moving-source segment; repeated TX, paid SAVE/ACK and powered state retention remain original consumer mechanisms.',
              'not_assumed':'The initial design may or may not transmit before recovery; a one-TX approximation does not certify retry/retention service.'}
  task['material_sources']['m2_lineage']={'base_task_canonical_sha256':BASE_ID,
      'generation_rule':rationale['construction'],
      'selection':'Exactly one concrete instance per declared mechanism; no score, simulation, answer search or method outcome used; retain PASS/FAIL/UNKNOWN/error without replacement.',
      'role':'Development mechanism comparison; not fresh family, transfer or statistical test set.'}
  check=structural_check(base,task)
  if task['motion']==base['motion'] and task['gateway_windows']==base['gateway_windows']:raise RuntimeError('OLD_PHYSICAL_INPUT')
  public={k:deepcopy(v) for k,v in task.items() if k in TASK_FIELDS}
  packet={'schema_version':'pqe-m2-public-input-v1','task':public,'initial_design':deepcopy(initial),'initial_problem':deepcopy(problem)}
  rel='public/task-%02d-input.json'%ordinal
  payloads[rel]=packet;catalog[task_id]=task
  entries.append({'ordinal':ordinal,'task_id':task_id,'mechanism':mechanism,'status':'EXPRESSIBLE_NOT_YET_EXECUTED',
    'host_task_key':task_id,'task_canonical_sha256':digest(task),'public_task_canonical_sha256':digest(public),
    'public_input_path':rel,'initial_design_sha256':digest(initial),'initial_problem_sha256':digest(problem),
    'generation':rationale,'structural_checks':check,'initial_dynamic_executions_A':0,'expected_label':'NOT_COMPUTED'})
 payloads['host/tasks.json']=catalog
 public_sources={name:{'sha256':source[name]['sha256'],'source':(SRC/name).read_text()} for name in
                 ('door_model.py','door_program.py','engineering.py','dynamic_relations.py')}
 payloads['public/source-materials.json']={'schema_version':'pqe-m2-public-source-materials-v1',
    'public_inputs':deepcopy(old_public),'source_files':public_sources,
    'common_tools':['extract_phase_facts(task, design, public_result)','predict_candidate(task, design, phase_facts=None)'],
    'tool_scope':'Facts and conditional approximations only; all predicted service verdicts remain UNKNOWN. No selected candidate or repair answer is supplied by this material.',
    'result_boundary':'No host raw assessment, per-event expected truth or private receiver diagnostics. Original public Result/details are shared equally after S0 execution.',
    'task_source':'Every condition receives the same frozen task input packet and current public evidence.'}
 return payloads,entries,source

def main():
 verify=sys.argv[1:]==['--verify']
 if sys.argv[1:] and not verify:raise SystemExit('Only --verify is supported')
 manifest_path=HERE/'TASKS-MANIFEST.json'
 payloads,entries,sources=construct()
 if verify:
  m=json.loads(manifest_path.read_text())
  for item in m['files']:
   b=(HERE/item['path']).read_bytes()
   if sha(b)!=item['sha256']:raise RuntimeError('OUTPUT_BYTE_MISMATCH:'+item['path'])
  for path,value in payloads.items():
   if json.loads((HERE/path).read_text())!=value:raise RuntimeError('RECONSTRUCTION_MISMATCH:'+path)
  print(json.dumps({'status':'VERIFIED_METADATA_ONLY','tasks':len(entries),'new_dynamic':0,'new_cheap':0,'new_models':0}));return
 if manifest_path.exists():raise RuntimeError('ALREADY_FROZEN_NO_OVERWRITE')
 import os
 stat=os.statvfs(HERE)
 free=stat.f_bavail*stat.f_frsize
 if free<10001000000:raise RuntimeError('CAPACITY_GATE')
 files=[]
 for rel,value in payloads.items():
  target=HERE/rel;target.parent.mkdir(parents=True,exist_ok=True)
  b=encode(value)
  with target.open('xb') as f:f.write(b)
  if target.read_bytes()!=b:raise RuntimeError('READBACK_MISMATCH')
  files.append({'path':rel,'sha256':sha(b),'bytes':len(b)})
 manifest={'schema_version':'pqe-m2-task-freeze-v1','package':PACKAGE,'owner':'campaign-a',
   'frozen_at':datetime.now(timezone.utc).isoformat(),'status':'FROZEN_BEFORE_ANY_M2_GROUP_RESULT',
   'host_task_catalog':'host/tasks.json','task_entries':entries,'files':files,
   'shared_public_materials':'public/source-materials.json','initial_design_origin':'Unchanged base Task.initial_design, a pre-repair initial point. No M1 successful C/base/stroke/gate combination is used.',
   'base_task':{'path':str(BASE_PATH),'byte_sha256':BASE_BYTES_SHA,'canonical_sha256':BASE_ID},
   'source_identities':sources,'generator':{'path':'freeze_inputs.py','sha256':sha(Path(__file__).read_bytes()),
   'basis':'Original piecewise-linear input contract, angle/speed domain, gateway window semantics and program retry; exposed development rules instantiated once with rational timing factors. Numeric M2 factors are declared here, not claimed as a previously sampled official distribution.',
   'random_or_method_inputs':None,'solution_search':False,'outcome_selection':False},
   'run_order':[{'task_ordinal':n,'condition':c} for n in (1,2) for c in ('G','F','U')],
   'execution_authority':'S0 alone: one common initial per task followed by G,F,U once; A performs zero full dynamic, cheap prediction or model calls.',
   'pre_run_requirement':'B wrapper/method source freeze before S0 initial executions; all conditions share the same initial public result. Do not expose host/tasks.json or host assessment as participant state.',
   'private_evaluation':'No expected truth or outcomes computed by A; S0 original evaluator retains assessments on host and exposes only original public Result.',
   'caps':{'A_dynamic':0,'A_cheap':0,'A_model':0,'global_dynamic':20,'global_cheap':144,'G_episodes':2,'global_usd':10,'per_track_candidates_including_cache':3,'per_track_cheap':24},
   'storage':{'available_before_bytes':free,'estimated_peak_additional_bytes':1000000,'retained_A_cap_bytes':1000000,'global_retained_cap_bytes':80000000,'global_peak_bytes':800000000},
   'claim_boundary':'Two pre-frozen development mechanism conditions only, no stable success rate, unseen transfer, automatic H learning or physical qualification.',
   'stop':'Keep any PASS/FAIL/UNKNOWN/difficult/tool-error instance; no replacement, scan, tuning, extra reference or group rerun.'}
 b=encode(manifest)
 with manifest_path.open('xb') as f:f.write(b)
 if json.loads(manifest_path.read_text())!=manifest:raise RuntimeError('MANIFEST_READBACK')
 print(json.dumps({'status':manifest['status'],'manifest':str(manifest_path),'manifest_sha256':sha(b),'tasks':[{k:e[k] for k in ('ordinal','task_id','task_canonical_sha256','public_task_canonical_sha256')} for e in entries],'new_dynamic':0,'new_cheap':0,'new_models':0}))

if __name__=='__main__':main()
