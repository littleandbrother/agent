"""Thin source-bound passive benchmark. Dynamics require frozen authorization.

No native-PMIC, mission, firmware, receiver or feasibility interface exists here.
The original static providers are imported unchanged under this new study ID.
"""
from pathlib import Path
import argparse, hashlib, json, math, sys, time, traceback
import inspect,scipy
from functools import lru_cache
import numpy as np
from numpy.polynomial import Polynomial
from scipy.integrate import Radau
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'sources/magnetic'))
from magnetic_interface import StaticMagneticInterface, DomainError, jsonable
VERSION='bf-conditional-qonly-passive-bridge-storage-v1'
STATE_NAMES=['q_m','qdot_m_s','Q_C','Vs_V','Dmechanical_J','Dresistor_J','Wdriver_translation_J','Wdriver_rotation_J']
QUAD_COLUMNS=['t_s','q_m','Fq6_N','Fq10_N','U6_J','U10_J','dU_da6_J_rad','dU_da10_J_rad']+[f'{label}_{axis}' for label in ['Ftip6_N','tauTip6_Nm','tauDriver6_Nm','Ftip10_N','tauTip10_Nm','tauDriver10_Nm','dDriverCenter_da_m_rad'] for axis in 'xyz']+['adot_rad_s','qdot_m_s','Vp_V','Vs_V','bridge_current_A','Pdriver_translation_W','Pdriver_rotation_W','Pmechanical_loss_W','Presistor_loss_W']
LEDGER_COLUMNS=['t_s','kinetic_J','elastic_J','piezo_J','storage_J','mutual_magnetic_J',*STATE_NAMES[4:],'residual_J','scale_J']

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_json(path,value):
    Path(path).write_text(json.dumps(jsonable(value),indent=2,allow_nan=False)+'\n')
def rectifier(vp,vs,resistance):
    current=max(abs(vp)-vs,0.)/resistance
    return current, float(np.sign(vp))*current

class Model:
    def __init__(self,cin,plan=None,study_deadline_unix=None):
        self.plan=plan or json.loads((ROOT/'PLAN.json').read_text())
        self.source=StaticMagneticInterface(ROOT/'sources/magnetic')
        self.rom=self.source.rom;self.cin=cin
        self.k=self.rom['k_N_m'];self.m=self.rom['mass_kg'];self.theta=self.rom['theta_C_m'];self.cp=self.rom['Cp_ritz_F']
        self.c=2*self.plan['damping_ratio']*math.sqrt(self.m*self.k)
        self.R=self.plan['rectifier']['series_resistance_ohm']
        self.pivot=self.source.A@(np.array(self.source.world['geometry']['pivot_world_m'])-self.source.beam_origin_world)
        self.amax=self.source.world['input']['opening_angle_rad'];self.opening=self.source.world['input']['opening_s']
        self.evaluations=0;self.force_evaluations=0;self.start=time.monotonic();self.last=None;self.study_deadline_unix=study_deadline_unix
    def budget(self):
        b=self.plan['budgets']
        if self.evaluations>b['rhs_per_trajectory'] or self.force_evaluations>b['force_evaluations_per_trajectory'] or time.monotonic()-self.start>b['wall_per_trajectory_s'] or (self.study_deadline_unix is not None and time.time()>=self.study_deadline_unix):
            raise RuntimeError('finite execution budget exhausted')
    @lru_cache(maxsize=64)
    def force(self,a,q,n):
        self.force_evaluations+=1;self.budget()
        return self.source.evaluate(a,q,n)
    def angle(self,t):return min(max(t,0.)/self.opening,1.)*self.amax
    def driver_terms(self,r,adot):
        dcenter_da=np.cross([0.,1.,0.],r['driver_center_beam_m']-self.pivot)
        # Actuator work on modeled system = -(driver magnetic generalized force)*adot.
        translation=float(r['force_beam_N']@dcenter_da)
        rotation=-float(r['driver_torque_about_COM_beam_N_m'][1])
        return translation*adot,rotation*adot,translation+rotation
    def rhs(self,t,y,adot):
        self.evaluations+=1;self.budget()
        if not np.isfinite(y).all():raise DomainError('nonfinite state')
        q,qd,Q,vs=y[:4]
        if vs < -self.plan['gates']['storage_negative_tolerance_V']:raise DomainError('negative storage voltage')
        if abs(q)>self.plan['gates']['q_limit_m']:raise DomainError('q outside inherited support')
        vp=(Q-self.theta*q)/self.cp
        if abs(vp)>self.plan['gates']['voltage_computational_guard_V'] or vs>self.plan['gates']['voltage_computational_guard_V']:raise DomainError('numerical voltage guard exceeded; not physical limit')
        r=self.force(self.angle(t),float(q),self.plan['dynamic_quadrature_order'])
        I,i=rectifier(vp,vs,self.R)
        pt,pr,_=self.driver_terms(r,adot)
        out=np.array([qd,(r['generalized_force_N']-self.c*qd-self.k*q+self.theta*vp)/self.m,-i,I/self.cin,self.c*qd*qd,self.R*I*I,pt,pr])
        self.last={'t_s':t,'state':y.tolist(),'rhs':out.tolist()}
        return out
    def stored(self,y,r):
        q,qd,Q,vs=y[:4];vp=(Q-self.theta*q)/self.cp
        energies=np.array([.5*self.m*qd*qd,.5*self.k*q*q,.5*self.cp*vp*vp,.5*self.cin*vs*vs,r['mutual_potential_J']])
        return energies

def real_roots_in_unit(poly):
    return [float(x.real) for x in poly.roots() if abs(x.imag)<1e-9 and 0<x.real<1]
def polynomial_bounds(poly):
    xs=[0.,1.]+real_roots_in_unit(poly.deriv())
    values=[float(poly(x)) for x in xs]
    return min(values),max(values)
def dense_polynomial(dense,index):
    # SciPy Radau dense output is a cubic in x=(t-t_old)/h.
    return Polynomial([dense.y_old[index],*dense.Q[index]])

def check_frozen():
    seal=json.loads((ROOT/'PLAN-SEAL.json').read_text())
    for p,h in seal['bindings'].items():
        if sha(ROOT/p)!=h:raise RuntimeError('frozen binding changed: '+p)
    toolchain=json.loads((ROOT/'PLAN.json').read_text())['toolchain']
    if toolchain['python']!=sys.version or toolchain['numpy']!=np.__version__ or toolchain['scipy']!=scipy.__version__ or toolchain['scipy_radau_source_sha256']!=sha(inspect.getfile(Radau)):
        raise RuntimeError('numerical runtime binding changed')
    authorization=json.loads((ROOT/'DYNAMIC-AUTHORIZATION.json').read_text())
    if authorization['plan_seal_sha256']!=sha(ROOT/'PLAN-SEAL.json') or not authorization.get('root_approved') or not authorization.get('independent_review_approved'):
        raise RuntimeError('exact frozen study not dynamically authorized')
    return seal

def require_complete(sample,accepted):
    """Reject interrupted, truncated, duplicated, nonfinite or stale time grids."""
    sample=np.asarray(sample);accepted=np.asarray(accepted)
    if sample.shape!=(4001,9) or accepted.ndim!=2 or accepted.shape[1]!=9 or len(accepted)<2:
        raise RuntimeError('incomplete state output dimensions')
    if not np.isfinite(sample).all() or not np.isfinite(accepted).all():raise RuntimeError('nonfinite retained states')
    if not np.array_equal(sample[:,0],np.linspace(0.,4.,4001)):raise RuntimeError('incomplete exact output grid')
    if accepted[0,0]!=0. or accepted[-1,0]!=4. or not np.all(np.diff(accepted[:,0])>0):raise RuntimeError('incomplete accepted-step time range')
    if not np.allclose(sample[-1,1:],accepted[-1,1:],atol=1e-13,rtol=1e-12):raise RuntimeError('final state disagreement')

def run_one(cin_id,resolution):
    check_frozen();plan=json.loads((ROOT/'PLAN.json').read_text())
    case=next(c for c in plan['cases'] if c['id']==cin_id);settings=plan['resolutions'][resolution]
    execution_id=f'{cin_id}-{resolution}';order=plan['execution_order'];index=order.index(execution_id)
    for previous in order[:index]:
        previous_path=ROOT/'outputs'/previous/'SUMMARY.json'
        if not previous_path.exists() or json.loads(previous_path.read_text())['status']!='TRAJECTORY_CHECKS_PASS':
            raise RuntimeError('previous planned trajectory missing/failed; branch stopped')
    started=list((ROOT/'outputs').glob('cin*-*/STARTED.json'))
    if len(started)>=plan['dynamic_trajectories_max']:raise RuntimeError('four-trajectory ceiling')
    if started and time.time()-min(json.loads(p.read_text())['started_unix'] for p in started)>plan['budgets']['total_wall_cap_s']:
        raise RuntimeError('whole-study wall budget')
    outdir=ROOT/'outputs'/f'{cin_id}-{resolution}'
    outdir.mkdir(exist_ok=False)
    identity={'version':VERSION,'case':case,'resolution_id':resolution,'settings':settings,'plan_seal_sha256':sha(ROOT/'PLAN-SEAL.json'),'equilibrium_sha256':sha(ROOT/'outputs/EQUILIBRIUM-PREFLIGHT.json')}
    write_json(outdir/'STARTED.json',{**identity,'started_unix':time.time()})
    study_start=min(json.loads(p.read_text())['started_unix'] for p in [*started,outdir/'STARTED.json'])
    m=Model(case['cin_F'],plan,study_start+plan['budgets']['total_wall_cap_s']);eq=json.loads((ROOT/'outputs/EQUILIBRIUM-PREFLIGHT.json').read_text())
    y=np.array([eq['q0_m'],0,eq['Q0_C'],0,0,0,0,0],float)
    r0=m.force(0.,float(y[0]),6);E0=m.stored(y,r0);initial=float(sum(E0))
    samples=[];segments=[];accepted=[[0.,*y]];quad=[];domain=[];ledger=[];simpson=np.zeros(4)
    grid=np.linspace(0.,4.,4001);gi=0;max_residual=0.;energy_scale=0.;failed='execution incomplete';completed=False
    maxima={'q_min_m':float(y[0]),'q_max_m':float(y[0]),'Vp_min_V':0.,'Vp_max_V':0.,'Vs_peak_V':0.}
    try:
        for ta,tb,adot in [(0.,2.,m.amax/2),(2.,4.,0.)]:
            solver=Radau(lambda t,y:m.rhs(t,y,adot),ta,y,tb,max_step=settings['max_step_s'],rtol=settings['rtol'],atol=np.array(settings['atol']),first_step=settings['first_step_s'])
            while solver.status=='running':
                m.budget();message=solver.step()
                if solver.status=='failed':raise RuntimeError('Radau: '+str(message))
                dense=solver.dense_output();h=dense.t-dense.t_old
                if len(segments)>=plan['budgets']['accepted_steps_per_trajectory']:raise RuntimeError('accepted-step budget exhausted')
                segments.append({'t0':dense.t_old,'t1':dense.t,'y0':dense.y_old.tolist(),'polynomial_coefficients':dense.Q.tolist()})
                qpoly=dense_polynomial(dense,0);Qpoly=dense_polynomial(dense,2);vspoly=dense_polynomial(dense,3)
                qpmin,qpmax=polynomial_bounds(qpoly);vppoly=(Qpoly-m.theta*qpoly)/m.cp
                vpmin,vpmax=polynomial_bounds(vppoly);vsmin,vsmax=polynomial_bounds(vspoly)
                if max(abs(qpmin),abs(qpmax))>plan['gates']['q_limit_m']:raise DomainError('dense path q-domain exit')
                if vsmin < -plan['gates']['storage_negative_tolerance_V']:raise DomainError('dense storage negativity')
                if max(abs(vpmin),abs(vpmax),vsmax)>plan['gates']['voltage_computational_guard_V']:raise DomainError('dense voltage guard')
                maxima['q_min_m']=min(maxima['q_min_m'],qpmin);maxima['q_max_m']=max(maxima['q_max_m'],qpmax)
                maxima['Vp_min_V']=min(maxima['Vp_min_V'],vpmin);maxima['Vp_max_V']=max(maxima['Vp_max_V'],vpmax);maxima['Vs_peak_V']=max(maxima['Vs_peak_V'],vsmax)
                # Lipschitz/Hausdorff clearance lower bound along this numerical cubic.
                qrate=max(abs(v) for v in polynomial_bounds(qpoly.deriv()))/h
                left=m.force(m.angle(dense.t_old),float(dense.y_old[0]),6)
                rp=np.linalg.norm(m.source.world['geometry']['tip_size_m'])/2
                rd=np.linalg.norm(m.source.world['geometry']['driver_size_m'])/2
                gamma=abs(m.rom['magnet_pitch_slope_per_m']);psi=m.rom['magnet_axial_shape']
                tip_rate=(math.sqrt(1+psi*psi)+rp*gamma)*qrate
                driver_radius=np.linalg.norm(np.cross([0.,1.,0.],left['driver_center_beam_m']-m.pivot))
                lower=left['contact']['surface_distance_lower_bound_m']-h*(tip_rate+(driver_radius+rd)*adot)
                if lower<=1e-12:raise DomainError('continuous numerical-path magnet separation not certified')
                domain.append([dense.t_old,dense.t,qpmin,qpmax,lower])
                while gi<len(grid) and grid[gi]<=dense.t+1e-14:
                    if grid[gi]>=dense.t_old-1e-14:samples.append([float(grid[gi]),*dense(float(grid[gi]))])
                    gi+=1
                accepted.append([float(solver.t),*solver.y])
                # Every accepted endpoint and midpoint, retaining one-sided t=2 powers.
                interval_powers=[]
                for tt in [dense.t_old,dense.t_old+h/2,dense.t]:
                    yy=dense(tt);a=m.angle(tt);r6=m.force(a,float(yy[0]),6);r10=m.force(a,float(yy[0]),10)
                    _,_,da6=m.driver_terms(r6,1.);_,_,da10=m.driver_terms(r10,1.)
                    quantities=[r6['generalized_force_N'],r10['generalized_force_N'],r6['mutual_potential_J'],r10['mutual_potential_J'],da6,da10]
                    dcda=np.cross([0.,1.,0.],r6['driver_center_beam_m']-m.pivot)
                    vp=(yy[2]-m.theta*yy[0])/m.cp;I,_=rectifier(vp,yy[3],m.R)
                    pt,pr,_=m.driver_terms(r6,adot);pd=m.c*yy[1]**2;pe=m.R*I*I
                    interval_powers.append([pd,pe,pt,pr])
                    primitives=[]
                    for rr in [r6,r10]:
                        for key in ['force_beam_N','tip_torque_about_COM_beam_N_m','driver_torque_about_COM_beam_N_m']:primitives.extend(rr[key])
                    quad.append([tt,yy[0],*quantities,*primitives,*dcda,adot,yy[1],vp,yy[3],I,pt,pr,pd,pe])
                    for j,key in [(0,'force_N'),(2,'potential_J'),(4,'driver_derivative_J_per_rad')]:
                        abs_tol,rel_tol=plan['gates']['quadrature'][key]
                        if abs(quantities[j]-quantities[j+1])>abs_tol+rel_tol*abs(quantities[j+1]):raise RuntimeError('quadrature refinement unresolved: '+key)
                    ee=m.stored(yy,r6);W=yy[6]+yy[7];D=yy[4]+yy[5]
                    resid=float(sum(ee)-initial+D-W)
                    scale=max(float(sum(E0[:4])),abs(W),abs(ee[4]-E0[4]),1e-9)
                    max_residual=max(max_residual,abs(resid));energy_scale=max(energy_scale,scale)
                    ledger.append([tt,*ee,*yy[4:],resid,scale])
                    if abs(resid)>plan['gates']['energy_abs_J']+plan['gates']['energy_relative']*scale:raise RuntimeError('energy ledger unresolved')
                    if min(yy[4],yy[5]) < -1e-12:raise RuntimeError('negative accumulated dissipation')
                simpson += h*(np.array(interval_powers[0])+4*np.array(interval_powers[1])+np.array(interval_powers[2]))/6
            y=solver.y.copy()
        if gi!=len(grid):raise RuntimeError('common sample grid incomplete')
        require_complete(samples,accepted)
        simpson_delta=abs(simpson-y[4:])
        if np.any(simpson_delta>plan['gates']['independent_ledger_abs_J']+plan['gates']['independent_ledger_relative']*np.maximum(abs(simpson),1e-9)):
            raise RuntimeError('independent Simpson ledger integration unresolved')
        m.budget();completed=True;failed=None
    except BaseException as e:
        failed=repr(e)
        (outdir/'FAILURE.txt').write_text(traceback.format_exc())
    finally:
        if not completed and failed is None:failed='execution incomplete'
        np.savez_compressed(outdir/'raw.npz',sample=np.array(samples),accepted=np.array(accepted),quadrature=np.array(quad),domain=np.array(domain),ledger=np.array(ledger))
        write_json(outdir/'DENSE-SEGMENTS.json',segments)
        summary={'status':'INSUFFICIENT_NUMERICAL_EVIDENCE' if failed else 'TRAJECTORY_CHECKS_PASS','exception':failed,'version':VERSION,'case':case,'resolution':resolution,'settings':settings,'initial_components_J':E0.tolist(),'initial_total_J':initial,'final_state':accepted[-1][1:],'last_accepted_t_s':accepted[-1][0],'maxima':maxima,'max_energy_residual_J':max_residual,'max_energy_scale_J':energy_scale,'rhs_evaluations':m.evaluations,'force_evaluations':m.force_evaluations,'accepted_steps':len(segments),'wall_s':time.monotonic()-m.start,'last_rhs':m.last,'state_names':STATE_NAMES,'quadrature_columns':QUAD_COLUMNS,'ledger_columns':LEDGER_COLUMNS,'independent_simpson_ledger_J':simpson.tolist(),'new_dynamic_trajectories':1,'native_equivalent':False,'physical_qualified':False,'assumed_q_only_path':True}
        if failed is None:
            summary['final_storage_J']=.5*m.cin*y[3]**2
            summary['final_components_J']=m.stored(y,m.force(m.amax,float(y[0]),6)).tolist()
            summary['minimum_continuous_path_clearance_lower_bound_m']=min(x[-1] for x in domain)
            summary['independent_simpson_minus_ode_ledger_J']=(simpson-y[4:]).tolist()
        write_json(outdir/'SUMMARY.json',summary)
        write_json(outdir/'RUN-SEAL.json',{'identity':identity,'files':{p.name:sha(p) for p in outdir.iterdir() if p.is_file() and p.name!='RUN-SEAL.json'}})
    print(json.dumps({k:v for k,v in summary.items() if k!='last_rhs'},indent=2))
    return failed is None

def compare():
    check_frozen();plan=json.loads((ROOT/'PLAN.json').read_text());result={'version':VERSION,'cases':{},'gates':{},'all_pass':True}
    fine={};resolution_deltas={}
    for case in plan['cases']:
        cid=case['id'];dirs=[ROOT/'outputs'/f'{cid}-{r}' for r in ['coarse','fine']]
        for r,d in zip(['coarse','fine'],dirs):
            seal=json.loads((d/'RUN-SEAL.json').read_text())
            expected={'version':VERSION,'case':case,'resolution_id':r,'settings':plan['resolutions'][r],'plan_seal_sha256':sha(ROOT/'PLAN-SEAL.json'),'equilibrium_sha256':sha(ROOT/'outputs/EQUILIBRIUM-PREFLIGHT.json')}
            if seal['identity']!=expected:raise RuntimeError('swapped/stale run identity')
            for name,h in seal['files'].items():
                if sha(d/name)!=h:raise RuntimeError('run artifact hash mismatch: '+name)
            if not {'STARTED.json','SUMMARY.json','raw.npz','DENSE-SEGMENTS.json'}<=set(seal['files']):raise RuntimeError('incomplete run binding')
        summaries=[json.loads((d/'SUMMARY.json').read_text()) for d in dirs]
        for r,s in zip(['coarse','fine'],summaries):
            if s['case']!=case or s['resolution']!=r or s['settings']!=plan['resolutions'][r]:raise RuntimeError('summary semantic identity mismatch')
        if any(s['status']!='TRAJECTORY_CHECKS_PASS' for s in summaries):raise RuntimeError('incomplete/failed trajectory; comparison refused')
        raw=[np.load(d/'raw.npz') for d in dirs]
        for data,s in zip(raw,summaries):
            require_complete(data['sample'],data['accepted'])
            if s['last_accepted_t_s']!=4. or not np.array_equal(s['final_state'],data['accepted'][-1,1:]):raise RuntimeError('summary completion mismatch')
        a,b=[data['sample'] for data in raw]
        if not np.array_equal(a[:,0],b[:,0]):raise RuntimeError('unmatched grids')
        m=Model(case['cin_F'],plan);checks={}
        series={'q_m':(a[:,1],b[:,1]),'Vs_V':(a[:,4],b[:,4]),'Vp_V':((a[:,3]-m.theta*a[:,1])/m.cp,(b[:,3]-m.theta*b[:,1])/m.cp)}
        for field,(x,y) in series.items():
            delta=float(max(abs(x-y)));scale=float(max(abs(y)));at,rt=plan['gates']['time_refinement'][field]
            checks[field]={'sup_abs_delta':delta,'threshold':at+rt*scale,'pass':delta<=at+rt*scale}
        for field in ['final_storage_J','maxima.Vs_peak_V']:
            vals=[s['final_storage_J'] if field=='final_storage_J' else s['maxima']['Vs_peak_V'] for s in summaries]
            at,rt=plan['gates']['time_refinement']['energy_J' if field=='final_storage_J' else 'Vs_V']
            delta=abs(vals[1]-vals[0]);checks[field]={'abs_delta':delta,'threshold':at+rt*abs(vals[1]),'pass':delta<=at+rt*abs(vals[1])}
        for index,label in [(4,'Dmechanical_J'),(5,'Dresistor_J'),(6,'Wdriver_translation_J'),(7,'Wdriver_rotation_J')]:
            vals=[s['final_state'][index] for s in summaries];at,rt=plan['gates']['time_refinement']['energy_J']
            delta=abs(vals[1]-vals[0]);checks[label]={'abs_delta':delta,'threshold':at+rt*abs(vals[1]),'pass':delta<=at+rt*abs(vals[1])}
        result['gates'][cid]=checks;result['all_pass'] &= all(v['pass'] for v in checks.values());fine[cid]=summaries[1]
        resolution_deltas[cid]={f:checks[f]['abs_delta'] for f in ['final_storage_J','maxima.Vs_peak_V']}
        result['cases'][cid]=summaries
    effects={}
    for field in ['final_storage_J','maxima.Vs_peak_V']:
        vals={cid:(s['final_storage_J'] if field=='final_storage_J' else s['maxima']['Vs_peak_V']) for cid,s in fine.items()}
        effect=vals['cin10']-vals['cin47'];resolution=sum(d[field] for d in resolution_deltas.values())
        effects[field]={'cin10_minus_cin47':effect,'coarse_fine_delta_sum':resolution,'effect_exceeds_five_times_observed_resolution_delta':abs(effect)>5*resolution,'empirical_only_not_error_bound':True}
    for v in effects.values():v['resolved_difference_admitted']=result['all_pass'] and v['effect_exceeds_five_times_observed_resolution_delta']
    result['effects']=effects;result['claim']='Numerically checked conditional passive comparison on assumed q-only path; only effects individually marked resolved_difference_admitted have a resolved direction' if result['all_pass'] else 'Insufficient numerical evidence; no sensitivity conclusion admitted'
    write_json(ROOT/'outputs/COMPARISON.json',result);print(json.dumps({'all_pass':result['all_pass'],'effects':effects},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',choices=['cin47','cin10']);p.add_argument('--resolution',choices=['coarse','fine']);p.add_argument('--compare',action='store_true');a=p.parse_args()
    if a.compare:compare()
    elif a.case and a.resolution:sys.exit(0 if run_one(a.case,a.resolution) else 2)
    else:p.error('case/resolution or compare required')
