"""Original Phase-2 tasks, two existing supply branches, one transient consumer."""
import copy
import fcntl
import hashlib
import json
import signal
import threading
from pathlib import Path

import numpy as np

from sim import simulate

HERE = Path(__file__).resolve().parent
OUT = HERE / "attribution"
MANIFEST = json.loads((OUT / "legacy-selection.json").read_text())
CACHE = OUT / "cache"
LOCK = threading.Lock()
LEGACY = None
DOMAIN = dict(main_length_mm=[24., 42.], aux_length_mm=[11., 24.], C_uF=[80., 1000.],
    gate_V=[1.9, 3.2], threshold_V=[.15, 20.], rearm_V=[.05, 10.], poll_s=[.015, 4.],
    R_ohm=[2000., 300000.], S_setting_V=[1., 50.], shunt_ohm=[500., 100000.],
    A=[False, True], B=[False, True], C=[False, True], D=[False, True])
DEFAULT_MODULES = dict(A=True, B=False, C=False, D=False)
TIMEOUT = "TOOL_ERROR: full numerical execution exceeded 120s; no scientific result"


def make_task(selection_id, branch, width):
    pair = next(p for p in MANIFEST['selected_pairs'] if p['selection_id'] == selection_id)
    instance = MANIFEST['instances'][pair['instance_id']]
    task = copy.deepcopy(instance['original_task'])
    task.update(id=selection_id, selection_id=selection_id, instance_id=pair['instance_id'], branch=branch, width=width)
    task['private']['base'] = copy.deepcopy(instance['original_initial_full_design'])
    if width == 'wide':
        task['domain'] = copy.deepcopy(DOMAIN)
        task['initial'].update(rearm_V=.33*task['initial']['threshold_V'], poll_s=.1,
            R_ohm=45000., S_setting_V=15., shunt_ohm=3000., **DEFAULT_MODULES)
    return task


def design(task, x, nominal=False):
    x = task['initial'] | x
    x = {k: float(v) if type(v) in (int, float) else v for k, v in x.items()}
    d = copy.deepcopy(task['private']['base'])
    factors = {} if nominal else task['private']['factors']
    d['harvester']['length_mm'] = x['main_length_mm']*factors.get('main_factor', 1.)
    d['trigger_beam']['length_mm'] = x['aux_length_mm']*factors.get('aux_factor', 1.)
    c = d['circuit']
    c.update(storage_uF=x['C_uF'], start_V=x['gate_V'], wake_high_V=x['threshold_V'],
             wake_low_V=x['rearm_V'] if task['width'] == 'wide' else .33*x['threshold_V'])
    d['firmware']['poll_s'] = x['poll_s'] if task['width'] == 'wide' else .1
    if task['branch'] == 'converter':
        c['converter_input_R_ohm'] = x['R_ohm'] if task['width'] == 'wide' else 45000.
    else:
        c.pop('converter_input_R_ohm', None)
    if task['width'] == 'wide':
        modules = {k: x[k] for k in 'ABCD'}
        if modules != DEFAULT_MODULES:
            d['modules'] = modules
        else:
            d.pop('modules', None)
        if modules['D']:
            c.update(shunt_threshold_V=x['S_setting_V'], shunt_ohm=x['shunt_ohm'])
    return d


def public_task(task):
    spec = copy.deepcopy(task['spec'])
    spec['base_design'] = design(task, task['initial'], nominal=True)
    spec['supply_branch'] = task['branch']
    spec['branch_equations'] = dict(
        direct='ih=max((abs(vh)-max(vs,0)-2*diode_V)/bridge_series_ohm,0); storage_current=ih.',
        converter='ih=max(abs(vh)-2*diode_V,0)/R; storage_current=0.65*max(abs(vh)-2*diode_V,0)*ih/max(vs,0.1).')
    spec['branch_costs'] = ('Existing converter branch additionally charges A/B/C/D idle power '
        '0.5/180/2/0.5 microW and B envelope energy. Existing direct branch does not charge '
        'that extra term. Both retain comparator/reference, leakage and actual envelope loads. '
        'C adds 5 microJ per SAVE on either branch. D dissipates actual parallel-shunt power.')
    if task['width'] == 'wide':
        spec['controls'].update(rearm_V='Envelope rearm voltage; use below threshold_V.',
            poll_s='Polling interval in seconds when MCU polls.',
            R_ohm='Converter input resistance; INERT in direct branch.',
            S_setting_V='Parallel shunt conduction threshold; effective only with D.',
            shunt_ohm='Parallel shunt resistance; effective only with D.',
            A='Auxiliary resonator/envelope wake-up.', B='Active envelope filter.',
            C='Additional FRAM.', D='Voltage-dependent parallel resistive shunt.')
    return dict(id=task['id'], initial=copy.deepcopy(task['initial']),
                domain=copy.deepcopy(task['domain']), spec=spec)


def _compact(result):
    return {k: copy.deepcopy(result[k]) for k in
            ('pass_', 'terminal', 'slack', 'base', 'fidelity', 'runtime_s') if k in result}


def _facts(actual, env):
    m, events = actual['metrics'], actual['events']
    times, y = np.asarray(actual['trace']['t']), np.asarray(actual['trace']['y'])
    return dict(pass_=actual['verdict'] == 'PASS',
        terminal={k: m[k] for k in ('faults', 'delivered_on_time', 'false_reports',
            'brownouts', 'peak_stress_MPa', 'peak_tip_mm')},
        slack=dict(delivery=m['delivered_on_time']/m['faults']-1,
            false_reports=-m['false_reports'], brownouts=-m['brownouts'],
            stress=1-m['peak_stress_MPa']/env['stress_limit_MPa'],
            travel=1-m['peak_tip_mm']/env['tip_travel_limit_mm']),
        base=dict(max_storage_V=float(y[:, 6].max()),
            storage_before_first_event_V=float(np.interp(7.99, times, y[:, 6])),
            main_peak_voltage_V=float(abs(y[:, 2]).max()), aux_peak_voltage_V=float(abs(y[:, 5]).max()),
            envelope_peak_V=float(y[:, 7].max()), cold_charge_ready_s=m['cold_charge_ready_s'],
            stages={k: sum(e['event'] == k for e in events) for k in
                ('WAKE', 'BOOT', 'SAMPLE', 'INFER', 'CONFIRM', 'REJECT', 'SAVE', 'TX', 'ACK', 'RECEIVED', 'BROWNOUT')}),
        fidelity='full transient', runtime_s=actual['runtime_s'])


def _timeout(signum, frame):
    raise RuntimeError(TIMEOUT)


def evaluate(task, x):
    global LEGACY
    d, env = design(task, x), task['private']['task']
    key = json.dumps([d, env], sort_keys=True)
    ident = hashlib.sha256(key.encode()).hexdigest()[:24]
    CACHE.mkdir(exist_ok=True)
    with LOCK, (CACHE/(ident+'.lock')).open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = CACHE/(ident+'.json')
        if path.exists():
            return json.loads(path.read_text()) | dict(cost=dict(full=0, numeric=0), reused=True)
        if LEGACY is None:
            LEGACY = json.loads(Path(MANIFEST['sources']['physics.json']).read_text())['cache']
        if key in LEGACY:
            return _compact(LEGACY[key]) | dict(evaluation_id=ident, cost=dict(full=0, numeric=0),
                reused=True, source=dict(kind='legacy_exact_input', path=MANIFEST['sources']['physics.json']))
        error_path = CACHE/(ident+'.execution-error.json')
        if error_path.exists():
            raise RuntimeError(json.loads(error_path.read_text())['error'])
        previous = signal.signal(signal.SIGALRM, _timeout)
        signal.setitimer(signal.ITIMER_REAL, 120)
        try:
            actual = simulate(d, env)
        except RuntimeError as error:
            if str(error) == TIMEOUT:
                error_path.write_text(json.dumps(dict(evaluation_id=ident, status='TOOL_ERROR',
                    error=str(error), scientific_result=None, limit_s=120))+'\n')
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
        result = _facts(actual, env) | dict(evaluation_id=ident, cost=dict(full=1, numeric=0),
            reused=False, source=dict(kind='new_full_transient'))
        path.write_text(json.dumps(result, separators=(',', ':'))+'\n')
        return result


def feedback(task, x, result):
    return dict(evaluation_id=result['evaluation_id'], current_design=copy.deepcopy(x), pass_=result['pass_'],
        terminal=copy.deepcopy(result['terminal']), slack=copy.deepcopy(result['slack']),
        fidelity=result['fidelity'], measurements=copy.deepcopy(result['base']))
