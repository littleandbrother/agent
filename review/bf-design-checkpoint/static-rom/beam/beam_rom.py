"""Static-only, source-traceable conditional one-term beam model; no ODE solver.

All lengths are SI. phi is dimensionless and q is the magnet COM vertical
displacement in metres. This is not COMSOL output or a calibrated device model.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from numpy.polynomial import Polynomial as P

ROOT = Path(__file__).resolve().parent
VERSION = "bf-conditional-psi5a4e-beam-ritz-v1"
UNITS = {
    "copper_length": "m", "copper_width": "m", "copper_thickness": "m",
    "pzt_start": "m", "pzt_end": "m", "pzt_width": "m", "pzt_thickness": "m",
    "magnet_start": "m", "magnet_end": "m", "magnet_width": "m", "magnet_height": "m",
    "copper_young": "Pa", "copper_density": "kg/m^3",
    "pzt_young_E1": "Pa", "pzt_density": "kg/m^3", "pzt_d31": "C/N",
    "pzt_epsilon_T33_relative": "1", "epsilon0": "F/m", "magnet_density": "kg/m^3",
    "poling_sign": "1", "rigid_attachment_start": "m",
}

def load_inputs(path=ROOT / "parameters.json"):
    data = json.loads(Path(path).read_text())
    if data.get("schema") != "bf-conditional-beam-input-v1":
        raise ValueError("unsupported parameter schema")
    entries = data["parameters"]
    if set(entries) != set(UNITS):
        raise ValueError("unknown or missing parameters")
    result = {}
    for key, unit in UNITS.items():
        item = entries[key]
        if item.get("unit") != unit:
            raise ValueError("unit mismatch: " + key)
        if not item.get("provenance_id"):
            raise ValueError("missing provenance: " + key)
        val = item.get("value")
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
            raise ValueError("nonfinite/missing numeric input: " + key)
        result[key] = val
    validate(result)
    return result

def validate(p):
    for key in UNITS:
        if key not in p or isinstance(p[key], bool) or not math.isfinite(p[key]):
            raise ValueError("missing/nonfinite parameter: " + key)
        if key not in {"pzt_d31", "poling_sign"} and p[key] <= 0:
            raise ValueError("nonpositive parameter: " + key)
    if p["poling_sign"] not in (-1, 1):
        raise ValueError("poling sign must be +1 or -1")
    if not 0 < p["pzt_start"] < p["pzt_end"] < p["magnet_start"] <= p["rigid_attachment_start"] <= p["copper_length"] < p["magnet_end"]:
        raise ValueError("unsupported geometry ordering")
    if p["pzt_width"] > p["copper_width"]:
        raise ValueError("patch wider than substrate")
    if p["rigid_attachment_start"] > (p["magnet_start"] + p["magnet_end"]) / 2:
        raise ValueError("force centroid behind attachment")
    eps = p["epsilon0"] * p["pzt_epsilon_T33_relative"]
    if eps - p["pzt_young_E1"] * p["pzt_d31"] ** 2 <= 0:
        raise ValueError("non-passive scalar constitutive set")

def integral(poly, length):
    anti = poly.integ()
    return float(anti(length) - anti(0))

def derive(p):
    """Analytic polynomial integration. Returns JSON-safe scalars and shapes."""
    validate(p)
    bc, tc, L = (p[k] for k in ("copper_width", "copper_thickness", "copper_length"))
    bp, tp, xp, xe = (p[k] for k in ("pzt_width", "pzt_thickness", "pzt_start", "pzt_end"))
    Ec, Ep = p["copper_young"], p["pzt_young_E1"]
    ac, ap = bc * tc, bp * tp
    zp = (tc + tp) / 2
    A = Ec * ac + Ep * ap
    zN = Ep * ap * zp / A
    EI0 = Ec * bc * tc**3 / 12
    EI1 = Ec * (bc * tc**3 / 12 + ac * zN**2) + Ep * (bp * tp**3 / 12 + ap * (zp-zN)**2)
    epsT = p["epsilon0"] * p["pzt_epsilon_T33_relative"]
    d = p["pzt_d31"] * p["poling_sign"]
    e = Ep * d
    epsS1 = epsT - Ep * d*d
    cN = bp / tp * epsS1 + (e * bp)**2 / A
    g = e * bp * (zp-zN)
    xg = (p["magnet_start"] + p["magnet_end"]) / 2
    a = p["rigid_attachment_start"]
    spans = [(0., xp, EI0, 0., ac*p["copper_density"]),
             (xp, xe, EI1, zN, ac*p["copper_density"]+ap*p["pzt_density"]),
             (xe, a, EI0, 0., ac*p["copper_density"])]
    compliance = sum(((xg-left)**3 - (xg-right)**3)/(3*EI) for left,right,EI,_,_ in spans)
    k = 1 / compliance
    shapes = []
    w0 = slope0 = u00 = mass_beam = beam_axial_rotary_diagnostic = 0.
    strain_energy_k = slope_patch_start = slope_patch_end = 0.
    for left,right,EI,zn,mu in spans:
        h = right-left
        phi = P([w0, slope0, k*(xg-left)/(2*EI), -k/(6*EI)])
        slope = phi.deriv()
        curvature = phi.deriv(2)
        u0 = P([u00]) + zn*(slope - P([slope0]))
        mass_beam += mu*integral(phi*phi, h)
        # Diagnostic only: longitudinal/rotary kinetic energy for the EB section.
        axial = p["copper_density"]*ac*integral(u0*u0 + slope*slope*(tc*tc/12), h)
        if left == xp:
            axial += p["pzt_density"]*ap*integral((u0-zp*slope)**2 + slope*slope*(tp*tp/12), h)
            slope_patch_start, slope_patch_end = float(slope(0)), float(slope(h))
        beam_axial_rotary_diagnostic += axial
        strain_energy_k += EI*integral(curvature*curvature, h)
        shapes.append({"x_start_m":left,"x_end_m":right,"phi_coefficients_in_local_x":phi.coef.tolist(),"u0q_coefficients_in_local_x":u0.coef.tolist(),"EI_N_m2":EI,"neutral_axis_z_m":zn})
        w0, slope0, u00 = float(phi(h)), float(slope(h)), float(u0(h))
    if a < L:
        h = L-a
        phi = P([w0,slope0])
        mass_beam += p["copper_density"]*ac*integral(phi*phi,h)
        beam_axial_rotary_diagnostic += p["copper_density"]*ac*(u00*u00+slope0*slope0*tc*tc/12)*h
        shapes.append({"x_start_m":a,"x_end_m":L,"phi_coefficients_in_local_x":phi.coef.tolist(),"u0q_coefficients_in_local_x":[u00],"EI_N_m2":None,"neutral_axis_z_m":0.,"rigid":True})
    phi_g = w0 + (xg-a)*slope0
    mg = p["magnet_density"]*(p["magnet_end"]-p["magnet_start"])*p["magnet_width"]*p["magnet_height"]
    zg = tc/2 + p["magnet_height"]/2
    Jyy = mg*((p["magnet_end"]-p["magnet_start"])**2 + p["magnet_height"]**2)/12
    psi_g = u00-zg*slope0
    mass_vertical = mg*phi_g**2
    mass_axial = mg*psi_g**2
    mass_rotation = Jyy*slope0**2
    mass = mass_beam+mass_vertical+mass_axial+mass_rotation
    theta = g*(slope_patch_end-slope_patch_start)
    cp = cN*(xe-xp)
    free_ritz = cp+theta*theta/k
    free_continuum = cp+g*g/EI1*(xe-xp)
    cp_static_condensed = free_continuum-theta*theta/k
    q_audit = .008  # inherited exploratory support, NOT a qualified domain
    max_strain = 0.
    for sh in shapes:
        if sh.get("rigid"):
            continue
        curv = P(sh["phi_coefficients_in_local_x"]).deriv(2)
        max_curv = max(abs(curv(0)),abs(curv(sh["x_end_m"]-sh["x_start_m"])))
        fibers = [-tc/2,tc/2]
        if sh["x_start_m"] == xp:
            fibers.append(tc/2+tp)
        max_strain=max(max_strain,q_audit*max_curv*max(abs(z-sh["neutral_axis_z_m"]) for z in fibers))
    return {
        "provider_version":VERSION,
        "status":"conditional_static_candidate_not_dynamic_admitted",
        "native_equivalent":False,"physical_qualified":False,"new_dynamic_runs":0,
        "rigid_attachment_start_m":a,"magnet_center_x_m":xg,
        "neutral_axis_patch_z_m":zN,"patch_axial_rigidity_N":A,
        "EI_bare_N_m2":EI0,"EI_patch_N_m2":EI1,
        "pzt_e31_scalar_C_m2":e,"pzt_epsilon_T33_F_m":epsT,
        "pzt_epsilon_S1_Tother0_F_m":epsS1,
        "cN_F_m":cN,"bending_voltage_coefficient_C":g,
        "k_N_m":k,"mass_kg":mass,"theta_C_m":theta,"Cp_ritz_F":cp,
        "Cfree_ritz_F":free_ritz,"Cfree_continuum_static_F":free_continuum,
        "Cp_static_q_condensed_F":cp_static_condensed,
        "Cp_scalar_S1_fixed_Tother0_F":bp*(xe-xp)/tp*epsS1,
        "Cp_free_material_T_fixed_F":bp*(xe-xp)/tp*epsT,
        "f_SC_ritz_Hz":math.sqrt(k/mass)/(2*math.pi),
        "f_OC_ritz_Hz":math.sqrt((k+theta*theta/cp)/mass)/(2*math.pi),
        "voltage_actuation_q_m_per_V":theta/k,
        "short_circuit_charge_C_per_N":theta/k,
        "magnet_mass_kg":mg,"magnet_centroid_Jyy_kg_m2":Jyy,
        "mass_terms_kg":{"beam_transverse":mass_beam,"magnet_vertical":mass_vertical,"magnet_axial_eccentric":mass_axial,"magnet_centroid_pitch":mass_rotation},
        "omitted_beam_axial_rotary_mass_diagnostic_kg":beam_axial_rotary_diagnostic,
        "magnet_pitch_slope_per_m":slope0,"magnet_axial_shape":psi_g,
        "phi_magnet_center":phi_g,"k_from_strain_energy_N_m":strain_energy_k,
        "material_k31_from_selected_primitives":math.sqrt(Ep*d*d/epsT),
        "material_k31_published_but_not_used":.35,
        "inherited_support_diagnostic_only":{"abs_q_m":q_audit,"magnet_pitch_abs_rad":q_audit*abs(slope0),"magnet_axial_displacement_abs_m":q_audit*abs(psi_g),"max_linear_fiber_strain_magnitude_at_V0":max_strain,"physical_validity":"unknown"},
        "shapes":shapes,
        "unknowns":{"damping_ratio":None,"actual_PZT_grade":None,"native_COMSOL_tensor":None,"adhesive_geometry_and_moduli":None,"electrode_mass":None,"qualified_q_voltage_domain":None},
        "force_compatibility":{"generalized_force":"Fz + psi_g*Fx - phi_prime_a*tau_y (beam-frame signs)","existing_transverse_fixed_tip_force_table":"not_automatically_compatible","must_resolve":"q-dependent tip orientation and axial translation, torque and consistent virtual work or explicit reviewed neglect assumption"},
    }

def enthalpy(rom, q_m, voltage_V):
    return .5*rom["k_N_m"]*q_m*q_m-rom["theta_C_m"]*q_m*voltage_V-.5*rom["Cp_ritz_F"]*voltage_V*voltage_V

def static_port(rom, q_m, voltage_V):
    if not all(math.isfinite(x) for x in (q_m, voltage_V)):
        raise ValueError("nonfinite port input")
    return {"force_N":rom["k_N_m"]*q_m-rom["theta_C_m"]*voltage_V,
            "charge_C":rom["theta_C_m"]*q_m+rom["Cp_ritz_F"]*voltage_V}

def dynamic_export(*args, **kwargs):
    raise RuntimeError("Static-only candidate: no dynamic adapter admitted; damping, force kinematics and reviewer authorization unresolved")

def pose_and_jacobian(rom, q_m, magnet_center_z_m):
    """Beam-frame small-deflection COM path and proper rotation about +y.

    This is an exposed conditional kinematic contract, not a force lookup.
    Rotation is evaluated as exp(skew(-phi_prime*q*ey)); COM translation is
    the retained first-order Ritz path. A nonlinear elastica would differ.
    """
    if not all(math.isfinite(x) for x in (q_m, magnet_center_z_m)):
        raise ValueError("nonfinite pose")
    slope=rom["magnet_pitch_slope_per_m"]
    psi=rom["magnet_axial_shape"]
    beta=-slope*q_m
    c,s=math.cos(beta),math.sin(beta)
    return {"frame":"right-handed beam: x length, z positive q, y completes triad",
            "center_m":[rom["magnet_center_x_m"]+psi*q_m,0.,magnet_center_z_m+q_m],
            "rotation_from_reference":[[c,0.,s],[0.,1.,0.],[-s,0.,c]],
            "pitch_about_positive_y_rad":beta,
            "dcenter_dq":[psi,0.,1.],"angular_velocity_per_qdot":[0.,-slope,0.]}

def project_force(rom, force_xyz_N, torque_about_COM_xyz_N_m):
    if len(force_xyz_N)!=3 or len(torque_about_COM_xyz_N_m)!=3:
        raise ValueError("force and COM torque need three beam-frame components")
    if not all(math.isfinite(x) for x in [*force_xyz_N,*torque_about_COM_xyz_N_m]):
        raise ValueError("nonfinite force/torque")
    return force_xyz_N[2]+rom["magnet_axial_shape"]*force_xyz_N[0]-rom["magnet_pitch_slope_per_m"]*torque_about_COM_xyz_N_m[1]

def build():
    source=ROOT/"sources"/"DoorBeam.java"
    if hashlib.sha256(source.read_bytes()).hexdigest() != "85e7749eb5319b75cc81b5d57f14844ce6ce4e24dea63aad5867938447dc5be6":
        raise ValueError("geometry source hash mismatch")
    provenance=json.loads((ROOT/'provenance.json').read_text())
    for item in provenance['sources']:
        if 'path' in item and hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError("provenance source hash mismatch: "+item['id'])
    p=load_inputs()
    result=derive(p)
    canonical=json.dumps(p,sort_keys=True,separators=(",",":"))
    result["parameter_values_sha256"]=hashlib.sha256(canonical.encode()).hexdigest()
    result["input_bindings_sha256"]={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'parameters.json',ROOT/'provenance.json',ROOT/'beam_rom.py',source]}
    return result

if __name__=="__main__":
    print(json.dumps(build(),indent=2,allow_nan=False))
