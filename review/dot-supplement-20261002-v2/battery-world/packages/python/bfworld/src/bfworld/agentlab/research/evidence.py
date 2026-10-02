"""Property-scoped computational evidence and checked transfer operators.

Certificates are conditional on the frozen first-order model, not claims about
hardware. Calibration-free predictions cannot satisfy a measured requirement.
Old evidence remains immutable; a transfer is a separate support object.
"""
from __future__ import annotations

import math
import time
from .. import product_energy
from ..store import identity
from .core import sha

PROPERTIES = ('daily_balance', 'dark_storage', 'normal_service', 'cold_ready')
ENERGY_KEYS = ('pv_power_mw', 'lit_hours', 'conversion_efficiency', 'capacitance_f',
               'capacitance_tolerance_low', 'v_high', 'v_low', 'sleep_ua', 'leakage_ua',
               'supply_v', 'led_total_ma', 'pulse_ms', 'mcu_event_mj', 'events_per_day', 'restore_voltage_v')


def verifier_revision():
    from pathlib import Path
    return identity({'energy': sha(Path(product_energy.__file__).read_bytes()),
                     'adapter': sha(Path(__file__).read_bytes())})


def validate(query):
    if query.get('schema_version') != 'bf-energy-query-v1' or 'product_revision' not in query:
        raise ValueError('EVIDENCE_QUERY_SCHEMA')
    e = query['energy']
    for key in ENERGY_KEYS:
        if key == 'restore_voltage_v' and key not in e:
            continue
        v = e.get(key)
        if type(v) not in (int, float) or not math.isfinite(v):
            raise ValueError('EVIDENCE_FINITE_INPUT:'+key)
    if not (0 < e['conversion_efficiency'] <= 1 and 0 < e['capacitance_tolerance_low'] <= 1
            and e['capacitance_f'] > 0 and 0 <= e['lit_hours'] <= 24
            and 0 < e['v_low'] < e['v_high'] <= 5.5 and e['v_high'] > e['supply_v']+.1):
        raise ValueError('EVIDENCE_MODEL_DOMAIN')
    if any(e[k] < 0 for k in ENERGY_KEYS if k in e):
        raise ValueError('EVIDENCE_NEGATIVE_INPUT')
    req = query['requirements']
    if type(req.get('minimum_service_fraction')) not in (float, int) or not 0 <= req['minimum_service_fraction'] <= 1:
        raise ValueError('EVIDENCE_SERVICE_REQUIREMENT')
    if type(req.get('cold_deadline_s')) not in (float, int) or not math.isfinite(req['cold_deadline_s']) or req['cold_deadline_s'] < 0:
        raise ValueError('EVIDENCE_DEADLINE_REQUIREMENT')
    if query.get('duration_s', 172800) != 172800:
        raise ValueError('EVIDENCE_HORIZON_UNSUPPORTED')
    if query.get('world_revision') != 'first-order-energy-v2':
        raise ValueError('EVIDENCE_WORLD_REVISION')


def _margins(e):
    # Small analytical operator. Does not claim transient or startup preservation.
    eta = e['conversion_efficiency']
    demand = (e['sleep_ua']*1e-6*e['supply_v']/eta + e['leakage_ua']*1e-6*e['v_high'])*86400
    demand += (e['supply_v']*e['led_total_ma']*1e-3*e['pulse_ms']/1000 + e['mcu_event_mj']/1000)/eta*e['events_per_day']
    harvest = e['pv_power_mw']*1e-3*eta*e['lit_hours']*3600
    available = e['capacitance_f']*e['capacitance_tolerance_low']*(e['v_high']**2-e['v_low']**2)/2
    return {'daily_balance': harvest-demand, 'dark_storage': available-demand*(24-e['lit_hours'])/24}


def dependencies(query, prop):
    req = query['requirements']
    keys = list(ENERGY_KEYS)
    if prop == 'daily_balance':
        keys = [k for k in keys if k not in {'capacitance_f', 'capacitance_tolerance_low', 'v_low', 'restore_voltage_v'}]
    elif prop == 'dark_storage':
        keys = [k for k in keys if k not in {'pv_power_mw', 'restore_voltage_v'}]
    return {'energy': {k: query['energy'].get(k) for k in keys},
            'requirement': req['minimum_service_fraction'] if prop == 'normal_service' else req['cold_deadline_s'] if prop == 'cold_ready' else 0,
            'world_revision': query['world_revision'], 'verifier_revision': query['verifier_revision'],
            'duration_s': query.get('duration_s', 172800),
            'calibration_required': query.get('calibration_required', False),
            'calibration_id': query.get('calibration_id'), 'assumptions': query.get('assumptions', [])}


def unknown(query):
    return (query.get('calibration_required', False) or query.get('verifier_revision') != verifier_revision())


def full_evaluate(query):
    validate(query)
    if unknown(query):
        return {p: {'verdict': 'UNKNOWN', 'margin': None,
                    'reason': 'measured calibration unavailable or verifier revision unsupported'} for p in PROPERTIES}
    raw = product_energy.calculate(query['energy'])
    normal, cold = raw['scenarios']['normal'], raw['scenarios']['cold']
    attempts = normal['accepted_events']+normal['unavailable_events']+normal['aborted_pulses']
    service = normal['accepted_events']/attempts if attempts else 0
    values = {'daily_balance': raw['margin_j_day'],
              'dark_storage': raw['usable_storage_j']-raw['dark_interval_demand_j'],
              'normal_service': service-query['requirements']['minimum_service_fraction'],
              'cold_ready': None if cold['first_ready_s'] is None else query['requirements']['cold_deadline_s']-cold['first_ready_s']}
    return {p: {'verdict': 'FAIL' if m is None else 'PASS' if m >= 0 else 'FAIL', 'margin': m,
                'reason': 'not ready during simulated horizon' if m is None else 'conditional computational predicate'} for p, m in values.items()}


def make_evidence(research, query):
    # Operator's evaluator only; participants cannot submit arbitrary values.
    started = time.perf_counter()
    result = full_evaluate(query)
    record = dict(schema_version='bf-property-evidence-v1', query=query, query_hash=identity(query),
                  results=result, evaluator=verifier_revision(), elapsed_s=time.perf_counter()-started,
                  fidelity='conditional-computational', hardware_verified=False)
    return research.put('evidence', record)


def validate_evidence(evidence):
    if evidence['query_hash'] != identity(evidence['query']) or evidence['evaluator'] != evidence['query']['verifier_revision']:
        raise ValueError('EVIDENCE_BINDING_MISMATCH')
    if set(evidence['results']) != set(PROPERTIES):
        raise ValueError('EVIDENCE_PROPERTIES_MISSING')


def transfer(evidence, query, prop, operator):
    validate(query)
    validate_evidence(evidence)
    if prop not in PROPERTIES:
        raise ValueError('EVIDENCE_PROPERTY')
    old = evidence['query']
    if unknown(query) or unknown(old) or evidence['evaluator'] != verifier_revision():
        return None
    if operator == 'exact-dependencies':
        if dependencies(old, prop) != dependencies(query, prop):
            return None
        return {'operator': operator, 'dependency_hash': identity(dependencies(query, prop)),
                'result': evidence['results'][prop], 'support_kind': 'exact-projection'}
    if operator == 'margin-bound':
        if prop not in {'daily_balance', 'dark_storage'} or old.get('assumptions') != query.get('assumptions'):
            return None
        if old.get('calibration_id') != query.get('calibration_id'):
            return None
        before, after = _margins(old['energy'])[prop], _margins(query['energy'])[prop]
        observed = evidence['results'][prop]['margin']
        if observed is None or not math.isclose(before, observed, abs_tol=1e-10, rel_tol=1e-10):
            return None
        # Triangle inequality plus conservative floating arithmetic allowance.
        bound = abs(after-before)+max(1e-9, abs(before)*1e-10, abs(after)*1e-10)
        verdict = evidence['results'][prop]['verdict']
        if (verdict == 'PASS' and before-bound >= 0) or (verdict == 'FAIL' and before+bound < 0):
            return {'operator': operator, 'old_margin': before, 'change_bound': bound,
                    'margin_interval': [before-bound, before+bound],
                    'result': {'verdict': verdict, 'margin': None, 'reason': 'predicate preserved by conservative model bound'},
                    'support_kind': 'conditional-model-bound'}
    return None


def plan(research, evidence_key, query, method):
    if method not in {'full-recompute', 'dependency-cache', 'fixed-transfer', 'cost-aware-transfer'}:
        raise ValueError('EVIDENCE_METHOD')
    started = time.perf_counter()
    evidence = research.get('evidence', evidence_key)
    validate_evidence(evidence)
    supported, pending, attempts = {}, [], []
    for prop in PROPERTIES:
        cert = None
        operators = [] if method == 'full-recompute' else ['exact-dependencies']
        if method in {'fixed-transfer', 'cost-aware-transfer'}:
            # Same library, different declared ordering; no privileged information.
            operators = ['margin-bound', 'exact-dependencies'] if method == 'fixed-transfer' else ['exact-dependencies', 'margin-bound']
        for operator in operators:
            cert = transfer(evidence, query, prop, operator)
            attempts.append({'property': prop, 'operator': operator, 'accepted': cert is not None})
            if cert:
                break
        if cert:
            record = dict(schema_version='bf-evidence-support-v1', evidence=evidence_key,
                          query=query, query_hash=identity(query), property=prop, certificate=cert,
                          evaluator=verifier_revision(), hardware_verified=False)
            supported[prop] = {'support': research.put('supports', record), **cert['result']}
        else:
            pending.append(prop)
    planning_s = time.perf_counter()-started
    # One real model execution for the unresolved properties, not four invented costs.
    started = time.perf_counter()
    computed = full_evaluate(query) if pending else {}
    recompute_s = time.perf_counter()-started
    results = {p: supported.get(p, computed.get(p)) for p in PROPERTIES}
    return dict(results=results, supports={p: x['support'] for p, x in supported.items()},
                unresolved_properties=pending, full_model_executions=int(bool(pending) and not unknown(query)),
                planning_s=planning_s, recompute_s=recompute_s, total_s=planning_s+recompute_s,
                attempts=attempts, method=method, query_hash=identity(query))


def check_support(research, support_key):
    support = research.get('supports', support_key)
    if support['query_hash'] != identity(support['query']) or support['evaluator'] != verifier_revision():
        raise ValueError('SUPPORT_BINDING_MISMATCH')
    e = research.get('evidence', support['evidence'])
    actual = transfer(e, support['query'], support['property'], support['certificate']['operator'])
    if actual is None or actual != support['certificate']:
        raise ValueError('SUPPORT_CERTIFICATE_INVALID')
    return True
