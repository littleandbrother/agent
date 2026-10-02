"""Versioned policy-driven extension of coupled.profiled v2.

The v2 electrical integrator is preserved verbatim. Only application scheduling
is replaced by bounded public-observation callbacks. No measured data or trained
model is substituted; this is the declared computational BF-AIoT task.
"""
from __future__ import annotations
import math
from dataclasses import asdict, dataclass
from typing import Any
from bfworld.kernel.canonical import canonical_hash
from bfworld.coupled.engine import Design, Reference, MODEL, FIDELITY, input_current, signal_window, classify

VERSION = 'coupled-programmed-reference-v3'


@dataclass(frozen=True)
class LoadProfile:
    boot_duration_s: float = .012
    sense_duration_s: float = .08
    infer_duration_s: float = .035
    tx_duration_s: float = .04
    receiver_delay_s: float = .008
    cold_start_duration_s: float = .004
    boot_power_w: float = .002
    sense_power_w: float = .003
    infer_power_w: float = .009
    sleep_power_w: float = .00005
    sample_count: int = 128
    source_kind: str = 'synthetic-declared-state-load'
    source_artifact_hash: str | None = None


def validate_inputs(design: Design, ref: Reference, load: LoadProfile):
    for name, obj in [('design',asdict(design)),('reference',asdict(ref)),('load',asdict(load))]:
        for key,value in obj.items():
            if isinstance(value,float) and not math.isfinite(value):
                raise ValueError(f'{name}.{key} is not finite')
            if key not in {'clamp_v','source_artifact_hash','fault','receiver_loss','device_session','source_kind'} and type(value) not in (int,float):
                raise ValueError(f'{name}.{key} must be a number, not a boolean or string')
    if type(ref.receiver_loss) is not bool or not isinstance(ref.device_session,str):
        raise ValueError('invalid receiver metadata')
    if design.clamp_v is not None and (type(design.clamp_v) not in (int,float) or not math.isfinite(design.clamp_v)):
        raise ValueError('invalid clamp type')
    if not .0001 <= design.capacitance_f <= .01 or design.esr_ohm < 0 or design.tx_power_w < 0:
        raise ValueError('C/ESR/TX outside declared electrical domain')
    if not 0 < ref.dt_s <= .002 or not 0 < ref.duration_s <= 10 or not 0 < ref.efficiency <= 1:
        raise ValueError('invalid solver/efficiency domain')
    if not 0 < ref.off_v < design.start_v <= ref.max_v or not 0 < ref.initial_v <= ref.max_v:
        raise ValueError('invalid voltage/start domain')
    if ref.rpm <= 0 or ref.pole_pairs <= 0 or ref.source_peak_a < 0 or ref.source_r_ohm <= 0 or ref.leakage_r_ohm <= 0:
        raise ValueError('invalid source domain')
    if ref.surge_multiplier < 0 or ref.deadline_s <= 0 or not 0 <= design.release_s <= ref.duration_s:
        raise ValueError('invalid mission/environment timing')
    if design.clamp_v is not None and not ref.off_v < design.clamp_v <= ref.max_v:
        raise ValueError('invalid clamp domain')
    if ref.fault not in ('normal','bearing-fault') or type(design.model_threshold) is not int or design.model_threshold <= 0:
        raise ValueError('unsupported information task')
    if type(load.sample_count) is not int or load.sample_count != 128:
        raise ValueError('v2 reference executes the declared 128-sample model only')
    if load.source_kind != 'synthetic-declared-state-load' or load.source_artifact_hash is not None:
        raise ValueError('measured waveform replay requires its own model; cannot relabel state averages as measured')
    for k,v in asdict(load).items():
        if k.endswith('_duration_s') or k=='receiver_delay_s':
            if type(v) not in (int,float) or v < ref.dt_s:
                raise ValueError('phase duration below solver resolution')
        if k.endswith('_power_w') and (type(v) not in (int,float) or v < 0):
            raise ValueError('negative phase power')
    for k in ('flash_bytes','sram_bytes'):
        if type(getattr(design,k)) is not int or getattr(design,k) < 0:
            raise ValueError('invalid deployment resources')


def execute(design=Design(), ref=Reference(), load=LoadProfile(), policy=None) -> dict[str,Any]:
    validate_inputs(design,ref,load)
    if policy is None: raise ValueError('policy callback required')
    decisions=[]; completed=[]; next_decision=0.
    dt,c,v = ref.dt_s,design.capacitance_f,ref.initial_v
    initial_energy=.5*c*v*v
    state,pmic,request='off','off','pending'
    until=0.; rows=[];events=[];samples=[];window=signal_window(ref)
    prediction=None;tx=None;received=None;brownouts=[];overs=[];power_failures=[]
    energies={k:0. for k in ('harvest','boot','sense','infer','tx','idle','pmic_loss','esr_loss','leakage','dump')}
    powers={'off':0.,'brownout':0.,'power-loss':0.,'sleep':load.sleep_power_w,'boot':load.boot_power_w,
            'sense':load.sense_power_w,'infer':load.infer_power_w,'tx':design.tx_power_w}
    def emit(t,priority,kind,**facts):
        events.append({'time_s':round(t,9),'priority':priority,'seq':len(events),'type':kind,'facts':facts})
    last_over=False
    # Include the final fractional step explicitly, without extending the mission.
    steps=math.ceil(ref.duration_s/dt)
    for step in range(steps+1):
        t=min(step*dt,ref.duration_s);h=0 if step==0 else t-min((step-1)*dt,ref.duration_s)
        p=powers[state];interval_state=state;current=harvest=actual=0.;collapsed=False
        if step:
            mid=t-h/2
            peak=ref.source_peak_a*(ref.surge_multiplier if mid>=ref.surge_after_s else 1.)
            source=peak*abs(math.sin(2*math.pi*ref.rpm/60*ref.pole_pairs*mid+ref.source_phase_rad))
            ih=max(0.,source-v/ref.source_r_ohm);i0=input_current(v,p,design.esr_ohm,ref.efficiency)
            vm=max(.01,v+h/2*(ih-i0-v/ref.leakage_r_ohm)/c)
            harvest=max(0.,source-vm/ref.source_r_ohm)
            current=input_current(vm,p,design.esr_ohm,ref.efficiency);leak=vm/ref.leakage_r_ohm
            # A maximum-power fallback current is not successful delivery of the
            # requested constant power. This failure can occur ABOVE off_v.
            collapsed=bool(p>0 and design.esr_ohm>0 and vm*vm<4*design.esr_ohm*p/ref.efficiency)
            raw=max(.001,v+h*(harvest-current-leak)/c)
            nv=min(raw,design.clamp_v) if design.clamp_v is not None else raw
            work_v=.5*(v+raw)
            energies['harvest']+=work_v*harvest*h
            energies['leakage']+=work_v*leak*h
            esr_loss=current*current*design.esr_ohm*h
            consumed=work_v*current*h-esr_loss
            energies['esr_loss']+=esr_loss;energies['pmic_loss']+=consumed*(1-ref.efficiency)
            energies[interval_state if interval_state in ('boot','sense','infer','tx') else 'idle']+=consumed*ref.efficiency
            energies['dump']+=.5*c*(raw*raw-nv*nv);actual=consumed*ref.efficiency/h
            v=nv
        terminal=v-current*design.esr_ohm
        over=v>ref.max_v
        if over and not last_over:
            overs.append(t);emit(t,10,'overvoltage',voltage_v=v,threshold_v=ref.max_v)
        last_over=over
        if pmic in ('regulated','cold-start') and (terminal < ref.off_v or collapsed):
            if terminal < ref.off_v:
                emit(t,10,'threshold_crossing',voltage_v=terminal,threshold_v=ref.off_v)
            if collapsed:
                power_failures.append(t)
                emit(t,10,'constant_power_collapse',requested_load_w=p,actual_load_w=actual,input_voltage_v=terminal)
            pmic='off';emit(t,20,'pmic_transition',state=pmic)
            if state in ('boot','sense','infer','tx'):
                if terminal < ref.off_v:brownouts.append(t)
                state='brownout' if terminal < ref.off_v else 'power-loss';request='aborted'
                emit(t,30,'mcu_transition',state=state)
                emit(t,40,'request_aborted',reason='power_lost',sample_count=len(samples))
            else:
                state='off';emit(t,30,'mcu_transition',state=state)
        elif pmic=='off' and v>=design.start_v and request!='aborted':
            pmic='cold-start';until=t+load.cold_start_duration_s;emit(t,20,'pmic_transition',state=pmic)
        elif pmic=='cold-start' and t>=until-1e-10:
            pmic='regulated';state='boot';until=t+load.boot_duration_s
            emit(t,20,'pmic_transition',state=pmic);emit(t,30,'mcu_transition',state=state)
        elif pmic=='regulated' and state=='boot' and t>=until-1e-10:
            state='sleep';emit(t,30,'mcu_transition',state=state)
        if state=='sense':
            n=min(load.sample_count,round((t-(until-load.sense_duration_s))/load.sense_duration_s*load.sample_count))
            samples=window[:max(0,n)]
            if t>=until-1e-10:
                samples=window[:];state='sleep';request='sampled';completed.append('sense')
                emit(t,30,'mcu_transition',state=state)
                emit(t,40,'acquisition_completed',window_hash=canonical_hash(samples))
        elif state=='infer' and t>=until-1e-10:
            prediction=classify(samples,design.model_threshold);state='sleep';request='inferred';completed.append('infer')
            emit(t,30,'mcu_transition',state=state);emit(t,40,'inference_completed',**prediction)
        elif state=='tx' and t>=until-1e-10:
            state='sleep';request='transmitted';until=t+load.receiver_delay_s;completed.append('report')
            emit(t,30,'mcu_transition',state=state);emit(t,40,'transmission_completed')
        if pmic=='regulated' and state=='sleep' and request in ('pending','sampled','inferred') and t>=next_decision-1e-10:
            if len(decisions)>=96: raise ValueError('POLICY_DECISION_BUDGET')
            observation={'time_s':round(t,9),'voltage_v':v,'energy_j':.5*c*v*v,
                'completed_actions':completed[:], 'prediction':prediction,
                'requirements':{'release_s':design.release_s,'deadline_s':ref.deadline_s,
                'max_voltage_v':ref.max_v,'off_voltage_v':ref.off_v,'sample_count':load.sample_count},
                'action_duration_s':{'sense':load.sense_duration_s,'infer':load.infer_duration_s,
                  'report':load.tx_duration_s,'receiver':load.receiver_delay_s},
                'remaining_decisions':96-len(decisions)}
            decision=policy(observation)
            if not isinstance(decision,dict) or set(decision)-{'action','duration_s'}:
                raise ValueError('INVALID_POLICY_ACTION')
            action=decision.get('action')
            decisions.append({'observation':observation,'action':decision})
            if action=='wait':
                duration=decision.get('duration_s',.02)
                if type(duration) not in (int,float) or not math.isfinite(duration) or not dt<=duration<=ref.duration_s:
                    raise ValueError('INVALID_WAIT_DURATION')
                next_decision=t+duration
            elif action=='sense' and request=='pending' and t>=design.release_s-1e-10:
                state='sense';request='acquiring';until=t+load.sense_duration_s
                emit(t,30,'mcu_transition',state=state);emit(t,40,'acquisition_started',samples=load.sample_count)
            elif action=='infer' and request=='sampled':
                state='infer';until=t+load.infer_duration_s;emit(t,30,'mcu_transition',state=state)
            elif action=='report' and request=='inferred':
                state='tx';until=t+load.tx_duration_s;tx=t
                emit(t,30,'mcu_transition',state=state)
                emit(t,40,'transmission_started',duration_s=load.tx_duration_s,power_w=design.tx_power_w)
            else: raise ValueError('ILLEGAL_ACTION_ORDER_OR_RELEASE')
            emit(t,40,'policy_decision',action=action,decision_index=len(decisions)-1)
        if request=='transmitted' and t>=until-1e-10:
            if ref.receiver_loss:
                request='receiver-lost';emit(t,40,'receiver_no_delivery')
            else:
                received=t;request='received';emit(t,40,'receiver_delivered',receiver_session=ref.device_session+'-rx')
        rows.append({'time_s':round(t,9),'storage_voltage_v':round(v,9),'input_voltage_v':round(terminal,9),
            'energy_j':round(.5*c*v*v,12),'harvest_current_a':round(harvest,9),'load_current_a':round(current,9),
            'load_power_w':p,'actual_load_power_w':actual,'interval_load_state':interval_state,
            'pmic_state':pmic,'mcu_state':state,'sensor_samples':len(samples),'request_state':request,
            'receiver_delivered':received is not None,'brownout':bool(brownouts),'overvoltage':over,
            'supply_power_shortfall':bool(power_failures)})
    correct=bool(prediction and prediction['predicted_label']==ref.fault and prediction['confidence']>=.7)
    physical={'quality_valid':correct,'delivered':received is not None,'deadline_met':received is not None and received<=ref.deadline_s,
        'electrical_safe':not brownouts and not overs and not power_failures,'deployment_feasible':design.capacitance_f<=.0047 and design.flash_bytes<=65536 and design.sram_bytes<=16384}
    physical['value']=all(physical.values())
    delta=.5*c*v*v-initial_energy;used=sum(v for k,v in energies.items() if k!='harvest')
    residual=energies['harvest']-used-delta
    emit(ref.duration_s,50,'mission_evaluated',**physical)
    events.sort(key=lambda e:(e['time_s'],e['priority'],e['seq']))
    result={'schema_version':VERSION,'design':asdict(design),'reference':asdict(ref),'load_profile':asdict(load),
        'rows':rows,'events':events,'policy_decisions':decisions,'request':{'samples':samples,'prediction':prediction,'ground_truth':ref.fault,
            'transmit_s':tx,'receive_s':received,'deadline_s':ref.deadline_s},
        'model_artifact':{**MODEL,'threshold':design.model_threshold},
        'fidelity':{**FIDELITY,'mcu':{'level':'explicit-phase-load-v2','kind':load.source_kind,'measured':False}},
        'energy_ledger':{**{k:round(v,12) for k,v in energies.items()},'storage_delta':round(delta,12),
            'residual_j':round(residual,12),'normalized_residual':abs(residual)/max(energies['harvest'],used,initial_energy,1e-12)},
        'summary':{'minimum_input_v':min(r['input_voltage_v'] for r in rows),'maximum_storage_v':max(r['storage_voltage_v'] for r in rows),
            'first_brownout_s':brownouts[0] if brownouts else None,'first_overvoltage_s':overs[0] if overs else None},
        'physical_mission_pass':physical,'power_delivery_failures_s':power_failures,'verified_mission_success':False,
        'time_semantics':{'rows':'post-event states; currents/power belong to preceding interval',
            'event_order':'integration -> threshold -> PMIC -> MCU -> application -> mission','timing_error_bound_s':dt},
        'claim_boundary':'Programmable synthetic computational reference derived from profiled v2; shares its primitive equations; not hardware, calibrated measurement, independent full-system physics or learned knowledge.'}
    result['content_hash']=canonical_hash(result)
    return result


def verify(run, reproduce=False):
    if run.get('schema_version')!=VERSION or run.get('content_hash')!=canonical_hash({k:v for k,v in run.items() if k!='content_hash'}):
        raise ValueError('profiled run identity mismatch')
    if run['energy_ledger']['normalized_residual']>1e-7 or run['verified_mission_success']:
        raise ValueError('energy closure or authority violation')
    if any(b['time_s']<=a['time_s'] for a,b in zip(run['rows'],run['rows'][1:])):
        raise ValueError('nonmonotonic timebase')
    order=[(e['time_s'],e['priority'],e['seq']) for e in run['events']]
    if order!=sorted(order):raise ValueError('event order mismatch')
    if reproduce:
        actions=iter(run['policy_decisions'])
        def replay(obs):
            entry=next(actions)
            if entry['observation']!=obs: raise ValueError('observation reproduction mismatch')
            return entry['action']
        if execute(Design(**run['design']),Reference(**run['reference']),LoadProfile(**run['load_profile']),replay)['content_hash']!=run['content_hash']:
            raise ValueError('programmed numerical reproduction mismatch')
    return {'status':'pass','content_hash':run['content_hash'],'reproduced':reproduce}
