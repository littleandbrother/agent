"""Independent static cubic-Hermite matrix/Schur review. No provider import,
no ODE, no eigenproblem, no commercial solver, no physical qualification."""
import hashlib,json,math
from pathlib import Path
import numpy as np
ROOT=Path('/workspace/shared/canonical-beam-rom-20261001')
OUT=Path('/workspace/shared/transparent-rom-independent-review-20261001/reports/hermite-schur-readback.json')
pin=json.loads((ROOT/'parameters.json').read_text());p={k:v['value'] for k,v in pin['parameters'].items()}
# Source-independent element/section energy assembly; q is endpoint COM coordinate.
bc,tc,Ec,rc=[p[k] for k in ['copper_width','copper_thickness','copper_young','copper_density']]
bp,tp,Ep,rp,d,epsT=[p[k] for k in ['pzt_width','pzt_thickness','pzt_young_E1','pzt_density','pzt_d31','pzt_epsilon_T33_relative']]
d*=p['poling_sign'];epsT*=p['epsilon0'];zp=(tc+tp)/2
Ac=bc*tc;Ap=bp*tp;A=Ec*Ac+Ep*Ap;B=Ep*Ap*zp
D=Ec*bc*tc**3/12+Ep*(bp*tp**3/12+Ap*zp*zp);P=Ep*d*bp
c_fixed=bp/tp*(epsT-Ep*d*d)
# Schur complement of axial strain in the exact three-variable section enthalpy
# order [axial strain, curvature, voltage], H=0.5*x.T*S*x.
S=np.array([[A,-B,P],[-B,D,-P*zp],[P,-P*zp,-c_fixed]])
Scond=S[1:,1:]-np.outer(S[1:,0],S[0,1:])/S[0,0]
EI=float(Scond[0,0]);g=float(-Scond[0,1]);cN=float(-Scond[1,1]);zn=B/A
bare=Ec*bc*tc**3/12
nodes=np.array([0,p['pzt_start'],p['pzt_end'],p['rigid_attachment_start']]);xg=(p['magnet_start']+p['magnet_end'])/2;a=nodes[-1];L=p['copper_length'];lp=nodes[2]-nodes[1]
K=np.zeros((8,8));M=np.zeros((8,8));elect=np.zeros(8)
for i in range(3):
 h=nodes[i+1]-nodes[i];EIx=EI if i==1 else bare;mu=rc*Ac+(rp*Ap if i==1 else 0)
 ke=EIx/h**3*np.array([[12,6*h,-12,6*h],[6*h,4*h*h,-6*h,2*h*h],[-12,-6*h,12,-6*h],[6*h,2*h*h,-6*h,4*h*h]])
 me=mu*h/420*np.array([[156,22*h,54,-13*h],[22*h,4*h*h,13*h,-3*h*h],[54,13*h,156,-22*h],[-13*h,-3*h*h,-22*h,4*h*h]])
 ids=np.arange(2*i,2*i+4);K[np.ix_(ids,ids)]+=ke;M[np.ix_(ids,ids)]+=me
# Uniform patch voltage enters only endpoint rotations through integral g*kappa.
elect[3]-=g;elect[5]+=g
# Copper overlap a..L is a rigid extension of node a.
h=L-a;M[6,6]+=rc*Ac*h;M[6,7]+=rc*Ac*h*h/2;M[7,6]+=rc*Ac*h*h/2;M[7,7]+=rc*Ac*h**3/3
Kf=K[2:,2:];tf=elect[2:];Mf=M[2:,2:];selector=np.zeros(6);selector[-2:]=[1,xg-a]
response=np.linalg.solve(Kf,np.column_stack([selector,tf]));fresp,vresp=response.T
compliance=float(selector@fresp);k=1/compliance;b=fresp/compliance
alpha=float(selector@vresp);theta=k*alpha;cp=cN*lp
free=float(cp+tf@vresp);condensed=free-alpha*alpha/compliance
ritzfree=cp+theta*theta/k
rotation=b[-1];u0=zn*(b[3]-b[1]);zg=(tc+p['magnet_height'])/2;eta=u0-zg*rotation
mg=p['magnet_density']*(p['magnet_end']-p['magnet_start'])*p['magnet_width']*p['magnet_height']
J=mg*((p['magnet_end']-p['magnet_start'])**2+p['magnet_height']**2)/12
mb=float(b@Mf@b);mv=mg*(selector@b)**2;mx=mg*eta**2;mr=J*rotation**2;mass=float(mb+mv+mx+mr)
values={'neutral_axis_patch_z_m':zn,'EI_bare_N_m2':bare,'EI_patch_N_m2':EI,'k_N_m':k,'theta_C_m':theta,'Cp_ritz_F':cp,'Cfree_ritz_F':ritzfree,'Cfree_continuum_static_F':free,'Cp_static_q_condensed_F':condensed,'mass_kg':mass,'magnet_pitch_slope_per_m':float(rotation),'magnet_axial_shape':float(eta),'phi_magnet_center':float(selector@b),'f_SC_ritz_Hz':math.sqrt(k/mass)/(2*math.pi),'f_OC_ritz_Hz':math.sqrt((k+theta*theta/cp)/mass)/(2*math.pi)}
# Explicit constrained static solution proves the endpoint Schur relation at nonzero V.
Ablock=np.block([[Kf,-selector[:,None]],[selector[None,:],np.zeros((1,1))]])
static=[]
for q,v in [(0,1),(.001,0),(.0008,3),(-.001,-2)]:
 sol=np.linalg.solve(Ablock,np.r_[tf*v,q]);F=float(sol[-1]);Q=float(tf@sol[:-1]+cp*v)
 expF=k*q-theta*v;expQ=theta*q+condensed*v
 assert np.isclose(F,expF,rtol=1e-10,atol=1e-14)
 assert np.isclose(Q,expQ,rtol=1e-10,atol=1e-18)
 static.append({'q_m':q,'v_V':v,'force_N':F,'charge_C':Q,'force_error_N':F-expF,'charge_error_C':Q-expQ})
# Direct section primitive energy versus its Schur counterpart.
section=[]
for curvature,voltage in [(.1,1),(-2,3),(0,5),(.4,0)]:
 eps=(B*curvature-P*voltage)/A;x=np.array([eps,curvature,voltage]);reduced=np.array([curvature,voltage]);h0=.5*x@S@x;h1=.5*reduced@Scond@reduced
 assert np.isclose(h0,h1,rtol=1e-12,atol=1e-16);section.append(float(h0-h1))
# Different synthetic energy from producer test: translation plus orientation coupling.
def potential(q):
 x=xg+eta*q;z=zg+q;beta=-rotation*q
 return 2*x*x+0.03*math.sin(8*z)+.002*math.cos(beta)+.07*x*math.sin(beta)
def generalized(q):
 x=xg+eta*q;z=zg+q;beta=-rotation*q
 Fx=-4*x-.07*math.sin(beta);Fz=-.24*math.cos(8*z);Ty=.002*math.sin(beta)-.07*x*math.cos(beta)
 return float(eta*Fx+Fz-rotation*Ty)
virtual=[]
for q in (-.004,-.001,0,.001,.004):
 h=1e-5
 fd=-(-potential(q+2*h)+8*potential(q+h)-8*potential(q-h)+potential(q-2*h))/(12*h)
 analytic=generalized(q);err=abs(fd-analytic);assert err<=1e-9
 virtual.append({'q_m':q,'Q_chainrule_N':analytic,'Q_energy_N':float(fd),'abs_error_N':float(err)})
reported=json.loads((ROOT/'outputs/canonical-static-rom.json').read_text());comparisons={}
for key,val in values.items():
 ref=reported[key];relative=abs(val-ref)/max(abs(ref),1e-30)
 assert relative<1e-10,(key,val,ref,relative)
 comparisons[key]={'independent':val,'provider':ref,'relative_difference':relative}
assert cp>0 and k>0 and condensed>=cp and free>=ritzfree
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'schema':'bf-independent-hermite-schur-static-review-v1','status':'pass_for_stated_conditional_scalar_model','method':'Cubic-Hermite stiffness/consistent-mass assembly, axial and endpoint Schur complements, constrained static solves, independent virtual-work finite differences','provider_imports':0,'dynamic_runs':0,'source_parameter_sha256':sha(ROOT/'parameters.json'),'provider_output_sha256':sha(ROOT/'outputs/canonical-static-rom.json'),'review_source_sha256':sha(Path(__file__)),'comparison_count':len(comparisons),'comparisons':comparisons,'max_relative_difference':max(v['relative_difference'] for v in comparisons.values()),'section_enthalpy_residuals_J_per_m':section,'constrained_endpoint_solutions':static,'virtual_work_checks':virtual,'mass_terms_kg':{'beam_transverse':mb,'magnet_vertical':float(mv),'magnet_axial':float(mx),'magnet_pitch':float(mr)},'capacitance_gap_from_omitted_bending_relaxation_F':condensed-cp,'force_table_automatically_compatible':False,'physical_qualified':False}
OUT.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['comparisons','constrained_endpoint_solutions','virtual_work_checks','mass_terms_kg']},indent=2))
