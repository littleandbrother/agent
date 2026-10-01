"""Write a new delivery receipt and seal, preserving every prior retained run."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from paths import ROOT, read, sha, write_once, verify_sources
import integration as i

def finish():
    versions = []
    totals = Counter()
    for name in ['retained-controls-v1', 'retained-controls-v2']:
        folder = ROOT / 'reports' / name
        result = read(folder / 'RESULT.json')
        versions.append({'run': name, 'result_sha256': sha(folder / 'RESULT.json'),
            'events_sha256': sha(folder / 'events.jsonl'),
            'assigned_episodes': result['all_attempt_ledger']['assigned_episode_count'],
            'recorded_attempts': result['all_attempt_ledger']['attempt_count'],
            'h0_solver_status': result['controls']['h0-solve'],
            'status': 'retained_failed_relative_path_history' if name.endswith('v1') else 'current_verified_controls',
            'historical_adapter_source_identity_recorded': name.endswith('v2')})
        for row in result['all_attempt_ledger']['episodes']:
            totals.update(row['statuses'])
    final_root = ROOT / 'reports/retained-controls-v2'
    final = read(final_root / 'RESULT.json')
    expected = {'h0-solve': 'activation_pass', 'h0-improve': 'activation_pass',
        'manual-h1': 'activation_pass', 'rollback-h0': 'activation_pass',
        'failed-import': 'import_failed', 'failed-invoke': 'invocation_failed',
        'failed-improver': 'invocation_failed', 'failed-build': 'build_failed',
        'timeout': 'timed_out', 'recover-receipt': 'activation_pass'}
    if final['controls'] != expected:
        raise ValueError('RETAINED_CONTROL_RESULT_MISMATCH')
    for path in (final_root / 'receipts').glob('*.json'):
        receipt = read(path)
        if receipt['details'].get('process_started'):
            i.verify_process_receipt(receipt['details'])
    tests = (ROOT / 'reports/tests-final-v2.log').read_text()
    if 'Ran 32 tests' not in tests or not tests.rstrip().endswith('OK'):
        raise ValueError('FINAL_TEST_LOG_NOT_PASSED')
    receipt = {'schema': 'controlled-launcher-integration-final-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'trusted_offline_integration_passed_participant_launch_blocked',
        'test_count': 32, 'tests_passed': True, 'tests_log_sha256': sha(ROOT / 'reports/tests-final-v2.log'),
        'build_receipt_sha256': sha(ROOT / 'reports/BUILD-RECEIPT.json'),
        'adapter_source_sha256': sha(ROOT / 'src/integration.py'),
        'retained_runs': versions, 'retained_attempts_total': sum(x['recorded_attempts'] for x in versions),
        'retained_assignment_total': sum(x['assigned_episodes'] for x in versions),
        'retained_status_counts_including_not_started': dict(totals),
        'denominator_scope': 'both retained integration runs only; repeated engineering controls, not scientific trials; transient unit tests counted separately',
        'provider_calls': 0, 'participant_calls': 0, 'native_solver_calls': 0,
        'real_pi_sdk_used': True, 'live_launch_allowed': False,
        'qualified_development_tasks': '0/2',
        'source_verification': verify_sources(),
        'sealed_inputs_edited': False, 'git_commits': 0, 'git_pushes': 0,
        'claim_boundary': final['claim_boundary'],
        'limitations': ['trusted fixtures are not participant isolation', 'no actual participant-authored H1',
            'legacy service has no new magnetic task route', 'no approved model or budget',
            'no full application init or monorepo regression', 'no qualified native reference',
            'all historical and H-loop scientific costs remain unestablished']}
    write_once(ROOT / 'FINAL-RECEIPT.json', receipt)
    files = {}
    links = {}
    for path in sorted(ROOT.rglob('*')):
        relative = str(path.relative_to(ROOT))
        if path.is_symlink():
            links[relative] = str(path.readlink())
        elif path.is_file() and relative not in {'FILE-MANIFEST.json'}:
            files[relative] = {'sha256': sha(path), 'bytes': path.stat().st_size}
    write_once(ROOT / 'FILE-MANIFEST.json', {'schema': 'controlled-launcher-delivery-manifest-v1',
        'files': files, 'external_read_only_symlinks': links,
        'portability': 'Requires the pinned restored Pi dependency tree; no dependency installation included.'})
    print({'receipt_sha256': sha(ROOT / 'FINAL-RECEIPT.json'),
        'manifest_sha256': sha(ROOT / 'FILE-MANIFEST.json'), 'files': len(files), 'symlinks': len(links)})

if __name__ == '__main__':
    finish()
