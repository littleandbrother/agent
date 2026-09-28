"""Bind local acceptance records without copying private conversations into docs."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

repo=Path(__file__).resolve().parents[2]
home=Path('/Users/depengsu/Documents/bf-agent-workbench')
verification=home/'verification'
evidence=verification/'trace-engineering-acceptance';evidence.mkdir(exist_ok=True)
logs={
    'full-init.log':'/tmp/bfa010-init-final.log',
    'trace-tests.log':'/tmp/bfa010-trace-final.log',
    'pi-root-lint.log':'/tmp/bfa010-pi-root-lint.log',
    'browser.log':'/tmp/bfa010-browser-final.log',
}
for name,source in logs.items():shutil.copyfile(source,evidence/name)
db=sqlite3.connect(home/'state/workbench.sqlite');db.row_factory=sqlite3.Row
before=json.loads((verification/'trace-engineering-before.json').read_text())
assert before['ledger']==[dict(r) for r in db.execute('SELECT * FROM model_requests')]
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before['traces'].items())
engines=[]
for row in db.execute('SELECT * FROM engineering_jobs WHERE owner="operator" ORDER BY created'):
    r=dict(row);request=json.loads(r['request']);result=json.loads(r['result'])
    assert r['status']=='SUCCEEDED'
    for artifact in result['artifacts']:
        path=home/'engineering'/r['id']/artifact['name']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==artifact['sha256']
    engines.append({'id':r['id'],'request':request,'result':result,'directory':str(home/'engineering'/r['id'])})
smoke=verification/'trace-engineering-smoke'
browser=json.loads((verification/'trace-engineering-browser/receipt.json').read_text())
assert browser['passed'] and browser['native_template_buttons_tested']
source_paths=[repo/'packages/python/bfworld/src/bfworld/agentlab'/p for p in ['engineering.py','trace_analysis.py','trace_review.py','server.py','organization.py','product.py','launcher.py','engineering_templates/blender_enclosure.py','engineering_templates/Cantilever.java']]
source_paths += [repo/'apps/agent-studio'/p for p in ['trace.js','engineering.js','trace.css','developer.js','product.js','index.html']]
source_paths += [Path('/Users/depengsu/Documents/pi-bf-aiot/packages/bf-agent/src')/p for p in ['chat-product.ts','chat-v2.ts']]
record={
    'schema_version':'bf-trace-engineering-delivery-v1','date':'2026-09-18','feature':'BFA-010-trace-engineering',
    'upstream':{'url':'https://github.com/minipopstyle/agent-workbench','fork':'https://github.com/littleandbrother/agent-workbench','commit':'7968c6073a5ba36a2561226cc2bf44f33ddab335','source_code_copied':False,'reason':'No project LICENSE at audited revision'},
    'verification':{'full_init':'PASS','python_tests':262,'trace_subset_tests':14,'pi_typescript':'PASS','pi_changed_entry_lint':'PASS','pi_full_check':'BLOCKED_BY_EXISTING_LINT_WARNINGS','logs':{n:{'path':str(evidence/n),'sha256':hashlib.sha256((evidence/n).read_bytes()).hexdigest()} for n in logs}},
    'browser':browser,'desktop_foreground_acceptance':'unavailable_while_Mac_locked',
    'preservation':{'trace_files_unchanged':len(before['traces']),'model_ledger_rows_unchanged':len(before['ledger']),'additional_paid_calls':0,'additional_model_cost_usd':0},
    'production_engineering_jobs':engines,
    'blender_independent_readback':json.loads((smoke/'blender-readback.json').read_text()),
    'comsol_independent_readback':{'path':str(smoke/'comsol-readback.log'),'sha256':hashlib.sha256((smoke/'comsol-readback.log').read_bytes()).hexdigest(),'mode':'native model load; -norun -nosave','passed':'100 %' in (smoke/'comsol-readback.log').read_text()},
    'smoke_job_receipt':str(smoke/'receipt.json'),
    'folder_configuration':json.loads((verification/'engineering-tool-enabled.json').read_text()),
    'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
    'limitations':['Typed local CLI templates only; no Pi engineering MCP server registered.','CAD deferred. No manufacturing, hardware or general multiphysics qualification.','Trace comparison does not establish causal Harness improvement.','Historical missing tool timestamps are not reconstructed.','No automatic restart or retry of interrupted engineering jobs.'],
    'committed':False,'development_changes_pushed':False,
}
(repo/'docs/agentlab/TRACE-ENGINEERING.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'receipt':'docs/agentlab/TRACE-ENGINEERING.json','engines':len(engines),'preservation':record['preservation']}))
