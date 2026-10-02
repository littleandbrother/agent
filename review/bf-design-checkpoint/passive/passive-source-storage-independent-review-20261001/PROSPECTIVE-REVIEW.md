# Prospective passive source/storage review

## Decision

Revision 2 passes independent prospective review for the exact four-cell conditional comparison. Root authorization is a separate required action. This review ran zero physical force evaluations, equilibrium solves or time integrations.

Accepted plan seal: `b8bf3b76eba19c991f739289c73c93c9ea627034677f030110469d3f0d1e68d8`.

Scientific plan: `306a5b3bc617dec411590c9ad5d03215496d098de9c153f5ade88421ab3f8dd4`.

Runner: `bd08538a6150bb0744e006f8123b350b76644a350e6770a90d1b754d6b392dee`.

All 40 revision-2 seal bindings were independently checked. The rejected revision-1 seal and all its bound files are preserved, and their hashes were independently checked. No scientific parameter, numerical tolerance, acceptance threshold or four-cell design changed during the execution-integrity repair.

## What was checked

- Charge convention, reciprocal piezo sign and single Cp_Ritz use
- Initial root, local stability, Q0=theta*q0, positive elastic and signed mutual magnetic energy
- Passive bridge/resistor/storage power identity, including negative piezo voltage
- Prescribed-driver translation and COM torque signs, independently reconstructed from retained source-frame geometry and primitive force/torque
- Retained one-sided angle finite difference: dU/dangle approximately −0.32916019346 J/rad, agreeing within 2.92e−10 J/rad
- Exact two-interval handling of the 2 s driver-speed break
- Separate order-6/order-10 force, potential and driver-derivative comparisons at each accepted interval start, midpoint and endpoint
- Retained powers for independent Simpson work/loss reconstruction, alongside ODE-integrated ledgers
- Gauge-invariant total-energy residual scaling
- Dense-cubic support and numerical-path separation checks, with scope limited to the numerical path and magnet pair
- Frozen Python/NumPy/SciPy/Radau identity, run-output seals, initial-state binding and comparison identity checks
- Four-cell ordering, no retries, stop-on-failure, per-cell execution budgets and in-cell global study deadline
- Exact terminal-time, finite 4001-sample grid and terminal-state consistency requirements
- Individually resolved-effect flags and valid unresolved/no-direction outcomes

Twenty-three producer software/algebra tests passed in an isolated reviewer copy. Two original producer tests that call the magnetic provider were deliberately not rerun; their retained root and angle-derivative data were checked independently. Five independent retained-data/algebra tests passed, as did one additional independent partial-run interruption probe. The producer's complete prefreeze suite records 25 passing tests. These counts are distinct, not additive evidence of new physical trials.

## Blocking finding and repair

Revision 1 caught only Exception. A KeyboardInterrupt or SystemExit could enter finally with failed=None and seal an incomplete result as TRAJECTORY_CHECKS_PASS. The reviewer reproduced this after one synthetic constant 1 ms segment, with a fake integrator and retained magnetic values. No scientific solver/provider was called.

Revision 2 defaults to incomplete, catches BaseException, requires explicit completion after all final gates, rejects truncated/nonfinite/mismatched grids in both execution and comparison, and retains failure evidence. The same independent 1 ms interruption probe now yields INSUFFICIENT_NUMERICAL_EVIDENCE. It also checks the whole-study deadline during active cells rather than only before launch. The original failed candidate remains intact.

## Exact authorized candidate, if root approves

The candidate comprises 47 and 10 microfarad storage, each at the two frozen Radau settings, in fixed order. Both use the unchanged conditional source/material branch, zeta=0.02, ideal bridge and R=100 kilohms, one initial equilibrium, 65-degree opening over 2 s and hold through 4 s. At most four trajectories may be attempted; a failed trajectory stops this branch and is not replaced.

R=100 kilohms is an expressly chosen benchmark resistance. It is not a sourced diode, measured ESR or LTC3588 path. This model is not a necessary-condition or upper-bound test for a real harvester. A successful comparison supports only storage sensitivity under its assumed q-only trajectory, material/damping branch and passive circuit. Nonzero-voltage and force-induced axial changes, omitted modes and physical preparation/reset remain unqualified. No startup, PMIC, firmware, receiver, mission, physical safety, hardware feasibility or Agent efficacy claim follows.

All numerical refinement evidence is empirical. In particular, sampled n6/n10 agreement is not a rigorous whole-domain bound, and five-times-observed coarse/fine separation is not a confidence interval or certified error bound.

## Next review stage

After root-authorized execution, audit saved states, primitive powers, dense segments, numerical gates, identities and effect calculations. No additional trajectories or magnetic evaluations are part of that audit. A failed or unresolved outcome is retained as such.
