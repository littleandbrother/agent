"""Independent stdlib-only LC-PV readback; never imports or calls a producer."""
from bisect import bisect_right
import binascii
import hashlib
import json
import math
import struct


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def coverage(times,start,end):
    ordered=sorted(set(times))
    points=[start]+[t for t in ordered if start<t<end]+[end]
    gaps=[{'start_s':a,'end_s':b,'duration_s':b-a} for a,b in zip(points,points[1:]) if b-a>60+1e-7]
    return {'maximum_gap_s':max((b-a for a,b in zip(points,points[1:])),default=end-start),'missing_intervals':gaps}


def review(inputs,raw):
    assert raw['input_sha256']==identity(inputs),'INPUT_IDENTITY_AUDIT_STOP'
    assert raw['result_sha256']==identity({k:v for k,v in raw.items() if k!='result_sha256'}),'RAW_IDENTITY_AUDIT_STOP'
    task,profile,design=inputs['Task'],inputs['Profile'],inputs['Design']
    service=task['service']
    # Exact analytical lag reconstruction, independent of the producer helper.
    knots=task['thermal_reference']['air_truth_piecewise_linear_knots_s_c']
    tau=task['thermal_reference']['nominal_tau_s']
    response=[float(task['initial']['sensor_temperature_c'])]
    for (ta,ya),(tb,yb) in zip(knots,knots[1:]):
        slope=(yb-ya)/(tb-ta)
        response.append(yb-slope*tau+(response[-1]-ya+slope*tau)*math.exp(-(tb-ta)/tau))
    temperatures=[]
    sensor_errors=[]
    for sample in raw['samples']:
        t=sample['time_s']
        index=min(len(knots)-2,max(0,bisect_right([r[0] for r in knots],t)-1))
        ta,ya=knots[index];tb,yb=knots[index+1]
        slope=(yb-ya)/(tb-ta)
        air=ya+slope*(t-ta)
        probe=air-slope*tau+(response[index]-ya+slope*tau)*math.exp(-(t-ta)/tau)
        sensor_errors.append(abs(probe-sample['sensor_temperature_c']))
        temperatures.append(abs(air-sample['reading_c']))
        quant=task['thermal_reference']['quantization_step_c']
        assert abs(round((probe+task['thermal_reference']['nominal_bias_c'])/quant)*quant-sample['reading_c'])<1e-9,'PROBE_QUANTIZATION_AUDIT_STOP'
    assert max(sensor_errors,default=0)<1e-8,'PROBE_RESPONSE_AUDIT_STOP'

    energy_keys=('background_j','leak_j','spill_j','boot_j','sense_j','save_j','tx_j','ack_j','sync_j','load_conversion_j','esr_j')
    max_residual=0.0
    previous=0.0
    totals={k:0.0 for k in ('optical_j','pv_j','pv_conversion_j','harvest_j',*energy_keys)}
    iv_residuals=[]
    pv=profile['pv']
    for row in raw['energy_bins']:
        assert abs(row['start_j']-previous)<1e-10,'ENERGY_CONTINUITY_AUDIT_STOP'
        residual=row['start_j']+row['harvest_j']-sum(row[k] for k in energy_keys)-row['stored_j']
        max_residual=max(max_residual,abs(residual))
        assert abs(row['pv_j']-row['pv_conversion_j']-row['harvest_j'])<1e-10,'PV_CONVERSION_AUDIT_STOP'
        assert row['pv_j']<=row['optical_j']+1e-12 and row['stored_j']>=-1e-14,'OPTICAL_ENERGY_AUDIT_STOP'
        assert row['stored_j']<=.5*design['capacitance_f']*profile['pmic']['maximum_voltage_v']**2+1e-10
        previous=row['stored_j']
        for key in totals:
            totals[key]+=row[key]
        point=row.get('last_pv_operating_point')
        if point:
            current=point['input_a'];junction=point['input_v']+current*pv['series_resistance_ohm']
            denominator=pv['ideality_factor']*pv['series_cells']*1.380649e-23*(pv['cell_temperature_c']+273.15)/1.602176634e-19
            residual=current-point['photocurrent_a']+pv['saturation_current_a']*math.expm1(min(80,junction/denominator))+junction/pv['shunt_resistance_ohm']
            if current:
                iv_residuals.append(abs(residual))
            else:
                assert residual>=-1e-12,'DIODE_BLOCKING_AUDIT_STOP'
    assert max_residual<1e-9 and abs(previous-raw['final_state']['energy_j'])<1e-10,'ENERGY_CLOSURE_AUDIT_STOP'
    assert max(iv_residuals,default=0)<1e-10,'LOADED_IV_AUDIT_STOP'

    by_sample={r['sample_index']:r for r in raw['records']}
    active=None
    memory,pending={},[]
    fifo_violations=[]
    actual_brownouts=[]
    clock_known=False
    clock_state_at_sample={}
    phase_totals={k:0.0 for k in ('boot','sense','save','tx','ack','sync')}
    last_t=-1
    for event in raw['activity']:
        t=event['time_s'];assert t+1e-9>=last_t,'EVENT_ORDER_AUDIT_STOP';last_t=t
        action=event['action']
        if action=='phase_begin':
            assert active is None,'OVERLAPPING_PHASE_AUDIT_STOP'
            active=event
            phase_totals[event['phase']]+=event['output_j']
            assert abs(event['storage_j']-event['output_j']-event['esr_j']-event['conversion_j'])<1e-12
        elif action=='phase_complete':
            assert active and active['phase']==event['phase'],'UNPAID_PHASE_COMPLETION_AUDIT_STOP'
            assert abs(t-active['completion_s'])<1e-7,'PHASE_DURATION_AUDIT_STOP'
            active=None
        elif action=='clock_sync':
            assert any(a<=t<b for a,b in task['gateway_windows_s']),'SYNC_WITHOUT_GATEWAY_AUDIT_STOP'
            clock_known=True
        elif action=='sample':
            clock_state_at_sample[event['sample_index']]=clock_known
            assert clock_known==event['time_known'],'UNPOWERED_CLOCK_AUDIT_STOP'
        elif action=='save_commit':
            record=by_sample[event['sample_index']]
            memory[event['seq']]=dict(record);pending.append(event['seq'])
        elif action=='wire_complete':
            if not pending or event['seq']!=min(pending):
                fifo_violations.append({'time_s':t,'seq':event['seq'],'pending':list(pending)})
        elif action=='ack_commit':
            if event['seq'] in pending:
                pending.remove(event['seq']);memory[event['seq']]['acked']=True
        elif action=='brownout':
            actual_brownouts.append(t);active=None;clock_known=False
            if not design['persistent_records']:
                memory.clear();pending.clear()
    assert memory=={r['seq']:r for r in raw['final_state']['memory']} and pending==raw['final_state']['pending'],'FINAL_MEMORY_AUDIT_STOP'
    for phase,total in phase_totals.items():
        assert abs(total-totals[phase+'_j'])<1e-9,'PHASE_ENERGY_AUDIT_STOP'

    # Decode every actual wire frame and independently rebuild deduplication.
    wire=struct.Struct('>IIiihBB')
    seen=set();accepted=[];duplicates=0;wire_errors=[]
    expected_receiver=[]
    for packet in raw['packets']:
        body=bytes.fromhex(packet['hex'])
        assert len(body)==wire.size+2 and binascii.crc_hqx(body[:-2],65535)==int.from_bytes(body[-2:],'big'),'CRC_AUDIT_STOP'
        device,seq,lo,hi,temp,kind,flags=wire.unpack(body[:-2])
        record=by_sample[packet['sample_index']]
        assert device==1701 and seq==record['seq'] and kind==0
        assert lo==round(record['time_interval_s'][0]*1000)
        assert hi==(round(record['time_interval_s'][1]*1000) if record['time_interval_s'][1] is not None else -1)
        assert temp==round(record['temperature_c']*100) and bool(flags&1)==record['time_known'],'WIRE_RECORD_BINDING_AUDIT_STOP'
        gateway=any(a<=packet['time_s']<b for a,b in task['gateway_windows_s'])
        assert gateway==packet['gateway']
        if not gateway:
            continue
        valid=not(flags&1) or bool(flags&2) or packet['time_s']-lo/1000<=60
        duplicate=seq in seen
        accept=valid and (not duplicate or not inputs['Program']['receiver_dedup'])
        if valid:
            seen.add(seq)
        duplicates+=int(duplicate)
        expected_receiver.append((packet['time_s'],seq,packet['sample_index'],valid,duplicate,accept))
        if accept:
            accepted.append(packet)
    assert expected_receiver==[(r['time_s'],r['seq'],r['sample_index'],r['valid'],r['duplicate'],r['accepted']) for r in raw['receiver']],'RECEIVER_REPLAY_AUDIT_STOP'
    received={}
    for row in accepted:
        received.setdefault(row['sample_index'],row['time_s'])
    final_ids={r['sample_index'] for r in raw['final_state']['memory']}
    lost=[r['sample_index'] for r in raw['records'] if r['sample_index'] not in received and r['sample_index'] not in final_ids]
    sampling=coverage([s['time_s'] for s in raw['samples']],service['continuous_new_sampling']['start_s'],task['duration_s'])
    dark=coverage([s['time_s'] for s in raw['samples']],*service['dark_interval_s'])
    time_failures=[]
    for record in raw['records']:
        low,high=record['time_interval_s'];actual=record['created_s']
        if (not record['time_known'] or high is None or not low<=actual<=high
                or high-low>120+1e-9 or abs((low+high)/2-actual)>60+1e-9):
            time_failures.append(record['sample_index'])
    recovery=service['recovery_at_s']
    old=[r for r in raw['records'] if r['created_s']<recovery and received.get(r['sample_index'],math.inf)>=recovery]
    old_late=[r['sample_index'] for r in old if received.get(r['sample_index'],math.inf)>service['recovery_old_history_deadline_s']+1e-8]
    fresh=[s for s in raw['samples'] if any(a<=s['time_s']<b for a,b in task['gateway_windows_s'])]
    fresh_late=[s['sample_index'] for s in fresh if received.get(s['sample_index'],math.inf)-s['time_s']>service['new_sample_receive_max_delay_s']+1e-8]
    missing_commits=sorted({s['sample_index'] for s in raw['samples']}-set(by_sample))
    first=min((r['time_s'] for r in accepted),default=None)
    gates={
        'cold_start_first_receive':first is not None and first<=service['cold_start_first_valid_receive_deadline_s'],
        'continuous_sampling':bool(raw['samples']) and not sampling['missing_intervals'],
        'dark_sampling':bool(raw['samples']) and not dark['missing_intervals'],
        'all_acquisitions_committed':not missing_commits,
        'committed_records_retained_or_received':not lost,
        'strict_fifo':not fifo_violations,
        'no_duplicate_logical_receipts':len({r['sample_index'] for r in accepted})==len(accepted),
        'all_pre_recovery_unacked_history_by_deadline':not old_late,
        'fresh_receive_from_actual_acquisition_time':not fresh_late,
        'temperature_accuracy':bool(temperatures) and max(temperatures)<=service['maximum_temperature_error_c'],
        'known_accurate_acquisition_times':not time_failures and bool(raw['records'])}
    return {'schema':'pqe-lcpv-independent-readback-v1','input_sha256':identity(inputs),'raw_result_sha256':raw['result_sha256'],
            'verdict':'PASS' if all(gates.values()) else 'FAIL','gates':gates,
            'facts':{'samples':len(raw['samples']),'committed_records':len(raw['records']),'unique_accepted_samples':len(received),
                     'first_receive_s':first,'brownouts':len(actual_brownouts),'brownout_times_s':actual_brownouts,
                     'maximum_sampling_gap_s':sampling['maximum_gap_s'],'sampling_missing_intervals':sampling['missing_intervals'],
                     'maximum_dark_sampling_gap_s':dark['maximum_gap_s'],'dark_missing_intervals':dark['missing_intervals'],
                     'unknown_or_invalid_record_times':len(time_failures),'lost_unreceived_committed_samples':lost,
                     'missing_sample_commits':missing_commits,'pending_old_at_recovery':len(old),'old_history_late_or_missing':len(old_late),
                     'latest_old_history_receive_s':max((received.get(r['sample_index'],recovery) for r in old if r['sample_index'] in received),default=None),
                     'fresh_samples_while_gateway_available':len(fresh),'fresh_late_or_missing':len(fresh_late),
                     'maximum_temperature_error_c':max(temperatures,default=None),'maximum_probe_reconstruction_error_c':max(sensor_errors,default=0),
                     'wire_duplicates_suppressed':duplicates,'fifo_violations':fifo_violations,'reported_gap_markers':raw['gaps']},
            'independent_checks':{'raw_and_input_hash':True,'crc_and_receiver_replay':True,'queue_and_final_memory_replay':True,
                'clock_state_replay':True,'paid_phase_durations':True,'phase_energy_vs_ledger':True,
                'energy_closure_max_residual_j':max_residual,'loaded_iv_checkpoint_max_residual_a':max(iv_residuals,default=0),
                'probe_analytic_reconstruction':True,'energy_totals_j':totals},
            'claim_boundary':'Independent stored-fact/algebra/service readback for this constructed discrete model; no producer rerun, complete-physics validation, hardware, transfer or full-interval normality inference. Missing samples stay missing; gap markers never satisfy strict sampling.'}
