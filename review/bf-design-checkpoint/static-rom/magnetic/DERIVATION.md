# Static, energy-consistent magnetic-to-beam interface v1

## Result and exact claim

The new identity `bf-conditional-psi5a4e-cuboid-generalized-force-v1` evaluates a finite-cuboid magnetic interaction on the conditional beam's retained q-only, V=0 configuration path. The generalized force includes translation **and** COM rotation. It is the negative derivative of the same mutual potential used for the numerical checks.

The approved five states, three quadrature orders and three central-difference steps were sealed with eight source hashes before the first force evaluation. All 45 planned virtual-work checks and all five order-6-to-10 checks pass their predeclared engineering tolerances. This verifies a conditional mathematical implementation at these points. It is not independent field-solver or physical validation, material identification, full-domain qualification, equilibrium, a force table, or a transient/mission result.

## 1. Source identities and assumptions

`STATIC-PLAN.json` binds all local source snapshots; `PLAN-SEAL.json` binds the plan. Sources are copied read-only in meaning and never used to replace the sealed source world.

- `world-v1.json`: source-authoritative development geometry, 1.25 T remanence, μrec=1, tip cube 10 mm and driver cube 20 mm, nominal x-center separation 48 mm
- `upstream_native.py`: existing quadrature kernel, source μ0=4π×10⁻⁷ H/m and old fixed-tip transverse-force identity
- `upstream_build_cad.py` plus `source-design.json`: installation transform, origin, CAD centers and polarity statement
- `beam_rom.py`, `beam-parameters.json`, `beam-static-rom.json`, `DoorBeam.java`: new conditional beam pose and Jacobians, geometry and original beam source

The computational μ0 is inherited from the old implementation for exact model comparison; it is not represented as an exact post-2019 SI constant. Br=1.25 T is a nominal source assumption, not a measured N42 material property. The source design separately says μr=1.05, but the sealed world and old analytical kernel explicitly select μrec=1. This interface follows that selected branch and retains the discrepancy. It does not silently mix a 1.05 magnetic response into the unity-permeability formula.

Assume both bodies are rigid, uniformly hard-magnetized, with material-fixed M=Br/μ0 along each body's +x axis. The surrounding space and recoil response have permeability μ0. No soft steel, induced magnetization, hysteresis, temperature response, eddy current or demagnetization model is supplied. Both magnets' initial +x polarization comes from the source, not a measured polarity map.

The fixed-M magnetic-charge representation follows the scalar-potential formulation for hard magnets: bulk charge is −div(M), and surface charge is M·n. Uniform material magnetization leaves only the two body-x pole faces. These are mathematical equivalent charges, not magnetic monopoles. See the [University of Texas derivation](https://farside.ph.utexas.edu/teaching/jk1/lectures/node60.html). The unity-permeability assumption and its pole-charge force analogy are also explicit in [COMSOL's hard-magnet force verification example](https://doc.comsol.com/6.4/doc/com.comsol.help.models.acdc.force_calculation_02_magnetic_force_bem/force_calculation_02_magnetic_force_bem.html). The constitutive branch is B=μ0 μrec H+Br, as described in [COMSOL's constitutive documentation](https://doc.comsol.com/6.3/doc/com.comsol.help.acdc/acdc_ug_magnetic_fields.08.032.html). These sources support the equations and restrictions; no commercial solver was run here.

## 2. Frame registration and signs, checked before evaluation

The CAD source maps product-local millimeters to world coordinates by

World XYZ=(1004−x, 70+z, 2140+y).

The beam coordinate starts at the source's global x=4 mm clamp, so its world origin is (1.000,0.070,2.140) m. The world-to-beam matrix is

A=[[-1,0,0],[0,0,1],[0,1,0]], det(A)=+1.

Thus beam x points toward negative world X, beam y toward world Z, and positive transverse beam z toward world Y. The rest magnet COM in the beam frame is (0.096,0,0.005265) m; mapping it back gives the canonical world COM (0.904,0.075265,2.140) m exactly to numerical tolerance.

At gap g, the door-closed driver center is (0.904−g,0.045,2.140) m in world coordinates. The driver's world rotation is Rz(a) about the source pivot; conjugating by A gives the beam rotation Ry(+a). Initial body magnetization +x is world −X. No reflection or informal moment-sign flip is used.

Let ψ=−0.08565521492786202 and s=16.400263573374637 m⁻¹ be the frozen beam coefficients. Its pose is

r_tip(q)=(0.096+ψq,0,0.005265+q), R_tip(q)=Ry(−s q).

dr_tip/dq=(ψ,0,1), ω/qdot=(0,−s,0).

The driver's position relative to the tip has the independent explicit form

Δx=0.904−(0.904−g)cos(a)+0.045sin(a)−ψq,

Δz=(0.904−g)sin(a)+0.045cos(a)−0.075265−q, Δy=0.

At a=q=0 and g=0.048 m it is (0.048,0,−0.030265) m. `FRAME-VERIFICATION.json` retains these checks and proper rotation determinants for all five states, created before magnetic evaluation. The relative signs are fixed by these coordinates, not corrected after observing force signs.

## 3. One mutual mechanical potential

For signed surface elements c_i=σ_i dA_i (units A·m), let r_ij=x_i−x_j, where i belongs to the tip and j to the driver. The quadrature computes

U_m=μ0/(4π) Σ_iΣ_j c_i c_j / |r_ij|.

This is the mutual mechanical potential, with zero at infinite separation. The cross interaction is counted once, so there is no extra factor 1/2. Rigid self energies are q-independent and omitted. No external coil/current-source energy is present.

Analytical differentiation with respect to the tip COM gives

F_tip=μ0/(4π) Σ_iΣ_j c_i c_j r_ij/|r_ij|³.

The body-fixed charges move and rotate with the magnet. Variation under a rigid angular displacement gives COM torque

τ_tip=Σ_i (x_i−r_tip) × Σ_j f_ij.

This charge torque already includes magnetization orientation work. Adding a separate m×B term would double count the rotational effect. Pairwise Newton balance and total moment balance are algebraic controls, not an independent force validation.

With F and τ expressed in the same proper beam frame and τ about the tip COM,

Q_mag=F·dr_tip/dq+τ·ω_q=Fz+ψ Fx−s τy=−∂U_m/∂q.

Units: μ0 is N/A², c is A·m, U is J; F is N, τ is N·m, dr/dq is dimensionless and ω_q has units 1/m. Therefore every term in Q is N, the force conjugate to q in meters.

The implementation obtains analytical F and τ from the pairwise gradient, then independently differences total potential along the q pose. This is an independent differentiation route within the **same** magnetic quadrature model, not independent physics.

## 4. Predeclared bounded evidence

Exactly these states were evaluated at g=48 mm:

| Door angle | q | Q at order 10 | Old fixed-tip Fz at order 10 |
|---|---:|---:|---:|
| 0° | 0 mm | −0.4212216534 N | −0.3154305985 N |
| 2° | −4 mm | +0.1188285652 N | +0.1151494874 N |
| 2° | +4 mm | −0.2274376426 N | −0.1143086024 N |
| 15° | +4 mm | +0.0008568919235 N | −0.0005330728900 N |
| 65° | 0 mm | −0.000004288885644 N | −0.000002677147010 N |

Gauss-Legendre orders were 4, 6 and 10 per pole-face dimension. Each nominal result used q central-difference perturbations h=2,1,0.5 μm. The fixed old code functions were AST-extracted from the source snapshot and evaluated as their own identity; no old table was imported into the new interface.

Predeclared virtual-work tolerance was 10⁻⁹ N +10⁻⁶ |Q|. All 45 checks pass; largest absolute discrepancy is 1.6638324×10⁻⁹ N. Predeclared order-6-to-10 Q tolerance was 10⁻⁹ N +10⁻⁴ |Q10|. The largest observed Q change is 3.3499639×10⁻¹⁰ N. Order-4-to-6 and potential/vector-force/vector-torque deltas are also retained. These differences are empirical numerical convergence evidence at five states, not a rigorous integration error bound or a physical uncertainty interval.

### What the old/new differences mean

At closed q=0 the new and old magnet poses coincide and their F vectors agree to roundoff. Generalized force nevertheless differs because the paths' tangents differ:

−0.315430598547 N transverse −0.009662170567 N axial −0.096128884265 N rotational = −0.421221653379 N.

At 15°/q=4 mm the tip pitch is −3.75866° and its axial shift is −0.342621 mm. Decomposition using retained order-10 results is:

- Legacy fixed-tip transverse force: −0.000533072890 N
- Transverse-force change due to the new pose: +0.000098040420 N
- Axial virtual-work contribution: +0.000098418531 N
- Rotational virtual-work contribution: +0.001193505862 N
- Total new generalized force: +0.000856891926 N

The opposite signs compare two different kinematic models. They show that old Fz cannot silently serve as new Q, **not** that the old fixed-tip quadrature is numerically wrong. A missing-torque and a transverse-force-only negative control fail the energy derivative by far more than the fixed tolerances.

## 5. Contact, domain and mechanical truncation

A 15-axis separating-axis test checks the two rotated cuboids before quadrature. Overlap and touching are rejected, including synthetic unit controls that never reach force integration. The reported maximum positive separating projection gap is a lower bound on surface distance, not exact clearance. All planned nominal and perturbed states pass this guard. Nominal lower bounds range from 33 mm to 815.85 mm. This covers only the two magnets at sampled states; no contact safety for the beam, enclosure, door, mounting hardware or continuous trajectory is established.

Nonfinite inputs, reflections/non-orthogonal rotations, and out-of-inherited-support values are rejected. The old |q|≤8 mm, angle≤65°, gap28..70 mm ranges remain exploratory computational support. The five evaluated points do not qualify those complete ranges.

The beam supplies short-circuit/V=0 q-only kinematics. Evaluating a proper rotation matrix does not make its first-order COM path a nonlinear elastica. Nonzero magnetic Fx induces axial resultant and additional deformation; magnetic torque can excite discarded bending shapes. Neither is statically recondensed here. Consequently energy consistency on the chosen path does not establish that path's physical accuracy. At nonzero voltage the beam's condensed axial solution also has a voltage-driven translation, omitted here; this package does not verify the fully coupled magnetic-piezo potential or charge derivative for nonzero V.

No convenient magnetic material values, source commits, external paid calls, licensed/native solvers, full table, equilibrium solve or time integration were used. The source repository's full init suite was not run; no source repository feature or health claim is made. The owned package has its own `init.sh`, with 26 retained-data, geometry and negative-control tests.

## 6. Raw-evidence completion replay

The initial runner retained derivative values and discrepancies but did not save individual perturbed potentials. That gap was disclosed to the parent and reviewer. The parent then explicitly authorized one separately identified recording replay of the exact existing state/order/step set, with no new physical state. `evidence-completion-replay/REPLAY-SEAL.json` binds the corrected recording code before execution, the unchanged provider, original results and reproduction tolerances.

`RAW-REPLAY-RESULTS.json` retains both U(q+h) and U(q−h), collision diagnostics and poses. All 105 original-value reproduction checks agree exactly (maximum discrepancy zero). The original outputs remain unchanged. The replay is **evidence completion, not independent samples or an additional physics validation**. All 45 finite differences can now be recomputed directly from saved raw potentials. The minimum perturbed magnet-OBB distance lower bound is 33.0000018 mm.
