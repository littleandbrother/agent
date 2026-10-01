# Conditional passive source/storage study

This separately versioned experiment asks how changing only storage capacitance from 47 to 10 µF changes one fixed conditional source trajectory and energy partition. It is not a native-LTC3588 model, physical validation, feasibility witness, or formal Agent experiment. `PLAN.json` is the machine-readable complete protocol; `PLAN-SEAL.json` binds it and executable inputs before dynamics. Dynamics additionally require exact root and independent-review approval.

## Fixed equations and initial state

The piezo convention is q positive along beam +z, Vp = Vtop−Vbottom, and Q the top-electrode supplied charge. Cp is the one-coordinate Ritz capacitance, 18.7519736138 nF, counted once. With theta = −0.000255573265001 C/m,

- Vp = (Q−theta q)/Cp
- m qdd + c qdot + k q − theta Vp = Fmag(q,angle)
- I = max(|Vp|−Vs,0)/R; i = sign(Vp) I
- Qdot = −i; Cin Vsdot = I

This is an ideal full-wave rectifier, a fixed series resistor R=100 kΩ, and an ideal initially empty capacitor, with no load or leakage. R is an explicit preselected benchmark assumption, not measured diode resistance, inferred ESR, or a representation of the PMIC. It supplies a finite, passive electrical response; it is not asserted to bound a real harvester from above. Damping is c=2(0.02)sqrt(mk), retaining uncalibrated zeta=0.02 only as a development assumption.

All four trajectories share q0 = −0.005838454977432304 m and qdot=0. The bounded static scan found one bracketed stable in-domain root; its effective stiffness is about 76.4414517 N/m. This is not a proof that every possible root was found. Vp0=Vs0=0 and Q0=theta q0=1.4921530011434105 µC. The nonzero signed electrode charge is required for physical zero piezo voltage; it is not electrical precharge.

Initial elastic energy is 1.4855861520281061 mJ; initial signed mutual magnetic potential is −7.71120726664825 mJ, in the source convention that mutual potential vanishes at infinite separation. Kinetic, piezo, and capacitor energy are zero. Preparation/reset work and the means of establishing this equilibrium remain unknown.

## Driver work and energy boundary

The driver opens linearly to 65° in 2 s and holds through 4 s. Integration is split exactly at 2 s. Driver translational and rotational magnetic work are both retained:

- d rdriver/d angle = ey × (rdriver−pivot_beam)
- Ptranslation = Ftip · (d rdriver/d angle) angle_dot
- Protation = −tau_driver_COM_y angle_dot
- E = ½m qdot² + ½k q² + (Q−theta q)²/(2Cp) + ½Cin Vs² + Umag
- E(t)−E(0) + integral(c qdot² + R I²)dt − Wtranslation − Wrotation = 0

All primitive forces/torques and driver derivatives are retained at accepted interval endpoints and midpoints, together with instantaneous powers. A separate composite-Simpson calculation audits all four loss/work integrals. Residual scaling uses initial nonmagnetic storage and energy changes/work, so a magnetic-potential gauge shift cannot make the gate easier. Driver-mechanism inertia/friction and physical reset are outside this boundary.

## Numerical checks and limits

The exact protocol contains two predeclared Radau resolutions per capacitor and four trajectories maximum. Both time resolutions use direct order-6 finite-cuboid force/potential, with separate order-10 evaluations at every accepted interval endpoint and midpoint. No old transverse-only force table is reused. Python, NumPy, SciPy and Radau source are pinned because the numerical-path check uses its cubic dense output.

Exact extrema of each Radau cubic bound q on that numerical segment. A conservative displacement/rotation-rate deduction from the initial magnet SAT gap bounds continuous separation along the cubic. Neither is a proof for an exact ODE solution or surrounding beam/door/fixture clearance. Inherited |q|≤8 mm is exploratory support, not physical safety or accuracy.

The assumed q-only magnetic pose omits voltage-dependent and force-induced additional axial motion, discarded bending modes, axial inertia and nonlinear beam behavior. Cp_Ritz is not silently replaced by endpoint-static capacitance. No claim that these omissions are negligible is made. Passing software, numerical refinement and energy gates would qualify only the declared conditional comparison.

Failures, partial states, budgets and raw evidence are retained. Any trajectory failure stops the branch; no replacement trajectory, tuning or search is allowed. A difference is called numerically resolved only if all declared checks pass and its magnitude exceeds five times the sum of observed coarse/fine differences. This empirical resolution test is not a confidence interval or rigorous error bound.

## Commands

`bash init.sh` runs only bounded static/algebra/software controls, not dynamics. It is the owned study's initializer, not the upstream repository's full test suite. The upstream root init was not run and no repository-health claim is made.

After approval, each exact `python passive_runner.py --case cin47|cin10 --resolution coarse|fine` runs one declared trajectory, in frozen order. `python passive_runner.py --compare` verifies sealed identities and compares the retained four results without integrating again.
