"""Unknown-frequency full-node inversion and a retained harmonic numerical task."""
import copy
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / 'deep')]
import semantic_alias as sa
import numerics_fidelity as nf
from sim import TASK, beam, simulate
from agent_limits import response

FILE = HERE / 'resonance_qualification.json'
QUAL = json.loads(FILE.read_text()) if FILE.exists() else {}
CACHE = QUAL.get('cache', {})
OLD = json.loads((HERE.parent / 'deep/numerics_fidelity_qualification.json').read_text())
MATH = {}
for row in OLD['records']:
    if row['task'] != 'P5-impact-narrow':
        continue
    r = row if 'design' in row else row['result']
    MATH[json.dumps(r['design'], sort_keys=True)] = r['result']


def tasks():
    t = copy.deepcopy(sa.tasks()[2])
    t.update(id='T4a_resonance', axis=4, _physical={},
             description='Repair a node under a fixed but unmeasured background vibration frequency. Keep the four-event service.',
             groups=dict(main_length_mm='harvester', aux_length_mm='aux', C_uF='storage', gate_V='storage', threshold_V='front_end'))
    t['spec']['input'] = 'Unknown fixed 38–52 Hz / .15g background; 210Hz / .5g / 150ms target; 250Hz / .8g / 200ms nuisance.'
    t['spec'].pop('uncertainty', None)
    t['spec']['measurement'] = 'Power observation includes the dominant mechanical frequency measured from the actual pre-event trajectory.'
    t['clean_spec'] = copy.deepcopy(t['spec'])
    h = next(q for q in nf.tasks() if q['id'] == 'P5-impact-narrow')
    groups = {k: 'harvester' for k in ('h', 'mass_g')}
    for group, keys in dict(storage=('C_uF', 'gate_V'), power=('R_kohm',), protection=('D', 'shunt_kohm', 'shield_V'),
                            aux=('A', 'L2_mm', 'm2_g', 'trigger_V'), active=('B',), memory=('C',), firmware=('poll_ms',)).items():
        groups.update({k: group for k in keys})
    h.update(id='T4b_numeric', axis=4, groups=groups, _source_id='P5-impact-narrow')
    h['clean_spec'] = copy.deepcopy(h['spec'])
    return [t, h]


def _harmonic_result(r):
    m = r['metrics']
    return dict(pass_=r['pass_'], terminal=dict(pass_=r['pass_']),
                power={k: m[k] for k in ('harvested_uW', 'required_uW', 'background_voltage_V')},
                trigger=dict(event_voltage_V=m['event_voltage_V']),
                program=dict(stress_MPa=m['stress_MPa'], scope='Harmonic screen; no executed firmware, classification or ACK.'),
                slack=r['slack'], cost=r['cost'], fidelity='harmonic-only')


def evaluate(t, x):
    if t['id'] == 'T4b_numeric':
        key = json.dumps(x, sort_keys=True)
        reused = key in MATH
        if not reused:
            MATH[key] = nf.evaluate(t, x, 'fast')
        r = copy.deepcopy(MATH[key])
        if reused:
            r['cost'] = dict(full=0, numeric=0)
        return _harmonic_result(r) | dict(cached=reused)
    d = sa._design(t, x)
    physical_task = dict(TASK, background_Hz=52.)
    key = json.dumps([d, physical_task], sort_keys=True)
    if key in CACHE:
        return copy.deepcopy(CACHE[key]) | dict(cost=dict(full=0, numeric=0), cached=True)
    r = simulate(d, physical_task)
    m = r['metrics']; y = np.asarray(r['trace']['y']); times = np.asarray(r['trace']['t'])
    q = np.interp(np.arange(2., 6., .001), times, y[:, 0]); spectrum = abs(np.fft.rfft(q - q.mean()))
    frequencies = np.fft.rfftfreq(len(q), .001)
    terminal = {k: m[k] for k in ('faults', 'delivered_on_time', 'false_reports', 'brownouts')}
    out = dict(pass_=r['verdict'] == 'PASS', terminal=terminal,
        power=dict(max_storage_V=float(y[:, 6].max()), storage_before_first_event_V=float(y[np.searchsorted(times, 7.99), 6]),
                   final_storage_V=m['final_storage_V'], main_peak_voltage_V=float(abs(y[:, 2]).max()),
                   observed_mechanical_frequency_Hz=float(frequencies[spectrum.argmax()]), cold_charge_ready_s=m['cold_charge_ready_s'], energy_J=r['energy_J']),
        trigger=dict(aux_peak_voltage_V=float(abs(y[:, 5]).max()), envelope_peak_V=float(y[:, 7].max()), wakeups=m['wakeups'], first_wake_s=m['first_wake_s']),
        program=dict(stages={k: sum(e['event'] == k for e in r['events']) for k in ('WAKE', 'SAMPLE', 'CONFIRM', 'REJECT', 'TX', 'RECEIVED', 'BROWNOUT')},
                     peak_stress_MPa=m['peak_stress_MPa'], peak_tip_mm=m['peak_tip_mm'], max_latency_s=m['max_latency_s'], minimum_active_storage_V=m['minimum_active_storage_V']),
        slack=dict(delivery=m['delivered_on_time']/m['faults']-1, false_reports=-m['false_reports'], brownouts=-m['brownouts'],
                   stress=1-m['peak_stress_MPa']/TASK['stress_limit_MPa'], travel=1-m['peak_tip_mm']/TASK['tip_travel_limit_mm']),
        cost=dict(full=1, numeric=0), fidelity='full transient', runtime_s=r['runtime_s'], cached=False)
    CACHE[key] = out
    QUAL['cache'] = CACHE
    FILE.write_text(json.dumps(QUAL, indent=2))
    return copy.deepcopy(out)


def optimize(t, x, variables, budget=50):
    if t['id'] != 'T4b_numeric' or len({t['groups'][k] for k in variables}) != 1:
        raise ValueError('Only T4b, one module per bounded numerical search.')
    result = nf.optimize(t, x, variables, budget)
    MATH[json.dumps(result['design'], sort_keys=True)] = result['result']
    return result | dict(result=_harmonic_result(result['result']))


if __name__ == '__main__':
    t = tasks()[0]
    scan = []
    for length in np.linspace(24, 42, 181):
        b = beam(dict(sa.BASE['harvester'], length_mm=float(length)))
        q, v = response(b, 52., .15, 1e8)
        scan.append(dict(length_mm=float(length), open_voltage_V=float(v)))
    QUAL.update(task='T4a_resonance', hidden_environment=dict(TASK, background_Hz=52.),
                selection='First freeze: initial 30mm, lower flank 26mm, open-voltage peak 27.6mm. After 27.6mm missed cold-start, use the 5kohm loaded-linear peak near 26.93mm to select 27mm. No model outcomes used.',
                harmonic_scan=scan, records=[], source_math_qualification='../deep/numerics_fidelity_qualification.json')
    for length in (30., 26., 27.6, 27., 27.3):
        x = t['initial'] | dict(main_length_mm=length)
        result = evaluate(t, x)
        QUAL['records'].append(dict(design=x, result=result))
        FILE.write_text(json.dumps(QUAL, indent=2))
        print(length, result['pass_'], result['terminal'], result['runtime_s'], flush=True)
