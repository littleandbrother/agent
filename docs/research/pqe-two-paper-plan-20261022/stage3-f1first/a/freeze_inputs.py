"""One prospective host-private generation; no apparatus or model call.

Seed, field mapping and all roles are committed before any outcome. All three
inputs are frozen together. Never select/reseed/replace using any result.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import secrets
import shutil

HERE = Path(__file__).resolve().parent
PLAN = HERE.parents[1]
ROOT = PLAN.parents[2]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
PRIVATE = CAN / 'studies/pqe20261022/f1first/private'
SHARED = PRIVATE.parent / 'shared'
SRC = CAN / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022'
PACKAGE = 'BF-PQE-S3-F1FIRST-20261023-001'
GENERATOR = 'pqe-f1first-grouped-door-blocks-v1'
SCIENCE = ('door_model.py', 'door_program.py', 'engineering.py', 'executor.py', 'evaluator.py')


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    path.chmod(0o444)


def normalized_block(task, scientific_sources):
    origin = task['motion'][0]['start_s']
    return {
        'science': scientific_sources, 'components': task['components'],
        'motion_shape_and_relative_schedule': [{**s, 'start_s': round(s['start_s'] - origin, 6),
                                                'end_s': round(s['end_s'] - origin, 6)} for s in task['motion']],
        'sensor': task['sensor'], 'initial': task['initial'],
        'state_retention': task['initial_design']['persistent_queue'],
        'gateway_windows': task['gateway_windows'], 'service': task['service'],
        'legal_domain': task['design_domain'],
    }


def main():
    assert not (PRIVATE / 'freeze.json').exists(), 'FROZEN_INPUTS_EXIST_NO_REGENERATION'
    assert not (PRIVATE / 'pre-generation.json').exists(), 'SEED_ALREADY_COMMITTED_NO_RESEED'
    free = shutil.disk_usage(ROOT).free
    assert free >= 10_100_000_000
    sources = {name: digest(SRC / name) for name in SCIENCE}
    catalog_path = CAN / 'studies/pqe20261022/shared/door-tasks.json'
    split_path = CAN / 'studies/pqe20261022/shared/split-rules.json'
    old = read(catalog_path)
    base = old['DOOR-DEV-D04-v1']
    families_path = CAN / 'studies/pqe20261022/shared/task-families.json'
    families = {x['id']: x for x in read(families_path)}
    seed = secrets.token_hex(32)
    # A whole joint motion/bounce/initial/state block has one indivisible role.
    rules = {
        'field_stream': 'u=int(first16hex(sha256(generator|private-seed|family|block-id|field)),16)/2**64',
        'rounding': 'Continuous seconds/angles rounded to6 decimal places; schedule anchors rounded down to integer seconds.',
        'motion_construction': 'Three open-close cycles, each at its own anchor; angle-continuous closed-to-open-to-closed segments; closing starts after the declared dwell. No global clock/gateway translation counts as independent.',
        'selection': {'family': 'D06', 'block_id': 'D06-long-idle-joint-state-001',
            'first_start_s': [28800, 32400], 'second_start_s': [47000, 49000], 'third_start_s': [73000, 75000],
            'open_duration_s': [1.7, 2.1], 'close_duration_s': [1.25, 1.65], 'open_dwell_s': [0.4, 0.9],
            'closed_angle_deg': 2.0, 'open_angle_deg': [86.5, 89.5],
            'bounce_total_s': [0.05, 0.08], 'bounce_fractions': [0, 0.17, 0.39, 0.7, 1],
            'initial_capacitor_v': 1.1, 'design_changes_from_base': {'capacitance_f': 0.0003, 'debounce_s': 0.06, 'persistent_queue': False}},
        'confirmation-t1': {'family': 'D01', 'block_id': 'D01-cold-short-interval-joint-bounce-001',
            'first_start_s': [140, 260], 'second_start_s': [610, 950], 'third_start_s': [39000, 42000],
            'open_duration_s': [0.85, 1.18], 'close_duration_s': [0.9, 1.3], 'open_dwell_s': [0.14, 0.3],
            'closed_angle_deg': 0.0, 'open_angle_deg': [84.5, 88.5],
            'bounce_total_s': [0.09, 0.13], 'bounce_fractions': [0, 0.12, 0.28, 0.46, 0.63, 0.81, 1],
            'initial_capacitor_v': 0.0, 'design_changes_from_base': {'esr_ohm': 35.0, 'debounce_s': 0.02, 'persistent_queue': True}},
        'confirmation-t2': {'family': 'D16', 'block_id': 'D16-nominal-warm-independent-motion-001',
            'first_start_s': [14, 31], 'second_start_s': [18000, 21000], 'third_start_s': [58000, 61000],
            'open_duration_s': [1.1, 1.45], 'close_duration_s': [1.2, 1.55], 'open_dwell_s': [1.2, 2.1],
            'closed_angle_deg': 4.0, 'open_angle_deg': [86, 89],
            'bounce_total_s': [0.025, 0.045], 'bounce_fractions': [0, 0.19, 0.43, 0.72, 1],
            'initial_capacitor_v': 2.6, 'design_changes_from_base': {'debounce_s': 0.07, 'persistent_queue': True}},
        'invariants': '24h, existing2s receive/0.5N force/ordered exact stable-event/CRC/receiver services, full current legal Design domain, same program/source, same always-open gateway. Empty queue/counter0 and mechanical energy0 are retained because no unsupported initial firmware-state API is invented.',
        'outcome_policy': 'Exactly one private initial execution per frozen block, total3. No repair/search/reseed/replacement. T2 no-change label is provisional and revoked if its initial full-service check is not PASS; its input remains fixed.',
    }
    save(PRIVATE / 'pre-generation.json', {'schema': 'pqe-f1first-private-seed-plan-v1', 'package': PACKAGE,
        'visibility': 'HOST_PRIVATE_NEVER_G_OR_FORMATION', 'at_utc': now(), 'generator': GENERATOR,
        'seed': seed, 'seed_commitment': identity(seed), 'rules': rules, 'rules_sha256': identity(rules),
        'sources': sources, 'before_any_task_generation_or_result': True,
        'resources': {'available_before_bytes': free, 'estimated_peak_additional_bytes': 100_000_000,
            'A_retained_output_cap_bytes': 25_000_000, 'package_cap_bytes': 150_000_000,
            'output_directories': [str(PRIVATE), str(HERE)], 'private_execution_cap': 3, 'native_cap': 0,
            'provider_requests_cap': 0, 'private_qualification_wall_cap_s': 120}})

    def value(role, field, lo, hi, integer=False):
        spec = rules[role]
        wire = '|'.join((GENERATOR, seed, spec['family'], spec['block_id'], field))
        u = int(hashlib.sha256(wire.encode()).hexdigest()[:16], 16) / 2**64
        z = lo + (hi - lo) * u
        return math.floor(z) if integer else round(z, 6)

    inputs, bindings = {}, {}
    old_blocks = {identity(normalized_block(t, sources)) for t in old.values()}
    normalized_seen = set(old_blocks)
    for role in ('selection', 'confirmation-t1', 'confirmation-t2'):
        spec = rules[role]
        task = deepcopy(base)
        task['task_id'] = 'DOOR-F1FIRST-' + spec['family'] + '-' + role.upper() + '-v1'
        task['family_id'] = spec['family']
        task['exposure'] = 'host-private prospectively frozen F1-first role block; withheld from formation'
        task['description'] = families[spec['family']]['user_request'] + ' Evaluate all frozen services over the complete supplied24h motion; current observations determine whether edits are warranted.'
        task['initial']['angle_deg'] = spec['closed_angle_deg']
        task['initial']['capacitor_v'] = spec['initial_capacitor_v']
        task['initial_design'].update(spec['design_changes_from_base'])
        task['motion'] = []
        for i, anchor in enumerate(('first_start_s', 'second_start_s', 'third_start_s')):
            start = value(role, anchor, *spec[anchor], integer=True)
            opening = value(role, f'open_duration_{i}', *spec['open_duration_s'])
            closing = value(role, f'close_duration_{i}', *spec['close_duration_s'])
            dwell = value(role, f'open_dwell_{i}', *spec['open_dwell_s'])
            angle = value(role, f'open_angle_{i}', *spec['open_angle_deg'])
            opened, close_start = round(start + opening, 6), round(start + opening + dwell, 6)
            task['motion'] += [{'start_s': float(start), 'end_s': opened, 'start_deg': spec['closed_angle_deg'], 'end_deg': angle},
                               {'start_s': close_start, 'end_s': round(close_start + closing, 6), 'start_deg': angle, 'end_deg': spec['closed_angle_deg']}]
        bounce = value(role, 'bounce_total', *spec['bounce_total_s'])
        task['sensor']['bounce_offsets_s'] = [round(bounce * f, 6) for f in spec['bounce_fractions']]
        task['material_sources']['prospective_generation'] = 'Outcome-blind joint block, version ' + GENERATOR + '; all motion/bounce/initial-state descendants keep one role.'
        assert task['service'] == base['service'] and task['design_domain'] == base['design_domain']
        assert task['components'] == base['components'] and task['gateway_windows'] == base['gateway_windows']
        last = 0.0
        angle = task['initial']['angle_deg']
        for segment in task['motion']:
            assert last <= segment['start_s'] < segment['end_s'] <= task['duration_s']
            assert segment['start_deg'] == angle and 0 <= segment['end_deg'] <= 90
            assert abs(segment['end_deg'] - segment['start_deg']) / (segment['end_s'] - segment['start_s']) <= 120
            last, angle = segment['end_s'], segment['end_deg']
        block_sha = identity(normalized_block(task, sources))
        assert block_sha not in normalized_seen, 'REPEATED_NORMALIZED_BLOCK_REJECT_NO_RESEED'
        normalized_seen.add(block_sha)
        context = {'Task': task, 'Design': task['initial_design'], 'Problem': task['initial_problem'],
                   'dt_s': task['integration']['dt_s'], 'scientific_sources': sources}
        inputs[role] = task
        bindings[role] = {'family': spec['family'], 'block_id': spec['block_id'], 'task_id': task['task_id'],
            'role': role, 'Task_sha256': identity(task), 'Design_sha256': identity(task['initial_design']),
            'Problem_sha256': identity(task['initial_problem']), 'input_commitment_sha256': identity(context),
            'normalized_joint_block_sha256': block_sha, 'source_model_sha256': identity(sources),
            'service_sha256': identity(task['service']), 'design_domain_sha256': identity(task['design_domain']),
            'shape_not_just_clock_or_gateway_shift': True, 'qualification_results_seen_before_freeze': 0}
    save(PRIVATE / 'inputs.json', inputs)
    freeze = {'schema': 'pqe-f1first-private-input-freeze-v1', 'package': PACKAGE, 'owner': 'campaign-a',
        'visibility': 'HOST_PRIVATE_NEVER_G_OR_FORMATION', 'at_utc': now(), 'status': 'ALL_THREE_INPUTS_FROZEN_BEFORE_RESULTS',
        'generator': GENERATOR, 'seed_plan_path': str(PRIVATE / 'pre-generation.json'),
        'seed_plan_byte_sha256': digest(PRIVATE / 'pre-generation.json'),
        'input_catalog_path': str(PRIVATE / 'inputs.json'), 'input_catalog_byte_sha256': digest(PRIVATE / 'inputs.json'),
        'bindings': bindings, 'scientific_sources': sources,
        'source_catalog_unchanged_byte_sha256': digest(catalog_path), 'old_split_rules_unchanged_byte_sha256': digest(split_path),
        'role_partition_independence': 'All normalized whole joint blocks differ from every existing current-source catalog block and one another after removing absolute first-motion time. Same frozen scientific model is intentionally shared.',
        'initial_state_scope': 'Only actual executor-supported initial capacitor voltage/door angle plus real persistent_queue Design differ. Initial logical state0/empty queue/counter0/mechanical energy0 remain canonical; no free initial record or unpowered clock is inserted.',
        'execution_permission': {'private_inputs': 3, 'per_block': 1, 'native': 0, 'provider': 0, 'repair_or_replacement': False,
            'T2_control_label': 'PROVISIONAL_UNTIL_ONE_PRIVATE_INITIAL_FULL_SERVICE_CHECK'}}
    save(PRIVATE / 'freeze.json', freeze)
    public = {'schema': 'pqe-f1first-public-role-freeze-v1', 'package': PACKAGE,
        'status': 'THREE_INPUT_BLOCKS_FROZEN_BEFORE_FORMATION_AND_ANY_RESULT', 'at_utc': freeze['at_utc'],
        'domain': 'DOOR, current fixed computational cam/source/program/receiver apparatus; complete24h service and unchanged legal Design domain.',
        'roles': [{k: bindings[role][k] for k in ('role', 'family', 'input_commitment_sha256', 'normalized_joint_block_sha256',
                                                'source_model_sha256', 'service_sha256', 'design_domain_sha256')}
                  for role in ('selection', 'confirmation-t1', 'confirmation-t2')],
        'generator_commitment_sha256': identity({'version': GENERATOR, 'seed_commitment': identity(seed), 'rules_sha256': identity(rules)}),
        'visibility': 'Role/domain and opaque commitments only; no target Task, Design, initial/result, expected label, correct parameters or private paths.',
        'role_access': 'Formation sees none of the concrete selection/confirmation instances or results. Selected frozen methods see selection at its authorized solve; confirmation starts only after adoption and H1/H2/H3/H4 freeze.',
        'independence_boundary': 'Prospective within-model pilot blocks, not final E2/E3 or statistical independent physical realizations.',
        'seed_timing_amendment': 'This workorder requires all three host-private inputs frozen before formation. Earlier split seed-after-H wording is superseded only for this pilot; seed/instances remain private and outcomes never choose replacements.'}
    save(SHARED / 'role-freeze-public.json', public)
    e2 = read(PLAN / 'stage3-e2dev/a/A-EPISODE-READBACK.json')
    amendment = {'schema': 'pqe-f1first-exposure-amendment-v1', 'package': PACKAGE, 'at_utc': now(),
        'append_only_amendment_to': {'path': str(split_path), 'byte_sha256': digest(split_path), 'original_file_modified': False},
        'exposure_rule': 'All actually exposed prior DOOR instances and their candidate inputs are development. Old role assignments do not restore unseen status.',
        'development_families_added_or_reaffirmed': ['D02', 'D10', 'D15'],
        'development_task_ids_added_or_reaffirmed': list(old),
        'all_E2_development_actions': [{'episode': c['episode'], 'task_id': c['task_id'],
            'input_hashes': [{'Design_sha256': identity(a['Design_after']), 'scientific_result_sha256': a['scientific_result_sha256'],
                              'execution_status': a['execution_status']} for a in c['actions']]} for c in e2['cells']],
        'M3_included': True, 'all_E2_initials_and_attempted_versions_development': True,
        'prior_R_A_reference_qualifications_remain_development': True,
        'no_new_private_results_or_review_answers_in_history': True,
        'new_role_commitments': public['roles'], 'old_history_not_overwritten': True,
        'future_final_E2_E3_LC_PV_LEAK_reserved': 'No fresh final-test input is disclosed or consumed by this pilot.'}
    save(SHARED / 'exposure-amendment.json', amendment)
    save(HERE / 'A-PROSPECTIVE.json', {'schema': 'pqe-f1first-a-prospective-v1', 'package': PACKAGE, 'owner': 'campaign-a',
        'at_utc': now(), 'status': 'FREEZE_COMPLETE_PRIVATE_INITIALS_NOT_EXECUTED',
        'hypothesis': 'Frozen independent grouped inputs allow the already authorized method-formation pilot to test actual future-task behavior without target leakage.',
        'falsifier': 'A duplicate normalized block, post-result role/value selection, target leakage, changed scientific semantics or false T2 no-change label invalidates the corresponding claim.',
        'public_role_freeze_path': str(SHARED / 'role-freeze-public.json'), 'public_role_freeze_sha256': digest(SHARED / 'role-freeze-public.json'),
        'exposure_amendment_path': str(SHARED / 'exposure-amendment.json'), 'exposure_amendment_sha256': digest(SHARED / 'exposure-amendment.json'),
        'host_private_freeze_path': str(PRIVATE / 'freeze.json'), 'host_private_freeze_sha256': digest(PRIVATE / 'freeze.json'),
        'resources': {'available_before_bytes': free, 'estimated_peak_additional_bytes': 100_000_000,
            'retained_cap_A_and_private_bytes': 25_000_000, 'total_package_retained_cap_bytes': 150_000_000,
            'A_provider_requests': 0, 'A_native_runs': 0, 'A_new_environments_or_backups': 0},
        'next': 'At most one private initial current-consumer execution per role; never solve/scan/replace. Then hand S0 private index and only public role commitments to B/G.'})
    print(json.dumps({'status': 'THREE_FROZEN_BEFORE_RESULTS', 'public_role_freeze_path': str(SHARED / 'role-freeze-public.json'),
        'public_role_freeze_sha256': digest(SHARED / 'role-freeze-public.json'),
        'exposure_amendment_sha256': digest(SHARED / 'exposure-amendment.json'),
        'host_private_freeze_path': str(PRIVATE / 'freeze.json'), 'host_private_freeze_sha256': digest(PRIVATE / 'freeze.json'),
        'free_after_bytes': shutil.disk_usage(ROOT).free}, indent=2))


if __name__ == '__main__':
    main()
