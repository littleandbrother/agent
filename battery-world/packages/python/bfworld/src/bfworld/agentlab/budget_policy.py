"""Explicit operator budget policy; historical limits and charges remain intact."""
import json


KEY = 'model_unbounded_policy'


def validate(value):
    if (not isinstance(value, dict) or
        value.get('schema_version') != 'bf-model-unbounded-policy-v1' or
        value.get('mode') != 'unbounded' or
        value.get('authorized_by') != 'direct-user' or
        not isinstance(value.get('direct_user_authorization'), str) or
        not value['direct_user_authorization'].strip() or
        value.get('fees_reset') is not False or
        value.get('unknown_reservations_preserved') is not True or
        any(key not in value or value[key] is not None for key in
            ('cumulative_usd_cap', 'cumulative_token_cap', 'request_count_cap', 'request_usd_cap'))):
        raise ValueError('MODEL_UNBOUNDED_AUTHORIZATION_REQUIRED')
    scope = value.get('scope')
    if scope == 'owners':
        owners = value.get('owners')
        if (not isinstance(owners, list) or not owners or
            any(not isinstance(owner, str) or not owner.startswith('pi-chat-') for owner in owners) or
            len(set(owners)) != len(owners)):
            raise ValueError('MODEL_UNBOUNDED_OWNER_SCOPE_REQUIRED')
    elif scope != 'interactive':
        raise ValueError('MODEL_UNBOUNDED_SCOPE_INVALID')
    return value


def configured(db):
    row = db.execute('SELECT value FROM settings WHERE key=?', (KEY,)).fetchone()
    return validate(json.loads(row['value'])) if row else None


def for_owner(db, owner):
    value = configured(db)
    if not value or not isinstance(owner, str):
        return None
    if value['scope'] == 'owners':
        return value if owner in value['owners'] else None
    # Interactive defaults do not silently amend frozen scientific studies.
    if (owner.startswith('pi-chat-') and not
        db.execute('SELECT 1 FROM research_model_owners WHERE owner=?', (owner,)).fetchone()):
        return value
    return None


def install(db, value):
    validate(value)
    db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
               (KEY, json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))))
