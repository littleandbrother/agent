# BFA-069: S0 execution handoff

Status: software preflight ready; first real consumption and all 18 formal attempts are pending S0. Local fixture results do not establish service success, discovery, or an interface advantage. No paid, Pi, simulator, or native job was launched by B.

## Minimal integration

Copy only the new module, script, test, `frozen-families.json`, and development request listed in `HANDOFF.json`. Use S0's existing dependency environment and original numerical/reference sources. B does not contain the shared phase3 checker; `ABC_SOURCE_ROOT` points local checks at S0's registered source, without copying it.

```python
from bfworld.agentlab.campaign20261019 import abc_interfaces as B

prepared = B.prepare_episode(spec, episode_root)
payload = prepared["participant_input"]
handler = B.create_handler(episode_root, spec, executor=exact_B_task_executor)
# Install handler in the existing shared gateway, then invoke the existing SDK.
# After the endpoint closes, outside participant access:
judgment = B.independent_check(episode_root, spec, executor=exact_B_task_executor)
```

The shared runner must inject that callback in both places. It currently calls these functions without `executor`; that leaves actual consumption blocked with `S0_REAL_EXECUTOR_REQUIRED`. No model call should be spent discovering this missing host dependency.

`spec` requires `source_root`, `frozen_families`, `frozen_families_sha256` (file bytes), `case`, and `condition`. First rehearsal: `case=development-cross-source`, `condition=observation_refinement`, `stage=development`. Extra shared episode identity fields are preserved. Formal specs use the exact 18 rows of `formal_attempts`, with the same freeze file/hash. The first request is researcher supplied and excluded from formal evidence.

`exact_B_task_executor(task_dict)` accepts the entire immutable task, using unchanged `b.simulate_b` and independent `energy_reference` / `reference_b`, plus S0's existing raw-artifact cache, hash audit, and scientific-cost ledger. The old C/delay-only `CaseStore.execute(world, patch)` is too narrow for the three new mechanisms. The callback returns:

```json
{
  "input_sha256": "SHA256(canonical task JSON)",
  "execution_key": "actual immutable execution identity",
  "origin": "new-full-feedback-response or sealed-historical-exact-input",
  "reference": {"verdicts": {"...": "original independent verdicts"}},
  "energy": {},
  "reused": false,
  "raw_path": "S0 canonical raw artifact"
}
```

Canonical task JSON uses sorted keys, compact separators, UTF-8, `ensure_ascii=False`, and disallows nonfinite values. The five required reference verdicts are `independent_energy`, `independent_receiver`, `event_receive`, `deduplication`, and `transient_voltage`. Missing keys are an error; UNKNOWN remains UNKNOWN. The adapter verifies input identity and refuses fixture origins as scientific evidence. S0 remains responsible for complete raw/reference hashes, backend identity, usage, and storage/budget gates.

At most two fixed design inputs exist: `retain=current`, `adopt=intervention`. Host final evaluation may fill a missing one through the same callback. Cached reads do not constitute new runs. S0 must count callback dispatches and final evaluation as well as participant checks; no hidden retry or scientific-semantic change is allowed. A wrong decision, bad prediction, missing submission, or rejected input stays in the original attempt.

## Source and type contract

`acquire` exposes the same complete catalogue to every arm: component records, excitation records, complete inputs, and unchanged executable model law. No source is withheld from the strong complete-information or conservative fixed-rule control. The only arm difference is the frozen method instruction. Model context is fresh for each formal row; no answer, development request, prior evaluator result, or other arm's trace enters it.

An expression leaf names its own `source_id` and JSON Pointer. The host infers the registered source unit and supports dimension-compatible prefix conversion. Every domain row names its own source; all bindings must share the frozen task context. Conditions, numeric bounds, payload hashes, and the source unit registry are checked before any execution. A Boolean is distinct from a number. An intentional conversion requires an explicit `boolean_map`; branch values are checked against the converted type and units. Errors identify the failing request field. This is an additive `abc-e5-input-v1` protocol; no old failed request is reclassified.

The frozen task's `device.event_latch` is the executable selector. The inherited `event_latch_scope` prose describes general apparatus provenance and is not an override. The same public clarification is given to all arms; inputs and numerical law remain unchanged.

Only `public/` and the participant payload may enter the participant context. `host/` contains case bindings, consumers, submissions, execution references, and final judgments. Neither final truth nor hidden checker output is a tool action. The public tool returns physical observations, selected input identity, and an UNKNOWN physical-qualification boundary.

`preflight` never runs science. A LEGAL response is source/unit/domain/type consistency only. A typed consumer is proved separately by a stored observation-to-input edge and the actual executed task hash. Prediction correctness, wrong adoption/rejection, selected service, coverage, and typed consumption are distinct fields. The main arm comparison uses prediction/decision results and full costs, not the fraction that used an optional interface.

## Frozen task scope

The pre-execution freeze chooses three mechanism families with two independent repeats in each of three arms (18 attempts). Sampling phase is reserved and excluded from this finite batch. No scientific outcomes were used to select or revise these cases.

| Family | Current → intervention | Digital-model boundary |
| --- | --- | --- |
| Storage connection | Two equal cells: parallel equivalent 22 µF / 0.3 Ω → series equivalent 5.5 µF / 1.2 Ω, fixed clamp | Ideal static circuit equivalence; no balancing, new circuit solver, or calibration |
| Reset placement | The same 40 µJ shunt moves from 80 ms to 12 ms; event memory is volatile | Timed energy-removal intervention in the existing model; no fabricated reset circuit |
| Package response | 150 µJ rectangular source changes from 20 ms at 0 ms to 40 ms at 70 ms | Prescribed source transformation; no calibrated mechanical transfer model |

The full unchanged service, deadline, independent receiver/energy checks, and physical UNKNOWN boundary apply to every arm. These are new digital tasks, not new hardware observations. A no-advantage or higher-cost outcome remains a valid outcome; the old no-improvement result is preserved.

## Costs and limits

Local preparation peak estimate is 64 MB with 180 MB retained-output cap and 10 GB free-space reserve. The common episode ceilings are 12 requests, 900 seconds, 40 tool calls, and two distinct designs; no automatic retry. The proposed 65,536 maximum output tokens requires S0's actual backend support verification before the paid freeze. The shared finite cycle and cost ceilings remain authoritative.

`costs` in the independent result contains adapter tool counts, explicit acquisition bytes, preflight/format rejects, and tool wall time. S0 must join actual provider tokens/charges, source/payload context bytes, Pi file reads, execution and final-evaluation costs, and rework. Adapter acquisition bytes alone are not a complete cost comparison. Participant source files must be included in the shared bound-file/hash audit.

## Local verification

Run from B's workbench parent using the registered Python, with `PYTHONDONTWRITEBYTECODE=1` and `-B`:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 ABC_SOURCE_ROOT="<S0 battery-world>" <registered-python> -B -m unittest discover -s battery-world/tests/agentlab -p test_abc_interfaces.py -v
```

The targeted tests cover source and domain units, cross-task evidence, payload/registry tampering, Boolean conversion, exact typed branch matching, all-arm information equality, the fixed 18 identities, preservation of the original five failure logs, and rejection before executor dispatch. The consumer-binding check uses a clearly labeled fixture; final evaluation rejects it. No repository-health, real consumer, provider identity, physical, or scientific-result claim follows from these tests.

The CLI only prepares or preflights. `--spec` resolves source/freeze paths relative to its own location; it never instantiates a real executor. S0's existing shared `campaign_abc.py` remains the sole paid/scientific entry point. Update result tables/figures/claims only after S0 hands back actual records.
