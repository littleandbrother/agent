"""Read only the14 declared full-result references; replay6 unique saved results."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter,defaultdict
import ast,builtins,hashlib,importlib.util,json,shutil,types
A=Path(__file__).resolve().parent
OUT=A.parent
BASE=A.parents[1]
ROOT=A.parents[4]
SRC=ROOT/'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src/bfworld/agentlab'
LC_REVIEW=BASE/'stage3-e2main/a/readback_lcpv.py'
DOOR_REVIEW=SRC/'pqe20261022/evaluator.py'

def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();b=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
def checked(r):
 v=ref(r['path']);assert all(v[k]==x for k,x in r.items()),('REFERENCE_CHANGED',r['path'])
 return read(r['path'])
def identity(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def save(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
ledger_ref=ref(OUT/'s0/resource-ledger.json');ledger=checked(ledger_ref)
protocol_ref=ref(OUT/'shared/protocol.json');protocol=checked(protocol_ref)
batch_ref=ref(OUT/'s0/batch-result.json');batch=checked(batch_ref);assert batch['complete'] is True
assert len(ledger['attempts'])==14
assert sum(r['new_full_dynamic_inputs'] for r in ledger['attempts'])==ledger['full_dynamic_inputs']==2
assert sum(bool(r['reused']) for r in ledger['attempts'])==ledger['cache_reuses']==12
assert ledger['new_engineering_initials']==0
assert ref(LC_REVIEW)['sha256']==protocol['source_bindings'][str(LC_REVIEW)]=='27fae669a3ae199660116b1e7a5d228067ae0b551d53f378e51a11b13c91ecea'
assert ref(DOOR_REVIEW)['sha256']==protocol['source_bindings'][str(DOOR_REVIEW)]=='5ca8799028fb2af212f62207bd00a868d3518aec37b2739f5a78121d3817cde3'
# LC is an unmodified standalone stdlib reviewer.
spec=importlib.util.spec_from_file_location('train_exit_lc_readback',LC_REVIEW)
lc_review=importlib.util.module_from_spec(spec);spec.loader.exec_module(lc_review)
# Door evaluator's only producer-module dependency is the pure identity helper.
# Extract that exact function from the frozen executor AST, without importing or
# executing the simulator module, then resolve only this import to the helper.
exec_path=SRC/'pqe20261022/executor.py'
assert ref(exec_path)['sha256']==protocol['source_bindings'][str(exec_path)]
identity_node=next(n for n in ast.parse(exec_path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='identity')
helper={'hashlib':hashlib,'json':json}
exec(compile(ast.Module(body=[identity_node],type_ignores=[]),str(exec_path), 'exec'),helper)
assert helper['identity']({'校验':[1,2.0]})==identity({'校验':[1,2.0]})
normal_import=builtins.__import__
def door_import(name,globals=None,locals=None,fromlist=(),level=0):
 if name=='executor' and level==1 and tuple(fromlist)==('identity',):return types.SimpleNamespace(identity=helper['identity'])
 if name=='binascii' and level==0:return normal_import(name,globals,locals,fromlist,level)
 raise RuntimeError(('UNEXPECTED_EVALUATOR_IMPORT',name,level))
door_namespace={'__name__':'saved_door_evaluator','__package__':'saved_only','__builtins__':{**vars(builtins),'__import__':door_import}}
exec(compile(DOOR_REVIEW.read_bytes(),str(DOOR_REVIEW),'exec'),door_namespace)
# Verify only the actual scientific consumer/evaluator sources, not method or
# formation sources and not the entire prior repository.
verified_sources={}
for world,mapping in protocol['apparatus_source'].items():
 for key,digest in mapping.items():
  if key.startswith('/'):
   path=Path(key)
  elif key.startswith('bold/'):
   path=SRC/'pqe20261023bold'/key.split('/',1)[1]
  else:path=SRC/'pqe20261022'/key
  source=ref(path);assert source['sha256']==digest,('APPARATUS_CHANGED',str(path))
  verified_sources[str(path)]=source
entries={}
for kind in ('training_tasks','tasks'):
 for entry in protocol[kind]:
  task=checked(entry['task']);ctx=None
  if entry['world']=='LC-PV':ctx={'public':checked(entry['lc_public']),'host_task':checked(entry['lc_host_task'])}
  entries[task['task_id']]={'entry':entry,'task':task,'context':ctx,'kind':kind}
unique={};row_checks=[]
for number,row in enumerate(ledger['attempts'],1):
 info=entries[row['task_id']];entry,task,ctx=info['entry'],info['task'],info['context']
 declared={k:row[k] for k in ('raw','assessment','public_result')}
 for r in declared.values():checked(r)
 folder=Path(row['raw']['path']).parent
 raw,assessment,pub=read(folder/'raw.json'),read(folder/'assessment.json'),read(folder/'public-result.json')
 design=pub['design'];world=entry['world'];sources=protocol['apparatus_source']['lc' if world=='LC-PV' else 'door']
 assert row['public_check']==pub['public_check'] and row['model_valid']==pub['model_valid']
 assert identity(task)==pub['task_sha256'] and pub['sources']==sources
 assert identity({k:v for k,v in raw.items() if k!='result_sha256'})==raw['result_sha256']==pub['result_sha256']
 for key,value in row['decision']['actual_input'].get('design_patch',{}).items():assert design[key]==value
 dt=row['decision']['actual_input'].get('dt_s',task['integration']['dt_s'])
 key=identity({'task':task,'design':design,'dt_s':dt,'consumer':sources,'lc_inputs':ctx})
 assert key==row['cache_key'],('CACHE_INPUT_MISMATCH',number)
 canonical_key=(world,raw['result_sha256'])
 if canonical_key not in unique:
  decision=read(folder/'decision.json');assert decision['actual_design']==design and decision['sources']==sources
  files={name:ref(folder/name) for name in ('raw.json','assessment.json','public-result.json','decision.json')}
  result={'world':world,'task_id':task['task_id'],'task_source':entry['task'],'scope':info['kind'],
    'first_ledger_row':number,'actual_design':design,'result_sha256':raw['result_sha256'],'files':files,
    'model_valid':pub['model_valid'],'domain_errors':pub['domain_errors'],'verdict':assessment['verdict'],
    'failures':assessment['failures'],'unknown':assessment['unknown']}
  if world=='LC-PV':
   inp=read(folder/'input.json');files['input.json']=ref(folder/'input.json');public=ctx['public']
   assert inp['Task']==ctx['host_task'] and inp['Profile']==public['Profile']
   assert inp['Design']=={k:design[k] for k in public['design_fields']}
   assert inp['Program']=={**public['Task']['fixed_program_semantics'],**{k:design[k] for k in public['program_fields']}}
   assert raw['input_sha256']==identity(inp)==assessment['input_sha256']==decision['consumer_input_sha256']
   assert all(sources[k]==v for k,v in raw['sources'].items())
   computed=lc_review.review(inp,raw)
   assert all(assessment[k]==v for k,v in computed.items()),('LC_READBACK_DIFFERENCE',number)
   assert sorted(k.upper() for k,v in computed['gates'].items() if not v)==assessment['failures']
   start,end=inp['Task']['service']['dark_interval_s']
   result.update(gates=computed['gates'],service_facts=computed['facts'],independent_checks=computed['independent_checks'],
    diagnostics={'first_boot_s':raw['first_boot_s'],'dark_samples':sum(start<=s['time_s']<=end for s in raw['samples']),
      'pre_recovery_samples':sum(s['time_s']<inp['Task']['service']['recovery_at_s'] for s in raw['samples']),
      'final_pending':raw['final_state']['pending'],'final_energy_j':raw['final_state']['energy_j'],
      'history_gate_empty':computed['facts']['pending_old_at_recovery']==0})
  else:
   assert raw['design']==design and raw['task_sha256']==identity(task) and raw['design_sha256']==identity(design)
   assert raw['dt_s']==dt and identity(raw['engineering_model'])==raw['engineering_model_sha256']==pub['engineering_model_sha256']
   computed=door_namespace['evaluate'](task,design,raw)
   assert computed==assessment,('DOOR_READBACK_DIFFERENCE',number)
   result.update(service_facts={'truth_events':len(computed['truth']),'received':len(computed['receiver_records']),
     'timely_matches':len(computed['matches']),'maximum_matched_latency_s':max((m['latency_s'] for m in computed['matches']),default=None),
     'missed':computed['missed_event_ids'],'unmatched':computed['unmatched_records'],'duplicate_wire_frames':computed['duplicate_wire_frames'],
     'peak_handle_force_n':raw['peak_handle_force_n'],'minimum_tx_terminal_v':raw['minimum_tx_terminal_v'],
     'remaining_queue':raw['remaining_queue']},
    energy=raw['energy'],program_phase_energy_j=raw['program_state']['phase_energy_j'],
    independent_checks={'exact_original_assessment_replay':True,'mechanical_residual_j':computed['mechanical_residual_j'],
     'storage_residual_j':computed['storage_residual_j'],'energy_tolerance_j':computed['energy_tolerance_j']},
    model_domain_interpretation='Original domain verdict retained. Receiver count does not establish service when model_valid is false; no new geometric/physical qualification is inferred.')
  assert computed['verdict']==pub['public_check']['verdict']
  assert assessment['failures']==pub['public_check']['failures'] and assessment['unknown']==pub['public_check']['unknown']
  result['independent_readback_identical']=True
  unique[canonical_key]=result
 row_checks.append({'ledger_row':number,'category':row['category'],'world':world,'task_id':row['task_id'],
  'selected_id':row['decision'].get('selected_id'),'cache_key':key,'exact_cache_input_verified':True,
  'new_full_dynamic_inputs':row['new_full_dynamic_inputs'],'reused':row['reused'],'canonical_result_sha256':raw['result_sha256'],
  'verdict':pub['public_check']['verdict'],'model_valid':pub['model_valid'],
  'original_refs':declared})
assert len(unique)==6
category_counts={}
for category in sorted({r['category'] for r in row_checks}):
 rr=[r for r in row_checks if r['category']==category]
 category_counts[category]={'evaluations':len(rr),'new_full_inputs':sum(r['new_full_dynamic_inputs'] for r in rr),
  'exact_reuses':sum(r['reused'] for r in rr),'service_verdicts':dict(Counter(r['verdict'] for r in rr))}
# Context only: unchanged original initial public result supports the initial
# service state. This is not an additional original-evaluator replay or a method
# Update/Stop audit, which belongs to S0/B.
initial_context=[]
for kind in ('training_tasks','tasks'):
 e=next(e for e in protocol[kind] if e['world']=='DOOR');pub=checked(e['initial_public_result'])
 initial_context.append({'kind':kind,'public_result':e['initial_public_result'],'original_public_check':pub['public_check'],
  'model_valid':pub['model_valid'],'evaluation_replayed_in_this_exit':False})
assert not any(r['category']=='t1-h1' for r in ledger['attempts'])
not_executed=[r['episode'] for r in batch['rows'] if r['status']=='NOT_EXECUTED_NO_QUALIFIED_DESCENDANT']
assert len(not_executed)==4
summary={'package':ledger['package'],'at_utc':datetime.now(timezone.utc).isoformat(),
 'status':'PASS_INDEPENDENT_SAVED_SERVICE_READBACK','status_means':'Stored evidence/reviewer agreement only, not all-service success.',
 'inputs':{'ledger_at_review':ledger_ref,'protocol':protocol_ref,'batch_at_review':batch_ref},
 'readback_program':ref(__file__),'reviewers':{'LC':ref(LC_REVIEW),'DOOR':ref(DOOR_REVIEW),'DOOR_identity_source':ref(exec_path)},
 'door_loading_boundary':'Original evaluator source executed unchanged with its only executor import resolved to the exact identity function extracted from the frozen executor AST. No executor module or simulator loaded or called.',
 'scientific_sources_verified':list(verified_sources.values()),'unique_results':list(unique.values()),
 'row_checks':row_checks,'by_category':category_counts,'unique_service_verdicts':dict(Counter(r['verdict'] for r in unique.values())),
 'scientific_dispatch_counts':{'actual_candidate_evaluations':14,'new_full_inputs':2,'exact_reused_evaluations':12,'new_engineering':0,'new_initials':0},
 'exit_audit_cost':{'unique_saved_results_reviewed':6,'saved_review_calls_total':7,'LC_saved_review_calls':5,'DOOR_saved_review_calls':2,
  'partial_attempt':{'completed_saved_LC_reviews':1,'error':'Readback wrapper expected failures on pure LC reviewer result; original LC reviewer returns gates. One stored review repeated after correcting wrapper access to already-verified assessment failures. No science rerun or source change.'},
  'new_full_inputs':0,'new_model_calls':0,'new_experimental_cheap_checks':0},
 'original_initial_context':initial_context,'t1_h1_new_candidate_count':0,
 'not_executed_child_cells_from_batch':not_executed,
 'scope':'Only actual original scientific-service results and exact reuse bindings. Formation, revision logic, history consumption, stopping rationale, cost/usage settlement and method causation are not independently audited here.',
 'important_boundary':'H4 second new DOOR output received6 but model_valid=false and original verdict UNKNOWN(MODEL_DOMAIN), with cam_pressure_angle_exceeded. This scientific-domain UNKNOWN is unrelated to billing UNKNOWN. Do not promote it to a service PASS or physical failure.',
 'limitations':'Original constructed-model saved-fact replay; no simulator rerun, independent full-physics certification, hardware proof or global method claim.',
 'storage':{'available_bytes':shutil.disk_usage(A).free,'new_backups_environments_worktrees':0}}
save(A/'FINAL-READBACK.json',summary)
lines=['# 执行贯通续包：原服务保存结果独立读回','',
'14次实际候选评价按原引用去重为6个结果；4个LC结果和2个DOOR结果的原独立评估逐项重放一致。输入、原科学源、结果哈希、完整Task/Design/步长/上下文组成的精确缓存键核对通过。此次保存证据一致性PASS，不等于服务全PASS。','',
'|范围|评价次数|本包新增完整输入|精确复用|原服务结果|','|---|---:|---:|---:|---|']
for k,v in category_counts.items():lines.append(f"|{k}|{v['evaluations']}|{v['new_full_inputs']}|{v['exact_reuses']}|{v['service_verdicts']}|")
lines += ['',
'H4两个新增DOOR结果：第一个模型有效，6/6事件在2s内正确接收，最大延迟0.722333s，完整PASS。第二个虽接收6条、原事件匹配也在2s内，但cam_pressure_angle_exceeded使model_valid=false，原服务是UNKNOWN(MODEL_DOMAIN)，不能记PASS；它与计费UNKNOWN不同。原评估保留这一科学域未知，不能从它推断已证实的物理失败。两者能量闭合均在原容差内，闭合也不能解除模型域限制。','',
'LC四个唯一结果全部FAIL：训练BOLD条件接收455/405，续评LC接收422/380；首接收分别68002.029/70034.029/69329.029/71038.029s。四者整个12h暗期均无采样、恢复前无采集，且各有31个新样超出10s期限。冷启动、连续采样、暗期采样、新样期限四门均FAIL。已存在记录的时间/温度门正确，以及空旧记录集合导致历史期限门为True，不能补回缺失覆盖或作为恢复改善。','',
'LC保存CRC、队列/最终内存、时钟、付费阶段/能量账本、IV检查点和温度解析重建全部与原assessment相同；DOOR原外部事件/CRC/期限/次序/重复/力/能量闭合重放与原assessment相同。完整逐项事实、残差、域错误和原文件绑定见FINAL-READBACK.json。','',
'本包0工程、0初态；2新增完整输入，12次精确复用。出口核验新增科学/模型/实验廉价检查均0，另列6个唯一保存结果、7次保存事实review调用（首次读回包装器在首份LC重放一致后误取纯reviewer不提供的failures键，修正包装器后重复了这一份；没有科学重跑或原源修改）。H1 DOOR没有新候选，其原初态公共结果仍为PASS；实际合并历史消费及Update/Stop过程归S0/B审计。batch列四个无合格后代测试格未执行，本报告不替方法归因。']
with (A/'FINAL-READBACK.md').open('x') as f:f.write('\n'.join(lines)+'\n')
print(json.dumps({'status':summary['status'],'receipt':ref(A/'FINAL-READBACK.json'),'note':ref(A/'FINAL-READBACK.md'),
 'unique_results':6,'by_category':category_counts,'new_full_for_audit':0,'new_model':0},ensure_ascii=False))
