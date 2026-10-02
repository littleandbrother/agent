"""Independent axial bar condensation, no provider imports or force evaluation."""
import json,hashlib,math
from pathlib import Path
import numpy as np
R=Path('/workspace/shared/canonical-beam-rom-20261001');O=Path('/workspace/shared/transparent-rom-independent-review-20261001/reports/axial-bar-readback.json')
p={k:v['value'] for k,v in json.loads((R/'parameters.json').read_text())['parameters'].items()}
xs=[0,p['pzt_start'],p['pzt_end'],p['rigid_attachment_start']]
A0=p['copper_young']*p['copper_width']*p['copper_thickness'];A1=A0+p['pzt_young_E1']*p['pzt_width']*p['pzt_thickness']
P=p['pzt_young_E1']*p['pzt_d31']*p['poling_sign']*p['pzt_width'];K=np.zeros((4,4));t=np.zeros(4)
for i in range(3):
 h=xs[i+1]-xs[i];A=A1 if i==1 else A0;K[i:i+2,i:i+2]+=A/h*np.array([[1,-1],[-1,1]])
# H contains +P*(u_right-u_left)*V, so t gives opposite voltage load.
t[1]+=P;t[2]-=P;K=K[1:,1:];t=t[1:];f=np.array([0.,0.,1.]);invf=np.linalg.solve(K,f);invt=np.linalg.solve(K,t)
alpha=float(f@invf);beta=float(f@invt)
epsS=p['epsilon0']*p['pzt_epsilon_T33_relative']-p['pzt_young_E1']*p['pzt_d31']**2
raw=p['pzt_width']/p['pzt_thickness']*epsS*(xs[2]-xs[1]);relaxed=float(raw+t@invt);fixed=relaxed-beta*beta/alpha
provider=json.loads((R/'AXIAL-SENSITIVITY.json').read_text())
for key,v in [('alpha_m_per_N',alpha),('beta_m_per_V_equivalently_C_per_N',beta),('fixed_eta_capacitance_F',fixed)]:assert math.isclose(v,provider[key],rel_tol=2e-14),(key,v,provider[key])
# Reconstruct the electrical boundary condition with endpoint displacement imposed.
block=np.block([[K,-f[:,None]],[f[None,:],np.zeros((1,1))]])
checks=[]
for V,N in [(0,1),(10,1),(10,-1),(-10,1),(0,-1)]:
 eta=alpha*N+beta*V;u=np.linalg.solve(block,np.r_[t*V,eta]);Q=float(t@u[:-1]+raw*V)
 assert math.isclose(u[-1],N,rel_tol=1e-12,abs_tol=1e-12)
 assert math.isclose(Q,relaxed*V+beta*N,rel_tol=1e-12,abs_tol=1e-18)
 strain=float(.5*u[:-1]@K@u[:-1]);free=invt*V;strain0=float(.5*free@K@free)
 expected=.5*alpha*N*N+beta*N*V;error=strain-strain0-expected;assert abs(error)<1e-20
 checks.append({'synthetic_voltage_V':V,'synthetic_axial_force_N':N,'eta_m':eta,'charge_C':Q,'elastic_energy_increment_J':strain-strain0,'formula_residual_J':error})
assert fixed>0
result={'schema':'bf-independent-axial-bar-condensation-v1','status':'pass_conditional_static_algebra','method':'Three nonuniform linear axial-bar elements; clamped-end and constrained-tip Schur solves, no producer imports','alpha_m_per_N':alpha,'beta_m_per_V':beta,'Cp_relaxed_F':relaxed,'Cp_fixed_eta_F':fixed,'reciprocal_charge_force_coefficient_C_per_N':beta,'synthetic_controls':checks,'magnetic_feedback_bound_conditions':['verified derivative supremum on entire interval','mapping into that interval','alpha*Lx<1'],'actual_operating_bounds':None,'new_dynamic_runs':0,'new_magnetic_evaluations':0,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'producer_addendum_sha256':hashlib.sha256((R/'AXIAL-SENSITIVITY.json').read_bytes()).hexdigest()}
O.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
