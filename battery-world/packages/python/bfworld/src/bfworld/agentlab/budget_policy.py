"""Explicit operator budget policy; historical limits and charges remain intact."""
import json


KEY = 'model_unbounded_policy'


def validate(value):
    if (not isinstance(value, dict) or
        value.get('schema_version') not in ('bf-model-unbounded-policy-v1','bf-model-unbounded-policy-v2') or
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
    if value['schema_version']=='bf-model-unbounded-policy-v2':
        if (value.get('wall_seconds') is not None or value.get('wall_authorized_by')!='direct-user'
            or value.get('wall_authorization_text')!='持续运行 不设置时间限制'
            or value.get('wall_unbounded') is not True):
            raise ValueError('MODEL_UNBOUNDED_TIME_AUTH_REQUIRED')
        carried=value.get('unknown_carryforward',{})
        if not isinstance(carried,dict) or any(not isinstance(k,str) or not isinstance(v,str) or
            len(v)!=64 for k,v in carried.items()):
            raise ValueError('MODEL_UNBOUNDED_CARRYFORWARD_INVALID')
        wall_owners=value.get('wall_owners',value.get('owners'))
        if not isinstance(wall_owners,list) or not wall_owners or any(not isinstance(o,str) or not o.startswith('pi-chat-') for o in wall_owners):
            raise ValueError('MODEL_UNBOUNDED_WALL_SCOPE_REQUIRED')
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


def unbounded_time(db,owner):
    value=for_owner(db,owner)
    return value if value and value['schema_version']=='bf-model-unbounded-policy-v2' and owner in value.get('wall_owners',value.get('owners',[])) else None
