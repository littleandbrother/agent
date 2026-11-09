"""Bind the existing public training whitelist and host-only continuation tasks."""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
import hashlib,json,shutil,stat
A=Path(__file__).resolve().parent
BASE=A.parents[1]
OLD=BASE/'lc-service-learning'
ROOT=A.parents[4]
PACKAGE='BF-PQE-TRAINING-EXECUTION-20261024-001'

def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();s=p.stat();assert not (getattr(s,'st_flags',0)&0x40000000),'NO_CLOUD_HYDRATION'
 data=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
def checked(r):
 actual=ref(r['path']);assert all(actual[k]==v for k,v in r.items() if k in actual),('REFERENCE_CHANGED',r['path'])
 return read(r['path'])
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def save(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def strings(v):
 if isinstance(v,str):yield v
 elif isinstance(v,dict):
  for k,x in v.items():yield str(k);yield from strings(x)
 elif isinstance(v,list):
  for x in v:yield from strings(x)
free=shutil.disk_usage(A).free;assert free>=11_000_000_000
protocol_ref=ref(OLD/'shared/protocol.json');p=checked(protocol_ref)
public=p['public_bindings'];history=checked(public['history']);catalog=checked(public['catalog']);parent=checked(public['parent'])
assert len(history)==22 and len(catalog)==38
assert len(p['training_tasks'])==len(p['training_task_descriptors'])==len(p['tasks'])==2
freeze=checked(p['isolated_freeze'])
# This deny set is host-only audit policy. Do not pass it or this script to G/H.
forbidden_prefixes=[str(OLD/'a/host')+'/',str(OLD/'s0/episodes/t1-'),str(OLD/'s0/episodes/t2-'),
 str(OLD/'a/FINAL-READBACK'),str(OLD/'s0/REPORT'),str(OLD/'s0/RESULTS'),str(OLD/'s0/batch-result'),
 str(OLD/'s0/adoption'),str(OLD/'s0/resource-ledger'),str(OLD/'shared/merged-test-'),
 str(OLD/'s0/formed-program-freeze'),str(BASE/'training-execution/a/INPUT-BINDINGS')]
private_ids=['DOOR-LCLEARN-PAUSED-STROKE-20261024-v1','LC-PV-LCLEARN-INTERMITTENT-20261024-v1']
public_ids={'DOOR-BOLD-REVERSAL-20261023-v1','LC-PV-BOLD-UNSTABLE-20261023-v1'}
violations=[]
scanned=[]
metadata_paths=set()

def scan(label,obj):
 text_values=list(strings(obj));bad=[]
 for s in text_values:
  if any(x in s for x in private_ids+forbidden_prefixes):bad.append(s[:300])
  if s.startswith('/Users/'):metadata_paths.add(s)
 if bad:violations.append({'source':label,'values':bad[:10]})
 scanned.append({'source':label,'strings_checked':len(text_values),'forbidden_hits':len(bad)})
scan('common-history',history);scan('parent-program',parent)
scan('training-task-descriptors',p['training_task_descriptors'])
for r in history:
 assert r['allowed_for_learning'] is True
 assert r['source_id'] in catalog
 assert all(k in catalog for k in r['record_ref'])
 assert r['result']['result_sha256']==r['typed_view']['result_identity']['result_sha256'] if 'result_identity' in r['typed_view'] else True
assert len({r['incident_id'] for r in history})==22
source_files={};source_entries=[]
for source_id,r in catalog.items():
 assert r.get('visibility','PUBLIC')=='PUBLIC' and r.get('allowed_json_pointers',['/'])==['/']
 path=str(Path(r['path']).resolve())
 if path not in source_files:
  obj=checked(r);scan(path,obj);source_files[path]=ref(path)
 source_entries.append({'source_id':source_id,**r,'effective_visibility':'PUBLIC',
  'effective_allowed_json_pointers':r.get('allowed_json_pointers',['/']),
  'authorization_basis':'Original frozen public-source-catalog entry; missing legacy visibility fields do not expand access beyond this exact source.'})
scan('source-catalog',catalog)
training_bound=[]
for e,d in zip(p['training_tasks'],p['training_task_descriptors']):
 t=checked(e['task']);initial=checked(e['initial_public_result'])
 assert t['task_id']==d['task_id']==initial['task_id'] and t['task_id'] in public_ids
 scan('training-public-task:'+e['role'],d['public_task'])
 assert initial['result_sha256'] in {row['result']['result_sha256'] for row in history}
 # The host Task may include evaluation-only data; only the original descriptor
 # public_task is permitted in formation/training requests.
 host_refs={k:v for k,v in e.items() if isinstance(v,dict) and 'path' in v}
 for r in host_refs.values():checked(r)
 training_bound.append({'role':e['role'],'world':e['world'],'task_id':t['task_id'],
  'original_entry':deepcopy(e),'public_descriptor_index':p['training_task_descriptors'].index(d),
  'public_descriptor_canonical_sha256':canonical(d),'public_task_canonical_sha256':canonical(d['public_task']),
  'initial_public_result':e['initial_public_result'],
  'host_private_fields_not_exposed':['lc_host_task','raw Task container','assessment/raw/cache directories']})
continuations=[]
for e in p['tasks']:
 old=next(v for v in freeze['entries'] if v['role']==e['role'])
 assert e['task']==old['task'] and e['initial_public_result']==old['initial']['public-result.json']
 for k,v in e.items():
  if isinstance(v,dict) and 'path' in v:checked(v)
 # Bind full original initial chain by references; do not copy its objects.
 for r in old['initial'].values():checked(r)
 continuations.append({'role':e['role'],'world':e['world'],'original_entry':e,
  'original_initial_refs':old['initial'],'new_initial_inputs':0,
  'visibility':'TEST_EXECUTOR_ONLY_AFTER_METHOD_SELECTION_FREEZE',
  'classification':'Originally predeclared tasks continued with learner isolation; coordinator has seen earlier parent results. Not a new never-seen blind test.'})
assert not violations,violations
allow={'package':PACKAGE,'at_utc':datetime.now(timezone.utc).isoformat(),'status':'BOUND_PUBLIC_ALLOWLIST',
 'initial_history_count':22,'source_catalog_count':38,'unique_catalog_files':len(source_files),
 'parent':public['parent'],'history':public['history'],'source_catalog':public['catalog'],
 'allowed_incident_ids':[r['incident_id'] for r in history],
 'incident_source_mapping':[{'incident_id':r['incident_id'],'source_id':r['source_id'],'record_ref':r['record_ref']} for r in history],
 'source_entries':source_entries,
 'training_descriptor_selector':{'host_container':protocol_ref,'json_pointer':'/training_task_descriptors',
  'canonical_sha256':canonical(p['training_task_descriptors']),
  'whole_container_may_be_registered_or_sent':False,
  'instruction':'Trusted host extracts only this value. Protocol contains private test entries and is never a public object or file source.'},
 'access_rules':['Register only exact catalog values under these38 source IDs plus the22 history objects and parent contract/code.',
  'Nested path/hash metadata does not grant file access; unregistered references require explicit existing allowed source identity, never arbitrary path traversal.',
  'No wildcard directory access, candidate-cache listing or local filesystem tool for formation/training.',
  'Keep same initial facts and rights for both formations. During this run each may see only its own public training feedback; merge both only after selection freeze for tests.',
  'Source/incident IDs remain distinct. Preserve original object/view semantics and bounded paging without replacing one view by result identity.'],
 'verification_boundary':'This binds original permitted source content. Actual new registration/paging and serialized G-ATTRIBUTE/G-PROPOSE/feedback requests must be checked in S0/B one offline direct-path run; that runtime check has not been performed by A.',
 'historical_learning_flags':'Original source flags preserved; this work order authorizes the fixed seen development materials.'}
save(A/'FORMATION-ALLOWLIST.json',allow)
bindings={'package':PACKAGE,'at_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS_INPUT_BINDING_AND_SOURCE_ISOLATION',
 'visibility':'HOST_ONLY; never register or send this document, since it binds continued test inputs and initial results.',
 'prior_protocol':protocol_ref,'work_order':ref(BASE/'实际训练与隔离评价_执行贯通续包_20261024.md'),
 'ownership':ref(A.parent/'shared/OWNERSHIP.json'),'formation_allowlist':ref(A/'FORMATION-ALLOWLIST.json'),
 'training_tasks':training_bound,'continued_test_tasks':continuations,'original_isolated_freeze':p['isolated_freeze'],
 'catalog_files_verified':list(source_files.values()),'isolation_scan':{'items':scanned,'forbidden_hits':violations,
  'denied_prefixes':forbidden_prefixes,'private_test_ids':private_ids,'scanned_unique_catalog_files':len(source_files),
  'provenance':'Original22 history and38 catalog bound to prior frozen protocol; no previous continued-test result/report/summary added.',
  'metadata_path_access':'Exact allowlist only; referenced directories/host caches remain inaccessible.'},
 'host_cache_policy':'Test-only old scientific cache may match only an independently submitted exact full input. Its directory/index and previous test decisions/results/summaries must not enter formation/training/selection. Fresh parent must consume merged new training history and decide again.',
 'no_inferred_policy_from_previous_parent_tests':True,
 'counts':{'new_engineering':0,'new_initials':0,'private_scans_for_solution':0,'new_scientific_dynamic_inputs':0,'new_model_calls':0,
  'bounded_input_source_isolation_checks':1,'no_other_repository_or_ledger_audit':True},
 'runtime_scope_pending':'S0/B actual public-object registration/paging and serialized request check; source-level PASS is not execution-path certification.',
 'storage':{'free_before_bytes':free,'estimated_peak_additional_bytes':1_000_000_000,'new_output_logical_cap_bytes':1_000_000,
  'no_backups_environments_worktrees':True},
 'next_handoff':'S0 integrates exact allowlist, performs the single offline real nested-path check, then actual training; A waits for completed saved scientific outputs for one independent readback.'}
save(A/'INPUT-BINDINGS.json',bindings)
print(json.dumps({'status':bindings['status'],'input_bindings':ref(A/'INPUT-BINDINGS.json'),
 'formation_allowlist':ref(A/'FORMATION-ALLOWLIST.json'),'history':22,'catalog':38,
 'unique_catalog_files':len(source_files),'training_tasks':len(training_bound),'continued_tests':len(continuations),
 'source_isolation_checks':1,'new_science':0,'new_model':0,'runtime_check':'PENDING_S0_B'},ensure_ascii=False))
