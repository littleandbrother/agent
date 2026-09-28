"""Coupled energy, PMIC, acquisition, integer inference and receiver runtime.

Synthetic signals and simplified component models are explicit. Outcomes are
computed from integration and events rather than case names or expected flags.
"""
from __future__ import annotations
import math
from dataclasses import asdict,dataclass,replace
from typing import Any
from bfworld.kernel.canonical import canonical_hash

@dataclass(frozen=True)
class Design:
    capacitance_f:float=.0022
    clamp_v:float|None=3.45
    esr_ohm:float=4.0
    start_v:float=2.35
    release_s:float=.25
    tx_power_w:float=.036
    model_threshold:int=25
    flash_bytes:int=8192
    sram_bytes:int=2048

@dataclass(frozen=True)
class Reference:
    duration_s:float=1.6
    dt_s:float=.001
    rpm:float=120.
    pole_pairs:int=4
    source_peak_a:float=.0033
    source_r_ohm:float=3000.
    initial_v:float=2.65
    leakage_r_ohm:float=200000.
    efficiency:float=.82
    off_v:float=1.8
    max_v:float=3.6
    deadline_s:float=1.1
    fault:str='bearing-fault'
    receiver_loss:bool=False
    surge_after_s:float=10.
    surge_multiplier:float=1.
    source_phase_rad:float=0.
    device_session:str='synthetic-rotary-session-0'

MODEL={'id':'difference-feature-int8-v1','weights':[1,-1],
       'format':'signed-int8 input, int32 difference accumulator',
       'training':'hand-authored classifier; no learned hardware accuracy claim'}
FIDELITY={
 'harvester':{'level':'F1-simplified','kind':'load-dependent rectified Norton','measured':False},
 'power':{'level':'F1-simplified','kind':'capacitor, leakage, ESR, efficiency and ideal clamp','measured':False},
 'pmic':{'level':'state-model','kind':'cold-start, regulated, off hysteresis','measured':False},
 'mcu':{'level':'state-load-model','kind':'sleep, boot, sense, infer, TX, brownout','measured':False},
 'information':{'level':'executed-integer-classifier','kind':'synthetic acquisition; integer feature/classifier','measured':False},
 'radio':{'level':'simplified-receiver','kind':'completed TX plus independent receiver delivery event','measured':False}}

def signal_window(ref:Reference)->list[int]:
    frequency=5 if ref.fault=='normal' else 23
    return [max(-128,min(127,round(74*math.sin(2*math.pi*frequency*i/128)+8*math.sin(2*math.pi*3*i/128)))) for i in range(128)]

def classify(samples:list[int],threshold:int)->dict:
    if len(samples)!=128:raise ValueError('incomplete acquisition')
    if any(not isinstance(x,int) or x < -128 or x >127 for x in samples):raise ValueError('INT8 input violated')
    accumulator=sum(abs(b-a) for a,b in zip(samples,samples[1:]))
    boundary=threshold*(len(samples)-1)
    margin=accumulator-boundary
    return {'predicted_label':'bearing-fault' if margin>=0 else 'normal',
            'integer_accumulator':accumulator,'threshold_accumulator':boundary,
            'score':margin,'confidence':round(.5+min(.49,abs(margin)/max(1,boundary)),6),
            'confidence_kind':'uncalibrated score mapping, not a probability'}

def input_current(v:float,p:float,esr:float,efficiency:float)->float:
    """Stable low-current branch of (V-I*R)*I=P/eta.

    Past the constant-power fold, return the maximum-power current; terminal
    undervoltage then shuts down the node. This is not a transistor PMIC model.
    """
    if p==0:return 0.
    pin=p/efficiency
    if esr==0:return pin/max(v,.001)
    return 2*pin/(v+math.sqrt(max(0,v*v-4*esr*pin))) if v*v>=4*esr*pin else v/(2*esr)

def execute(design:Design=Design(),ref:Reference=Reference())->dict[str,Any]:
    if not(.0001<=design.capacitance_f<=.01 and 0<ref.dt_s<=.002):raise ValueError('invalid capacitance or timestep')
    if ref.efficiency<=0 or ref.efficiency>1 or design.esr_ohm<0:raise ValueError('invalid component parameters')
    if ref.duration_s<=0 or ref.duration_s>10 or ref.source_r_ohm<=0 or ref.leakage_r_ohm<=0:raise ValueError('invalid reference domain')
    if design.start_v<=ref.off_v or design.tx_power_w<0 or design.release_s<0:raise ValueError('invalid operating policy')
    if design.clamp_v is not None and design.clamp_v<=ref.off_v:raise ValueError('invalid clamp')
    if ref.fault not in ('normal','bearing-fault'):raise ValueError('unknown signal family')
    dt=ref.dt_s;c=design.capacitance_f;v=ref.initial_v
    energy0=.5*c*v*v;pmic='off';mcu='off';until=0.;request_state='pending'
    rows=[];events=[];window=signal_window(ref);samples=[];prediction=None;tx=None;received=None
    brownouts=[];overs=[];energy={k:0. for k in ['harvest','sense','infer','tx','boot','idle','pmic_loss','esr_loss','leakage','dump']}
    seq=0;last_violation=False
    def emit(t,priority,kind,**facts):
        nonlocal seq
        events.append({'time_s':round(t,9),'priority':priority,'seq':seq,'type':kind,'facts':facts});seq+=1
    powers={'off':0.,'sleep':.00005,'boot':.002,'sense':.003,'infer':.009,'tx':design.tx_power_w,'brownout':0.}
    predicted_average=(ref.source_peak_a*2/math.pi-ref.initial_v/ref.source_r_ohm)*ref.initial_v
    predicted_load=(.003*.08+.009*.035+design.tx_power_w*.04+.002*.012)/ref.duration_s/ref.efficiency
    for step in range(int(round(ref.duration_s/dt))+1):
        t=round(step*dt,9)
        # Continuous storage integration precedes threshold / power / application.
        interval_state=mcu;p=powers[mcu];harvest=0.;iin=0.;leak=0.;actual_power=0.
        if step:
            tm=t-dt/2
            peak=ref.source_peak_a*(ref.surge_multiplier if tm>=ref.surge_after_s else 1)
            source=peak*abs(math.sin(2*math.pi*ref.rpm/60*ref.pole_pairs*tm+ref.source_phase_rad))
            ih0=max(0,source-v/ref.source_r_ohm)
            i0=input_current(v,p,design.esr_ohm,ref.efficiency);il0=v/ref.leakage_r_ohm
            vm=max(.01,v+dt/2*(ih0-i0-il0)/c)
            harvest=max(0,source-vm/ref.source_r_ohm);iin=input_current(vm,p,design.esr_ohm,ref.efficiency);leak=vm/ref.leakage_r_ohm
            raw=max(.001,v+dt*(harvest-iin-leak)/c)
            new=min(raw,design.clamp_v) if design.clamp_v else raw
            work_v=.5*(v+raw)
            energy['harvest']+=work_v*harvest*dt
            energy['leakage']+=work_v*leak*dt
            esr_loss=iin*iin*design.esr_ohm*dt
            energy['esr_loss']+=esr_loss
            consumed=work_v*iin*dt-esr_loss
            actual_power=consumed*ref.efficiency/dt
            energy['pmic_loss']+=consumed*(1-ref.efficiency)
            energy[mcu if mcu in ('sense','infer','tx','boot') else 'idle']+=consumed*ref.efficiency
            energy['dump']+=.5*c*(raw*raw-new*new)
            v=new
        rail_input=v-iin*design.esr_ohm
        violated=rail_input<ref.off_v and mcu in ('boot','sense','infer','tx')
        over=v>ref.max_v
        if over and not last_violation:
            overs.append(t);emit(t,10,'electrical_observation',storage_voltage_v=v,threshold_v=ref.max_v)
        last_violation=over
        if pmic in ('regulated','cold-start') and rail_input<ref.off_v:
            emit(t,10,'threshold_crossing',voltage_v=rail_input)
            pmic='off';emit(t,20,'pmic_transition',state=pmic)
            if violated:
                brownouts.append(t);mcu='brownout';request_state='aborted'
                emit(t,30,'mcu_transition',state=mcu)
                emit(t,40,'request_aborted',reason='power_lost',sample_count=len(samples))
            else:mcu='off';emit(t,30,'mcu_transition',state=mcu)
        elif pmic=='off' and v>=design.start_v and request_state!='aborted':
            pmic='cold-start';until=t+.004;emit(t,20,'pmic_transition',state=pmic)
        elif pmic=='cold-start' and t>=until-1e-10:
            pmic='regulated';mcu='boot';until=t+.012
            emit(t,20,'pmic_transition',state=pmic);emit(t,30,'mcu_transition',state=mcu)
        elif pmic=='regulated' and mcu=='boot' and t>=until-1e-10:
            mcu='sleep';emit(t,30,'mcu_transition',state=mcu)
        if pmic=='regulated' and mcu=='sleep' and request_state=='pending' and t>=design.release_s:
            mcu='sense';request_state='acquiring';until=t+.08
            emit(t,30,'mcu_transition',state=mcu);emit(t,40,'acquisition_started',request_id='request-0')
        elif mcu=='sense':
            count=min(128,int(round((t-(until-.08))/.08*128)))
            samples=window[:count]
            if t>=until-1e-10:
                samples=window[:];mcu='infer';until=t+.035
                emit(t,30,'mcu_transition',state=mcu)
                emit(t,40,'acquisition_completed',samples=len(samples),window_hash=canonical_hash(samples))
        elif mcu=='infer' and t>=until-1e-10:
            prediction=classify(samples,design.model_threshold);mcu='tx';until=t+.04;tx=t
            emit(t,30,'mcu_transition',state=mcu)
            emit(t,40,'inference_completed',**prediction,model_hash=canonical_hash({**MODEL,'threshold':design.model_threshold}))
            emit(t,40,'transmission_started',request_id='request-0')
        elif mcu=='tx' and t>=until-1e-10:
            mcu='sleep';request_state='transmitted';until=t+.008
            emit(t,30,'mcu_transition',state=mcu);emit(t,40,'transmission_completed',request_id='request-0')
        if request_state=='transmitted' and t>=until-1e-10:
            if not ref.receiver_loss:
                received=t;request_state='received';emit(t,40,'receiver_delivered',request_id='request-0',receiver_session=ref.device_session+'-rx',protocol='broadcast receiver log; no protocol ACK asserted')
            else:request_state='receiver-lost';emit(t,40,'receiver_no_delivery',request_id='request-0')
        pred_e=energy0+(predicted_average-predicted_load)*t
        rows.append({'time_s':t,'rpm':ref.rpm,'shaft_angle_rad':2*math.pi*ref.rpm/60*t,
                     'storage_voltage_v':round(v,9),'input_voltage_v':round(rail_input,9),
                     'energy_j':round(.5*c*v*v,12),'harvest_current_a':round(harvest,9),
                     'load_current_a':round(iin,9),'load_power_w':p,'actual_load_power_w':actual_power,
                     'interval_load_state':interval_state,'pmic_state':pmic,'mcu_state':mcu,
                     'sensor_samples':len(samples),'predicted_label':prediction['predicted_label'] if prediction else None,
                     'receiver_delivered':received is not None,'request_state':request_state,
                     'brownout':bool(brownouts),'overvoltage':over,
                     'predicted_voltage_v':round(math.sqrt(max(0,2*pred_e/c)),9)})
    correct=bool(prediction and prediction['predicted_label']==ref.fault and prediction['confidence']>=.7)
    physical={'quality_valid':correct,'delivered':received is not None,
              'deadline_met':received is not None and received<=ref.deadline_s,
              'electrical_safe':not brownouts and not overs,
              'deployment_feasible':design.flash_bytes<=65536 and design.sram_bytes<=16384 and design.capacitance_f<=.0047}
    physical['value']=all(physical.values())
    # EA checks identity/trace completeness of this computational experiment;
    # it is not an independent hidden qualification receipt.
    ea={'identity_current':True,'scope_covered':True,'closure_complete':True,
        'independence_satisfied':False,'value':False}
    consumed=sum(energy[k] for k in energy if k!='harvest')
    delta=.5*c*v*v-energy0;residual=energy['harvest']-consumed-delta
    ledger={**{k:round(v,12) for k,v in energy.items()},'storage_delta':round(delta,12),
            'residual_j':round(residual,12),'normalized_residual':abs(residual)/max(energy['harvest'],consumed,energy0,1e-12),'unit':'J'}
    emit(ref.duration_s,50,'mission_evaluated',**physical)
    result={'schema_version':'bfworld-coupled-run-v1','design':asdict(design),'reference':asdict(ref),
            'design_hash':canonical_hash(asdict(design)),'reference_hash':canonical_hash(asdict(ref)),
            'prediction_model':{'id':'average-energy-v0','claim':'mean energy approximation','known_omissions':['transient voltage','ESR','PMIC states','quality drift']},
            'model_artifact':{**MODEL,'threshold':design.model_threshold},'fidelity':FIDELITY,
            'time_semantics':{'rows':'post-event state at t; currents and powers represent preceding integration interval',
              'event_order':'integration -> threshold(10) -> PMIC(20) -> MCU(30) -> application(40) -> mission(50)',
              'timing_error_bound_s':dt,'signal':'128 deterministic INT8 samples acquired over 80 ms; no analog sensor bandwidth claim'},
            'rows':rows,'events':events,'request':{'request_id':'request-0','samples':samples,'window_hash':canonical_hash(samples),
              'ground_truth':ref.fault,'prediction':prediction,'transmit_s':tx,'receive_s':received,'deadline_s':ref.deadline_s},
            'energy_ledger':ledger,'physical_mission_pass':physical,'evidence_admissibility':ea,
            'verified_mission_success':False,'submitted':False,
            'summary':{'minimum_input_v':min(r['input_voltage_v'] for r in rows),'maximum_storage_v':max(r['storage_voltage_v'] for r in rows),
                       'first_brownout_s':brownouts[0] if brownouts else None,'first_overvoltage_s':overs[0] if overs else None},
            'claim_boundary':'Synthetic-data computational reference; no measured hardware, calibrated TinyML accuracy, Agent efficacy or sealed qualification claim.'}
    result['content_hash']=canonical_hash(result)
    return result

def reference_cases()->dict[str,tuple[Design,Reference]]:
    return {'pass':(Design(),Reference()),
            'overvoltage':(replace(Design(),clamp_v=None),replace(Reference(),surge_after_s=.9,surge_multiplier=7)),
            'brownout':(replace(Design(),capacitance_f=.00033,esr_ohm=18),Reference()),
            'wrong-diagnosis':(replace(Design(),model_threshold=120),Reference()),
            'receiver-loss':(Design(),replace(Reference(),receiver_loss=True))}
