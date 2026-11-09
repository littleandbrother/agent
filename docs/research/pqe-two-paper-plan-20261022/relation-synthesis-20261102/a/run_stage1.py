"""BFA-100 A: exact designs, original M2r tasks/consumer/evaluator; no API."""
from pathlib import Path
import sys, json, gzip, hashlib, time, signal, os, traceback
from collections import Counter
from copy import deepcopy

A = Path(__file__).resolve().parent
R = A.parents[4]
BASE = A.parent.parent
OLD = BASE / 'partial-ancestor-validation'
sys.path.insert(0, str(R / 'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src'))

def read(p):
    with (gzip.open(p, 'rt') if str(p).endswith('.gz') else open(p)) as f:
        return json.load(f)

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, x): p.write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
def ref(p): return {'path': str(p.relative_to(R)), 'sha256': sha(p)}
def alarm(*_): raise TimeoutError('BFA100_A_PER_FULL_OR_ABSOLUTE_CAP')

def main():
    from bfworld.agentlab.pqe20261024debt import adapter, task as task_module, facts
    pre = read(A.parent / 's0/preflight.json')
    reg = read(A.parent / 'shared/registration.json')
    assert reg['package'] == 'BF-PQE-RELATION-SYNTHESIS-20261102-001'
    assert time.time() < pre['absolute_deadline_epoch']
    assert os.statvfs(R).f_bavail * os.statvfs(R).f_frsize >= pre['required_available_bytes']
    manifest_path = OLD / 'a/M2r/public-tasks-and-common-parent.json'
    callback_path = OLD / 's0/episodes/mechanism-G-271828/callbacks/12/callback-result.json'
    comparison_path = OLD / 's0/comparison-result.json'
    manifest, callback = read(manifest_path), read(callback_path)
    oldR = next(x for x in read(comparison_path)['rows'] if x['id'] == 'mechanism-R-314159')
    rows = manifest['rows']
    parent = deepcopy(rows[0]['common_parent_design'])
    low = deepcopy(parent)
    low.update(startup_v=1.9, persistent_queue=False, holding_component='off')
    exactG = deepcopy(callback['payload']['design'])
    oldfinal = oldR['final']['final_design']
    difference = {k: {'new': low.get(k), 'old_R_success': oldfinal.get(k)}
                  for k in sorted(set(low) | set(oldfinal)) if low.get(k) != oldfinal.get(k)}
    assert difference == {'persistent_queue': {'new': False, 'old_R_success': True}}
    sources = adapter.source_identity()
    assert sources == oldR['history'][-1]['members'][0]['sources'], 'FROZEN_ORIGINAL_SCIENCE_SOURCE_DRIFT'
    counter = {'schema': 'BFA100-A-resource-counter-v1', 'full_attempts': 0,
               'full_completed': 0, 'full_wall_s': 0.0, 'cheap_numeric': 0,
               'software_checks': 1, 'provider_requests': 0, 'rows': [],
               'caps': {'full': 6, 'per_full_s': 120, 'cheap': 32, 'software': 4},
               'absolute_deadline_epoch': pre['absolute_deadline_epoch']}
    inputs, statics = [], []
    (A / 'inputs').mkdir(exist_ok=False)
    for name, design in [('startup19_no_persistence_holder_off', low),
                         ('saved_G_callback12_untouched', exactG)]:
        for item in rows:
            assert item['common_parent_design'] == parent
            task = item['task']
            decision = {'actual_input': {'operation': 'edit', 'design_patch': deepcopy(design)}}
            inp = {'design_name': name, 'condition_id': item['condition_id'], 'task': task,
                   'parent_design': item['common_parent_design'], 'problem': item['common_problem'],
                   'design': design, 'decision': decision}
            path = A / 'inputs' / (name + '--' + item['condition_id'] + '.json')
            write(path, inp)
            entry = {**ref(path), 'design_name': name, 'condition_id': item['condition_id'],
                     'task_sha256': adapter.digest(task), 'design_sha256': adapter.digest(design)}
            before = set(task_module._STATIC_GEOMETRY_CACHE)
            try:
                prepared, _, _ = adapter.prepare(task, inp['parent_design'], inp['problem'], decision,
                    task_resolver=lambda tid: task if tid == task['task_id'] else None)
                assert prepared == design
                static = {'status': 'LEGAL', 'error': None}
            except ValueError as exc:
                static = {'status': 'ILLEGAL', 'error': str(exc)}
            misses = len(set(task_module._STATIC_GEOMETRY_CACHE) - before)
            counter['cheap_numeric'] += misses
            statics.append({**entry, **static, 'static_geometry_real_misses': misses})
            inputs.append(entry)
    freeze = {'schema': 'BFA100-A-stage1-frozen-v1', 'at_epoch': time.time(),
              'classification': 'PRIVATE_DEVELOPER_COUNTERFACTUALS', 'package': reg['package'],
              'original_inputs': [ref(manifest_path), ref(callback_path), ref(comparison_path)],
              'preflight': ref(A.parent / 's0/preflight.json'),
              'registration': ref(A.parent / 'shared/registration.json'),
              'runner': ref(Path(__file__)), 'sources': sources,
              'designs': {'startup19_no_persistence_holder_off': low, 'saved_G_callback12_untouched': exactG},
              'new_vs_old_R_success': difference,
              'old_R_success': {'id': oldR['id'], 'design': oldfinal,
                  'final_node_id': oldR['final']['final_node_id'],
                  'canonical_members': [m['canonical_public_path'] for m in oldR['history'][-1]['members']]},
              'inputs': inputs, 'static_results': statics,
              'claim_boundary': 'Fixed-design neighborhood only; no new model episode, no global necessity, no old outcome replacement. Static legality is distinct from dynamic model validity.'}
    write(A / 'STAGE1-INPUTS-FROZEN.json', freeze)
    write(A / 'counter.json', counter)
    signal.signal(signal.SIGALRM, alarm)
    for entry, static in zip(inputs, statics):
        if static['status'] != 'LEGAL':
            counter['rows'].append({**entry, 'status': 'STATIC_ILLEGAL_NOT_RUN', 'error': static['error']})
            write(A / 'counter.json', counter)
            continue
        assert adapter.source_identity() == sources
        assert sha(R / entry['path']) == entry['sha256']
        remaining = min(120.0, 3600 - counter['full_wall_s'], pre['absolute_deadline_epoch'] - time.time())
        assert remaining > 0 and counter['full_attempts'] < 6
        assert os.statvfs(R).f_bavail * os.statvfs(R).f_frsize >= pre['required_available_bytes']
        inp = read(R / entry['path'])
        task = inp['task']
        folder = A / 'runs' / (str(counter['full_attempts'] + 1).zfill(2) + '--' + entry['design_name'] + '--' + entry['condition_id'])
        folder.mkdir(parents=True, exist_ok=False)
        row = {**entry, 'status': 'RUNNING', 'folder': str(folder.relative_to(R)),
               'started_epoch': time.time(), 'wall_cap_s': remaining}
        counter['rows'].append(row)
        counter['full_attempts'] += 1
        write(A / 'counter.json', counter)
        cache_before = set(task_module._STATIC_GEOMETRY_CACHE)
        start = time.monotonic()
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            public = adapter.execute(task, inp['parent_design'], inp['problem'], inp['decision'], folder / 'result',
                task_resolver=lambda tid: task if tid == task['task_id'] else None)
            row['status'] = 'COMPLETE'
            counter['full_completed'] += 1
        except Exception as exc:
            row.update(status='TOOL_ERROR', error=str(exc))
            write(folder / 'tool-error.json', {'status': 'TOOL_ERROR', 'type': type(exc).__name__,
                'message': str(exc), 'diagnostic': getattr(exc, 'diagnostic', None),
                'traceback': traceback.format_exc(limit=8), 'scientific_verdict': 'NOT_ESTABLISHED', 'retry_authorized': False})
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            row['elapsed_s'] = time.monotonic() - start
            counter['full_wall_s'] += row['elapsed_s']
            misses = len(set(task_module._STATIC_GEOMETRY_CACHE) - cache_before)
            counter['cheap_numeric'] += misses
            row['static_geometry_real_misses'] = misses
        if row['status'] == 'COMPLETE':
            raw, ass = read(folder / 'result/raw.json.gz'), read(folder / 'result/assessment.json.gz')
            assert raw['design'] == inp['design'] and raw['task_sha256'] == adapter.digest(task)
            assert raw['result_sha256'] == public['result_sha256']
            assert adapter.source_identity() == sources
            counts = Counter(e['action'] for e in public.get('facts', {}).get('activity', []))
            write(folder / 'public-record-relations.json', facts.public_record_relations(public))
            pubfacts = public.get('facts', {})
            def keys_count(records):
                return dict(Counter(str((x.get('seq'), x.get('direction'))) for x in records if isinstance(x, dict)))
            row.update(model_valid=raw['model_valid'], domain_errors=raw['domain_errors'],
                verdict=ass['verdict'], failures=ass['failures'], unknown=ass['unknown'],
                activity_counts=dict(counts), stage_counts={'CAPTURE': counts['capture'], 'SAVE': counts['save_commit'],
                    'TX': counts['wire_complete'], 'RX': len(ass['receiver_records']), 'ACK': counts['ack_commit']},
                public_occurrence_keys={'saved': keys_count(pubfacts.get('records', [])),
                    'received': keys_count(pubfacts.get('receiver_records', [])),
                    'identity_scope': 'Numeric seq/direction are not globally unique across resets; occurrence counts only.'},
                deadline={'receive_deadline_s': task['service']['receive_deadline_s'],
                    'missed_or_late_count': len(ass['missed_event_ids']), 'truth_event_count_private_host_only': len(ass['truth'])},
                duplicate_wire_frames=len(ass['duplicate_wire_frames']), unmatched_records=len(ass['unmatched_records']),
                brownout_count=counts['brownout'], energy=raw['energy'],
                holding_loads_diagnostic_subset=raw.get('holding_loads'), peak_handle_force_n=raw['peak_handle_force_n'],
                mechanical_residual_j=ass['mechanical_residual_j'], storage_residual_j=ass['storage_residual_j'],
                energy_tolerance_j=ass['energy_tolerance_j'], physical_qualification=ass['physical_qualification'],
                loss_rate_statistical_claim=ass['loss_rate_statistical_claim'],
                artifacts=[ref(p) for p in sorted((folder / 'result').iterdir()) if p.is_file()])
        write(folder / 'summary.json', row)
        write(A / 'counter.json', counter)
        print(json.dumps({k: row.get(k) for k in ['design_name', 'condition_id', 'status', 'verdict', 'model_valid', 'stage_counts', 'elapsed_s']}), flush=True)
        if row['status'] != 'COMPLETE' or not row['model_valid']:
            break
    assert adapter.source_identity() == sources
    counter['software_checks'] = 2
    counter['free_bytes_after'] = os.statvfs(R).f_bavail * os.statvfs(R).f_frsize
    counter['retained_bytes_A'] = sum(p.stat().st_size for p in A.rglob('*') if p.is_file())
    counter['status'] = 'COMPLETE' if len(counter['rows']) == 6 else 'STOPPED_NO_RETRY'
    write(A / 'counter.json', counter)
    write(A / 'STAGE1-RESULT.json', {'schema': 'BFA100-A-exact-counterfactual-result-v1', 'status': counter['status'],
        'freeze': ref(A / 'STAGE1-INPUTS-FROZEN.json'), 'counter': ref(A / 'counter.json'), 'rows': counter['rows'],
        'new_vs_old_R_success': difference, 'new_model_requests': 0, 'old_tool_cap_result_unchanged': True,
        'scope': 'Fixed-design neighborhood only; original full consumer/evaluator/service/domain unchanged.'})
    print(json.dumps({'status': counter['status'], 'full': counter['full_attempts'], 'wall_s': counter['full_wall_s'],
        'cheap': counter['cheap_numeric'], 'software_checks': counter['software_checks']}), flush=True)

if __name__ == '__main__': main()
