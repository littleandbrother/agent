"""Exact operator-approved historical liabilities; never settlement or grants."""
import json
import time
from .store import canonical, identity

AMENDMENT_ID = 'BF-REPAIR-ACCOUNTING-AMENDMENT-20261021-001'
REQUEST_ID = 'llm-1de4d60d9bc93d257392'
ORIGINAL_OWNER = 'pi-chat-c93c7d3151f67b86'
ORIGINAL_ROW_HASH = 'cb56348ff7ed2dfafa7358a02d680a627d142d2e1dcd14de27acf49ed3247843'
CODEBT_AMENDMENT_ID = 'BF-PQE-CODEBT-ACCOUNTING-AMENDMENT-20261024-001'
CODEBT_PACKAGE = 'BF-PQE-CODEBT-KILL-20261024-001'
PARTIAL_ANCESTOR_PACKAGE = 'BF-PQE-PARTIAL-ANCESTOR-VALIDATION-20261026-001'
RELATION_SYNTHESIS_PACKAGE = 'BF-PQE-RELATION-SYNTHESIS-20261102-001'
JOINT_CLOSURE_PACKAGE = 'BF-PQE-JOINT-CLOSURE-20261102-001'
# The 2026-10-26 direct work order carries the two exact, unchanged liabilities
# into this one new package. The original authorizations and ledger rows remain
# untouched; this finite allowlist does not authorize any other new package.
CARRYFORWARD_PACKAGES = {CODEBT_PACKAGE: CODEBT_PACKAGE,
                        PARTIAL_ANCESTOR_PACKAGE: CODEBT_PACKAGE,
                        # Direct human 2026-11-02 finite work order: the same
                        # two immutable liabilities, no old retry or new waiver.
                        RELATION_SYNTHESIS_PACKAGE: CODEBT_PACKAGE,
                        # Direct human "开始执行吧": same immutable liabilities
                        # for the one finite same-backend joint/closure package.
                        JOINT_CLOSURE_PACKAGE: CODEBT_PACKAGE}
EXACT_POLICIES = {
    AMENDMENT_ID: dict(request_id=REQUEST_ID, owner=ORIGINAL_OWNER,
                      row_hash=ORIGINAL_ROW_HASH, reserve=0.2661324, package=None),
    CODEBT_AMENDMENT_ID: dict(request_id='llm-16cd5bfe95e06e92fd6d',
        owner='pi-chat-cf40305e2149b2b9',
        row_hash='d99d2c6bc24a008eb13fbde98045f8e2b982b2acaadf97558149c26bafdcb801',
        reserve=0.1025205, package=CODEBT_PACKAGE),
}


def ensure_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS historical_usage_exceptions(
        id TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,original_row_hash TEXT NOT NULL,
        authorized_at REAL NOT NULL,authorization TEXT NOT NULL)''')


def valid_authority(value):
    policy = EXACT_POLICIES.get(value.get('id')) if isinstance(value, dict) else None
    return (policy is not None and value.get('request_id') == policy['request_id']
            and isinstance(value.get('authority'), str) and bool(value['authority'].strip())
            and value.get('preserve_original_status') == 'UNKNOWN'
            and value.get('preserve_reserved_usd') == policy['reserve']
            and (policy['package'] is None or value.get('package') == policy['package'])
            and value.get('original_request_retry_allowed') is False
            and value.get('source_ledger_rewrite_allowed') is False)


def install(db, authorization, authorized_at):
    if not valid_authority(authorization):
        raise ValueError('EXACT_HISTORICAL_USAGE_AUTHORITY_REQUIRED')
    spec = EXACT_POLICIES[authorization['id']]
    row = db.execute('SELECT * FROM model_requests WHERE id=?', (spec['request_id'],)).fetchone()
    if not row or identity(dict(row)) != spec['row_hash']:
        raise ValueError('HISTORICAL_USAGE_ORIGINAL_ROW_CHANGED')
    if not row['created'] < authorized_at <= time.time():
        raise ValueError('HISTORICAL_USAGE_AUTHORITY_TIME_INVALID')
    ensure_schema(db)
    expected = (authorization['id'], spec['request_id'], spec['row_hash'], authorized_at, canonical(authorization))
    old = db.execute('SELECT * FROM historical_usage_exceptions WHERE id=?', (authorization['id'],)).fetchone()
    if old and tuple(old) != expected:
        raise ValueError('HISTORICAL_USAGE_AUTHORITY_CHANGED')
    db.execute('INSERT OR IGNORE INTO historical_usage_exceptions VALUES(?,?,?,?,?)', expected)


def verified_exceptions(db, package=None):
    """Read back exact policy and original liability; a scoped policy never widens."""
    result = {}
    for amendment, spec in EXACT_POLICIES.items():
        if (spec['package'] is not None
                and CARRYFORWARD_PACKAGES.get(package) != spec['package']):
            continue
        policy = db.execute('SELECT * FROM historical_usage_exceptions WHERE id=?', (amendment,)).fetchone()
        if (not policy or policy['request_id'] != spec['request_id']
                or policy['original_row_hash'] != spec['row_hash']):
            continue
        try:
            authority = json.loads(policy['authorization'])
        except (TypeError, ValueError):
            continue
        row = db.execute('SELECT * FROM model_requests WHERE id=?', (spec['request_id'],)).fetchone()
        if (valid_authority(authority) and authority['id'] == amendment and row
                and row['created'] < policy['authorized_at'] <= time.time()
                and identity(dict(row)) == spec['row_hash']):
            result[spec['request_id']] = spec['row_hash']
    return result


def carryforward_for_new_batch(db, owner):
    """Only a new conversation can carry the exact immutable old R11 liability.

    This does not revive the old owner, issue a grant, change any monetary ceiling,
    authorize a retry, or permit any subsequent missing provider usage.
    """
    if not owner:
        return {}
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'historical_usage_exceptions', 'conversations'} <= tables:
        return {}
    batch = db.execute('SELECT * FROM conversations WHERE id=?', (owner,)).fetchone()
    if not batch:
        return {}
    operation = dict(batch).get('operation', '') or ''
    package = next((name for name in CARRYFORWARD_PACKAGES
                    if operation.startswith(name + '-')), None)
    verified = verified_exceptions(db, package)
    result = {}
    for amendment, spec in EXACT_POLICIES.items():
        policy = db.execute('SELECT * FROM historical_usage_exceptions WHERE id=?', (amendment,)).fetchone()
        if (policy and owner != spec['owner'] and batch['created'] >= policy['authorized_at']
                and spec['request_id'] in verified):
            result[spec['request_id']] = spec['row_hash']
    return result


def new_batch_usage_blockers(db, owner):
    carried = carryforward_for_new_batch(db, owner)
    return [dict(row) for row in db.execute(
        "SELECT * FROM model_requests WHERE status='UNKNOWN' OR (status='SETTLED' AND usage IS NULL)")
        if carried.get(row['id']) != identity(dict(row))]
