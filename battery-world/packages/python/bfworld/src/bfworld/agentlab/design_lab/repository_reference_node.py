"""Executable nominal piezo reference: modal source, storage, host events, RX.

The task fixes excitation, current envelopes and conversion efficiency. Device
variables are beam geometry, storage and the participant's compiled schedule.
No PMIC switching, target-MCU peripheral or RF equivalence is assumed here.
"""
import csv
import io
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from ..store import canonical
from .repository import file_hash

VERSION = 'piezo-reference-v1'


def environment():
    paths = {'clang': Path('/Library/Developer/CommandLineTools/usr/bin/clang'), 'ngspice': Path(shutil.which('ngspice') or '/opt/homebrew/bin/ngspice'),
             'sandbox': Path('/usr/bin/sandbox-exec')}
    if not all(p.is_file() for p in paths.values()): raise ValueError('REFERENCE_TOOL_MISSING')
    functions = (modal, sandbox_run, spice, trace, integral, firmware_events, run)
    return {'version': VERSION, 'execution_sources': {f.__name__: hashlib.sha256(inspect.getsource(f).encode()).hexdigest() for f in functions},
            'tools': {k: {'path': str(p), 'sha256': file_hash(p)} for k, p in paths.items()}}


def modal(design, scenario):
    """Cubic tip-normalized assumed mode; consistent mass, force and coupling."""
    L, b, hs, hp, mt = (design[k] for k in ('length_m', 'width_m', 'substrate_m', 'piezo_m', 'tip_mass_kg'))
    if not (0.02 <= L <= 0.1 and 0.002 <= b <= 0.03 and 5e-5 <= hs <= 0.001 and
            5e-5 <= hp <= 0.001 and 0 <= mt <= 0.02): raise ValueError('REFERENCE_GEOMETRY_DOMAIN')
    material = scenario['material']
    Es, Ep, rs, rp, d31, eps = (material[k] for k in ('substrate_E_pa', 'piezo_E_pa', 'substrate_density',
        'piezo_density', 'd31_m_v', 'relative_permittivity'))
    ys, yp = hs/2, hs+hp/2
    yn = (Es*hs*ys + Ep*hp*yp)/(Es*hs + Ep*hp)
    EI = Es*b*(hs**3/12 + hs*(ys-yn)**2) + Ep*b*(hp**3/12 + hp*(yp-yn)**2)
    mass = b*L*(rs*hs + rp*hp)
    m, forcing_mass = mass*33/140 + mt, mass*3/8 + mt
    k = 3*EI/L**3; omega0 = math.sqrt(k/m)
    c = 2*scenario['damping_ratio']*m*omega0
    theta = -d31*Ep*b*(yp-yn)*1.5/L
    cp = eps*8.8541878128e-12*b*L/hp
    omega = 2*math.pi*scenario['frequency_hz']; resistance = scenario['electrical_load_ohm']
    impedance = 1/(1/resistance + 1j*omega*cp)
    force = forcing_mass*scenario['acceleration_peak_m_s2']
    x = force/(k-m*omega**2+1j*omega*c+1j*omega*theta**2*impedance)
    voltage = 1j*omega*theta*impedance*x
    return {'mass_kg': m, 'forcing_mass_kg': forcing_mass, 'stiffness_n_m': k, 'damping_n_s_m': c,
        'theta_n_v': theta, 'capacitance_f': cp, 'force_n': force, 'frequency_hz': omega0/(2*math.pi),
        'power_w': abs(voltage)**2/(2*resistance), 'voltage_peak_v': abs(voltage), 'tip_peak_m': abs(x),
        'mode': 'phi(x)=x^2*(3L-x)/(2L^3); integral phi^2=33L/140; integral phi=3L/8'}


def sandbox_run(command, root, timeout=30):
    # Participant C can only write its isolated run directory; the environment is clean.
    escaped = str(root.resolve()).replace('\\', '\\\\').replace('"', '\\"')
    policy = '(version 1)(deny default)(allow process*)(allow sysctl-read)(allow mach-lookup)' + \
        '(allow file-read* (subpath "/usr") (subpath "/System") (subpath "/Library")' + \
        ' (subpath "/opt/homebrew") (subpath "/private/etc") (subpath "/private/var/db/dyld")' + \
        ' (literal "/") (literal "/dev/null") (literal "/dev/random") (literal "/dev/urandom")' + \
        ' (subpath "'+escaped+'"))' + \
        '(allow file-write* (subpath "'+escaped+'") (literal "/dev/null"))'
    return subprocess.run(['/usr/bin/sandbox-exec', '-p', policy, *command], cwd=root,
        env={'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'TMPDIR': str(root), 'LANG': 'C'},
        capture_output=True, text=True, timeout=timeout)


def spice(root, filename, content):
    (root/filename).write_text(content)
    result = sandbox_run([str(environment()['tools']['ngspice']['path']), '-b', filename], root)
    (root/(filename+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode: raise ValueError('REFERENCE_SPICE_FAILED: '+result.stderr[-1000:])


def trace(path):
    if not path.is_file(): raise ValueError('REFERENCE_OUTPUT_MISSING: '+path.name)
    rows = [[float(v) for v in line.split()] for line in path.read_text().splitlines() if line.strip()]
    if len(rows) < 2 or any(not all(math.isfinite(x) for x in r) for r in rows): raise ValueError('REFERENCE_TRACE_INVALID')
    return rows


def integral(rows, column, start=None):
    rows = [r for r in rows if start is None or r[0] >= start]
    return sum((b[0]-a[0])*(a[column]+b[column])/2 for a, b in zip(rows, rows[1:]))


def firmware_events(raw, scenario):
    reader = csv.DictReader(io.StringIO(raw))
    if reader.fieldnames != ['t_s', 'duration_s', 'state', 'seq', 'value', 'crc']: raise ValueError('FIRMWARE_EVENT_SCHEMA')
    rows = []
    for r in reader:
        if r['state'] not in scenario['state_currents_a']: raise ValueError('UNKNOWN_FIRMWARE_STATE')
        value = {'t_s': float(r['t_s']), 'duration_s': float(r['duration_s']), 'state': r['state'],
                 'seq': int(r['seq']), 'value': int(r['value']), 'crc': int(r['crc'])}
        if not math.isfinite(value['t_s']) or not math.isfinite(value['duration_s']) or not (
            0 <= value['t_s'] and 0 < value['duration_s'] <= 1 and value['t_s']+value['duration_s'] <= scenario['duration_s']):
            raise ValueError('FIRMWARE_EVENT_TIME')
        rows.append(value)
    if not rows or len(rows) > 10000: raise ValueError('FIRMWARE_EVENT_COUNT')
    if any(a['t_s']+a['duration_s'] > b['t_s'] for a, b in zip(rows, rows[1:])): raise ValueError('FIRMWARE_EVENT_OVERLAP')
    return rows


def run(root, system, inputs, source_lookup=None):
    from .native_slot import native_slot
    scenario = system['task_definition']['scenario']; design = json.loads(inputs['design.json'])
    m = modal(design, scenario)
    capacitance = design['storage_f']
    if not 1e-6 <= capacitance <= 0.02: raise ValueError('REFERENCE_STORAGE_DOMAIN')
    (root/'main.c').write_text(inputs['firmware/main.c'])
    compiled = sandbox_run([environment()['tools']['clang']['path'], '-isysroot', '/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk',
                            '-std=c11', '-Wall', '-Wextra', '-Werror', 'main.c', '-o', 'firmware'], root)
    (root/'build.log').write_text(compiled.stdout+compiled.stderr)
    if compiled.returncode: raise ValueError('REFERENCE_FIRMWARE_BUILD: '+compiled.stderr[-1500:])
    binary_sha256 = file_hash(root/'firmware')
    process = sandbox_run([str(root/'firmware')], root, 5)
    if process.returncode: raise ValueError('REFERENCE_FIRMWARE_EXECUTION: '+process.stderr[-1000:])
    if file_hash(root/'firmware') != binary_sha256: raise ValueError('REFERENCE_FIRMWARE_SELF_MODIFICATION')
    events = firmware_events(process.stdout, scenario)
    freq, resistance = scenario['frequency_hz'], scenario['electrical_load_ohm']
    source = f'''Piezo modal two-port, SI force-voltage / velocity-current analogy
Vforce drive 0 SIN(0 {m['force_n']:.14g} {freq:.14g})
Lmass drive damper {m['mass_kg']:.14g}
Rdamper damper spring {m['damping_n_s_m']:.14g}
Cspring spring coupling {1/m['stiffness_n_m']:.14g}
Bcouple coupling sense V={m['theta_n_v']:.14g}*v(piezo)
Vsense sense 0 0
Bpiezo 0 piezo I={m['theta_n_v']:.14g}*i(Vsense)
Cp piezo 0 {m['capacitance_f']:.14g}
Rl piezo 0 {resistance:.14g}
.control
set wr_singlescale
tran {1/freq/160:.14g} {120/freq:.14g} 0 {1/freq/160:.14g}
let power=v(piezo)*v(piezo)/{resistance:.14g}
wrdata source.dat v(piezo) power
quit
.endc
.end
'''
    currents = scenario['state_currents_a']; idle = currents['idle']
    pairs = [(0.0, idle)]
    for e in events:
        t, end = e['t_s'], e['t_s']+e['duration_s']
        if t <= pairs[-1][0]+1e-7: raise ValueError('REFERENCE_EVENT_GAP_REQUIRED')
        pairs.extend([(t-1e-7, idle), (t, currents[e['state']]),
                      (end-1e-7, currents[e['state']]), (end, idle)])
    pairs.append((scenario['duration_s'], idle))
    if any(b[0] <= a[0] for a, b in zip(pairs, pairs[1:])): raise ValueError('REFERENCE_LOAD_TIME_ORDER')
    with native_slot():
        cached = source_lookup(source) if source_lookup else None
        if cached:
            for filename, raw in cached['artifacts'].items(): (root/filename).write_bytes(raw)
        else: spice(root, 'source.cir', source)
        rows = trace(root/'source.dat'); stable = [r for r in rows if r[0] >= 100/freq]
        power = integral(stable, 2)/(stable[-1][0]-stable[0][0])
        available = power*scenario['conversion_efficiency']
        pwl = '\n+ '.join(' '.join(f'{t:.12g} {i:.12g}' for t, i in pairs[n:n+6]) for n in range(0, len(pairs), 6))
        storage = f'''Nominal energy interface: fixed harvested average power and declared conversion efficiency
Cstore storage 0 {capacitance:.14g} IC={scenario['initial_storage_v']:.14g}
Bharvest 0 harvesting I={available:.14g}/max(v(storage),0.2)
Vharvest harvesting storage 0
Iload load 0 PWL({pwl})
Vload load 0 0
Vconsume storage consuming 0
Bconsume consuming 0 I={scenario['rail_v']:.14g}*i(Vload)/(-max(v(storage),0.2))*max(min(v(storage)/0.2,1),0)
Vclamp storage clamping 0
Bclamp clamping 0 I=max(v(storage)-{scenario['storage_max_v']:.14g},0)*0.1
.control
set wr_singlescale
tran 0.01 {scenario['duration_s']:.14g} 0 0.01 uic
let harvest=v(storage)*i(Vharvest)
let consume=v(storage)*i(Vconsume)
let clamp=v(storage)*i(Vclamp)
wrdata storage.dat v(storage) harvest consume clamp
quit
.endc
.end
'''
        spice(root, 'storage.cir', storage)
    storage_rows = trace(root/'storage.dat')
    metrics = {'source': m, 'native_source_power_w': power, 'available_power_w': available,
               'source_relative_error': abs(power-m['power_w'])/max(m['power_w'], 1e-30),
               'source_reused_from': cached['execution_id'] if cached else None,
               'native_dispatches': ['storage'] if cached else ['source','storage'],
               'events': len(events), 'minimum_storage_v': min(r[1] for r in storage_rows),
               'final_storage_v': storage_rows[-1][1], 'firmware_sha256': binary_sha256,
               'scope': 'linear modal source, average-power conversion, compiled host schedule, digital receiver'}
    outputs = {p: (root/p).read_bytes() for p in ['source.cir', 'source.cir.log', 'source.dat',
        'storage.cir', 'storage.cir.log', 'storage.dat', 'build.log', 'firmware']}
    outputs.update({'events.csv': process.stdout, 'events.json': canonical(events), 'load.json': canonical(pairs),
                    'source-model.json': canonical(m), 'design.json': inputs['design.json'], 'main.c': inputs['firmware/main.c']})
    return metrics, outputs


def independent_check(repo, system, execution):
    """Recompute the load from executed events; assess RX only with sufficient supply."""
    from .repository_task_standards import REFERENCE_RULES
    rules = system['task_definition'].get('standards', {}).get('reference_rules') or REFERENCE_RULES
    scenario = system['task_definition']['scenario']
    def raw(path): return (repo.root/'blobs'/execution['artifacts'][path]['sha256']).read_text()
    events = firmware_events(raw('events.csv'), scenario)
    rows = [[float(v) for v in line.split()] for line in raw('storage.dat').splitlines() if line.strip()]
    source_rows = [[float(v) for v in line.split()] for line in raw('source.dat').splitlines() if line.strip()]
    model = json.loads(raw('source-model.json')); end = source_rows[-1][0]; window = 20/scenario['frequency_hz']
    selected = [r for r in source_rows if r[0] >= end-window]
    source_power = integral(selected, 2)/(selected[-1][0]-selected[0][0])
    source_error = abs(source_power-model['power_w'])/max(model['power_w'], 1e-30)
    delivered, failed, frame_errors = [], [], []
    previous_sample = None
    for e in events:
        if e['state'] == 'sample': previous_sample = e
        if e['state'] != 'tx': continue
        witness = [r[1] for r in rows if e['t_s'] <= r[0] <= e['t_s']+e['duration_s']]
        valid = (0 <= e['seq'] <= 65535 and e['value'] == scenario['sensor_value'] and
                 e['crc'] == ((e['seq'] ^ e['value'] ^ 0xA5) & 255) and previous_sample is not None and
                 previous_sample['seq'] == e['seq'] and previous_sample['value'] == e['value'] and
                 previous_sample['duration_s'] >= scenario['minimum_sample_s'] and e['duration_s'] >= scenario['minimum_tx_s'])
        if not valid: frame_errors.append(e['seq'])
        sample_witness = [r[1] for r in rows if previous_sample and previous_sample['t_s'] <= r[0] <= previous_sample['t_s']+previous_sample['duration_s']]
        if valid and witness and sample_witness and min(witness+sample_witness) >= scenario['minimum_storage_v']: delivered.append(e['seq'])
        else: failed.append(e['seq'])
    pairs = json.loads(raw('load.json'))
    expected_charge = scenario['state_currents_a']['idle']*scenario['duration_s'] + sum(
        (scenario['state_currents_a'][e['state']]-scenario['state_currents_a']['idle'])*e['duration_s'] for e in events)
    actual_charge = sum((b[0]-a[0])*(a[1]+b[1])/2 for a,b in zip(pairs,pairs[1:]))
    load_equal = abs(actual_charge-expected_charge) <= max(rules['charge_absolute_tolerance_c'], expected_charge*rules['charge_relative_tolerance'])
    unique = len(delivered) == len(set(delivered))
    minimum = system['task_definition']['acceptance']['receiver_service']['minimum_packets']
    design = json.loads(raw('design.json'))
    delta_energy = .5*design['storage_f']*(rows[-1][1]**2-scenario['initial_storage_v']**2)
    net_energy = integral(rows,2)-integral(rows,3)-integral(rows,4)
    energy_error = abs(delta_energy-net_energy)
    energy_valid = min(r[1] for r in rows) >= -rules['negative_voltage_tolerance_v'] and energy_error <= max(rules['energy_absolute_tolerance_j'],abs(net_energy)*rules['energy_relative_tolerance'])
    linear = model['tip_peak_m'] <= rules['tip_displacement_length_ratio_max']*design['length_m']
    return {'source_model': {'status': 'PASS' if source_error < rules['source_relative_error_lt'] and linear else 'FAIL', 'relative_error': source_error,
                    'linear_motion_domain':linear,
                    'source_power_w': source_power, 'analytic_power_w': model['power_w']},
            'load_binding': {'status': 'PASS' if load_equal else 'FAIL', 'actual_charge_c': actual_charge, 'expected_charge_c': expected_charge},
            'power_service': {'status': 'PASS' if len(delivered) >= minimum and not failed and energy_valid else 'FAIL',
                    'delivered_packets': len(delivered), 'failed_sequences': failed, 'final_storage_v': rows[-1][1],
                    'stored_energy_change_j':delta_energy, 'net_input_energy_j':net_energy, 'energy_residual_j':energy_error},
            'receiver_service': {'status': 'PASS' if len(delivered) >= minimum and unique and not frame_errors else 'FAIL',
                    'received_sequences': delivered, 'frame_errors': frame_errors, 'minimum_packets': minimum}}
