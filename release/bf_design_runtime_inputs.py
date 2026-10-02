"""Verify a newly generated local integration lock, never a historical seal.

Local consistency only: a party that can rewrite sources and the lock is outside
this trusted offline probe's threat model. This does not authorize execution.
"""
import hashlib
import json
from pathlib import Path


def verify_inputs():
    lock = Path(__file__).resolve().parents[1] / 'LOCAL-INPUT-LOCK.json'
    value = json.loads(lock.read_text())
    if value.get('schema') != 'bf-design-local-runtime-inputs-v1':
        raise ValueError('LOCAL_INPUT_LOCK_SCHEMA')
    failures = []
    for path, expected in value['files'].items():
        source = Path(path)
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            failures.append(path)
    if failures:
        raise ValueError('LOCAL_INTEGRATION_INPUT_DRIFT:' + ','.join(failures))
    return {'schema': value['schema'], 'files': len(value['files']),
            'lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest(),
            'unchanged': True, 'historical_seal': False, 'execution_authorized': False}
