"""Prospective four-task construction; no solver, search, or result imports."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
PRIVATE = CAN / 'studies/pqe20261022/e2main/private'
SHARED = PRIVATE.parent / 'shared'
SRC = CAN / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022'
PACKAGE = 'BF-PQE-S3-E2MAIN-20261023-001'


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    path.chmod(0o444)


def segment(start, duration, a, b):
    return {'start_s': start, 'end_s': round(start + duration, 6), 'start_deg': a, 'end_deg': b}


def cycles(start, count, duration, dwell, maximum=90):
    result = []
    for index in range(count):
        at = start + index * 2 * (duration + dwell)
        result += [segment(round(at, 6), duration, 0, maximum),
                   segment(round(at + duration + dwell, 6), duration, maximum, 0)]
    return result


def main():
    assert not (PRIVATE / 'freeze.json').exists(), 'ALREADY_FROZEN_NO_REGENERATION'
    free = shutil.disk_usage(ROOT).free
    assert free >= 11_500_000_000, 'STORAGE_RESERVE_STOP'
    catalog_path = CAN / 'studies/pqe20261022/shared/door-tasks.json'
    catalog = json.loads(catalog_path.read_text())
    tasks, entries = {}, {}
    for role, family, template in [('d04', 'D04', 'DOOR-DEV-D04-v1'),
                                    ('d05', 'D05', 'DOOR-DEV-D04-v1'),
                                    ('d10', 'D10', 'DOOR-DEV-D10-v1'),
                                    ('d16', 'D16', 'DOOR-DEV-D04-v1')]:
        task = deepcopy(catalog[template])
        task.update(task_id='DOOR-E2MAIN-' + family + '-20261023-v1', family_id=family,
                    exposure='prospective-main-comparison; development-derived constructed apparatus; NOT unseen-family or held-out transfer')
        task['qualification_claim'] = 'Finite declared-model simulation only; one prospective initial check; no hardware or population loss-rate claim.'
        task['material_sources']['e2main_lineage'] = {
            'template_task_id': template, 'template_task_sha256': identity(catalog[template]),
            'known_exposure': 'D04/D10 apparatus and development failures exposed; D16 control family previously exposed in F1; new motion/configuration blocks fixed before results, not independent unseen families.',
            'generation': 'Explicit deterministic joint input values in freeze_inputs.py, no sampling, sweep, pre-solving, rejection, or post-result replacement.'}
        task['initial_problem']['assumptions'] += ['All methods may expand active variables and remove temporary fixed choices anywhere within the full public design_domain.']
        tasks[role] = task

    d04 = tasks['d04']
    d04['description'] = 'A reed installation chatters during short repeated cabinet openings. Record stable real transitions without duplicate reports or suppressing a genuine later opening/closing. Hardware thresholds and the full legal design domain are supplied; no repair setting is prescribed.'
    d04['sensor'].update(open_deg=55.0, closed_deg=35.0,
                        bounce_offsets_s=[0.0, .013, .027, .043, .067])
    d04['service'].update(open_deg=55.0, closed_deg=35.0)
    d04['motion'] = cycles(12, 2, .65, .08, 65) + cycles(24010, 2, .65, .08, 65) + cycles(70020, 2, .65, .08, 65)
    d04['initial']['capacitor_v'] = 2.6
    d04['initial_design'].update(capacitance_f=.0003, debounce_s=0.0)
    entries['d04'] = 'fixed-failure-entry; initial failure label conditional on the actual single initial check'

    d05 = tasks['d05']
    d05['description'] = 'The cabinet is now opened and closed continuously in two bursts. Determine whether every stable transition is retained and received on time under the supplied volatile queue, supply and transmission settings. Only the existing powered level-contact program and legal edits are available; there is no autonomous edge-capture buffer.'
    d05['motion'] = cycles(18, 5, .85, .09) + cycles(36110, 4, .85, .09)
    d05['sensor']['bounce_offsets_s'] = [0.0, .008, .016, .024, .032]
    d05['initial_design'].update(capacitance_f=.00012, esr_ohm=25.0, startup_v=2.5,
                                 brownout_v=1.9, tx_gate_v=2.4, debounce_s=.06,
                                 persistent_queue=False, retry_s=.08)
    entries['d05'] = 'operating-condition-change-entry; continuous cycling replaces sparse workload; no claimed failure before initial check'

    d10 = tasks['d10']
    d10['description'] = 'A user enlarged storage to 1000 uF and now asks whether reporting meets the same service deadline. The first opening has a slow early arc followed by a faster sweep, with short later cycles. The initial capacitor-only activity is a reversible diagnostic choice, not a user prohibition: every method may activate other legal design variables. No joint or structural repair is predeclared necessary.'
    d10['motion'] = [segment(44, .8, 0, 20), segment(44.8, .75, 20, 90),
                     segment(45.85, .95, 90, 0)] + cycles(22240, 2, .9, .16)
    entries['d10'] = 'user-design-entry; enlarged storage and reversible initial capacitor-only scope; not a gateway-window shift or old halfspeed M3'

    d16 = tasks['d16']
    d16['description'] = 'Check whether the current device already meets all declared service conditions; preserve a satisfactory design unless evidence justifies an edit. This is prospectively designated a no-change control, and the designation is withdrawn if its single initial check fails; the Task itself is never replaced.'
    d16['motion'] = cycles(9, 1, 1.2, 1.6) + cycles(21340, 1, 1.4, 1.8) + cycles(77500, 1, 1.25, 1.7)
    d16['sensor']['bounce_offsets_s'] = [0.0, .011, .022, .033, .044]
    d16['initial']['capacitor_v'] = 2.6
    d16['initial_design'].update(debounce_s=.07, persistent_queue=True)
    entries['d16'] = 'prospective-no-change-control; never counted as failure repair or transfer success'

    sources = {name: digest(SRC / name) for name in
               ('door_model.py', 'door_program.py', 'engineering.py', 'executor.py', 'evaluator.py')}
    for role, task in tasks.items():
        task['material_sources']['e2main_lineage']['entry_type'] = entries[role]
        previous_end, previous_angle = 0, task['initial']['angle_deg']
        for motion in task['motion']:
            assert motion['start_s'] >= previous_end and motion['start_deg'] == previous_angle
            assert abs((motion['end_deg'] - motion['start_deg']) / (motion['end_s'] - motion['start_s'])) <= 120
            previous_end, previous_angle = motion['end_s'], motion['end_deg']
    inputs = PRIVATE / 'inputs.json'
    save(inputs, tasks)
    bindings = {role: {'Task_sha256': identity(task), 'Design_sha256': identity(task['initial_design']),
                      'Problem_sha256': identity(task['initial_problem']),
                      'input_commitment_sha256': identity({'Task': task, 'Design': task['initial_design'],
                          'Problem': task['initial_problem'], 'dt_s': task['integration']['dt_s'], 'scientific_sources': sources})}
                for role, task in tasks.items()}
    freeze = {'schema': 'pqe-e2main-a-prospective-freeze-v1', 'package': PACKAGE,
              'at_utc': datetime.now(timezone.utc).isoformat(), 'owner': 'campaign-a',
              'input_catalog_path': str(inputs), 'input_catalog_byte_sha256': digest(inputs), 'bindings': bindings,
              'entry_types': entries, 'scientific_sources': sources,
              'source_catalog_path': str(catalog_path), 'source_catalog_sha256': digest(catalog_path),
              'resource': {'available_before_bytes': free, 'estimated_combined_peak_additional_bytes': 1_500_000_000,
                  'door_retained_cap_bytes': 400_000_000, 'lcpv_retained_cap_bytes': 100_000_000},
              'limits': {'initial_new_inputs': 4, 'per_task': 1, 'paid_requests': 0, 'native': 0,
                         'repair_scans': 0, 'replacement_tasks': 0, 'initial_wall_cap_s': 240},
              'decision_rule': 'Complete valid initial enters frozen matrix regardless of PASS/FAIL; invalid/unsupported is excluded with reason, without replacement. D16 control status conditional, task unchanged.',
              'claim_boundary': 'Development-derived finite four-task comparison; no unseen-family generalization, precomputed solution or hardware qualification.'}
    save(PRIVATE / 'freeze.json', freeze)
    save(SHARED / 'task-freeze-public.json', {'schema': 'pqe-e2main-public-task-freeze-v1', 'package': PACKAGE,
         'at_utc': freeze['at_utc'], 'input_catalog_sha256': digest(inputs), 'task_hashes': {r: identity(t) for r,t in tasks.items()},
         'entry_types': entries, 'exposure': 'Prospective instances of development-derived constructed apparatus, not unseen-family testing.',
         'generation': 'All four complete Task inputs fixed before initial checks; one initial each; no search or replacement.'})
    save(SHARED / 'task-public-materials.json', {'schema': 'pqe-e2main-public-materials-v1', 'package': PACKAGE,
         'hardware': 'Constructed cam/linear-generator, loaded capacitor/ESR, powered level-contact program, atomic SAVE/ACK, optional persistent FIFO, CRC sequence/direction radio frame; gateway arrival clock only.',
         'permissions': 'All methods have identical full design_domain and may reform initial Problem activity/fixed choices; Task, environment, external truth and service cannot be edited.',
         'source_scope': 'Reuse current five frozen scientific modules; constructed loads/kinematics, no calibrated product or <=1% population loss claim.',
         'availability': 'Full task material and legal facts are supplied identically through existing public_task projection. Private initial diagnoses, reference deductions, evaluator truth and hidden final results are excluded.',
         'no_extra_hardware': 'No unpowered event history, autonomous pulse capture, absolute clock, external energy or added buffer.'})
    print(json.dumps({'status': 'FOUR_TASKS_FROZEN_BEFORE_RESULTS', 'freeze_path': str(PRIVATE / 'freeze.json'),
                      'freeze_sha256': digest(PRIVATE / 'freeze.json'), 'free_before_bytes': free}))


if __name__ == '__main__':
    main()
