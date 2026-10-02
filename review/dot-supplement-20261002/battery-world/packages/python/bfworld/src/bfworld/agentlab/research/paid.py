"""Explicit local study authorization under the existing provider ledger/caps.

No credentials are copied into checkpoints. The model call goes through the
running workbench proxy. New study windows cannot renew prior studies/trials.
"""
import json
import time
import urllib.request

from ..store import Store, canonical, identity
from ..recovery import Recovery
from .core import implementation_binding, write_atomic


def authorize(research, protocol_key, *, max_usd, wall_s, authorization):
    p = research.get('protocols', protocol_key)
    if p['implementation'] != implementation_binding():
        raise ValueError('RESEARCH_IMPLEMENTATION_DRIFT')
    if not authorization or not 0 < max_usd <= p['budget']['study_usd'] or not 0 < wall_s <= p['budget']['study_wall_s']:
        raise ValueError('RESEARCH_AUTHORIZATION_SCOPE')
    store = Store(research.home/'state')
    Recovery(store)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT * FROM research_model_studies WHERE protocol=?', (protocol_key,)).fetchone()
        if old:
            if old['max_usd'] != max_usd or old['authorization'] != authorization:
                raise ValueError('RESEARCH_AUTHORIZATION_CONFLICT')
            return dict(old)
        limit = db.execute('SELECT * FROM model_limits WHERE id=1').fetchone()
        held = db.execute("SELECT sum(CASE WHEN status='SETTLED' THEN charged ELSE reserved END) FROM model_requests").fetchone()[0] or 0
        if held+max_usd >= limit['total_usd']:
            raise ValueError('RESEARCH_ALLOWANCE_EXCEEDS_EXISTING_GLOBAL_CAP')
        unresolved = db.execute("SELECT count(*) FROM model_requests WHERE status IN ('UNKNOWN','DISPATCHED') AND id NOT IN (SELECT request_id FROM model_resolutions WHERE kind='NOT_SENT')").fetchone()[0]
        if unresolved:
            raise ValueError('RESEARCH_PROVIDER_USAGE_UNRESOLVED')
        now = time.time()
        row = dict(protocol=protocol_key, created=now, expires=now+wall_s,
                   max_usd=max_usd, model=p['model']['requested_id'], authorization=authorization)
        db.execute('INSERT INTO research_model_studies VALUES(:protocol,:created,:expires,:max_usd,:model,:authorization)', row)
    research.event('paid_study_authorized', {**row, 'global_cap_unchanged': limit['total_usd'], 'held_at_authorization': held})
    return row


def owner(research, trial):
    claim = research.check_trial(trial)
    store = Store(research.home/'state')
    owner_id = 'research-'+trial[:32]
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        auth = db.execute('SELECT * FROM research_model_studies WHERE protocol=?', (claim['binding']['protocol'],)).fetchone()
        if not auth or time.time() >= auth['expires']:
            raise ValueError('RESEARCH_STUDY_NOT_AUTHORIZED_OR_EXPIRED')
        db.execute('INSERT OR IGNORE INTO research_model_owners VALUES(?,?,?)', (owner_id, claim['binding']['protocol'], trial))
        db.execute('INSERT OR IGNORE INTO owner_model_caps VALUES(?,?)', (owner_id, claim['budget']['trial_usd']))
        db.execute('INSERT OR IGNORE INTO grants VALUES(?,?,?,?)', (owner_id, canonical([]), 0, min(auth['expires'], claim['deadline'])))
    return store, owner_id


def metrics(research, trial):
    import sqlite3
    db = sqlite3.connect((research.home/'state/workbench.sqlite').as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in db.execute('SELECT id,status,reserved,charged,usage,response_hash,error FROM model_requests WHERE owner=? ORDER BY created', ('research-'+trial[:32],))]
    finally:
        db.close()
    return {'calls': len(rows), 'cost_usd': sum(r['charged'] if r['status'] == 'SETTLED' else r['reserved'] for r in rows),
            'unknown': any(r['status'] in {'DISPATCHED', 'UNKNOWN'} for r in rows), 'requests': rows}


def complete(research, trial, messages, port=8768):
    claim = research.check_trial(trial)
    before = metrics(research, trial)
    if before['unknown']:
        raise ValueError('RESEARCH_PROVIDER_USAGE_UNRESOLVED')
    if before['calls'] >= claim['budget']['model_calls_per_trial']:
        raise ValueError('RESEARCH_MODEL_CALL_CAP')
    store, owner_id = owner(research, trial)
    token = store.issue(owner_id)
    protocol = research.get('protocols', claim['binding']['protocol'])
    payload = {'model': protocol['model']['requested_id'], 'messages': messages, 'temperature': .7, 'max_tokens': 1024}
    number = before['calls']+1
    path = research.root/'trials'/trial/'model'/str(number)
    write_atomic(path/'request.json', canonical(payload).encode())
    request = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',
        data=canonical(payload).encode(), headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=min(110, max(1, claim['deadline']-time.time()))) as response:
        raw = response.read(2_000_000)
    write_atomic(path/'response.json', raw)
    value = json.loads(raw)
    after = metrics(research, trial)
    if after['unknown'] or after['calls'] != before['calls']+1:
        raise ValueError('RESEARCH_MODEL_LEDGER_MISMATCH')
    write_atomic(path/'receipt.json', canonical({'request_hash': identity(payload), 'ledger': after['requests'][-1],
        'reported_model': value.get('model'), 'identity_level': protocol['model']['identity_level']}).encode())
    choice = value['choices'][0]
    if choice.get('finish_reason') != 'stop':
        raise ValueError('RESEARCH_MODEL_OUTPUT_INCOMPLETE')
    return choice['message']['content']
