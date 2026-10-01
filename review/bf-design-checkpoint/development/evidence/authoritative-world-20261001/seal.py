"""One-way software-evidence seal, limited to this newly owned directory."""
import datetime, json, pathlib, re, sys
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from authoritative_world import file_hash, read_json, write_json, verify_sources, load_world, world_id, task_id
if (ROOT/'FREEZE-RECEIPT.json').exists():raise SystemExit('Already frozen: no overwrite; use a new version directory.')
errors=verify_sources(check_originals=True)
if errors:raise SystemExit(str(errors))
log=(ROOT/'runs/tests.log').read_text()
match=re.search(r'Ran (\d+) tests in',log)
if not match or not log.rstrip().endswith('OK'):raise SystemExit('Tests did not pass; no seal.')
contracts={str(p.relative_to(ROOT)):file_hash(p) for p in sorted((ROOT/'contracts').glob('*.json'))}
files=[{'path':str(p.relative_to(ROOT)),'sha256':file_hash(p),'bytes':p.stat().st_size} for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in ('FILE-MANIFEST.json','FREEZE-RECEIPT.json')]
write_json(ROOT/'FILE-MANIFEST.json',{'schema':'bf-artifact-manifest-v1','files':files})
world=load_world();tasks=read_json(ROOT/'contracts/tasks-v2.json')['tasks']
receipt={'schema':'bf-authoritative-world-freeze-receipt-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'world_id':world_id(world), 'legacy_world_id':world_id(load_world(ROOT/'contracts/legacy-world-v1.json')),
 'computational_spec_frozen':True,'physical_qualified':False,'requirements_owner_frozen':False,'formal_trial_admitted':False,
 'tasks':[{'task_id':t['task_id'],'task_contract_id':task_id(t),'migration_status':t['migration']['status'],'admitted':False} for t in tasks],
 'source_registry_sha256':file_hash(ROOT/'contracts/source-registry.json'),'authority_registry_sha256':file_hash(ROOT/'contracts/authority-registry.json'),'artifact_manifest_sha256':file_hash(ROOT/'FILE-MANIFEST.json'),'contract_files':contracts,
 'test_result':{'executed':int(match[1]),'passed':int(match[1]),'failed':0,'log_sha256':file_hash(ROOT/'runs/tests.log'),'nested_coordinate_comparisons':72,'host_C_tests':5},
 'original_source_hashes_rechecked':True,'upstream_full_init_run':False,'full_application_health_claimed':False,
 'new_magnetic_world_dynamic_solves':0,'paid_calls':0,'commercial_tools':0,'commits_or_pushes':0,
 'blockers':[x['id'] for x in world['unresolved_facts']],
 'next_plan':{'path':'NEXT-REFERENCE-PLAN.json','sha256':file_hash(ROOT/'NEXT-REFERENCE-PLAN.json'),'status':'prospective_not_executed_requires_review'},
 'claim':'Frozen executable development specification and checked identities only; neither physical qualification nor formal task admission.'}
write_json(ROOT/'FREEZE-RECEIPT.json',receipt)
print(json.dumps(receipt,indent=2))
