"""Independent review of full native waveforms and source-bound execution facts.

No solver or participant program is executed here. Requirements-only changes
reuse raw execution and produce a new immutable review through Repository.
"""
import csv
import io
import json
from pathlib import Path
import tempfile

import numpy as np

from ..store import identity
from .repository import file_hash
from .repository_feedback_contract import VERSION, ABI, NUMERICS, STATES
from .feedback_native import waveform, observe, coefficients, deck

VALIDATOR = 'bf-feedback-validation-v1'


def protocol(system):
    task = system['task_definition']
    value = {'version':VALIDATOR, 'adapter':VERSION, 'abi':ABI,
        'task_definition':task['id'], 'service':task['standards']['service'],
        'acceptance':task['acceptance'], 'scenario':task['scenario'],
        'rules':NUMERICS, 'authority':{'design':'participant candidate',
            'requirements':'operator', 'validation':'independent immutable record'},
        'scope':'reciprocal linear piezo, vendor PMIC, declared current model, host C, digital RX',
        'sources':{p.name:file_hash(p) for p in (Path(__file__),Path(__file__).with_name('repository_feedback_contract.py'))}}
    return {'id':'VP-'+identity(value),**value}


def interval_min(t, values, a, b):
    if not 0 <= a < b <= t[-1]+1e-9: raise ValueError('FEEDBACK_REVIEW_WINDOW')
    return float(min(np.r_[np.interp([a,b],t,values), values[(t>=a)&(t<=b)]]))


def phase(repo, system, execution, name):
    scenario = system['task_definition']['scenario']; artifacts = execution['artifacts']
    def data(path): return (repo.root/'blobs'/artifacts[path]['sha256']).read_bytes()
    def obj(path): return json.loads(data(path))
    convergence = obj(name+'/convergence.json')
    if convergence.get('converged') is not True: raise ValueError('FEEDBACK_REVIEW_UNCONVERGED')
    step = NUMERICS['program_step_s']/(NUMERICS['refinement'] if name=='fine' else 1)
    if convergence.get('step_s')!=step: raise ValueError('FEEDBACK_REVIEW_STEP')
    grid = np.linspace(0,scenario['duration_s'],int(np.ceil(scenario['duration_s']/step))+1)
    names = ['t_s','dt_s','supply_v','pgood_v','powered','boot','state','seq','value','crc']
    reader = csv.DictReader(io.StringIO(data(name+'/program.csv').decode()))
    if reader.fieldnames != names: raise ValueError('FEEDBACK_REVIEW_PROGRAM_SCHEMA')
    rows = np.array([[float(r[k]) for k in names] for r in reader])
    if rows.shape != (len(grid)-1,10) or not np.isfinite(rows).all() or not np.allclose(rows[:,:2],
            np.column_stack([grid[:-1],np.diff(grid)]),rtol=0,atol=1e-12):
        raise ValueError('FEEDBACK_REVIEW_PROGRAM_GRID')
    pairs = np.asarray(obj(name+'/load.json'))
    if pairs.ndim!=2 or pairs.shape[1]!=2 or not np.isfinite(pairs).all() or pairs[0,0]!=0 or abs(pairs[-1,0]-grid[-1])>1e-9 or np.any(np.diff(pairs[:,0])<=0):
        raise ValueError('FEEDBACK_REVIEW_LOAD_GRID')
    design = json.loads(data('design.json'))
    if artifacts['design.json']['sha256'] != system['files']['design.json']['sha256'] or artifacts['main.c']['sha256'] != system['files']['firmware/main.c']['sha256']:
        raise ValueError('FEEDBACK_REVIEW_CANDIDATE_INPUTS')
    recorded_env = obj('execution-environment.json')
    if recorded_env != execution['descriptor']['environment']:
        raise ValueError('FEEDBACK_REVIEW_ENVIRONMENT')
    if file_hash(repo.root/'blobs'/artifacts['program/firmware']['sha256']) != execution['metrics']['firmware_sha256']:
        raise ValueError('FEEDBACK_REVIEW_BINARY')
    if data(name+'/system.cir').decode() != deck(design,scenario,pairs,min(NUMERICS['native_max_step_s'],step/10)):
        raise ValueError('FEEDBACK_REVIEW_NETLIST')
    if convergence['load_sha256'] != artifacts[name+'/load.json']['sha256'] or convergence['program_sha256'] != artifacts[name+'/program.csv']['sha256']:
        raise ValueError('FEEDBACK_REVIEW_FINAL_BINDING')
    last = convergence['iterations'][-1]
    if (last['native']['raw_sha256'] != artifacts[name+'/system.raw.zlib']['sha256'] or
            last['max_current_difference_a']>NUMERICS['current_tolerance_a'] or
            (last['max_voltage_difference_v'] is not None and last['max_voltage_difference_v']>NUMERICS['voltage_tolerance_v'])):
        raise ValueError('FEEDBACK_REVIEW_FIXED_POINT')
    with tempfile.TemporaryDirectory(prefix='bf-feedback-review-') as tmp:
        root = Path(tmp); (root/'system.raw.zlib').write_bytes(data(name+'/system.raw.zlib'))
        t,v = waveform(root,scenario['duration_s'])
    if not np.allclose(rows[:,2],observe(t,v['v(out)'],grid)[:-1],rtol=0,atol=1e-10) or not np.allclose(
            rows[:,3],observe(t,v['v(pgood)'],grid)[:-1],rtol=0,atol=1e-10):
        raise ValueError('FEEDBACK_REVIEW_SUPPLY_OBSERVATIONS')
    powered, boot = False, 0
    current = scenario['current_model']['values_a']; states = list(STATES)
    for r in rows:
        if not all(r[k]==int(r[k]) for k in range(4,10)) or not 0 <= r[6] <= 3:
            raise ValueError('FEEDBACK_REVIEW_PROGRAM_VALUES')
        if powered and r[2]<scenario['brownout_v']: powered=False
        if not powered and r[2]>=scenario['start_v'] and r[3]>=scenario['pgood_min_v']:
            powered,boot=True,boot+1
        if (r[4],r[5]) != (int(powered),boot) or (not powered and r[6]!=0) or (powered and r[6]==0):
            raise ValueError('FEEDBACK_REVIEW_RESET')
    # Mid-interval values avoid the declared 1 ns transition ramps.
    mid = grid[:-1]+np.diff(grid)/2
    target = np.array([current[states[int(s)]] for s in rows[:,6]])
    load_equal = np.allclose(np.interp(mid,pairs[:,0],pairs[:,1]),target,rtol=0,atol=1e-12)
    consumed = np.interp(t,pairs[:,0],pairs[:,1])*np.clip(v['v(out)']/1.8,0,1)
    load_error = float(max(abs(consumed-v['i(bload)'])))
    load_equal = bool(load_equal and load_error<=NUMERICS['load_current_tolerance_a'])
    # Reconstruct activity runs from the independent state witness, then match
    # only completed, same-boot sample/TX pairs against actual VDD windows.
    changes = [0]+[i for i in range(1,len(rows)) if tuple(rows[i,4:])!=tuple(rows[i-1,4:])]+[len(rows)]
    events=[]
    for a,b in zip(changes,changes[1:]):
        r=rows[a]
        if int(r[6]) not in (2,3): continue
        end=float(rows[b,0]) if b<len(rows) else float(grid[-1])
        done=bool(b<len(rows) and rows[b,4] and rows[b,5]==r[5])
        events.append({'t_s':float(r[0]),'duration_s':end-float(r[0]),'state':states[int(r[6])],
            'boot':int(r[5]),'seq':int(r[7]),'value':int(r[8]),'crc':int(r[9]),'completed':done})
    if events != obj(name+'/events.json'): raise ValueError('FEEDBACK_REVIEW_EVENT_WITNESS')
    delivered=[]; invalid=[]; low=[]; tx=[]
    for e in events:
        if e['state']!='tx' or not e['completed']: continue
        tx.append(e)
        samples=[s for s in events if s['state']=='sample' and s['completed'] and s['boot']==e['boot'] and s['seq']==e['seq'] and
                 s['t_s']+s['duration_s']<=e['t_s']+1e-10]
        sample=samples[-1] if samples else None
        valid=bool(sample and sample['value']==e['value']==scenario['sensor_value'] and
            0<=e['seq']<=65535 and e['crc']==((e['seq']^e['value']^0xA5)&255) and
            sample['duration_s']+1e-10>=scenario['minimum_sample_s'] and e['duration_s']+1e-10>=scenario['minimum_tx_s'] and
            e['t_s']+e['duration_s']-sample['t_s']<=scenario['sample_validity_s']+1e-10)
        if not valid: invalid.append(e['seq'])
        supplied=bool(sample and min(interval_min(t,v['v(out)'],e['t_s'],e['t_s']+e['duration_s']),
            interval_min(t,v['v(out)'],sample['t_s'],sample['t_s']+sample['duration_s']))>=scenario['minimum_supply_v'])
        if not supplied: low.append(e['seq'])
        if valid and supplied: delivered.append(e['seq'])
    m=coefficients(design,scenario)
    # LTspice stores the two saved node voltages of V(a,b) separately.
    q=(v['v(spring)']-v['v(coupling)'])/m['stiffness_n_m']; u=v['i(vsense)']
    energy=.5*m['mass_kg']*u*u+.5*m['stiffness_n_m']*q*q+.5*m['capacitance_f']*v['v(piezo)']**2
    def accumulated(y): return np.r_[0,np.cumsum(np.diff(t)*(y[1:]+y[:-1])/2)]
    work=accumulated(v['v(drive)']*u); port=accumulated(v['v(piezo)']*v['i(vport)'])
    loss=accumulated(m['damping_n_s_m']*u*u)
    residual=energy-energy[0]+port+loss-work
    relative=float(max(abs(residual))/max(max(abs(work)),max(abs(port)),max(energy),1e-12))
    stored=.5*design['storage_f']*v['v(vin)']**2+.5*design['output_f']*v['v(out)']**2
    stored+=.5e-6*(v['v(vin)']-v['v(cap)'])**2+.5*4.7e-6*v['v(vin2)']**2+.5*design['inductance_h']*v['i(l1)']**2
    load_energy=float(np.trapezoid(v['v(out)']*v['i(bload)'],t))
    # LTspice UIC writes a synthetic zero row at t=0, then applies capacitor
    # ICs at the first positive time. Check that first state against the task;
    # initial energy comes from the declared capacitor ICs, never the sentinel.
    first=int(np.flatnonzero(t>0)[0])
    initial_error=max(abs(v['v(vin)'][first]-scenario['initial_storage_v']),
        abs(v['v(out)'][first]-scenario['initial_output_v']),
        abs(v['v(vin)'][first]-v['v(cap)'][first]),abs(v['v(vin2)'][first]))
    initial_equal=bool(t[first]<=1e-7 and initial_error<=NUMERICS['initial_condition_tolerance_v'])
    initial_energy=.5*design['storage_f']*scenario['initial_storage_v']**2+.5*design['output_f']*scenario['initial_output_v']**2
    unresolved=float(port[-1]-(stored[-1]-initial_energy)-load_energy)
    return {'delivered':delivered,'completed_tx':tx,'invalid_frames':invalid,'low_supply':low,
        'load_equal':load_equal,'load_error_a':load_error,'source_residual_relative':relative,
        'peak_tip_m':float(max(abs(q))),'linear_domain':bool(max(abs(q))<=NUMERICS['linear_displacement_ratio']*design['length_m']),
        'load_energy_j':load_energy,'unresolved_electrical_j':unresolved,
        'energy_lower_bound':bool(unresolved>=-NUMERICS['energy_absolute_tolerance_j']),
        'initial_state_equal':initial_equal,'initial_state_error_v':float(initial_error),
        'initial_storage_v':float(v['v(vin)'][first]),'initial_output_v':float(v['v(out)'][first]),
        'initial_energy_j':initial_energy,
        'first_powered_s':float(rows[np.flatnonzero(rows[:,4])[0],0]) if np.any(rows[:,4]) else None,
        'boots':boot,'final_storage_v':float(v['v(vin)'][-1]),'final_output_v':float(v['v(out)'][-1]),
        'step_s':step,'convergence':convergence}


def independent_check(repo, system, execution):
    coarse=phase(repo,system,execution,'coarse'); fine=phase(repo,system,execution,'fine')
    task=system['task_definition']; minimum=task['acceptance']['receiver_service']['minimum_packets']
    def result(passed,**findings): return {'status':'PASS' if passed else 'FAIL',**findings}
    same = coarse['delivered']==fine['delivered'] and len(coarse['completed_tx'])==len(fine['completed_tx'])
    timing=max([abs((a['t_s']+a['duration_s'])-(b['t_s']+b['duration_s'])) for a,b in zip(coarse['completed_tx'],fine['completed_tx'])]+[0.])
    energy_delta=abs(coarse['load_energy_j']-fine['load_energy_j'])
    numeric=bool(same and timing<=NUMERICS['refinement_event_steps']*coarse['step_s']+1e-10 and
        energy_delta<=max(NUMERICS['energy_absolute_tolerance_j'],abs(fine['load_energy_j'])*NUMERICS['refinement_energy_relative']))
    return {'source_model':result(fine['linear_domain'] and fine['source_residual_relative']<=NUMERICS['relative_mechanical_residual'],
                peak_tip_m=fine['peak_tip_m'],mechanical_residual_relative=fine['source_residual_relative']),
        'load_binding':result(fine['load_equal'] and coarse['load_equal'],load_error_a=fine['load_error_a'],current_model=task['scenario']['current_model']),
        'power_service':result(len(fine['completed_tx'])>=minimum and not fine['low_supply'] and fine['energy_lower_bound'] and fine['initial_state_equal'],
                first_powered_s=fine['first_powered_s'],boots=fine['boots'],low_supply_sequences=fine['low_supply'],
                completed_tx=len(fine['completed_tx']),load_energy_j=fine['load_energy_j'],unresolved_electrical_j=fine['unresolved_electrical_j'],
                initial_energy_j=fine['initial_energy_j'],initial_state_error_v=fine['initial_state_error_v']),
        'receiver_service':result(len(fine['delivered'])>=minimum and len(fine['delivered'])==len(set(fine['delivered'])) and not fine['invalid_frames'],
                received_sequences=fine['delivered'],invalid_frames=fine['invalid_frames'],minimum_packets=minimum),
        'coupling_numerics':result(numeric,converged=True,steps_s=[coarse['step_s'],fine['step_s']],
                same_service_result=same,maximum_tx_time_difference_s=timing,load_energy_difference_j=energy_delta)}
