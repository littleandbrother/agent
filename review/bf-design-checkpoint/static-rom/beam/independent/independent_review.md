# Independent section-algebra and static-shape crosscheck

## Result and scope

For the conditional PSI-5A4E scalar model and rigid-overlap idealization, the independent calculation gives

- k = 87.1629593634 N/m
- m = 0.00869349453683 kg (beam transverse inertia plus complete magnet rigid-body inertia as defined below)
- theta = −2.55573265001e−4 C/m = N/V
- Cp_Ritz = 18.7519736138 nF
- f_SC = 15.9363523141 Hz and f_OC = 16.2516607341 Hz, algebraically inferred from these coefficients

These are conditional Euler–Bernoulli/assumed-electric-field calculations, not native COMSOL results, measurements, acceptance limits, model equivalence, or dynamic simulations. No damping is assigned. Only static section algebra and a statically chosen trial shape were evaluated. The frequencies are Rayleigh estimates from the stated coefficients.

## Sources and identity limits

DoorBeam.java was read at `/workspace/shared/current-cache-integration-20261001/working/battery-world/configs/reference_cases/door-magnetic-v1/DoorBeam.java`; its SHA256 is `85e7749eb5319b75cc81b5d57f14844ce6ce4e24dea63aad5867938447dc5be6`.

The Java file imports a COMSOL library material named lead_zirconate_titanate_(pzt-5a). It does not reveal that imported native tensor. It must remain unknown here.

The new conditional scalar material uses the manufacturer's PSI-5A4E guideline values: Y1^E = 66 GPa, d31 = −190 pC/N, epsilon33^T/epsilon0 = 1800 (manufacturer specifies 1 kHz), and density = 7800 kg/m³. Source checked 2026-10-01: https://piezo.com/pages/piezo-material . These values do not identify the actual native material or real device. The nominal 1 kHz permittivity is treated as constant in this static model. Vacuum permittivity is pinned to 8.8541878188e−12 F/m, independently checked against NIST CODATA2022: https://www.physics.nist.gov/cgi-bin/cuu/Value?eqep0= .

Copper E = 110 GPa and rho = 8960 kg/m³; magnet rho = 7500 kg/m³, and native-source E = 160 GPa. The latter does not enter the assumed perfectly rigid magnet idealization.

## Coordinates and constitutive conventions

All lengths below are SI unless stated. Local x is global x minus 4 mm. Positive w and q are global +z. PZT poling is +z, v = top potential minus bottom potential, and the assumed thickness field is E3 = −v/tp.

Euler–Bernoulli kinematics: u_x(x,z) = u0(x) − z w′(x), epsilon_x = e0 − z kappa, where e0 = u0′ and kappa = w″.

The scalar stress-charge reduction starts from

S1 = T1/Yp + d31 E3,
D3 = d31 T1 + epsilon33^T E3.

Thus T1 = Yp(S1 − d31 E3) and D3 = Yp d31 S1 + (epsilon33^T − Yp d31²) E3.

The quantity epsilon33^T − Yp d31² fixes only S1 within this scalar, transverse-stress-free description. It is not the full 3D fully-clamped epsilon33^S, which would require the missing tensor. The manufacturer epsilon33^T cannot simply be inserted as the capacitance of a mechanically constrained composite.

An additional electric-field approximation is explicit: under bending, uniform E3 together with the scalar constitutive law produces z-dependent D3. The reciprocal terminal charge of this assumed-field model is obtained by differentiating its electric enthalpy, equivalently using −bp times the thickness-average of D3 integrated along the patch. Evaluating D3 only at the top-fiber strain while maintaining uniform E3 would not be reciprocal. Resolving pointwise Gauss law and the nonuniform thickness field is a different refinement.

## Section condensation

Let Ac = bc tc, Ap = bp tp, and zp = 0.000415 m. On the patched segment, define

A = Ec Ac + Yp Ap,
B = Yp Ap zp,
D = Ec bc tc³/12 + Yp(bp tp³/12 + Ap zp²),
P = Yp d31 bp.

The axial resultant is N = A e0 − B kappa + P v. Setting N = 0 gives

e0 = zN kappa − (P/A)v,
zN = B/A,
EI = D − B²/A.

The condensed section electric enthalpy per unit x is

h_N = (1/2) EI kappa² − g kappa v − (1/2)cN v²,

g = P(zp − zN),
cN = (bp/tp)(epsilon33^T − Yp d31²) + P²/A.

The positive P²/A term is the axial-relaxation contribution and must not be dropped when N = 0 is imposed.

Numerical section data:

| Quantity | Value |
|---|---:|
| A | 741400 N |
| B | 65.736 N m |
| D | 0.0421154983333 N m² |
| zN above copper midplane | 0.0886646884273 mm |
| patched EI | 0.0362870363749 N m² |
| bare copper EI | 0.0136470583333 N m² |
| P | −0.10032 N/V |
| g | −3.27379584570e−5 C |
| epsilon33^T | 1.593753807384e−8 F/m |
| scalar fixed-S1 permittivity | 1.355493807384e−8 F/m |
| fixed-S1 c per length | 3.614650153024e−7 F/m |
| axial-relaxation increment per length | 1.357445697329e−8 F/m |
| cN | 3.750394722757e−7 F/m |

## Trial shape, static reciprocity, and capacitance definitions

Let xg = 0.096 m, with compliant length a = 0.091 m. Let EI(x) take the bare and patched values on [0,0.006], [0.006,0.056], and [0.056,a], respectively. There is no compliant curvature after a.

The unit-force displacement is

f(x) = integral from 0 to min(x,a) of [(x−s)(xg−s)/EI(s)] ds.

Its compliance at the force coordinate is C = f(xg) = integral_0^a [(xg−x)²/EI(x)] dx. Use phi(x)=f(x)/C, so phi(xg)=1, k=1/C, and phi″(x)=k(xg−x)/EI(x) for x<a.

A rigid extension has phi(x)=phi(a)+(x−a)phi′(a). This applies to the copper continuation to x=0.096 m and to the magnet, whose x-centroid and loaded-face x-centroid are xg. Their mean vertical displacement equals q in the infinitesimal rigid-body kinematics; the top-face z-offset does not change the mean vertical displacement or moment of a purely vertical resultant at first order.

The one-term electric enthalpy is H=(1/2)kq²−theta qv−(1/2)Cp_Ritz v², hence

F = kq − theta v,
Q_top = theta q + Cp_Ritz v,
theta = integral_patch g phi″ dx,
Cp_Ritz = integral_patch cN dx.

Negative theta follows from the requested voltage, poling, charge, and displacement signs. In particular q/v at F=0 equals theta/k = −2.93213157134 micrometres/V. Reciprocity gives the same numerical coefficient for Q_top/F at v=0, in C/N.

Four distinct capacitances must be kept separate:

1. Cp_Ritz: fixed q within the one-term shape family; all retained bending motion is fixed
2. Cfree_Ritz = Cp_Ritz + theta²/k: mechanically free within that same one-term shape family
3. Cfree_continuum = Cp_Ritz + integral_patch(g²/EI)dx: all static beam curvatures released in the same scalar section model
4. Cp_condensed = Cfree_continuum − theta²/k: static fixed-endpoint-q capacitance allowing other curvature shapes to relax

The difference Cp_condensed−Cp_Ritz is omitted bending relaxation. Adding it to the one-term Cp while leaving the model otherwise unchanged changes the reduction; it must be identified rather than silently included. Cfree_continuum and q/v are identical for both overlap idealizations here, since their difference lies beyond the active patch.

## Magnet inertia and axial-condensation assumptions

The canonical mass retains beam transverse inertia and magnet rigid-body inertia. At v=0, the axial reference-line shape is

u0q(x) = integral_0^x zN(s) phi″(s) ds.

For a magnet COM at zg = 0.005265 m,

psi_g = u0q(a) − zg phi′(a),
Mmag = 0.0075 kg,
Jyy_COM = Mmag(0.010²+0.010²)/12 = 1.25e−7 kg m²,

m = integral_copper rho_c Ac phi²dx + integral_patch rho_p Ap phi²dx + Mmag[1+psi_g²] + Jyy_COM phi′(a)².

This includes vertical COM translation, horizontal COM translation from pitch about an eccentric attachment plus relaxed axial motion, and central pitch inertia. Using Jyy_COM and the explicit COM translation avoids double counting a parallel-axis term.

For a=0.091 m, phi′(a)=16.4002635734 m^-1, u0q(a)=0.000692172785955, and psi_g=−0.0856552149279.

| Rigid-overlap effective mass contribution | kg |
|---|---:|
| copper transverse | 0.00106247615596454 |
| PZT transverse | 0.0000423711813704881 |
| magnet vertical COM | 0.0075 |
| magnet horizontal COM | 0.0000550261188325368 |
| magnet central pitch | 0.0000336210806595199 |
| canonical total | 0.00869349453682708 |

The full physical unweighted mass is 0.012994848 kg; it is not the modal mass.

Beam horizontal/rotary inertia is omitted in the canonical thin-beam model. Integrating the same assumed kinematics gives a diagnostic omitted contribution of 2.39650429661e−8 kg. Adding it yields 0.00869351850187 kg and f_SC=15.9363303486 Hz.

A simple no-horizontal-COM diagnostic keeps the central pitch inertia but suppresses psi_g²: m=0.00863846841799 kg and f_SC=15.9870281712 Hz. A literal zg=0 diagnostic retaining u0q gives m=0.00863847201127 kg and f_SC=15.9870248462 Hz. Omitting all magnet pitch/horizontal motion gives m=0.00860484733734 kg and f_SC=16.0182301862 Hz. These are explicitly modified inertia models, not alternative geometric truths.

The N=0 condensation is quasistatic in the axial direction. At nonzero v it also gives u0v(a)=−(P/A)Lpatch=6.76557863501e−9 m/V. The canonical scalar mass is taken from the short-circuit q-dependent shape; it neglects voltage-dependent axial kinetic energy and its cross terms. As an algebraic scale check only, inserting v/q=−theta/Cp_Ritz into this axial field changes the canonical effective inertia to 0.00869337612785 kg and its open-frequency estimate to 16.2517714123 Hz. This is not a replacement dynamical model.

## Structural idealization sensitivity

The flexible-overlap comparison lets copper bend to a=0.096 m while attaching the lumped rigid magnet at its x-centroid. It deliberately ignores the actual stiffness reinforcement of the bonded copper/magnet overlap. A rigid magnet cannot be bonded over that entire interval while the same copper interval freely follows a curved EB field. Consequently this comparison is an idealization sensitivity, not a consistent finite-stiffness model of the same overlap.

| Quantity | Rigid overlap, a=91 mm | Flexible-overlap diagnostic, a=96 mm |
|---|---:|---:|
| k, N/m | 87.1629593634 | 87.1397695057 |
| canonical m, kg | 0.00869349453683 | 0.00869377495349 |
| theta, C/m | −2.55573265001e−4 | −2.55505269287e−4 |
| Cp_Ritz, nF | 18.7519736138 | 18.7519736138 |
| Cfree_Ritz, nF | 19.5013480529 | 19.5011486805 |
| Cfree_continuum, nF | 20.2287736380 | 20.2287736380 |
| Cp_condensed, nF | 19.4793991989 | 19.4795985713 |
| f_SC, Hz | 15.9363523141 | 15.9339752455 |
| f_OC, Hz | 16.2516607341 | 16.2491535716 |
| k_OC, N/m | 90.6462030544 | 90.6211599971 |

Here f_SC=sqrt(k/m)/(2pi), k_OC=k+theta²/Cp_Ritz, and f_OC=sqrt(k_OC/m)/(2pi). These formulas use the same short-circuit trial shape and mass for both electrical conditions. They are not independently resolved short/open eigenmodes.

The additional compliance is exactly (0.005 m)³/(3 EI_copper). Its small effect arises from the short, low-moment added span near xg. It does not demonstrate that real 3D overlap, shear, adhesive, or finite magnet compliance are negligible.

## Numerical method and reproducibility

Run `python crosscheck.py` in this directory to regenerate `results.json`. The implementation is independent of the parent implementation. It uses closed-form piecewise polynomial antiderivatives for the unit-load shape and compliance; eight-point Gauss–Legendre integration independently evaluates strain energy, coupling, and mass. All integrated expressions are piecewise polynomials of degree at most six, so that quadrature is exact in exact arithmetic. Printed differences are ordinary floating-point roundoff, not acceptance tolerances.

The energy-integrated stiffness is 87.16295936341257 N/m versus inverse-compliance 87.16295936341255 N/m. Both independent coupling calculations return −0.00025557326500094804 C/m. No native results were used to fit or calibrate any coefficient.

## Provider comparison receipt

After independent derivation and computation, the completed provider JSON was read solely for comparison; its Python implementation was not imported. The epsilon0 value was harmonized from the independent preliminary CODATA value to the requested CODATA2022 pin before comparison.

`comparison_receipt.json` records the provider-output hash, independent-script hash, exact observed differences, and 13 compared quantities. The greatest absolute relative difference was 1.1972562715452787e−15 (effective mass); theta and all four capacitances were bitwise equal in the printed Python floats. This records agreement of the two calculations under their shared explicit assumptions. It is not an acceptance threshold, native-model validation, or a physical qualification.

For additional material consistency context, the selected scalar primitives imply abs(d31)*sqrt(Y1^E/epsilon33^T) = 0.386647272653, while the manufacturer's guideline table separately lists k31 = 0.35. No adjustment or fit is made to reconcile these nominal guideline values; the scalar model is defined by its chosen primitive Y, d, and epsilon values.
