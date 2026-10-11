#!/usr/bin/env python3
"""Seal an evidence-bounded closeout without model calls or native reruns."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import zipfile

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab.contracts import sealed, sha

OUT = APP / 'docs/agentlab/refactor-r3-r5-20261012'
OLD = APP / 'docs/agentlab/refactor-r0-r2-20261011'
CURRENT_ENV = OUT / 'environment-1791740435574814000'
FIRST = OUT / 'method-study-77a587a1bb6ee37dd97726d8'
CONFIRM = OUT / 'method-study-followup-d98c5124f7b02b89f532eea5'
A = OUT / 'method-study-finite-A-03e829fdf3861737fe38'
B = OUT / 'method-study-finite-B-134a541e8fa66a1c754c'
AUDIT = OUT / 'system-audit-1791740938815627000'


def read(path):
    return json.loads(path.read_text())


def freeze_executed_method_sources():
    semantics = APP / 'packages/python/bfworld/src/bfworld/agentlab/design_lab/method_study.py'
    for directory, filename in [(FIRST, 'run_method_study.py'), (CONFIRM, 'run_method_followup.py')]:
        protocol = read(directory / 'protocol.json')
        assert sha(semantics) == protocol['model_semantics'], 'EXECUTED_METHOD_SEMANTICS_DRIFT'
        source = APP / 'scripts/design_lab' / filename
        data = source.read_bytes()
        reconstruction = False
        if hashlib.sha256(data).hexdigest() != protocol['runner_sha256']:
            # Only the new descendant precondition was added after confirmation.
            # Recover old bytes, then verify against the original pre-run hash.
            text = data.decode()
            start = text.index("confirmation=OUT/'method-study-followup-")
            end = text.index('case_map=', start)
            data = (text[:start] + text[end:]).encode()
            reconstruction = True
        assert hashlib.sha256(data).hexdigest() == protocol['runner_sha256'], 'EXECUTED_RUNNER_NOT_RECOVERED'
        frozen = directory / 'frozen-controller'
        for path, contents in [(frozen / filename, data), (frozen / 'method_study.py', semantics.read_bytes())]:
            if path.exists():
                assert path.read_bytes() == contents
            else:
                path.write_bytes(contents)
        sealed(frozen / 'executed-python-recovery.json', {
            'schema_version': 'bf-executed-source-recovery-v1',
            'protocol_sha256': sha(directory / 'protocol.json'),
            'runner_sha256': protocol['runner_sha256'],
            'semantics_sha256': protocol['model_semantics'],
            'reconstructed_from_current_then_original_hash_verified': reconstruction,
            'models_dispatched': 0, 'native_solves': 0,
            'claim': 'Exact bytes match original pre-run hashes; not a repeat experiment.'})


def amendments():
    rows = [
        ('environment-1791737955447945000', 'INCOMPLETE', 'Initial slow PWL replay was stopped in its own qualification process. No final qualification; no product or Pi failure attribution.'),
        ('environment-1791738019954513000', 'FAILED_RETAINED', 'B reference failed because the public environment incorrectly required A diagnosis window length. B notification window corrected in subsequent environment; original failure retained.'),
        ('environment-1791738066130701000', 'WITHDRAWN', 'v2 leaked evaluator truth to participant and allowed participant-declared free stage current. Its PASS cannot qualify design or method comparison.'),
        ('environment-1791739329751894000', 'SUPERSEDED', 'v3 fixed truth/current, but host-only file I/O was not rejected and numerical receipt was not bound to the exact execution. Not current authority.'),
        ('environment-1791740348895775000', 'SUPERSEDED', 'Preliminary v4 lacked exact execution/trace binding in numeric acceptance. Later v4 qualification adds binding; these are different code hashes despite a shared version label.'),
        ('system-audit-1791739639072070000', 'WITHDRAWN_CHECKER_ERROR', 'Auditor read physical instead of physical_hash and incorrectly reported 0/10 stage deliveries. Corrected source binding audit reports 10/10 and 588 matching records. No Pi repair or model call caused this correction.'),
    ]
    records = []
    for name, status, reason in rows:
        directory = OUT / name
        files = {p.name: sha(p) for p in directory.iterdir() if p.is_file() and p.name in ('qualification.json', 'report.json')}
        records.append({'directory': name, 'status': status, 'reason': reason, 'retained_receipts': files})
    value = {'schema_version': 'bf-validity-amendments-v1', 'original_receipts_overwritten': False,
             'current_environment': {'path': str(CURRENT_ENV / 'qualification.json'), 'sha256': sha(CURRENT_ENV / 'qualification.json')},
             'current_audit': {'path': str(AUDIT / 'report.json'), 'sha256': sha(AUDIT / 'report.json')},
             'records': records,
             'other_retained_errors': ['Mach-O host object initially sent to ELF-only parser: local checker error, repaired with nm -u.',
                 'A first source-in-candidate call was silently ignored by common tool handler; first FAIL and eleven charges retained.',
                 'A postprocessor used status instead of scoped_status; recovery reads original evidence without rerunning.',
                 'Early method authorization/prefix/localhost containment errors occurred before paid dispatch.'],
             'models_dispatched': 0, 'native_solves': 0}
    sealed(OUT / 'validity-amendments.json', value)


def finite_delivery(directory, name):
    result = read(directory / 'result.json')
    assert result['scoped_passed'] and not result['full_product_passed'] and not result['physical_verified']
    source = read(directory / 'submitted-source.json')['program.c']
    for checkdir in ('independent-final', 'independent-variation'):
        if not (directory / checkdir).is_dir():
            # Older runner names are discovered by check.json; never invent a name.
            continue
        assert (directory / checkdir / 'program.c').read_text() == source
    files = {}
    for path in directory.rglob('*'):
        if path.is_file() and not path.is_symlink() and 'node_modules' not in path.parts:
            files[str(path.relative_to(directory))] = path
    for rel, path in files.items():
        if path.name == 'check.json' and rel.startswith('independent'):
            assert read(path)['scoped_status'] == 'PASS'
        if path.name == 'program.c' and rel.startswith('independent'):
            assert path.read_text() == source
    destination = OUT / 'deliveries'
    destination.mkdir(exist_ok=True)
    zip_path = destination / (name + '-F0-digital-design.zip')
    manifest = {'schema_version': 'bf-finite-delivery-v1', 'case': name, 'design_id': result['design_id'],
                'owner': result['owner'], 'scope': result['scope'], 'scoped_passed': True,
                'full_product_passed': False, 'physical_validation': 'NOT_TESTED',
                'files': {rel: sha(p) for rel, p in sorted(files.items())},
                'source_actor': 'Pi', 'Codex_participant_source_edits': 0,
                'model_and_solver_calls_during_packaging': 0}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    if zip_path.exists():
        raise ValueError('DELIVERY_ALREADY_EXISTS: inspect its immutable receipt instead of overwriting')
    with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('delivery-manifest.json', manifest_bytes)
        for rel, path in sorted(files.items()):
            archive.write(path, rel)
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
        assert archive.read('delivery-manifest.json') == manifest_bytes
        for rel, digest in manifest['files'].items():
            assert hashlib.sha256(archive.read(rel)).hexdigest() == digest
    receipt = {**manifest, 'zip_path': str(zip_path), 'zip_sha256': sha(zip_path),
               'zip_bytes': zip_path.stat().st_size, 'crc_and_all_member_sha_readback': True}
    sealed(destination / (name + '-delivery.json'), receipt)
    return receipt


def main():
    freeze_executed_method_sources()
    amendments()
    receipts = [finite_delivery(A, 'A'), finite_delivery(B, 'B')]
    first, confirmed = read(FIRST / 'comparison.json'), read(CONFIRM / 'comparison.json')
    full = OLD / 'verification/native-environment-1791741319469001000/report.json'
    assert full.is_file() and read(full)['passed'], 'WAIT_FOR_APPLICATION_INIT'
    audit = read(AUDIT / 'report.json')
    row_map = {}
    for directory in (FIRST, CONFIRM):
        for path in directory.glob('trials/*/result.json'):
            for row in read(path)['billing_rows']:
                row_map[row['id']] = row
    for directory in (A, B):
        for row in read(directory / 'result.json')['billing_rows']:
            row_map[row['id']] = row
    assert all(row['status'] == 'SETTLED' for row in row_map.values())
    statuses = Counter(g['status'] for p in audit['latest_papers'] for g in p['functional_gates'])
    closeout = {'schema_version': 'bf-r3-r5-bounded-closeout-v1', 'created': time.time(),
        'R3': {'finite_A_B_controls': 'PASS', 'full_exit': 'NOT_MET', 'actual_Pi_A_B_C_scoped': 'PASS',
               'remaining': ['calibrated mechanical/source and switching converter A/B', 'changed-load C recoupling', 'target peripheral and physical RF qualification']},
        'R4': {'actual_candidate_and_pairing_complete': True, 'candidate': first['decision']['candidate_id'],
               'first_limited_verdict': first['decision']['decision'], 'fresh_confirmation_verdict': confirmed['decision']['decision'],
               'production_adoption': False, 'correctness_gains': 0},
        'R5': {'descendant': 'BLOCKED_NO_CONFIRMED_PARENT', 'physical': 'NOT_TESTED', 'complete': False, 'RSI_proven': False},
        'actual_new_paid_requests': len(row_map), 'registered_charged_usd': sum(r['charged'] for r in row_map.values()),
        'original_ten': {'stage_delivery_passed': audit['stage_delivery_passed'],
             'full_digital_products_passed': audit['full_digital_products_passed'], 'functional_gates': dict(statuses),
             'registered_charged_usd': audit['registered_charged_usd_original_ten'],
             'unknown_rows': audit['unknown_rows_original_ten'], 'unknown_full_reserve_usd': audit['unknown_reserved_original_ten_usd']},
        'deliveries': [{'case': x['case'], 'path': x['zip_path'], 'sha256': x['zip_sha256']} for x in receipts],
        'application_full_init': {'path': str(full), 'sha256': sha(full), 'passed': True},
        'evidence': {str(p.relative_to(APP)): sha(p) for p in [CURRENT_ENV / 'qualification.json', FIRST / 'comparison.json', CONFIRM / 'comparison.json', AUDIT / 'report.json', OUT / 'R5-descendant-blocked.json', OUT / 'validity-amendments.json']},
        'models_or_native_solves_during_closeout': 0, 'old_D5_native_solves': 0,
        'claim': 'Separate finite engineering, method comparison, full product and physical states. No completion score or proven recursive improvement.'}
    sealed(OUT / 'closeout.json', closeout)
    print(json.dumps({'closeout': str(OUT / 'closeout.json'), 'actual_new_paid_requests': len(row_map), 'registered_charged_usd': closeout['registered_charged_usd'], 'deliveries': closeout['deliveries']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
