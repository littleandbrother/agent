"""Scoped Pi delegation on the existing repository/controller and operation journal.

Assignments bind immutable inputs. Workers return evidence and proposed files;
the lead keeps the only current-candidate write authority.
"""
import hashlib
import json

from ..store import canonical, identity
from .repository import name, file_hash
from .repository_task_actions import file_inputs
from .repository_task_standards import check_files, path_allowed

ARMS = {
    'single': {'allowed': [], 'required': [], 'max_workers': 0},
    'temporary': {'allowed': ['source'], 'required': [], 'max_workers': 1},
    'fixed': {'allowed': ['power', 'firmware'], 'required': ['power', 'firmware'], 'max_workers': 2},
    'joint': {'allowed': ['source', 'joint'], 'required': [], 'max_workers': 2},
}
READS = ('repository_work_task', 'repository_work_read', 'repository_work_result',
         'repository_work_policy', 'repository_work_request_guard', 'repository_state', 'repository_task_schema',
         'repository_task_definition', 'repository_task_result')


def install(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS design_work_policies(id TEXT PRIMARY KEY,project TEXT UNIQUE NOT NULL,value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS design_scoped_tasks(id TEXT PRIMARY KEY,project TEXT NOT NULL,
        owner TEXT UNIQUE NOT NULL,status TEXT NOT NULL,value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS design_scoped_results(id TEXT PRIMARY KEY,project TEXT NOT NULL,
        owner TEXT NOT NULL,task TEXT,value TEXT NOT NULL);
    ''')


def task(repo, owner, db=None):
    if db is None:
        with repo.store.connect() as con: return task(repo, owner, con)
    row = db.execute('SELECT value,status FROM design_scoped_tasks WHERE owner=?', (owner,)).fetchone()
    return {**json.loads(row['value']), 'status': row['status']} if row else None


def tasks(repo, pid, db):
    return [{**json.loads(r['value']), 'status': r['status']} for r in db.execute(
        'SELECT value,status FROM design_scoped_tasks WHERE project=? ORDER BY rowid', (pid,))]


def policy(repo, pid, db=None):
    if db is None:
        with repo.store.connect() as con: return policy(repo, pid, con)
    row = db.execute('SELECT value FROM design_work_policies WHERE project=?', (pid,)).fetchone()
    return json.loads(row['value']) if row else None


def counts(repo, pid, db=None):
    if db is None:
        with repo.store.connect() as con: return counts(repo, pid, con)
    p = repo.project(pid, db=db)
    owners = [p['owner']] + [t['owner'] for t in tasks(repo, pid, db)]
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='model_requests'").fetchone()
    calls = sum(db.execute('SELECT count(*) FROM model_requests WHERE owner=?', (o,)).fetchone()[0] for o in owners) if exists else 0
    return {'model_calls': calls, 'workers': len(owners)-1,
            'candidate_evaluations': db.execute('SELECT count(*) FROM design_task_executions WHERE project=?', (pid,)).fetchone()[0]}


def public_policy(repo, owner, pid):
    value = policy(repo, pid)
    if value is None: return {'policy': None}
    return {'policy': value, 'counts': counts(repo, pid), 'task': task(repo, owner),
            'protocol': 'work_assign(kind,base_system,question,completion,rationale); work_run(task_owner) waits; '
                        'work_result(task_owner) returns the evidence/proposal; work_apply(result_id,base_system,expected_revision,rationale) '
                        'merges a checked proposal. work_read(path,system_id?) reads candidate sources or task-definition.json. '
                        'Workers work_submit(content JSON). Source-study lead work_answer(content JSON). '
                        'Result: {completed_scope,files:{path:UTF8},facts:[{field,value,unit,conditions,sources:[{path,sha256,locator}]}],'
                        'judgment,assumptions:[],issues:[]}. locator is JSON pointer or Lstart-Lend. '
                        'All changes need operation_id; work_request_guard stops at the fixed shared request limit.'}


def configure(repo, owner, body, operator):
    if not operator: raise PermissionError('WORK_POLICY_OPERATOR_ONLY')
    p = repo.leader(body['project_id'], owner)
    raw = body['policy']; arm = raw['organization']
    if arm not in ARMS: raise ValueError('WORK_ORGANIZATION_UNKNOWN')
    if raw.get('kind') not in ('design', 'source'): raise ValueError('WORK_KIND_UNKNOWN')
    limits = raw['limits']
    for key in ('candidate_evaluations_per_trial', 'requests_per_trial'):
        if type(limits.get(key)) is not int or not 1 <= limits[key] <= 100: raise ValueError('WORK_LIMIT_INVALID')
    if not isinstance(raw.get('protocol_sha256'), str) or len(raw['protocol_sha256']) != 64:
        raise ValueError('WORK_PROTOCOL_HASH_REQUIRED')
    def apply(db):
        if policy(repo, p['id'], db): raise ValueError('WORK_POLICY_ALREADY_FROZEN')
        if counts(repo, p['id'], db)['model_calls']: raise ValueError('WORK_POLICY_REQUIRES_FRESH_OWNER')
        value = {'schema_version': 'bf-work-policy-v1', 'project_id': p['id'], **raw,
                 **ARMS[arm], 'worker_depth': 1, 'worker_submissions': 1}
        if raw['kind']=='source' and arm=='temporary': value['required']=['source']
        value['id'] = 'WP-' + identity(value)
        db.execute('INSERT INTO design_work_policies VALUES(?,?,?)', (value['id'], p['id'], canonical(value)))
        return value
    return repo.mutate(owner, body, apply)


def guard(repo, owner, body, operator=False):
    """Guard precedes all generic repository handlers, including task mutations."""
    t = task(repo, owner)
    action = body['action']
    if t:
        if action not in (*READS, 'repository_work_submit'): raise PermissionError('SCOPED_WORKER_ACTION_DENIED')
        if body.get('system_id', t['base_system']) != t['base_system']: raise PermissionError('SCOPED_WORKER_BASE_CONFLICT')
        if body.get('task_owner', owner) != owner: raise PermissionError('SCOPED_WORKER_PEER_DENIED')
    cfg = policy(repo, body['project_id'])
    if not cfg or operator: return
    if action in ('repository_decide', 'repository_work_answer'):
        with repo.store.connect() as db:
            rows = tasks(repo, body['project_id'], db)
        submitted = {r['kind'] for r in rows if r['status'] == 'SUBMITTED'}
        if not set(cfg['required']) <= submitted: raise ValueError('REQUIRED_SCOPED_WORK_NOT_SUBMITTED')
    if action == 'repository_task_execute':
        from .repository_task_execution import current_execution
        system = repo.system(body['project_id'], body['system_id'])
        if counts(repo, body['project_id'])['candidate_evaluations'] >= cfg['limits']['candidate_evaluations_per_trial']:
            with repo.store.connect() as db: old = current_execution(repo, system, db)
            if not old: raise ValueError('FINITE_CANDIDATE_LIST_EXHAUSTED')


def document(repo, pid, sid, path):
    system = repo.system(pid, sid)
    if path == 'task-definition.json': text = canonical(system['task_definition'])
    else:
        ref = system['files'].get(name(path))
        if not ref: raise ValueError('WORK_SOURCE_NOT_IN_BASE')
        src = repo.root/'blobs'/ref['sha256']
        if file_hash(src) != ref['sha256']: raise ValueError('WORK_SOURCE_CHANGED')
        text = src.read_text()
    return text, hashlib.sha256(text.encode()).hexdigest()


def read(repo, owner, body):
    p = repo.project(body['project_id'], owner)
    t = task(repo, owner)
    sid = t['base_system'] if t else body.get('system_id') or p['submitted']
    text, digest = document(repo, p['id'], sid, body['path'])
    offset, limit = body.get('offset', 0), body.get('limit', 12000)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 24000: raise ValueError('WORK_READ_RANGE')
    return {'system_id': sid, 'path': body['path'], 'sha256': digest, 'content': text[offset:offset+limit],
            'offset': offset, 'total_chars': len(text), 'next_offset': offset+limit if offset+limit < len(text) else None}


def validate_result(repo, pid, sid, raw, kind, db):
    if isinstance(raw, str): raw = json.loads(raw)
    expected = {'completed_scope', 'files', 'facts', 'judgment', 'assumptions', 'issues'}
    if not isinstance(raw, dict) or set(raw) != expected: raise ValueError('WORK_RESULT_FIELDS')
    if not all(isinstance(raw[k], str) and raw[k].strip() for k in ('completed_scope', 'judgment')): raise ValueError('WORK_RESULT_TEXT')
    if not isinstance(raw['facts'], list) or not raw['facts'] or len(raw['facts']) > 40: raise ValueError('WORK_FACTS_REQUIRED')
    for fact in raw['facts']:
        if set(fact) != {'field','value','unit','conditions','sources'}: raise ValueError('WORK_FACT_FIELDS')
        if not fact['field'] or not isinstance(fact['unit'], str) or not isinstance(fact['conditions'], str) or not fact['sources']:
            raise ValueError('WORK_FACT_CONTEXT_REQUIRED')
        for source in fact['sources']:
            text, digest = document(repo, pid, sid, source['path'])
            if source['sha256'] != digest: raise ValueError('WORK_SOURCE_HASH_CONFLICT')
            loc = source['locator']
            if loc.startswith('/'):
                value = json.loads(text)
                try:
                    for bit in loc[1:].split('/'):
                        bit = bit.replace('~1', '/').replace('~0', '~')
                        value = value[int(bit)] if isinstance(value, list) else value[bit]
                except (KeyError, IndexError, ValueError, TypeError) as error: raise ValueError('WORK_SOURCE_POINTER') from error
            elif loc.startswith('L'):
                import re
                match = re.fullmatch(r'L([1-9][0-9]*)(?:-L([1-9][0-9]*))?', loc)
                if not match or not int(match[1]) <= int(match[2] or match[1]) <= len(text.splitlines()):
                    raise ValueError('WORK_SOURCE_LINES')
            else: raise ValueError('WORK_SOURCE_LOCATOR')
    if not all(isinstance(raw[k], list) and all(isinstance(x, str) for x in raw[k]) for k in ('assumptions','issues')):
        raise ValueError('WORK_UNRESOLVED_FORMAT')
    if not isinstance(raw['files'], dict): raise ValueError('WORK_FILES_FORMAT')
    if kind == 'source' and raw['files']: raise PermissionError('SOURCE_WORKER_READ_ONLY')
    allowed = {'power': ('design.json', 'notes/'), 'firmware': ('firmware/main.c', 'notes/'),
               'joint': ('design.json','firmware/main.c','notes/'), 'source': ()}[kind]
    for path in raw['files']:
        if not path_allowed(name(path), allowed): raise PermissionError('SCOPED_PROPOSAL_PATH')
    system = repo.system(pid, sid, db)
    refs = {**system['files'], **file_inputs(repo, db, raw['files'])}
    previous = json.loads(document(repo, pid, sid, 'design.json')[0]) if 'design.json' in system['files'] else None
    check_files(system['task_definition'], refs,
        lambda path: (repo.root/'blobs'/refs[path]['sha256']).read_text(), previous, raw['files'])
    return raw


def assign(repo, owner, body, operator):
    p = repo.leader(body['project_id'], owner); cfg = policy(repo, p['id'])
    if not cfg or body['kind'] not in cfg['allowed']: raise PermissionError('WORK_KIND_NOT_ALLOWED')
    if body['base_system'] != p['submitted']: raise ValueError('WORK_ASSIGN_BASE_CONFLICT')
    for key in ('question','completion','rationale'):
        if not isinstance(body.get(key), str) or not 1 <= len(body[key]) <= 4000: raise ValueError('WORK_'+key.upper()+'_REQUIRED')
    # Check before allocating a deferred conversation, then check again atomically.
    with repo.store.connect() as db:
        old = db.execute('SELECT result FROM design_operations WHERE owner=? AND operation=? AND status=?',
            (owner,body['operation_id'],'SUCCEEDED')).fetchone()
        if not old and counts(repo,p['id'],db)['workers'] >= cfg['max_workers']: raise ValueError('FINITE_WORKER_LIST_EXHAUSTED')
    child = repo.lab.app.conversations.create(p['title']+' · '+body['kind']+'\n'+body['question'], None,
        'scoped-task-'+identity({'lead': owner, 'operation': body['operation_id']}), defer_dispatch=True)['id']
    def apply(db):
        if counts(repo,p['id'],db)['workers'] >= cfg['max_workers']: raise ValueError('FINITE_WORKER_LIST_EXHAUSTED')
        if repo.project(p['id'],owner,db)['submitted'] != body['base_system']: raise ValueError('WORK_ASSIGN_BASE_CONFLICT')
        value = {'schema_version':'bf-scoped-task-v1','project_id':p['id'],'owner':child,'lead':owner,
                 'base_system':body['base_system'],'kind':body['kind'],'depth':1,'policy_id':cfg['id'],
                 **{k:body[k] for k in ('question','completion','rationale')}}
        value['id'] = 'WT-'+identity(value)
        db.execute('INSERT INTO design_scoped_tasks VALUES(?,?,?,?,?)',(value['id'],p['id'],child,'QUEUED',canonical(value)))
        repo.lab.event(owner,'scoped_work_assigned',value,db)
        return {**value,'status':'QUEUED'}
    return repo.mutate(owner,body,apply)


def submit(repo, owner, body, answer=False):
    p = repo.project(body['project_id'],owner); t = task(repo,owner)
    if answer:
        repo.leader(p['id'],owner)
        if policy(repo,p['id'])['kind'] != 'source': raise ValueError('WORK_ANSWER_SOURCE_STUDY_ONLY')
        sid = p['submitted']; kind = 'source'
    else:
        if not t: raise PermissionError('SCOPED_WORKER_REQUIRED')
        sid, kind = t['base_system'], t['kind']
    def apply(db):
        if not answer and task(repo,owner,db)['status'] == 'SUBMITTED': raise ValueError('WORK_ALREADY_SUBMITTED')
        if answer and db.execute('SELECT 1 FROM design_scoped_results WHERE project=? AND task IS NULL',(p['id'],)).fetchone():
            raise ValueError('WORK_ANSWER_ALREADY_SUBMITTED')
        raw = validate_result(repo,p['id'],sid,body['content'],kind,db)
        value = {'schema_version':'bf-scoped-result-v1','project_id':p['id'],'owner':owner,
                 'task_id': t['id'] if t else None,'base_system':sid,'kind':kind,**raw}
        value['id'] = 'WR-'+identity(value)
        db.execute('INSERT INTO design_scoped_results VALUES(?,?,?,?,?)',(value['id'],p['id'],owner,t['id'] if t else None,canonical(value)))
        if t: db.execute("UPDATE design_scoped_tasks SET status='SUBMITTED' WHERE id=?",(t['id'],))
        repo.lab.event(owner,'scoped_work_submitted',{'result_id':value['id'],'task_id':value['task_id']},db)
        return value
    return repo.mutate(owner,body,apply)


def result(repo, owner, body):
    p = repo.project(body['project_id'],owner); target = body.get('task_owner',owner)
    if target != owner: repo.leader(p['id'],owner)
    with repo.store.connect() as db:
        rows = db.execute('SELECT value FROM design_scoped_results WHERE project=? AND owner=? ORDER BY rowid DESC', (p['id'],target)).fetchall()
    return {'project_id':p['id'],'result':json.loads(rows[0]['value']) if rows else None,'task':task(repo,target)}


def apply_result(repo, owner, body):
    p = repo.leader(body['project_id'],owner)
    with repo.store.connect() as db: value = repo._object(db,'design_scoped_results',body['result_id'],p['id'])
    base = repo.system(p['id'],body['base_system']); original = repo.system(p['id'],value['base_system'])
    if original['task_definition']['id'] != base['task_definition']['id']: raise ValueError('WORK_TASK_REBASE_REQUIRED')
    if not value['files']: raise ValueError('WORK_RESULT_HAS_NO_PROPOSAL')
    # Three-way merge: independent proposals can share a base; conflicting paths cannot.
    for path in value['files']:
        if original['files'].get(path) != base['files'].get(path): raise ValueError('WORK_PROPOSAL_REBASE_REQUIRED')
    from .repository_task_actions import commit
    return commit(repo,owner,{**body,'files':value['files'],
        'rationale':'Scoped result '+value['id']+'; '+body['rationale']},False)


def handle(repo, owner, body, operator):
    action=body['action']; pid=body['project_id']
    if action=='repository_work_configure': return configure(repo,owner,body,operator)
    if action=='repository_work_policy': return public_policy(repo,owner,pid)
    if action=='repository_work_request_guard':
        cfg=policy(repo,pid); used=counts(repo,pid)
        if cfg and used['model_calls'] >= cfg['limits']['requests_per_trial']: raise ValueError('FINITE_MODEL_LIST_EXHAUSTED')
        return {'counts':used,'limit':cfg['limits']['requests_per_trial'] if cfg else None}
    if action=='repository_work_task': return {'task':task(repo,owner)}
    if action=='repository_work_tasks':
        repo.leader(pid,owner)
        with repo.store.connect() as db: return {'tasks':tasks(repo,pid,db)}
    if action=='repository_work_read': return read(repo,owner,body)
    if action=='repository_work_assign': return assign(repo,owner,body,operator)
    if action=='repository_work_submit': return submit(repo,owner,body)
    if action=='repository_work_answer': return submit(repo,owner,body,True)
    if action=='repository_work_result': return result(repo,owner,body)
    if action=='repository_work_apply': return apply_result(repo,owner,body)
    if action=='repository_work_run':
        p=repo.leader(pid,owner); target=body['task_owner']; t=task(repo,target)
        if not t or t['project_id']!=pid: raise PermissionError('SCOPED_WORK_PROJECT_CONFLICT')
        from .repository_controller import start, state
        if t['status']=='SUBMITTED': return state(repo,owner,target)
        running=repo.lab.controllers.get(target)
        if running and running.is_alive(): return state(repo,owner,target)
        repo.lab.handle(target,{'action':'method_authorize','task_id':'method-study-scoped-'+t['id'],
            'wall_authorization_text':'持续运行 不设置时间限制','model_profile':'engineering-reasoning-efficient-v5'},True)
        return start(repo,target)
    return None
