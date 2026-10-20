"""Executable controls for D/H/G invalidation, not a learned fast method.

The toy apparatus has a feedback controller that transmits only above its
threshold. Replaying an old action trace after an energy change is deliberately
incorrect; conservative dependency invalidation and full execution are oracles.
"""
from .common import digest


def full(design):
    energy = design['initial']
    states, actions = [], []
    for arrival in design['arrivals']:
        energy = min(design['capacity'], energy + arrival)
        action = energy >= design['threshold']
        if action:
            energy -= design['cost']
        actions.append(action)
        states.append(energy)
    return {'actions': actions, 'states': states, 'packets': sum(actions),
            'admissible': min(states) >= 0}


def replay(design, old_actions):
    energy = design['initial']
    states = []
    for arrival, action in zip(design['arrivals'], old_actions):
        energy = min(design['capacity'], energy + arrival)
        if action:
            energy -= design['cost']
        states.append(energy)
    return {'actions': list(old_actions), 'states': states,
            'packets': sum(old_actions), 'admissible': min(states) >= 0}


def invalidation(kind, changed, feedback=True):
    if kind == 'H':
        return 'task-entry'
    if kind == 'G':
        return 'method-lineage-root'
    if kind != 'D':
        raise ValueError('UNKNOWN_INTERVENTION_KIND')
    if not changed:
        return 'reuse-exact-input'
    return 'full-feedback-response' if feedback else 'dependent-suffix'


def qualify():
    base = {'initial': 0, 'capacity': 8, 'arrivals': [4, 4, 4, 4],
            'threshold': 4, 'cost': 4}
    old = full(base)
    mutations = [('unchanged', {}), ('less-energy', {'arrivals': [2, 2, 2, 2]}),
                 ('higher-load', {'cost': 5, 'threshold': 5}),
                 ('threshold-only', {'threshold': 6}),
                 ('capacity-limit', {'capacity': 3}),
                 ('arrival-order', {'arrivals': [0, 0, 8, 8]})]
    cache = {digest(base): old}
    rows = []
    for name, patch in mutations:
        d = {**base, **patch}
        truth = full(d)
        key = digest(d)
        hit = key in cache
        cached = cache[key] if hit else full(d)
        cache[key] = cached
        fixed = replay(d, old['actions'])
        # This conservative boundary expands to the full feedback response.
        dependency = full(d) if patch else old
        boundary = full(d) if patch else old
        rows.append({'case': name, 'input_sha256': key, 'fixed_trajectory': fixed,
                     'dependency': dependency, 'boundary': boundary,
                     'full': truth, 'exact_response_cache': cached,
                     'cache_hit': hit, 'fixed_matches_full': fixed == truth,
                     'correct_methods_match': dependency == boundary == cached == truth,
                     'response_executions': {'fixed': 0, 'dependency': int(bool(patch)),
                         'boundary': int(bool(patch)), 'full': 1, 'exact_cache': int(not hit)}})
    return {'schema_version': 'campaign-f1a-control-v1', 'apparatus': base, 'rows': rows,
            'qualification': all(r['correct_methods_match'] for r in rows)
                             and any(not r['fixed_matches_full'] for r in rows),
            'claim_boundary': 'Deterministic public control, not a physical solver speedup; '
                              'boundary and dependency methods intentionally expand to full.'}
