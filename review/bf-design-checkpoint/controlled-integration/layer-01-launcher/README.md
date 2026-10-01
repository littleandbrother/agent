# Controlled launcher integration: actual Pi, trusted offline scope

This additive package connects the prospective D/H checks to a real execution
path without authorizing a participant experiment. Original repositories,
sealed physics/evaluator packages, and production ledgers are read-only.

## Executed entry points

1. `bfworld.agentlab.launcher.freeze`: copies the existing H0 source, invokes the
   restored pinned `tsgo` compiler, and binds real emitted JS, world/controller
   inputs, Pi app build and npm lock. The harnesses are written only under this
   package's `fixture-runtime`.
2. Existing `pi-bf-aiot/packages/bf-agent/src/main.ts`: an isolated copy retains
   the actual Pi runtime, resource loader, tool setup, in-memory session, and
   dry-run behavior. The diff adds post-import and post-invocation events at the
   actual solver/improver import and call sites. It requires `dryRun === true`.
   No replacement Python harness impersonates the Pi process.
3. `bfworld.runtime.journal.HashJournal`: durable assignment and attempt records
   with a file lock, full denominator, unknown-effect stop, immutable receipt
   linkage, and recovery without spawning another process.
4. `bfworld.campaign.budget.Ledger`: existing conservative reservations,
   settlement, idempotency and unknown-cost stop are tested using isolated
   fixture databases. These are explicitly synthetic usage-receipt unit tests,
   not billable calls and not permission to reuse old CNY or USD limits.
5. `bfworld.agentlab.recursive.compatible` and `campaign.splits`: H0 compatibility,
   exact H0 reload, lineage consistency, actual-parent receipt requirement,
   manual-edit exclusion, and exposed/duplicate physics rejection.
6. Existing `pipeline-handoff-v2`: reconstruction, current source/tool recheck
   and the exact `submit_candidate(candidate, output, cache_root, confirm)` data
   contract. This adapter does not import or run native solvers. Handoff tests
   use explicitly synthetic tool identities and never qualify a model.

## What the retained run proves

`reports/retained-controls-v2/RESULT.json` points to the final append-only run containing:

- Actual H0 solver and improver function activation in fresh Pi processes
- The old `harness_loaded` event followed by a genuine import exception, which
  correctly does not count as activation
- Genuine invocation failures after import, including improver failure after
  successful solver initialization
- A genuine TypeScript build failure and a killed time-limited child
- A manually changed fixture followed by an independently started exact H0
  rollback; the manual fixture is never represented as participant-authored H1
- A durable result followed by recovery of its unfinished journal transition,
  without another process effect
- A counted budget-stop attempt and a never-started assigned episode

Raw stdout, stderr, pid, random nonce, module/app/source hashes, function output
and its verified hash, mode, target binding, and exit code are retained. Import
alone, a pre-import log, successful solver startup alone, or a status string
without a process cannot satisfy activation. The supervisor validates every
invocation output hash as well as trace and terminal-receipt hashes.
The aggregated actual receipt also passes the existing prospective protocol's
`activation_errors` function. The adapter's source hash is part of the target
binding, and replay uses the original supervisor pid rather than the reader pid.

The first retained CLI run is preserved in `retained-controls-v1`. Its solver
control failed because a relative output path was resolved twice by the child;
this was fixed by normalizing the book and process roots to absolute paths.
The final suite includes a relative-output regression. `FINAL-RECEIPT.json`
retains both run identities and all 22 recorded attempts, including this failure,
both budget stops and both never-started assignments. These are repeated
engineering controls, not 22 independent scientific trials. The earlier v1
adapter did not record its own source hash; no retrospective source attestation
is invented for it. Transient unit tests are reported separately as test coverage.

The target task/world/evaluator binding is explicitly *prospective identity*,
not evidence that the magnetic task or evaluator ran. The solver fixture task
is labeled `TRUSTED_ACTIVATION_FIXTURE_ONLY`. Its single allowed local service
read is `/api/budget`; the fixture has no model or experiment route. Improve
mode requires no service requests. Pi's `session.prompt` is never called.

## Reproduce

The package uses the materialized restored dependency tree; no install or
network download is necessary:

    python -B -m unittest discover -s tests -v
    python -B run_controls.py --output reports/NEW-retained-controls

Choose a new output directory. Tests intentionally mutate and restore local
fixture build bytes for stale-build checks, so do not run multiple suites
concurrently in the same package. A reviewer should copy the package and its
symlinks to a separate directory first. The adapter paths derive its output
root from `src/paths.py`; input roots remain the exact read-only materialization.

The compiled overlay and build receipt are included. `build_overlay.py` records
a new build receipt with exclusive creation; an existing historical receipt
must be preserved under a new name before deliberately rebuilding this local
development overlay. Never overwrite a sealed delivered package.

## Current launch blockers

`launch_participant` fails before the original launcher can call `Store.grant`,
`Store.issue`, or any provider/credential path. The retained `LIVE-READINESS.json` includes the
complete current blocker list:

- Prospective protocol has no owner-approved model, limits, ledger, assignments,
  frozen analysis or heldout configuration
- Qualified development tasks remain 0/2; no independent feasible reference
- `/usr/bin/sandbox-exec` and actual-host Seatbelt qualification are unavailable
- The legacy Pi service exposes its old finite `dev-01`/`dev-02` tasks and literal
  model/caps; it is not a registered magnetic-task experiment service
- The trusted dry-run overlay is not a participant isolation boundary

No force flag, injected dispatcher, fallback bare participant subprocess, or
conversion of fixture receipts into launch authorization exists.

## Boundaries and next integration seam

This is real runtime integration evidence, not a live D/H experiment. The
instrumentation is implemented in a separate executable overlay and patch;
production behavior has not been changed or deployed. After a qualified native
runtime, feasible task reference and exact owner-approved model/budget exist,
the next engineering step is registering the new task/provider in the existing
experiment service and making its model/caps derive from the approved contract.
The current legacy launcher must not silently substitute its old tasks or caps.

Activation traces come from fixed trusted source allowlists. A child log is not
an authentication boundary against arbitrary hostile participant code. Real
participant execution still requires externally protected artifacts, isolation
qualification, independent evaluator authority and provider-ledger reconciliation.

Lineage checks prove mechanical consistency and reject fixture/exposed/manual
inputs. They do not authenticate participant authorship or grant promotion.
Heldout tests here contain synthetic registry objects, not actual blind tasks.

Recorded local attempt costs include source checks and freeze/build plus the
fresh process; process-only timing is separately labeled. They do not reconstruct
historical acquisition, scientific qualification, transfer or the complete H-loop
cost. The isolated fixture campaign enforces an explicit attempt cap and child
wall stop. A live multidimensional envelope still belongs to the future approved
runtime/provider contract; old literal limits are not inherited authorization.

`INPUT-LOCK.json` verifies 2,161 original Python/Pi source/build and contract files.
The npm lock binds dependency versions; it is not a byte audit of every third-party
dependency. No complete `./init.sh` or monorepo-wide `npm run check` was run here:
those mutate/materialize unrelated original outputs, while this task owns only
the additive overlay. The focused TypeScript builds and integration tests do not
claim application-wide health, native physics qualification, or hardware results.

No Git commit or push was made.
