"""Operator-owned model configuration; participants cannot raise their own limits."""
import json

DEFAULT = {'version': 'legacy-v1', 'thinking': 'disabled', 'reasoning_effort': None,
           'max_output_tokens': 8192, 'request_bytes': 128000, 'target_bytes': 103000}
ENGINEERING = {'version': 'engineering-reasoning-v1', 'thinking': 'enabled', 'reasoning_effort': 'high',
               'max_output_tokens': 32768, 'request_bytes': 256000, 'target_bytes': 220000}
COMPACT = {**ENGINEERING, 'version': 'engineering-reasoning-compact-v2',
           'request_bytes': 160000, 'target_bytes': 120000, 'compact_state': True}
OUTPUT64 = {**ENGINEERING, 'version': 'engineering-reasoning-output64-v3',
            'max_output_tokens': 65536}
ACTIVE = {**OUTPUT64, 'version': 'engineering-reasoning-active-context-v4',
          'request_bytes': 1048576}
EFFICIENT = {**ACTIVE, 'version': 'engineering-reasoning-efficient-v5',
             'aggregate_closed_continuations': True, 'deduplicate_skills': True}


def named(name):
    profiles = {p['version']: p for p in (ENGINEERING, COMPACT, OUTPUT64, ACTIVE, EFFICIENT)}
    if not isinstance(name, str) or name not in profiles:
        raise ValueError('MODEL_PROFILE_INVALID')
    return dict(profiles[name])


def qualified_owner(current, qualification, owner):
    """Only an operator-published qualification can opt an original owner in."""
    overrides = qualification.get('original_owner_output_profiles', {})
    if not isinstance(overrides, dict):
        raise ValueError('MODEL_PROFILE_OVERRIDE_INVALID')
    version = overrides.get(owner)
    return named(version) if version is not None else dict(current)


def for_owner(db, owner):
    row = db.execute('SELECT value FROM settings WHERE key=?', ('model_profile:' + owner,)).fetchone()
    if row is None:
        return dict(DEFAULT)
    return named(json.loads(row['value']))
