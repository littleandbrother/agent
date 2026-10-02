# Conditional PSI-5A4E beam ROM, static candidate v1

## Result and status

This package derives a new one-term Rayleigh–Ritz Euler–Bernoulli development model from the geometry in the source-hashed `DoorBeam.java`. It is **not** a COMSOL reproduction, identification of the installed material, physical qualification, dynamic trajectory, or feasible mission witness. The native PZT tensor remains unknown. The provider deliberately refuses dynamic export.

Conditional canonical coefficients (SI):

| Quantity | Value |
|---|---:|
| Patch neutral axis above copper midplane | 0.08866468843 mm |
| Bare / patched EI | 0.01364705833 / 0.03628703637 N m² |
| k | 87.16295936 N/m |
| Generalized mass | 0.008693494537 kg |
| theta, for the declared polarity | −0.0002555732650 C/m |
| Cp, fixed single Ritz coordinate with axial relaxation | 18.75197361 nF |
| Single-term short-circuit Rayleigh frequency | 15.93635231 Hz |
| Single-term open-circuit Rayleigh frequency | 16.25166073 Hz |

These digits support reproducibility, not physical precision.

## 1. Provenance and constitutive primitives

Geometry source: `DoorBeam.java`, SHA-256 `85e7749eb5319b75cc81b5d57f14844ce6ce4e24dea63aad5867938447dc5be6`. Its native material assignment imports `lead_zirconate_titanate_(pzt-5a)` from a local COMSOL library. That library and complete tensor are absent; this package does not fill or claim to recover them.

The **new conditional branch** instead selects four primitive properties for the single named manufacturer material PSI-5A4E:

- Y1 at constant electric field: 66 GPa, perpendicular to thickness poling
- d31: −190 pC/N = −190 pm/V
- Relative epsilon33 at constant stress: 1800, listed at 1 kHz
- Density: 7800 kg/m³

Primary evidence: [current manufacturer material page](https://piezo.com/pages/piezo-material), and Piezo Systems' manufacturer-authored [Catalog #7C (2008), page 24](https://cdn.thomasnet.com/ccp/00979620/121657.pdf#page=24), hosted by ThomasNet. The page was rendered and visually checked, and agrees with the current official table. The full PDF, HTML snapshot, extraction and rendered page are retained under `sources/`. ThomasNet is the archival host, not a claim that its URL is the manufacturer's current domain.

The table describes guidelines, not a jointly certified tensor or guaranteed tolerances. Using these primitives gives sqrt(Y1*d31²/epsilon33T)=0.38664727, while the same table separately lists k31=0.35. We retain the four selected primitives, expose this 10.47% discrepancy, and do not impose k31 as a fifth inconsistent equation. The commercial sheet thicknesses and their capacitance tolerances do not establish tolerances for the source's custom 0.300 mm geometry. The current official PDF labelled 3195STD/3195HD gives different material values and is **not** mixed into this PSI branch.

Epsilon0=8.8541878188e−12 F/m is the [2022 CODATA value at NIST](https://www.physics.nist.gov/cgi-bin/cuu/Value?eqep0=). Its uncertainty is negligible relative to the unresolved material/model uncertainty, but it is not an exact SI constant.

Copper E=110 GPa and rho=8960 kg/m³, magnet rho=7500 kg/m³, and all dimensions are inherited **source assumptions**, not measurements. Source magnet E=160 GPa is recorded but not used by the rigid-body idealization. Source Poisson ratios are not used by this uniaxial plane-stress reduction. Manufacturer ceramic Qm=80 is not equated to assembled-beam damping; damping remains null.

The model extrapolates the tabulated dielectric value from 1 kHz to a quasistatic/fundamental-mode approximation without verified dielectric dispersion, loss, amplitude or temperature dependence. This is a declared conditional material assumption, not a material qualification.

## 2. Geometry, electrodes, and coordinate

Use a right-handed beam frame: x along the copper length, z the positive transverse displacement, and y completing the triad. Local x = DoorBeam global x − 4 mm; z retains the source origin at the copper midplane.

| Part | x extent | y extent | z extent |
|---|---|---|---|
| Copper | 0 to 96 mm | −5 to +5 mm | −0.265 to +0.265 mm |
| PZT | 6 to 56 mm | −4 to +4 mm | +0.265 to +0.565 mm |
| Magnet | 91 to 101 mm | −5 to +5 mm | +0.265 to +10.265 mm |

The copper is clamped at x=0. The top and bottom PZT electrode faces cover the complete 50×8 mm patch, as intended by the source selections. The modeled area is 4e−4 m² and separation 3e−4 m. These are ideal equipotential, zero-mass electrodes with no fringe, wire, leakage or parasitic capacitance. Source selection code is not evidence that a native geometry selection actually executed successfully.

The canonical boundary idealization makes the magnet and copper overlap x=91..96 mm rigid. Elastic flexure ends at a=91 mm. The rigid body extends to x=101 mm and its COM is xg=96 mm, zg=5.265 mm. Generalized q is vertical COM displacement, equal to the mean displacement of the source's uniformly loaded top magnet face at first order. Thus phi(xg)=1 and a uniform transverse force on that face has resultant at xg, with a 5 mm lever arm about a.

A separately identified sensitivity branch permits copper flexure to a=96 mm, with a point attachment at the magnet centroid. It is not the same bonded-overlap boundary and cannot silently replace it.

## 3. Reduced material equations and laminate neutral axis

Adopt a uniaxial, transverse-stress-free piezo reduction, not a full 3D tensor reconstruction:

S1 = s11E T1 + d31 E3

D3 = d31 T1 + epsilon33T E3

Y=1/s11E; e=Y*d31; epsilon_bar=epsilon33T−Y*d31².

Then T1=Y*S1−e*E3 and D3=e*S1+epsilon_bar*E3. Epsilon_bar is constrained only in the longitudinal strain S1 while other stresses are zero. It is **not** the fully strain-clamped tensor epsilon33S. It is positive for the selected primitives.

Let u0 be axial displacement at z=0, kappa=w'', and S1=u0'−z*kappa. Define section quantities A=sum(Ei Ai), B=sum(Ei Ai zi), D=sum(Ei[Ii+Ai zi²]). Enforcing zero axial resultant N gives zN=B/A and EI=D−B²/A, equivalently sum(Ei[Ii+Ai(zi−zN)²]). The neutral axis is stiffness weighted, not the geometric centroid.

Positive polarization is assumed along +z. Voltage v=Vtop−Vbottom, hence E3=−v/tp. For the patch,

u0' = zN*kappa − (e*bp/A)*v.

Substitution in electric enthalpy gives per unit beam length:

H' = (EI/2)*kappa² − g*kappa*v − (cN/2)*v²,

g=e*bp*(zp−zN),

cN=(bp/tp)*(epsilon33T−Y*d31²)+(e*bp)²/A.

The positive axial-relaxation term in cN is essential. Neither epsilon33T alone nor a fully clamped tensor value can be inserted as Cp while retaining this same reduction without changing the model.

The assumed electric potential is linear across thickness. Because bending strain varies with z, pointwise D3 from that assumption is not uniform. Generalized terminal charge is derived from −dH/dv, equivalently −bp times the thickness-averaged D3 integrated over x. Evaluating D3 only at the top strained fiber while retaining uniform E would break reciprocity. A pointwise Gauss-law-resolved electric field, fringing field or 3D lateral constraint requires a different model.

## 4. One-term shape, stiffness, and modal mass

The shape is the exact static flexural response to a unit transverse resultant at xg, within the declared piecewise-EI/rigid-end model. It is a one-term admissible Ritz basis, not a claimed exact first eigenmode.

J = integral(0..a) (xg−x)²/EI(x) dx; k=1/J.

phi''(x)=k*(xg−x)/EI(x), with phi(0)=phi'(0)=0.

For x>a, phi(x)=phi(a)+(x−a)*phi'(a). The normalization phi(xg)=1 follows from the same compliance integral. Check k=integral EI*phi''² dx. Each flexible segment has an exact cubic polynomial; mass is integrated analytically. An independent implementation uses separate closed-form shape evaluation and Gaussian quadrature.

For short-circuit modal kinematics, u0q(x)=integral(0..x) zN(t)*phi''(t) dt. The magnet's axial COM shape is psi_g=u0q(a)−zg*phi'(a). With pitch about +y equal to −phi'(a)*q,

m = integral copper+PZT rho*A*phi² dx + mg*(1+psi_g²) + Jyy*phi'(a)².

The overlap copper's transverse mass is included while moving rigidly. Magnet mg=7.5 g; Jyy=mg*(length²+height²)/12=1.25e−7 kg m² about its COM. No parallel-axis inertia is added a second time: COM translation plus centroidal rotation already account for it.

Mass terms:
- Beam transverse: 1.104847337 g
- Magnet vertical translation: 7.500000000 g
- Magnet eccentric axial translation: 0.055026119 g
- Magnet centroidal pitch: 0.033621081 g

The omitted beam axial/rotary contribution computed with the same displacement field is 2.3965043e−8 kg, about 2.76 ppm of retained mass. This numerical smallness does not bound other model errors. Voltage-induced axial relaxation is statically condensed and its inertia is omitted; a higher-order dynamic reduction could introduce additional frequency dependence and mixed inertial terms. Adhesive/electrode mass is unknown, not measured zero.

## 5. Piezo charge, capacitance, and reciprocity

Set w=q*phi. Then theta=integral_patch g*phi'' dx = g*[phi'(xe)−phi'(xp)] and Cp_Ritz=integral_patch cN dx.

H(q,v)=k*q²/2−theta*q*v−Cp_Ritz*v²/2.

F=k*q−theta*v; Q=theta*q+Cp_Ritz*v.

Therefore dq/dv at zero applied transverse force and dQ/dF at v=0 both equal theta/k=−2.932131571 micrometres/volt = −2.932131571 microcoulombs/newton. Opposite poling flips theta without changing k,m,Cp. Charge is top-electrode supplied charge, not an automatically chosen rectifier current sign.

The reciprocal dynamic form, if later separately admitted, would be m*qddot+k*q−theta*v=Fext and Qdot=theta*qdot+Cp*vdot; the energy is 0.5*m*qdot²+0.5*k*q²+0.5*Cp*v², with external powers Fext*qdot+v*Qdot. In charge coordinates its potential is 0.5*k*q²+(Q−theta*q)²/(2*Cp), which is positive. This equation is documentation, not an authorized dynamic solve. Any circuit adapter must preserve the stated current direction and count Cp once.

### Capacitance is boundary-condition dependent

- Fixed longitudinal strain, other stresses free: 18.0732507651 nF
- Axially relaxed, fixed single Ritz q: Cp_Ritz=18.7519736138 nF
- Single Ritz mode, force-free: Cp_Ritz+theta²/k=19.5013480529 nF
- Fully relaxed *static EB bending* continuum: Cp_Ritz+integral(g²/EI) dx=20.2287736380 nF
- Continuum with endpoint q fixed, other static bending coordinates condensed: 19.4793991989 nF
- Entire material stress-free parallel-plate value: 21.2500507651 nF

The endpoint-static Schur capacitance exceeds the one-term Cp by 3.8792%. Its difference is relaxation in discarded bending coordinates. It cannot be substituted into a one-term dynamic model as a cost-free exact refinement: dynamic shape/inertia consequences need examination. One-term SC/OC frequencies are reported for the single basis and Cp_Ritz only.

## 6. Force pose and virtual work: integration remains blocked

The retained mode does not move the magnet only transversely. The exposed conditional kinematic map is

r_COM(q) = [xg+psi_g*q, 0, zg+q],

R(q)=Ry(−phi'(a)*q),

dr/dq=[psi_g,0,1]; angular velocity per qdot=[0,−phi'(a),0].

The COM path is the first-order beam kinematics. Evaluating its rotation as a proper rotation matrix does not turn it into nonlinear elastica. Force and torque must both be expressed in the same right-handed beam frame, with torque about COM. Then

Qmag = Fz + psi_g*Fx − phi'(a)*tau_y = −dU_magnetic(r(q),R(q))/dq.

`pose_and_jacobian` and `project_force` expose this contract. A synthetic analytic potential with translational, rotational and cross terms passes a centered finite-difference check against the force-plus-torque projection. That checks the chain rule and signs; it does not qualify a magnetic force model.

At inherited |q|=8 mm, this linear shape predicts magnet pitch 0.13120 rad (~7.52 degrees) and axial COM displacement 0.68524 mm. Ignoring those effects is not an identity and cannot be justified by an unquantified 'small' label. Existing force tables that translate a fixed-orientation magnet and retain only transverse force are **not automatically compatible**. New q-dependent pose/torque samples or an explicitly reviewed neglect approximation are required. Beam-to-world frame registration must be pinned, including moment signs, before integration. Existing 48 mm installation, 65-degree door motion, and 2/4 s times are neither changed nor used in a trajectory here.

## 7. Sensitivity and limits

`outputs/sensitivity.json` records:
- Two mechanically explicit overlap branches and a sampled envelope within that idealized family, not real-device bounds
- Boundary-condition capacitance differences
- Point-mass inertia omission and beam axial/rotary diagnostic
- Local dimensionless parameter elasticities, with finite-difference half-step consistency; derivative steps are numerical probes, not claimed manufacturing ranges
- Unknown damping and unknown actual material/assembly tolerances

The rigid-versus-flexible-overlap change in k is only about −0.0266%, because the newly compliant distal 5 mm carries a small moment. That observation does not validate perfect bonding or the clamp. Using a pure point mass instead omits about 1.02% of the generalized mass. Replacing Cp_Ritz by stress-free material capacitance overstates it by about 13.32%.

No defensible physical confidence interval can be assigned without actual grade and lot properties, dimensions/tolerances, electrode/bond details, clamp compliance, damping/loss data and nonlinear qualification. The inherited ±8 mm limit is a previous exploratory support, not a safety or accuracy bound. Maximum predicted linear fiber strain at that limit is reported only as a diagnostic; no strength/yield claim follows.

## 8. Verification and missing evidence

26 local static tests cover source binding, geometry/order/units, sign and polarity, exact normalization, section and interface conditions, mass bookkeeping, independent primitive-volume enthalpy quadrature, reciprocity/passivity, open/short relations, capacitance ordering, length scaling, proper pose matrices, magnetic virtual-work chain rule, absent/nonfinite/nonpassive inputs and rejection of dynamic export. Independent closed-form/quadrature output agrees with the provider to floating-point roundoff. This is algebra/numerical verification of a declared model, not validation of nature.

The upstream full init suite was not run by this package: no active repository feature was modified and no repository-health claim is made. No licensed software, account agreement, paid model call, commit, push, prior fixture ROM, old cloud ROM or new dynamic trace was used.

Remaining inputs/gates:
1. Review and explicit acceptance of the new material/boundary/Ritz assumptions as a separately versioned development provider
2. Force kinematics and torque/axial virtual work consistent with its q; frame registration and applicable force domain
3. Choice between one-term and higher static/dynamic mechanical reduction, with charge/current and Cp conventions kept consistent
4. Explicit damping/loss model if any dynamic screening is later considered
5. Independent dynamic PMIC model/port/auxiliary-store evidence, initialization and energy ledger; this package supplies none
6. Actual native PZT tensor and native solver evidence for any native-equivalence claim
7. Actual physical material, geometry, bond/electrode/clamp and validity evidence for physical claims

The useful outcome is a transparent, testable conditional static branch and a precise integration blocker. No four-cell run is admitted by this deliverable.
