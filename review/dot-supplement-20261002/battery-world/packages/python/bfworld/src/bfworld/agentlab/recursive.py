"""Predeclared, small engineering controls for H=(solver P, improver U).

This controller does not author candidate source or read hidden transfer outcomes
into development history. All paid work uses the common external ledger.
"""
import argparse
import json
import time
from pathlib import Path
from . import study
from .launcher import HOME_ROOT, launch, filehash, world_binding
from .store import Store, identity
from .experiments import task, VARIANTS

ROOT = HOME_ROOT / 'studies' / 'recursive-v1'
DEV = ['dev-01', 'dev-02']
TRANSFER = ['transfer-01', 'transfer-02']


def read(path):
    return json.loads(Path(path).read_text())


def manifest(harness):
    return read(Path(harness) / 'manifest.json')


def immutable(path, value):
    path = Path(path)
    if path.exists() and read(path) != value:
        raise ValueError('FROZEN_RECURSIVE_PROTOCOL_DRIFT:' + path.name)
    if not path.exists():
        study.save(path, value)
    return value


def compatible(a, b):
    for key in ['world_binding', 'app_build_hash', 'pi_lock_hash', 'tools', 'thinking',
                'session_caps', 'resource_hashes', 'model']:
        if a[key] != b[key]:
            raise ValueError('RECURSIVE_BOUNDARY_MISMATCH:' + key)


def prepare(h0, h1):
    a, b = manifest(h0), manifest(h1)
    compatible(a, b)
    # Freeze selection before running any new recursive treatment. H0 data only;
    # source tasks are declared public development conditions, never transfer.
    full = [x for x in study.experience(['h0']) if x['metrics']['task_id'] in DEV]
    compact = [{k: v for k, v in x.items() if k != 'public_trace'} for x in full]
    immutable(ROOT / 'public-experience.json', full)
    immutable(ROOT / 'public-memory.json', compact)
    protocol = {
        'schema': 'bf-recursive-engineering-v1', 'h0': str(h0), 'h1': str(h1),
        'P0': a['loaded_modules']['solver'], 'P1': b['loaded_modules']['solver'],
        'U0': a['loaded_modules']['improver'], 'dev_tasks': DEV, 'repetitions': 1,
        'transfer_tasks': TRANSFER,
        'task_bindings': {t: identity({'public': task(t), 'conditions': VARIANTS[t]}) for t in DEV + TRANSFER},
        'world_binding': world_binding(), 'public_experience_hash': identity(full),
        'public_memory_hash': identity(compact), 'caps': a['session_caps'],
        'arms': {
            'fixed': 'H0; unchanged task prompt; same public history file accessible',
            'memory': 'H0; same public history also injected in task prompt',
            'fixed-u': 'P1,U0 from independently generated H1',
            'joint': 'P1,Ug from U-only independent modification of H1',
        },
        'meta': 'U0 and Ug receive identical P1, complete selected public traces, mutable solver.ts, tools and per-session caps. Evaluate descendants on the same two development tasks.',
        'transfer': 'Freeze descendants first; compare H0 and the Ug descendant on both untouched tasks. Do not return transfer outcomes to any improver.',
        'falsifier': 'Inactive manipulation, mismatched P/data/budget/boundary, no actual diff, no sealed submission, or no matched improvement defeats the corresponding claim.',
        'decision': 'Report all candidates, failures and costs; no automatic promotion or claim of statistical or recursive efficacy.',
        'extra_assets': {'new_trained_model': 'NOT_EVALUATED', 'STM32_nRF_firmware': 'NOT_EVALUATED',
                         'PV_piezo': 'NOT_EVALUATED', 'physical_assembly_CAD_PCB': 'NOT_EVALUATED',
                         'measurement_replay': 'NOT_EVALUATED', 'hardware_loop': 'NOT_EVALUATED'},
        'asset_reason': 'No authenticated asset package, physical setup or required compiler chain was supplied for these transfer domains.',
        'ledger': str(HOME_ROOT / 'state/workbench.sqlite'), 'paid_hard_cap_usd': 2.90,
        'budget_scope': 'All prior work and every development/generation/control/meta/transfer call counted; identical per-session caps do not imply equal realized spending.',
    }
    return immutable(ROOT / 'protocol.json', protocol)


def budget_guard():
    with Store(HOME_ROOT / 'state').connect() as db:
        rows = list(db.execute('SELECT status,charged,reserved FROM model_requests'))
    if any(r['status'] in ['UNKNOWN', 'DISPATCHED'] for r in rows):
        raise ValueError('RECURSIVE_USAGE_NOT_SETTLED')
    spent = sum(r['charged'] if r['status'] == 'SETTLED' else r['reserved'] for r in rows)
    # Dispatch guard leaves a small reserve; the provider enforces the actual
    # ledger cap atomically for every call (never the user's full USD 3).
    with Store(HOME_ROOT / 'state').connect() as db:
        cap=db.execute('SELECT total_usd FROM model_limits WHERE id=1').fetchone()[0]
    if spent >= cap-.02:
        raise ValueError('RECURSIVE_BUDGET_STOP')
    return spent


def candidate(parent, label, mutable):
    record_path = study.ROOT / 'candidates' / label / 'candidate.json'
    if not record_path.exists():
        budget_guard()
        study.propose(parent, [], label, mutable=mutable,
                      public_experience=read(ROOT / 'public-experience.json'),
                      feedback={'mutation_scope':list(mutable),
                        'instruction':('This invocation modifies U, the improvement procedure in harness/improver.ts itself. The generic parent template mentions solver edits, but harness/solver.ts is outside this invocation and read-only. Decide independently how future improvers should analyze public evidence, propose patches and verify them. Do not attempt to change P. ' if mutable==('improver.ts',) else 'This invocation modifies P in harness/solver.ts only; U is read-only. ')+
                        'No implementation or failure cause is prescribed. Leave the permitted patch, local build result and candidate-note.md.'})
    record = read(record_path)
    if record.get('harness_path'):
        return Path(record['harness_path'])
    # One mechanical continuation, identical for both meta arms. The external
    # owner grant keeps its original expiry and request count; no budget reset.
    immutable(ROOT / 'continuation-policy.json', {
        'max_continuations': 1, 'request_count': 'same owner, cumulative maximum 24',
        'time': 'original external grant expiry; never renewed',
        'feedback': 'mechanical no-op/build/scope status only; no prescribed source fix',
        'history': 'same frozen public history; retain all prior source and process artifacts'})
    continued = study.ROOT / 'candidates' / (label + '-continued') / 'candidate.json'
    if not continued.exists():
        with Store(HOME_ROOT / 'state').connect() as db:
            owner = record['improver_process']
            count = db.execute('SELECT COUNT(*) FROM model_requests WHERE owner=?', (owner,)).fetchone()[0]
            grant = db.execute('SELECT expires FROM grants WHERE owner=?', (owner,)).fetchone()
        if count >= 24 or not grant or time.time() >= grant['expires'] - 10:
            return None
        budget_guard()
        study.propose(parent, [], label + '-continued', mutable=mutable,
                      continuation_owner=owner, public_experience=read(ROOT / 'public-experience.json'),
                      feedback={'mechanical_status': record['status'], 'requests_used': count,
                                'requests_total_cap': 24, 'allowed_paths': ['harness/' + x for x in mutable],
                                'instruction': 'Continue this same bounded attempt from existing files. The explicit allowed_paths for this invocation override generic editable-file suggestions in the parent template. '+
                                  ('This invocation changes the improvement procedure in harness/improver.ts itself; harness/solver.ts is read-only. ' if mutable==('improver.ts',) else '')+
                                  'Leave an actual permitted source patch, build and repair it, and write candidate-note.md. No patch cause or implementation is prescribed.'})
    final = read(continued)
    return Path(final['harness_path']) if final.get('harness_path') else None


def evolve(joint_label='R1-Ug'):
    p = read(ROOT / 'protocol.json')
    ug = candidate(Path(p['h1']), joint_label, ('improver.ts',))
    if ug is None:
        study.save(ROOT / 'lineage.json', {'status': 'STAGNATED_U_NOT_CHANGED', 'h0': p['h0'], 'h1': p['h1']})
        return None
    h1, hg = manifest(p['h1']), manifest(ug)
    compatible(h1, hg)
    if hg['loaded_modules']['solver'] != h1['loaded_modules']['solver']:
        raise ValueError('U_ONLY_P_DRIFT')
    if hg['loaded_modules']['improver'] == h1['loaded_modules']['improver']:
        raise ValueError('U_MANIPULATION_NOT_ACTIVATED')
    # Neither branch is selected by its later evaluation or transfer results.
    c0 = candidate(Path(p['h1']), 'R2-U0-child', ('solver.ts',))
    cg = candidate(ug, 'R2-Ug-child', ('solver.ts',))
    lineage = {'status': 'DESCENDANTS_BUILT' if c0 and cg else 'DESCENDANT_STAGNATION', 'joint_candidate_label':joint_label,
               'h0': p['h0'], 'h1': p['h1'], 'joint': str(ug),
               'meta_u0_child': str(c0) if c0 else None, 'meta_ug_child': str(cg) if cg else None,
               'fallback': 'An unchanged parent is retained as a no-op outcome; it is never represented as a new descendant.'}
    study.save(ROOT / 'lineage.json', lineage)
    return lineage


def verify_activation(receipt):
    events = [json.loads(line) for line in (HOME_ROOT / 'sessions' / receipt['owner'] / 'trace.jsonl').read_text().splitlines()]
    loaded = [e for e in events if e.get('type') == 'harness_loaded']
    expected=1+len(receipt.get('previous_attempts',[]))
    if len(loaded) != expected or any(e['loaded'] != receipt['harness']['loaded_modules'] for e in loaded):
        raise ValueError('RECURSIVE_PROCESS_ACTIVATION_MISMATCH')
    return {'pids':[e['pid'] for e in loaded], 'pid': loaded[-1]['pid'], 'modules': loaded[0]['loaded'], 'trace_hash': filehash(HOME_ROOT / 'sessions' / receipt['owner'] / 'trace.jsonl')}


def run_arm(group, arm, harness, tasks, memory=False):
    p = read(ROOT / 'protocol.json')
    m = manifest(harness)
    compatible(manifest(p['h0']), m)
    public = [] if group == 'transfer' else read(ROOT / 'public-memory.json')
    protocol = {'group': group, 'arm': arm, 'harness': m, 'tasks': tasks,
                'memory_in_prompt': memory, 'public_data_hash': identity(public),
                'task_bindings': {t: p['task_bindings'][t] for t in tasks},
                'caps': p['caps'], 'repetitions': 1}
    immutable(ROOT / f'{group}-{arm}-protocol.json', protocol)
    path = ROOT / f'{group}-{arm}-results.json'
    rows = read(path) if path.exists() else []
    for t in tasks:
        owner = f'pi-rec-{group}-{arm}-{t}'
        if any(r['owner'] == owner for r in rows):
            continue
        receipt_path = HOME_ROOT / 'sessions' / owner / 'receipt.json'
        if receipt_path.exists():
            receipt = read(receipt_path)
            if receipt['status'] == 'RUNNING':
                raise ValueError('RECURSIVE_RECONCILIATION_REQUIRED')
        else:
            budget_guard()
            receipt = launch(harness, t, label=owner, public_history=public, memory_in_prompt=memory)
        row = {**study.metrics(receipt), 'activation_verified': verify_activation(receipt),
               'public_history_hash': receipt['public_history_hash'],
               'memory_in_prompt': receipt['memory_in_prompt'], 'task_input_hash': receipt['task_input_hash']}
        if row['public_history_hash'] != protocol['public_data_hash'] or row['memory_in_prompt'] != memory:
            raise ValueError('MEMORY_TREATMENT_MISMATCH')
        rows.append(row)
        study.save(path, rows)
        print(json.dumps({'group': group, 'arm': arm, 'task': t, 'outcome': row['outcome'], 'cost': row['cost_upper_bound_usd']}), flush=True)
    return rows


def run(group):
    p, lineage = read(ROOT / 'protocol.json'), read(ROOT / 'lineage.json')
    plan=read(ROOT/'execution-plan.json') if (ROOT/'execution-plan.json').exists() else {'development_tasks':DEV}
    dev_tasks=plan['development_tasks']
    if group == 'controls':
        for arm, h, memory in [('fixed', p['h0'], False), ('memory', p['h0'], True),
                               ('fixed-u', p['h1'], False), ('joint', lineage.get('joint'), False)]:
            if h:
                run_arm(group, arm, Path(h), dev_tasks, memory)
    elif group == 'meta':
        for arm, h in [('u0', lineage.get('meta_u0_child') or p['h1']),
                       ('ug', lineage.get('meta_ug_child') or lineage.get('joint'))]:
            if h:
                run_arm(group, arm, Path(h), dev_tasks)
    elif group == 'transfer':
        h = lineage.get('meta_ug_child') or lineage.get('joint')
        if not h:
            raise ValueError('NO_FROZEN_DESCENDANT_FOR_TRANSFER')
        immutable(ROOT/'transfer-subject.json',{'subject':h,'is_new_P_descendant':bool(lineage.get('meta_ug_child')),
          'selection':'Ug descendant if built, otherwise last valid joint P1,Ug; fixed before first transfer result, no outcome-based selection'})
        for arm, harness in [('parent', p['h0']), ('descendant', h)]:
            run_arm(group, arm, Path(harness), TRANSFER)
    else:
        raise ValueError('UNKNOWN_RECURSIVE_GROUP')


def report():
    p = read(ROOT / 'protocol.json')
    lineage = read(ROOT / 'lineage.json') if (ROOT / 'lineage.json').exists() else None
    arms = {}
    for path in sorted(ROOT.glob('*-results.json')):
        rows = read(path)
        for row in rows:
            trace=HOME_ROOT/'sessions'/row['owner']/'trace.jsonl'
            errors=[e['message'].get('errorMessage','') for line in trace.read_text().splitlines()
                    if (e:=json.loads(line)).get('type')=='message' and e.get('message',{}).get('role')=='assistant']
            stops=[error for error in errors if any(code in error for code in
                   ['MODEL_TOKEN_BUDGET','MODEL_USD_BUDGET','MODEL_WALL_BUDGET','PROVIDER_USAGE_UNKNOWN_STOP'])]
            block=stops[-1] if stops and not row.get('submitted') else None
            row['past_global_budget_stops']=stops
            row['evaluation_status']='INTERRUPTED_BY_GLOBAL_BUDGET' if block else ('EVALUATED_AFTER_BUDGET_RESTART' if stops else 'EVALUATED')
            row['global_budget_stop']=block
        arms[path.stem.removesuffix('-results')] = {
            'trials': len(rows), 'passed': sum(r['outcome'] == 'PASS' for r in rows),
            'failed': sum(r['outcome'] == 'FAIL' for r in rows),
            'not_evaluated': sum(r['outcome'] == 'NOT_EVALUATED' for r in rows),
            'cost_upper_usd': sum(r['cost_upper_bound_usd'] for r in rows),
            'global_budget_interruptions':sum(bool(r['global_budget_stop']) for r in rows),'rows': rows}
    with Store(HOME_ROOT / 'state').connect() as db:
        fees = [dict(r) for r in db.execute('SELECT owner,status,charged,reserved FROM model_requests')]
    by_owner = {}
    for r in fees:
        by_owner[r['owner']] = by_owner.get(r['owner'], 0) + (r['charged'] if r['status'] == 'SETTLED' else r['reserved'])
    expected = ['controls-' + x for x in ['fixed', 'memory', 'fixed-u', 'joint']] + ['meta-u0', 'meta-ug', 'transfer-parent', 'transfer-descendant']
    plan=read(ROOT/'execution-plan.json') if (ROOT/'execution-plan.json').exists() else {'development_tasks':DEV}
    result = {'schema': p['schema'], 'lineage': lineage, 'arms': arms,
              'execution_plan':plan,
              'all_declared_trials_attempted': all(k in arms and arms[k]['trials'] == (2 if k.startswith('transfer') else len(plan['development_tasks'])) for k in expected),
              'completed_all_declared_trials': all(k in arms and arms[k]['trials'] == (2 if k.startswith('transfer') else len(plan['development_tasks'])) for k in expected) and not any(v['global_budget_interruptions'] for v in arms.values()),
              'all_work_cost_upper_usd': sum(by_owner.values()), 'all_costs_by_owner': by_owner,
              'unknown_usage': any(r['status'] == 'UNKNOWN' for r in fees), 'additional_assets': p['extra_assets'],
              'recovery_affected':any(r.get('past_global_budget_stops') for v in arms.values() for r in v['rows']),
              'interpretation': 'P and U activation, solver outcomes and descendant outcomes are distinct. The prospectively budget-reduced development comparison is a single trial per arm, not evidence of general or meta improvement. Failed/no-op candidates and earlier costs remain included.',
              'promotion': 'NOT_PROMOTED'}
    study.save(ROOT / 'report.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'evolve', 'controls', 'meta', 'transfer', 'report'])
    parser.add_argument('--h0', type=Path)
    parser.add_argument('--h1', type=Path)
    parser.add_argument('--joint-label', default='R1-Ug')
    a = parser.parse_args()
    if a.mode == 'prepare':
        print(json.dumps(prepare(a.h0, a.h1)))
    elif a.mode == 'evolve':
        print(json.dumps(evolve(a.joint_label)))
    elif a.mode == 'report':
        print(json.dumps(report()))
    else:
        run(a.mode)


if __name__ == '__main__':
    main()
