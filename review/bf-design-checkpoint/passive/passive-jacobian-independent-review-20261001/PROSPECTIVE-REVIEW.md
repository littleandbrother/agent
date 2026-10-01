# Structured-Jacobian passive study: prospective review

## Decision

The exact candidate passes prospective independent review. A new root authorization is required for any trajectories. This review performed no new magnetic evaluations, equilibrium solves or time integrations.

Candidate plan seal: `adc8647db2251a93142dfc1ec928ae0bf471f810b2e03c879c3a11fd484eca8e`.

Runner: `433a799eb874d3cb5f09b8b9c139369adbb4192f2a3fca9b922f437fd6d54720`.

Structured matrix module: `6d02068a30ba5c0d028849b2baba4b02f7b15209a25f53648240a8ddd1f11ddf`.

All 52 candidate bindings were verified. The physical model, source files, 47/10 microfarad intervention, initial equilibrium, motion, energy/domain/quadrature/refinement gates and two solver settings are unchanged from the stopped study. The new numerical revision supplies the Jacobian, bounds and checks its magnetic q derivatives, retains rejected-probe diagnostics, and adds a finite Jacobian-call ceiling.

## Mathematical and software checks

The branch-aware matrix has the correct reciprocal piezo stiffness term −theta²/Cp, charge/storage current signs, damping and resistor-energy derivatives. The four accumulator feedback columns are identically zero. The storage-voltage column is exactly zero in the off branch. Exact bridge equality uses the declared inactive generalized-Jacobian convention; the physical current law is not smoothed or altered.

The magnetic adapter differentiates only q, using the same fixed source provider. It compares centered differences at h and h/2 and returns the latter. Its nominal h is 0.1 micrometer, reduced to one quarter of remaining q support when necessary. An unresolved interval is rejected rather than extrapolated. Each force call remains in the original force budget. The derivative absolute thresholds have the recorded N/m or W/m units and the relative threshold is 0.001.

The reviewer recomputed all retained differences and all entries of the three 8-by-8 matrices at the frozen first/middle/last accepted states. Maximum h-versus-h/2 discrepancies were:

- Generalized-force derivative: 3.3306691e−9 N/m
- Translational driver-power derivative: 1.5265567e−9 W/m
- Rotational driver-power derivative: 1.7347235e−11 W/m

The adapter was also exercised using only those retained values, with the actual magnetic evaluator blocked. Its matrices matched the independent calculation. Both conducting polarities, off/equality branches, enormous synthetic accumulator values, domain refusal and JSON-safe nonfinite/rejected-voltage telemetry were checked separately.

The runner supplies this Jacobian directly to Radau. Fail-closed interruption handling, exact 4 s and 4,001-point completion checks, source/run identity binding and continuous per-cell/global budgets remain present. Rejected RHS or derivative calls are labeled as internal evaluations with exact state, time, computed guard fields and last accepted state, so they cannot be mistaken for accepted physical overvoltage.

## Test accounting

- Producer full suite records 30 passing no-trajectory tests
- Reviewer ran 27 tests that do not call magnetics
- Three provider-evaluating tests were not rerun: original equilibrium, original angle derivative and the new three-state q derivative test
- Six additional independent retained/algebra/rejection tests passed
- The new derivative test records 12 magnetic evaluations; the full producer suite also repeats four original-control provider calls, for 16 provider calls in that suite
- Reviewer magnetic evaluations and trajectories: zero

The 12 derivative evaluations are development checks derived from the stopped trajectory. They are not held-out physical validation. The stopped study remains attempted=1, completed=0, unrun=3; no result or cost is erased by the numerical repair.

## Execution and claim boundary

The candidate is suitable for a separately authorized, bounded four-cell conditional comparison. Completion or success is not guaranteed. All per-run, force, derivative, energy, path and convergence failures remain valid stopping outcomes. Any new attempt must retain its new identity and the prior failed attempt.

Successful completion would establish only a conditional numerical sensitivity for the declared q-only material/damping branch and ideal 100 kilohm passive circuit. It would not provide a native-PMIC reference, a real-device necessary condition or upper bound, startup, mission, hardware or physical-preparation evidence. The sampled derivative checks do not prove a whole-domain error bound or make omitted coordinates negligible.
