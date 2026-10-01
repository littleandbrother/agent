"""Independent packet/journal/registered-tool evidence readback; no dispatch."""
from pathlib import Path
import hashlib,json,sys,importlib.util
P=Path('/workspace/shared/controlled-magnetic-service-integration-20261001')
R=Path('/workspace/shared/next-stage-integration-review-20261001/service-review-v2')
W=Path('/workspace/shared/authoritative-world-20261001')
F=Path('/workspace/shared/controlled-launcher-integration-20261001')
run=P/'reports/probe-v3'
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(o):return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
packet=read(run/'EXECUTION-PACKET.json');result=read(run/'RESULT.json')
assert digest({k:v for k,v in packet.items() if k!='packet_id'})==packet['packet_id']
registry=read(W/'contracts/tasks-v2.json');task=next(t for t in registry['tasks'] if t['task_id']=='DEV-FEASIBLE-01')
assert packet['task_contract_hash']==digest({k:v for k,v in task.items() if k not in ['reference_witness','qualification','status']})
assert packet['task_registry_sha256']==sha(W/'contracts/tasks-v2.json')
assert packet['world_id']==registry['world_id']==task['world_id']
assert packet['world_input_id']==task['world']['input_id']
assert packet['approved_model'] is None and packet['approved_budget'] is None and packet['approval'] is None
profile=packet['runtime_profile'];assert profile['native_tools']=={} and profile['native_identity_status']=='absent_not_substituted'
assert profile['model']['provider']=='bf-offline-fixture' and profile['model']['model_id']=='offline-no-call-model'
assert profile['budget']['model_calls']==profile['budget']['solver_calls']==profile['budget']['money']==0
assert not packet['execution_authorized'] and not packet['model_dispatch_allowed'] and not packet['native_dispatch_allowed']
assert result['execution_packet_id']==packet['packet_id'] and result['pid']!=result['supervisor_pid']
assert sha(run/'process/stdout.jsonl')==result['stdout_sha256'] and sha(run/'process/stderr.log')==result['stderr_sha256']
events=[json.loads(x) for x in (run/'process/stdout.jsonl').read_text().splitlines()]
ctrl=[e for e in events if e.get('type')=='controlled_activation']
assert [(e['phase'],e['entrypoint']) for e in ctrl]==[('post_import','solver'),('post_import','improver'),('invoked','solver.initialState'),('invoked','solver.solverPrompt')]
manifest=next(e['source'] for e in events if e.get('type')=='harness_loaded')
assert digest({k:v for k,v in manifest.items() if k!='identity'})==manifest['identity']
assert manifest['model'] is None and manifest['session_caps'] is None and manifest['world'] is None
for e in ctrl:
 assert e['pid']==result['pid'] and e['mode']=='solve' and e['binding_hash']==digest(packet)
 assert e['app_build_hash']==manifest['app_build_hash'] and e['harness_source_hash']==manifest['source_hash']
 assert e['loaded']=={k:manifest['loaded_modules'][k] for k in ['solver','improver']}
 if e['phase']=='invoked':assert e['output_hash']==hashlib.sha256(json.dumps(e['output'],ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
assert len(set(e['nonce'] for e in ctrl))==1
runtime=[e for e in events if e.get('type')=='controlled_runtime_configuration'];assert len(runtime)==1
assert runtime[0]['model']==profile['model'] and runtime[0]['budget']==profile['budget']
bound=[e for e in events if e.get('type')=='controlled_task_bound'];assert len(bound)==1
assert bound[0]['binding']=={k:packet[k] for k in ['world_id','world_input_id','task_contract_hash','task_registry_sha256','evaluator_sha256']}
probes=[e for e in events if e.get('type')=='trusted_controller_probe'];assert len(probes)==1
probe=probes[0];assert probe['tool_name']=='bf_experiment' and probe['arguments']=={'operation_id':'trusted-controller-probe-1'}
assert probe['packet_id']==packet['packet_id'] and probe['autonomous_participant'] is False
job=json.loads(probe['result']['content'][0]['text']);assert job['status']=='BLOCKED' and job['result'] is None
assert job['request']['task_id']=='DEV-FEASIBLE-01' and job['execution_packet_id']==packet['packet_id']
assert job['native_tool_identities']=={} and job['native_prepare_error']=='TOOL_IDENTITY_MISSING_OR_INVALID:pmic_model'
assert job['model_calls']==job['native_solver_calls']==0 and job['scientific_success'] is False
complete=[e for e in events if e.get('type')=='session_complete'];assert len(complete)==1 and complete[0]['messages']==0 and complete[0]['submitted'] is False
assert not any(e.get('type') in ['message','model_dispatched'] for e in events)
rows=[json.loads(x) for x in (run/'service/events.jsonl').read_text().splitlines()];prev=None
for idx,row in enumerate(rows):
 assert row['index']==idx and row['previous_hash']==prev and row['run_id']==packet['service_identity']
 assert row['event_hash']=='sha256:'+digest({k:v for k,v in row.items() if k!='event_hash'});prev=row['event_hash']
assert result['service_journal_head']==prev
assert [r['type'] for r in rows]==['service_bound','budget_read','task_read','snapshot_intent','snapshot_complete','job_intent','job_blocked','budget_read']
for file,h in rows[0]['payload']['inputs'].items():assert sha(file)==h
assert digest({'inputs':rows[0]['payload']['inputs'],'adapter':sha(P/'src/service_adapter.py'),'server':sha(P/'src/server_overlay.py')})==packet['service_identity']
snap_id=job['snapshot_id'];snap_path=run/'service/snapshots'/snap_id/'receipt.json';snap=read(snap_path)
assert snap['uploaded_files']=={'candidate.json':'{}\n'}
assert digest(snap['uploaded_files'])==snap['file_hash']
assert digest({'owner':snap['owner'],'packet_id':packet['packet_id'],'files':snap['uploaded_files']})==snap_id
assert sha(snap_path)==next(r['payload']['receipt_sha256'] for r in rows if r['type']=='snapshot_complete')
# Read-only reuse of the independently pinned upstream normalizer, not producer adapter.
sys.path.insert(0,str(W/'src'));import authoritative_world as aw
assert aw.migrate_upstream_spec(json.loads(snap['uploaded_files']['candidate.json']),'upstream-338d603')==snap['candidate']
assert digest({k:v for k,v in snap['candidate'].items() if k!='presentation'})==snap['candidate_design_hash']
job_path=run/'service/jobs'/(job['id']+'.json');assert read(job_path)==job
assert sha(job_path)==next(r['payload']['receipt_sha256'] for r in rows if r['type']=='job_blocked')
assert digest(job['request'])==job['request_hash']
assert job['binding']==snap['binding']=={k:packet[k] for k in ['world_id','task_contract_hash','evaluator_sha256']}
first_manifest=read(F/'FILE-MANIFEST.json');assert all(sha(F/p)==x['sha256'] for p,x in first_manifest['files'].items())
originals=read(F/'INPUT-LOCK.json')['files'];assert all(sha(p)==h for p,h in originals.items())
out={'schema':'independent-magnetic-service-readback-v1','status':'pass_trusted_registered_tool_transport_and_identity_only','packet_id':packet['packet_id'],'task_id':packet['task_id'],'task_contract_hash':packet['task_contract_hash'],'world_id':packet['world_id'],'evaluator_sha256':packet['evaluator_sha256'],'journal_rows':len(rows),'journal_head':prev,'registered_tool':'bf_experiment','original_uploaded_bytes_retained':True,'normalized_candidate_reconstructed':True,'native_tools_absent':True,'native_error':job['native_prepare_error'],'job_status':job['status'],'first_layer_files_unchanged':len(first_manifest['files']),'original_files_unchanged':len(originals),'readback_started_processes':0,'model_calls':0,'native_solver_calls':0,'participant_execution_admitted':False,'producer_result_sha256':sha(run/'RESULT.json')}
(R/'outputs/INDEPENDENT-READBACK.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
