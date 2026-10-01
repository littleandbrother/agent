#!/usr/bin/env python3
"""Read-only standard-library artifact verification. Starts no processes/services."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def journal(path):
    raw = Path(path).read_bytes()
    assert not raw or raw.endswith(b'\n'), 'truncated journal'
    rows = [json.loads(line) for line in raw.splitlines()]
    previous = None
    for number, row in enumerate(rows):
        assert row['index'] == number and row['previous_hash'] == previous
        assert row['run_id'] == rows[0]['run_id']
        assert row['event_hash'] == 'sha256:' + digest({k:v for k,v in row.items() if k != 'event_hash'})
        previous = row['event_hash']
    return rows

def locate(layer, text):
    original = {'layer-01-launcher': '/workspace/shared/controlled-launcher-integration-20261001/',
                'layer-02-magnetic-service': '/workspace/shared/controlled-magnetic-service-integration-20261001/'}[layer]
    relative = text.removeprefix(original)
    candidate = (ROOT / layer / relative).resolve()
    assert candidate.is_relative_to((ROOT / layer).resolve()), 'outside export'
    return candidate

def verify():
    exported = read(ROOT / 'PORTABLE-MANIFEST.json')
    for path, info in exported['files'].items():
        assert sha(ROOT / path) == info['sha256'], 'export hash mismatch: ' + path
    omissions = read(ROOT / 'EXPORT-OMISSIONS.json')['omitted_files']
    original_counts = {}
    for layer in ('layer-01-launcher', 'layer-02-magnetic-service'):
        manifest = read(ROOT / layer / 'FILE-MANIFEST.json')
        skipped = {x['path'] for x in omissions if x['layer'] == layer}
        checked = 0
        for path, info in manifest['files'].items():
            item = ROOT / layer / path
            if not item.exists():
                assert path in skipped, 'unexplained missing sealed file: ' + path
                assert '.pi' in Path(path).parts or any(x in path.lower() for x in ('credential', 'secret', '.token', '.sqlite'))
            else:
                assert sha(item) == info['sha256'], 'sealed input mismatch: ' + path
                checked += 1
        original_counts[layer] = {'verified_included_files': checked, 'explicitly_omitted_auth_files': len(skipped)}
    attempts = 0
    processes = 0
    for run in ('retained-controls-v1', 'retained-controls-v2'):
        directory = ROOT / 'layer-01-launcher/reports' / run
        rows = journal(directory / 'events.jsonl')
        attempts += sum(r['type'] == 'attempt_reserved' for r in rows)
        for row in rows:
            if row['type'] != 'attempt_finished':
                continue
            p = row['payload']
            receipt_path = directory / p['receipt_file']
            assert sha(receipt_path) == p['receipt_sha256']
            receipt = read(receipt_path)
            assert receipt['provider_calls'] == 0 and receipt['participant_calls'] == 0 and receipt['scientific_success'] is False
            detail = receipt['details']
            if not detail.get('process_started'):
                continue
            processes += 1
            trace_path = locate('layer-01-launcher', detail['trace_file'])
            assert sha(trace_path) == detail['trace_sha256']
            assert sha(locate('layer-01-launcher', detail['stderr_file'])) == detail['stderr_sha256']
            events = [json.loads(x) for x in trace_path.read_text().splitlines() if x.startswith('{')]
            acts = [e for e in events if e.get('type') == 'controlled_activation']
            expected = detail['expected']
            for event in acts:
                for key in ('pid', 'nonce', 'harness_source_hash', 'app_build_hash', 'loaded', 'binding_hash', 'mode'):
                    assert event[key] == expected[key]
                if event['phase'] == 'invoked':
                    output = json.dumps(event['output'], ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
                    assert hashlib.sha256(output).hexdigest() == event['output_hash']
            if receipt['status'] == 'activation_pass':
                assert detail['exit_code'] == 0
                assert [e['entrypoint'] for e in acts if e['phase'] == 'post_import'] == ['solver', 'improver']
                last = 'solver.solverPrompt' if expected['mode'] == 'solve' else 'improver.improvementPrompt'
                assert [e['entrypoint'] for e in acts if e['phase'] == 'invoked'] == ['solver.initialState', last]
    assert attempts == 22 and processes == 18
    spec = importlib.util.spec_from_file_location('strict_readback', ROOT / 'layer-02-magnetic-service/src/trace_readback.py')
    strict = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(strict)
    service_runs = []
    for run in ('probe-v1', 'probe-v2', 'probe-v3'):
        directory = ROOT / 'layer-02-magnetic-service/reports' / run
        packet = read(directory / 'EXECUTION-PACKET.json')
        assert packet['packet_id'] == digest({k:v for k,v in packet.items() if k != 'packet_id'})
        result = read(directory / 'RESULT.json')
        trace_path = directory / 'process/stdout.jsonl'
        assert sha(trace_path) == result['stdout_sha256']
        assert sha(directory / 'process/stderr.log') == result['stderr_sha256']
        events = [json.loads(x) for x in trace_path.read_text().splitlines() if x.startswith('{')]
        manifest = next(e['source'] for e in events if e['type'] == 'harness_loaded')
        first = next(e for e in events if e['type'] == 'controlled_activation')
        checked = strict.validate_trace(events, packet, manifest, result['pid'], first['nonce'], result['exit_code'])
        rows = journal(directory / 'service/events.jsonl')
        for row in rows:
            if row['type'] == 'job_blocked':
                job = directory / 'service/jobs' / (row['payload']['id'] + '.json')
                assert sha(job) == row['payload']['receipt_sha256']
            elif row['type'] == 'snapshot_complete':
                snapshot = directory / 'service/snapshots' / row['payload']['snapshot_id'] / 'receipt.json'
                assert sha(snapshot) == row['payload']['receipt_sha256']
                if run == 'probe-v3':
                    value = read(snapshot)
                    assert digest(value['uploaded_files']) == value['file_hash']
                    assert digest({'owner': value['owner'], 'packet_id': value['packet_id'], 'files': value['uploaded_files']}) == value['snapshot_id']
        assert checked['native_tool_identities'] == {} and checked['native_solver_calls'] == 0
        service_runs.append({'run': run, 'task': packet['task_id'], 'status': checked['status']})
    return {'status': 'portable_evidence_checks_passed', 'exported_files': len(exported['files']),
        'original_seals': original_counts, 'layer_01_retained_attempts': attempts,
        'layer_01_retained_processes': processes, 'layer_02_retained_runs': service_runs,
        'new_model_calls': 0, 'new_native_calls': 0, 'scope': 'hash/journal/trace readback only; not a Pi rebuild or scientific qualification'}

if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
