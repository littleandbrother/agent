"""Metadata-only E2 input/cache index and exact common Task projection.

No raw file is opened or copied. No solver/evaluator is executed.
"""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent
PLAN = STAGE.parent
ROOT = PLAN.parents[2]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'


def read(path):
    return json.loads(path.read_text())


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    proposal_file = HERE / 'INITIAL-CACHE-PROPOSAL.json'
    materials_file = CAN / 'studies/pqe20261022/shared/e2dev-public-materials.json'
    if proposal_file.exists() or materials_file.exists():
        raise SystemExit('ALREADY_PREPARED; do not overwrite frozen inputs or inspect raw')
    free = shutil.disk_usage(ROOT).free
    assert free >= 10_005_000_000
    prospective = read(HERE / 'A-PROSPECTIVE.json')
    tasks = read(CAN / 'studies/pqe20261022/shared/door-tasks.json')
    science = prospective['current_five_scientific_sources']
    task_ids = list(prospective['task_bindings'])
    for task_id in task_ids:
        assert identity(tasks[task_id]) == prospective['task_bindings'][task_id]['Task_sha256']
    engineering_receipt_path = PLAN / 'stage2-engineering/a/A-RECEIPT.json'
    engineering = {x['case']: x for x in read(engineering_receipt_path)['coupled_review']}
    d15_receipt_path = PLAN / 'stage2-d15/a/A-RECEIPT.json'
    d15 = read(d15_receipt_path)
    m3_receipt_path = PLAN / 'stage2-m3/a/A-RECEIPT.json'
    m3 = read(m3_receipt_path)

    def entry(label, task_id, source_dir, public_path, prior_path, prior_review, initial):
        task = tasks[task_id]
        source = PLAN / source_dir
        decision_path = source / 'decision.json'
        source_public_path = source / 'public-result.json'
        decision = read(decision_path)
        public = read(public_path)
        source_public = read(source_public_path)
        actual = decision['actual_design']
        assert public['design'] == source_public['design'] == actual == prior_review['design']
        assert public['task_sha256'] == source_public['task_sha256'] == decision['task_sha256'] == identity(task)
        assert public['result_sha256'] == source_public['result_sha256']
        assert prior_review['recorded_task_sha256'] == identity(task)
        assert prior_review['recorded_design_sha256'] == identity(actual)
        assert {k: decision['sources'].get(k) for k in science} == science
        assert {k: public['sources'].get(k) for k in science} == science
        assert decision['problem'] == source_public['problem'] == public['problem']
        assert public['public_check']['verdict'] == prior_review['independent_service']['verdict']
        if initial:
            assert actual == task['initial_design'] and public['problem'] == task['initial_problem']
        raw_path = source / 'raw.json'
        assert raw_path.exists()
        submitted = decision['decision']['actual_input']
        dt = submitted.get('dt_s', task['integration']['dt_s'])
        cache_key = identity({'task': task, 'design': actual, 'dt': dt, 'scientific_source': science})
        return {
            'entry_id': label, 'classification': 'EXACT_CURRENT_SHARED_INITIAL' if initial else 'EXACT_CURRENT_SCIENTIFIC_CACHE_ONLY',
            'eligibility': 'ELIGIBLE_ON_METADATA_AND_EXISTING_INDEPENDENT_READBACK',
            'task_id': task_id, 'task_sha256': identity(task), 'actual_design': actual,
            'design_sha256': identity(actual), 'source_problem_sha256': identity(public['problem']),
            'dt_s': dt, 'dt_provenance': 'Explicit decision dt_s' if 'dt_s' in submitted else 'No dt_s in original accepted action; exact adapter/executor uses this immutable Task.integration.dt_s default. No new raw read.',
            'scientific_sources': science, 'exact_cache_key': cache_key,
            'raw_path': str(raw_path), 'raw_reads_this_package': 0, 'raw_copies': 0,
            'source_decision_path': str(decision_path), 'source_decision_file_sha256': sha(decision_path),
            'source_public_path': str(source_public_path), 'source_public_file_sha256': sha(source_public_path),
            'public_path': str(public_path), 'public_file_sha256': sha(public_path),
            'source_result_sha256': public['result_sha256'],
            'engineering_model_sha256': public['engineering_model_sha256'],
            'program_version': public['program_version'], 'public_projection': public.get('public_projection'),
            'public_projection_requirement': 'Use existing project_result before any participant delivery; original older public source remains sealed.' if not public.get('public_projection') else 'Current public projection present; preserve original scientific result identity and reproject through the same existing boundary on access.',
            'prior_independent_receipt': str(prior_path), 'prior_case': prior_review['case'],
            'independent_service_verdict': prior_review['independent_service']['verdict'],
            'visibility': 'HOST_ONLY index. Only this task initial may be supplied as common initial observation. Success entries require autonomous exact participant submission first.',
        }

    initials = [
        entry('d15-initial', 'DOOR-DEV-D15-v2', 'stage2-engineering/s0/coupled/d15-initial',
              PLAN / 'stage2-d15/s0/initial/public-result.json', engineering_receipt_path, engineering['d15-initial'], True),
        entry('m3-initial', 'DOOR-DEV-D02-M3-v2', 'stage2-m3/s0/initial',
              PLAN / 'stage2-m3/s0/initial/public-result.json', m3_receipt_path, m3['shared_initial_review'], True),
    ]
    successes = [
        entry('d15-existing-exact-success', 'DOOR-DEV-D15-v2', 'stage2-d15/s0/episodes/d15-generic/actions/01',
              PLAN / 'stage2-d15/s0/episodes/d15-generic/actions/01/public-result.json', d15_receipt_path, d15['new_coupled_review'], False),
        entry('d07-existing-exact-success', 'DOOR-DEV-D07-v1', 'stage2-engineering/s0/coupled/nominal-debounce-70ms',
              PLAN / 'stage2-engineering/s0/coupled/nominal-debounce-70ms/public-result.json', engineering_receipt_path, engineering['nominal-debounce-70ms'], False),
    ]
    rejected = []
    for rel in ('s0/qualification-v1/d07-initial', 's0/qualification-v2/d07-initial',
                'stage2-pilot1/s0/episodes/d07-generic/actions/01'):
        d = PLAN / rel
        p = read(d / 'public-result.json')
        assert p['task_sha256'] == identity(tasks['DOOR-DEV-D07-v1'])
        assert p['design'] == tasks['DOOR-DEV-D07-v1']['initial_design']
        mismatches = {k: {'recorded': p.get('sources', {}).get(k), 'required': v}
                      for k, v in science.items() if p.get('sources', {}).get(k) != v}
        assert mismatches
        rejected.append({'task_id': 'DOOR-DEV-D07-v1', 'public_path': str(d / 'public-result.json'),
                         'raw_path': str(d / 'raw.json'), 'source_result_sha256': p['result_sha256'],
                         'Task_and_initial_Design_match': True, 'source_mismatches': mismatches,
                         'eligibility': 'NOT_CURRENT_CACHE_SOURCE_MISMATCH', 'raw_reads': 0,
                         'old_status': 'Historical only; no claim that TX failure persists under current DoorProgram.'})

    # Pure public Task projections. No Result or cache entry is inserted here.
    sys.path.insert(0, str(CAN / 'packages/python/bfworld/src'))
    from bfworld.agentlab.pqe20261022 import adapter, pilot
    materials = {task_id: pilot.public_task(adapter.load_task(task_id)) for task_id in task_ids}
    for task_id, material in materials.items():
        assert material['design_domain'] == tasks[task_id]['design_domain']
        assert material['service'] == tasks[task_id]['service']
        assert material['components'] == tasks[task_id]['components']
        assert material['motion'] == tasks[task_id]['motion']
    assert materials['DOOR-DEV-D02-M3-v2']['public_inputs']['source_envelope'] == tasks['DOOR-DEV-D02-M3-v2']['public_inputs']['source_envelope']
    with materials_file.open('x') as f:
        f.write(json.dumps(materials, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    assert read(materials_file) == materials
    proposal = {
        'schema_version': 'pqe-e2dev-initial-cache-proposal-v1', 'package': prospective['package'],
        'feature': prospective['feature'], 'owner': 'campaign-a', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'READY_TWO_EXACT_INITIALS_ONE_CURRENT_INITIAL_REQUIRED', 'audience': 'HOST_ONLY',
        'prospective_path': str(HERE / 'A-PROSPECTIVE.json'),
        'prospective_file_sha256': sha(HERE / 'A-PROSPECTIVE.json'),
        'current_Task_bindings': prospective['task_bindings'],
        'current_five_scientific_sources_verified_in_prospective': science,
        'exact_initial_entries': initials, 'exact_success_cache_entries': successes,
        'rejected_old_initial_entries': rejected,
        'new_initial_required': [{'task_id': 'DOOR-DEV-D07-v1',
                                 'task_sha256': identity(tasks['DOOR-DEV-D07-v1']),
                                 'initial_design_sha256': identity(tasks['DOOR-DEV-D07-v1']['initial_design']),
                                 'initial_problem_sha256': identity(tasks['DOOR-DEV-D07-v1']['initial_problem']),
                                 'dt_s': tasks['DOOR-DEV-D07-v1']['integration']['dt_s'],
                                 'count': 1, 'executor_owner': 'campaign-s0',
                                 'reason': 'Existing same-Task initial artifacts use different/missing scientific source versions. Do not reuse as current or infer current TX reset from them.',
                                 'after_result_rule': 'Apply the frozen current-source mechanism criterion. Report absent/changed mechanism without replacing or tuning the Task.'}],
        'mechanism_admission': {
            'DOOR-DEV-D15-v2': {'status': 'PRESENT_BY_EXISTING_CURRENT_INDEPENDENT_READBACK',
                               'initial_received': engineering['d15-initial']['unique_received_count'],
                               'different_SAVE_sequence_reuse': len(engineering['d15-initial']['state']['different_record_sequence_reuse']),
                               'same_record_retransmissions': len(engineering['d15-initial']['state']['same_record_retransmissions']),
                               'criterion_source': str(HERE / 'A-PROSPECTIVE.json')},
            'DOOR-DEV-D07-v1': {'status': 'PENDING_ONE_NECESSARY_CURRENT_INITIAL', 'joint_repair_required': 'NOT_ASSUMED'},
            'DOOR-DEV-D02-M3-v2': {'status': 'PRESENT_BY_EXISTING_CURRENT_INDEPENDENT_READBACK',
                                  'boot_count': m3['startup_observation']['boot_count'],
                                  'initial_service': m3['shared_initial_review']['independent_service']['verdict'],
                                  'qualification_reused': str(PLAN / 'stage2-m3/a/A-QUALIFICATION.json'),
                                  'full_legal_domain_service': 'UNKNOWN'},
        },
        'public_materials': {'path': str(materials_file), 'file_sha256': sha(materials_file),
                             'bytes': materials_file.stat().st_size, 'format': '{task_id:pilot.public_task(adapter.load_task(task_id))}',
                             'projection_calls': len(task_ids), 'JSON_readback_equal': True,
                             'same_materials_for_all_four_conditions': True,
                             'cache_entries_or_prior_trajectories_inserted': False},
        'cache_contract': prospective['cache_policy'],
        'cache_alias_notes': ['D15 full_h prior success is an alias of the single generic raw; it is not another independent cache result.',
                              'Matching Design hashes across different full Tasks do not authorize cross-Task reuse.',
                              'Source public files lacking current projection may contain private host annotations and must never be served directly. Existing project_result is required; no new projection policy is proposed.'],
        'resources': {'available_before_bytes': free, 'estimated_peak_additional_bytes': 5_000_000,
                      'retained_output_cap_bytes': 1_000_000, 'output_directory': str(HERE),
                      'A_provider_requests': 0, 'A_scientific_executions': 0, 'A_qualification_reruns': 0,
                      'A_native_solver_runs': 0, 'A_parameter_scans': 0, 'A_raw_reads': 0, 'A_raw_copies': 0,
                      'A_new_environments': 0, 'A_new_backups': 0, 'A_workers': 0,
                      'necessary_S0_new_initials_proposed': 1, 'maximum_new_initials_authorized': 3,
                      'available_after_bytes': shutil.disk_usage(ROOT).free},
        'handoff': 'A first phase complete and idle. S0 owns one necessary current D07 initial, projection/cache serving integration and fixed twelve-cell execution; B owns methods and common recovery release. No extra qualification or repair search.',
    }
    with proposal_file.open('x') as f:
        f.write(json.dumps(proposal, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    assert read(proposal_file) == proposal
    print(json.dumps({'status': proposal['status'], 'proposal_sha256': sha(proposal_file),
                      'proposal_bytes': proposal_file.stat().st_size, 'materials': proposal['public_materials'],
                      'initial_keys': {x['entry_id']: x['exact_cache_key'] for x in initials},
                      'success_keys': {x['entry_id']: x['exact_cache_key'] for x in successes},
                      'free_bytes': shutil.disk_usage(ROOT).free}, indent=2))


if __name__ == '__main__':
    main()
