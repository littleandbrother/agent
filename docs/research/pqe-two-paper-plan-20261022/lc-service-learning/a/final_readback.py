"""Single independent readback of saved LC evidence; no producer imports/calls."""
from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,importlib.util,json,shutil
A=Path(__file__).resolve().parent
B=A.parent
ROOT=A.parents[4]
REVIEW=A.parents[1]/'stage3-e2main/a/readback_lcpv.py'
EXPECTED='27fae669a3ae199660116b1e7a5d228067ae0b551d53f378e51a11b13c91ecea'

def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();data=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
def checked(r):
 actual=ref(r['path']);assert all(actual[k]==v for k,v in r.items()),('REFERENCE_CHANGED',r['path'])
 return read(r['path'])
def identity(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def save(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
assert ref(REVIEW)['sha256']==EXPECTED
allowed={'bisect','binascii','hashlib','json','math','struct'}
for node in ast.walk(ast.parse(REVIEW.read_text())):
 if isinstance(node,ast.Import):assert all(n.name in allowed for n in node.names)
 if isinstance(node,ast.ImportFrom):assert node.level==0 and node.module in allowed
spec=importlib.util.spec_from_file_location('lc_final_stdlib_readback',REVIEW)
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
ledger_ref=ref(B/'s0/resource-ledger.json');ledger=checked(ledger_ref)
batch_ref=ref(B/'s0/batch-result.json');batch=checked(batch_ref);assert batch['complete'] is True
protocol_ref=ref(B/'shared/protocol.json');protocol=checked(protocol_ref)
freeze_ref=ref(A/'host/TASK-FREEZE.json');freeze=checked(freeze_ref)
assert ref(protocol['isolated_freeze']['path'])['sha256']==protocol['isolated_freeze']['sha256']
lc=next(e for e in freeze['entries'] if e['world']=='LC-PV')
public_task=checked(lc['context']['public']);host_task=checked(lc['context']['host_task']);driver_task=checked(lc['task'])
scientific=protocol['apparatus_source']['lc']
assert scientific==read(A/'ENGINEERING-FREEZE.json')['scientific_identity']
source_refs=[]
for path,digest in scientific.items():
 r=ref(path);assert r['sha256']==digest,('SOURCE_CHANGED',path);source_refs.append(r)
rows=[r for r in ledger['attempts'] if r['category']=='t2-h1']
assert len(rows)==4 and sum(r['new_full_dynamic_inputs'] for r in rows)==2
unique={};row_results=[]

def review_unique(folder,expected_design,label,declared_refs):
 folder=Path(folder)
 for r in declared_refs.values():checked(r)
 files={name:ref(folder/name) for name in ('input.json','raw.json','assessment.json','public-result.json','decision.json')}
 inp,raw,assessment,pub,decision=[read(files[name]['path']) for name in files]
 assert inp['Task']==host_task and inp['Profile']==public_task['Profile']
 assert pub['design']==expected_design==decision['actual_design']
 assert inp['Design']=={k:expected_design[k] for k in public_task['design_fields']}
 assert inp['Program']=={**public_task['Task']['fixed_program_semantics'],**{k:expected_design[k] for k in public_task['program_fields']}}
 assert identity(inp)==raw['input_sha256']==assessment['input_sha256']==decision['consumer_input_sha256']
 assert raw['result_sha256']==pub['result_sha256']==assessment['raw_result_sha256']
 assert identity(driver_task)==decision['task_sha256']==pub['task_sha256']
 assert all(scientific.get(k)==v for k,v in raw['sources'].items())
 assert decision['sources']==scientific
 assert pub['sources']==scientific
 assert assessment['evaluation_source']['sha256']==EXPECTED
 # This is the unchanged standalone stdlib reviewer; no simulator or host import.
 computed=checker.review(inp,raw)
 assert all(assessment[k]==v for k,v in computed.items()),('ASSESSMENT_DIFFERENCE',label)
 failures=sorted(k.upper() for k,v in computed['gates'].items() if not v)
 assert failures==assessment['failures']==pub['public_check']['failures']
 assert computed['verdict']==pub['public_check']['verdict']
 assert pub['model_valid'] is True and not pub['domain_errors']
 dark_start,dark_end=host_task['service']['dark_interval_s']
 diagnostics={'first_boot_s':raw['first_boot_s'],
  'dark_sample_count':sum(dark_start<=s['time_s']<=dark_end for s in raw['samples']),
  'samples_before_recovery':sum(s['time_s']<host_task['service']['recovery_at_s'] for s in raw['samples']),
  'pending_at_end':raw['final_state']['pending'],
  'final_storage_energy_j':raw['final_state']['energy_j'],
  'no_old_history_is_not_recovery_repair':computed['facts']['pending_old_at_recovery']==0}
 result={'label':label,'files':files,'actual_design':expected_design,'assessment_identical':True,
  'input_task_profile_program_bound_to_isolated_freeze':True,'consumer_sources_bound':True,
  'verdict':computed['verdict'],'gates':computed['gates'],'facts':computed['facts'],
  'independent_checks':computed['independent_checks'],'diagnostics':diagnostics,
  'result_sha256':raw['result_sha256']}
 unique[str(folder)]=result
 return result

initial_folder=Path(lc['initial']['raw.json']['path']).parent
initial=review_unique(initial_folder,lc['initial_design'],'isolated-initial',lc['initial'])
current=dict(lc['initial_design']);problem=lc['initial_problem'].copy()
for i,row in enumerate(rows,1):
 actual=row['decision']['actual_input'];assert actual['operation']=='edit'
 current={**current,**actual.get('design_patch',{})};problem={**problem,**actual.get('problem_patch',{})}
 expected_key=identity({'task':driver_task,'design':current,
  'dt_s':actual.get('dt_s',driver_task['integration']['dt_s']),
  'consumer':scientific,'lc_inputs':{'public':public_task,'host_task':host_task}})
 assert row['cache_key']==expected_key,('CACHE_KEY_DIFFERENCE',i)
 declared={k:row[k] for k in ('raw','assessment','public_result')}
 for r in declared.values():checked(r)
 folder=Path(row['raw']['path']).parent
 if str(folder) not in unique:
  assert row['reused'] is False
  result=review_unique(folder,current,row['decision']['selected_id'],declared)
 else:
  assert row['reused'] is True and row['new_full_dynamic_inputs']==0
  result=unique[str(folder)];assert result['actual_design']==current
  reuse_path=B/f's0/episodes/t2-h1/solve/actions/{i:02d}/reuse.json'
  reuse=read(reuse_path);checked(reuse['original'])
  assert reuse['original']==row['public_result'] and reuse['cache_key']==expected_key
  assert reuse['current_problem']==problem
 assert row['public_check']==read(row['public_result']['path'])['public_check']
 assert row['model_valid'] is True
 record={'evaluation_number':i,'selected_id':row['decision']['selected_id'],'exact_cache_key_recomputed':expected_key,
  'reused':row['reused'],'new_full_dynamic_inputs':row['new_full_dynamic_inputs'],
  'result_sha256':result['result_sha256'],'canonical_files':result['files'],
  'verdict':result['verdict'],'service_result_equal_to_original':True}
 if row['reused']:record['reuse_receipt']=ref(reuse_path)
 row_results.append(record)
assert len(unique)==3
# Do not alter the root ledger; reference its snapshot and separate audit counts.
summary={'package':ledger['package'],'at_utc':datetime.now(timezone.utc).isoformat(),
 'status':'PASS_INDEPENDENT_SAVED_LC_READBACK','evaluator':ref(REVIEW),'readback_program':ref(__file__),
 'scope':'Only original isolated LC initial plus t2-h1 saved scientific inputs/results. No engineering rerun, formation audit, method causal attribution or source edit.',
 'inputs':{'resource_ledger_at_readback':ledger_ref,'batch_result_at_readback':batch_ref,'protocol':protocol_ref,'isolated_task_freeze':freeze_ref},
 'source_refs_verified':source_refs,'unique_saved_results_reviewed':3,'candidate_evaluations':4,
 'new_unique_candidate_results':2,'exact_reused_candidate_evaluations':2,
 'original_initial_reviewed_once':True,'rows':row_results,'unique_results':list(unique.values()),
 'counts':{'new_full_dynamic_inputs':0,'new_model_calls':0,'new_experimental_cheap_checks':0,
  'saved_result_review_calls':3,'engineering_runs':0},
 'service_outcome':'Initial and both distinct parent candidates remain full-service FAIL. Both distinct candidates have zero dark samples and no pre-recovery acquisitions; their old-history gate is vacuously satisfied, not a recovery repair.',
 'limitations':'Exact stored-fact/algebra/service replay within the unchanged constructed model. No new physical qualification, full-domain theorem, independent generator validation or automated-method benefit claim.',
 'storage':{'free_bytes':shutil.disk_usage(A).free,'no_backups_new_environments_worktrees':True}}
save(A/'FINAL-READBACK.json',summary)
lines=['# 最终LC保存结果独立读回','',
'原stdlib独立评估对隔离初态和两个实际不同候选的保存轨迹重放，服务、CRC、队列、时钟、付费阶段、能量闭合、受载IV和温度重建均与原assessment逐项一致；输入、结果和源哈希绑定通过。4次候选评价为2次新增计算加2次精确复用，复用键按冻结Task/Design/步长/源/LC上下文重新计算相同。','',
'|保存结果|首接收s|最大采样间隔s|暗期采样数|最大暗期间隔s|接收数|旧历史逾期|新样逾期|全服务|',
'|---|---:|---:|---:|---:|---:|---:|---:|---|']
for r in unique.values():
 f=r['facts'];d=r['diagnostics']
 lines.append(f"|{r['label']}|{f['first_receive_s']:.3f}|{f['maximum_sampling_gap_s']:.3f}|{d['dark_sample_count']}|{f['maximum_dark_sampling_gap_s']:.3f}|{f['unique_accepted_samples']}|{f['old_history_late_or_missing']}|{f['fresh_late_or_missing']}|{r['verdict']}|")
lines += ['',
'两个候选的首接收分别为69329.029s和71038.029s，均违反1800s冷启动；从连续采样服务起点至首次采样分别缺67529.025s和69238.025s，整个25200–68400s暗期无采样。两个候选没有恢复前采集的记录，故“旧历史无逾期”不是恢复成功；全部已生成记录的时间有效、温度准确、零brownout和最终清空队列也不能替代全天覆盖。两候选新样各31条超过实际采集起算的10s期限。','',
'三份保存结果的独立重放覆盖能量、时钟和记录语义；详细账本、逐门事实、残差及文件引用见FINAL-READBACK.json。没有调用生产者、科学求解器或模型，没有修改冻结源；工程八格未重跑。本次只核验实际消费者结果，不审查形成器或解释方法失败原因。']
with (A/'FINAL-READBACK.md').open('x') as f:f.write('\n'.join(lines)+'\n')
print(json.dumps({'status':summary['status'],'receipt':ref(A/'FINAL-READBACK.json'),'note':ref(A/'FINAL-READBACK.md'),
 'unique_results':3,'candidate_evaluations':4,'new_full':0,'model_calls':0,'experimental_cheap_checks':0},ensure_ascii=False))
