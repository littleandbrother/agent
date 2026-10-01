"""Create the initial protocol before any dynamic trajectory; never reseal silently."""
from pathlib import Path
import hashlib,json,platform,sys
import numpy,scipy,scipy.integrate._ivp.radau as radau
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    p=ROOT/p
    if p.exists():raise RuntimeError('refuse overwrite '+str(p))
    p.write_text(json.dumps(v,indent=2)+'\n')
source_manifest={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'sources').rglob('*')) if p.is_file() and '__pycache__' not in str(p)}
write('SOURCE-MANIFEST.json',source_manifest)
eq=json.loads((ROOT/'outputs/EQUILIBRIUM-PREFLIGHT.json').read_text())
rom=json.loads((ROOT/'sources/magnetic/sources/beam-static-rom.json').read_text())
plan={
 'schema':'bf-conditional-passive-study-plan-v1',
 'model_version':'bf-conditional-qonly-passive-bridge-storage-v1',
 'purpose':'Matched 47-versus-10 microfarad input-storage sensitivity on one explicitly assumed q-only conditional source model',
 'claim_boundary':'No native equivalence, PMIC, firmware, receiver, task/mission, robustness, physical safety, hardware feasibility or Agent efficacy claim',
 'dynamic_trajectories_max':4,
 'cases':[{'id':'cin47','cin_F':47e-6},{'id':'cin10','cin_F':10e-6}],
 'execution_order':['cin47-coarse','cin47-fine','cin10-coarse','cin10-fine'],
 'mechanics':{key:rom[key] for key in ['k_N_m','mass_kg','theta_C_m','Cp_ritz_F','magnet_pitch_slope_per_m','magnet_axial_shape']},
 'damping_ratio':.02,
 'damping_provenance':'Inherited uncalibrated development assumption from source world; c=2*zeta*sqrt(m*k), not inferred from ceramic Qm',
 'rectifier':{'type':'ideal full-wave bridge plus fixed series resistor and otherwise ideal storage capacitor',
  'series_resistance_ohm':100000.,'choice':'Explicit round-number passive benchmark assumption selected before trajectories, not measured ESR and not a fitted/optimized/native diode or PMIC model',
  'law':'I=max(abs(Vp)-Vs,0)/R; terminal outward i=sign(Vp)*I; Qdot=-i; Cin*Vsdot=I',
  'reverse_leakage_A':0.,'forward_voltage_drop_V':0.,'load_current_A':0.,'external_electrical_work_J':0.,
  'power_identity':'Vp*i = Vs*I + R*I^2 >=0 for Vs>=0; ideal diode loss=0',
  'upper_bound_on_real_harvester':False},
 'signed_port':{'q':'positive world +y, beam +z','Vpiezo':'top electrode minus bottom electrode','Q':'top-electrode supplied charge','equations':'Vp=(Q-theta*q)/Cp_Ritz; m*qdd=Fmag-c*qdot-k*q+theta*Vp','Cp_count':1},
 'initial_state':{key:eq[key] for key in ['q0_m','qdot0_m_s','Q0_C','Vpiezo0_V','Vstorage0_V','initial_elastic_J','initial_mutual_magnetic_J','initial_piezo_J','initial_storage_J','initial_kinetic_J']},
 'initial_recipe':'Same retained stable closed-door root for all four trajectories, selected by STATIC-PREFLIGHT-PLAN; Q0=theta*q0 makes physical Vpiezo=0; signed electrode charge is not an electrical precharge',
 'initial_preparation':'Computational initial equilibrium only; initial elastic and signed mutual potential are accounted; preparation/reset work remains unknown and no first-operation/reset qualification is claimed',
 'magnetic_potential_gauge':'Mutual potential tends to zero at infinite separation; initial Umag is signed, and adding a constant does not change equations or ledger gates',
 'driver_input':{'angle_profile':'linear from 0 to 65deg over 0..2s; hold 2..4s','opening_angle_rad':1.1344640137963142,'opening_s':2.,'observation_s':4.,'gap_m':.048,'break_handling':'two continuous-state integration segments meet exactly at 2s; one-sided driver powers retained'},
 'ledger':{'stored':'0.5*m*qdot^2+0.5*k*q^2+(Q-theta*q)^2/(2*Cp)+0.5*Cin*Vs^2+Umag',
  'driver_translation':'Ptrans=Ftip dot (d rdriver/d angle)*angle_dot',
  'driver_rotation':'Prot=-tau_driver_COM_y*angle_dot',
  'driver_derivative':'d rdriver/d angle=e_y cross (rdriver-pivot_beam); omega_driver=e_y*angle_dot',
  'balance':'E(t)-E(0)+Dmechanical+Dresistor-Wdriver_translation-Wdriver_rotation=0',
  'dissipation':'Dmechanical_dot=c*qdot^2; Dresistor_dot=R*I^2',
  'work_scope':'Work by externally prescribed driver against magnetic forces and torque only; driver-mechanism inertia, actuation friction and reset are outside boundary',
  'normalization':'max(initial nonmagnetic positive storage,abs(Wdriver),abs(Umag(t)-Umag(0)),1e-9 J); invariant to magnetic additive constant'},
 'mechanical_assumptions':['One retained Ritz bending coordinate with fixed mass/stiffness/reciprocal piezo port','Magnetic COM path and pitch are q-only short-circuit kinematics; nonzero-voltage axial shift beta*V and force-induced additional axial shift are omitted','Discarded bending shapes and torque-driven modal content, axial inertia, geometric/material nonlinearity, actual tensor, damping, losses, assembly and installation physics are unqualified','Voltage/domain guards are computational only. No negligibility or physical-accuracy bound on omitted coordinates is claimed'],
 'dynamic_quadrature_order':6,
 'path_quadrature_check':'Direct unchanged finite-cuboid evaluations at n=6 and n=10 at every accepted interval start, midpoint and end, separately from timestep refinement; raw Ftip, tip torque, driver COM torque, driver pose derivative and powers retained. Differences are empirical numerical refinement evidence, not rigorous error bounds or physical validation.',
 'resolutions':{
  'coarse':{'method':'SciPy Radau','max_step_s':.002,'first_step_s':1e-5,'rtol':1e-6,'atol':[1e-10,1e-8,1e-14,1e-8,1e-12,1e-12,1e-12,1e-12]},
  'fine':{'method':'SciPy Radau','max_step_s':.001,'first_step_s':5e-6,'rtol':2.5e-7,'atol':[2.5e-11,2.5e-9,2.5e-15,2.5e-9,2.5e-13,2.5e-13,2.5e-13,2.5e-13]}},
 'resolution_rationale':'Mechanical period about 62.75ms; R*Cp about 1.875ms. Implicit Radau resolves passive-RC stiffness, adaptive tolerances treat diode corners; exact input break and fixed refinements declared before output. No PMIC source timestep imported.',
 'gates':{'q_limit_m':.008,'storage_negative_tolerance_V':1e-9,'voltage_computational_guard_V':500.,
  'quadrature':{'force_N':[1e-9,1e-4],'potential_J':[1e-11,1e-4],'driver_derivative_J_per_rad':[1e-9,1e-4]},
  'energy_abs_J':1e-9,'energy_relative':.001,'independent_ledger_abs_J':1e-9,'independent_ledger_relative':.005,
  'time_refinement':{'q_m':[1e-6,.005],'Vs_V':[1e-4,.005],'Vp_V':[1e-3,.01],'energy_J':[1e-9,.005]},
  'continuous_numerical_path':'Radau cubic q extrema exactly evaluated. Magnet clearance at interval start minus h*(maximum tip translation/rotation speed + driver translation/rotation speed) must remain >1e-12m. This bounds separation along numerical cubic, not exact ODE path or surrounding assembly.'},
 'budgets':{'wall_per_trajectory_s':420,'rhs_per_trajectory':100000,'force_evaluations_per_trajectory':150000,'accepted_steps_per_trajectory':20000,'total_wall_cap_s':1800,'dynamic_trajectories':4,'software_test_wall_s':30,'software_test_additional_static_states_max':20,'paid_calls':0},
 'stop_conditions':['source or code hash mismatch','missing exact frozen approval','failed static/software preflight','nonfinite/negative passive store/domain/contact or continuous clearance guard','wall/RHS/force/step budget','solver failure','unresolved force quadrature or energy accounting','after one trajectory failure stop branch; no replacement, retry, threshold tuning or new design','after time-refinement failure retain four results but no admitted sensitivity conclusion'],
 'outputs':['raw state samples on common 1ms grid','all accepted states and every Radau cubic coefficient','raw n6/n10 potentials and primitive force/torque/driver-pose derivatives at all accepted endpoints/midpoints','sample powers and ODE-integrated signed translational/rotational driver work','independent Simpson integration of all four work/loss rates','full stored-energy ledger and residuals','domain checks with cubic extrema and magnet-clearance bounds','peak/final q, piezo and storage voltages/energy, budgets, failures, source and code hashes'],
 'interpretation_rule':'Report signed cin10-minus-cin47 differences in final storage energy and peak storage voltage, plus coupled q/piezo/energy partition. Compare each effect against five times sum of observed within-case coarse/fine deltas; below this report numerically unresolved. This is not a confidence/error bound or guarantee against common-mode quadrature/model errors.',
 'source_manifest_sha256':sha(ROOT/'SOURCE-MANIFEST.json'),
 'equilibrium_receipt_sha256':sha(ROOT/'outputs/EQUILIBRIUM-PREFLIGHT.json'),
 'toolchain':{'python':sys.version,'platform':platform.platform(),'numpy':numpy.__version__,'scipy':scipy.__version__,'scipy_radau_source_sha256':sha(radau.__file__)},
 'authorization_status':'Pending independent code/plan review and root approval; creation of this file authorizes no trajectory'}
write('PLAN.json',plan)
