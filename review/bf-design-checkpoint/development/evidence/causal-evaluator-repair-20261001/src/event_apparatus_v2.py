"""Separately versioned, generic reduced-order diagnostic apparatus.
Not a vendor PMIC model; not authoritative door-world or hardware evidence.
Derived from pinned event_design.py; attribution and hash in source-binding.json.
"""
import math
import re
from pathlib import Path
MODEL_VERSION = "bf-event-apparatus-v2-fixed-reset-ports"
SPEC_VERSION = "bf-event-design-v2"
CHANNEL_KEYS = ['time_s','drive','displacement_m','velocity_m_s','piezo_v','storage_v','enabled','stage_time_s','force_n','rectifier_a','load_a','diode_loss_w','quiescent_a','piezo_to_bridge_a','negative_rail_v']


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('EVENT_PARAMETER_INVALID:' + name)
    return float(value)

def validate(spec):
    if not isinstance(spec, dict) or spec.get('schema_version') != SPEC_VERSION:
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
    control=spec.get('control',{})
    number(control.get('timer_reset_tau_s'),'timer_reset_tau_s',1e-9,.01)
    if control.get('feedback_mode') not in ('reciprocal','no-feedback'):
        raise ValueError('EVENT_FEEDBACK_MODE_REQUIRED')
    if 'control' not in groups:
        raise ValueError('EVENT_CONTROL_PROVENANCE_REQUIRED')
    return spec

def netlist(spec, step, out_name):
    validate(spec)
    number(step,'step',1e-7,spec['simulation']['step_s'])
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',out_name):
        raise ValueError('EVENT_OUTPUT_BASENAME_REQUIRED')
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
    return f'''BF event apparatus v2 fixed-reset explicit ports
Vdrive drive 0 PWL({drive})
Cmass u 0 {m['mass_kg']:.12g} ic=0
Rdamping u 0 {1/m['damping_ns_m']:.12g}
Bspring u 0 I={m['stiffness_n_m']:.12g}*v(q)
Bpiezo_force u 0 I={(m['coupling_n_v'] if spec['control']['feedback_mode']=='reciprocal' else 0):.12g}*v(p)
Bforce 0 u I={force}
Bforce_monitor force 0 V={force}
Cposition q 0 1 ic=0
Bposition 0 q I=v(u)
Cpiezo p 0 {m['piezo_capacitance_f']:.12g} ic=0
Bpiezo_current 0 p I={m['coupling_n_v']:.12g}*v(u)
Vpiezo_port p bridge_p 0
D1 bridge_p rect Dbridge
D2 0 rect Dbridge
D3 neg bridge_p Dbridge
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
Btimer 0 timer I=(v(gate)>0.5?1:-v(timer)/{spec['control']['timer_reset_tau_s']:.12g})
Bload cap neg I=(v(gate)>0.5?{oncurrent}:0)
.options reltol=1e-5 abstol=1e-11 vntol=1e-8 method=gear
.save all @bload[i] @bquiescent[i] @d1[id] @d2[id] @d3[id] @d4[id]
.control
set noaskquit
set numdgt=17
set wr_singlescale
set wr_vecnames
tran {step:.12g} {spec['simulation']['duration_s']:.12g} 0 {step:.12g} uic
let storage_v=v(cap)-v(neg)
let load_i=@bload[i]
let diode_loss=(v(p)-v(rect))*@d1[id]+(-v(rect))*@d2[id]+(v(neg)-v(p))*@d3[id]+v(neg)*@d4[id]
wrdata {out_name} v(drive) v(q) v(u) v(p) storage_v v(gate) v(timer) v(force) i(Vsense) load_i diode_loss @bquiescent[i] i(Vpiezo_port) v(neg)
quit
.endc
.end
'''

def integrate(times, values):
    return sum((times[i]-times[i-1])*(values[i]+values[i-1])/2 for i in range(1,len(times)))

def read_channels(path):
    with Path(path).open() as f:
        header=f.readline()
        rows=[[float(x) for x in line.split()] for line in f if line.strip()]
    if len(rows)<10 or any(len(r)!=len(CHANNEL_KEYS) or any(not math.isfinite(v) for v in r) for r in rows):
        raise ValueError('EVENT_SPICE_CHANNELS_INVALID:'+header[:100])
    if any(b[0]<=a[0] for a,b in zip(rows,rows[1:])):
        raise ValueError('EVENT_SPICE_TIME_NOT_STRICT')
    return [dict(zip(CHANNEL_KEYS,r)) for r in rows]
