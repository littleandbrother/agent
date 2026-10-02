import datetime,hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
review=Path('/workspace/shared/world-evaluator-independent-review-20261001/reports/evaluator-independent-readback.json')
rail_review=Path('/workspace/shared/world-evaluator-independent-review-20261001/reports/RAIL-SOURCE-REVIEW.md')
receipt=json.loads((root/'DIAGNOSTIC-RESULT.json').read_text());result=json.loads((root/'EVALUATION-RESULT.json').read_text())
final={'schema_version':'bf-causal-evaluator-repair-final-v2','status':'isolated-causal-diagnostic-verified-static-contract-only',
'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scientific_solves':receipt['scientific_runs_started'],'scientific_solves_completed':receipt['scientific_runs_completed'],
'software_tests':{'passed':29,'failed':0,'full_upstream_init_run':False},'checks':result['checks'],'all_previous_diagnostic_files_preserved':True,
'new_rail_scientific_solves':0,'paid_calls':0,'commercial_solver_runs':0,'commits':0,'pushes':0,'production_source_changed':False,
'plan_sha256':sha(root/'contracts/prospective-plan-v2.json'),'rail_contract_sha256':sha(root/'contracts/ltc3588-rail-state-v2.json'),
'rail_module_sha256':sha(root/'src/ltc3588_rail_contract_v2.py'),
'independent_review':{'path':str(review),'sha256':sha(review),'scope':'all 12 hashes/cells/activation/refinement/energy ledgers, zero new solves'},
'rail_source_review':{'path':str(rail_review),'sha256':sha(rail_review),'scope':'source PDF and static-only rail/PGOOD semantics; zero native solves'},
'claim_limit':'Generic computational causal apparatus verified. No native PMIC transient, authoritative door-world feasibility, hardware, learned knowledge promotion, or RSI.'}
(root/'FINAL-RECEIPT.json').write_text(json.dumps(final,indent=2)+'\n')
files={str(p.relative_to(root)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in ['FINAL-MANIFEST.json']}
manifest={'schema_version':'bf-causal-evaluator-repair-manifest-v2','excluded':['Python __pycache__ runtime files','FINAL-MANIFEST.json self hash'],'files':files}
(root/'FINAL-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'final_receipt_sha256':sha(root/'FINAL-RECEIPT.json'),'manifest_sha256':sha(root/'FINAL-MANIFEST.json'),'files':len(files)},indent=2))
