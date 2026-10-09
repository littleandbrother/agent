"""Operator-owned model configuration; participants cannot raise their own limits."""
import json

DEFAULT = {'version': 'legacy-v1', 'thinking': 'disabled', 'reasoning_effort': None,
           'max_output_tokens': 8192, 'request_bytes': 128000, 'target_bytes': 103000}
ENGINEERING = {'version': 'engineering-reasoning-v1', 'thinking': 'enabled', 'reasoning_effort': 'high',
               'max_output_tokens': 32768, 'request_bytes': 256000, 'target_bytes': 220000}
COMPACT = {**ENGINEERING, 'version': 'engineering-reasoning-compact-v2',
           'request_bytes': 160000, 'target_bytes': 120000, 'compact_state': True}


def named(name):
    if not isinstance(name, str) or name not in (ENGINEERING['version'], COMPACT['version']):
        raise ValueError('MODEL_PROFILE_INVALID')
    return dict(COMPACT if name == COMPACT['version'] else ENGINEERING)


def for_owner(db, owner):
    row = db.execute('SELECT value FROM settings WHERE key=?', ('model_profile:' + owner,)).fetchone()
    if row is None:
        return dict(DEFAULT)
    return named(json.loads(row['value']))
