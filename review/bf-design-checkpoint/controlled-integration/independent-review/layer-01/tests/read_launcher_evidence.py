"""Independent read-only hash-chain and real Pi activation evidence audit."""
from pathlib import Path
import hashlib,json
R=Path('/workspace/shared/next-stage-integration-review-20261001')
P=Path('/workspace/shared/controlled-launcher-integration-20261001')
def path(p):
 p=Path(p);return p if p.is_absolute() else P/p
def sha(p):return hashlib.sha256(path(p).read_bytes()).hexdigest()
def digest(o):return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
lock=json.load(open(P/'INPUT-LOCK.json'))
assert all(sha(path)==h for path,h in lock['files'].items())
results=[]
for ver in ['v1','v2']:
 root=P/'reports'/('retained-controls-'+ver);rows=[json.loads(s) for s in (root/'events.jsonl').read_text().splitlines()]
 prev=None;attempts={};pid=[];nonces=[];process_checks=[]
 for idx,row in enumerate(rows):
  assert row['index']==idx and row['previous_hash']==prev
  body={k:v for k,v in row.items() if k!='event_hash'}
  assert row['event_hash']=='sha256:'+digest(body);prev=row['event_hash']
  if idx==0:
   assert row['type']=='assigned';contract=row['payload'];assert row['run_id']==digest(contract)
  assert row['run_id']==digest(contract)
  p=row['payload']
  if row['type']=='attempt_reserved':
   assert p['attempt_id'] not in attempts and p['episode_id'] in contract['assignments']
   assert p['request_hash']==digest(p['request']);attempts[p['attempt_id']]={**p,'status':'unknown'}
  elif row['type']=='attempt_finished':
   a=attempts[p['attempt_id']];assert a['status']=='unknown'
   file=root/p['receipt_file'];assert sha(file)==p['receipt_sha256'];rec=json.load(open(file))
   assert rec['episode_id']==a['episode_id'] and rec['attempt_id']==p['attempt_id'] and rec['request_hash']==a['request_hash']
   assert rec['binding']==contract['binding'];assert rec['status']==p['status']
   assert rec['scientific_success'] is False and rec['provider_calls']==0 and rec['participant_calls']==0
   a['status']=p['status'];d=rec['details']
   if d.get('process_started'):
    assert sha(d['trace_file'])==d['trace_sha256'] and sha(d['stderr_file'])==d['stderr_sha256']
    ev=[json.loads(s) for s in path(d['trace_file']).read_text().splitlines() if s.startswith('{')]
    ex=d['expected'];ac=[e for e in ev if e.get('type')=='controlled_activation'];imports=[];calls=[]
    assert ex['binding_hash']==digest(contract['binding'])
    for e in ac:
     for key in ['pid','nonce','harness_source_hash','app_build_hash','loaded','binding_hash','mode']:assert e[key]==ex[key]
     if e['phase']=='post_import':imports.append(e['entrypoint'])
     elif e['phase']=='invoked':
      assert e['entrypoint'].split('.')[0] in imports
      assert e['output_hash']==hashlib.sha256(json.dumps(e['output'],ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
      calls.append(e['entrypoint'])
    required=['solver.initialState','solver.solverPrompt' if ex['mode']=='solve' else 'improver.improvementPrompt']
    good=d['exit_code']==0 and imports==['solver','improver'] and calls==required and len([e for e in ev if e.get('type')=='session_complete'])==1
    assert good==d['activation_passed'] and good==(rec['status']=='activation_pass')
    assert d['model_prompt_called'] is False and d['provider_calls']==0 and d['participant_isolation_qualified'] is False
    assert not any(e.get('type')=='message' and e.get('message',{}).get('role')=='assistant' for e in ev)
    assert all(x=={'method':'GET','path':'/api/budget'} for x in d['service_requests'])
    manifest=json.load(open(Path(d['harness_path'])/'manifest.json'))
    assert sha(Path(d['harness_path'])/'manifest.json')==d['manifest_sha256']
    assert manifest['source_hash']==ex['harness_source_hash'];assert manifest['app_build_hash']==ex['app_build_hash']
    assert digest({k:v for k,v in manifest.items() if k!='identity'})==manifest['identity']
    texts={name:(Path(d['harness_path'])/name).read_text() for name in manifest['source_files']}
    assert digest(texts)==manifest['source_hash']
    for name,h in manifest['source_files'].items():assert sha(Path(d['harness_path'])/name)==h
    for name,h in ex['loaded'].items():assert sha(Path(d['harness_path'])/'dist'/(name+'.js'))==h
    pid.append(ex['pid']);nonces.append(ex['nonce'])
    process_checks.append({'attempt_id':rec['attempt_id'],'pid':ex['pid'],'status':rec['status'],'imports':imports,'calls':calls,'output_hashes_verified':True,'exit_code':d['exit_code'],'service_requests':d['service_requests']})
 assert len(nonces)==len(set(nonces)) and len(pid)==len(set(pid))
 final=json.load(open(root/'RESULT.json'));assert final['all_attempt_ledger']['journal_head']==prev
 assert final['all_attempt_ledger']['attempt_count']==len(attempts)
 assert final['all_attempt_ledger']['assigned_episode_count']==len(contract['assignments'])
 assert len(attempts)==11 and len(contract['assignments'])==11
 assert any(x['episode_id']=='never-started' and x['statuses']==['not_started'] for x in final['all_attempt_ledger']['episodes'])
 assert attempts['failed-import-a2']['status']=='budget_exhausted'
 assert final['launch_blocked'] and final['qualified_tasks']==0
 results.append({'version':ver,'status':'historical_rejected_run' if ver=='v1' else 'accepted_trusted_offline_control_run','journal_rows':len(rows),'journal_head':prev,'assigned_episodes':len(contract['assignments']),'attempt_count':len(attempts),'statuses':{k:v['status'] for k,v in attempts.items()},'actual_processes':process_checks,'not_started_assignments_retained':True})
out={'schema':'bf-independent-pi-evidence-readback-v1','input_files_rehashed':len(lock['files']),'input_lock_sha256':sha(P/'INPUT-LOCK.json'),'runs':results,'legacy_relative_path_resolution':'Historical v1 receipt paths resolved relative to original producer package, matching its recorded CLI context; no producer receipt changed','reviewer_started_processes':0,'provider_calls':0,'participant_calls':0,'scientific_success':False,'scope':'Readback of fixed trusted dry-run Pi processes only; no participant isolation/authorship or hidden evaluator qualification'}
(R/'outputs/LAUNCHER-JOURNAL-ACTIVATION-READBACK.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'input_files':len(lock['files']),'retained_runs':2,'attempts_per_run':[x['attempt_count'] for x in results],'processes_per_run':[len(x['actual_processes']) for x in results],'passed':True},indent=2))
