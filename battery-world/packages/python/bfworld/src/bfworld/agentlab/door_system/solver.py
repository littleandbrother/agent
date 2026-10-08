"""D4 full-cycle native reciprocal electromechanics; v1 solver is unchanged.

Copied versioned implementation retains the same native RAW, SIL, PMIC and
convergence checks; the initial state and prescribed actuator path are explicit.
"""
import ctypes
import importlib.util
import json
import re
import shutil
from pathlib import Path
import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import brentq
from ..simulation_chain.contracts import ChainError,file_hash,write_json
from ..simulation_chain.native import command,WINE,PMIC
from .model import initial_equilibrium, drive_ledger
from .contracts import verify_design

def read_raw(path,duration):
    data=Path(path).read_bytes();marker='Binary:\n'.encode('utf-16-le')
    try:offset=data.index(marker)+len(marker);header=data[:offset].decode('utf-16-le')
    except ValueError as exc:raise ChainError('tool_fail','Unrecognized native waveform') from exc
    flags=re.search(r'Flags: ([^\n]+)',header)[1]
    if 'real' not in flags or any(x in flags for x in ('FastAccess','double','complex')):
        raise ChainError('tool_fail','Unsupported RAW flags '+flags)
    n=int(re.search(r'No. Variables: (\d+)',header)[1]);count=int(re.search(r'No. Points:\s+(\d+)',header)[1])
    names=[r.split()[1].lower() for r in header.split('Variables:\n')[1].split('Binary:')[0].splitlines() if r.strip()]
    values=np.frombuffer(data,offset=offset,dtype=np.dtype([('t','<f8'),('v','<f4',(n-1,))]))
    t=np.abs(values['t'])
    if len(values)!=count or not np.isfinite(values['v']).all() or (np.diff(t)<0).any() or abs(t[-1]-duration)>1e-7:
        raise ChainError('numerical_fail','Incomplete/nonfinite/nonmonotonic native transient')
    # Integrations require strictly increasing coordinates.
    unique=np.r_[True,np.diff(t)>0]
    result={name:values['v'][unique,i].astype(float) for i,name in enumerate(names[1:])}
    if 'v(pz1)' in result and 'v(pz2)' in result:result['v(pz1,pz2)']=result['v(pz1)']-result['v(pz2)']
    return t[unique],result

def table_expression(angles,qs,values):
    def fmt(v):return f'{float(v):.10g}'
    # Nodes outside the certified box are detected in raw output and rejected.
    rows=[f'{fmt(a)},table(q,'+','.join(f'{fmt(q)},{fmt(v)}' for q,v in zip(qs,row))+')' for a,row in zip(angles,values)]
    return '.func magnetic(a,q) {table(a,'+','.join(rows)+')}\n'

def load_pwl(path,t,current):
    indices=np.r_[0,np.flatnonzero(np.diff(current)!=0)+1,len(t)-1]
    rows=[]
    for i in sorted(set(indices)):
        if i>0 and current[i]!=current[i-1]:rows.append((max(0,t[i]-1e-9),current[i-1]))
        rows.append((t[i],current[i]))
    np.savetxt(path,rows,fmt='%.12g')

def deck(directory,spec,rom,force_path,t,current,resistor=None):
    table=np.load(force_path);angles,qs,values=[table[k] for k in ('angles','qs','values')]
    interp=RegularGridInterpolator((angles,qs),values,bounds_error=True)
    k,m,theta,cp=[rom[n] for n in ('k','mass','theta','cp')]
    design=verify_design(spec['system_design'])
    q0=initial_equilibrium(interp,rom,np.deg2rad(design['frozen']['task']['angle_deg']))
    mech=spec['mechanical'];circuit=spec['circuit'];damping=2*mech['damping_ratio']*np.sqrt(k*m)
    task=design['frozen']['task'];c,h,o=task['closing_s'],task['holding_s'],task['opening_s']
    angle=np.deg2rad(task['angle_deg'])
    angle_source=f'Vangle angle 0 PWL(0 {angle} {c} 0 {c+h} 0 {c+h+o} {angle} {t[-1]} {angle})'
    load_pwl(directory/'load.pwl',t,current);shutil.copy2(PMIC,directory/'LTC3588-1.sub')
    power=f'''XU1 port pz2 cap vin sw out vin2 vin2 0 pgood 0 LTC3588-1
Cstorage vin 0 {circuit['cin_uF']*1e-6} IC={circuit['initial_vin_V']}
Ccap vin cap 1u
Cvin2 vin2 0 4.7u
L1 sw out 10u Rser=0.4
Cout out 0 {circuit['cout_uF']*1e-6} Rser=0.02
Vload schedule 0 PWL FILE="load.pwl"
* Draw remains present before PGOOD. Taper below reset voltage avoids an ideal negative supply.
Bload out 0 I=V(schedule)*limit(V(out)/1.8,0,1)
Idiagnostic 0 vin {circuit['diagnostic_input_A']}
.lib LTC3588-1.sub
'''
    if resistor is not None:
        power=f'Rtest port pz2 {resistor}\nVout out 0 0\nVvin vin 0 0\nVgood pgood 0 0\nBload out 0 I=0\n'
    content=f'''* Reciprocal single-mode ROM; q [m], u [m/s]; Cp counted exactly once.
{table_expression(angles,qs,values)}
{angle_source}
Bforce force 0 V=magnetic(V(angle),V(q))
Cmass u 0 {m} IC=0
Bmechanics 0 u I=V(force)-{k}*V(q)-{damping}*V(u)-{theta}*V(pz1,pz2)
Cposition q 0 1 IC={q0}
Bposition 0 q I=V(u)
Rposition q 0 1T
Bpiezo pz2 pz1 I={theta}*V(u)
Cpiezo pz1 pz2 {cp} IC=0
Rreference pz2 0 1G
Vsense pz1 port 0
{power}
.tran 0 {t[-1]} 0 {spec['solver']['max_step_s']} uic
.options threads=2 plotwinsize=0 reltol={spec['solver']['reltol']} abstol=1e-12 vntol=1e-9
.save V(q) V(u) V(force) V(angle) V(pz1,pz2) V(vin) V(out) V(pgood) I(Vsense) I(Bload)
.meas TRAN storage_peak MAX V(vin)
.meas TRAN output_peak MAX V(out)
.end
'''
    (directory/'system.cir').write_text(content)
    return q0,damping

def native_solve(directory,duration):
    command([WINE,'--enable-alt-loader=macdrv','--bottle','default','--no-gui','--workdir',
             'C:/Program Files/ADI/LTspice','LTspice.exe','-b',directory/'system.cir'],directory,'launcher',240)
    log=(directory/'system.log').read_text(errors='replace') if (directory/'system.log').exists() else ''
    if 'Total elapsed time:' not in log or 'Fatal' in log:raise ChainError('numerical_fail','LTspice transient incomplete')
    t,v=read_raw(directory/'system.raw',duration)
    for key,var in [('storage_peak','v(vin)'),('output_peak','v(out)')]:
        match=re.search(r'^'+key+r':.*?=\s*([-+\d.eE]+)',log,re.M)
        if not match or not np.isclose(float(match[1]),max(v[var]),rtol=5e-4,atol=1e-7):
            raise ChainError('numerical_fail','Native .meas vs RAW mismatch: '+key)
    return t,v

def execute_program(firmware,t,supply,pgood):
    library=ctypes.CDLL(str(firmware/'program.dylib'))
    library.bf_step.argtypes=[ctypes.c_double]*3;library.bf_step.restype=ctypes.c_int
    library.bf_current_mA.restype=ctypes.c_double;library.bf_state.restype=ctypes.c_int
    library.bf_reset();payload=(ctypes.c_uint8*12)();library.bf_payload(payload)
    current=np.zeros(len(t));states=np.zeros(len(t),int);events=[]
    for i in range(len(t)):
        complete=library.bf_step((t[i]-t[i-1])*1000 if i else 0,float(supply[i]),float(pgood[i]))
        current[i]=library.bf_current_mA()/1000;states[i]=library.bf_state()
        if complete:events.append({'time_s':float(t[i]),'payload_hex':bytes(payload).hex(),'origin':'shared-C-software-in-loop','capture_id':f'sil-tx-{len(events)}'})
    return current,states,events

def conservative_sample(t,v,grid):
    """Include a sub-grid brownout/PGOOD loss, rather than interpolate over it."""
    out=np.interp(grid,t,v)
    bins=np.searchsorted(grid,t,side='left');bins=np.minimum(bins,len(grid)-1)
    np.minimum.at(out,bins,v)
    return out

def receive(firmware,events,link):
    spec=importlib.util.spec_from_file_location('closed_receiver',firmware/'receiver.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    rng=np.random.default_rng(int(link['seed']));records=[];dropped=[]
    for e in events:
        allowed=e['time_s']%.1<.1*link['scan_duty'] and rng.random()>=link['loss_probability']
        (records if allowed else dropped).append(e)
    return {'transmitted':events,'delivered':records,'dropped':dropped,'events':mod.group(records),
            'scope':'virtual link + existing BFD2 decoder, no RF propagation/physical receive evidence'}

def solve(directory,spec,rom,force_path,firmware,resistor=None):
    design=verify_design(spec['system_design'])
    task=design['frozen']['task']
    duration=sum(task[k] for k in ('closing_s','holding_s','opening_s','settling_s'))
    grid=np.linspace(0,duration,round(duration/spec['solver']['firmware_step_s'])+1)
    current=np.full(len(grid),spec['firmware']['reset_uA']*1e-6)
    previous_supply=None;iterations=[];converged=False
    for n in range(int(spec['solver']['max_coupling_iterations'])):
        d=directory/f'iteration-{n:02}';d.mkdir()
        q0,damping=deck(d,spec,rom,force_path,grid,current,resistor)
        t,v=native_solve(d,duration)
        # LTspice UIC writes an all-zero display row at t=0 before capacitor ICs.
        # Restore ONLY explicitly declared states; the untouched native RAW is retained.
        if t[0]==0 and abs(v['v(q)'][0]-q0)>1e-9 and t[1]<1e-7 and abs(v['v(q)'][1]-q0)<1e-7:
            v['v(q)'][0]=q0;v['v(force)'][0]=rom['k']*q0
            v['v(vin)'][0]=spec['circuit']['initial_vin_V']
        if np.max(abs(v['v(q)']))>.008+1e-8:
            raise ChainError('out_of_domain','Beam deflection exceeded certified +/-8mm; no extrapolated verdict')
        supply=conservative_sample(t,v['v(out)'],grid);good=conservative_sample(t,v['v(pgood)'],grid)
        nxt,states,events=execute_program(firmware,grid,supply,good)
        difference=float(np.max(abs(nxt-current)));voltage_delta=float(np.max(abs(supply-previous_supply))) if previous_supply is not None else None
        iterations.append({'iteration':n,'max_current_difference_A':difference,'max_supply_difference_V':voltage_delta,'packets':len(events)})
        # Exact state/load fixed point with voltage check; never accept an iteration cap as convergence.
        if resistor is not None or (difference<1e-12 and (previous_supply is None or voltage_delta<.001)):
            converged=True;break
        current=nxt;previous_supply=supply
    write_json(directory/'coupling-iterations.json',iterations)
    if not converged:raise ChainError('numerical_fail','Program/power waveform relaxation did not converge')
    np.savetxt(directory/'program.csv',np.column_stack([grid,supply,good,states,nxt]),delimiter=',',header='time_s,supply_V,pgood_V,state,current_A',comments='')
    receiver=receive(firmware,events,spec['link']);write_json(directory/'receiver.json',receiver)
    q,u,pz,F=[v[k] for k in ('v(q)','v(u)','v(pz1,pz2)','v(force)')]
    stored=.5*rom['mass']*u*u+.5*rom['k']*q*q+.5*rom['cp']*pz*pz
    port=cumulative_trapezoid(pz*v['i(vsense)'],t,initial=0)
    loss=cumulative_trapezoid(damping*u*u,t,initial=0);work=cumulative_trapezoid(F*u,t,initial=0)
    residual=stored-stored[0]+port+loss-work
    scale=max(np.max(abs(work)),stored[0],np.max(abs(port)),1e-12)
    ledger={'initial_mechanical_piezo_J':float(stored[0]),'final_mechanical_piezo_J':float(stored[-1]),
      'external_force_work_J':float(work[-1]),'mechanical_loss_J':float(loss[-1]),'pmic_port_energy_J':float(port[-1]),
      'mechanical_piezo_residual_J':float(max(abs(residual))),'relative_residual':float(max(abs(residual))/scale),
      'pmic_initial_storage_J':.5*spec['circuit']['cin_uF']*1e-6*spec['circuit']['initial_vin_V']**2,
      'diagnostic_source_energy_J':float(np.trapezoid(v['v(vin)']*spec['circuit']['diagnostic_input_A'],t)),
      'load_energy_J':float(np.trapezoid(v['v(out)']*v['i(bload)'],t)),
      'cp_count':1,'pmic_internal_loss':'not independently observable from encrypted macro-model; full PMIC energy residual not certified'}
    ledger['initial_state_handling']='Explicit capacitor/ROM ICs; LTspice UIC display-only zero row corrected in derived arrays, original RAW unchanged.'
    columns=['v(q)','v(u)','v(pz1,pz2)','v(vin)','v(out)','v(pgood)']
    sample=np.linspace(0,duration,4001)
    np.savetxt(directory/'waveform.csv',np.column_stack([sample]+[np.interp(sample,t,v[k]) for k in columns]),delimiter=',',
        header='time_s,tip_m,velocity_m_s,piezo_V,storage_V,supply_V,pgood_V',comments='')
    write_json(directory/'energy.json',ledger)
    # Retain final native deck/raw/log at the stage root for portable evidence.
    for name in ['system.cir','system.raw','system.log','load.pwl']:shutil.copy2(d/name,directory/name)
    summary={'coupling_converged':True,'iterations':iterations,'energy_ledger':ledger,
       'peak_tip_mm':float(max(abs(q))*1000),'peak_piezo_V':float(max(abs(pz))),
       'peak_storage_V':float(max(v['v(vin)'])),'peak_supply_V':float(max(v['v(out)'])),
       'tx_completed':len(events),'received_events':len(receiver['events']),
       'cold_start_reached':bool(max(v['v(out)'])>=3.2),
       'program_states_reached':sorted(set(states.tolist())), 'q0_m':q0,
       'numerical_energy_passed':ledger['relative_residual']<.01,
       'diagnostic_only':bool(spec['circuit']['initial_vin_V'] or spec['circuit']['diagnostic_input_A'])}
    summary['drive_ledger']=drive_ledger(directory,design,rom,t,q,u,pz,port,loss)
    summary['design_id']=design['design_id']
    summary['task_phase']='full close-hold-open motion notification; not a certified open/closed state detector'
    write_json(directory/'solve.json',summary);return summary
