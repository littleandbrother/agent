"""Prospective DOOR/qualified LC definitions only: no simulation or provider."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
import json, hashlib, sys, os

A = Path(__file__).resolve().parent
R = A.parents[4]
BASE = A.parent.parent
sys.path.insert(0, str(R / 'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src'))

def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p): return {'path': str(Path(p).resolve()), 'sha256': sha(p)}
def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')

def main():
    from bfworld.agentlab.pqe20261024debt import adapter as door, task as dtask
    from bfworld.agentlab.pqe20261023bold import lc_adapter as lc
    out = A / 'stage3-host'
    assert not out.exists(), 'DO_NOT_REPLACE_FROZEN_TASKS'
    pre = read(A.parent / 's0/preflight.json')
    available = os.statvfs(R).f_bavail * os.statvfs(R).f_frsize
    assert available >= pre['required_available_bytes']
    prior = read(A / 'counter.json')
    assert prior['full_attempts'] == 6 and prior['software_checks'] == 2
    at = datetime.now(timezone.utc).isoformat()
    package = 'BF-PQE-RELATION-SYNTHESIS-20261102-001'
    rules = {'schema': 'BFA100-A-stage3-prospective-rules-v1', 'package': package, 'at': at,
        'selection': 'One natural rule per condition, frozen before stage2 outcome and stage3 dispatch. No sweep, method-outcome selection, private solution or replacement.',
        'visibility': 'A_S0_HOST_ONLY_UNTIL_B_STAGE2_ALGORITHM_FREEZE',
        'DOOR': [
            {'id': 'local-repair-control', 'starts_s': [61.0, 66.0, 71.0],
             'segments': [[0, 90, 1.5, .5], [90, 0, 1.5, 0]], 'gateway': [[0, 86400]],
             'role': 'local-repair/complexity-control',
             'mechanism': 'Three smooth complete warm cycles with ample stable endpoint holds and uninterrupted link; complex holder enabling is optional, never required by task construction.'},
            {'id': 'cold-contact-challenge', 'starts_s': [73.0, 211.0, 51017.0],
             'segments': [[0, 74, 1.1, 0], [74, 90, .18, .2], [90, 16, .95, 0], [16, 0, .18, 0]],
             'gateway': [[0, 86400]], 'role': 'natural cold/source/contact challenge',
             'mechanism': 'Widely separated complete cycles and split-speed strokes change when mechanical work reaches the store relative to stable contact events; continuous link isolates source/event timing.'},
            {'id': 'link-recovery-challenge', 'starts_s': [95.0, 101.0, 43019.0],
             'segments': [[0, 90, 1.25, .35], [90, 0, 1.25, 0]],
             'gateway': [[0, 95.9], [96.8, 101.9], [102.8, 43019.9], [43020.8, 86400]],
             'role': 'natural transport challenge',
             'mechanism': 'Three complete strokes with a finite 0.9s gateway outage around each opening; the unchanged two-second delivery deadline applies and no future gateway observation is added.'}],
        'LC': [
            {'id': 'local-repair-control', 'dark': [21600, 64800], 'gateway': [[0, 86400]],
             'recovery': 64800, 'light_blocks_s': [86400], 'lit_w_m2': [.6],
             'shade_blocks_s': [86400], 'shade': [.8], 'role': 'local-repair/complexity-control',
             'mechanism': 'Stable illumination outside the original twelve-hour dark interval and continuously available link remove shadow/outage interactions; strict energy, sample, timestamp and service requirements remain.'},
            {'id': 'light-before-link-challenge', 'dark': [23400, 66600],
             'gateway': [[0, 14400], [67800, 86400]], 'recovery': 67800,
             'light_blocks_s': [1200, 1800, 900], 'lit_w_m2': [.4, .8, .55],
             'shade_blocks_s': [2700, 1800], 'shade': [.8, .45], 'role': 'natural recovery/queue challenge',
             'mechanism': 'Light returns 1200s before connectivity after twelve hours of darkness, coupling powered sampling and accumulated FIFO delivery without changing scheduling or service deadlines.'},
            {'id': 'link-before-light-challenge', 'dark': [25200, 68400],
             'gateway': [[0, 18000], [66600, 86400]], 'recovery': 66600,
             'light_blocks_s': [1800, 1200, 600], 'lit_w_m2': [.7, .35, .9],
             'shade_blocks_s': [1800, 3600], 'shade': [.65, .9], 'role': 'natural retained-energy challenge',
             'mechanism': 'Connectivity returns 1800s before the twelve-hour darkness ends, so any recovery must use retained stored energy; no new storage/RTC or policy branch is introduced.'}],
        'initials': 'Same original task-module default DOOR design in all DOOR conditions; original qualified LC flat default in all LC conditions. No engineering winner. Initial PASS remains a correct-stop control.',
        'initial_dispatch': {'owner': 'campaign-s0', 'cap_each': 1, 'cap_total': 6, 'A_new_full': 0},
        'evaluation': 'One whole design must pass all three complete original service conjunctions; no cross-design splicing. Six candidate slots are additional to common initial; exact reuse consumes its candidate/evaluation slot.',
        'complexity': 'Report actual edited fields, enabled components, source area, storage, and measured load/energy separately; no invented weighted score.',
        'unexpressible_LC': 'Return NOT_RUN_INTERFACE_GAP with exact missing original interface; do not substitute DOOR, invent platform/model or change semantics.',
        'claim_boundary': 'Finite constructed two-family/two-seed comparison only; not an official benchmark, physical or unseen-model qualification.'}
    save(out / 'RULES.json', rules)
    freeze1 = read(A / 'STAGE1-INPUTS-FROZEN.json')
    assert door.source_identity() == freeze1['sources']
    devpath = BASE / 'lc-service-learning/a/DEVELOPMENT-TASKS.json'
    dev = read(devpath)['entries'][1]
    for item in [dev['public'], dev['host_task']]:
        assert sha(item['path']) == item['sha256'], 'ORIGINAL_LC_DEFINITION_CHANGED'
    public_base, host_base = read(dev['public']['path']), read(dev['host_task']['path'])
    qualified = read(BASE / 'lc-service-learning/a/ENGINEERING-FREEZE.json')
    lc_sources = lc.source_identity()
    assert lc_sources == qualified['scientific_identity'], 'ORIGINAL_QUALIFIED_LC_SOURCE_DRIFT'
    original_door = read(BASE / 'partial-ancestor-validation/a/M2r/public-tasks-and-common-parent.json')['rows'][0]['task']
    entries, checks = [], []
    cache_before = set(dtask._STATIC_GEOMETRY_CACHE)
    # One direct software check: original DOOR permissions, schedules and source.
    for config in rules['DOOR']:
        task = deepcopy(original_door)
        task.update(task_id='REL-SYNTH-DOOR-20261102:' + config['id'],
            family_id='REL-SYNTH-DOOR-20261102', condition_id=config['id'],
            description=config['mechanism'], exposure='Prospectively frozen before stage2 outcomes; new stage3 schedules.',
            motion=[], gateway_windows=deepcopy(config['gateway']), initial_design=deepcopy(dtask.DEFAULT_DESIGN))
        task.pop('selection_rule', None)
        task['initial_problem']['assumptions'] = ['Original continuous cam source, loads, dimensions, service, legal domain and existing firmware/holder contracts are fixed.']
        for start in config['starts_s']:
            t = start
            for lo, hi, duration, pause in config['segments']:
                task['motion'].append({'start_s': t, 'end_s': t + duration, 'start_deg': lo, 'end_deg': hi})
                t += duration + pause
        last_time, last_angle = 0.0, task['initial']['angle_deg']
        for segment in task['motion']:
            assert last_time <= segment['start_s'] < segment['end_s'] <= 86400
            assert last_angle == segment['start_deg']
            assert abs(segment['end_deg'] - segment['start_deg']) / (segment['end_s'] - segment['start_s']) <= 120
            last_time, last_angle = segment['end_s'], segment['end_deg']
        assert last_angle == 0
        for k in ['service', 'initial', 'components', 'geometry', 'design_domain', 'integration']:
            assert task[k] == original_door[k]
        door.validate_design(task, task['initial_design'])
        folder = out / 'DOOR' / config['id']
        save(folder / 'task.json', task)
        save(folder / 'initial-design.json', task['initial_design'])
        save(folder / 'initial-problem.json', task['initial_problem'])
        entries.append({'family': 'DOOR', 'condition_id': config['id'], 'task_id': task['task_id'],
            'role': config['role'], 'task': ref(folder / 'task.json'),
            'initial_design': ref(folder / 'initial-design.json'), 'initial_problem': ref(folder / 'initial-problem.json'),
            'consumer': 'bfworld.agentlab.pqe20261024debt.adapter.execute', 'initial_status': 'NOT_EXECUTED'})
    cheap = len(set(dtask._STATIC_GEOMETRY_CACHE) - cache_before)
    checks.append({'name': 'DOOR_original_source_domain_schedule_service_binding', 'status': 'PASS', 'new_full': 0, 'cheap_geometry_misses': cheap})
    def blocks(lo, hi, durations, values):
        rows, t, i = [], lo, 0
        while t < hi:
            end = min(t + durations[i % len(durations)], hi)
            rows.append([t, end, values[i % len(values)]])
            t, i = end, i + 1
        return rows
    # One direct software check: all LC original public/host bindings and readback.
    changed_service = {'dark_interval_s', 'recovery_at_s', 'recovery_old_history_deadline_s', 'history', 'new_sample_receive_scope'}
    for config in rules['LC']:
        host, public = deepcopy(host_base), deepcopy(public_base)
        lo, hi = config['dark']
        recovery = config['recovery']
        task_id = 'REL-SYNTH-LC-20261102:' + config['id']
        host.update(instance_id=task_id, allowed_for_learning=False, description=config['mechanism'])
        host['service'].update(dark_interval_s=[lo, hi], recovery_at_s=recovery,
            recovery_old_history_deadline_s=recovery + 120,
            history=f'All committed records retained; pre-recovery unacknowledged records delivered by {recovery + 120} in acquisition order without duplicate logical samples.',
            new_sample_receive_scope='Every sample acquired while gateway is available must be received within10s of acquisition; no frame-label exemption.')
        host['gateway_windows_s'] = deepcopy(config['gateway'])
        host['optical_environment']['irradiance_schedule_w_m2'] = blocks(0, lo, config['light_blocks_s'], config['lit_w_m2']) + [[lo, hi, 0.0]] + blocks(hi, 86400, config['light_blocks_s'], config['lit_w_m2'])
        host['optical_environment']['uniform_shading_transmission'] = blocks(0, lo, config['shade_blocks_s'], config['shade']) + [[lo, hi, .8]] + blocks(hi, 86400, config['shade_blocks_s'], config['shade'])
        host['next_owner'] = 'S0 common host; at most one initial, no replacement.'
        pt = public['Task']
        pt.update(task_id=task_id, instance_id=task_id, description=config['mechanism'], allowed_for_learning=False,
            exposure='Prospectively frozen before stage2 outcomes; new stage3 schedules.',
            service=deepcopy(host['service']), gateway_windows_s=deepcopy(host['gateway_windows_s']),
            optical_environment=deepcopy(host['optical_environment']))
        public['package'] = package
        task = lc.participant_task(public)
        task.update(family_id='REL-SYNTH-LC-20261102', condition_id=config['id'])
        # Original participant_task is authoritative; metadata lives in the manifest.
        task.pop('family_id'); task.pop('condition_id')
        inputs = lc.bind_inputs(task, public['Design'], {'public': public, 'host_task': host})
        assert inputs['Profile'] == public_base['Profile'] and public['Design'] == public_base['Design']
        assert pt['design_domain'] == public_base['Task']['design_domain']
        assert pt['fixed_program_semantics'] == public_base['Task']['fixed_program_semantics']
        assert host['initial'] == host_base['initial'] and hi - lo == 43200
        assert {k: v for k, v in host['service'].items() if k not in changed_service} == {k: v for k, v in host_base['service'].items() if k not in changed_service}
        for field in ['irradiance_schedule_w_m2', 'uniform_shading_transmission']:
            schedule = host['optical_environment'][field]
            assert schedule[0][0] == 0 and schedule[-1][1] == 86400
            for i, (start, end, value) in enumerate(schedule):
                assert start < end and value >= 0 and (i == 0 or schedule[i-1][1] == start)
                assert field != 'uniform_shading_transmission' or value <= 1
        folder = out / 'LC' / config['id']
        save(folder / 'task.json', task); save(folder / 'lc-public.json', public); save(folder / 'lc-host-task.json', host)
        save(folder / 'initial-design.json', public['Design']); save(folder / 'initial-problem.json', public['Problem'])
        entries.append({'family': 'LC', 'condition_id': config['id'], 'task_id': task_id, 'role': config['role'],
            'task': ref(folder / 'task.json'), 'lc_public': ref(folder / 'lc-public.json'), 'lc_host_task': ref(folder / 'lc-host-task.json'),
            'initial_design': ref(folder / 'initial-design.json'), 'initial_problem': ref(folder / 'initial-problem.json'),
            'consumer': 'bfworld.agentlab.pqe20261023bold.lc_adapter.execute', 'initial_status': 'NOT_EXECUTED'})
    for entry in entries:
        for item in entry.values():
            if isinstance(item, dict) and 'path' in item:
                assert sha(item['path']) == item['sha256']
        entry.update(initial_execution_owner='campaign-s0', initial_full_cap=1, no_replacement=True)
    assert door.source_identity() == freeze1['sources'] and lc.source_identity() == lc_sources
    checks.append({'name': 'LC_original_source_profile_service_host_public_binding_and_all_artifact_readback', 'status': 'PASS', 'new_full': 0, 'new_cheap_numeric': 0})
    save(out / 'CHECKS.json', {'checks': checks, 'software_checks': 2, 'cheap_numeric': cheap, 'full_calls': 0, 'model_calls': 0, 'meaning': 'Static permissions and binding only; service and dynamic model validity UNKNOWN until S0 execution.'})
    manifest = {'schema': 'BFA100-A-stage3-task-manifest-v1', 'package': package, 'at': at,
        'status': 'TWO_FAMILIES_THREE_CONDITIONS_SEALED_NO_INITIAL_EXECUTION',
        'visibility': rules['visibility'], 'rules': ref(out / 'RULES.json'), 'checks': ref(out / 'CHECKS.json'),
        'generator': ref(Path(__file__)), 'entries': entries,
        'consumer_sources': {'door': door.source_identity(), 'lc': lc_sources},
        'original_LC': {'development_index': ref(devpath), 'public': dev['public'], 'host_task': dev['host_task'], 'qualification': ref(BASE / 'lc-service-learning/a/ENGINEERING-FREEZE.json')},
        'original_DOOR': {'source': ref(BASE / 'partial-ancestor-validation/a/M2r/public-tasks-and-common-parent.json'), 'initial': 'pqe20261024debt.task.DEFAULT_DESIGN', 'consumer_scope': 'Existing common holder/firmware extension, original continuous mechanical source and original evaluator; no new source or policy branch.'},
        'dispatch': rules['initial_dispatch'], 'controller_fairness': rules['evaluation'],
        'A_stage3_new_full': 0, 'A_stage3_models': 0, 'no_private_solution_or_scan': True,
        'no_task_to_B_stage2': True, 'initial_pass_is_retained': True, 'initial_and_dynamic_results': 'UNKNOWN_NOT_EXECUTED',
        'storage': {'available_before_bytes': available, 'estimated_peak_additional_bytes': 1000000000, 'retained_cap_bytes_package': 150000000}}
    save(out / 'MANIFEST.json', manifest)
    prior['software_checks'] += 2
    prior['cheap_numeric'] += cheap
    prior['stage3_freeze'] = ref(out / 'MANIFEST.json')
    prior['stage3_new_full'] = 0
    prior['free_bytes_after'] = os.statvfs(R).f_bavail * os.statvfs(R).f_frsize
    prior['retained_bytes_A'] = sum(p.stat().st_size for p in A.rglob('*') if p.is_file())
    (A / 'counter.json').write_text(json.dumps(prior, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': manifest['status'], 'manifest': ref(out / 'MANIFEST.json'), 'A_total_full': 6,
        'A_total_full_wall_s': prior['full_wall_s'], 'A_total_cheap': prior['cheap_numeric'], 'A_total_software': prior['software_checks'],
        'models': 0, 'retained_bytes_A': prior['retained_bytes_A'], 'free_bytes': prior['free_bytes_after']}), flush=True)

if __name__ == '__main__': main()
