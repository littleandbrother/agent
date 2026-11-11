"""Thirty-two frozen full-transient tasks. Private qualification is never learner input."""
import copy
import concurrent.futures
import json
from pathlib import Path

import numpy as np

from sim import TASK, G, beam

HERE = Path(__file__).resolve().parent
OUT = HERE / "funnel"
BASE = json.loads((HERE / "design.json").read_text())
DOMAIN = dict(main_length_mm=[24., 42.], aux_length_mm=[11., 24.], C_uF=[80., 1000.],
              gate_V=[1.9, 3.2], threshold_V=[.15, 20.], rearm_V=[.05, 10.], poll_s=[.015, 4.],
              R_ohm=[2000., 300000.], S_setting_V=[1., 50.], shunt_ohm=[500., 100000.],
              A=[False, True], B=[False, True], C=[False, True], D=[False, True])
INITIAL = dict(main_length_mm=34., aux_length_mm=16., C_uF=100., gate_V=2.9,
               threshold_V=.55, rearm_V=.18, poll_s=.1, R_ohm=45000., S_setting_V=15., shunt_ohm=3000.,
               A=True, B=False, C=False, D=False)
WITNESS = INITIAL | dict(main_length_mm=30., aux_length_mm=18., C_uF=150.)
SPEC = dict(
    objective="Deliver all four target events before their deadlines, zero false reports and brownouts, within stress/travel limits.",
    uncertainty="Fixed but undisclosed mounting/manufacturing factors may alter effective beam lengths. Factors remain unchanged during one task.",
    controls=dict(main_length_mm="Nominal harvester length (mm)", aux_length_mm="Nominal auxiliary beam length (mm)",
        C_uF="Storage capacitance (microfarads)", gate_V="MCU supply startup voltage; brownout 1.8 V",
        threshold_V="Envelope wake voltage", rearm_V="Envelope voltage below which the trigger rearms; use below threshold_V", poll_s="Polling interval with no wake modules",
        R_ohm="Regulated rectifier input resistance (ohms)", S_setting_V="Voltage at which D begins parallel shunt conduction",
        shunt_ohm="D shunt resistance (ohms)", A="Install passive auxiliary resonator/envelope wake-up",
        B="Install active filter wake-up", C="Install additional FRAM", D="Install voltage-dependent parallel resistive shunt"),
    modules=dict(A="0.5 microW idle; passive resonator and envelope detector", B="180 microW idle; active envelope, 2 V/g",
                 C="2 microW idle and 5 microJ per SAVE", D="0.5 microW idle plus actual shunt dissipation"),
    acquisition="128 samples / 2048 Hz; fixed classifier and finite BOOT/INFER/SAVE/TX/ACK loads.",
    physics=["Mechanical and electrical loads are coupled; changing geometry or impedance shifts response.",
             "A/B replace repeated polling with envelope-triggered acquisition. Installing components incurs their actual modeled costs.",
             "D can reduce displacement/stress while removing harvested energy.",
             "Storage helps active bursts but requires energy to reach startup; open-circuit voltage is not delivered service."],
    base_design=BASE)


def design_for(t, x):
    x = t['initial'] | x
    d = copy.deepcopy(BASE)
    f = t['private'].get('factors', {})
    d['harvester']['length_mm'] = x['main_length_mm'] * f.get('main_factor', 1.)
    d['trigger_beam']['length_mm'] = x['aux_length_mm'] * f.get('aux_factor', 1.)
    d['modules'] = {k: bool(x[k]) for k in 'ABCD'}
    d['circuit'].update(storage_uF=x['C_uF'], start_V=x['gate_V'], wake_high_V=x['threshold_V'],
        wake_low_V=x['rearm_V'], converter_input_R_ohm=x['R_ohm'],
        shunt_threshold_V=x['S_setting_V'], shunt_ohm=x['shunt_ohm'])
    d['firmware'].update(poll_s=x['poll_s'])
    d['firmware'].update(t['private'].get('firmware_patch', {}))
    return d


def public_task(t):
    env = t['private']['task']
    public_env = {k: v for k, v in env.items() if not k.endswith('starts_s')}
    public_env['fault_count'] = len(env['fault_starts_s'])
    public_env['event_schedule'] = 'Four target events; timing is hidden truth and never detector input.'
    # The manual shows the task's actual fixed firmware and nominal initial
    # design, never an old successful configuration or hidden effective length.
    nominal = dict(t, private=t['private'] | dict(factors={}))
    spec = t['spec'] | dict(environment=public_env, base_design=design_for(nominal,t['initial']))
    spec['detector_wiring'] = ('Harvester voltage drives the envelope independently of A/B; fixed wake_from_harvester=True.'
        if t['private'].get('firmware_patch',{}).get('wake_from_harvester') else
        'A enables the auxiliary-beam envelope; B enables active envelope gain; with neither, MCU polls.')
    return dict(id=t['id'], initial=t['initial'], domain=t['domain'], spec=spec)


def _energy_upper(t, end):
    """Cauchy bound from -M*a*u-c*u² <= M²*a²/(4c), zero initial energy.

    Interval bounds on M and c cover every allowed nominal length, not samples.
    The acceleration integral is bounded above by piecewise sums of amplitudes;
    this deliberately includes all sinusoidal cross terms and window tapers.
    """
    p, env, ksum = t['private'], t['private']['task'], 0.
    for name, axis, factor in [('harvester', 'main_length_mm', 'main_factor'), ('trigger_beam', 'aux_length_mm', 'aux_factor')]:
        lo, hi = np.array(t['domain'][axis]) * p.get('factors', {}).get(factor, 1.)
        b0, b1 = beam(BASE[name] | dict(length_mm=lo)), beam(BASE[name] | dict(length_mm=hi))
        # k falls as L^-3, m rises with L; independent endpoint bounds are conservative.
        cmin = 2 * BASE[name]['damping_ratio'] * np.sqrt(b1['k'] * b0['m'])
        ksum += b1['forcing_mass'] ** 2 / (4 * cmin)
    edges = {0., end}
    for kind in ('fault', 'nuisance'):
        for start in env[kind + '_starts_s']:
            edges.update([min(end, max(0., start)), min(end, max(0., start + env[kind + '_duration_s']))])
    points = sorted(edges)
    integral = 0.
    for a, b in zip(points, points[1:]):
        mid = (a+b)/2
        amp = env['background_peak_g']
        for kind in ('fault', 'nuisance'):
            amp += sum(env[kind + '_peak_g'] for s in env[kind + '_starts_s']
                       if s <= mid < s + env[kind + '_duration_s'])
        integral += (G*amp)**2 * (b-a)
    # B's acceleration-driven envelope is not a passive transducer in this
    # representative kernel. Bound its possible supply credit explicitly:
    # ve <= 2*max|a/g| and negative ve_dot >= -ve/.04.
    peak = env['background_peak_g'] + env['fault_peak_g'] + env['nuisance_peak_g']
    active_credit = BASE['circuit']['envelope_nF']*1e-9 * (2*peak)**2 * end/.04
    return float(ksum * integral + active_credit)


def envelope(t):
    """Fact-only necessary bound, scoped to the exact public action rectangle."""
    env, f = t['private']['task'], BASE['firmware'] | t['private'].get('firmware_patch', {})
    digital = sum(f[n+'_s'] * f[n+'_mW'] * 1e-3 for n in ('boot', 'infer', 'save', 'tx', 'ack'))
    digital += f['sample_count']/f['sample_Hz'] * f['sample_mW'] * 1e-3
    need = len(env['fault_starts_s']) * digital / BASE['circuit']['regulator_efficiency']
    total = _energy_upper(t, env['duration_s'])
    first_end = env['fault_starts_s'][0] + env['delivery_deadline_s']
    early = _energy_upper(t, first_end)
    start = .5 * t['domain']['C_uF'][0] * 1e-6 * t['domain']['gate_V'][0]**2
    return dict(scope='Entire declared geometry/architecture/parameter rectangle; zero initial energy; fixed original transient consumer.',
        input_energy_upper_J=total, four_service_energy_lower_J=need,
        first_deadline_input_upper_J=early, minimum_startup_storage_J=start,
        all_designs_excluded_by_energy=total < need,
        all_designs_excluded_before_first_deadline=early < start,
        derivation='For each beam, -M*a*u-c*u^2 <= M^2*a^2/(4c). M upper and c lower are interval endpoint bounds. Sinusoidal input is bounded by piecewise amplitude sums, including all cross terms. The active B envelope is additionally credited Ce*(2*max|a/g|)^2*T/.04, bounding any modeled negative envelope-power contribution; remaining loads are passive.')


def build_tasks():
    """Ordered settings fixed before any Agent result; no method-dependent filtering."""
    rows = []
    for family in ('1A','1B','2A','2B','3A','3B','4A','4B'):
        for i in range(4):
            task = copy.deepcopy(TASK)
            task.update(background_peak_g=.16+.01*i, fault_starts_s=[8.4+.13*i,14.4+.13*i,20.4+.13*i,26.4+.13*i])
            initial, witness, factors, fw = INITIAL.copy(), WITNESS.copy(), {}, {}
            domain = copy.deepcopy(DOMAIN)
            if family == '1A':
                initial.update(main_length_mm=33.5+.4*i, aux_length_mm=18.)
            elif family == '1B':
                task['fault_starts_s'] = [6.0+.4*i,13.,19.,25.]
                initial.update(main_length_mm=30., aux_length_mm=18., C_uF=800., gate_V=3.2)
                witness.update(gate_V=2.6)
            elif family == '2A':
                initial.update(A=False, main_length_mm=30., aux_length_mm=18.)
            elif family == '2B':
                task.update(background_peak_g=.28+.01*i, fault_Hz=45., fault_peak_g=3.+.05*i, fault_duration_s=.20,
                            stress_limit_MPa=100., tip_travel_limit_mm=3.)
                fw.update(target_band_Hz=[30.,65.], minimum_target_rms_g=.5, wake_from_harvester=True)
                initial.update(main_length_mm=30., aux_length_mm=18., threshold_V=4.)
                witness.update(main_length_mm=27.5, C_uF=100., gate_V=2.5, D=True, A=False,
                               threshold_V=8., rearm_V=3., S_setting_V=5., shunt_ohm=50000.)
            elif family == '3A':
                factors = {'main_factor': [.81,.86,.91,.96][i]} if i < 2 else {'aux_factor': [1.,1.,1.18,1.27][i]}
                witness.update(main_length_mm=30./factors.get('main_factor',1.), aux_length_mm=18./factors.get('aux_factor',1.))
            elif family == '3B':
                factors = dict(main_factor=[.83,.87,.91,.95][i], aux_factor=[1.16,1.20,1.24,1.28][i])
                initial.update(C_uF=80.)
                witness.update(main_length_mm=30./factors['main_factor'], aux_length_mm=18./factors['aux_factor'], C_uF=200.)
            elif family == '4A':
                task.update(background_peak_g=.0001*(i+1), fault_peak_g=.0003,
                            nuisance_peak_g=.0003)
                witness = None
            else:
                task.update(background_peak_g=.003+.0005*i, fault_starts_s=[.015+.005*i,14.,20.,26.],
                            fault_peak_g=.025, nuisance_starts_s=[3.,10.,17.,24.], nuisance_peak_g=.8)
                witness = None
            ident = f'N{len(rows)+1:02d}'
            rows.append(dict(id=ident, subgroup=family, initial=initial, domain=domain, spec=copy.deepcopy(SPEC),
                private=dict(factors=factors, task=task, firmware_patch=fw, witness=witness)))
    return rows


def tasks():
    return json.loads((OUT/'tasks.json').read_text()) if (OUT/'tasks.json').exists() else build_tasks()


def _qualify(t):
    from funnel_physics import evaluate
    x = t['private']['witness']
    if x is None:
        b = envelope(t)
        return dict(id=t['id'], subgroup=t['subgroup'], status='PROVEN_INFEASIBLE' if
            b['all_designs_excluded_by_energy'] or b['all_designs_excluded_before_first_deadline'] else 'NOT_QUALIFIED', proof=b)
    r = evaluate(t, x)
    return dict(id=t['id'], subgroup=t['subgroup'], status='FEASIBLE_WITNESS' if r['pass_'] else 'NOT_QUALIFIED',
                input=x, execution=dict(design=design_for(t,x), environment=t['private']['task']), result=r)


if __name__ == '__main__':
    import sys
    OUT.mkdir(exist_ok=True)
    if '--qualify' in sys.argv:
        rows = tasks()
        with concurrent.futures.ProcessPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(_qualify, rows))
        path = OUT/'qualification.json'
        receipt = json.loads(path.read_text()) if path.exists() else dict(generation_rule='Fixed ordered settings in build_tasks; before model runs.', attempts=[], count_full=0)
        receipt['attempts'] += results
        receipt['count_full'] += sum(r.get('result',{}).get('cost',{}).get('full',0) for r in results)
        path.write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps({r['id']:dict(status=r['status'], terminal=r.get('result',{}).get('terminal')) for r in results},indent=2))
        raise SystemExit
    rows = build_tasks()
    for t in rows:
        t['private']['proof'] = envelope(t)
    (OUT/'tasks.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps({t['id']: dict(subgroup=t['subgroup'], upper=t['private']['proof']['input_energy_upper_J'],
        lower=t['private']['proof']['four_service_energy_lower_J'], early=t['private']['proof']['first_deadline_input_upper_J'],
        startup=t['private']['proof']['minimum_startup_storage_J']) for t in rows if t['subgroup'][0]=='4'}, indent=2))
