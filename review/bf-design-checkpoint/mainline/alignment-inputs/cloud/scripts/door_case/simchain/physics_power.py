"""SIMULATION-only reciprocal ROM + own behavioral power model, not vendor SPICE.

All electrical states start at zero. The same trajectory includes electromechanical
back-action, bridge, PMIC input draw, output storage, and firmware load. Firmware
is sampled only at accepted macro ticks; Radau's internal trial steps have no
firmware side effects. This is a versioned approximation, not calibrated hardware.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import time

import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT/'configs/reference_cases/door-magnetic-v1/design.json'
VERSION = 'reciprocal-behavioral-power-v1.2-solver-provider-provenance'
SOURCE = 'https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf'
DEFAULT_POWER = {
    'input_capacitance_uF':47., 'output_capacitance_uF':100., 'output_voltage_V':3.3,
    'pmic':{'uvlo_rise_V':5.05,'uvlo_fall_V':3.67,'efficiency':.8,
            'input_quiescent_A':.95e-6,'input_leakage_ohm':1e9,
            'output_leakage_ohm':1e7,'startup_rail_energy_J':.5*5.7e-6*4.8**2,
            'startup_current_A':.001,'startup_taper_s':.0001,'aux_off_decay_s':.1,'max_output_current_A':.01,
            'regulator_resistance_ohm':2.,'pgood_rise_fraction':.95,
            'pgood_fall_fraction':.90,'bridge_drop_V':.2,'bridge_resistance_ohm':100.}}
ASSUMPTIONS = {
    'identity':VERSION,'vendor_model_executed':False,'COMSOL_executed':False,
    'datasheet':SOURCE,
    'datasheet_derived':{'uvlo_3v3_typical_rise_V':5.05,'uvlo_3v3_typical_fall_V':3.67,
                        'uvlo_rise_min_max_V':[4.73,5.37]},
    'engineering_assumptions': ['Efficiency 0.8 constant, not measured',
      'Bridge 0.2 V per diode + 100 ohm series model, not vendor rectifier',
      'Explicit startup rail energy store 0.5*5.7uF*4.8V^2; off-state exponential energy decay tau0.1s assumed, loss ledger included',
      'Startup current 1 mA, fixed 0.1 ms rail-charge taper; output cap 10 mA, regulator 2 ohm droop',
      'Quiescent 0.95 uA constant; leakage input 1Gohm/output 10Mohm',
      'PGOOD fractions 0.95/0.90 are behavioral assumptions',
      'No switching ripple, overshoot, thermal, EMI, inductor saturation or tolerance model',
      'Inherited beam modal constants; damping 0.02 assumed; ideal Br=1.25T mur=1 magnets',
      'Firmware/load, UVLO, PGOOD and auxiliary-ready latch update at accepted macro/event ticks; halve tick for convergence',
      'Numerical guard:10000 RHS calls per interval,5million per solve,300s wall limit per solve; excess is numerical_fail'],
    'interpolation':'181 angle by49 displacement samples; displacement support [-8,8]mm; candidate-specific rebuilt table',
    'scope':'Declared F1 computational model only; no physical/product acceptance'}

class OutOfDomain(ValueError): pass


def _sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def _write(p,x):
    with Path(p).open('x') as f: json.dump(x,f,indent=2,sort_keys=True,allow_nan=False)
def _num(x,name,low=None,high=None):
    if type(x) not in (int,float) or not math.isfinite(x): raise ValueError('INVALID_NUMBER:'+name)
    if low is not None and x<low or high is not None and x>high: raise OutOfDomain('OUTSIDE_MODEL_RANGE:'+name)
    return float(x)


def parameters():
    # Blocked piezo C is used once; reciprocal theta couples the mechanical and
    # electrical equations. Never add another piezo C or harvested-energy source.
    k=.3/.0034403062781818306; theta=k*2.4862056721220446e-6
    return {'k':k,'mass':k/(2*np.pi*15.9152427488183)**2,
            'theta':theta,'cp':1.7773565412243214e-8-theta**2/k,'zeta':.02}


def normalize(design):
    baseline=json.loads(REFERENCE.read_text()); mech=deepcopy(design.get('mechanics',{}))
    unknown=set(mech)-{'reference_design','installation_gap_mm','opening_s','open_angle_deg','mode','controlled_input'}
    if unknown:raise OutOfDomain('UNSUPPORTED_MECHANICS_FIELD:'+','.join(sorted(unknown)))
    ref=deepcopy(mech.get('reference_design',baseline))
    for key in ('beam','pzt','magnets'):
        observed=deepcopy(ref[key]); expected=deepcopy(baseline[key])
        if key=='magnets': observed.pop('nominal_center_separation_x_mm',None); expected.pop('nominal_center_separation_x_mm',None)
        if observed!=expected: raise OutOfDomain('ROM_OR_FORCE_UPGRADE_REQUIRED:'+key)
    # Reference is a pinned world definition, not an alternate door/board backdoor.
    refcheck=deepcopy(ref);basecheck=deepcopy(baseline)
    refcheck.pop('revision',None);basecheck.pop('revision',None)
    refcheck['magnets']['nominal_center_separation_x_mm']=basecheck['magnets']['nominal_center_separation_x_mm']
    refcheck['door']['product_origin_world_mm'][0]=basecheck['door']['product_origin_world_mm'][0]
    if refcheck!=basecheck:raise OutOfDomain('UNSUPPORTED_REFERENCE_WORLD_MUTATION')
    reference_gap=ref['magnets']['nominal_center_separation_x_mm']
    expected_origin=baseline['door']['product_origin_world_mm'][0]+reference_gap-baseline['magnets']['nominal_center_separation_x_mm']
    if ref['door']['product_origin_world_mm'][0]!=expected_origin:raise OutOfDomain('REFERENCE_PLACEMENT_GAP_MISMATCH')
    mode=mech.get('mode','door')
    if mode not in ('door','controlled_input'): raise ValueError('UNKNOWN_EXCITATION_MODE')
    gap=_num(mech.get('installation_gap_mm',ref['magnets']['nominal_center_separation_x_mm']),'gap',40,60)
    opening=_num(mech.get('opening_s',ref['door']['opening_s']),'opening',.05,20)
    angle=_num(mech.get('open_angle_deg',ref['door']['open_angle_deg']),'angle',0,65)
    ref['door']['product_origin_world_mm'][0]+=gap-ref['magnets']['nominal_center_separation_x_mm']
    ref['magnets']['nominal_center_separation_x_mm']=gap
    ref['door']['opening_s']=opening; ref['door']['open_angle_deg']=angle
    power=deepcopy(DEFAULT_POWER)
    for key,value in design.get('power',{}).items():
        if key=='pmic':power['pmic'].update(value)
        elif key in power:power[key]=value
        else:raise ValueError('UNKNOWN_POWER_FIELD:'+key)
    for k in ('input_capacitance_uF','output_capacitance_uF'): _num(power[k],k,.1,1000)
    if power['output_voltage_V']!=3.3:raise OutOfDomain('ONLY_3V3_THRESHOLD_MODEL_SUPPORTED')
    pm=power['pmic']
    if set(pm)!=set(DEFAULT_POWER['pmic']):raise ValueError('UNKNOWN_PMIC_FIELD')
    for k,v in pm.items(): _num(v,k,0)
    if not 0<pm['efficiency']<=1:raise ValueError('EFFICIENCY_RANGE')
    if not 0<pm['uvlo_fall_V']<pm['uvlo_rise_V']<19:raise ValueError('UVLO_RANGE')
    for k in ('input_leakage_ohm','output_leakage_ohm','regulator_resistance_ohm','bridge_resistance_ohm','startup_taper_s','aux_off_decay_s'):
        if pm[k]<=0:raise ValueError('POSITIVE_RESISTANCE_REQUIRED')
    if not 0<pm['pgood_fall_fraction']<pm['pgood_rise_fraction']<=1:raise ValueError('PGOOD_RANGE')
    control=mech.get('controlled_input',{})
    if mode=='controlled_input':
        _num(control.get('voltage_V',6),'controlled_voltage',0,12)
        _num(control.get('series_resistance_ohm',20),'controlled_resistance',1,1e8)
        _num(control.get('duration_s',.3),'controlled_duration',0,20)
    return ref,mode,power,control


def build_mechanical(design):
    ref,mode,power,control=normalize(design);p=parameters()
    if mode=='controlled_input':
        return (lambda t,q:0.),0.,{'mode':mode,'force_grid':None,'parameters':p,
            'claim':'External electrical input diagnostic; not door harvesting or D2 mission'}
    module_path=ROOT/'scripts/door_case/coupled.py'
    spec=importlib.util.spec_from_file_location('_simchain_force',module_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    # Force support is rebuilt from candidate geometry, never reused under an old ID.
    angles=np.linspace(0,np.deg2rad(max(ref['door']['open_angle_deg'],1e-6)),181)
    qs=np.linspace(-.008,.008,49);grid=np.empty((len(angles),len(qs)))
    origin=ref['door']['product_origin_world_mm']; driver=ref['door']['driver_closed_world_mm'];tip=ref['magnets']['tip_center_mm']
    if origin[2]+tip[1]!=driver[2]:raise OutOfDomain('OUT_OF_PLANE_MAGNET_UNSUPPORTED')
    for i,a in enumerate(angles):
        dx=(origin[0]-tip[0]-(driver[0]*np.cos(a)-driver[1]*np.sin(a)))/1000
        dz=(driver[0]*np.sin(a)+driver[1]*np.cos(a)-origin[1]-tip[2])/1000
        for j,q in enumerate(qs):grid[i,j]=module.force(dx,dz-q,a)[2]
    table=RegularGridInterpolator((angles,qs),grid,bounds_error=True)
    def force(t,q):
        if abs(q)>.008:raise OutOfDomain('ORIGINAL_8MM_ROM_LIMIT_EXCEEDED')
        a=min(max(t,0)/ref['door']['opening_s'],1)*np.deg2rad(ref['door']['open_angle_deg'])
        return float(table([[a,q]])[0])
    try:q0=brentq(lambda q:p['k']*q-force(0,q),-.008,.008)
    except ValueError as exc:raise OutOfDomain('NO_EQUILIBRIUM_IN_ROM_DOMAIN') from exc
    return force,q0,{'mode':mode,'force_grid':grid,'angles_rad':angles.tolist(),'deflections_m':qs.tolist(),'parameters':p,'initial_equilibrium_m':q0}


class ConstantLoad:
    def __init__(self,current_A=0): self.current_A=current_A
    def load_current_a(self,vdd,pgood):return self.current_A if vdd>0 else 0.
    def advance(self,t_s,dt_s,vdd_v,pgood,**kwargs):return {'state':'constant-load','events':[]}


def simulate(design,firmware=None,*,step_s=None,mechanical=None):
    ref,mode,power,control=normalize(design)
    mission=design.get('mission',{});dt=_num(step_s if step_s is not None else mission.get('step_s',.0005),'step',1e-6,.002)
    duration=_num(mission.get('duration_s',ref['door']['opening_s']+2 if mode=='door' else .3),'duration',dt,20)
    f,q0,mechanical=mechanical or build_mechanical(design);p=parameters();pm=power['pmic']
    firmware=firmware or ConstantLoad();ci=power['input_capacitance_uF']*1e-6;co=power['output_capacitance_uF']*1e-6;target=power['output_voltage_V']
    # q, qdot, Vpiezo, Vin, Vout, Eaux; integrated work/loss registers.
    y=np.zeros(16);y[0]=q0;initial=.5*p['k']*q0*q0
    enabled=False;pgood=False;events=[];rows=[];residuals=[];wall=time.monotonic()
    damping=2*p['zeta']*math.sqrt(p['k']*p['mass']);nsteps=math.ceil(duration/dt)
    peak_q=abs(q0);peak_vin=0.;peak_vout=0.;max_residual=0.;total_rhs=0;max_interval_rhs=0
    t=0.;index=0
    while t<duration-1e-12:
        h=min(dt,duration-t)
        if hasattr(firmware,'next_transition_s'):
            remaining=firmware.next_transition_s()
            if remaining is not None:h=min(h,max(float(remaining),1e-9))
        if mode=='controlled_input' and t<control.get('duration_s',duration)<t+h:
            h=control.get('duration_s',duration)-t
        index+=1
        if index>2000000:raise RuntimeError('INTEGRATION_TICK_BUDGET_EXCEEDED')
        if enabled and y[3]<=pm['uvlo_fall_V']:enabled=False
        elif not enabled and y[3]>=pm['uvlo_rise_V']:enabled=True
        if pgood and y[4]<=target*pm['pgood_fall_fraction']:pgood=False
        elif not pgood and enabled and y[4]>=target*pm['pgood_rise_fraction']:pgood=True
        # Discrete converter-ready latch is constant during Radau trial/Newton evaluations.
        aux_ready = y[5]>=pm['startup_rail_energy_J']*(1-1e-6)
        start_pgood=pgood
        requested=float(firmware.load_current_a(float(y[4]),pgood))
        if not math.isfinite(requested) or requested<0:raise ValueError('INVALID_FIRMWARE_CURRENT')
        # Side-effect-free RHS; power loss and storage are integrated alongside states.
        interval_rhs=0
        def rhs(tt,z):
            nonlocal interval_rhs,total_rhs
            interval_rhs+=1;total_rhs+=1
            if interval_rhs>10000 or total_rhs>5000000:raise RuntimeError('NUMERICAL_RHS_BUDGET_EXCEEDED')
            if total_rhs%128==0 and time.monotonic()-wall>300:raise RuntimeError('NUMERICAL_WALL_DEADLINE_EXCEEDED')
            q,vel,vp,vin,vout,aux=z[:6]; vinp=max(vin,0.);vop=max(vout,0.)
            ib=max(abs(vp)-vinp-2*pm['bridge_drop_V'],0)/pm['bridge_resistance_ohm']
            src=0.
            if mode=='controlled_input' and tt<=control.get('duration_s',duration)+1e-12:
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
        sol=solve_ivp(rhs,(t,t+h),y,method='Radau',rtol=2e-8,atol=1e-13,max_step=h)
        max_interval_rhs=max(max_interval_rhs,interval_rhs)
        if not sol.success:raise RuntimeError('RADAU_FAILURE:'+sol.message)
        y=sol.y[:,-1]
        if min(y[3:6]) < -1e-8:raise RuntimeError('NEGATIVE_ENERGY_STATE')
        peak_q=max(peak_q,float(np.max(np.abs(sol.y[0]))));peak_vin=max(peak_vin,float(np.max(sol.y[3])));peak_vout=max(peak_vout,float(np.max(sol.y[4])))
        if peak_q>.008:raise OutOfDomain('ORIGINAL_8MM_ROM_LIMIT_EXCEEDED')
        if peak_vin>=19:raise OutOfDomain('SHUNT_REGION_NOT_MODELED')
        if pgood and y[4]<=target*pm['pgood_fall_fraction']:pgood=False
        elif not pgood and enabled and y[4]>=target*pm['pgood_rise_fraction']:pgood=True
        step_result=firmware.advance(t,h,float(y[4]),bool(start_pgood and pgood),min_vdd_v=float(np.min(sol.y[4])))
        for e in step_result.get('events',step_result.get('packet_events',[])):events.append(e)
        stored=.5*p['mass']*y[1]**2+.5*p['k']*y[0]**2+.5*p['cp']*y[2]**2+.5*ci*y[3]**2+.5*co*y[4]**2+y[5]
        residual=stored-initial+sum(y[8:13])+y[15]-y[6]-y[7]
        max_residual=max(max_residual,abs(residual))
        rows.append([t+h,*map(float,y[:6]),bool(enabled),bool(pgood),requested,step_result.get('state','unknown'),float(residual)])
        t+=h
    denom=float(max(initial,y[13]+y[14]+y[7],1e-12))
    return {'schema_version':'simchain-physics-result-v1','model':deepcopy(ASSUMPTIONS),'mode':mode,
      'dt_s':dt,'duration_s':duration,'wall_s':time.monotonic()-wall,'trace':rows,'events':events,
      'trace_columns':['time_s','q_m','velocity_m_s','piezo_V','vin_V','vout_V','aux_rail_J','pmic_enabled','pgood','load_A','firmware_state','residual_J'],
      'metrics':{'rhs_evaluations':total_rhs,'max_interval_rhs_evaluations':max_interval_rhs,'peak_tip_mm':peak_q*1000,'peak_vin_V':peak_vin,'peak_vout_V':peak_vout,'final_vout_V':float(y[4]),
         'relative_energy_residual':float(max_residual/denom),'max_energy_residual_J':float(max_residual),'numerical_pass':bool(max_residual/denom<.01),
         'pmic_started':any(r[7] for r in rows),'pgood_observed':any(r[8] for r in rows)},
      'energy_ledger_J':{'initial_mechanical':initial,'mechanical_work':float(y[6]),'external_electrical_work':float(y[7]),
         'mechanical_positive_work':float(y[13]),'mechanical_negative_work_magnitude':float(y[14]),
         'controlled_source_resistor_loss':float(y[15]),'mechanical_damping':float(y[8]),'bridge_loss':float(y[9]),'conversion_loss':float(y[10]),
         'quiescent_and_leakage':float(y[11]),'firmware_load':float(y[12]),'final_stored':float(stored),
         'final_piezo':float(.5*p['cp']*y[2]**2),'final_input_capacitor':float(.5*ci*y[3]**2),
         'final_output_capacitor':float(.5*co*y[4]**2),'final_aux_rail':float(y[5]),'balance_residual':float(residual)},
      'firmware_summary':firmware.summary() if hasattr(firmware,'summary') else {},
      'parameters':p,'power':power,'model_binding':model_versions(),'hardware_verified':False,'product_accepted':False}


def solver_blas_providers():
    """Bind this installed NumPy/SciPy wheel's BLAS, not every loaded plugin.

    Supported provider locations are the package-owned .libs directories in
    official binary-wheel layouts. An unresolved provider is not silently
    treated as known. Other process pools remain available in cost/audit JSON.
    """
    from threadpoolctl import threadpool_info
    roots={}
    for owner,module in (('numpy',np),('scipy',__import__('scipy'))):
        package=Path(module.__file__).resolve().parent
        roots[owner]=((package.parent/(owner+'.libs')).resolve(),(package/'.libs').resolve())
    found=[];owners=set()
    for item in threadpool_info():
        if item.get('user_api')!='blas':continue
        provider=Path(item['filepath']).resolve()
        ownership=sorted(owner for owner,dirs in roots.items() if any(provider.is_relative_to(root) for root in dirs))
        if not ownership:continue
        record={k:v for k,v in item.items() if k!='filepath'}
        record.update(library_name=provider.name,library_sha256=_sha(provider),solver_packages=ownership)
        found.append(record);owners.update(ownership)
    if owners!={'numpy','scipy'}:raise RuntimeError('UNRESOLVED_NUMPY_SCIPY_BLAS_PROVIDER')
    return sorted(found,key=lambda item:(item['library_name'],item['library_sha256']))


def model_versions():
    thread_limits={key:os.environ.get(key) for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS')}
    semantics=deepcopy(ASSUMPTIONS);semantics['thread_limit_environment']=thread_limits
    blas=solver_blas_providers()
    semantics['provider_scope']='BLAS providers inside installed NumPy/SciPy package-owned wheel library directories only; other process pools audited separately'
    semantics['numerical_runtime']={'numpy':np.__version__,'scipy':__import__('scipy').__version__,'blas':blas}
    base={'version':VERSION,'semantics':semantics,'source_hashes':{str(Path(__file__).relative_to(ROOT)):_sha(__file__),'scripts/door_case/coupled.py':_sha(ROOT/'scripts/door_case/coupled.py')},
      'dependency_hashes':{'blas_runtime':hashlib.sha256(json.dumps(blas,sort_keys=True).encode()).hexdigest(),'thread_limit_environment':hashlib.sha256(json.dumps(thread_limits,sort_keys=True).encode()).hexdigest(),'numpy_version':hashlib.sha256(np.__version__.encode()).hexdigest(),'scipy_version':hashlib.sha256(__import__('scipy').__version__.encode()).hexdigest()},
      'applicability':{'gap_mm':[40,60],'max_deflection_mm':8,'beam':'inherited only','magnetic_force':'uniform mur1 cuboids','physical_calibration':False}}
    return {'mechanical':deepcopy(base),'coupled_power':deepcopy(base)}


def _failure(exc):
    out=isinstance(exc,OutOfDomain)
    return {'run_status':'out_of_domain' if out else 'input_error' if isinstance(exc,(ValueError,KeyError,TypeError)) else 'numerical_fail',
      'design_status':'insufficient_evidence','metrics':{},'applicability':{'status':'out_of_domain' if out else 'unknown','limits':[],'checks':{}},'reasons':[str(exc)],'artifacts':[]}


def mechanical_stage(context):
    try:
        f,q,model=build_mechanical(context['design']);out=Path(context['output_dir']);out.mkdir(parents=True,exist_ok=True)
        grid=model.pop('force_grid')
        _write(out/'mechanical.json',model)
        artifacts=[{'kind':'mechanical-model','path':'mechanical.json'}]
        if grid is not None:np.save(out/'force-grid.npy',grid);artifacts.append({'kind':'force-grid','path':'force-grid.npy'})
        return {'run_status':'completed','design_status':'satisfied','metrics':{'initial_equilibrium_m':q,'acceptance_scope':'in-domain numerical mechanical model only','hardware_verified':False},
          'applicability':{'status':'in_domain','limits':[model_versions()['mechanical']['applicability']],'checks':{'original_8mm':abs(q)<=.008}},'reasons':['Inherited uncalibrated ROM; no stress/COMSOL qualification'],'artifacts':artifacts}
    except Exception as exc:return _failure(exc)


def mechanical_from_upstream(context):
    upstream=context.get('inputs',{}).get('mechanical')
    if not upstream:raise ValueError('MECHANICAL_UPSTREAM_REQUIRED')
    paths={a['kind']:Path(a['absolute_path']) for a in upstream['artifacts']}
    model=json.loads(paths['mechanical-model'].read_text())
    ref,mode,power,control=normalize(context['design'])
    if model['mode']!=mode or model['parameters']!=parameters():raise ValueError('MECHANICAL_MODEL_BINDING_MISMATCH')
    if mode=='controlled_input':return (lambda t,q:0.),0.,model
    grid=np.load(paths['force-grid'],allow_pickle=False)
    axes=(np.array(model['angles_rad']),np.array(model['deflections_m']))
    if grid.shape!=(len(axes[0]),len(axes[1])) or not np.isfinite(grid).all():raise ValueError('FORCE_TABLE_INVALID')
    table=RegularGridInterpolator(axes,grid,bounds_error=True)
    def force(t,q):
        if abs(q)>.008:raise OutOfDomain('ORIGINAL_8MM_ROM_LIMIT_EXCEEDED')
        angle=min(max(t,0)/ref['door']['opening_s'],1)*np.deg2rad(ref['door']['open_angle_deg'])
        return float(table([[angle,q]])[0])
    return force,model['initial_equilibrium_m'],model


def convergence(coarse,fine):
    """Time-discretization consistency, not physics calibration or uncertainty."""
    rows=[]
    for key in ('peak_vin_V','peak_vout_V','final_vout_V'):
        a=coarse['metrics'][key];b=fine['metrics'][key]
        relative=abs(a-b)/max(abs(b),1e-6)
        rows.append({'metric':key,'coarse':a,'fine':b,'relative_delta':relative,'pass':relative<=.05 or abs(a-b)<=1e-5})
    for key in ('final_input_capacitor','final_output_capacitor','firmware_load'):
        a=coarse['energy_ledger_J'][key];b=fine['energy_ledger_J'][key]
        relative=abs(a-b)/max(abs(b),1e-12)
        rows.append({'metric':key,'coarse':a,'fine':b,'relative_delta':relative,'pass':relative<=.05 or abs(a-b)<=1e-9})
    return {'status':'passed' if all(r['pass'] for r in rows) else 'failed',
            'coarse_dt_s':coarse['dt_s'],'fine_dt_s':fine['dt_s'],'checks':rows,
            'relative_tolerance':.05,'scope':'Macro tick halving under the same explicit behavioral assumptions; not native FEM/COMSOL gate'}


def require_runtime_binding(expected_semantics, observed_model):
    if observed_model.get('semantics')!=expected_semantics:
        raise RuntimeError('NUMERICAL_RUNTIME_IDENTITY_DRIFT')


def coupled_power_stage(context):
    try:
        from .firmware_receiver import FirmwareReceiver
        expected_semantics=deepcopy(context.get('model_version',model_versions()['coupled_power'])['semantics'])
        require_runtime_binding(expected_semantics,model_versions()['coupled_power'])
        out=Path(context['output_dir']);out.mkdir(parents=True,exist_ok=True)
        fw=FirmwareReceiver(context['design'].get('program',{}),build_dir=out/'firmware-build')
        upstream=context.get('inputs',{}).get('program_build',{}).get('result',{}).get('metrics',{})
        expected_build=upstream.get('build_identity')
        if not expected_build or fw.receipt['build_identity']!=expected_build:raise ValueError('RUNTIME_PROGRAM_BUILD_IDENTITY_MISMATCH')
        mech=mechanical_from_upstream(context)
        result=simulate(context['design'],fw,mechanical=mech)
        require_runtime_binding(expected_semantics,result['model_binding']['coupled_power'])
        fine_fw=FirmwareReceiver(context['design'].get('program',{}),build_dir=out/'firmware-build-halfstep')
        if fine_fw.receipt['build_identity']!=expected_build:raise ValueError('HALFSTEP_PROGRAM_BUILD_IDENTITY_MISMATCH')
        fine=simulate(context['design'],fine_fw,step_s=result['dt_s']/2,mechanical=mech)
        require_runtime_binding(expected_semantics,fine['model_binding']['coupled_power'])
        require_runtime_binding(expected_semantics,model_versions()['coupled_power'])
        check=convergence(result,fine)
        # Timing is cost evidence, never scientific artifact content/cache identity.
        from threadpoolctl import threadpool_info
        _write(out/'solver-cost.json',{'coarse_solver_wall_s':result.pop('wall_s'),'halfstep_solver_wall_s':fine.pop('wall_s'),'process_threadpool_inventory':threadpool_info(),'inventory_scope':'Audit only; unrelated CAD/OpenMP/plugin pools are not scientific physics dependencies'})
        _write(out/'physics-power.json',result);_write(out/'physics-power-halfstep.json',fine);_write(out/'time-step-check.json',check)
        metrics=deepcopy(result['metrics']);metrics['firmware']=result['firmware_summary'];metrics['step_halving']=check
        metrics['runtime_build_matches_upstream']=True;metrics['acceptance_scope']='declared-model numerical simulation only';metrics['hardware_verified']=False
        passed=result['metrics']['numerical_pass'] and fine['metrics']['numerical_pass'] and check['status']=='passed'
        return {'run_status':'completed' if passed else 'numerical_fail','design_status':'satisfied' if passed else 'insufficient_evidence',
          'metrics':metrics,'applicability':{'status':'in_domain','limits':ASSUMPTIONS['engineering_assumptions'],'checks':{'energy_balance':result['metrics']['numerical_pass'],'step_halving':check['status']=='passed'}},
          'reasons':['Behavioral PMIC/load execution; receiver determines simulated event mission; physical acceptance not established'],
          'artifacts':[{'kind':'physics-power','path':'physics-power.json'},{'kind':'physics-power-halfstep','path':'physics-power-halfstep.json'},{'kind':'time-step-check','path':'time-step-check.json'},
                       {'kind':'firmware-runtime-build','path':'firmware-build/program-build.json'},{'kind':'firmware-runtime-library','path':'firmware-build/libbf_event.so'}]}
    except Exception as exc:return _failure(exc)
