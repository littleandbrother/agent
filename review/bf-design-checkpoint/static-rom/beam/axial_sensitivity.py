"""Additive static axial compliance/voltage sensitivity. No dynamics or force solve."""
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from numpy.polynomial import Polynomial as P
from beam_rom import ROOT,load_inputs,build,enthalpy

def coefficients(p):
    A0=p['copper_young']*p['copper_width']*p['copper_thickness']
    A=A0+p['pzt_young_E1']*p['pzt_width']*p['pzt_thickness']
    length=p['pzt_end']-p['pzt_start']
    e=p['pzt_young_E1']*p['pzt_d31']*p['poling_sign']
    alpha=(p['rigid_attachment_start']-length)/A0+length/A
    beta=-e*p['pzt_width']*length/A
    return alpha,beta

def bounded_shift(alpha,beta,force_bound_N,voltage_bound_V):
    if min(force_bound_N,voltage_bound_V)<0 or not all(math.isfinite(x) for x in [force_bound_N,voltage_bound_V]):
        raise ValueError('Bounds must be nonnegative finite verified magnitudes')
    return {'axial_displacement_bound_m':alpha*force_bound_N+abs(beta)*voltage_bound_V,
            'axial_load_charge_bound_C':abs(beta)*force_bound_N,
            'fixed_qV_load_induced_elastic_energy_change_abs_bound_J':.5*alpha*force_bound_N**2+abs(beta)*force_bound_N*voltage_bound_V}

def feedback_shift_bound(alpha,beta,reference_force_N,voltage_bound_V,force_gradient_bound_N_m):
    if force_gradient_bound_N_m<0 or not math.isfinite(force_gradient_bound_N_m) or alpha*force_gradient_bound_N_m>=1:
        raise ValueError('No contraction bound: alpha*Lx must be strictly below one')
    if voltage_bound_V<0 or not all(math.isfinite(x) for x in [voltage_bound_V,reference_force_N]):
        raise ValueError('Invalid force/voltage bound')
    return (alpha*abs(reference_force_N)+abs(beta)*voltage_bound_V)/(1-alpha*force_gradient_bound_N_m)

def primitive_energy(p,r,q,V,N):
    """Integrate primitive elastic and electric enthalpy with constant axial N."""
    gp,gw=np.polynomial.legendre.leggauss(8)
    H=elastic=0.
    for sh in r['shapes']:
        if sh.get('rigid'):continue
        h=sh['x_end_m']-sh['x_start_m'];patched=sh['x_start_m']==p['pzt_start']
        A=p['copper_young']*p['copper_width']*p['copper_thickness']
        if patched:A+=p['pzt_young_E1']*p['pzt_width']*p['pzt_thickness']
        curv=P(sh['phi_coefficients_in_local_x']).deriv(2)
        for xx,wx in zip((gp+1)*h/2,gw*h/2):
            kappa=q*curv(xx);uprime=sh['neutral_axis_z_m']*kappa+N/A
            if patched:uprime-=r['pzt_e31_scalar_C_m2']*p['pzt_width']*V/A
            layers=[(-p['copper_thickness']/2,p['copper_thickness'],p['copper_width'],p['copper_young'],False)]
            if patched:layers.append((p['copper_thickness']/2,p['pzt_thickness'],p['pzt_width'],p['pzt_young_E1'],True))
            for z0,t,b,E,piezo in layers:
                for z,wz in zip(z0+(gp+1)*t/2,gw*t/2):
                    S=uprime-z*kappa;el=.5*E*S*S;dens=el
                    if piezo:
                        field=-V/p['pzt_thickness']
                        dens-=r['pzt_e31_scalar_C_m2']*S*field+.5*r['pzt_epsilon_S1_Tother0_F_m']*field*field
                    H+=wx*wz*b*dens;elastic+=wx*wz*b*el
    return H,elastic

def main():
    p=load_inputs();r=build();alpha,beta=coefficients(p)
    checks=[]
    # Synthetic algebra controls, not device force/voltage operating assumptions.
    for q,V,N in [(0.,0.,1.),(.0008,10.,1.),(.0008,10.,-1.),(-.0008,-10.,1.),(.0008,0.,-1.)]:
        H,E=primitive_energy(p,r,q,V,N);_,E0=primitive_energy(p,r,q,V,0.)
        expectedH=enthalpy(r,q,V)+.5*alpha*N*N
        expectedE=.5*alpha*N*N+beta*N*V
        if abs(H-expectedH)>2e-15 or abs(E-E0-expectedE)>2e-15:
            raise AssertionError('primitive-energy axial reduction mismatch')
        checks.append({'synthetic_q_m':q,'synthetic_V':V,'synthetic_N':N,'enthalpy_residual_J':H-expectedH,'elastic_energy_increment_residual_J':E-E0-expectedE})
    def H_eta(q,eta,V):return enthalpy(r,q,V)+(eta-beta*V)**2/(2*alpha)
    eta=alpha+beta*10;dv=1e-4;Q=-(H_eta(.0008,eta,10+dv)-H_eta(.0008,eta,10-dv))/(2*dv)
    expectedQ=r['theta_C_m']*.0008+r['Cp_ritz_F']*10+beta
    if abs(Q-expectedQ)>1e-15:raise AssertionError('voltage derivative charge mismatch')
    for args in [(-1.,1.),(1.,-1.),(float('nan'),1.)]:
        try:bounded_shift(alpha,beta,*args)
        except ValueError:pass
        else:raise AssertionError('invalid bound accepted')
    for L in [1/alpha,2/alpha,-1.]:
        try:feedback_shift_bound(alpha,beta,1,1,L)
        except ValueError:pass
        else:raise AssertionError('noncontractive gradient accepted')
    out={
      'schema':'bf-static-axial-sensitivity-addendum-v1','base_manifest_sha256':hashlib.sha256((ROOT/'MANIFEST.json').read_bytes()).hexdigest(),
      'scope':'Fixed retained bending q and voltage; constant axial force carried by the flexible composite beam, rigid distal body; no dynamics or magnetic-force evaluations',
      'alpha_m_per_N':alpha,'beta_m_per_V_equivalently_C_per_N':beta,
      'fixed_eta_capacitance_F':r['Cp_ritz_F']-beta*beta/alpha,
      'one_axial_coordinate_enthalpy':'H(q,eta,V)=H_Ritz(q,V)+(eta-beta*V)^2/(2*alpha)',
      'eta_definition':'Additional axial COM displacement relative to q-only short-circuit path; eta=alpha*N+beta*V. Pitch and retained q are held fixed.',
      'axial_force_relation':'N=(eta-beta*V)/alpha',
      'charge_relation':'Q=theta*q+Cp_Ritz*V+beta*N',
      'zero_N_voltage_pose_term':'q-only pose omits eta=beta*V even at N=0',
      'fixed_qV_elastic_energy_increment':'DeltaU_elastic = 0.5*alpha*N^2 + beta*N*V, relative to N=0 at the same q,V. It can be signed and is storage, not a loss.',
      'zero_V_energy':'At V=0, extra elastic energy is exactly 0.5*alpha*N^2 within this model.',
      'retained_bending_energy':'0.5*k*q^2; a relative error bound divides the absolute load-induced energy bound by this value only for q!=0. No finite relative bound exists at q=0.',
      'bound_formulas':{'shift':'|delta_x| <= alpha*Fmax+|beta|*Vmax','load_induced_charge':'|DeltaQ| <= |beta|*Fmax','energy_increment_abs':'|DeltaU_elastic| <= 0.5*alpha*Fmax^2+|beta|*Fmax*Vmax','magnetic_energy_pose_change':'|DeltaU_mag| <= Fmax_path*|delta_x| if Fmax_path truly bounds axial force on the displaced segment at fixed q/pitch/driver state'},
      'magnetic_feedback':{'condition':'alpha*Lx<1, with Lx a verified sup|dFx/dx| on an invariant displacement interval; x-force orientation and COM torque held according to the selected kinematic model','bound':'|delta_x| <= (alpha*|Fx(q-only)|+|beta|*Vmax)/(1-alpha*Lx)','no_bound_if_condition_missing':True,'gradient_contraction_threshold_N_m':1/alpha,'qualification':'A local derivative at a few points is not a global Lipschitz supremum; interval invariance also must be checked.'},
      'actual_force_voltage_gradient_bounds':{'Fmax_N':None,'Vmax_V':None,'Lx_N_m':None},
      'negligible_claim':False,'second_axial_DOF_needed':'undecided until actual force/voltage/gradient bounds and required accuracy are supplied; static condensation itself does not validate dynamics',
      'remaining_truncations':['discarded bending shapes','nonlinear beam and axial geometry','axial inertia','voltage-dependent magnetic potential if pose depends on V','full tensor and material dispersion'],
      'checks':{'primitive_volume_energy_cases':checks,'charge_voltage_derivative_abs_error_C':abs(Q-expectedQ),'invalid_bound_cases_rejected':3,'noncontractive_gradient_cases_rejected':3},
      'new_dynamic_runs':0,'new_magnetic_evaluations':0,'dynamic_admitted':False,
    }
    (ROOT/'AXIAL-SENSITIVITY.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({'alpha_m_per_N':alpha,'beta_m_per_V':beta,'checks_passed':True,'new_dynamic_runs':0},indent=2))

if __name__=='__main__':main()
