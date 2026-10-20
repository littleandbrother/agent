#!/usr/bin/env python3
"""Verify the saved A/B evidence capsule without models or native execution."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(value):
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    manifest = json.loads((ROOT/'manifest.json').read_text())
    for name, ref in manifest['files'].items():
        path = ROOT/name
        assert path.resolve().is_relative_to(ROOT) and not path.is_symlink(), name
        assert digest(path) == ref['sha256'] and path.stat().st_size == ref['bytes'], name
    evidence = ROOT/'evidence'
    proof = json.loads((evidence/'qualification.json').read_text())
    assert proof['id'] == 'FQ-'+identity({k:v for k,v in proof.items() if k != 'id'})
    assert proof['status'] == 'PASS' and len(proof['controls']) == 11 and all(proof['controls'].values())
    assert digest(evidence/'protocol.json') == proof['protocol']
    for name, expected in proof['evidence'].items():
        assert digest(evidence/name) == expected, name
    for label, frames in [('nominal',5), ('delayed-start',1)]:
        check = json.loads((evidence/(label+'-check.json')).read_text())
        gates = check['result']['gates']
        assert len(gates['receiver_service']['findings']['received_sequences']) == frames
        assert gates['receiver_service']['status'] == ('PASS' if label == 'nominal' else 'FAIL')
        delivery = json.loads((evidence/(label+'-delivery.json')).read_text())
        assert delivery['status'] == 'PASS' and delivery['system'] == check['target']
    protected = json.loads((evidence/'preservation.json').read_text())
    assert protected['status'] == 'PASS'
    assert protected['original_sessions_engineering_billing_unchanged']
    assert protected['v2_sessions_design_and_billing_unchanged']
    assert protected['baseline']['status'] == 'PASS'
    print(json.dumps({'status':'PASS','files':len(manifest['files']), 'controls':11,
        'qualification':proof['id'],'model_calls':0,'native_dispatches':0},ensure_ascii=False))


if __name__ == '__main__':
    main()
