"""Experimental terminal-root PMIC hybrid integrator; frozen parent is unchanged.

This remains the same uncalibrated reciprocal/behavioral physical model. Only
PMIC switching-time semantics change. The inherited firmware adapter still uses
accepted interval samples and its existing current/duration assumptions.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import numpy as np
from scipy.integrate import solve_ivp

ROOT=Path('/workspace/shared/bf-simulation-chain/battery-world')
sys.path.insert(0,str(ROOT/'scripts/door_case'))
from simchain import physics_power as parent
VERSION='reciprocal-behavioral-power-v1.3.1-experimental-terminal-events-tight'
PARENT_SHA256='73162bce557a5ad4e5e83236b7c675e89e18376718903c66aa7ee895442d7915'
LIMITS={'rhs_per_segment':10000,'rhs_total':5000000,'wall_s':300,
        'accepted_segments':2000000,'pmic_events':20000,'zero_time_events':8}
PRIORITY=('uvlo_fall','uvlo_rise','aux_fall','aux_rise','pgood_fall','pgood_rise')
ASSUMPTIONS=deepcopy(parent.ASSUMPTIONS)
ASSUMPTIONS['identity']=VERSION
ASSUMPTIONS['engineering_assumptions']=[x for x in ASSUMPTIONS['engineering_assumptions'] if not x.startswith(('Firmware/load, UVLO','Numerical guard:'))]
ASSUMPTIONS['engineering_assumptions'] += [
 'UVLO, auxiliary-ready and PGOOD directional terminal roots; simultaneous-event order UVLO, auxiliary, PGOOD; all continuous states and ledgers remain continuous',
 'Firmware uses unchanged accepted-interval adapter; root boundaries are additional accepted ticks, current sampled per interval; voltage-triggered firmware transitions are not claimed continuously event-located',
 'Regular macro grid stays anchored at t=0; inherited firmware scheduled transitions and controlled-source cutoff are integration boundaries',
 'No state projection, hysteresis widening, threshold easing, hidden source or numerical fallback; zero-time roots require a discrete change and are bounded',
 'Radau rtol2e-10/atol1e-14 numerical-only repair, all prior gates unchanged',
 'Numerical guards:'+json.dumps(LIMITS,sort_keys=True)]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify_parent():
    if sha(parent.__file__)!=PARENT_SHA256:raise RuntimeError('FROZEN_PARENT_SOURCE_DRIFT')
def model_versions():
    verify_parent();old=parent.model_versions();new=deepcopy(old['coupled_power'])
    new.update(version=VERSION,semantics={**deepcopy(ASSUMPTIONS),
          **{k:v for k,v in new['semantics'].items() if k in ('thread_limit_environment','provider_scope','numerical_runtime')}},
          source_hashes={**new['source_hashes'],'experimental/event_power.py':sha(__file__)},
          parent_version=parent.VERSION)
    return {'mechanical':old['mechanical'],'coupled_power':new}


class Latches:
    """Directional guards with deterministic discrete transitions, no state reset."""
    def __init__(self,pm,target):
        self.pm=pm;self.target=target;self.enabled=False;self.aux_ready=False;self.pgood=False
    def state(self):return (self.enabled,self.aux_ready,self.pgood)
    def guards(self):
        p=self.pm;guards=[]
        specs=[('uvlo_fall' if self.enabled else 'uvlo_rise',3,p['uvlo_fall_V'] if self.enabled else p['uvlo_rise_V'],-1 if self.enabled else 1)]
        # Auxiliary increases only while enabled, and decreases only while off.
        if self.enabled and not self.aux_ready:specs.append(('aux_rise',5,p['startup_rail_energy_J']*(1-1e-6),1))
        if not self.enabled and self.aux_ready:specs.append(('aux_fall',5,p['startup_rail_energy_J']*(1-1e-6),-1))
        if self.pgood:specs.append(('pgood_fall',4,self.target*p['pgood_fall_fraction'],-1))
        elif self.enabled:specs.append(('pgood_rise',4,self.target*p['pgood_rise_fraction'],1))
        for name,index,level,direction in specs:
            def event(t,z,index=index,level=level):return z[index]-level
            event.terminal=True;event.direction=direction;event.name=name;event.index=index;event.level=level
            guards.append(event)
        return guards
    def apply(self,names,z):
        """Root names are authoritative at roundoff; activation closure has no reset."""
        names=set(names);before=self.state()
        for name in PRIORITY:
            if name not in names:continue
            if name=='uvlo_fall':self.enabled=False
            elif name=='uvlo_rise':self.enabled=True
            elif name=='aux_fall':self.aux_ready=False
            elif name=='aux_rise':self.aux_ready=True
            elif name=='pgood_fall':self.pgood=False
            elif name=='pgood_rise':self.pgood=True
        # A guard can become active already satisfied, e.g. enabling at high
        # Vout or an initially zero auxiliary target. Exact comparisons only.
        if self.enabled and not self.aux_ready and z[5]>=self.pm['startup_rail_energy_J']*(1-1e-6):self.aux_ready=True
        if not self.enabled and self.aux_ready and z[5]<=self.pm['startup_rail_energy_J']*(1-1e-6):self.aux_ready=False
        if self.enabled and not self.pgood and z[4]>=self.target*self.pm['pgood_rise_fraction']:self.pgood=True
        return before,self.state()


def simulate(design,firmware=None,*,step_s=None,mechanical=None):
    verify_parent()
    ref,mode,power,control=parent.normalize(design)
    mission=design.get('mission',{});dt=parent._num(step_s if step_s is not None else mission.get('step_s',.0005),'step',1e-6,.002)
    duration=parent._num(mission.get('duration_s',ref['door']['opening_s']+2 if mode=='door' else .3),'duration',dt,20)
    f,q0,mechanical=mechanical or parent.build_mechanical(design);p=parent.parameters();pm=power['pmic']
    firmware=firmware or parent.ConstantLoad();ci=power['input_capacitance_uF']*1e-6;co=power['output_capacitance_uF']*1e-6;target=power['output_voltage_V']
    y=np.zeros(16);y[0]=q0;initial=.5*p['k']*q0*q0
    latch=Latches(pm,target);latch.apply([],y)
    events=[];rows=[];pmic_events=[];wall=time.monotonic()
    damping=2*p['zeta']*math.sqrt(p['k']*p['mass'])
    peak_q=abs(q0);peak_vin=0.;peak_vout=0.;max_residual=0.;total_rhs=0;max_interval_rhs=0
    t=0.;index=0;macro_index=1;zero_time_count=0
    stored=initial;residual=0.;enabled_duration=0.;peak_aux=0.
    while t<duration-1e-12:
        while macro_index*dt<=t+1e-14:macro_index+=1
        endpoint=min(macro_index*dt,duration)
        if hasattr(firmware,'next_transition_s'):
            remaining=firmware.next_transition_s()
            if remaining is not None:endpoint=min(endpoint,t+max(float(remaining),1e-9))
        cutoff=control.get('duration_s',duration)
        if mode=='controlled_input' and t<cutoff<endpoint:endpoint=cutoff
        h=endpoint-t
        if h<=0:raise RuntimeError('NONPOSITIVE_SEGMENT')
        index+=1
        if index>LIMITS['accepted_segments']:raise RuntimeError('INTEGRATION_TICK_BUDGET_EXCEEDED')
        enabled=latch.enabled;aux_ready=latch.aux_ready;start_pgood=latch.pgood
        requested=float(firmware.load_current_a(float(y[4]),latch.pgood))
        if not math.isfinite(requested) or requested<0:raise ValueError('INVALID_FIRMWARE_CURRENT')
        interval_rhs=0
        def rhs(tt,z):
            nonlocal interval_rhs,total_rhs
            interval_rhs+=1;total_rhs+=1
            if interval_rhs>LIMITS['rhs_per_segment'] or total_rhs>LIMITS['rhs_total']:raise RuntimeError('NUMERICAL_RHS_BUDGET_EXCEEDED')
            if total_rhs%128==0 and time.monotonic()-wall>LIMITS['wall_s']:raise RuntimeError('NUMERICAL_WALL_DEADLINE_EXCEEDED')
            q,vel,vp,vin,vout,aux=z[:6]; vinp=max(vin,0.);vop=max(vout,0.)
            ib=max(abs(vp)-vinp-2*pm['bridge_drop_V'],0)/pm['bridge_resistance_ohm']
            src=0.
            if mode=='controlled_input' and t<cutoff:
                src=max(control.get('voltage_V',6.)-vinp,0)/control.get('series_resistance_ohm',20.)
            # Explicit bypass-rail store, capped continuously near its target.
            startup=min(pm['startup_current_A']*vinp,max(pm['startup_rail_energy_J']-aux,0)/pm['startup_taper_s']) if enabled else 0.
            aux_decay=max(aux,0)/pm['aux_off_decay_s'] if not enabled else 0.
            ready=aux_ready
            io=min(pm['max_output_current_A'],max(target-vop,0)/pm['regulator_resistance_ohm']) if enabled and ready else 0.
            # Graceful input-voltage availability, not a hidden ideal power source.
            io*=min(1.,vinp/max(pm['uvlo_fall_V'],1e-9))
            pout=io*vop;conv=pout/pm['efficiency'];iq=pm['input_quiescent_A']*min(1.,vinp/.1)
            il=vinp/pm['input_leakage_ohm'];ol=vop/pm['output_leakage_ohm']
            load=requested*min(1.,vop/.1)
            draw=(conv+startup)/max(vinp,1e-9)+iq+il
            applied=f(tt,q)
            return [vel,(applied-p['k']*q-damping*vel-p['theta']*vp)/p['mass'],
                    (p['theta']*vel-np.sign(vp)*ib)/p['cp'],(ib+src-draw)/ci,(io-load-ol)/co,startup-aux_decay,
                    applied*vel,src*control.get('voltage_V',6.),damping*vel*vel,ib*(abs(vp)-vinp),
                    conv-pout,iq*vinp+il*vinp+ol*vop+aux_decay,load*vop,max(applied*vel,0.),max(-applied*vel,0.),
                    src*src*control.get('series_resistance_ohm',20.)]
        guards=latch.guards()
        sol=solve_ivp(rhs,(t,endpoint),y,method='Radau',rtol=2e-10,atol=1e-14,max_step=h,events=guards)
        max_interval_rhs=max(max_interval_rhs,interval_rhs)
        if not sol.success:raise RuntimeError('RADAU_FAILURE:'+sol.message)
        previous_t=t;previous_y=y.copy();y=sol.y[:,-1];t=float(sol.t[-1]);accepted_h=t-previous_t
        if min(y[3:6]) < -1e-8:raise RuntimeError('NEGATIVE_ENERGY_STATE')
        peak_q=max(peak_q,float(np.max(np.abs(sol.y[0]))));peak_vin=max(peak_vin,float(np.max(sol.y[3])));peak_vout=max(peak_vout,float(np.max(sol.y[4])));peak_aux=max(peak_aux,float(np.max(sol.y[5])))
        if peak_q>.008:raise parent.OutOfDomain('ORIGINAL_8MM_ROM_LIMIT_EXCEEDED')
        if peak_vin>=19:raise parent.OutOfDomain('SHUNT_REGION_NOT_MODELED')
        triggered=[g.name for g,ts in zip(guards,sol.t_events) if len(ts) and abs(float(ts[-1])-t)<=1e-12]
        # Simultaneous roots might be truncated by the first terminal root. Add
        # only guards at roundoff whose one-sided derivative has its direction.
        # Tolerances classify coincident roots, never change any guard level.
        if triggered:
            derivative=rhs(t,y)
            for g in guards:
                tol=1e-14 if g.index==5 else 1e-10
                if abs(g(t,y))<=tol and derivative[g.index]*g.direction>0:triggered.append(g.name)
        before,after=latch.apply(triggered,y)
        if triggered:
            roots=[{'name':g.name,'guard_residual':float(g(t,y)),'threshold':g.level} for g in guards if g.name in triggered]
            pmic_events.append({'time_s':t,'events':sorted(set(triggered),key=PRIORITY.index),'before':list(before),'after':list(after),'root_details':roots,'continuous_state_jump_max':0.})
            if len(pmic_events)>LIMITS['pmic_events']:raise RuntimeError('HYBRID_EVENT_BUDGET_EXCEEDED')
        if accepted_h<=0:
            zero_time_count+=1
            if not triggered or before==after or zero_time_count>LIMITS['zero_time_events']:raise RuntimeError('HYBRID_ZERO_TIME_LOOP')
            if not np.array_equal(y,previous_y):raise RuntimeError('ZERO_TIME_STATE_CHANGED')
            continue
        zero_time_count=0
        if enabled:enabled_duration+=accepted_h
        step_result=firmware.advance(previous_t,accepted_h,float(y[4]),bool(start_pgood and latch.pgood),min_vdd_v=float(np.min(sol.y[4])))
        for e in step_result.get('events',step_result.get('packet_events',[])):events.append(e)
        stored=.5*p['mass']*y[1]**2+.5*p['k']*y[0]**2+.5*p['cp']*y[2]**2+.5*ci*y[3]**2+.5*co*y[4]**2+y[5]
        residual=stored-initial+sum(y[8:13])+y[15]-y[6]-y[7]
        max_residual=max(max_residual,abs(residual))
        # Existing columns represent the interval's applied enabled mode, plus
        # post-event PGOOD; explicit event records carry both sides of each root.
        rows.append([t,*map(float,y[:6]),bool(enabled),bool(latch.pgood),requested,step_result.get('state','unknown'),float(residual)])
    denom=float(max(initial,y[13]+y[14]+y[7],1e-12))
    return {'schema_version':'simchain-physics-result-v1','model':deepcopy(ASSUMPTIONS),'mode':mode,
      'dt_s':dt,'duration_s':duration,'wall_s':time.monotonic()-wall,'trace':rows,'events':events,'pmic_events':pmic_events,
      'trace_columns':['time_s','q_m','velocity_m_s','piezo_V','vin_V','vout_V','aux_rail_J','pmic_enabled','pgood','load_A','firmware_state','residual_J'],
      'metrics':{'rhs_evaluations':total_rhs,'max_interval_rhs_evaluations':max_interval_rhs,'peak_tip_mm':peak_q*1000,'peak_vin_V':peak_vin,'peak_vout_V':peak_vout,'final_vout_V':float(y[4]),
         'relative_energy_residual':float(max_residual/denom),'max_energy_residual_J':float(max_residual),'numerical_pass':bool(max_residual/denom<.01),
         'pmic_started':any(r[7] for r in rows),'pgood_observed':any(r[8] for r in rows),
         'peak_auxiliary_energy_J':peak_aux,'pmic_enabled_duration_s':enabled_duration,
         'pmic_enable_intervals':sum('uvlo_rise' in e['events'] for e in pmic_events),'hybrid_event_count':len(pmic_events),'accepted_segments':index},
      'energy_ledger_J':{'initial_mechanical':initial,'mechanical_work':float(y[6]),'external_electrical_work':float(y[7]),
         'mechanical_positive_work':float(y[13]),'mechanical_negative_work_magnitude':float(y[14]),
         'controlled_source_resistor_loss':float(y[15]),'mechanical_damping':float(y[8]),'bridge_loss':float(y[9]),'conversion_loss':float(y[10]),
         'quiescent_and_leakage':float(y[11]),'firmware_load':float(y[12]),'final_stored':float(stored),
         'final_piezo':float(.5*p['cp']*y[2]**2),'final_input_capacitor':float(.5*ci*y[3]**2),
         'final_output_capacitor':float(.5*co*y[4]**2),'final_aux_rail':float(y[5]),'balance_residual':float(residual)},
      'firmware_summary':firmware.summary() if hasattr(firmware,'summary') else {},
      'parameters':p,'power':power,'model_binding':model_versions(),'hardware_verified':False,'product_accepted':False}
