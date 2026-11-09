"""Read saved F1 artifacts only; no imports of experiment/runtime/solver code."""
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os
ROOT=Path('/Users/depengsu/Documents/Long-Horizon AI Agent')
BASE=ROOT/'docs/research/pqe-two-paper-plan-20261022/f1-conditional-learning'
A=BASE/'a';S=BASE/'s0'
SRC=ROOT/'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src/bfworld/agentlab/pqe20261022'
checks=[];bindings={}
def read(path):return json.loads(Path(path).read_text())
def ident(v,ascii=True):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False,ensure_ascii=ascii).encode()).hexdigest()
def bind(path):
 p=Path(path);b=p.read_bytes();r={'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)};bindings[str(p)]=r;return r

def check(condition,name):
 if not condition:raise AssertionError(name)
 checks.append(name)
def checked(ref):
 got=bind(ref['path']);check(got['sha256']==ref['sha256'] and ('bytes' not in ref or got['bytes']==ref['bytes']),'binding:'+str(ref['path']))
 return read(ref['path'])
def save(path,v):
 with Path(path).open('x') as h:json.dump(v,h,ensure_ascii=False,indent=2,allow_nan=False);h.write('\n')
stat=os.statvfs(ROOT);available_before=stat.f_bavail*stat.f_frsize
check(available_before>=10001000000,'review storage headroom')
protocol=read(BASE/'shared/protocol.json');batch=read(S/'batch-result.json');ledger=read(S/'resource-ledger.json')
manifest=checked(protocol['task_manifest']);qualification=checked(ledger['initial_ledger'])
check(batch['complete'] is True,'batch complete')
check(len(batch['rows'])==12,'twelve planned formation/solve entries')
check(manifest['status']=='TWO_ROLES_QUALIFIED','two preregistered qualified tasks')
for name,digest in protocol['apparatus_source'].items():check(bind(SRC/name)['sha256']==digest,'unchanged apparatus:'+name)
for name in ('pilot.py','restricted_worker.py','conditional_learning_methods.py'):
 p=SRC/name;check(bind(p)['sha256']==protocol['source_bindings'][str(p)],'unchanged direct source:'+name)
for name in ('TASK-RULES.json','TASK-FREEZE.json','TASK-MANIFEST.json'):
 p=A/name;check(bind(p)['sha256']==protocol['source_bindings'][str(p)],'unchanged task freeze:'+name)
parent=checked(protocol['public_bindings']['parent']);history=checked(protocol['public_bindings']['history']);h3=checked(protocol['public_bindings']['h3'])
new_ids=[e['task_id'] for e in manifest['tasks']]
for name,obj in [('history',history),('h3',h3)]:
 check(all(i not in json.dumps(obj) for i in new_ids),'new task identities absent from '+name)
formed=read(S/'formed-program-freeze.json');formations=[]
for ep in ('form-h2','form-h4'):
 d=S/'episodes'/ep;f=read(d/'formation.json');bind(d/'formation.json')
 check(f['parent_sha256']==ident(parent['program']),'formation exact parent '+ep)
 check(f['proposals']['no_update'] is True and not f['proposals']['programs'] and not f['proposals']['rejected'],'valid no-update '+ep)
 check(f['raw_proposal_count']==0 and not f['local_evaluations'] and not f['selected_candidate'],'no formed descendant '+ep)
 check(len(f['raw_proposals'])==1 and f['raw_proposals'][0]['payload']=={'status':'OK','patches':[]},'original empty patches '+ep)
 check(all(i not in json.dumps(f) for i in new_ids),'new tasks absent formation '+ep)
 check(f['selected_program']==parent['program'],'no parent substitution as child '+ep)
 check(formed['conditions'][f['condition']]['qualified_descendant'] is False,'formed freeze no child '+ep)
 checked(formed['conditions'][f['condition']]['program'])
 formations.append({'episode':ep,'condition':f['condition'],'original_raw_payload':f['raw_proposals'][0]['payload'],'selected_descendant':False,'parent_retained':f['parent_retained'],'formation':bind(d/'formation.json')})
check(len({read(S/'episodes'/ep/'formation.json')['common_history_sha256'] for ep in ('form-h2','form-h4')})==1,'same history both formations')
entries={e['role']:e for e in protocol['tasks']};catalog=checked(protocol['tasks'][0]['task'])
initials={};public_tasks={}
for role,e in entries.items():
 task=catalog[e['task_key']];packet=checked(e['public_input']);init=checked(e['initial_public_result']);checked(e['initial_full_result']);checked(e['initial_assessment'])
 check(ident(task)==e['task_canonical_sha256'] and ident(packet['task'])==e['public_task_canonical_sha256'],'task identities '+role)
 check(task['initial']=={'angle_deg':0,'capacitor_v':0,'event_counter':0,'logical_state':0,'mechanical_stored_j':0,'queue':[]},'original zero state '+role)
 check(init['model_valid'] is True and init['public_check']['verdict']=='FAIL','initial valid FAIL '+role)
 initials[role]=init;public_tasks[role]=packet
science_names=('door_model.py','door_program.py','engineering.py','executor.py','evaluator.py')
all_actions=[];cells=[];requests=[];episode_costs=[];transcripts={};raw_seen={}
for row in batch['rows']:
 ep=row['episode']
 if row['status']=='NOT_EXECUTED_NO_QUALIFIED_DESCENDANT':
  check(row['condition'] in ('H2','H4') and row['candidate_evaluations']==row['provider_requests']==0,'skipped child '+ep)
  cells.append({'episode':ep,'role':row['role'],'condition':row['condition'],'status':'NOT_EXECUTED_NO_QUALIFIED_DESCENDANT','repair_service':None,'repair_design_actions':0,'new_full_inputs':0,'cache_reuses':0})
  continue
 d=S/'episodes'/ep;cost=read(d/'provider-costs.json');bind(d/'provider-costs.json')
 check(cost['requests']==len(cost['rows'])==row['accounting']['requests'],'episode request count '+ep)
 check(not cost['unknown_or_missing_usage'] and cost['unsettled_reserved_usd']==0,'settled accounting '+ep)
 for req in cost['rows']:
  usage=json.loads(req['usage']) if isinstance(req['usage'],str) else req['usage']
  check(req['status']=='SETTLED' and usage is not None,'request settled '+req['id'])
  requests.append({'episode':ep,'id':req['id'],'charged_usd':req['charged'],'input_tokens':usage['prompt_tokens'],'output_tokens':usage['completion_tokens']})
 episode_costs.append({'episode':ep,'requests':cost['requests'],'rate_estimate_usd':cost['cache_aware_rate_estimate_usd']})
 if row['role']=='formation':continue
 role=row['role'];entry=entries[role];task=catalog[entry['task_key']]
 tr=read(d/'method-transcript.json');transcripts[ep]=tr;bind(d/'method-transcript.json');iu=read(d/'initial-update.json');bind(d/'initial-update.json')
 check(tr['initial_state']['task']==public_tasks[role]['task'],'same public task '+ep)
 check(tr['initial_state']['design']==public_tasks[role]['initial_design'] and tr['initial_state']['problem']==public_tasks[role]['initial_problem'],'independent initial state '+ep)
 check(tr['initial_update']['status']=='UPDATED' and tr['initial_update']['parent_design_preserved'] and not tr['initial_update']['submitted_candidate'] and not tr['initial_update']['new_tool_or_numerical_execution'],'initial real Update '+ep)
 check(tr['initial_update']['result_sha256']==initials[role]['result_sha256'],'initial Update result binding '+ep)
 check(iu['initial_update']==tr['initial_update'],'separately saved initial Update '+ep)
 check(tr['initial_update']['site_calls'][0]['site']=='H-UPDATE','initial Update precedes Generate '+ep)
 if row['condition']=='H3':check(tr['initial_update']['site_calls'][0]['loaded'] and tr['initial_update']['site_calls'][0]['triggered'] and tr['initial_update']['site_calls'][0]['isolated'],'H3 actual isolated initial Update '+ep)
 index=read(d/'public-objects/index.json')
 def expand(value):
  if isinstance(value,dict):
   if set(value)=={'audit_public_object','sha256'}:
    ref=index['objects'][value['audit_public_object']];obj=read(ref['path'])
    check(hashlib.sha256(json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()==ref['sha256']==value['sha256'],'audit object binding '+value['audit_public_object'])
    return obj
   return {k:expand(v) for k,v in value.items()}
  if isinstance(value,list):return [expand(v) for v in value]
  return value
 actions=[]
 for ordinal,step in enumerate(tr['steps'],1):
  folder=d/'actions'/f'{ordinal:02d}';rb=read(folder/'readback.json');bind(folder/'readback.json')
  public=checked(rb['public_result']);raw=checked(rb['raw']);assessment=checked(rb['assessment']);decision=step['select']
  check(ident(decision)==step['decision_sha256_before_execution']==rb['decision_sha256'],'independent submitted decision '+ep+str(ordinal))
  check(step['state_before']['task']==public_tasks[role]['task'],'task unchanged before action '+ep+str(ordinal))
  design={**deepcopy(step['state_before']['design']),**deepcopy(decision['actual_input'].get('design_patch',{}))}
  check(design==public['design']==raw['design'],'actual design is submitted patch '+ep+str(ordinal))
  check(public['task_sha256']==raw['task_sha256']==entry['task_canonical_sha256'],'action full Task binding '+ep+str(ordinal))
  check(ident(design)==public['input_sha256']==raw['design_sha256']==rb['design_sha256'],'action design identity '+ep+str(ordinal))
  check(public['sources']==protocol['apparatus_source'],'action source binding '+ep+str(ordinal))
  check(ident({k:v for k,v in raw.items() if k!='result_sha256'})==raw['result_sha256']==public['result_sha256'],'original raw result identity '+ep+str(ordinal))
  for field in ('trace','activity','records','packets','energy','program_state'):check(public['facts'][field]==raw[field],'full public/raw '+ep+str(ordinal)+':'+field)
  check(public['facts']['receiver_records']==assessment['receiver_records'],'original receiver '+ep+str(ordinal))
  check(public['public_check']['verdict']==assessment['verdict'] and public['model_valid']==raw['model_valid']==rb['model_valid'],'original validity/verdict '+ep+str(ordinal))
  check(public['execution_status']==raw['execution_status']=='COMPLETE','complete original execution '+ep+str(ordinal))
  check(len(assessment['truth'])==6 and len(assessment['matches'])==rb['timely_matches'],'original timely matching '+ep+str(ordinal))
  cnt=dict(Counter(x['action'] for x in raw['activity']));check(cnt==rb['activity_counts'],'activity counts '+ep+str(ordinal))
  key=ident({'task':task,'design':design,'dt':raw['dt_s'],'scientific_source':{k:public['sources'][k] for k in science_names}})
  check(key==rb['cache_key'],'exact cache key '+ep+str(ordinal))
  audit_result=expand(step['result']);check(audit_result==public,'transcript complete result link '+ep+str(ordinal))
  original_pass=(raw['model_valid'] and not raw['domain_errors'] and assessment['verdict']=='PASS' and len(assessment['matches'])==6 and not assessment['failures'] and not assessment['unknown'])
  if original_pass:
   check(cnt.get('save_commit')==cnt.get('ack_commit')==6 and len(raw['remaining_queue'])==0,'PASS SAVE/ACK/queue '+ep+str(ordinal))
   check([x['seq'] for x in raw['records']]==[1,2,3,4,5,6],'PASS six independent IDs '+ep+str(ordinal))
   check(abs(assessment['mechanical_residual_j'])<=assessment['energy_tolerance_j'] and abs(assessment['storage_residual_j'])<=assessment['energy_tolerance_j'],'PASS energy '+ep+str(ordinal))
   check(raw['peak_handle_force_n']<=task['service']['handle_force_max_n'],'PASS force '+ep+str(ordinal))
  reuse_source=None
  if rb['reused']:
   reuse=read(folder/'reuse.json');source=checked(reuse['source_public_result']);reuse_source=reuse['source_public_result']
   check(reuse['key']==key and reuse['same_task_design_dt_scientific_source'],'reuse exact identity flag '+ep+str(ordinal))
   check(source['design']==design and source['task_sha256']==public['task_sha256'] and source['result_sha256']==public['result_sha256'] and source['facts']==public['facts'],'cached original facts '+ep+str(ordinal))
   check(rb['full_dynamic_inputs']==0 and public['usage']['numerical_inputs']==0,'cached cost zero new full '+ep+str(ordinal))
  else:
   check(rb['full_dynamic_inputs']==1 and public['usage']['numerical_inputs']==1,'new full counted '+ep+str(ordinal))
   before=read(folder/'decision.json');check(before['decision']==decision and before['actual_design']==design and before['phase']=='BEFORE_EXECUTION','saved pre-execution decision '+ep+str(ordinal))
  action={'episode':ep,'ordinal':ordinal,'operation':decision['actual_input']['operation'],'selected_id':decision['selected_id'],'design_patch':decision['actual_input'].get('design_patch',{}),'actual_design':design,'model_valid':raw['model_valid'],'domain_errors':raw['domain_errors'],'verdict':assessment['verdict'],'timely_count':len(assessment['matches']),'received_count':len(assessment['receiver_records']),'saved_count':len(raw['records']),'tx_count':cnt.get('tx_begin',0),'ack_count':cnt.get('ack_commit',0),'remaining_queue':len(raw['remaining_queue']),'minimum_tx_terminal_v':raw['minimum_tx_terminal_v'],'peak_handle_force_n':raw['peak_handle_force_n'],'original_full_service_pass':bool(original_pass),'reused':rb['reused'],'new_full_inputs':rb['full_dynamic_inputs'],'wall_s':rb.get('wall_s',0),'decision_sha256':rb['decision_sha256'],'cache_key':key,'readback':bind(folder/'readback.json'),'raw':rb['raw'],'assessment':rb['assessment'],'public_result':rb['public_result'],'cache_source':reuse_source}
  actions.append(action);all_actions.append(action);raw_seen[rb['raw']['path']]=rb['raw']
 check(len(actions)==row['candidate_evaluations'],'charged evaluated action count '+ep)
 check(sum(x['new_full_inputs'] for x in actions)==row['new_full_dynamic_inputs'],'new full per episode '+ep)
 edits=[x for x in actions if x['operation']=='edit']
 status='VALID_REPAIR_PASS' if any(x['original_full_service_pass'] for x in edits) else ('OBSERVE_ONLY_HOOK_ERROR_NO_REPAIR_SUBMISSION' if tr['termination']['reason']=='HOOK_ERROR' and not edits else 'MODEL_DOMAIN_UNKNOWN_NO_VALID_REPAIR')
 if not edits:check(all(x['reused'] and x['actual_design']==public_tasks[role]['initial_design'] for x in actions),'observe-only unchanged initial '+ep)
 check(all(not st['scope_effect']['active_variables_removed'] and not st['scope_effect']['candidate_scope_changed'] for st in tr['steps']),'no unsupported scope exclusion '+ep)
 cells.append({'episode':ep,'role':role,'condition':row['condition'],'status':status,'repair_service':6 if status=='VALID_REPAIR_PASS' else None,'repair_design_actions':len(edits),'evaluated_observe_actions':len(actions)-len(edits),'new_full_inputs':sum(x['new_full_inputs']for x in actions),'cache_reuses':sum(x['reused']for x in actions),'original_termination':tr['termination'],'original_service_origin_label':row['service_origin'],'classification_note':'H3 LAST_CANDIDATE points only to observed initial FAIL; no repair science failure is inferred.' if not edits else None,'transcript':bind(d/'method-transcript.json')})
check(len(cells)==10,'ten solve cells classified')
check(sum(x['new_full_inputs']for x in all_actions)+qualification['new_full_dynamic_inputs']==ledger['full_dynamic_inputs']==6,'six full including qualifications')
check(sum(x['reused']for x in all_actions)==ledger['cache_reuses']==7,'seven exact cache reuses')
check(len(all_actions)==ledger['candidate_evaluations']==11,'eleven evaluated actions')
check(sum(x['operation']=='observe'for x in all_actions)==6 and sum(x['operation']=='edit'for x in all_actions)==5,'six observations and five edit submissions')
check(abs(sum(x['wall_s']for x in all_actions)+qualification['wall_s']-ledger['full_dynamic_wall_s'])<1e-8,'full wall ledger readback')
check(ledger['cheap_calls']==0,'zero cheap relations')
check(len(requests)==len({r['id']for r in requests})==25,'twenty five distinct settled requests')
rate_estimate=sum(x['rate_estimate_usd']for x in episode_costs)
check(abs(rate_estimate-.3513135)<1e-10,'total rate estimate')
check(protocol['provider_before']['historical_unknown_sha256']==batch['provider_after']['historical_unknown_sha256'],'historical UNKNOWN preserved')
check(batch['provider_after']['total']-protocol['provider_before']['total']==25 and batch['provider_after']['inflight']==0,'provider batch delta')
h1_t2=transcripts['t2-h1'];h0_t2=read(S/'episodes/t2-h0/actions/01/public-result.json')
check(all(h0_t2['result_sha256'] not in json.dumps(record.get('request',{})) for record in h1_t2['callback_records']),'other-group successful result absent before independent H1 submission')
check(h1_t2['steps'][1]['select']['actual_input']['design_patch']=={'persistent_queue':True},'H1 independently submitted retention edit')
hook=read(S/'hook-error-readback.json');hook_binding=bind(S/'hook-error-readback.json')
check(hook['read_only_no_model_or_hook_execution'] and len(hook['rows'])==2,'S0 H3 readback is non-executing')
for h in hook['rows']:
 check(h['exact_match'] and h['recorded_context_sha256']==h['reconstructed_context_sha256'],'S0 exact-context binding '+h['episode'])
 check(h['encoded_frame_bytes']=={'t1-h3':2461796,'t2-h3':2124991}[h['episode']] and h['original_frame_limit']==2000000 and not h['new_execution'],'S0 original frame guard evidence '+h['episode'])
check(all(not x['qualified_descendant']for x in formed['conditions'].values()),'no automatic descendant eligible for adoption')
review={'schema':'f1-A-final-independent-review-v1','package':batch['package'],'status':'A_REVIEW_COMPLETE_RETAIN_PARENT_NO_AUTOMATIC_DESCENDANT','at_utc':datetime.now(timezone.utc).isoformat(),'manifest':protocol['task_manifest'],'batch':bind(S/'batch-result.json'),'ledger':bind(S/'resource-ledger.json'),'protocol':bind(BASE/'shared/protocol.json'),'formations':formations,'cells':sorted(cells,key=lambda x:x['episode']),'actions':all_actions,'adoption':{'decision':'RETAIN_FIXED_PARENT','reason':'Both automatic formations validly returned no-update; no qualified automatic descendant entered either task. H1 same-history parent attained valid original full service on both tasks.','learning_gain':'NOT_ESTABLISHED_NO_DESCENDANT','H3':'Tool-censored observation-only episodes; no repair submission or scientific repair failure.','H0_T1':'Two invalid-model designs with diagnostic six deliveries are UNKNOWN, not valid PASS.'},'audit':{'checks_passed':len(checks),'current_sources_verified':['six apparatus files','pilot.py','restricted_worker.py','conditional_learning_methods.py'],'task_rules_and_inputs_unchanged':True,'initial_update_actual':True,'exact_cache_submission_bindings':True,'new_tasks_absent_frozen_history_h3_and_formation':True,'H3_frame_limit_S0_readback':hook_binding,'H3_root_cause':'Both original contexts exactly reconstructed by S0 and rejected by the frozen 2000000-byte guard. A read this evidence without rebuilding or rerunning either hook; original exception text was not retained.','source_field_note':'Audit public-object references resolve through their saved index, including original external paths.'},'resources':{'original_qualification_inputs_A':2,'new_full_inputs_solve':4,'new_full_inputs_total':6,'full_wall_s':ledger['full_dynamic_wall_s'],'cached_actions':7,'charged_evaluated_actions':11,'observe_actions':6,'design_edit_submissions':5,'distinct_new_solve_scientific_inputs':4,'provider_requests_SETTLED':25,'rate_estimate_usd':rate_estimate,'invoice_amount_known':False,'input_tokens':sum(x['input_tokens']for x in requests),'output_tokens':sum(x['output_tokens']for x in requests),'new_cheap_calls':0,'new_billing_UNKNOWN':0,'audit_new_full_or_model_or_cheap_calls':0},'episode_costs':episode_costs,'limits':['One bounded prospective package, with four descendant cells unexecuted; no effect-size claim about learning efficacy.','H1 versus H0 is one realized two-task comparison, not causal isolation or statistical superiority.','No H3 engineering inferiority conclusion from original hook censoring.','Original nominal simulation does not establish hardware, population reliability, transfer or RSI.'],'next_handoff':'S0 final closure under original finite protocol; no repair, reformation, extra candidate or numerical rerun.'}
save(A/'FINAL-REVIEW.json',review)
md='F1 A独立复核完成：保留固定父方法。H2/H4均有效返回空补丁，无合格自动后代；四个后代求解格未执行。本包未建立自动学习增益。\n\n| 条件 | 题一：冷启动 | 题二：历史保持 |\n|---|---|---|\n| H0 | 两个域外设计，诊断接收6/6，判定UNKNOWN | 仅开启persistent_queue，合法PASS6/6 |\n| H1 | 合法PASS6/6 | 独立提交相同保持编辑，精确缓存复用PASS6/6 |\n| H2 / H4 | 无合格后代，未执行 | 无合格后代，未执行 |\n| H3 | 两次初态观察后HOOK_ERROR，无修复设计 | 两次初态观察后HOOK_ERROR，无修复设计 |\n\n冻结任务、初态与科学源绑定保持一致。六个实际求解格均经过初态Update。原raw/public/assessment、提交决定、实际Design及缓存键读回通过；11个已评行动为6次观察和5次编辑，编辑对应4个新数值输入及1次精确复用。公共对象哈希按原键顺序验证，科学身份哈希继续按原排序算法验证。\n\n题一H0的两项域外原因分别为assembly_envelope_exceeded和cam_pressure_angle_exceeded，诊断6/6不构成合法PASS。三处合法PASS均由原完整服务结果支持，其中题二H1复用题二H0的同Task、Design、dt及科学源结果。\n\nS0的hook-error-readback.json记录两项原context SHA均精确匹配；题一帧2,461,796B、题二帧2,124,991B，均超过原2,000,000B限制。A只读核对该记录，没有再次重建或运行hook。原异常正文未保留；定位依据是精确上下文和原确定性门。两项HOOK_ERROR不作为工程失败。\n\n全包25个SETTLED请求，费率估算USD0.3513135；6个完整数值输入含原2项资格，账本时间26.59855017s；7次复用、0cheap、0新增billing UNKNOWN，原历史UNKNOWN保留。本次审计新增科学输入和模型调用均为0。结果仅覆盖本次有限名义仿真，不支持统计优势或硬件验收结论。\n\n详细绑定见FINAL-REVIEW.json，交接及存储回执见FINAL-RECEIPT.json。交由S0收口，不追加形成、候选、hook或数值运行。\n'
(A/'FINAL-REVIEW.md').write_text(md)
stat=os.statvfs(ROOT);available_after=stat.f_bavail*stat.f_frsize
retained=sum(p.stat().st_size for p in A.rglob('*') if p.is_file())
check(retained<7800000 and available_after>=10001000000,'final storage gate')
receipt={'schema':'f1-A-final-receipt-v1','package':batch['package'],'status':review['status'],'at_utc':datetime.now(timezone.utc).isoformat(),'owner':'campaign-a','review':bind(A/'FINAL-REVIEW.json'),'readable_review':bind(A/'FINAL-REVIEW.md'),'verification_script':bind(Path(__file__)),'task_manifest':protocol['task_manifest'],'batch':bind(S/'batch-result.json'),'resource_ledger':bind(S/'resource-ledger.json'),'protocol':bind(BASE/'shared/protocol.json'),'checks_passed':len(checks),'classifications':{x['episode']:x['status']for x in cells},'adoption':review['adoption'],'resources':review['resources'],'storage':{'available_before_bytes':available_before,'available_after_bytes':available_after,'estimated_review_peak_additional_bytes':1000000,'A_retained_bytes_before_receipt':retained,'A_retained_cap_bytes':8000000,'new_backups_environments_worktrees':0,'deleted_old_content_bytes':0,'reclaimed_bytes':0},'audit_boundary':'All experiment sources/results read only; new artifacts only A FINAL-REVIEW.json/md, FINAL-RECEIPT.json and readback_final.py. No solver, hook, model, predictor or evaluator was invoked.','next':'S0 root closure/unique completion; no commit/push or extra experiment.'}
save(A/'FINAL-RECEIPT.json',receipt)
check(read(A/'FINAL-REVIEW.json')==review,'full content report readback')
check(read(A/'FINAL-RECEIPT.json')==receipt,'full content receipt readback')
print(json.dumps({'status':review['status'],'checks':len(checks),'review':bind(A/'FINAL-REVIEW.md'),'receipt':bind(A/'FINAL-RECEIPT.json'),'resources':review['resources'],'available_bytes':available_after},ensure_ascii=False))
