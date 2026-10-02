"""Shared read-only projection of actual studies, costs, jobs and submissions."""
import json
import re
import csv
import io
from pathlib import Path
from .simulation_chain.contracts import file_hash
from .runtime_config import HOME_ROOT
from .recovery import Recovery


def projection(store, owner=None):
    recovery=Recovery(store)
    with store.connect() as db:
        studies = [dict(r) for r in db.execute('SELECT protocol,created,expires,max_usd,model FROM research_model_studies ORDER BY created DESC')]
        trial_rows = [dict(r) for r in db.execute('''SELECT r.owner,r.protocol,r.trial,c.status,c.error,c.title
            FROM research_model_owners r JOIN conversations c ON c.id=r.owner ORDER BY c.created''')]
        if owner is not None:
            trial_rows = [r for r in trial_rows if r['owner'] == owner]
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='method_revisions'").fetchone()
        blockers=[dict(r) for r in db.execute("SELECT id,owner,reserved,error FROM model_requests WHERE status='UNKNOWN' AND id NOT IN (SELECT request_id FROM model_resolutions WHERE kind='NOT_SENT')")]
        if owner is not None:
            blockers = [r for r in blockers if r['owner'] == owner]
        for row in trial_rows:
            cid = row['owner']
            row['conservative_continuation']=bool(recovery.usage_continuation(db,owner=cid))
            usage = [dict(r) for r in db.execute('SELECT status,charged,reserved,usage FROM model_requests WHERE owner=?', (cid,))]
            row['model_calls'] = len(usage)
            row['cost_upper_usd'] = sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in usage)
            row['usage_settled'] = all(r['status']=='SETTLED' for r in usage)
            row['unknown_requests'] = sum(r['status']=='UNKNOWN' for r in usage)
            row['tokens'] = sum(json.loads(r['usage']).get('total_tokens', 0) for r in usage if r['usage'])
            row['jobs'] = []
            for job in db.execute('SELECT id,status,created,started,ended,request,result,error FROM engineering_jobs WHERE owner=? ORDER BY created', (cid,)):
                req = json.loads(job['request']); result = json.loads(job['result']) if job['result'] else {}
                row['jobs'].append({'id': job['id'], 'status': job['status'], 'created': job['created'],
                    'started': job['started'], 'ended': job['ended'], 'candidate': req.get('parameters', {}).get('candidate'),
                    'run_status': result.get('run_status'), 'metrics': result.get('metrics'),
                    'evaluation': result.get('task_evaluation'), 'stages': result.get('stages'),
                    'error': job['error'], 'solver_s': result.get('elapsed_s')})
            selected = db.execute('SELECT receipt FROM simulation_task_submissions WHERE owner=?', (cid,)).fetchone()
            row['submission'] = json.loads(selected['receipt']) if selected else None
            row['method_revisions'] = [json.loads(r[0]) for r in db.execute('SELECT receipt FROM method_revisions WHERE owner=? ORDER BY created', (cid,))] if exists else []
        for study in studies:
            study['conservative_continuation']=bool(recovery.usage_continuation(db,protocol=study['protocol']))
    if owner is not None:
        studies = [s for s in studies if s['protocol'] in {r['protocol'] for r in trial_rows}]
    for study in studies:
        study['initial_runs'] = []
        if not re.fullmatch(r'door-[A-Za-z0-9_-]+', study['protocol']):
            continue
        root = HOME_ROOT/'studies'/study['protocol']
        seal = root/'seal.json'
        if seal.exists():
            value = json.loads(seal.read_text())
            study['task_hash'] = value['task']['task_hash']
            study['method'] = value['protocol'].get('method')
            study['execution_blocker']='PROVIDER_USAGE_UNKNOWN_STOP' if blockers and not study['conservative_continuation'] else None
            index = root/'evidence-index.json'
            if index.exists():
                evidence = json.loads(index.read_text())
                study['evidence_assets'] = list(evidence['assets'])
            if owner is None:
                existing={r['trial'] for r in trial_rows if r['protocol']==study['protocol']}
                for trial in value['protocol'].get('pi_trials',[]):
                    if trial['id'] not in existing:
                        trial_rows.append({'owner':None,'protocol':study['protocol'],'trial':trial['id'],
                            'status':'NOT_STARTED','error':study['execution_blocker'],
                            'initial':trial['initial'],'model_calls':0,'cost_upper_usd':0,
                            'tokens':0,'jobs':[],'submission':None,'method_revisions':[],
                            'planned_only':True,'usage_settled':True})
            for path in sorted((root/'runs').glob('*/receipt.json')):
                receipt = json.loads(path.read_text())
                result = path.parent/'result.json'
                data = json.loads(result.read_text()) if result.exists() else {}
                study['initial_runs'].append({'id': path.parent.name, 'receipt': receipt,
                    'evaluation': data.get('task_evaluation'), 'metrics': data.get('metrics')})
    return {'schema_version': 'design-pilot-projection-v1', 'studies': studies, 'trials': trial_rows,
        'billing_blockers':blockers,
        'scope': '受限名义模型的真实 Pi 先导；失败、越界和未结束运行保留。不代表物理合格、架构综合或方法优越。'}


def export_projection(store, owner=None):
    """Export the same read model as Studio/Lab; no private transcript or secrets."""
    view = projection(store, owner)
    fields = ['protocol', 'trial', 'owner', 'planned_only', 'status', 'model_calls',
              'tokens', 'cost_upper_usd', 'usage_settled', 'job_id', 'job_status',
              'run_status', 'nominal_task_status', 'submitted', 'solver_s',
              'end_to_end_job_s', 'cache_hits', 'cold_stages']
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for trial in view['trials']:
        for job in trial['jobs'] or [None]:
            row = {k: trial.get(k) for k in fields if k in trial}
            row.update(planned_only=trial.get('planned_only', False), submitted=bool(trial['submission']))
            if job:
                stages = (job.get('stages') or {}).values()
                row.update(job_id=job['id'], job_status=job['status'], run_status=job.get('run_status'),
                           nominal_task_status=(job.get('evaluation') or {}).get('nominal_task_status'),
                           solver_s=job.get('solver_s'),
                           end_to_end_job_s=job['ended']-job['created'] if job['ended'] else None,
                           cache_hits=sum(bool(s.get('cache_hit')) for s in stages),
                           cold_stages=sum(not s.get('cache_hit') for s in stages))
            writer.writerow(row)
    return {'schema_version': 'design-pilot-export-v1', 'projection': view,
            'trials_csv': buf.getvalue(), 'cost_semantics': 'Conservative upper charge; UNKNOWN retains reservation.',
            'claim_boundary': view['scope']}


def evidence_file(protocol, name):
    """Only operator-registered, hash-bound portable files; never arbitrary record_file paths."""
    if not re.fullmatch(r'door-[A-Za-z0-9_-]+', protocol):
        raise ValueError('PILOT_EVIDENCE_PROTOCOL')
    index = HOME_ROOT/'studies'/protocol/'evidence-index.json'
    asset = json.loads(index.read_text())['assets'].get(name)
    if not asset:
        raise ValueError('PILOT_EVIDENCE_ASSET')
    rel = Path(asset['path'])
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('PILOT_EVIDENCE_PATH')
    path = HOME_ROOT/rel
    if path.is_symlink() or not path.resolve().is_relative_to((HOME_ROOT/'verification').resolve()):
        raise ValueError('PILOT_EVIDENCE_PATH')
    if path.suffix not in ('.png', '.svg', '.zip') or path.stat().st_size > 80_000_000:
        raise ValueError('PILOT_EVIDENCE_TYPE_SIZE')
    if file_hash(path) != asset['sha256']:
        raise ValueError('PILOT_EVIDENCE_HASH')
    return path
