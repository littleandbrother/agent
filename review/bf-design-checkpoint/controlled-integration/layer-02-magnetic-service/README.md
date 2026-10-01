# Source-bound magnetic task service integration

This separate second layer removes the old task/model/cap literals from the
controlled offline path. The independently reviewed first layer remains sealed.

## Executed path

`actual Pi session -> registered bf_experiment ToolDefinition.execute ->
existing server.handler with narrow registry hooks -> immutable candidate upload
-> packet-bound job -> existing pipeline-handoff-v2.prepare_request -> BLOCKED`

The probe retrieves the real registered tool through
`session.getToolDefinition('bf_experiment')` and supplies the session's real
extension context. Its tool call is scripted by the trusted controller; no model
chooses it and `session.prompt` is never called.
The inherited registration of `bf_job` or `bf_submit` does not mean those
workflows are enabled or tested here. Only `bf_experiment`'s blocked transport
is exercised, and the controlled service denies submission and other job APIs.

The actual task is `DEV-FEASIBLE-01`, not an alias for `dev-01` or `dev-02`.
The original source-bound task, world input, evaluator and protocol identities
survive the execution packet, public task read, exact uploaded candidate, job
request, immutable blocked receipt and child trace.

## Effective configuration and boundaries

- The Pi SDK reads its model descriptor and budgets from the explicit packet
- `approved_model`, `approved_budget` and approval remain null
- The SDK model is named `offline-no-call-model`, explicitly fictional and
  solely for constructing the actual SDK in dry-run mode
- Model/native-solver budgets and money are zero; separately declared local
  fixture upload/job-intent caps control transport tests
- H0 state/prompt limits derive from the packet, not 6/24/600 literals
- The source/build manifest delegates model, caps and execution-world identity
  to the packet. The old synthetic world label is only legacy source provenance
- No native tool identity is invented: the retained job passes `{}` to the real
  handoff and receives `TOOL_IDENTITY_MISSING_OR_INVALID:pmic_model`
- Neither `Workbench.__init__`, `Store` auto-grants, `Provider`, nor the old
  experiment worker is constructed. An explicitly nonsecret fixture bearer
  authenticates only the short-lived loopback fixture server
- `/api/solve`, `/v1/chat/completions`, submission, other APIs and UI routes are
  denied in this controlled fixture service; legacy launcher launch() is disabled

This removes the old alias/literal routing obstacle for offline integration.
It does not implement an approved live provider dispatch path. A future live
path still requires owner approval, qualified task/reference, actual native
identity collection, isolated participant runtime and original-ledger binding.

## Evidence

- `reports/tests-final-24.log`: 24 focused tests pass
- `reports/probe-v3/RESULT.json`: final real-process receipt
- `reports/probe-v3/EXECUTION-PACKET.json`: explicit packet and null approvals
- `reports/probe-v3/process/stdout.jsonl`: imports, actual H0 invocations,
  effective runtime configuration, task binding, registered-tool name/arguments
  and one zero-message completed session
- `reports/probe-v3/service/events.jsonl`: existing HashJournal chain across
  task/budget reads, upload intent/completion and job intent/BLOCKED
- `reports/probe-v3/service/snapshots/`: exact original `candidate.json` text,
  its hash, normalized candidate and immutable binding
- `reports/probe-v3/service/jobs/`: full blocked request and missing tool evidence
- `src/trace_readback.py`: strict standard-library-only trace verifier

Earlier retained probes v1/v2 remain as development history, with their source
and build receipts. v3 adds strict readback and exact uploaded-source retention;
older snapshots must not be represented as having that stronger receipt schema.
All retained probes are included in the final checkpoint rather than selecting
only the final one. Initial setup errors were corrected before v1: copied source
path assumptions and the SDK tool execute() context signature. No model/native
calls occurred during those failed setup attempts.

## Negative controls

The tests cover missing/reordered activation, wrong tool/arguments, wrong task
binding, duplicate completion, same-ID packet-content mutation, rehashed changed
model/budget rejected against the actual service, stale registry/model/budget,
pre-start source drift, legacy aliases/operator attempts, model/solve/submit
denials, changed excitation/precharge/external power, exact upload bytes,
interrupted uploads before/after artifact creation, partial/tampered receipts,
restarted recovery, duplicate/conflicting and concurrent job requests, and local
caps that count every reserved intent. Partial corrupt files are never overwritten
or dispatched. Durable artifact writes are fsynced before their completion event.

## Reproduce in the pinned runtime

    python -B -m unittest discover -s tests -v
    python -B run_probe.py --output reports/NEW-probe

Use a new output directory. The original restored Pi dependency tree and Battery
World Python sources are prerequisites; this package does not install or upgrade
them. `build_overlay.py` reconstructs the narrow patches with exact-target checks
and the pinned compiler. Preserve the existing build receipt under a new name
before a deliberate local rebuild; never edit the sealed first-layer package.

Standalone delivered checks validate hashes, journals and strict retained traces.
They do not rebuild Pi, invoke native solvers, authenticate an external author,
qualify physics, or prove an autonomous D/H scientific outcome. No full repository
`init.sh`, native commercial solver or monorepo-wide regression was run here.
