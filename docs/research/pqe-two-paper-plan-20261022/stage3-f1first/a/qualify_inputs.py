"""Exactly three frozen private initial executions; no search or retry.

The unchanged current engineering consumer and evaluator receive the complete
prospectively frozen private Tasks. The old shared Task registry is not edited.
Only private canonical raw files are saved; no model/native calls are made.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import signal
import sqlite3
import time

HERE = Path(__file__).resolve().parent
PLAN = HERE.parents[1]
ROOT = PLAN.parents[2]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
PRIVATE = CAN / 'studies/pqe20261022/f1first/private'
SRC = CAN / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    path.chmod(0o444)


def usage_gate():
    from bfworld.agentlab import historical_usage as authority
    protocol = read(CAN / 'studies/pqe20261022/shared/e2dev-protocol.json')
    database = Path(protocol['provider_database'])
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        row = db.execute('SELECT * FROM model_requests WHERE id=?', (authority.REQUEST_ID,)).fetchone()
        policy = db.execute('SELECT * FROM historical_usage_exceptions WHERE id=?', (authority.AMENDMENT_ID,)).fetchone()
        assert row and authority.identity(dict(row)) == authority.ORIGINAL_ROW_HASH, 'ORIGINAL_R11_CHANGED_STOP'
        assert policy and authority.valid_authority(json.loads(policy['authorization'])), 'R11_EXACT_AMENDMENT_NOT_LOADED'
        unknown = [dict(x) for x in db.execute("SELECT * FROM model_requests WHERE status='UNKNOWN' OR (status='SETTLED' AND usage IS NULL)")]
        blockers = [x['id'] for x in unknown if x['id'] != authority.REQUEST_ID or authority.identity(x) != authority.ORIGINAL_ROW_HASH]
        assert not blockers, 'NEW_UNKNOWN_USAGE_STOP:' + str(blockers)
        return {'database': str(database), 'new_missing_usage_or_UNKNOWN': blockers,
            'exact_R11_amendment_loaded': True, 'original_R11_row_sha256': authority.ORIGINAL_ROW_HASH,
            'original_R11_status': row['status'], 'original_R11_usage_is_null': row['usage'] is None,
            'original_R11_reserved_usd': row['reserved'], 'R11_retry_or_grant_or_settlement': False}


class InMemoryRaw:
    def __init__(self, raw):
        self.raw, self.reads = raw, 0

    def read_text(self):
        self.reads += 1
        assert self.reads == 1
        return json.dumps(self.raw, allow_nan=False)

    def __str__(self):
        return 'host-private-current-execution-in-memory; canonical path separately bound'


def main():
    registry_path = PRIVATE / 'registry.json'
    assert not registry_path.exists(), 'PRIVATE_INITIALS_ALREADY_RECORDED_NO_RERUN'
    freeze = read(PRIVATE / 'freeze.json')
    inputs_path = Path(freeze['input_catalog_path'])
    assert digest(inputs_path) == freeze['input_catalog_byte_sha256']
    tasks = read(inputs_path)
    assert all(digest(SRC / name) == h for name, h in freeze['scientific_sources'].items())
    free_before = shutil.disk_usage(ROOT).free
    assert free_before >= 10_100_000_000
    gate_before = usage_gate()
    from bfworld.agentlab.pqe20261022.adapter import validate_design, source_identity
    from bfworld.agentlab.pqe20261022.engineering import build_engineering_model, consume_engineering_model
    from bfworld.agentlab.pqe20261022.executor import execute_design
    from bfworld.agentlab.pqe20261022.evaluator import evaluate
    from bfworld.agentlab.pqe20261022.public_projection import project_result
    helper_path = CAN / 'studies/pqe20261022/engineering/stage2/native/review_coupled.py'
    spec = importlib.util.spec_from_file_location('f1_private_readback', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    began = time.monotonic()
    rows, registry_roles = [], {}
    aliases = {'selection': 'selection', 'confirmation-t1': 't1', 'confirmation-t2': 't2'}
    for role in ('selection', 'confirmation-t1', 'confirmation-t2'):
        task = tasks[role]
        binding = freeze['bindings'][role]
        design, problem, dt = task['initial_design'], task['initial_problem'], task['integration']['dt_s']
        assert identity(task) == binding['Task_sha256']
        assert identity(design) == binding['Design_sha256'] and identity(problem) == binding['Problem_sha256']
        assert identity({'Task': task, 'Design': design, 'Problem': problem, 'dt_s': dt,
                         'scientific_sources': freeze['scientific_sources']}) == binding['input_commitment_sha256']
        validate_design(task, design)
        assert set(problem['active_variables']) == set(task['design_domain']) and not problem['fixed_choices']
        model = build_engineering_model(task, design)
        consumed = consume_engineering_model(model, task, design)
        assert consumed['model_sha256'] == identity(model)
        assert all(digest(SRC / name) == h for name, h in freeze['scientific_sources'].items())
        usage_gate()
        directory = PRIVATE / 'initial' / aliases[role]
        assert not directory.exists(), 'ATTEMPT_EXISTS_NO_PRIVATE_INPUT_RETRY:' + role
        directory.mkdir(parents=True)
        save(directory / 'attempt.json', {'schema': 'pqe-f1first-private-initial-attempt-v1',
            'package': freeze['package'], 'role': role, 'at_utc': datetime.now(timezone.utc).isoformat(),
            'input_commitment_sha256': binding['input_commitment_sha256'], 'numerical_input_reserved': 1,
            'remaining_per_block_after_dispatch': 0, 'no_retry_or_replacement': True})
        def expired(signum, frame):
            raise TimeoutError('PRIVATE_QUALIFICATION_WALL_CAP_NO_RETRY')
        remaining = 120 - (time.monotonic() - began)
        assert remaining > 0, 'PRIVATE_QUALIFICATION_WALL_BUDGET_EXHAUSTED_STOP'
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(max(1, int(remaining)))
        started = time.monotonic()
        try:
            raw = execute_design(task, design, dt_s=dt, engineering_model=model)
        finally:
            signal.alarm(0)
        wall = time.monotonic() - started
        # Save the single canonical raw before any independent metadata audit.
        raw_path = directory / 'raw.json'
        save(raw_path, raw)
        assert identity({k: v for k, v in raw.items() if k != 'result_sha256'}) == raw['result_sha256']
        assert raw['task_sha256'] == identity(task) and raw['design_sha256'] == identity(design)
        assert raw['engineering_model'] == model and raw['engineering_model_sha256'] == identity(model)
        assessment = evaluate(task, design, raw)
        review = helper.review('f1-private-initial-' + role, InMemoryRaw(raw), task)
        independent = review['independent_service']
        assert independent['verdict'] == assessment['verdict'] and independent['failures'] == assessment['failures']
        assert independent['unknown'] == assessment['unknown'] and independent['matches'] == assessment['matches']
        assert independent['truth'] == assessment['truth'] and independent['missing'] == assessment['missed_event_ids']
        assert review['energy']['within_tolerance'] and review['force']['within_limit']
        sources = source_identity()
        assert {k: sources[k] for k in freeze['scientific_sources']} == freeze['scientific_sources']
        public = {'schema_version': 'pqe-public-result-v2', 'execution_status': raw['execution_status'],
            'task_id': task['task_id'], 'task_sha256': identity(task), 'input_sha256': identity(design),
            'design': design, 'problem': problem, 'sources': sources, 'model_valid': raw['model_valid'],
            'domain_errors': raw['domain_errors'], 'program_version': raw['program_version'],
            'engineering_model_sha256': raw['engineering_model_sha256'],
            'facts': {**{k: raw[k] for k in ('trace', 'activity', 'records', 'packets', 'energy', 'peak_handle_force_n', 'minimum_tx_terminal_v', 'program_state')},
                      'receiver_records': assessment['receiver_records']},
            'public_check': {'verdict': assessment['verdict'], 'failures': assessment['failures'],
                'unknown': assessment['unknown'], 'received_count': len(assessment['receiver_records'])},
            'usage': {'paid_model_requests': 0, 'numerical_inputs': 1, 'wall_s': wall},
            'result_sha256': raw['result_sha256']}
        public = project_result(public)
        public_path = directory / 'public-result.json'
        save(public_path, public)
        save(directory / 'assessment.json', assessment)
        legal = raw['model_valid'] and not raw['domain_errors'] and raw['execution_status'] == 'COMPLETE'
        row = {'role': role, 'status': 'INITIAL_VALID_COMPLETE' if legal else 'INITIAL_MODEL_DOMAIN_OR_EXECUTION_UNKNOWN',
            'visibility': 'HOST_PRIVATE_NOT_FORMATION', 'input_commitment_sha256': binding['input_commitment_sha256'],
            'raw_path': str(raw_path), 'raw_byte_sha256': digest(raw_path), 'raw_result_sha256': raw['result_sha256'],
            'model_sha256': raw['engineering_model_sha256'], 'model_valid': raw['model_valid'], 'domain_errors': raw['domain_errors'],
            'execution_status': raw['execution_status'], 'wall_s': wall, 'initial_verdict': independent['verdict'],
            'event_truth_count': len(independent['truth']), 'independent_service': independent,
            'independent_crc_commit_energy_force_checks': {'received_unique': review['unique_received_count'],
                'all_commit_durations': review['state']['all_commit_and_duration_checks'],
                'final_RAM_NVM_reconstructed': review['state']['final_RAM_NVM_reconstructed'],
                'energy_closure': review['energy']['within_tolerance'], 'force_limit': review['force']['within_limit']},
            'T2_no_change_label': ('ESTABLISHED_FOR_THIS_INITIAL_ONLY' if legal and independent['verdict'] == 'PASS' else 'WITHDRAWN_TASK_RETAINED_UNCHANGED') if role == 'confirmation-t2' else 'NOT_ASSIGNED',
            'scope': 'Single frozen initial legality/consumer/full-service readback; no repair/design search or domain feasibility conclusion.'}
        save(directory / 'qualification.json', row)
        rows.append(row)
        registry_roles[aliases[role]] = {'task_path': str(inputs_path), 'task_json_key': role,
            'task_file_sha256': digest(inputs_path), 'task_sha256': identity(task), 'design_sha256': identity(design),
            'problem_sha256': identity(problem), 'input_commitment_sha256': binding['input_commitment_sha256'],
            'initial_public_result_path': str(public_path), 'initial_public_result_sha256': digest(public_path),
            'initial_public_result_object_sha256': identity(public),
            'raw_path': str(raw_path), 'raw_file_sha256': digest(raw_path), 'raw_result_sha256': raw['result_sha256'],
            'dt_s': dt, 'qualification_status': row['status'],
            'qualification_path': str(directory / 'qualification.json'), 'qualification_file_sha256': digest(directory / 'qualification.json'),
            'exact_cache_key': identity({'task': task, 'design': design, 'dt': dt, 'scientific_source': freeze['scientific_sources']})}
    gate_after = usage_gate()
    assert all(digest(SRC / name) == h for name, h in freeze['scientific_sources'].items())
    assert digest(CAN / 'studies/pqe20261022/shared/door-tasks.json') == freeze['source_catalog_unchanged_byte_sha256']
    assert digest(CAN / 'studies/pqe20261022/shared/split-rules.json') == freeze['old_split_rules_unchanged_byte_sha256']
    registry = {'schema': 'pqe-f1first-private-registry-v1', 'package': freeze['package'],
        'visibility': 'S0_HOST_PRIVATE_NEVER_B_G_OR_FORMATION', 'at_utc': datetime.now(timezone.utc).isoformat(),
        'roles': registry_roles, 'scientific_sources': freeze['scientific_sources'],
        'freeze_path': str(PRIVATE / 'freeze.json'), 'freeze_file_sha256': digest(PRIVATE / 'freeze.json'),
        'Task_loading': "task=json.loads(Path(role['task_path']).read_text())[role['task_json_key']]; assert identity(task)==role['task_sha256']; design=task['initial_design']; problem=task['initial_problem']",
        'hash_convention': '*_file_sha256 and initial_public_result_sha256 are file-byte SHA256; task/design/problem/object/exact_cache_key use canonical JSON identity; raw_result_sha256 excludes the raw result_sha256 field.',
        'consumer_scope': 'Tasks passed directly to unchanged engineering.build/consume_engineering_model -> executor.execute_design -> evaluator.evaluate -> public_projection.project_result. Old global adapter Task registry is untouched; S0 may bind this private frozen registry in its thin host adapter.',
        'initial_reuse': 'Reuse these exact initial public results/keys for authorized solves; do not dispatch another initial numerical input.',
        'counts': {'private_new_numerical_inputs': 3, 'per_role': 1, 'native': 0, 'provider_requests': 0,
            'repair_or_parameter_scans': 0, 'target_replacements': 0, 'budget_remaining_for_S0_new_coupled_inputs': 78}}
    save(registry_path, registry)
    inventory = [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': digest(p)}
                 for directory in (PRIVATE, HERE) for p in sorted(directory.rglob('*')) if p.is_file()]
    size = sum(x['bytes'] for x in inventory)
    assert size < 25_000_000
    receipt = {'schema': 'pqe-f1first-a-initial-receipt-v1', 'package': freeze['package'], 'owner': 'campaign-a',
        'visibility': 'HOST_PRIVATE_CONTAINS_INITIAL_VERDICTS_NOT_FOR_FORMATION',
        'status': 'THREE_FROZEN_INPUTS_AND_LIMITED_INITIAL_CHECKS_COMPLETE; A_AWAITS_ACTUAL_SELECTION_CONFIRMATION',
        'at_utc': datetime.now(timezone.utc).isoformat(), 'registry_path': str(registry_path), 'registry_file_sha256': digest(registry_path),
        'rows': rows, 'counts': registry['counts'], 'scientific_sources_unchanged': True,
        'old_catalog_and_split_unchanged': True, 'new_UNKNOWN_usage_gate_before': gate_before,
        'new_UNKNOWN_usage_gate_after': gate_after,
        'resource': {'available_before_bytes': free_before, 'estimated_peak_additional_bytes': 100_000_000,
            'A_and_private_retained_cap_bytes': 25_000_000, 'retained_bytes_excluding_this_receipt': size,
            'available_after_bytes': shutil.disk_usage(ROOT).free, 'total_private_wall_s': time.monotonic() - began,
            'new_environments': 0, 'new_backups': 0, 'full_raw_files': 3, 'full_raw_copies': 0, 'workers': 0},
        'artifact_inventory_excluding_self': inventory,
        'next_A': 'Only after three actual selection and later confirmation episodes exist, independently review mechanism/service/scope and unintended interventions. Selection scope-review conditions.H1/H2/H4 will bind episode_result path/hash and unsupported_global_exclusions/erroneous_adoptions with evidence. No new H patch, qualification or target answer is supplied to G.'}
    save(HERE / 'A-INITIAL-RECEIPT.json', receipt)
    assert sum(p.stat().st_size for d in (PRIVATE, HERE) for p in d.rglob('*') if p.is_file()) < 25_000_000
    print(json.dumps({'status': 'THREE_PRIVATE_INITIAL_EXECUTIONS_COMPLETE_NO_ADDITIONAL_RUN_AUTHORIZED',
        'registry_path': str(registry_path), 'registry_file_sha256': digest(registry_path),
        'receipt_path': str(HERE / 'A-INITIAL-RECEIPT.json'), 'receipt_file_sha256': digest(HERE / 'A-INITIAL-RECEIPT.json'),
        'private_new_inputs': 3, 'provider_requests': 0, 'native': 0,
        'free_after_bytes': shutil.disk_usage(ROOT).free}, indent=2))


if __name__ == '__main__':
    main()
