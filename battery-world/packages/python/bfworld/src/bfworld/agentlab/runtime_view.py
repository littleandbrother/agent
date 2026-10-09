"""Public, owner-scoped run projection. Reads facts and never dispatches work."""
import json
from .store import identity
from .native_outcome import summarize

DOMAINS = ('mechanical', 'circuit', 'pcb', 'power', 'firmware')


def domain(engine=None, argv=None, request=None):
    command = (argv or [None])[0]
    if command in ('pcb', 'board'):
        return 'pcb'
    if command in ('sch', 'bom', 'lib'):
        return 'circuit'
    if engine in ('blender', 'comsol', 'product-model'):
        return 'mechanical'
    if engine in ('mcu-firmware', 'tinyml-nas'):
        return 'firmware'
    if engine == 'engineering-project':
        request=request or {}
        kind = str(request.get('project',{}).get('manifest',{}).get('kind') or request.get('parameters', {}).get('kind', ''))
        return 'firmware' if 'firmware' in kind else 'mechanical' if kind in ('cad','cadquery','blender','comsol') else 'power' if kind=='ngspice' else None
    if engine in ('event-transient', 'beam-event', 'closed-simulation', 'door-system', 'door-selfpower'):
        return 'power'
    return None


def eda_outcome(app, job):
    result = job.get('result') or {}
    if result.get('outcome'):
        return result['outcome']
    # Older rows contain truncated stdout. Read only the server-owned full receipt.
    path = app.store.root.parent / 'eda-cli' / (job['id'] + '.json')
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
        return None
    try:
        receipt = json.loads(path.read_text())
        if (receipt.get('owner') != job['owner'] or receipt.get('job_id') != job['id']
                or identity(receipt) != result.get('receipt_sha256')):
            return None
        return summarize(receipt)
    except (OSError, ValueError):
        return None


def snapshot(app, owner):
    app.conversations.get(owner)
    with app.store.connect() as db:
        db.execute('BEGIN')
        conversation = dict(db.execute('SELECT id,status,error,harness FROM conversations WHERE id=?', (owner,)).fetchone())
        cursor = db.execute('SELECT COALESCE(MAX(seq),0) FROM chat_events WHERE conversation=?', (owner,)).fetchone()[0]
        calls = []
        if conversation['status'] in ('RUNNING', 'QUEUED', 'STARTING'):
            # Recover only open calls in this turn, without loading historical traces.
            boundary = db.execute("""SELECT COALESCE(MAX(seq),0) FROM chat_events WHERE conversation=? AND
                (json_extract(data,'$.type') IN ('chat_idle','session_complete','turn_stopped','turn_complete') OR
                 (json_extract(data,'$.type')='conversation_status' AND
                  json_extract(data,'$.status') NOT IN ('RUNNING','QUEUED','STARTING')))""", (owner,)).fetchone()[0]
            for row in db.execute("""SELECT s.data FROM chat_events s WHERE s.conversation=? AND s.seq>? AND
                json_extract(s.data,'$.type')='tool_execution_start' AND NOT EXISTS
                (SELECT 1 FROM chat_events e WHERE e.conversation=s.conversation AND e.seq>s.seq AND
                 json_extract(e.data,'$.type')='tool_execution_end' AND
                 json_extract(e.data,'$.toolCallId')=json_extract(s.data,'$.toolCallId'))
                ORDER BY s.seq DESC LIMIT 64""", (owner,boundary)):
                event = json.loads(row['data'])
                calls.append({k:event.get(k) for k in ('toolCallId','toolName','args')})
        rows = [dict(r) for r in db.execute("""SELECT * FROM eda_cli_jobs WHERE owner=? AND
            (status IN ('RUNNING','QUEUED','UNKNOWN') OR id IN (SELECT id FROM eda_cli_jobs WHERE owner=? ORDER BY created DESC LIMIT 30)
             OR id IN (SELECT id FROM eda_cli_jobs WHERE owner=? GROUP BY json_extract(request,'$.argv[0]') HAVING created=MAX(created))
             OR id IN (SELECT id FROM eda_cli_jobs WHERE owner=? AND json_extract(request,'$.argv[1]') IN ('drc','check','bridge-check','module-check')
                 GROUP BY json_extract(request,'$.argv[0]'),json_extract(request,'$.argv[1]') HAVING created=MAX(created))) ORDER BY created DESC""", (owner,owner,owner,owner))]
        engineering = [dict(r) for r in db.execute("SELECT * FROM engineering_jobs WHERE owner=? AND (status IN ('RUNNING','QUEUED','UNKNOWN') OR id IN (SELECT id FROM engineering_jobs WHERE owner=? ORDER BY created DESC LIMIT 30)) ORDER BY created DESC", (owner,owner))]
    jobs = []
    for row in rows:
        row['request'] = json.loads(row['request'])
        row['result'] = json.loads(row['result']) if row['result'] else None
        argv = row['request'].get('argv', [])
        jobs.append({'id': row['id'], 'domain': domain(argv=argv), 'status': row['status'],
                     'created': row['created'], 'ended': row['ended'], 'operation': row['operation'],
                     'label': ' '.join(argv[:2]), 'outcome': eda_outcome(app, row)})
    for row in engineering:
        request = json.loads(row['request'])
        jobs.append({'id': row['id'], 'domain': domain(request.get('engine'), request=request),
                     'status': row['status'], 'created': row['created'], 'ended': row['ended'],
                     'operation': row['operation'], 'label': request.get('engine', 'engineering'), 'outcome': None})
    value = {'schema_version': 'bf-runtime-view-v1', 'owner': owner, 'cursor': cursor,
             'conversation': conversation, 'jobs': sorted(jobs, key=lambda j: j['created']), 'tool_calls': calls,
             'actor': 'Pi', 'domains': list(DOMAINS), 'hardware_verified': False,
             'resources': app.skills.catalog(owner) if hasattr(app,'skills') else None,
             'scope': 'Execution and explicit native checks; no inferred product acceptance.'}
    value['sha256'] = identity(value)
    return value
