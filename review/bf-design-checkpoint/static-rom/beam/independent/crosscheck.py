#!/usr/bin/env python3
"""Independent static section algebra and polynomial quadrature, SI units.
No native model or time-domain/eigenvalue solve is run.
"""
import hashlib, json, math
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent
SRC=Path('/workspace/shared/current-cache-integration-20261001/working/battery-world/configs/reference_cases/door-magnetic-v1/DoorBeam.java')
eps0=8.8541878188e-12
Ecu=110e9; bcu=.010; tcu=.000530; rhocu=8960
Ep=66e9; bp=.008; tp=.000300; rhop=7800; zp=.000415
d=-190e-12; epsT=1800*eps0
xp0=.006; xp1=.056; Lcu=.096; xg=.096
lm=.010; hm=.010; bm=.010; rhom=7500; zm=.005265
Ac=bcu*tcu; Ap=bp*tp
A0=Ecu*Ac; D0=Ecu*bcu*tcu**3/12
A=A0+Ep*Ap; B=Ep*Ap*zp; D=D0+Ep*(bp*tp**3/12+Ap*zp**2)
zN=B/A; EI=D-B*B/A
P=Ep*d*bp; g=P*(zp-zN)
eps_scalar=epsT-Ep*d*d
c_scalar=bp/tp*eps_scalar
c_axial=P*P/A
cN=c_scalar+c_axial
Cp=cN*(xp1-xp0)
M=rhom*lm*hm*bm; J=M*(lm*lm+hm*hm)/12
# An 8-point Gauss-Legendre rule exactly integrates all piecewise polynomials
# used below in exact arithmetic (highest degree is six). No fit/tolerance.
nodes,weights=np.polynomial.legendre.leggauss(8)
def integ(fn, lo, hi):
    xx=(hi-lo)/2*nodes+(hi+lo)/2
    return (hi-lo)/2*sum(w*fn(float(x)) for x,w in zip(xx,weights))
def solve(a):
    sections=[(0,xp0,D0,0),(xp0,xp1,EI,zN),(xp1,a,D0,0)]
    comp=sum(((xg-l)**3-(xg-r)**3)/(3*rigid) for l,r,rigid,zn in sections)
    k=1/comp
    def base(x, deriv=0):
        ans=0.
        for l,r,rigid,zn in sections:
            r=min(r,x)
            if r<=l: continue
            if deriv==0: ans+=(x*xg*(r-l)-(x+xg)*(r*r-l*l)/2+(r**3-l**3)/3)/rigid
            else: ans+=(xg*(r-l)-(r*r-l*l)/2)/rigid
        return k*ans
    def phipp(x):
        if x>a: return 0.
        return k*(xg-x)/(EI if xp0<x<xp1 else D0)
    def psi(x):
        r=min(x,xp1)
        if r<=xp0:return 0.
        return zN*k*(xg*(r-xp0)-(r*r-xp0*xp0)/2)/EI
    part=[0,xp0,xp1,a,Lcu]
    part=sorted(set(part))
    def integrate_segments(fn):return sum(integ(fn,l,r) for l,r in zip(part,part[1:]))
    # Copper exists throughout 0..96 mm, including its rigid overlap piece.
    mcu_z=integrate_segments(lambda x:rhocu*Ac*base(x)**2)
    mcu_x=integrate_segments(lambda x:rhocu*(Ac*psi(x)**2+bcu*tcu**3/12*base(x,1)**2))
    mp_z=integ(lambda x:rhop*Ap*base(x)**2,xp0,xp1)
    mp_x=integ(lambda x:rhop*(Ap*(psi(x)-zp*base(x,1))**2+bp*tp**3/12*base(x,1)**2),xp0,xp1)
    rot=base(a,1); uxM=psi(a)-zm*rot
    mM_z=M*base(xg)**2
    mM_x=M*uxM**2
    mM_pitch=J*rot**2
    mt=mcu_z+mp_z+mM_z
    beam_x_rotary=mcu_x+mp_x
    mass=mt+mM_x+mM_pitch
    mass_with_beam_x_rotary=mass+beam_x_rotary
    mass_no_horizontal_COM=mt+mM_pitch
    mass_centered_z0=mass_no_horizontal_COM+M*psi(a)**2
    theta=g*(base(xp1,1)-base(xp0,1))
    # Independent Gaussian strain-energy and direct coupling check.
    k_integral=sum(integ(lambda x:rigid*phipp(x)**2,l,r) for l,r,rigid,zn in sections)
    theta_integral=integ(lambda x:g*phipp(x),xp0,xp1)
    CfreeROM=Cp+theta**2/k
    CfreeFull=Cp+g*g/EI*(xp1-xp0)
    CfixedQFull=CfreeFull-theta*theta/k
    # These are algebraic Rayleigh estimates, not modal/dynamic executions.
    fsc=math.sqrt(k/mass)/(2*math.pi)
    foc=math.sqrt((k+theta*theta/Cp)/mass)/(2*math.pi)
    # Voltage-dependent axial relaxation is NOT included in the canonical mass.
    chi_tip=-P/A*(xp1-xp0) # u0 / volt from N=0, curvature fixed
    # If v follows open circuit under the one-mode electrical relation,
    # v/q=-theta/Cp; this shows the scale of omitted quasistatic axial kinetic terms.
    v_over_q=-theta/Cp
    uxM_oc=uxM+chi_tip*v_over_q
    mM_x_oc=M*uxM_oc**2
    beam_x_oc=0.
    def chi(x):return -P/A*max(0,min(x,xp1)-xp0)
    beam_x_oc+=integrate_segments(lambda x:rhocu*(Ac*(psi(x)+chi(x)*v_over_q)**2+bcu*tcu**3/12*base(x,1)**2))
    beam_x_oc+=integ(lambda x:rhop*(Ap*(psi(x)+chi(x)*v_over_q-zp*base(x,1))**2+bp*tp**3/12*base(x,1)**2),xp0,xp1)
    mass_oc_shape=mt+mM_pitch+mM_x_oc
    mass_oc_shape_with_beam=mass_oc_shape+beam_x_oc
    return dict(a_m=a, compliance_m_per_N=comp,k_N_per_m=k,k_quadrature_N_per_m=k_integral,normalization=base(xg),
        theta_C_per_m=theta,theta_quadrature_C_per_m=theta_integral,Cp_fixed_shape_F=Cp,
        C_free_ROM_F=CfreeROM,C_free_continuum_F=CfreeFull,C_fixed_endpoint_continuum_F=CfixedQFull,
        delta_C_ROM_F=theta**2/k,delta_C_continuum_F=g*g/EI*(xp1-xp0),
        mass_kg=mass,mass_with_beam_axial_rotary_kg=mass_with_beam_x_rotary,
        mass_no_horizontal_COM_kg=mass_no_horizontal_COM,mass_magnet_centered_z0_kg=mass_centered_z0,
        omitted_beam_axial_rotary_mass_kg=beam_x_rotary,
        f_short_no_horizontal_COM_Hz=math.sqrt(k/mass_no_horizontal_COM)/(2*math.pi),
        f_short_centered_z0_Hz=math.sqrt(k/mass_centered_z0)/(2*math.pi),
        vertical_mass_only_kg=mt,beam_vertical_mass_kg=mcu_z+mp_z,
        copper_vertical_mass_kg=mcu_z,pzt_vertical_mass_kg=mp_z,
        copper_horizontal_rotary_mass_kg=mcu_x,pzt_horizontal_rotary_mass_kg=mp_x,
        magnet_vertical_mass_kg=mM_z,magnet_horizontal_mass_kg=mM_x,magnet_pitch_mass_kg=mM_pitch,
        magnet_slope_per_q_per_m=rot,magnet_u0_per_q=psi(a),magnet_uxCOM_per_q=uxM,
        magnet_pitch_J_kg_m2=J,magnet_COM_z_m=zm,
        f_short_Hz=fsc,f_open_Hz=foc,open_stiffness_N_per_m=k+theta*theta/Cp,
        f_short_vertical_mass_only_Hz=math.sqrt(k/mt)/(2*math.pi),
        static_q_per_v_m_per_V=theta/k,static_topQ_per_force_C_per_N=theta/k,
        scalar_q_at_0p3N_m=.3/k,
        chi_tip_m_per_V=chi_tip,voltage_dependent_axial_mass_sensitivity_kg=mass_oc_shape,
        voltage_dependent_axial_mass_with_beam_sensitivity_kg=mass_oc_shape_with_beam,
        voltage_dependent_axial_f_open_sensitivity_Hz=math.sqrt((k+theta*theta/Cp)/mass_oc_shape)/(2*math.pi))

results={'source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),
 'material_source_url':'https://piezo.com/pages/piezo-material',
 'material_identity':'Conditional PSI-5A4E assumption only; native imported COMSOL PZT tensor unknown.',
 'section':dict(A_N=A,B_N_m=B,D_N_m2=D,zN_m=zN,EI_patched_N_m2=EI,EI_copper_N_m2=D0,
   P_N_per_V=P,g_C=g,epsT_F_per_m=epsT,eps_fixed_S1_F_per_m=eps_scalar,
   c_scalar_F_per_m=c_scalar,c_axial_relaxation_F_per_m=c_axial,cN_F_per_m=cN,
   Cp_fixed_shape_F=Cp,Cp_using_epsilonT_F=bp/tp*epsT*(xp1-xp0),
   full_physical_mass_kg=rhocu*Ac*Lcu+rhop*Ap*(xp1-xp0)+M,
   magnet_mass_kg=M,magnet_pitch_J_kg_m2=J),
 'rigid_overlap':solve(.091),'flexible_overlap':solve(.096)}
(OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
