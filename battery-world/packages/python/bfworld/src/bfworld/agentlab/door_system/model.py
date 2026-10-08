"""Full prescribed door cycle and reciprocal work; SI coordinates throughout.

Magnetic field and potential share a uniform cuboid model. Their agreement checks
implementation, not independent FEM confirmation or physical calibration.
"""
from functools import lru_cache
import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.integrate import solve_ivp, cumulative_trapezoid
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import brentq
from ..simulation_chain.native import MU0
from ..simulation_chain.contracts import ChainError, write_json

def angle_path(t, frozen):
    task = frozen['task']; c, h, o = [task[k] for k in ('closing_s', 'holding_s', 'opening_s')]
    t = np.asarray(t); a = np.deg2rad(task['angle_deg'])
    return np.where(t < c, a * (1-t/c), np.where(t < c+h, 0., a*np.clip((t-c-h)/o, 0, 1)))

def coordinates(angle, mechanical):
    x = (.904-mechanical['gap_mm']/1000); y = (.075265+mechanical['closed_dz_mm']/1000)
    return .904-(x*np.cos(angle)-y*np.sin(angle)), x*np.sin(angle)+y*np.cos(angle)-.075265

@lru_cache(maxsize=8)
def charge_nodes(n):
    g, w = leggauss(n); yy, zz = np.meshgrid(g, g); ww = np.outer(w, w).ravel()
    return np.column_stack([np.zeros(n*n), yy.ravel()*.005, zz.ravel()*.005]), np.column_stack([np.zeros(n*n), yy.ravel()*.01, zz.ravel()*.01]), ww

def field_energy(angle, q, mechanical, br=1.25, n=6):
    tip, driver, w = charge_nodes(n); dx, dz = coordinates(angle, mechanical)
    rot = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]])
    force = np.zeros(3); energy = 0.
    for a in (-1, 1):
        ta = tip.copy(); ta[:, 0] = a*.005
        for b in (-1, 1):
            db = driver.copy(); db[:, 0] = b*.01; db = db@rot.T+[dx, 0, dz-q]
            r = ta[:, None, :]-db[None, :, :]; distance = np.linalg.norm(r, axis=2)
            if distance.min() < 1e-5: raise ChainError('out_of_domain', 'Magnet contact/singular interaction')
            weights = a*b*w[:, None]*w[None, :]
            force += np.sum((weights/distance**3)[:, :, None]*r, axis=(0, 1))
            energy += np.sum(weights/distance)
    factor = mechanical['polarity']*MU0/(4*np.pi)*(br/MU0)**2*.005**2*.01**2
    return force*factor, float(energy*factor)

def force_table(directory, design):
    # Dense where the rotating driver passes the tip; whole 0..65 degree domain
    # checked, including high-gradient cells rather than only random 0..15 points.
    angles = np.deg2rad(np.unique(np.r_[np.linspace(0, 10, 81), np.linspace(10, 25, 31), np.linspace(25, 65, 25)]))
    qs = np.linspace(-.008, .008, 65)
    values = np.array([[field_energy(a, q, design['mechanical'])[0][2] for q in qs] for a in angles])
    np.savez(directory/'force-table.npz', angles=angles, qs=qs, values=values)
    interp = RegularGridInterpolator((angles, qs), values, bounds_error=True)
    peak = max(np.max(abs(values)), 1e-9)
    rng = np.random.default_rng(17); checks = []
    cells = np.argwhere(abs(np.diff(values, axis=0)) > .05*peak)
    points = [[rng.uniform(0, angles[-1]), rng.uniform(qs[0], qs[-1])] for _ in range(64)]
    points += [[(angles[i]+angles[i+1])/2, qs[j]] for i, j in cells[::max(1, len(cells)//32)][:32]]
    for a, q in points:
        reference = field_energy(a, q, design['mechanical'], n=10)[0][2]
        coarse = field_energy(a, q, design['mechanical'], n=6)[0][2]
        checks.append({'angle_deg': float(np.rad2deg(a)), 'tip_m': q,
                       'interpolation_error_over_peak': abs(float(interp([[a, q]])[0])-reference)/peak,
                       'quadrature_error_over_peak': abs(coarse-reference)/peak})
    result = {'schema_version': 'bf-door-rotated-domain-v1', 'design_id': design['design_id'],
              'tip_m': [-.008, .008], 'angle_deg': [0., 65.], 'checks': checks,
              'max_interpolation_error_over_peak': max(r['interpolation_error_over_peak'] for r in checks),
              'max_quadrature_error_over_peak': max(r['quadrature_error_over_peak'] for r in checks),
              'independent_confirmation': False, 'scope': 'Nominal model quadrature/interpolation only; all angles and high-gradient cells checked.'}
    result['interpolation_passed'] = bool(result['max_interpolation_error_over_peak'] <= design['frozen']['numerics']['interpolation_target'])
    write_json(directory/'force-domain.json', result)
    return interp, result

def initial_equilibrium(interp, rom, a):
    grid = np.linspace(-.008, .008, 129); f = lambda q: rom['k']*q-float(interp([[a, q]])[0])
    roots = []
    for x, y in zip(grid[:-1], grid[1:]):
        if f(x)*f(y) <= 0:
            r = brentq(f, x, y); eps = 1e-7
            if r-eps >= -.008 and r+eps <= .008 and (f(r+eps)-f(r-eps))/(2*eps)>0: roots.append(r)
    if not roots: raise ChainError('out_of_domain', 'No stable initial equilibrium in ROM domain')
    return min(roots, key=abs)

def resistive_screen(directory, design, rom, resistance=1e6):
    interp, domain = force_table(directory, design); frozen = design['frozen']; task = frozen['task']
    duration = sum(task[k] for k in ('closing_s', 'holding_s', 'opening_s', 'settling_s'))
    k, m, theta, cp = [rom[k] for k in ('k', 'mass', 'theta', 'cp')]
    damping = 2*frozen['model']['damping_ratio']*np.sqrt(k*m)
    q0 = initial_equilibrium(interp, rom, angle_path(0, frozen))
    def ode(t, y):
        q, u, v, loss, port, work = y
        force = float(interp([[float(angle_path(t, frozen)), np.clip(q, -.008, .008)]])[0])
        return [u, (force-k*q-damping*u-theta*v)/m, (theta*u-v/resistance)/cp,
                damping*u*u, v*v/resistance, force*u]
    def limit(t, y): return .008-abs(y[0])
    limit.terminal = True; limit.direction = -1
    sol = solve_ivp(ode, [0, duration], [q0, 0, 0, 0, 0, 0], rtol=2e-7, atol=1e-11,
                    max_step=.001, dense_output=True, events=limit)
    t = np.linspace(0, sol.t[-1], 6501); y = sol.sol(t); q, u, v = y[:3]
    angles = angle_path(t, frozen); stored = .5*m*u*u+.5*k*q*q+.5*cp*v*v
    residual = stored-stored[0]+y[3]+y[4]-y[5]
    np.savetxt(directory/'screen-waveform.csv', np.column_stack([t, angles, y.T]), delimiter=',',
               header='time_s,angle_rad,tip_m,velocity_m_s,piezo_V,damping_J,resistor_J,magnetic_work_J', comments='')
    result = {'design_id': design['design_id'], 'status': 'out_of_domain' if sol.t_events[0].size else 'completed',
              'resistance_ohm': resistance, 'peak_tip_mm': float(max(abs(q))*1000),
              'peak_piezo_V': float(max(abs(v))), 'resistor_energy_J': float(y[4, -1]),
              'initial_mechanical_J': float(.5*k*q0*q0),
              'relative_residual': float(max(abs(residual))/max(np.max(abs(y[5])), np.max(abs(stored)), 1e-12)),
              'elapsed_trajectory_s': float(t[-1]), 'interpolation_passed': domain['interpolation_passed'],
              'scope': 'Resistive ROM space screening; no PMIC/application success inference.'}
    write_json(directory/'screen-result.json', result)
    return result

def drive_ledger(directory, design, rom, t, q, u, piezo, port_J, damping_J):
    """Actuator work pays magnetic potential change AND work delivered to the beam."""
    task = design['frozen']['task']; times = np.linspace(t[0], t[-1], 5001)
    q, u, piezo = [np.interp(times, t, a) for a in (q, u, piezo)]
    angles = angle_path(times, design['frozen']); mech = design['mechanical']; eps = 1e-5
    pairs = [field_energy(a, z, mech) for a, z in zip(angles, q)]
    force = np.array([p[0][2] for p in pairs]); potential = np.array([p[1] for p in pairs])
    torque_on_driver = np.array([-(field_energy(a+eps, z, mech)[1]-field_energy(a-eps, z, mech)[1])/(2*eps) for a, z in zip(angles, q)])
    velocity = np.where(times < task['closing_s'], -np.deg2rad(task['angle_deg'])/task['closing_s'],
                        np.where((times > task['closing_s']+task['holding_s']) &
                                 (times < task['closing_s']+task['holding_s']+task['opening_s']),
                                 np.deg2rad(task['angle_deg'])/task['opening_s'], 0.))
    actuator_power = -torque_on_driver*velocity
    actuator_work = cumulative_trapezoid(actuator_power, times, initial=0)
    beam_work = cumulative_trapezoid(force*u, times, initial=0)
    magnetic_residual = potential-potential[0]+beam_work-actuator_work
    stored = .5*rom['k']*q*q+.5*rom['mass']*u*u+.5*rom['cp']*piezo*piezo
    port = np.interp(times, t, port_J); loss = np.interp(times, t, damping_J)
    total = stored-stored[0]+potential-potential[0]+port+loss-actuator_work
    scale = max(max(abs(actuator_work)), max(abs(beam_work)), max(abs(potential-potential[0])), 1e-12)
    phases = []
    start = 0.
    for name, duration in [('close', task['closing_s']), ('hold', task['holding_s']), ('open', task['opening_s']), ('settle', task['settling_s'])]:
        end = start+duration; select = (times >= start) & (times <= end)
        first, last = np.flatnonzero(select)[[0, -1]]
        phases.append({'phase': name, 'start_s': start, 'end_s': end,
                       'actuator_net_J': float(actuator_work[last]-actuator_work[first]),
                       'beam_work_J': float(beam_work[last]-beam_work[first]),
                       'port_J': float(port[last]-port[first]), 'damping_J': float(loss[last]-loss[first]),
                       'magnetic_potential_change_J': float(potential[last]-potential[first])})
        start = end
    result = {'schema_version': 'bf-door-drive-ledger-v1', 'design_id': design['design_id'], 'phases': phases,
              'actuator_net_input_J': float(actuator_work[-1]),
              'actuator_positive_input_J': float(np.trapezoid(np.maximum(actuator_power, 0), times)),
              'actuator_returned_J': float(-np.trapezoid(np.minimum(actuator_power, 0), times)),
              'initial_mechanical_J': float(stored[0]), 'initial_electric_J': 0.,
              'potential_change_J': float(potential[-1]-potential[0]), 'pmic_port_J': float(port[-1]),
              'magnetic_identity_relative_residual': float(max(abs(magnetic_residual))/scale),
              'total_relative_residual': float(max(abs(total))/scale),
              'scope': 'Same-model prescribed actuator reaction work; no measured input, hysteresis, contact or bracket compliance.'}
    result['numerical_passed'] = max(result['magnetic_identity_relative_residual'], result['total_relative_residual']) <= design['frozen']['numerics']['energy_residual_target']
    np.savetxt(directory/'drive-ledger.csv', np.column_stack([times, angles, q, potential, actuator_power, actuator_work, beam_work, port, loss, total]), delimiter=',',
               header='time_s,angle_rad,tip_m,magnetic_potential_J,actuator_power_W,actuator_work_J,beam_work_J,pmic_port_J,damping_J,total_residual_J', comments='')
    write_json(directory/'drive-ledger.json', result)
    return result
