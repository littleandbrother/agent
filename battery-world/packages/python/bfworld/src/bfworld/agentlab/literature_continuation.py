"""Operator-authorized renewal; fees and unresolved usage remain historical facts."""
import math
import time
from pathlib import Path
from .literature_campaign import read, digest
from .store import identity, canonical
from . import budget_policy

AUTHORITY = 'campaign/parallel-20261009/authorization.json'
BUDGET_AUTHORITY = 'campaign/parallel-20261009/unbounded-budget-authorization.json'
TIME_AUTHORITY = 'campaign/parallel-20261009/authorization-v2.json'
TIME_BUDGET_AUTHORITY = 'campaign/parallel-20261009/unbounded-budget-authorization-v2.json'

def validate_authority(value, now):
    version = value.get('schema_version')
    if (version not in ('bf-ten-paper-continuation-authority-v1', 'bf-ten-paper-continuation-authority-v2') or
        not isinstance(value.get('direct_user_authorization'), str) or
        not value['direct_user_authorization'].strip() or
        value.get('defer_usage_reconciliation') is not True or
        value.get('unknown_rows_and_full_reservations_preserved') is not True or
        value.get('no_fee_reset') is not True):
        raise ValueError('CONTINUATION_USER_AUTHORITY_REQUIRED')
    created = value.get('created')
    if type(created) not in (int, float) or not math.isfinite(created) or now < created:
        raise ValueError('CONTINUATION_USER_WINDOW_EXPIRED')
    if version == 'bf-ten-paper-continuation-authority-v1':
        if value.get('usd_cap_per_original_owner') != 30 or value.get('additional_wall_seconds_per_original_owner') != 21600:
            raise ValueError('CONTINUATION_USER_AUTHORITY_REQUIRED')
        if now >= created + 21600: raise ValueError('CONTINUATION_USER_WINDOW_EXPIRED')
    elif (value.get('wall_unbounded') is not True or
          value.get('wall_authorization_text') != '持续运行 不设置时间限制' or
          'additional_wall_seconds_per_original_owner' not in value or
          value['additional_wall_seconds_per_original_owner'] is not None or
          'usd_cap_per_original_owner' not in value or value['usd_cap_per_original_owner'] is not None or
          not isinstance(value.get('parent_authority_sha256'), str) or len(value['parent_authority_sha256']) != 64):
        raise ValueError('CONTINUATION_UNBOUNDED_TIME_AUTHORITY_REQUIRED')
    owners = value.get('owners', [])
    if (len(owners) != 10 or {r.get('paper_id') for r in owners} != {f'P{i:02}' for i in range(1, 11)} or
        len({r.get('owner') for r in owners}) != 10 or
        any(not isinstance(r.get('owner'), str) or not r['owner'].startswith('pi-chat-') for r in owners)):
        raise ValueError('CONTINUATION_TEN_ORIGINAL_OWNERS_REQUIRED')
    return value

def load_authority(root, now=None):
    path = Path(root) / AUTHORITY
    if not path.is_file(): return None
    v2 = Path(root) / TIME_AUTHORITY
    if v2.is_file():
        value=validate_authority(read(v2), time.time() if now is None else now)
        parent=read(path)
        validate_authority(parent, parent['created'])  # Historical authorization remains historical.
        if value['parent_authority_sha256'] != digest(path) or value['owners'] != parent['owners']:
            raise ValueError('CONTINUATION_ORIGINAL_OWNER_HISTORY_CHANGED')
        amendment=Path(root)/TIME_BUDGET_AUTHORITY
        policy=budget_policy.validate(read(amendment))
        owners={r['owner'] for r in value['owners']}
        if (policy['schema_version']!='bf-model-unbounded-policy-v2' or policy['scope']!='owners' or
            set(policy['owners'])!=owners or set(policy.get('wall_owners',policy['owners']))!=owners or
            policy.get('original_authority_sha256')!=digest(path) or
            policy.get('active_authority_sha256')!=digest(v2)):
            raise ValueError('CONTINUATION_BUDGET_AMENDMENT_SCOPE_CHANGED')
        return {**value,'authority_file':TIME_AUTHORITY,'authority_sha256':digest(v2),
                'budget_policy':policy,'budget_authority_file':TIME_BUDGET_AUTHORITY,
                'budget_authority_sha256':digest(amendment)}
    scope={**validate_authority(read(path), time.time() if now is None else now),
           'authority_file': AUTHORITY, 'authority_sha256': digest(path)}
    amendment=Path(root)/BUDGET_AUTHORITY
    if amendment.is_file():
        policy=budget_policy.validate(read(amendment))
        if (policy['scope']!='owners' or set(policy['owners'])!={r['owner'] for r in scope['owners']} or
            policy.get('original_authority_sha256')!=scope['authority_sha256'] or
            policy.get('wall_window_changed') is not False):
            raise ValueError('CONTINUATION_BUDGET_AMENDMENT_SCOPE_CHANGED')
        scope.update(budget_policy=policy,budget_authority_file=BUDGET_AUTHORITY,
                     budget_authority_sha256=digest(amendment))
    return scope

def owner_window(root, scope, paper, owner, original_target, now):
    validate_authority(scope, now)
    row = next((r for r in scope['owners'] if r['paper_id'] == paper and r['owner'] == owner), None)
    if not row: raise ValueError('CONTINUATION_ORIGINAL_OWNER_REQUIRED')
    path = Path(original_target) / 'authorization.json'
    original = row['original_authorization']
    if path.resolve() != (Path(root) / original['path']).resolve() or digest(path) != original['sha256']:
        raise ValueError('CONTINUATION_ORIGINAL_AUTHORIZATION_CHANGED')
    auth = read(path)
    if auth.get('usd_cap') != 30: raise ValueError('CONTINUATION_MONETARY_CAP_CHANGED')
    window={'schema_version': 'bf-paper-renewed-window-v1', 'paper_id': paper, 'owner': owner,
            'usd_cap': 30, 'expires': None if scope.get('wall_unbounded') else scope['created'] + 21600,
            'original_expires': auth['expires'], 'original_authorization_sha256': original['sha256'],
            'authority_file': scope['authority_file'], 'authority_sha256': scope['authority_sha256'],
            'defer_usage_reconciliation': True, 'fees_reset': False}
    if scope.get('budget_policy'):
        policy=budget_policy.validate(scope['budget_policy'])
        if owner not in policy['owners']:raise ValueError('CONTINUATION_BUDGET_OWNER_CHANGED')
        window.update(usd_cap=None,token_cap=None,request_count_cap=None,budget_policy=policy,
                      budget_authority_file=scope['budget_authority_file'],
                      budget_authority_sha256=scope['budget_authority_sha256'])
    return window

def prior_requests_allowed(rows, scope, owner):
    permitted = {r['owner'] for r in scope['owners']} if scope else set()
    return all(r['status'] == 'SETTLED' or
               (r['status'] == 'UNKNOWN' and r['owner'] == owner and owner in permitted)
               for r in rows)

def retained_unknowns(rows, historical, scope, now):
    if scope: validate_authority(scope, now)
    pinned = {r['id']: r['original_row_sha256'] for r in historical}
    owners = {r['owner'] for r in scope['owners']} if scope else set()
    records = []
    for row in rows:
        sha = identity(row)
        if row['id'] in pinned:
            if sha != pinned[row['id']]: raise ValueError('UNKNOWN_LIABILITY_CHANGED')
        elif row.get('status') != 'UNKNOWN' or row['owner'] not in owners:
            raise ValueError('UNKNOWN_LIABILITY_NOT_AUTHORIZED')
        records.append({'id': row['id'], 'original_row_sha256': sha,
                        'retained_reservation_usd': row['reserved']})
    return records

def record_carryforwards(db, protocol, records, authorization):
    for row in records:
        old = db.execute('SELECT original_row_hash FROM research_usage_carryforwards WHERE protocol=? AND request_id=?',
                         (protocol, row['id'])).fetchone()
        if old and old['original_row_hash'] != row['original_row_sha256']:
            raise ValueError('UNKNOWN_LIABILITY_CHANGED')
        db.execute('INSERT OR IGNORE INTO research_usage_carryforwards VALUES(?,?,?,?,?)',
                   (protocol, row['id'], row['original_row_sha256'], canonical(authorization), time.time()))

def renew_owner(db, owner, window, records, authorization):
    row = db.execute('SELECT protocol FROM research_model_owners WHERE owner=?', (owner,)).fetchone()
    cap = db.execute('SELECT max_usd FROM owner_model_caps WHERE owner=?', (owner,)).fetchone()
    if not row or not cap or cap['max_usd'] != 30: raise ValueError('ORIGINAL_OWNER_CAP_REQUIRED')
    if window.get('budget_policy'):
        policy=budget_policy.validate(window['budget_policy'])
        if policy['scope']!='owners' or owner not in policy['owners']:
            raise ValueError('CONTINUATION_BUDGET_OWNER_CHANGED')
        budget_policy.install(db,policy)
    protocol = row['protocol']
    if window['expires'] is None:
        if not budget_policy.unbounded_time(db,owner): raise ValueError('CONTINUATION_UNBOUNDED_TIME_AUTHORITY_REQUIRED')
        # Preserve old studies, limits, grants and finite continuation receipts.
        # The separately authorized v2 policy is the effective time override.
    else:
        db.execute('UPDATE research_model_studies SET expires=?,authorization=? WHERE protocol=?',
                   (window['expires'], canonical(authorization), protocol))
        db.execute('INSERT INTO research_usage_continuations VALUES(?,?,?,?) ON CONFLICT(protocol) DO UPDATE SET expires=excluded.expires,authorization=excluded.authorization',
                   (protocol, time.time(), window['expires'], canonical(authorization)))
    record_carryforwards(db, protocol, records, authorization)
    if window['expires'] is not None:
        db.execute('UPDATE model_limits SET expires=max(expires,?) WHERE id=1', (window['expires'],))
