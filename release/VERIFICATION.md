# Product execution authority release verification — 2026-09-29

This release adds BFA-025 to the source snapshot originally published at
`773730a4d0614160254aea5d26ce1caf174e0f34`. Checks ran on the original macOS host
from the independent `agent-github-release` checkout. They establish local
platform behavior, not qualification on a new machine, autonomous model design,
physical calibration, manufacture, firmware flashing or hardware operation.

## Final checks

- `cd pi-bf-aiot && npm run bf:build`: passed. This is the scoped BF build;
  the unrelated full upstream repository lint/check is not claimed here.
- `cd battery-world && BF_PI_ROOT=/absolute/release/pi-bf-aiot ./init.sh`:
  **388 Python tests passed**, with SDK type checks, World Studio type/build,
  deterministic reproduction and source-to-view validation passed.
- Nine product-authority checks include real CadQuery STEP generation and
  independent dimensions/volume readback, actual ngspice raw output and tamper
  rejection, a multiple-C-file STM32L031 target build, geometry-driven coupled
  simulation, camera-only negative control, stage conflicts and input identity.
- Seven Panorama checks include cloud-only source/history handling. Such files
  must not hang the projection or be mistaken for deleted/passing evidence.
- Seven changed frontend JavaScript modules pass `node --check`.
- An independent real Pi process used six scripted local model responses to
  write a project, submit the public engineering tool, run real ngspice and
  read its independent result. It yielded 120 points / four variables and a
  verified loaded product Harness hash. This is an integration test with zero
  external model calls; it is not an autonomous reasoning experiment.
- Live in-app-browser review confirmed the task stage summary, product node
  evidence/questions, console authored-project capabilities/product Harness,
  and source-backed Panorama (13 modules, 21 declared edges). Existing product
  assembly v14 was observed, without changing its design or target.
- Local production model ledger counts remained 1,933 SETTLED and one historical
  UNKNOWN request before/after review. No new paid calls or budget reset.

## Failures retained and resolved

An earlier full run found an import that worked under focused unittest discovery
but failed under root discovery. The test now supports both package entry paths.

Independent release verification also encountered macOS FileProvider cloud-only
placeholders in tracked source, TypeScript dependencies and generated CAD Python
bytecode. Compiler/process samples confirmed blocked file reads. Missing tracked
bytes were restored from Git after inventory verification; build dependencies
were restored only against matching lockfiles. Four generated cloud bytecode
files were quarantined locally, and required CadQuery source dependencies were
materialized through a local import. No timeout or acceptance threshold was
relaxed. The interrupted compiler run and the full run with one CAD timeout are
retained separately from the final passing run. A subsequent nine-test native
recheck passed before the full regression rerun.

Panorama now detects cloud-only snapshots and source files before reading them,
keeps local history usable and exposes unavailable data explicitly. This handles
the observed map failure; it is not a general-purpose cloud filesystem repair.

## Publication and evidence boundaries

Runtime data, credentials, private sessions, installed toolchains and large native
artifacts are excluded. Exported bytes are inventoried in `source-manifest.json`.
The explicit source scan found no installed provider credential, credential-token
pattern, runtime database or file above 50 MB in the release scope. Git commit,
remote equality and fresh-clone verification are recorded after publication in
the local coordinator receipt, avoiding a self-referential commit identity here.

Test-generated machine-specific legacy reports are restored to the previously
published source-bound reports; they are not promoted into new scientific results.
The original source release's initial fixture materialization ordering correction
remains in `init.sh`; this update does not change scientific model semantics.

BFA-025 covers unified stage verdicts, input-scoped invalidation, authored native
projects, geometry-to-coupled simulation, the loaded product Harness and the four
UI projections. Detailed restrictions and next work are documented in
`battery-world/docs/agentlab/PRODUCT-EXECUTION-AUTHORITY.md`.

BFA-024 remains blocked by reference calibration and current-board integration.
Many complete-delivery validators are still `not_run`; local native readback does
not satisfy them. Arbitrary COMSOL project execution, a complete generic product
contract library, current pluck PCB manufacturing data, measured MCU power and
wireless reception, and Agent/Harness efficacy have not been established here.
The older coordination repository's 88 scientific features and feat-397 remain
unchanged; its separate scientific init was not run or claimed healthy.
