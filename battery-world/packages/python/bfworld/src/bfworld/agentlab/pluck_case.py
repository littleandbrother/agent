"""Source-bound plucking reference apparatus. Does not alter event-design v1.

Magnetic force: SMS 2025 Eq. 2 (including beam-tip longitudinal motion).
SECE: Fig. 4 transistor topology; semiconductor parasitics remain declared
assumptions. PMIC is explicitly a behavioral energy model, not LTC silicon.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
from functools import lru_cache



def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def validate(case, capacitance_f, gap, step, motion_scale, inductor, initial_q):
    """Reject invalid values before interpolating a SPICE program."""
    def finite(value, positive=False):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
            raise ValueError('INVALID_MODEL_PARAMETER')
    for group in ('mechanics', 'motion', 'power', 'acceptance', 'workload'):
        for key, value in case[group].items():
            if isinstance(value, (int, float)):finite(value)
    for key in ('mass_kg','stiffness_n_m','damping_ns_m','piezo_capacitance_f','beam_length_m','tip_magnet_volume_m3','driver_magnet_volume_m3','remanence_t'):
        finite(case['mechanics'][key],True)
    for value in (capacitance_f,gap,step,inductor,case['motion']['duration_s'],case['workload']['beacon_interval_s']):finite(value,True)
    finite(motion_scale);finite(initial_q)
    if not 0 < case['power']['efficiency'] <= 1 or case['power']['start_v'] <= case['power']['stop_v'] or abs(initial_q) >= case['mechanics']['beam_length_m']:
        raise ValueError('INVALID_MODEL_BOUNDARY')
    for kind in ('diode_model','pnp_model','npn_model'):
        for key,value in case['interface'][kind].items():
            if not key.isalpha():raise ValueError('INVALID_SPICE_MODEL_KEY')
            finite(value,True)
    for stage in case['workload']['stages']:
        finite(stage['duration_s'],True);finite(stage['energy_j'],True)


def magnetic(q, b, m, gap):
    length = m['beam_length_m']
    if abs(q) >= length:
        raise ValueError('BEAM_GEOMETRY_OUT_OF_DOMAIN')
    d = gap + length - math.sqrt(length**2-q*q)
    dp = q / math.sqrt(length**2-q*q)
    r2 = (q-b)**2+d*d
    c = m.get('magnetic_polarity',1)*m['remanence_t']**2*m['tip_magnet_volume_m3']*m['driver_magnet_volume_m3']/(16*math.pi**2*1e-7)
    potential = c*(r2**-1.5-3*d*d*r2**-2.5)
    force = 3*c/r2**2.5*((q-b)+3*d*dp-5*d*d/r2*((q-b)+d*dp))
    return potential, force


def netlist(case, interface='seh', capacitance_f=47e-6, gap=None,
            step=20e-6, loaded=False, motion_scale=1.0, inductor=None,
            initial_deflection_m=0.0):
    if interface not in ('seh', 'sece', 'open'):
        raise ValueError('INTERFACE_UNKNOWN')
    m, d, i, p, w = [case[k] for k in ('mechanics','motion','interface','power','workload')]
    length=m['beam_length_m']; gap=d['gap_m'] if gap is None else gap
    validate(case,capacitance_f,gap,step,motion_scale,inductor or i['inductance_h'],initial_deflection_m)
    c=m.get('magnetic_polarity',1)*m['remanence_t']**2*m['tip_magnet_volume_m3']*m['driver_magnet_volume_m3']/(16*math.pi**2*1e-7)
    magnetic_expression=f'{motion_scale*3*c:.15g}/pow(v(r2),2.5)*((v(q)-v(b))+3*v(d)*v(dp)-5*v(d)*v(d)/v(r2)*((v(q)-v(b))+v(d)*v(dp)))'
    front='''D1 piezo rect DD
D2 0 rect DD
D3 neg piezo DD
D4 neg 0 DD'''
    if interface=='sece':
        front+=f'''
D5 rect envelope DD
Csense envelope neg {i['sense_capacitance_f']}
Q1 control rect envelope QP
D7 control base DD
Q2 collector base sw QN
Rbase base sw 100meg
Renvelope envelope neg 1g
D8 rect collector DD
Lextract sw lr {inductor or i['inductance_h']}
Rcoil lr neg {i['inductor_resistance_ohm']}
D6 storelow sw DD
Vmonitor neg capport 0
Resr capport store 0.1
* inverting extraction: storage-positive is bridge-negative.
Rreference storelow 0 1e9
'''
    elif interface=='seh':
        front+='\nVmonitor rect store 0\nVreturn neg storelow 0\nRreference storelow 0 1e9\n'
    else:
        front='Vmonitor unused store 0\nRopen piezo 0 1e12\nRunused unused 0 1e12\nVreturn storelow 0 0\n'
    models='\n'.join('.model '+name+' '+kind+'('+ ' '.join(f'{k}={v}' for k,v in params.items())+')' for name,kind,params in [('DD','D',i['diode_model']),('QP','PNP',i['pnp_model']),('QN','NPN',i['npn_model'])])
    stage_current=[];elapsed=0
    for stage in w['stages'][:2]:
        elapsed+=stage['duration_s']
        stage_current.append(f'v(age)<{elapsed}?{stage["energy_j"]/(stage["duration_s"]*p["output_v"])}:')
    beacon=w['stages'][2]
    phase=f'(v(age)-{elapsed}-{w["beacon_interval_s"]}*floor((v(age)-{elapsed})/{w["beacon_interval_s"]}))'
    current='('+''.join(stage_current)+f'({phase}<{beacon["duration_s"]}?{beacon["energy_j"]/(beacon["duration_s"]*p["output_v"])}:{w["idle_current_a"]}))'
    # Two separate reservoirs: input UVLO pauses the buck, not the MCU. Cout
    # continues feeding firmware until its own brownout boundary is reached.
    # The bounded average buck is a new behavioral model, not LTC3588 switching.
    draw=f'v(out)*i(Vbuck)/{p["efficiency"]}/max(v(store,storelow),0.01)' if loaded else '0'
    iq=p['quiescent_a'] if loaded else 0
    return f'''Pluck reference simulation v1 - declared models, not hardware
Vb b 0 PWL(0 {d['initial_b_m']} {d['duration_s']} {d['initial_b_m']+d['velocity_m_s']*d['duration_s']})
Bd d 0 V={gap}+{length}-sqrt(max({length*length}-v(q)*v(q),1e-12))
Bdp dp 0 V=v(q)/sqrt(max({length*length}-v(q)*v(q),1e-12))
Br2 r2 0 V=pow(v(q)-v(b),2)+v(d)*v(d)
Bforce force 0 V={magnetic_expression}
Cmass velocity 0 {m['mass_kg']} ic=0
Rdamping velocity 0 {1/m['damping_ns_m']}
Bspring velocity 0 I={m['stiffness_n_m']}*v(q)
Bcoupling velocity 0 I={m['coupling_n_v']}*v(piezo)
Bdrive 0 velocity I=v(force)
Cposition q 0 1 ic={initial_deflection_m}
Bposition 0 q I=v(velocity)
Cpiezo piezo 0 {m['piezo_capacitance_f']} ic={m['coupling_n_v']*initial_deflection_m/m['piezo_capacitance_f']}
Bpiezo 0 piezo I={m['coupling_n_v']}*v(velocity)
{front}
{models}
Cstorage store storelow {capacitance_f} ic=0
Vlogic logic 0 1
Sgate logic buckgate store storelow ENABLE
Rgate buckgate 0 1
.model ENABLE sw(ron=1e-6 roff=1e12 vt={(p['start_v']+p['stop_v'])/2} vh={(p['start_v']-p['stop_v'])/2})
Bbuck 0 buckout I=(v(buckgate)>0.5?min(0.1,max({p['output_v']}-v(out),0)*0.1):0)*{1 if loaded else 0}
Vbuck buckout out 0
Cout out 0 {p['output_capacitance_f']} ic=0
Srun logic enabled out 0 MCU
Rrun enabled 0 1
.model MCU sw(ron=1e-6 roff=1e12 vt=2.95 vh=0.25)
Bfirmware out 0 I=(v(enabled)>0.5?{current}*{p['output_v']}/max(v(out),0.1):0)
Routleak out 0 100meg
Ctimer timer 0 1 ic=0
Btimer 0 timer I=(v(enabled)>0.5?1:-v(timer)/{step/10})
Bage age 0 V=max(v(timer),0)
Bload store storelow I={draw}
Bquiet store storelow I={iq}*v(store,storelow)/(abs(v(store,storelow))+0.01)
Bshunt store storelow I=max(v(store,storelow)-20,0)/10*{1 if loaded else 0}
.options reltol=1e-4 abstol=1e-10 vntol=1e-8 method=trap itl4=200 gmin=1e-10
.save v(b) v(q) v(velocity) v(piezo) v(store) v(storelow) v(enabled) v(timer) v(force) i(Vmonitor) @bload[i] @bquiet[i] v(out) @bfirmware[i] i(Vbuck) @bshunt[i]
.control
set noaskquit
set wr_singlescale
set wr_vecnames
set numdgt=17
tran {step} {d['duration_s']} 0 {step} uic
let storage_v=v(store)-v(storelow)
wrdata channels.txt v(b) v(q) v(velocity) v(piezo) storage_v v(enabled) v(timer) v(force) i(Vmonitor) @bload[i] @bquiet[i] v(out) @bfirmware[i] i(Vbuck) @bshunt[i]
quit
.endc
.end
'''


KEYS=['time_s','driver_m','displacement_m','velocity_m_s','piezo_v','storage_v','enabled','timer_s','force_n','harvest_a','load_a','quiet_a','output_v','firmware_a','buck_a','shunt_a']


def run(case, out, **parameters):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    text=netlist(case,**parameters)
    (out/'model.cir').write_text(text)
    (out/'input.json').write_text(json.dumps({'case':case,'parameters':parameters},ensure_ascii=False,indent=2))
    try:
        result=subprocess.run(['/opt/homebrew/bin/ngspice','-b','model.cir'],cwd=out,capture_output=True,text=True,timeout=180)
    except subprocess.TimeoutExpired as error:
        (out/'solver.log').write_bytes((error.stdout or b'')+(error.stderr or b'')+b'\nSOLVER_WALL_LIMIT_180S\n')
        raise RuntimeError('SOLVER_WALL_LIMIT_180S') from error
    (out/'solver.log').write_text(result.stdout+result.stderr)
    if result.returncode or not (out/'channels.txt').exists():
        raise RuntimeError('SPICE_FAILED:'+str(out/'solver.log'))
    with (out/'channels.txt').open() as source:
        count=sum(1 for _ in source)-1
    if count<10:raise ValueError('INVALID_CHANNELS')
    m=case['mechanics'];cap=parameters.get('capacitance_f',47e-6)
    energy=dict.fromkeys(['work','damping','harvested','used','quiet','shunt','firmware','outleak'],0.0)
    def powers(r):
        return {'work':r['force_n']*r['velocity_m_s'], 'damping':m['damping_ns_m']*r['velocity_m_s']**2,
                'harvested':r['storage_v']*r['harvest_a'],'used':r['storage_v']*r['load_a'],
                'quiet':r['storage_v']*r['quiet_a'],'shunt':r['storage_v']*r['shunt_a'],
                'firmware':r['output_v']*r['firmware_a'],'outleak':r['output_v']**2/1e8}
    starts=[];tx=[];brownouts=[];active=False;next_tx=0;previous=None
    init=sum(s['duration_s'] for s in case['workload']['stages'][:2]);duration=case['workload']['stages'][2]['duration_s']
    peaks=dict(storage=0.0,deflection=0.0,piezo=0.0)
    with (out/'channels.txt').open() as source, gzip.open(out/'channels.csv.gz','wt') as compressed, (out/'trace.csv').open('w') as preview:
        next(source);writer=csv.DictWriter(compressed,fieldnames=KEYS);writer.writeheader()
        sample=csv.DictWriter(preview,fieldnames=KEYS);sample.writeheader()
        for index,line in enumerate(source):
            if not line.strip():continue
            values=list(map(float,line.split()))
            if len(values)!=len(KEYS) or not all(math.isfinite(v) for v in values):raise ValueError('INVALID_CHANNELS')
            r=dict(zip(KEYS,values));writer.writerow(r)
            if index%max(1,count//4000)==0 or index==count-1:sample.writerow(r)
            power=powers(r)
            if previous is not None:
                dt=r['time_s']-previous['time_s']
                if dt<=0:raise ValueError('CHANNEL_TIME_ORDER')
                for k in energy:energy[k]+=dt*(power[k]+last_power[k])/2
            peaks['storage']=max(peaks['storage'],r['storage_v']);peaks['deflection']=max(peaks['deflection'],abs(r['displacement_m']));peaks['piezo']=max(peaks['piezo'],abs(r['piezo_v']))
            on=r['enabled']>.5 and parameters.get('loaded',False)
            if on and not active:starts.append(r['time_s']);next_tx=init+duration
            if on and r['timer_s']>=next_tx:tx.append(r['time_s']);next_tx+=case['workload']['beacon_interval_s']
            if active and not on:brownouts.append(r['time_s'])
            active=on;previous=r;last_power=power
    (out/'channels.txt').unlink()  # all solver samples retained as gzip CSV
    last=previous;work=energy['work'];damping=energy['damping'];harvested=energy['harvested'];used=energy['used'];quiet=energy['quiet'];shunt=energy['shunt']
    stored=.5*cap*last['storage_v']**2
    final_mech=.5*m['mass_kg']*last['velocity_m_s']**2+.5*m['stiffness_n_m']*last['displacement_m']**2
    final_piezo=.5*m['piezo_capacitance_f']*last['piezo_v']**2
    residual=harvested-stored-used-quiet-shunt
    q0=parameters.get('initial_deflection_m',0)
    initial_energy=.5*(m['stiffness_n_m']+m['coupling_n_v']**2/m['piezo_capacitance_f'])*q0*q0
    loss=initial_energy+work-damping-final_mech-final_piezo-harvested
    report={'schema_version':'bf-pluck-simulation-v1','parameters':parameters,'scope':'coupled ngspice; assumed semiconductor parasitics and behavioral PMIC','samples':count,'peak_storage_v':peaks['storage'],'final_storage_v':last['storage_v'],'peak_deflection_m':peaks['deflection'],'startup_times_s':starts,'tx_complete_times_s':tx,'brownouts_s':brownouts,'energy_j':{'initial':initial_energy,'mechanical_work':work,'damping':damping,'harvested':harvested,'stored':stored,'load_input':used,'quiescent':quiet,'storage_residual':residual,'interface_loss_inferred':loss},'checks':{'complete':abs(last['time_s']-case['motion']['duration_s'])<1e-5,'storage_balance':abs(residual)<max(1e-8,abs(harvested)*.03),'passive_interface':loss>=-max(1e-8,abs(work+initial_energy)*.03),'geometry_domain':peaks['deflection']<m['beam_length_m'],'service':any(t<=case['acceptance']['event_deadline_s'] for t in tx) if parameters.get('loaded') else None},'hardware_verified':False,'input_sha256':digest(out/'input.json'),'netlist_sha256':digest(out/'model.cir')}
    firmware=energy['firmware']
    outleak=energy['outleak']
    output_store=.5*case['power']['output_capacitance_f']*last['output_v']**2
    out_residual=used*case['power']['efficiency']-firmware-outleak-output_store
    report['energy_j'].update(firmware=firmware,output_stored=output_store,output_balance_residual=out_residual)
    report['checks']['output_balance']=abs(out_residual)<max(1e-8,used*.03)
    report['energy_j']['shunt']=shunt
    report['peak_piezo_v']=peaks['piezo']
    report['checks']['deflection_limit']=report['peak_deflection_m']<=case['acceptance']['max_deflection_m']
    (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


def receive(tx_times, drop_indices=(), silence_s=.35):
    """Simulation receiver groups a burst; does not invent a persistent event ID.

    Direction remains unknown. Packet-count direction needs mounted asymmetry
    and experimentally separated class distributions, not symmetric fixtures.
    """
    if not math.isfinite(silence_s) or silence_s<=0:raise ValueError('INVALID_SILENCE')
    all_times=[float(t) for t in tx_times]
    if any(not math.isfinite(t) or t<0 for t in all_times):raise ValueError('INVALID_PACKET_TIME')
    if any(b<a for a,b in zip(all_times,all_times[1:])):raise ValueError('PACKET_ORDER')
    drops=set(drop_indices);packets=[t for i,t in enumerate(all_times) if i not in drops]
    events=[]
    for t in packets:
        if not math.isfinite(t) or t<0:raise ValueError('INVALID_PACKET_TIME')
        if events and t<events[-1]['last_packet_s']:raise ValueError('PACKET_ORDER')
        if not events or t-events[-1]['last_packet_s']>silence_s:
            events.append({'first_packet_s':t,'last_packet_s':t,'packets':1,'direction':'unknown','origin':'simulated-reception'})
        else:events[-1]['last_packet_s']=t;events[-1]['packets']+=1
    return events


@lru_cache(maxsize=512)
def _stat_digest(path, identity):
    return digest(path)


def projection(home):
    """Operator-only report; never injected into participant memory."""
    root=Path(home)/'reference-cases'/'pluck-v1'
    receipt=root/'receipt.json'
    if not receipt.exists():return {'available':False,'title':'拨动压电参考案例','status':'尚未生成验收包'}
    data=json.loads(receipt.read_text()); mismatches=[]
    # Append a new engineering package without rewriting the old scientific
    # receipt. Participant routes never return this operator reference view.
    pointer=root/'delivery/latest.json'
    if pointer.exists():
        ref=json.loads(pointer.read_text());path=(root/ref['path']).resolve()
        if not path.is_relative_to((root/'delivery').resolve()) or not path.is_file() or digest(path)!=ref['sha256']:
            mismatches.append('delivery/latest.json')
        else:
            delivery=json.loads(path.read_text());data['delivery']=delivery
            data['artifacts']+=delivery.get('artifacts',[])
    for item in data.get('artifacts',[]):
        path=(root/item['path']).resolve()
        identity=path.stat() if path.is_relative_to(root.resolve()) and path.is_file() else None
        if identity is None or _stat_digest(str(path),(identity.st_ino,identity.st_size,identity.st_mtime_ns,identity.st_ctime_ns))!=item['sha256']:
            mismatches.append(item['path'])
    return {'available':True,**data,'artifact_integrity':not mismatches,'mismatches':mismatches}
