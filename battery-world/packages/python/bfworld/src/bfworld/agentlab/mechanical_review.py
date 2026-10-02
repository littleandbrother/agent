"""Read-only diagnostic audit of a sealed loading/release model.

The controls use a resistor, not a PMIC or an application. An instantaneous
force removal is an explicitly unrealizable diagnostic control, never a design.
This module does not alter the closed-simulation apparatus or its evaluator.
"""
import json
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from .simulation_chain.contracts import file_hash, write_json


class ForceTable:
    def __init__(self, angles, qs, values):
        self.angles=np.asarray(angles);self.qs=np.asarray(qs);self.values=np.asarray(values)
        if (self.values.shape!=(len(angles),len(qs)) or not np.isfinite(self.values).all()
                or not np.isfinite(self.angles).all() or not np.isfinite(self.qs).all()
                or not (np.diff(self.angles)>0).all() or not (np.diff(self.qs)>0).all()):
            raise ValueError('INVALID_FORCE_TABLE')

    def row(self, angle):
        if not self.angles[0]<=angle<=self.angles[-1]:raise ValueError('ANGLE_OUTSIDE_DOMAIN')
        i=min(len(self.angles)-2,max(0,np.searchsorted(self.angles,angle)-1))
        f=(angle-self.angles[i])/(self.angles[i+1]-self.angles[i])
        return self.values[i]*(1-f)+self.values[i+1]*f

    def force(self, angle, q):
        return float(np.interp(q,self.qs,self.row(angle)))

    def equilibria(self, angle, stiffness):
        force=self.row(angle);g=stiffness*self.qs-force;roots=[]
        for i in range(len(self.qs)-1):
            if g[i]*g[i+1]>0:continue
            if g[i+1]==g[i]:continue  # flat/neutral interval is not a stable root
            q=self.qs[i]-g[i]*(self.qs[i+1]-self.qs[i])/(g[i+1]-g[i])
            effective=(g[i+1]-g[i])/(self.qs[i+1]-self.qs[i])
            if roots and abs(roots[-1]['q_m']-q)<1e-12:continue
            roots.append({'q_m':float(q),'effective_stiffness_N_m':float(effective),'stable':bool(effective>0)})
        return roots


def control(rom, table, spec, kind, *, resistor=1e6, max_step=.0005):
    if kind not in ('fixed_door','rotary_path','instant_force_removal','close_hold_open'):raise ValueError('UNKNOWN_CONTROL')
    k,m,theta,cp=(float(rom[n]) for n in ('k','mass','theta','cp'))
    if min(k,m,cp,resistor,max_step)<=0:raise ValueError('NONPASSIVE_PARAMETERS')
    damping=2*spec['mechanical']['damping_ratio']*np.sqrt(k*m)
    opening=spec['mechanical']['opening_s'];end=opening+2 if opening else 4
    amax=np.deg2rad(spec['mechanical']['angle_deg'])
    initial_angle=amax if kind=='close_hold_open' else 0
    q0=brentq(lambda q:k*q-table.force(initial_angle,q),table.qs[0],table.qs[-1])
    if kind=='close_hold_open':
        if opening<=0:raise ValueError('LOADING_CYCLE_REQUIRES_MOTION')
        end=2*opening+2.5
    def angle(t):
        if kind=='close_hold_open':
            if t<=opening:return amax*max(0,1-t/opening)
            return amax*min(1,max(0,(t-opening-.5)/opening))
        return amax*min(t/opening,1) if opening else 0
    def rhs(t,y):
        q,u,v,_,_,_=y
        force=0 if kind=='instant_force_removal' else table.force(angle(t) if kind in ('rotary_path','close_hold_open') else 0,q)
        return [u,(force-k*q-damping*u-theta*v)/m,(theta*u-v/resistor)/cp,
                v*v/resistor,damping*u*u,force*u]
    def boundary(t,y):return min(y[0]-table.qs[0],table.qs[-1]-y[0])
    boundary.terminal=True;boundary.direction=-1
    grid=np.linspace(0,end,8001)
    solution=solve_ivp(rhs,[0,end],[q0,0,0,0,0,0],t_eval=grid,events=boundary,
                       method='DOP853',max_step=max_step,rtol=1e-8,atol=1e-12)
    if not solution.success:raise ValueError('DIAGNOSTIC_INTEGRATION_FAILED')
    q,u,v,port,loss,work=solution.y
    energy=.5*m*u*u+.5*k*q*q+.5*cp*v*v;e0=.5*k*q0*q0
    residual=energy-e0+port+loss-work
    result={'control':kind,'scope':'SciPy reciprocal ROM with 1 MOhm resistor; no PMIC/application verdict',
        'status':'out_of_domain' if solution.t_events[0].size else 'completed',
        'initial_elastic_J':e0,'resistor_energy_J':float(port[-1]),'magnetic_work_on_beam_J':float(work[-1]),
        'damping_loss_J':float(loss[-1]),'final_stored_J':float(energy[-1]),
        'peak_tip_mm':float(np.max(abs(q))*1000),'peak_velocity_m_s':float(np.max(abs(u))),
        'peak_voltage_V':float(np.max(abs(v))),'relative_energy_residual':float(np.max(abs(residual))/max(e0,np.max(abs(work)),1e-12)),
        'diagnostic_only':True,'instant_removal_is_not_realizable_design':kind=='instant_force_removal',
        'loading_trajectory_included':kind=='close_hold_open',
        'full_door_loading_work_observed':False}
    return result,np.column_stack([solution.t,q,u,v,port,loss,work,energy])


def audit(run, cache, output):
    run,cache,output=map(Path,(run,cache,output))
    if output.exists():raise ValueError('AUDIT_OUTPUT_EXISTS_PRESERVE_PRIOR')
    result=json.loads((run/'result.json').read_text());sources={}
    def verified(path,expected):
        actual=file_hash(path)
        if actual!=expected:raise ValueError('SOURCE_HASH_MISMATCH:'+str(path))
        sources[str(path)]={'sha256':actual,'bytes':path.stat().st_size}
        return path
    artifact_index={a['name']:a['sha256'] for a in result['artifacts']}
    for name in ('energy.json','design-spec.json','waveform.csv'):
        verified(run/name,artifact_index[name])
    sources[str(run/'result.json')]={'sha256':file_hash(run/'result.json')}
    sources[str(Path(__file__).resolve())]={'sha256':file_hash(Path(__file__))}
    def checkpoint_file(stage,name):
        key=result['stages'][stage]['key'];d=cache/stage/key
        cp=json.loads((d/'checkpoint.json').read_text())
        if cp['key']!=key or cp['stage']!=stage:raise ValueError('CHECKPOINT_BINDING_MISMATCH')
        expected=next(a['sha256'] for a in cp['files'] if a['path']==name)
        sources[str(d/'checkpoint.json')]={'sha256':file_hash(d/'checkpoint.json')}
        return verified(d/name,expected)
    rom=json.loads(checkpoint_file('beam','rom.json').read_text())
    f=np.load(checkpoint_file('force','force-table.npz'))
    table=ForceTable(f['angles'],f['qs'],f['values'])
    spec=json.loads((run/'design-spec.json').read_text());ledger=json.loads((run/'energy.json').read_text())
    output.mkdir(parents=True)
    equilibria=[{'angle_deg':float(np.rad2deg(a)),'roots':table.equilibria(a,rom['k'])}
                for a in np.linspace(0,np.deg2rad(spec['mechanical']['angle_deg']),261)]
    write_json(output/'equilibria.json',equilibria)
    controls=[]
    for kind in ('fixed_door','rotary_path','instant_force_removal'):
        value,wave=control(rom,table,spec,kind);controls.append(value)
        np.savetxt(output/(kind+'.csv'),wave,delimiter=',',header='time_s,tip_m,velocity_m_s,piezo_V,resistor_J,damping_J,magnetic_work_J,stored_J',comments='')
    e0=ledger['initial_mechanical_piezo_J']
    shares={k:ledger[k]/e0 for k in ('external_force_work_J','mechanical_loss_J','pmic_port_energy_J')}
    # These are energy-to-threshold lower bounds, not capacitor recommendations.
    capacitors=[{'capacitance_uF':c,'threshold_V':v,'ideal_charge_energy_uJ':.5*c*v*v}
                for c in (10,22,47,100,220,330,1000,2200,4700) for v in (3.77,5.05)]
    value={'schema_version':'mechanical-release-audit-v1','source_hashes':sources,'rom':rom,
        'sealed_native_energy_ledger':ledger,'fractions_of_initial_elastic_energy':shares,
        'sampled_equilibrium_counts':sorted(set(len(e['roots']) for e in equilibria)),
        'minimum_stable_effective_stiffness_N_m':min(r['effective_stiffness_N_m'] for e in equilibria for r in e['roots'] if r['stable']),
        'controls':controls,'capacitor_threshold_energy_bounds':capacitors,
        'interpretation_limits':['Negative magnetic work is energy leaving the beam/piezo subsystem; it is not a measured door-input efficiency.',
            'Initial beam preload provenance and full loading/closing cycle are absent.',
            'Equilibria only examine interpolated short-circuit static ROM within +/-8mm; absence of a sampled fold is not global stability proof.',
            'Instant force removal isolates stored-energy availability, not a manufacturable mechanism.',
            'Physical magnetic qualification remains failed; controls share the unqualified force table.',
            'Capacitance-to-threshold bounds omit converter, ESR and load losses; cannot prove startup.'],
        'new_native_solver_calls':0,'new_model_calls_in_this_script':0,'sealed_apparatus_modified':False}
    write_json(output/'audit.json',value)
    plot(output,controls,ledger)
    return value


def plot(output,controls,ledger):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(2,2,figsize=(11,7),layout='constrained')
    for r in controls:
        a=np.loadtxt(output/(r['control']+'.csv'),delimiter=',',skiprows=1)
        axs[0,0].plot(a[:,0],a[:,1]*1000,label=r['control'])
        axs[0,1].plot(a[:,0],a[:,3],label=r['control'])
        axs[1,0].plot(a[:,0],a[:,4]*1e6,label=r['control'])
    axs[0,0].set(ylabel='Beam displacement (mm)',xlabel='Time (s)')
    axs[0,1].set(ylabel='Resistive-control voltage (V)',xlabel='Time (s)')
    axs[1,0].set(ylabel='Energy to 1 MOhm (uJ)',xlabel='Time (s)')
    values=[-ledger['external_force_work_J'],ledger['mechanical_loss_J'],ledger['pmic_port_energy_J']]
    axs[1,1].bar(['Magnetic withdrawal','Damping','PMIC port'],np.array(values)*1e6,color=['#7e8ca0','#de9a4a','#307bb8'])
    axs[1,1].set(ylabel='Sealed native baseline energy (uJ)',title='Initial preload: %.1f uJ'%(ledger['initial_mechanical_piezo_J']*1e6))
    for ax in axs.flat:ax.grid(alpha=.2)
    axs[0,0].legend(fontsize=7)
    fig.suptitle('Loading / release audit — diagnostic controls, not product validation')
    fig.savefig(output/'energy-transfer.png',dpi=170);plt.close(fig)
