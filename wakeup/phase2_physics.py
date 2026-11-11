"""Phase-2 tasks and compact facts from the unchanged coupled node."""
import copy
import json
import threading
from pathlib import Path

import numpy as np

from sim import TASK, acceleration, simulate
from deep import semantic_alias as sa

FILE = Path(__file__).with_name('phase2') / 'physics.json'
STATE = json.loads(FILE.read_text()) if FILE.exists() else dict(tasks={}, cache={}, qualification=[])
LOCK = threading.Lock()  # LSODA is not reentrant.
DOMAIN = dict(main_length_mm=[24., 42.], aux_length_mm=[11., 24.], C_uF=[80., 500.],
              gate_V=[2., 3.2], threshold_V=[.15, 1.])
SPEC = dict(sa.tasks()[2]['spec'])
SPEC['uncertainty'] = ('Effective beam lengths can differ from nominal dimensions by an unknown, '
                       'stationary manufacturing/mounting factor; zero deviation is possible.')
SPEC['controls'] = dict(main_length_mm='Main energy-harvesting beam nominal length, mm.',
    aux_length_mm='Auxiliary trigger beam nominal length, mm.', C_uF='Supply storage, microfarads.',
    gate_V='Stored-supply voltage required to start MCU; brownout is 1.8 V.',
    threshold_V='Trigger-envelope voltage required to wake; separate from stored supply.')


def _task(ident, family, factors, initial=None):
    x = sa.INITIAL | (initial or {})
    return dict(id=ident, public_id='node-' + family, family=family, initial=x,
                domain=copy.deepcopy(DOMAIN), spec=copy.deepcopy(SPEC),
                private=dict(factors=factors, task=copy.deepcopy(TASK)))


def tasks(stage='A1'):
    """All later tasks are frozen here before the first model run."""
    stage = {'A2': 'A1', 'A3': 'A1', 'CA1': 'CA', 'CA2': 'CA', 'J1': 'J', 'J2': 'J'}.get(stage, stage)
    if stage in STATE['tasks']:
        return copy.deepcopy(STATE['tasks'][stage])
    if stage == 'A1':
        rows = []
        for name, key, factor, knob, start in [('E1', 'main_factor', .75, 'main_length_mm', 35.),
            ('E2', 'main_factor', .85, 'main_length_mm', 33.),
            ('T1', 'aux_factor', 1.4, 'aux_length_mm', 15.5),
            ('T2', 'aux_factor', 1.25, 'aux_length_mm', 16.)]:
            for world, f in [('nominal', 1.), ('offset', factor)]:
                rows.append(_task(f'A1-{name}-{world}', name, {key: f}, {knob: start}))
    elif stage == 'CA':
        rows = []
        for i, factor in enumerate([.78, .80, .82, .88, .90, .92, 1.18, 1.22, 1.28, 1.32, 1.36, 1.38]):
            main = i < 6
            key, knob, start = ('main_factor', 'main_length_mm', 34.) if main else ('aux_factor', 'aux_length_mm', 16.)
            rows.append(_task(f'CA-{i+1:02}', 'energy' if main else 'trigger', {key: factor}, {knob: start}))
    elif stage == 'J':
        rows = []
        for i, (h, w, c) in enumerate([(.80, 1.30, 50.), (.90, 1.20, 70.), (.78, 1.35, 60.), (.88, 1.25, 50.)]):
            t = _task(f'J-{i+1}', 'coupled', dict(main_factor=h, aux_factor=w),
                      dict(main_length_mm=34., aux_length_mm=16., C_uF=c))
            t['domain']['C_uF'][0] = 50.
            rows.append(t)
    else:
        raise ValueError(stage)
    STATE['tasks'][stage] = rows
    _save()
    return copy.deepcopy(rows)


def _save():
    FILE.parent.mkdir(exist_ok=True)
    FILE.write_text(json.dumps(STATE, indent=2) + '\n')


def _design(t, x):
    return sa._design(dict(axis=2, _physical=t['private']['factors']), x)


def _response(times, values, drive, mask, hz):
    phase = np.exp(-2j * np.pi * hz * times[mask])
    v, a = 2 * np.mean(values[mask] * phase), 2 * np.mean(drive[mask] * phase)
    return dict(amplitude_V=float(abs(v)), phase_vs_acceleration_deg=float(np.angle(v / a, deg=True)))


def evaluate(t, x):
    """Return actual executed facts; cached returns cost zero. Never expose private truth."""
    d, task = _design(t, x), t['private']['task']
    key = json.dumps([d, task], sort_keys=True)
    with LOCK:
        if key in STATE['cache']:
            r = copy.deepcopy(STATE['cache'][key])
            return r | dict(cost=dict(full=0, numeric=0), reused=True)
        r = simulate(d, task)
        m, events = r['metrics'], r['events']
        times, y = np.asarray(r['trace']['t']), np.asarray(r['trace']['y'])
        drive = np.array([acceleration(s, task) for s in times])
        bg = (times >= 4.) & (times < 7.)
        target = np.zeros(len(times), dtype=bool)
        for start in task['fault_starts_s']:
            target |= (times >= start + .01) & (times < start + task['fault_duration_s'] - .01)
        stages = {k: sum(e['event'] == k for e in events) for k in
                  ('WAKE', 'BOOT', 'SAMPLE', 'INFER', 'CONFIRM', 'REJECT', 'SAVE', 'TX', 'ACK', 'RECEIVED', 'BROWNOUT')}
        base = dict(max_storage_V=float(y[:, 6].max()), storage_before_first_event_V=float(np.interp(7.99, times, y[:, 6])),
            main_peak_voltage_V=float(abs(y[:, 2]).max()), aux_peak_voltage_V=float(abs(y[:, 5]).max()),
            envelope_peak_V=float(y[:, 7].max()), cold_charge_ready_s=m['cold_charge_ready_s'], stages=stages)
        diagnostic = dict(main_background_response=_response(times, y[:, 2], drive, bg, task['background_Hz']),
            aux_target_response=_response(times, y[:, 5], drive, target, task['fault_Hz']),
            energy_J=r['energy_J'], minimum_active_storage_V=m['minimum_active_storage_V'],
            event_windows=[dict(start_s=s, stored_supply_before_V=float(np.interp(s-.001, times, y[:, 6])),
                wake_times_s=[e['time_s'] for e in events if e['event']=='WAKE' and s <= e['time_s'] < s+task['delivery_deadline_s']],
                received_s=[q['received_s'] for q in r['records'] if s <= q['received_s'] <= s+task['delivery_deadline_s']])
                for s in task['fault_starts_s']],
            measurement='Actual voltage/acceleration cross-phase and event/energy facts from this same full transient; not natural frequency or hidden calibration.')
        out = dict(pass_=r['verdict']=='PASS', terminal={k: m[k] for k in
            ('faults', 'delivered_on_time', 'false_reports', 'brownouts', 'peak_stress_MPa', 'peak_tip_mm')},
            slack=dict(delivery=m['delivered_on_time']/m['faults']-1, false_reports=-m['false_reports'],
                brownouts=-m['brownouts'], stress=1-m['peak_stress_MPa']/task['stress_limit_MPa'],
                travel=1-m['peak_tip_mm']/task['tip_travel_limit_mm']),
            base=base, diagnostic=diagnostic, cost=dict(full=1, numeric=0), fidelity='full transient',
            runtime_s=r['runtime_s'], reused=False)
        STATE['cache'][key] = out
        _save()
        return copy.deepcopy(out)


def view(t, x, result, condition='P'):
    z = dict(current_design=x.copy(), pass_=result['pass_'], terminal=result['terminal'],
             slack=result['slack'], fidelity=result['fidelity'])
    if condition == 'R':
        z['measurements'] = [[k, v] for k, v in result['base'].items()]
    else:
        z['measurements'] = result['base']
    if condition == 'D':
        z['diagnostic'] = result['diagnostic']
    if condition == 'K':
        f = t['private']['factors']
        z['actual_calibration'] = dict(effective_length='nominal_length * factor',
            main_factor=f.get('main_factor', 1.), aux_factor=f.get('aux_factor', 1.))
    return z


def anchoring_cases():
    """Four fixed observed pairs; nominal estimates never replace measured facts."""
    if 'anchors' in STATE:
        return copy.deepcopy(STATE['anchors'])
    cases = []
    patches = dict(E1=dict(main_length_mm=36.), E2=dict(main_length_mm=34.),
                   T1=dict(aux_length_mm=14.5), T2=dict(aux_length_mm=15.))
    for t in tasks('A1'):
        if not t['id'].endswith('offset'):
            continue
        name = t['family']
        xs = [t['initial'], t['initial'] | patches[name]]
        actual = [evaluate(t, x) for x in xs]
        nominal = copy.deepcopy(t)
        nominal['private']['factors'] = {}
        predicted = [evaluate(nominal, x) for x in xs]
        response = 'main_background_response' if name.startswith('E') else 'aux_target_response'
        values = [r['diagnostic'][response]['amplitude_V'] for r in actual]
        estimates = [r['diagnostic'][response]['amplitude_V'] for r in predicted]
        cases.append(dict(id='anchor-'+name, task=t, response=response,
            measured_points=[dict(design=x, facts=view(t, x, r, 'D')) for x, r in zip(xs, actual)],
            nominal_prediction=dict(model='Nominal effective lengths equal the declared lengths; actual device may differ.',
                                    amplitude_V=estimates),
            private=dict(actual_best_index=int(np.argmax(values)), nominal_best_index=int(np.argmax(estimates)),
                         measured_amplitude_V=values, conflict=bool(np.argmax(values) != np.argmax(estimates)))))
    STATE['anchors'] = cases
    _save()
    return copy.deepcopy(cases)


def qualify(limit=32):
    """One initial and one predeclared analytic witness per A1 task; no search."""
    before = len(STATE['cache'])
    for stage in ('A1', 'CA', 'J'):
        tasks(stage)
    for t in tasks('A1'):
        f = t['private']['factors']
        witness = t['initial'] | dict(main_length_mm=30/f.get('main_factor', 1.), aux_length_mm=18/f.get('aux_factor', 1.))
        rows = []
        for label, x in [('initial', t['initial']), ('calibrated_witness', witness)]:
            if len(STATE['cache']) - before >= limit:
                break
            r = evaluate(t, x)
            rows.append(dict(label=label, design=x, result=r))
            print(t['id'], label, r['pass_'], r['terminal']['delivered_on_time'], round(r['runtime_s'], 3), flush=True)
        STATE['qualification'].append(dict(task=t['id'], rows=rows))
        _save()
    return STATE['qualification']


if __name__ == '__main__':
    qualify()
