"""Finite LC-PV hybrid consumer with explicitly constructed coefficients.

Reuses the A/R wire/receiver, visible queue fields/rank evaluator, and existing
ESR constant-power primitive. It does not inherit their mission qualification.
The new spectral PV/controlled-input relation and probe response are local to
this version. No model/evaluator, Agent, native simulator or hardware is called.
"""
from bisect import bisect_right
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from ..campaign20261019 import ar, ar_service
from ...coupled.engine import input_current

MODEL_ID = 'pqe-lcpv-constructed-hybrid-20261023-v1'
Q, H, LIGHT_SPEED, K_B = 1.602176634e-19, 6.62607015e-34, 299792458.0, 1.380649e-23


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def dependency_identity():
    import inspect
    paths = [Path(__file__), Path(ar.__file__), Path(ar_service.__file__), Path(inspect.getfile(input_current))]
    return {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def at(schedule, t, default=0.0):
    return next((row[2] for row in schedule if row[0] <= t < row[1]), default)


@lru_cache(maxsize=1)
def spectrum():
    wavelengths = tuple(range(380, 781))
    weights = tuple(.5 if nm in (380, 780) else 1.0 for nm in wavelengths)
    shape = tuple(.25 * math.exp(-.5*((nm-450)/12)**2)/(12*math.sqrt(2*math.pi))
                  + .75 * math.exp(-.5*((nm-580)/60)**2)/(60*math.sqrt(2*math.pi)) for nm in wavelengths)
    integral = sum(w*x for w,x in zip(weights,shape))
    return wavelengths, weights, tuple(x/integral for x in shape)


@lru_cache(maxsize=16)
def spectral_responsivity(eqe):
    wavelengths, weights, phi = spectrum()
    return sum(w*p*eqe*Q*(nm*1e-9)/(H*LIGHT_SPEED) for nm,w,p in zip(wavelengths,weights,phi))


def diode_current(voltage, iph, pv):
    """Module current at a supplied loaded voltage; reverse current is blocked."""
    thermal = pv['ideality_factor'] * pv['series_cells'] * K_B * (pv['cell_temperature_c']+273.15)/Q
    def residual(current):
        junction = voltage + current*pv['series_resistance_ohm']
        return current-iph + pv['saturation_current_a']*math.expm1(min(80.0,junction/thermal)) + junction/pv['shunt_resistance_ohm']
    if residual(0.0) >= 0 or iph <= 0:
        return 0.0, residual(0.0)
    low, high = 0.0, iph
    for _ in range(32):
        middle = (low+high)/2
        if residual(middle) > 0:
            high = middle
        else:
            low = middle
    current = (low+high)/2
    return current, residual(current)


def pv_point(task, profile, design, t, storage_v, powered):
    optical, pv, pmic = task['optical_environment'], profile['pv'], profile['pmic']
    irradiance = at(optical['irradiance_schedule_w_m2'],t)
    shade = at(optical['uniform_shading_transmission'],t)
    incident = irradiance*shade*optical['window_transmission']*max(0.0,math.cos(math.radians(optical['incidence_angle_deg'])))
    area = design['area_cm2']*1e-4
    # Total active area includes all cells. Series cells share the same current.
    iph = area/pv['series_cells']*incident*spectral_responsivity(pv['eqe_constant'])
    vin = (pmic['operating_input_offset_v'] + storage_v/pmic['storage_reflection_divisor']) if powered else pmic['cold_input_v']
    current, residual = diode_current(vin,iph,pv)
    raw_power = vin*current
    permitted = vin >= pmic['cold_min_input_v'] and raw_power >= pmic['cold_min_power_w']
    bus_power = raw_power*pmic['conversion_efficiency'] if permitted else 0.0
    return {'incident_w':incident*area,'irradiance_w_m2':irradiance,'effective_irradiance_w_m2':incident,
            'input_v':vin,'input_a':current,'photocurrent_a':iph,'diode_residual_a':residual,
            'raw_power_w':raw_power,'bus_power_w':bus_power,'conversion_loss_w':raw_power-bus_power}


def air_value(knots,t):
    index = min(len(knots)-2,max(0,bisect_right([x[0] for x in knots],t)-1))
    a,b = knots[index],knots[index+1]
    slope = (b[1]-a[1])/(b[0]-a[0])
    return a[1]+(t-a[0])*slope,slope


def probe_advance(sensor, air_start, slope, elapsed, tau):
    """Exact first-order response over one affine air-temperature segment."""
    return air_start+slope*elapsed-slope*tau+(sensor-air_start+slope*tau)*math.exp(-elapsed/tau)


def clock_interval(now,sync_at,ppm,bound_ppm,gap_start):
    if sync_at is None:
        return [gap_start,None],False
    midpoint = now+(now-sync_at)*ppm/1e6
    radius = abs(now-sync_at)*bound_ppm/1e6 + .001
    return [midpoint-radius,midpoint+radius],True


def validate(inputs):
    task,profile,d,p = (inputs[k] for k in ('Task','Profile','Design','Program'))
    if task['task_id'] != 'LC-PV-STRICT-24H-v1' or task['duration_s'] != 86400:
        raise ValueError('TASK_DOMAIN')
    if task['initial']['capacitor_v'] != 0 or task['initial']['battery_or_chemical_store_j'] != 0:
        raise ValueError('ZERO_INITIAL_ENERGY_REQUIRED')
    if not .001 <= d['capacitance_f'] <= 1 or not 10 <= d['area_cm2'] <= 50:
        raise ValueError('STORAGE_AREA_DOMAIN')
    if not 0 < d['brownout_v'] < d['startup_v'] < profile['pmic']['maximum_voltage_v']:
        raise ValueError('THRESHOLD_DOMAIN')
    if not 0 < p['sample_period_s'] <= 60 or p['ack_spacing_s'] < 0 or p['retry_s'] <= 0:
        raise ValueError('PROGRAM_TIMING_DOMAIN')
    if profile['pv']['parallel_strings'] != 1 or profile['pv']['cell_temperature_c'] != 25:
        raise ValueError('ONLY_FROZEN_UNIFORM_SINGLE_STRING_25C_PROFILE_SUPPORTED')
    if profile['pmic']['maximum_step_s'] != 1:
        raise ValueError('ONLY_FROZEN_ONE_SECOND_HYBRID_MODEL')
    if task['thermal_reference']['max_abs_air_slew_c_s'] > .02:
        raise ValueError('PROBE_DOMAIN')


def simulate(inputs):
    validate(inputs)
    task,profile,d,p = (deepcopy(inputs[k]) for k in ('Task','Profile','Design','Program'))
    sources = dependency_identity()
    load,pmic = profile['load'],profile['pmic']
    c, horizon = d['capacitance_f'],task['duration_s']
    e = 0.0
    eon,eoff,emax = [.5*c*v*v for v in (d['startup_v'],d['brownout_v'],pmic['maximum_voltage_v'])]
    t, sensor = 0.0, float(task['initial']['sensor_temperature_c'])
    powered, phase, sequence, sync_at = False,None,0,None
    memory,pending,seen = {},[],set()
    next_sample = next_tx = math.inf
    gap_start,reset_pending,beacon_pending = 0.0,False,False
    previous_gateway,ack_loss,first_boot = False,p['ack_drop_first_n'],None
    activity,samples,records,packets,receiver,gaps,losses,bins = [],[],[],[],[],[],[],[]
    ledger = None
    integration_count,max_diode_residual,max_optical_violation = 0,0.0,0.0

    def emit(action,**facts):
        activity.append({'time_s':t,'action':action,**facts})

    def ensure_bin():
        nonlocal ledger
        start = math.floor((t+1e-9)/60)*60
        if ledger is None or ledger['start_s'] != start:
            if ledger is not None:
                bins.append(ledger)
            ledger = {'start_s':start,'end_s':t,'start_j':e,'stored_j':e,
                      **{k:0.0 for k in ('optical_j','pv_j','pv_conversion_j','harvest_j','background_j','leak_j','spill_j',
                                        'boot_j','sense_j','save_j','tx_j','ack_j','sync_j','load_conversion_j','esr_j')}}

    def account(field,amount):
        ensure_bin()
        ledger[field] += amount
        ledger['stored_j'],ledger['end_s'] = e,t

    def off(reason):
        nonlocal powered,phase,sync_at,next_sample,next_tx,gap_start,reset_pending,sequence
        if not powered:
            return
        known = [r['time_interval_s'][0] for r in memory.values() if r['time_known']]
        gap_start = max(known,default=gap_start)
        emit('brownout',reason=reason,interrupted_phase=phase['kind'] if phase else None,
             pending_sequences=list(pending),energy_j=e)
        if not d['persistent_records']:
            lost = [deepcopy(memory[s]) for s in pending]
            losses.append({'time_s':t,'reason':'volatile_reset','records':lost})
            emit('volatile_image_lost',lost_records=len(lost),sequence_reset=True)
            memory.clear();pending.clear();sequence=0
        powered,phase,sync_at = False,None,None
        next_sample=next_tx=math.inf
        reset_pending=True

    def start(kind,payload=None):
        nonlocal e,phase
        duration,joules = load[kind+'_s'],load[kind+'_j']
        v = math.sqrt(max(0.0,2*e/c))
        current = input_current(v,joules/duration,d['esr_ohm'],load['efficiency'])
        terminal = v-current*d['esr_ohm']
        drawn = v*current*duration
        collapsed = v*v < 4*d['esr_ohm']*(joules/duration)/load['efficiency']
        if collapsed or terminal < load['output_v']+load['dropout_v'] or e-drawn < eoff:
            emit('phase_blocked',phase=kind,terminal_v=terminal,required_j=drawn,energy_j=e)
            if collapsed or terminal < load['output_v']+load['dropout_v']:
                off('ACTIVITY_ESR_DROPOUT')
            return False
        ensure_bin()
        e -= drawn
        esr = current*current*d['esr_ohm']*duration
        conversion = drawn-esr-joules
        account(kind+'_j',joules);account('esr_j',esr);account('load_conversion_j',conversion)
        phase = {'kind':kind,'until':t+duration,'payload':deepcopy(payload)}
        emit('phase_begin',phase=kind,completion_s=t+duration,output_j=joules,
             storage_j=drawn,esr_j=esr,conversion_j=conversion,terminal_v=terminal)
        return True

    def complete(gateway):
        nonlocal phase,sequence,sync_at,next_sample,next_tx,first_boot,reset_pending,beacon_pending
        kind,payload = phase['kind'],phase['payload']
        phase=None
        emit('phase_complete',phase=kind)
        if kind=='boot':
            first_boot=t if first_boot is None else first_boot
            next_sample=next_tx=t
        elif kind=='sync':
            if gateway:
                sync_at=t;beacon_pending=False;next_tx=min(next_tx,t)
                emit('clock_sync',absolute_time_s=t)
                if reset_pending:
                    gaps.append({'lower_s':gap_start,'upper_s':t,'basis':'last known durable timestamp to actual gateway synchronization; true outage endpoints unknown'})
                    reset_pending=False
        elif kind=='sense':
            thermal=task['thermal_reference']
            reading=round((sensor+thermal['nominal_bias_c'])/thermal['quantization_step_c'])*thermal['quantization_step_c']
            interval,known=clock_interval(t,sync_at,task['clock_reference']['nominal_rate_error_ppm'],
                                          task['clock_reference']['rate_bound_ppm'],gap_start)
            sample={'sample_index':len(samples)+1,'time_s':t,'sensor_temperature_c':sensor,'reading_c':reading}
            samples.append(sample)
            emit('sample',sample_index=sample['sample_index'],reading_c=reading,time_known=known)
            record={'kind':0,'created_s':t,'temperature_c':reading,'time_interval_s':interval,
                    'time_known':known,'sample_index':sample['sample_index'],'acked':False}
            if not start('save',record):
                emit('sample_not_committed',sample_index=sample['sample_index'])
        elif kind=='save':
            if len(memory)>=d['nvm_capacity_records']:
                emit('capacity_blocked',sample_index=payload['sample_index'])
                return
            sequence+=1
            record={**payload,'seq':sequence,'committed_s':t,'durable':d['persistent_records']}
            memory[sequence]=deepcopy(record);pending.append(sequence);records.append(deepcopy(record))
            emit('save_commit',seq=sequence,sample_index=record['sample_index'],durable=d['persistent_records'])
        elif kind=='tx':
            record=payload
            visible=ar_service.visible_fields(record,t,sync_at,task['clock_reference']['nominal_rate_error_ppm'])
            raw=ar.frame(record,1701,not visible['age_known'] or visible['age_s']>60)
            packet={'time_s':t,'seq':record['seq'],'sample_index':record['sample_index'],'hex':raw.hex(),'gateway':gateway}
            packets.append(packet)
            valid,reason=ar._receiver(raw,t,record,{'device':{'id':1701},'required_sample_period_s':60}) if gateway else (False,'no-gateway')
            duplicate=record['seq'] in seen
            accepted=valid and (not duplicate or not p['receiver_dedup'])
            ack=valid and ack_loss==0
            if valid:
                seen.add(record['seq'])
                if ack_loss:
                    # This assignment stays in the enclosing simulation state.
                    consume_dropped_ack()
            if gateway:
                receiver.append({**packet,'valid':valid,'reason':reason,'duplicate':duplicate,'accepted':accepted,'ack':ack})
            emit('wire_complete',seq=record['seq'],sample_index=record['sample_index'],gateway=gateway,valid=valid,accepted=accepted,ack=ack)
            next_tx=t+(p['ack_spacing_s'] if ack else p['retry_s'])
            if ack:
                start('ack',record)
        elif kind=='ack':
            seq=payload['seq']
            if seq in pending:
                pending.remove(seq);memory[seq]['acked']=True
            emit('ack_commit',seq=seq,sample_index=payload['sample_index'],durable=d['persistent_records'])

    def consume_dropped_ack():
        nonlocal ack_loss
        ack_loss-=1

    boundaries = {float(horizon)}
    for name in ('irradiance_schedule_w_m2','uniform_shading_transmission'):
        boundaries.update(float(x) for row in task['optical_environment'][name] for x in row[:2])
    boundaries.update(float(x) for row in task['gateway_windows_s'] for x in row)
    boundaries.update(float(row[0]) for row in task['thermal_reference']['air_truth_piecewise_linear_knots_s_c'])
    boundaries=sorted(boundaries)
    while t < horizon-1e-9:
        gateway=any(a<=t<b for a,b in task['gateway_windows_s'])
        if powered and gateway and not previous_gateway:
            beacon_pending=True
            emit('gateway_beacon_available')
        previous_gateway=gateway
        if powered and e < eoff-1e-14:
            off('BACKGROUND_UVLO')
        if phase and t>=phase['until']-1e-9:
            complete(gateway)
        if not powered and e>=eon:
            powered=True
            if not start('boot'):
                powered=False
        if powered and phase is None:
            if gateway and (sync_at is None or beacon_pending):
                if not start('sync'):
                    beacon_pending=False
            elif t>=next_sample-1e-9:
                next_sample=t+p['sample_period_s']
                start('sense')
            elif pending and t>=next_tx-1e-9:
                chosen=max(pending,key=lambda seq:ar_service.rank_value(p['rank'],ar_service.visible_fields(memory[seq],t,sync_at,task['clock_reference']['nominal_rate_error_ppm'])))
                if not start('tx',memory[chosen]):
                    next_tx=t+1
        # Break at every phase, program, environmental and compact ledger edge.
        future=[t+1.0,float(horizon),(math.floor((t+1e-8)/60)+1)*60]
        future += [x for x in boundaries if x>t+1e-9][:1]
        if phase:
            future.append(phase['until'])
        elif powered:
            future += [x for x in (next_sample,next_tx if pending else math.inf) if x>t+1e-9]
        end=min(x for x in future if x>t+1e-10)
        elapsed=end-t
        ensure_bin()
        source=pv_point(task,profile,d,t,math.sqrt(max(0.0,2*e/c)),powered)
        max_diode_residual=max(max_diode_residual,abs(source['diode_residual_a']) if source['input_a'] else 0.0)
        max_optical_violation=max(max_optical_violation,source['raw_power_w']-source['incident_w'])
        harvest=source['bus_power_w']*elapsed
        before=e
        e+=harvest
        spill=max(0.0,e-emax);e-=spill
        leak=min(e,(2*e/c)/load['leakage_ohm']*elapsed);e-=leak
        background=min(e,(load['powered_background_w'] if powered else load['off_background_w'])*elapsed);e-=background
        for field,value in [('optical_j',source['incident_w']*elapsed),('pv_j',source['raw_power_w']*elapsed),
                            ('pv_conversion_j',source['conversion_loss_w']*elapsed),('harvest_j',harvest),
                            ('spill_j',spill),('leak_j',leak),('background_j',background)]:
            ledger[field]+=value
        ledger.update(end_s=end,stored_j=e,last_pv_operating_point=source)
        air,slope=air_value(task['thermal_reference']['air_truth_piecewise_linear_knots_s_c'],t)
        sensor=probe_advance(sensor,air,slope,elapsed,task['thermal_reference']['nominal_tau_s'])
        integration_count+=1
        t=end
    if ledger is not None:
        bins.append(ledger)
    raw={'schema':MODEL_ID,'name':inputs['name'],'input_sha256':identity(inputs),'sources':sources,
         'execution_status':'COMPLETE','duration_s':horizon,'activity':activity,'samples':samples,
         'records':records,'packets':packets,'receiver':receiver,'gaps':gaps,'volatile_losses':losses,
         'energy_bins':bins,'first_boot_s':first_boot,
         'final_state':{'powered':powered,'phase':phase,'energy_j':e,'sensor_temperature_c':sensor,
                        'sequence':sequence,'memory':list(memory.values()),'pending':list(pending),'clock_synchronized':sync_at is not None},
         'numerics':{'maximum_step_s':1.0,'phase_boundaries_explicit':True,'integration_intervals':integration_count,
                     'maximum_conducting_diode_residual_a':max_diode_residual,'maximum_pv_minus_incident_w':max_optical_violation,
                     'scope':'One-second, left-state controlled-source energy model with paid atomic activity impulses and positive completion durations; not switching, RF, continuous-time convergence or physical qualification.'},
         'claim_boundary':'Private constructed LC-PV model qualification only; no inherited A/R verdict, ideal-air device observation, unpowered clock, missing-data normality, hardware or Agent transfer result.'}
    if dependency_identity()!=sources:
        raise RuntimeError('LC_PV_APPARATUS_CHANGED_DURING_EXECUTION')
    raw['result_sha256']=identity(raw)
    return raw
