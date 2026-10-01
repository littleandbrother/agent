from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from paths import ROOT, FIRST, PI, read, sha, write_once, verify_inputs

def finish():
    tests = (ROOT / 'reports/tests-final-24.log').read_text()
    if 'Ran 24 tests' not in tests or not tests.rstrip().endswith('OK'):
        raise ValueError('FINAL_TEST_LOG_NOT_PASSED')
    # Restore historical application bytes only when their exact prior recorded
    # source/build hashes verify. This never alters a retained trace or old seal.
    new = 'Upload immutable candidate.json under the registered canonical magnetic schema, then request preflight. Missing native identity or qualification returns BLOCKED, never a completed experiment. Reuse operation_id after interruption.'
    old = 'Upload immutable current design.json and policy.py, then submit one async experiment. Persist and reuse operation_id after interruption.'
    for run in ('probe-v1', 'probe-v2'):
        output = ROOT / 'reports' / run / 'source'
        output.mkdir(parents=True, exist_ok=True)
        for suffix, expected in [('ts', '1dfffd1accd78de4334b52550978291a66db18f7d31fd9601f1a987e877ed996'),
                                 ('js', '0eb73f1653d9393dfbffd7b03bfbd5f2f37d40c4fbdb8c660616ffdd60e7d266')]:
            source = PI / 'packages/bf-agent' / ('src' if suffix == 'ts' else 'dist') / ('main.' + suffix)
            value = source.read_text().replace(new, old)
            target = output / ('main.' + suffix)
            if not target.exists():
                target.write_text(value)
            if sha(target) != expected:
                raise ValueError('HISTORICAL_APPLICATION_RECONSTRUCTION_DID_NOT_MATCH_RECORDED_HASH')
    runs = []
    for name in ('probe-v1', 'probe-v2', 'probe-v3'):
        base = ROOT / 'reports' / name
        result = read(base / 'RESULT.json')
        if result['status'] != 'transport_and_identity_pass_native_blocked' or result['model_calls'] != 0 or result['native_solver_calls'] != 0:
            raise ValueError('UNEXPECTED_RETAINED_RESULT')
        runs.append({'run': name, 'result_sha256': sha(base / 'RESULT.json'),
            'packet_sha256': sha(base / 'EXECUTION-PACKET.json'),
            'events_sha256': sha(base / 'service/events.jsonl'),
            'stdout_sha256': result['stdout_sha256'], 'status': result['status'],
            'final_strict_schema': name == 'probe-v3'})
    reviewer = Path('/workspace/shared/next-stage-integration-review-20261001/service-review-v2/outputs')
    receipt = {'schema': 'magnetic-service-integration-final-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'reviewed_trusted_offline_transport_passed_native_and_participant_dispatch_blocked',
        'test_count': 24, 'tests_log_sha256': sha(ROOT / 'reports/tests-final-24.log'),
        'retained_runs': runs, 'retained_processes': 3, 'retained_job_intents': 3,
        'retained_snapshot_intents': 3, 'all_retained_jobs_status': 'BLOCKED',
        'scope': 'three repeated engineering probes; not independent scientific trials',
        'model_calls': 0, 'participant_calls': 0, 'native_solver_calls': 0,
        'approved_model': None, 'approved_budget': None, 'qualified_tasks': '0/2',
        'first_layer_manifest_sha256': sha(FIRST / 'FILE-MANIFEST.json'),
        'first_layer_seal_unchanged': True, 'source_verification': verify_inputs(),
        'independent_review': {'snapshot_binding_sha256': sha(reviewer / 'SNAPSHOT-BINDING.json'),
            'isolated_test_log_sha256': sha(reviewer / 'isolated-tests.log'),
            'scope_review': 'passed', 'final_byte_check': 'separate reviewer addendum after this manifest'},
        'legacy_task_alias_used': False, 'legacy_provider_or_worker_instantiated': False,
        'fictional_profile_is_authorization': False, 'git_commits': 0, 'git_pushes': 0,
        'claim_boundary': 'Real Pi registered-tool and existing HTTP-handler identity path, scripted trusted control only. Missing native identities remain absent. No autonomous participant, native solve, qualification, or scientific success.'}
    write_once(ROOT / 'FINAL-RECEIPT.json', receipt)
    files, links = {}, {}
    for path in sorted(ROOT.rglob('*')):
        relative = str(path.relative_to(ROOT))
        if path.is_symlink():
            links[relative] = str(path.readlink())
        elif path.is_file() and relative != 'FILE-MANIFEST.json':
            files[relative] = {'sha256': sha(path), 'bytes': path.stat().st_size}
    write_once(ROOT / 'FILE-MANIFEST.json', {'schema': 'magnetic-service-delivery-manifest-v1',
        'files': files, 'external_read_only_symlinks': links,
        'scope': 'sealed second integration layer; requires pinned dependencies for actual Pi rerun'})
    print({'receipt_sha256': sha(ROOT / 'FINAL-RECEIPT.json'), 'manifest_sha256': sha(ROOT / 'FILE-MANIFEST.json'),
        'files': len(files), 'links': len(links)})

if __name__ == '__main__':
    finish()
