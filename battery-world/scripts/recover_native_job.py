"""Operator-only adoption of a preserved D5 subprocess after a service update.

Never launches/replays/kills a solver. A completed job requires the original
process identity, unchanged input, matching terminal stdout and result, and a
readable evidence ZIP. Missing evidence remains UNKNOWN, never success.
"""
import argparse
import hashlib
import json
import sqlite3
import subprocess
import time
import zipfile
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def process_identity(pid):
    p = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart=', '-o', 'args='],
                       capture_output=True, text=True, check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def completed_result(directory, checkpoint):
    if digest(directory/'input.json') != checkpoint['input_sha256']:
        raise ValueError('RECOVERY_INPUT_CHANGED')
    value = json.loads((directory/'result.json').read_text())
    # The pipeline prints exactly its returned result after packaging. File
    # existence alone is insufficient: result.json precedes ZIP finalization.
    with (directory/'process.log').open('rb') as f:
        f.seek(max(0, (directory/'process.log').stat().st_size-2*1024*1024))
        last = f.read().decode(errors='replace').splitlines()[-1]
    if json.loads(last) != value:
        raise ValueError('RECOVERY_TERMINAL_RESULT_MISMATCH')
    request = json.loads((directory/'input.json').read_text())
    if value['design_id'] != request['parameters']['candidate']['design_id']:
        raise ValueError('RECOVERY_DESIGN_MISMATCH')
    manifest=json.loads((directory/'system-manifest.json').read_text())
    if manifest['executor_sha256'] != request['template_sha256'] or manifest['design_id'] != value['design_id']:
        raise ValueError('RECOVERY_EXECUTOR_MISMATCH')
    if value.get('source_stable') is not True:
        raise ValueError('RECOVERY_SOURCE_NOT_STABLE')
    with zipfile.ZipFile(directory/'engineering-evidence.zip') as z:
        if z.testzip() is not None:
            raise ValueError('RECOVERY_ZIP_INVALID')
    return value


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--job', required=True)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--capture', action='store_true')
    args = p.parse_args()
    db = sqlite3.connect(args.runtime/'workbench/state/workbench.sqlite', timeout=30)
    db.row_factory = sqlite3.Row
    job = dict(db.execute('SELECT * FROM engineering_jobs WHERE id=?', (args.job,)).fetchone())
    request = json.loads(job['request'])
    if request['engine'] != 'door-selfpower':
        raise ValueError('RECOVERY_ENGINE_NOT_SUPPORTED')
    directory = args.runtime/'workbench/engineering'/args.job
    row = db.execute("SELECT data FROM engineering_events WHERE job_id=? AND kind='process_spawned' ORDER BY seq DESC LIMIT 1", (args.job,)).fetchone()
    pid = json.loads(row['data'])['pid']
    identity = process_identity(pid)
    if args.capture:
        if job['status'] != 'RUNNING' or not identity or str(directory) not in identity or 'bfworld.agentlab.door_selfpower.pipeline' not in identity:
            raise ValueError('RECOVERY_LIVE_IDENTITY_REQUIRED')
        record = {'job_id':args.job, 'owner':job['owner'], 'pid':pid,
                  'process_identity':identity, 'input_sha256':digest(directory/'input.json'),
                  'request_hash':job['request_hash'], 'captured':time.time(),
                  'deadline':job['started']+12000, 'operator_intervention':True}
        args.checkpoint.write_text(json.dumps(record, indent=2))
        print(json.dumps({'captured':True, 'job':args.job, 'pid':pid}), flush=True)
        return
    record = json.loads(args.checkpoint.read_text())
    if record['job_id'] != args.job or record['pid'] != pid or record['request_hash'] != job['request_hash'] or record['owner'] != job['owner']:
        raise ValueError('RECOVERY_CHECKPOINT_MISMATCH')
    if job['status'] not in ('UNKNOWN','RUNNING') or (identity is not None and identity != record['process_identity']):
        raise ValueError('RECOVERY_STATE_OR_PROCESS_CHANGED')
    def event(kind, data):
        db.execute('INSERT INTO engineering_events(owner,job_id,time,kind,data) VALUES(?,?,?,?,?)',
                   (job['owner'],args.job,time.time(),kind,json.dumps(data)))
    with db:
        db.execute("UPDATE engineering_jobs SET status='RUNNING',error=NULL WHERE id=?", (args.job,))
        event('native_process_adopted', {'pid':pid, 'checkpoint_sha256':digest(args.checkpoint), 'replayed':False})
    print(json.dumps({'adopted':args.job, 'pid':pid, 'replayed':False}), flush=True)
    try:
        while process_identity(pid) is not None:
            if process_identity(pid) != record['process_identity']:
                raise ValueError('RECOVERY_PID_REUSED')
            if time.time() > record['deadline']:
                raise ValueError('RECOVERY_DEADLINE_REQUIRES_OPERATOR_REVIEW')
            time.sleep(5)
        result = completed_result(directory, record)
        allowed = {'.json','.jsonl','.log','.csv','.tsv','.cir','.png','.blend','.glb','.mph','.py','.java','.epro-source','.epro2','.net','.zip','.step','.stl','.brep','.svg','.dsn','.ses','.c','.h','.ld','.elf','.hex','.bin','.raw','.map','.md','.pdf','.html'}
        artifacts = [{'name':f.name,'bytes':f.stat().st_size,'sha256':digest(f)} for f in sorted(directory.iterdir()) if f.is_file() and f.suffix in allowed]
        result.update(artifacts=artifacts,design_revision=request['design_revision'],input_hash=record['input_sha256'])
        status = 'SUCCEEDED' if result['run_status'] == 'completed' else 'FAILED'
        with db:
            db.execute('UPDATE engineering_jobs SET status=?,ended=?,result=?,error=NULL WHERE id=?', (status,time.time(),json.dumps(result),args.job))
            event('native_process_recovered', {'pid':pid,'terminal_result_verified':True,'process_exit_code':None,'replayed':False})
            event('job_completed', {'artifact_count':len(artifacts),'result':result})
        print(json.dumps({'job':args.job,'status':status,'qualification':result.get('qualification')}), flush=True)
    except Exception as exc:
        with db:
            db.execute("UPDATE engineering_jobs SET status='UNKNOWN',error=? WHERE id=?", (str(exc),args.job))
            event('native_recovery_needs_review', {'error':str(exc),'replayed':False})
        raise


if __name__ == '__main__':
    main()
