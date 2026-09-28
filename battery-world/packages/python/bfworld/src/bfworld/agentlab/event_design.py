"""Transient electromechanical event adapter, executed by ngspice.

This is a declared reduced-order candidate-model apparatus, not a hardware
oracle. Mechanical velocity/displacement are circuit state variables; piezo
coupling conserves energy and the rectifier/storage/load are solved together.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

from .store import identity

SPICE = Path('/opt/homebrew/bin/ngspice')
SCOPE = '单模态机电耦合、二极管整流、行为电源管理及阶段负载的 ngspice 瞬态计算；不是已校准磁体、原厂 PMIC 模型或硬件验收。'
SKILL = """# Event-level transient co-design
Write an event-design JSON file in your workspace, then bf_engineering run
engine=event-transient parameters={spec_path:"event-design.json"}.
This engine solves coupled mechanics, piezoelectric voltage, a full diode
bridge, storage and a hysteretic power/load state machine using ngspice.
It does not prescribe a target product or preload a paper's design.

Required schema_version: bf-event-design-v1. All numeric values use SI units.
mechanics: mass_kg, stiffness_n_m, damping_ns_m, coupling_n_v, piezo_capacitance_f.
drive: kind (force-pwl or dipole-potential), trajectory (array of [time_s,value]
starting at time zero). force-pwl values are newtons and qualify only a force
input component model, NOT a magnetic mechanism. dipole-potential values are
driver position metres; also give gap_m, moment_product_a2_m4 and magnet_extent_m.
Its potential is -1e-7*moment_product/(gap^2+(driver-q)^2)^1.5 for dipoles
perpendicular to the motion plane with antiparallel moments (attractive). The force on q is
3e-7*moment_product*(driver-q)/(gap^2+(driver-q)^2)^2.5. A far-field check uses
gap/magnet_extent>=5. This is an applicability check, not a magnetic calibration.
storage: capacitance_f, initial_v, leakage_a.
power: start_v, stop_v, output_v, efficiency (0,1], quiescent_a.
workload: origin (estimate or measured), stages [{name,duration_s,current_a}],
tx_stage (stage name), idle_current_a, firmware_sha256 (64 hex, or null).
Measured origin additionally requires measurement_sha256 and operator-imported
measurement evidence; otherwise it is rejected. A JSON label alone is not a
measurement. The ideal regulated output requires stop_v>=output_v.
diode: saturation_a, emission_coefficient, series_ohm, junction_capacitance_f,
transit_time_s (source/assumption required).
simulation: duration_s, step_s (<=1/100 of the linear coupled open-circuit period and <=1/20
of shortest stage; <=200000 steps). Fine validation runs at half this step.
requirements: action_time_s, deadline_s, max_deflection_m.
provenance: nonempty list [{parameter,origin,source,locator,conditions}]. origin
is assumption, datasheet, paper or measured. Every parameter group must be
covered. Store exact acquired source IDs where available; numerical agreement
does not establish that parameter values or physical assumptions are true.

Results include immutable input, actual ngspice netlists/logs, channels.csv,
energy checks, coarse/fine checks, startup/brownout/tx attempt times and a
SIMULATED receiver event. The receiver assumes reception and uses the stated
single-action boundary; radio reliability and physical event identity remain
unverified. Firmware compilation and measured load are separate gates.
Do not change the verifier or relax user requirements to pass. Design, model
and workflow revisions are separate. Use the actual timeline to investigate
failures, and fetch public references when assumptions lack support.
"""


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('EVENT_PARAMETER_INVALID:' + name)
    return float(value)


def validate(spec):
    if not isinstance(spec, dict) or spec.get('schema_version') != 'bf-event-design-v1':
        raise ValueError('EVENT_SCHEMA_REQUIRED')
    ranges = {
        'mechanics': {'mass_kg':(1e-7,10), 'stiffness_n_m':(.001,1e7), 'damping_ns_m':(1e-9,1e4), 'coupling_n_v':(1e-10,1), 'piezo_capacitance_f':(1e-12,.01)},
        'storage': {'capacitance_f':(1e-9,10), 'initial_v':(0,100), 'leakage_a':(0,.1)},
        'power': {'start_v':(.1,100), 'stop_v':(.1,100), 'output_v':(.1,24), 'efficiency':(.01,1), 'quiescent_a':(0,.1)},
        'diode': {'saturation_a':(1e-15,.001), 'emission_coefficient':(1,4), 'series_ohm':(.001,1e5), 'junction_capacitance_f':(1e-15,1e-6), 'transit_time_s':(0,.001)},
        'simulation': {'duration_s':(.001,30), 'step_s':(1e-7,.001)},
        'requirements': {'action_time_s':(0,30), 'deadline_s':(.0001,30), 'max_deflection_m':(1e-7,.1)},
    }
    for group, fields in ranges.items():
        for key, bounds in fields.items():
            number(spec.get(group, {}).get(key), group+'.'+key, *bounds)
    p, sim, m = spec['power'], spec['simulation'], spec['mechanics']
    if not p['start_v'] > p['stop_v'] >= p['output_v']:
        raise ValueError('EVENT_POWER_THRESHOLDS_INVALID')
    if sim['duration_s']/sim['step_s'] > 200000:
        raise ValueError('EVENT_STEP_BUDGET')
    open_circuit_stiffness=m['stiffness_n_m']+m['coupling_n_v']**2/m['piezo_capacitance_f']
    if sim['step_s'] > 2*math.pi*math.sqrt(m['mass_kg']/open_circuit_stiffness)/100:
        raise ValueError('EVENT_MECHANICAL_STEP_TOO_LARGE')
    drive = spec.get('drive', {})
    if drive.get('kind') not in ('force-pwl','dipole-potential'):
        raise ValueError('EVENT_DRIVE_KIND_INVALID')
    trajectory = drive.get('trajectory', [])
    if not isinstance(trajectory,list) or not 2 <= len(trajectory) <= 200 or not isinstance(trajectory[0],list) or len(trajectory[0])!=2 or trajectory[0][0] != 0:
        raise ValueError('EVENT_TRAJECTORY_INVALID')
    previous = -1
    for pair in trajectory:
        if not isinstance(pair,list) or len(pair)!=2:
            raise ValueError('EVENT_TRAJECTORY_INVALID')
        t = number(pair[0], 'drive.time', 0, sim['duration_s'])
        number(pair[1], 'drive.value', -100,100)
        if t <= previous:
            raise ValueError('EVENT_TRAJECTORY_TIME_ORDER')
        previous = t
    if drive['kind'] == 'dipole-potential':
        for key, bounds in {'gap_m':(1e-5,1),'moment_product_a2_m4':(1e-12,100),'magnet_extent_m':(1e-6,.1)}.items():
            number(drive.get(key),key,*bounds)
    w = spec.get('workload',{})
    if w.get('origin') not in ('estimate','measured'):
        raise ValueError('EVENT_LOAD_ORIGIN_REQUIRED')
    if w['origin']=='measured' and not w.get('measurement_sha256'):
        raise ValueError('EVENT_MEASUREMENT_BINDING_REQUIRED')
    if w.get('firmware_sha256') is not None and not re.fullmatch('[a-f0-9]{64}',w['firmware_sha256']):
        raise ValueError('EVENT_FIRMWARE_HASH_INVALID')
    number(w.get('idle_current_a'),'idle_current_a',0,1)
    stages = w.get('stages',[])
    if not isinstance(stages,list) or not 1<=len(stages)<=16:
        raise ValueError('EVENT_STAGES_REQUIRED')
    names=[]
    for s in stages:
        if not isinstance(s.get('name'),str) or not re.fullmatch('[a-zA-Z0-9_-]{1,40}',s['name']):
            raise ValueError('EVENT_STAGE_NAME_INVALID')
        names.append(s['name'])
        duration=number(s.get('duration_s'),'stage.duration',1e-5,10)
        number(s.get('current_a'),'stage.current',1e-9,1)
        if sim['step_s']>duration/20:
            raise ValueError('EVENT_LOAD_STEP_TOO_LARGE')
    if len(names)!=len(set(names)) or w.get('tx_stage') not in names:
        raise ValueError('EVENT_TX_STAGE_INVALID')
    provenance=spec.get('provenance',[])
    if not isinstance(provenance,list) or not provenance:
        raise ValueError('EVENT_PROVENANCE_REQUIRED')
    for index,r in enumerate(provenance):
        if not isinstance(r,dict):raise ValueError(f'EVENT_PROVENANCE_RECORD_INVALID: provenance[{index}] must be an object')
        if r.get('origin') not in ('assumption','datasheet','paper','measured'):
            raise ValueError(f'EVENT_PROVENANCE_RECORD_INVALID: provenance[{index}].origin must be assumption, datasheet, paper or measured')
        missing=[k for k in ('parameter','source','locator','conditions') if not isinstance(r.get(k),str) or not r[k].strip()]
        if missing:raise ValueError(f'EVENT_PROVENANCE_RECORD_INVALID: provenance[{index}] needs nonempty strings '+','.join(missing))
    groups={r['parameter'].split('.')[0] for r in provenance}
    if not {'mechanics','drive','storage','power','workload','diode','requirements'} <= groups:
        raise ValueError('EVENT_PROVENANCE_GROUP_MISSING: '+','.join(sorted({'mechanics','drive','storage','power','workload','diode','requirements'}-groups)))
    return spec


def request(app, owner, params):
    if set(params)!={'spec_path'} or not isinstance(params['spec_path'],str):
        raise ValueError('EVENT_SPEC_PATH_REQUIRED')
    root=(app.store.root.parent/'participants'/owner).resolve()
    source=(root/params['spec_path']).resolve()
    if not source.is_relative_to(root) or not source.is_file() or source.stat().st_size>100000:
        raise ValueError('EVENT_SPEC_PATH_DENIED')
    spec=validate(json.loads(source.read_text()))
    if spec['workload']['origin']=='measured':
        from .event_measurement import verified_load
        record=verified_load(app.store.root.parent, owner, spec['workload'])
        voltage=spec['power']['output_v']
        if abs(record['voltage_min_v']-voltage)>voltage*.05 or abs(record['voltage_max_v']-voltage)>voltage*.05:
            raise ValueError('MEASUREMENT_REGULATED_VOLTAGE_MISMATCH')
    return {'event_spec':spec,'event_spec_sha256':identity(spec),'event_source_path':params['spec_path']}


def netlist(spec, step, out_name):
    m,s,p,w,d= [spec[k] for k in ('mechanics','storage','power','workload','drive')]
    drive=' '.join(f'{t:.12g} {v:.12g}' for t,v in d['trajectory'])
    force='v(drive)' if d['kind']=='force-pwl' else f"{3e-7*d['moment_product_a2_m4']:.12g}*(v(drive)-v(q))/pow({d['gap_m']**2:.12g}+pow(v(drive)-v(q),2),2.5)"
    elapsed=0
    clauses=[]
    for stage in w['stages']:
        elapsed+=stage['duration_s']
        clauses.append(f"v(timer)<{elapsed:.12g}?{stage['current_a']:.12g}:")
    current='('+''.join(clauses)+str(w['idle_current_a'])+')'
    oncurrent=f"{p['output_v']:.12g}*{current}/({p['efficiency']:.12g}*max(v(cap,neg),0.01))"
    diode=spec['diode']
    return f'''BF event reduced-order coupled transient v1
Vdrive drive 0 PWL({drive})
Cmass u 0 {m['mass_kg']:.12g} ic=0
Rdamping u 0 {1/m['damping_ns_m']:.12g}
Bspring u 0 I={m['stiffness_n_m']:.12g}*v(q)
Bpiezo_force u 0 I={m['coupling_n_v']:.12g}*v(p)
Bforce 0 u I={force}
Bforce_monitor force 0 V={force}
Cposition q 0 1 ic=0
Bposition 0 q I=v(u)
Cpiezo p 0 {m['piezo_capacitance_f']:.12g} ic=0
Bpiezo_current 0 p I={m['coupling_n_v']:.12g}*v(u)
D1 p rect Dbridge
D2 0 rect Dbridge
D3 neg p Dbridge
D4 neg 0 Dbridge
.model Dbridge D(is={diode['saturation_a']:.12g} n={diode['emission_coefficient']:.12g} rs={diode['series_ohm']:.12g} cjo={diode['junction_capacitance_f']:.12g} tt={diode['transit_time_s']:.12g})
Vsense rect cap 0
Cstorage cap neg {s['capacitance_f']:.12g} ic={s['initial_v']:.12g}
Bquiescent cap neg I={p['quiescent_a']+s['leakage_a']:.12g}*v(cap,neg)/(abs(v(cap,neg))+0.01)
Rreference neg 0 1e12
* gate and timer are mathematical state, not an external product supply.
* PMIC control energy is explicitly included in Bquiescent above.
Vlogic logic 0 1
Sgate logic gate cap neg ENABLE
Rgate gate 0 1
.model ENABLE sw(ron=1e-6 roff=1e12 vt={(p['start_v']+p['stop_v'])/2:.12g} vh={(p['start_v']-p['stop_v'])/2:.12g})
Ctimer timer 0 1 ic=0
Btimer 0 timer I=(v(gate)>0.5?1:-v(timer)/{step/10:.12g})
Bload cap neg I=(v(gate)>0.5?{oncurrent}:0)
.options reltol=1e-5 abstol=1e-11 vntol=1e-8 method=gear
.save all @bload[i] @bquiescent[i] @d1[id] @d2[id] @d3[id] @d4[id]
.control
set noaskquit
set wr_singlescale
set wr_vecnames
tran {step:.12g} {spec['simulation']['duration_s']:.12g} 0 {step:.12g} uic
let storage_v=v(cap)-v(neg)
let load_i=@bload[i]
let diode_loss=(v(p)-v(rect))*@d1[id]+(-v(rect))*@d2[id]+(v(neg)-v(p))*@d3[id]+v(neg)*@d4[id]
wrdata {out_name} v(drive) v(q) v(u) v(p) storage_v v(gate) v(timer) v(force) i(Vsense) load_i diode_loss @bquiescent[i]
quit
.endc
.end
'''


def integrate(times, values):
    return sum((times[i]-times[i-1])*(values[i]+values[i-1])/2 for i in range(1,len(times)))


def read_channels(path):
    with path.open() as f:
        header=f.readline()
        rows=[[float(x) for x in line.split()] for line in f if line.strip()]
    if len(rows)<10 or any(len(r)!=13 or any(not math.isfinite(v) for v in r) for r in rows):
        raise ValueError('EVENT_SPICE_CHANNELS_INVALID:'+header[:100])
    keys=['time_s','drive','displacement_m','velocity_m_s','piezo_v','storage_v','enabled','stage_time_s','force_n','rectifier_a','load_a','diode_loss_w','quiescent_a']
    return [dict(zip(keys,r)) for r in rows]


def summarize(spec, rows):
    m,s,p,w,req=[spec[k] for k in ('mechanics','storage','power','workload','requirements')]
    times=[r['time_s'] for r in rows]
    mech=integrate(times,[r['force_n']*r['velocity_m_s'] for r in rows])
    damping=integrate(times,[m['damping_ns_m']*r['velocity_m_s']**2 for r in rows])
    delivered=integrate(times,[r['storage_v']*r['load_a'] for r in rows])
    idle=integrate(times,[r['storage_v']*r['quiescent_a'] for r in rows])
    rectified=integrate(times,[r['storage_v']*r['rectifier_a'] for r in rows])
    last=rows[-1]
    final_mech=.5*m['mass_kg']*last['velocity_m_s']**2+.5*m['stiffness_n_m']*last['displacement_m']**2
    final_piezo=.5*m['piezo_capacitance_f']*last['piezo_v']**2
    delta_store=.5*s['capacitance_f']*(last['storage_v']**2-s['initial_v']**2)
    storage_residual=rectified-delivered-idle-delta_store
    # Difference at the mechanical/piezo boundary includes diode dissipation.
    inferred_rectifier_loss=mech-damping-final_mech-final_piezo-rectified
    tx_end=0
    for stage in w['stages']:
        tx_end+=stage['duration_s']
        if stage['name']==w['tx_stage']:
            break
    starts,completed,brownouts=[],[],[]
    active,done=False,False
    for row in rows:
        enabled=row['enabled']>.5
        if enabled and not active:
            starts.append(row['time_s']);done=False
        if enabled and not done and row['stage_time_s']>=tx_end:
            completed.append(row['time_s']);done=True
        if not enabled and active and not done:
            brownouts.append(row['time_s'])
        active=enabled
    eligible=[t for t in completed if req['action_time_s']<=t<=req['action_time_s']+req['deadline_s']]
    d=spec['drive']
    applicability=d['kind']!='dipole-potential' or d['gap_m']/d['magnet_extent_m']>=5
    checks={'storage_balance':abs(storage_residual)<=max(1e-8,abs(rectified)*.03),
            'nonnegative_rectifier_loss':inferred_rectifier_loss>=-max(1e-8,abs(mech)*.03),
            'deflection_within_requirement':max(abs(r['displacement_m']) for r in rows)<=req['max_deflection_m'],
            'source_applicability_screen':applicability,'simulated_event_in_deadline':bool(eligible),
            'transient_complete':abs(times[-1]-spec['simulation']['duration_s'])<=spec['simulation']['step_s']}
    return {'checks':checks,'startup_times_s':starts,'brownout_times_s':brownouts,'tx_complete_times_s':completed,
            'receiver':{'kind':'simulation-assuming-reception','events':1 if eligible else 0,'duplicate_tx_attempts':max(0,len(completed)-1),
                        'latency_s':eligible[0]-req['action_time_s'] if eligible else None,'physical_reception_verified':False,
                        'deduplication':'single input action window; physical multi-action identity unverified'},
            'peak_storage_v':max(r['storage_v'] for r in rows),'peak_deflection_m':max(abs(r['displacement_m']) for r in rows),
            'energy_j':{'mechanical_port_work':mech,'damping_loss':damping,'rectified':rectified,'load_input':delivered,
                        'quiescent_and_leakage':idle,'storage_change':delta_store,'remaining_mechanical':final_mech,
                        'remaining_piezo':final_piezo,'inferred_rectifier_loss':inferred_rectifier_loss,'storage_balance_residual':storage_residual},
            'scope':SCOPE,'hardware_verified':False,'firmware_measured':w['origin']=='measured'}


def run(engineering, job, directory, deadline):
    spec=validate(job['event_spec'])
    if identity(spec)!=job['event_spec_sha256']:
        raise ValueError('EVENT_INPUT_TAMPER')
    (directory/'event-design.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2))
    reports={}
    for name, factor in [('coarse',1),('fine',.5)]:
        source=directory/(name+'.cir')
        source.write_text(netlist(spec,spec['simulation']['step_s']*factor,name+'.tsv'))
        engineering.command(job['id'],job['owner'],[str(SPICE),'-n','-b',str(source)],directory,deadline)
        rows=read_channels(directory/(name+'.tsv'))
        if abs(rows[-1]['time_s']-spec['simulation']['duration_s'])>spec['simulation']['step_s']:
            raise ValueError('EVENT_SPICE_TRANSIENT_INCOMPLETE')
        reports[name]=summarize(spec,rows)
        if name=='fine':
            with (directory/'channels.csv').open('w') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    coarse,fine=reports['coarse'],reports['fine']
    convergence={k:abs(coarse[k]-fine[k])/max(abs(fine[k]),1e-9) for k in ('peak_storage_v','peak_deflection_m')}
    numerical=all(v<.03 for v in convergence.values()) and bool(coarse['receiver']['events'])==bool(fine['receiver']['events'])
    result={'schema_version':'bf-event-run-v1','engine':'ngspice','event_spec_sha256':identity(spec),
            'coarse':coarse,'fine':fine,'numerical_relative_changes':convergence,
            'timeline':[{k:r[k] for k in ('time_s','storage_v','displacement_m','enabled','load_a')} for r in rows[::max(1,len(rows)//300)]],
            'checks':{**fine['checks'],'coarse_fine_agreement':numerical},'claim_level':'reduced-order-computation',
            'hardware_verified':False,'product_verified':False,'scope':SCOPE,
            'limitations':['磁力、阻尼和材料参数未因数值收敛而获得实物校准。','电源管理为行为模型，非原厂芯片模型。','无线接收是假设，未测量射频可靠性。','软件状态负载必须另与实际二进制绑定和测量。']}
    result['computational_checks_passed']=all(result['checks'].values())
    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result
