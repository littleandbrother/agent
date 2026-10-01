"""Retain real trusted Pi activation/recovery artifacts; never dispatch models."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
import integration as i
from paths import ROOT, write_once, verify_sources, read, sha

def run(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('NEW_OUTPUT_REQUIRED')
    variants = [('h0-solve', 'h0', 'solve'), ('h0-improve', 'h0', 'improve'),
        ('manual-h1', 'h1-manual-fixture', 'improve'), ('rollback-h0', 'h0', 'improve'),
        ('failed-import', 'import-failure', 'improve'), ('failed-invoke', 'invoke-failure', 'improve'),
        ('failed-improver', 'improver-failure', 'improve'), ('failed-build', 'build-failure', 'improve'),
        ('timeout', 'timeout', 'improve'), ('recover-receipt', 'h0', 'improve')]
    assigned = [name for name, _, _ in variants] + ['never-started']
    book = i.AttemptBook(output, assigned, i.current_binding(), max_attempts=len(variants))
    receipts = {}
    for name, variant, mode in variants:
        receipt = i.run_trusted_fixture(book, name, name + '-a1', variant, mode,
            timeout=2 if variant == 'timeout' else 15, artifact_only=name == 'recover-receipt')
        if name == 'recover-receipt':
            receipt = book.recover(name + '-a1')
        receipts[name] = receipt
        print(json.dumps({'episode': name, 'status': receipt['status'], 'provider_calls': 0}), flush=True)
    try:
        i.run_trusted_fixture(book, 'failed-import', 'failed-import-a2')
    except i.BudgetStop:
        pass
    rollback = i.rollback_h0(Path(receipts['rollback-h0']['details']['harness_path']),
        Path(receipts['manual-h1']['details']['harness_path']), receipts['rollback-h0'])
    write_once(output / 'H0-ROLLBACK.json', rollback)
    readiness = i.live_readiness()
    write_once(output / 'LIVE-READINESS.json', readiness)
    summary = {'schema': 'controlled-launcher-integration-result-v1', 'source_verification': verify_sources(),
        'actual_pi_sdk_used': True, 'provider_calls': 0, 'participant_calls': 0,
        'native_solver_calls': 0, 'scientific_success_claimed': False,
        'controls': {key: value['status'] for key, value in receipts.items()},
        'all_attempt_ledger': book.summary(), 'rollback': rollback,
        'launch_blocked': True, 'qualified_tasks': readiness['qualified_tasks'],
        'claim_boundary': 'trusted offline integration with actual Pi runtime; no participant efficacy, H1 authorship, isolation qualification, native world execution, or scientific promotion'}
    write_once(output / 'RESULT.json', summary)
    return summary

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))
