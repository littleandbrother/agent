"""Operator-owned model configuration; participants cannot raise their own limits."""
import json

DEFAULT = {'version': 'legacy-v1', 'thinking': 'disabled', 'reasoning_effort': None,
           'max_output_tokens': 8192, 'request_bytes': 128000, 'target_bytes': 103000}
ENGINEERING = {'version': 'engineering-reasoning-v1', 'thinking': 'enabled', 'reasoning_effort': 'high',
               'max_output_tokens': 32768, 'request_bytes': 256000, 'target_bytes': 220000}


def for_owner(db, owner):
    row = db.execute('SELECT value FROM settings WHERE key=?', ('model_profile:' + owner,)).fetchone()
    if row is None:
        return dict(DEFAULT)
    name = json.loads(row['value'])
    if name != ENGINEERING['version']:
        raise ValueError('MODEL_PROFILE_INVALID')
    return dict(ENGINEERING)
