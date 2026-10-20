# campaign-a -> S0: BFA-045 finite package complete

Date: 2026-10-19. **Ready for S0 integration. No follow-on execution is running.**
Working tree: `/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-a-20261019`.
All writes are the declared ar.py, b.py, campaign_reference.py,
test_campaign_reference.py, and the two reference config/docs directories.
No __init__.py, common/shared code, PROJECT, feature file, root state, original
V2 source, existing Pi project, model SDK or immutable historical result was edited.

Baseline: CB-6f1c798155bb7ca2352d362d57a7e2032dc79379450a723ea3cff2751ce5318c.
HEAD: 317d40fef0137d3c1ad1873e53c3e9968b31200a. Full content audit before and
after implementation matches 5,543 files; the only remaining difference is
S0's already-authorized PROJECT active-feature overlay. There was no Git
commit, push, original V2 Git operation, chat message, sub-agent or owner restart.

## Delivered facts

1. Frozen six-task, 17-condition public input and expected positive/negative
   controls; configuration hash 19757a1c9aa8a889dbb7258276121d3621c0faa7d468aa47ff95ac9a1a201fdb.
2. A/R-1 complete nominal light/storage/power/temperature/program/digital
   reception chain, ordinary strapped container installation and BOM. First
   fresh receive 773 s; six-hour light/dark run 348 samples and service PASS.
3. R-history: all 170 durable records retained but 660 new-sampling windows
   and one temperature event missed; gap delivered, clock continuity UNKNOWN,
   recovery deadline FAIL. Volatile control loses 121 records.
4. Gateway recovery: 60 queued records uploaded in 82 s, two duplicate arrivals
   correctly deduplicated; naive receiver accepts both. Combined live service
   still FAIL because one new sample waits 30 s in FIFO (10 s requirement).
5. B: same 150 uJ source succeeds at 15.8 ms with low ESR and fails with high
   ESR. Split 210 uJ/shunt/reset pair succeeds at 46.9 ms with an assumed passive
   latch and fails with captured volatile event loss. No release energy added.
6. Epishine/e-peas and ECO260 official anchors recorded. Models are behavioral;
   IV, native PMIC/kinetic dynamics and hardware remain UNKNOWN.

Raw immutable output:
`/Users/depengsu/.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-001`.
Candidate CR-f7d7d4fc3b1d830ea36f96ea11671e927de9f55748d842d10385b7f693cf0183.
81 files, 42.99 MB before seal. All source and raw input/trace/receiver files have
hashes; candidate is portable under stdlib Python. Read [RESULTS.md](RESULTS.md),
[REPRODUCE.md](REPRODUCE.md), results.json/CSV, artifact-index.json and feature-receipt.json.

## Verification and failure history

Twelve targeted tests PASS. Requested architecture-v2-ci init PASS: 343
repository tests plus saved 44-file/11-control readback. New independent saved
readback PASS for all 17 cases/81 files, without reexecution. Two copied-source
portability runs match observations and trace bytes exactly. These software
checks do not establish the default full init, native or physical qualification.

The first targeted run caught a checker error: stale historical data was counted
as first fresh reception. Original source, input, trace, wrong result and receipt
are retained at `a/verification-001/stale-failure/`; second-run logs are at
`a/verification-002/`. No input, expected outcome or requirement was relaxed.
The dark, volatile, duplicate, late-energy, high-ESR and FIFO failures all remain.

## S0-owned integration and state

Import only the exact owned files listed in changed-files.json. Update
PROJECT.yaml, project/features/BFA-045-ar-b-reference/feature.yaml,
docs/PROGRESS.md, docs/SESSION-HANDOFF.md and root feature/progress/handoff state
from feature-receipt.json; campaign-a intentionally did not write these files.
No shared module edit was needed. APIs use only dict inputs and stdlib.

The flat verdict dictionary includes logical/vacuous checks. Select required
gates by task and applicability; B-event-memory's reset gate is not required for
B-pulse. Never turn 17 expected-control matches into 17 product successes. Keep
AR-upload's live failure alongside its upload/dedup PASS. No formal test split
or holdout was created. Public development exposure applies to both papers.

These are local campaign reference artifacts. Runtime/ObservationBroker/System
Commit/RunBundle registration, if desired for a later experiment, remains S0
integration work with its own identity and authority; this package does not edit
those shared contracts. Fixed source-port assumptions must not be promoted as
load-dependent PV/PMIC models. Preserve the case IDs and candidate hashes when
using these facts as F1a inputs or P1 illustrations.

New experiment paid requests 0; native EDA/simulator dispatches 0; hardware
writes 0. No active native job or final authorization question remains. This
finite work package stops here; sensor/IV/RTC/NVM/radio qualification and the
known FIFO scheduling improvement are future work, not hidden completed gates.
