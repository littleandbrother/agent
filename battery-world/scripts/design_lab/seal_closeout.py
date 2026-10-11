#!/usr/bin/env python3
"""Seal read-only review facts; never promote old products or method efficacy."""
import hashlib
import json
from pathlib import Path
import time

APP = Path(__file__).resolve().parents[2]
OUT = APP / 'docs/agentlab/refactor-r0-r2-20261011'
def latest(pattern):
    paths = sorted(OUT.glob(pattern))
    if not paths:
        raise RuntimeError('EVIDENCE_MISSING:' + pattern)
    return paths[-1]
def read(path):
    return json.loads(path.read_text())
review = read(OUT / 'trial/independent-review.json')
preserved = read(latest('preservation-final-*.json'))
scoped = read(OUT / 'verification/run-1791735857347696000/report.json')
qualification = read(OUT / 'trial/environment-qualification.json')
live = read(latest('live-readback-*.json'))
recovery = read(OUT / 'trial/zero-model-recovery-1791736036726117000.json')
full_reports = [p for p in OUT.glob('verification/native-environment-*/report.json')
                if any(r['name'] == 'application-init' for r in read(p)['checks'])]
assert full_reports, 'APPLICATION_INIT_REPORT_MISSING'
app_report = sorted(full_reports)[-1]
assert review['submission']['acceptance']['scoped_passed']
assert preserved['passed'] and scoped['passed'] and qualification['passed'] and live['passed']
assert recovery['fee_operation_and_adopted_task_unchanged']
assert review['operator_design_actions'] == 0 and review['new_native_solver_calls'] == 0
root = APP.parent.parents[1]
features = read(root / 'feature_list.json')['features']
root_sha = hashlib.sha256(json.dumps(features, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
assert len(features) == 88 and root_sha == '16e3c12f9412dcb6e986bf668e384410e556743e5f024b5414f27fc3aa1302a1'
sources = [OUT / 'trial/independent-review.json', latest('preservation-final-*.json'),
    OUT / 'verification/run-1791735857347696000/report.json', OUT / 'trial/environment-qualification.json',
    latest('live-readback-*.json'), OUT / 'trial/zero-model-recovery-1791736036726117000.json',
    app_report, latest('environment-snapshot-*.json')]
receipt = {'schema_version': 'bf-R0-R2-finite-C-closeout-v1', 'time': time.time(),
    'scoped_completion': True, 'scope': qualification['scope'],
    'actual_paid_harness_id': review['harness_id'], 'zero_model_recovery_harness_id': recovery['harness_id'],
    'owner': review['owner'], 'design_id': review['design_id'],
    'submission_id': review['submission']['submission_id'],
    'independent_gates': review['submission']['acceptance']['gates'],
    'application_full_init_passed': read(app_report)['passed'],
    'root_full_init_passed': False, 'root_scientific_features_sha256': root_sha,
    'original_fee_rows_verified': preserved['original_owner_fee_rows_verified'],
    'physical': 'NOT_TESTED', 'full_product_passed': False, 'method_gain': 'NOT_EVALUATED',
    'teacher_design_actions': 0, 'new_D5_native_solver_calls': 0,
    'fees': review['fees'], 'main_ui_restored': True,
    'evidence': [{'path': str(p.relative_to(APP)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
    'remaining': ['changed-load recoupling R3', 'full MCU/SoC/S132 and board/RF', 'A/B environment qualification',
                  'ten original paper product closure', 'method paired evaluation and descendant recursion',
                  'full root frozen-evidence health', 'clean-room dependency reproduction'],
    'committed': False, 'pushed': False}
dest = OUT / ('closeout-' + str(time.time_ns()) + '.json')
dest.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
print(json.dumps({'scoped_completion': True, 'application_full_init_passed': receipt['application_full_init_passed'],
                  'receipt': str(dest)}))
