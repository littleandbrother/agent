# Conditional static magnetic generalized force

Result: the new energy-consistent interface includes axial translation and magnet rotation. The exact five-state plan passes all 45 planned energy-derivative checks and its order-6-to-10 numerical checks. It does not authorize a force table or transient integration.

Read `DERIVATION.md` for physics, frames, model identities, results and limits. Inspect `outputs/STATIC-RESULTS.json` for the retained quadrature results; `outputs/FRAME-VERIFICATION.json` was generated before force evaluation. `STATIC-PLAN.json` and `PLAN-SEAL.json` bind the predeclared state set and frozen sources. `outputs/EVALUATION-IDENTITY.json` binds the evaluated source/runner hashes.

Run `./init.sh` for 26 local tests without any new magnetic states. `evaluate_static.py` refuses to overwrite retained outputs. Do not rerun a new experiment in this directory or expand state/order support without separately identifying and reviewing it.

Scope: uniform hard magnets, μrec=1, source Br=1.25T and 10/20mm cubes; V=0 retained q-only conditional beam pose. Axial magnetic-load condensation, higher bending modes, voltage-induced axial translation, physical material qualification, full assembly contact, force-table generation, equilibrium and dynamics remain open.

Raw U(q±h), perturbation pose/contact data and exact reproduction checks are retained in `evidence-completion-replay/RAW-REPLAY-RESULTS.json`. This explicitly approved same-state recording replay is evidence completion, not independent samples.
