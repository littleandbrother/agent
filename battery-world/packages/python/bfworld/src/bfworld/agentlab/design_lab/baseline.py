"""Read-only baseline inventory. No Workbench construction or recovery effects."""
import json
from pathlib import Path
import sqlite3
import subprocess
import time
from .contracts import sha, sealed
from ..store import identity

PINNED_D5_RESULT = 'f6375bc0f8757a06a26bc703cb4a9db3145432e32d15f17009be3b62fe7342bd'


def environment(reference):
    reference = Path(reference).resolve()
    result = json.loads((reference/'result.json').read_text())
    if sha(reference/'result.json') != PINNED_D5_RESULT:
        raise ValueError('REFERENCE_NOT_PINNED_D5')
    if not result['qualification']['nominal_prediction_eligible'] or not all(result['checks'].values()):
        raise ValueError('REFERENCE_NOT_QUALIFIED')
    files = {r['name']:r['sha256'] for r in result['artifacts']}
    # Verify the consumed waveform, exact inputs, numeric/rating evidence and CAD.
    for name, digest in files.items():
        if sha(reference/name) != digest:
            raise ValueError('REFERENCE_FILE_TAMPER:'+name)
    files['result.json'] = PINNED_D5_RESULT
    manifest = json.loads((reference/'system-manifest.json').read_text())
    # The final native RAW archives remain readable dependencies, not copied GBs.
    native = []
    for stage in ('joint', 'time-step'):
        item = next(v for v in manifest['native_archives'] if v['path']==stage+'/system.raw.archive.json')
        path = reference/stage/item['archive_name']
        if sha(path) != item['archive_sha256']:
            raise ValueError('REFERENCE_RAW_ARCHIVE_TAMPER')
        native.append({'path':str(path),'sha256':item['archive_sha256'],
                       'original_sha256':item['original_sha256'],'readback_verified':item['readback_verified']})
    value = {'schema_version':'bf-design-environment-v1','root':str(reference),
             'files':files,'native_dependencies':native,'design_id':result['design_id'],
             'legacy_executor_sha256':manifest['executor_sha256'],
             'qualification':result['qualification'],
             'supported':'Unchanged D5 physical model and exact stage-load witness; new event application compiled/executed as F0.',
             'unqualified':['arbitrary HEX execution','board/RF','changed load without native recoupling',
                            'ROM extrapolation','Cases A/B full execution'],
             'new_native_solver_calls':0}
    return {**value,'environment_id':'E-'+identity(value)}


def rows_receipt(dbpath, owners):
    db = sqlite3.connect(f'file:{Path(dbpath)}?mode=ro',uri=True)
    db.row_factory = sqlite3.Row
    try:
        all_rows = [dict(r) for r in db.execute('SELECT * FROM model_requests ORDER BY id')]
        rows = [r for r in all_rows if r['owner'] in owners]
        conversations = [dict(r) for r in db.execute('SELECT * FROM conversations ORDER BY id') if r['id'] in owners]
        active = [dict(r) for r in db.execute("SELECT id,owner,status FROM engineering_jobs WHERE status IN ('RUNNING','QUEUED')")]
        settings = {r['key']:json.loads(r['value']) for r in db.execute('SELECT key,value FROM settings')
                    if r['key'].startswith('model_profile:') or r['key']=='model_unbounded_policy'}
        return {'db_path':str(dbpath),'access':'mode=ro',
                'owners':conversations,'engineering_active':active,
                'ledger_rows_sha256':identity(rows),'ledger_row_hashes':{r['id']:identity(r) for r in rows},
                'unknown':{r['id']:{'row_sha256':identity(r),'reserved_usd':r['reserved']} for r in all_rows if r['status']=='UNKNOWN'},
                'counts':{k:sum(r['status']==k for r in rows) for k in ['SETTLED','UNKNOWN','NOT_SENT','DISPATCHED']},
                'registered_usd':sum(r['charged'] for r in rows if r['status']=='SETTLED'),
                'settings':settings}
    finally:db.close()


def capture(runtime, code, destination):
    runtime,code,destination = map(Path,(runtime,code,destination))
    index_path = runtime/'reference-cases/literature-rsi-20261008/campaign/parallel-20261009/pi-session-index.json'
    index = json.loads(index_path.read_text())
    # Preserve the real owner IDs; accept the existing index's paper mapping.
    raw = index.get('sessions', index.get('papers', []))
    owners = [x.get('owner') or x.get('session_id') or x.get('conversation_id') for x in raw]
    if len(owners)!=10 or any(not isinstance(x,str) or not x.startswith('pi-chat-') for x in owners):
        raise ValueError('TEN_ORIGINAL_OWNERS_REQUIRED')
    databases = [runtime/'workbench/state/workbench.sqlite',
                 runtime/'reference-cases/literature-rsi-20261008/campaign/parallel-20261009/workbench/state/workbench.sqlite']
    databases = [p for p in databases if p.is_file()]
    if len(databases)!=2:
        # The index supplies the operational paper-state layout in deployments.
        candidates=list((runtime/'reference-cases/literature-rsi-20261008').glob('**/state/workbench.sqlite'))
        databases=[runtime/'workbench/state/workbench.sqlite',*candidates]
        databases=list(dict.fromkeys(databases))
    ledgers = [rows_receipt(p,owners) for p in databases]
    if any(x['engineering_active'] for x in ledgers):
        raise ValueError('BASELINE_REQUIRES_DRAINED_SERVICES')
    env = environment(runtime/'reference-cases/door-selfpower-v1/full-bank3-46-c15-01')
    source_files={str(p.relative_to(code)):sha(p) for p in sorted(
        (code/'battery-world/packages/python/bfworld/src/bfworld/agentlab').rglob('*.py'))}
    value={'schema_version':'bf-refactor-baseline-v1','created':time.time(),
           'original_code':str(code),'git_head':subprocess.check_output(['git','-C',str(code),'rev-parse','HEAD'],text=True).strip(),
           'git_status':subprocess.check_output(['git','-C',str(code),'status','--porcelain','--untracked-files=no'],text=True),
           'source_files':source_files,'session_index':{'path':str(index_path),'sha256':sha(index_path)},
           'original_owners':owners,'ledgers':ledgers,'environment':env,
           'authorization':{'authorized_by':'direct-user','wall_seconds':None,'wall_text':'持续运行 不设置时间限制',
                            'cumulative_usd':None,'cumulative_tokens':None,'requests':None,
                            'fees_reset':False,'unknown_preserved':True,'usage_reconciliation':'deferred'},
           'claims':{'physical':False,'RSI':False,'ten_products_passed':False}}
    value['baseline_id']='R0-'+identity(value)
    sealed(destination/'baseline.json',value)
    sealed(destination/'environment.json',env)
    return value

