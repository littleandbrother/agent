# BFA-055 phase2 paper and interpretation — complete; A idle

The final external decision is **REJECT_PROMOTION_KEEP_EXPERIMENTAL_ARTIFACT**; the default H is unchanged. H0 (22 µF / 45 ms, RX46.9 ms) and H′ (9 µF / 3.7 ms, RX5.6 ms) both pass the full frozen computational service. Initial physical cache snapshot parity was not established; the gate rejects `PARITY_INITIAL_CACHE_SHA256`, so the pair is descriptive. The 22 µF baseline refutes the proposed necessary capacitance band/late-floor exclusions. It does not refute the separate contiguous-harvest-segment rule or meet the proposal's exact 2 ms conjunctive edge-case falsifier.

Both event latches remain volatile. Both deliver before any reset; H′ resets at 12.1 ms after delivery. The legacy reset-preservation PASS for H′ records success-and-any-reset, not pending-state persistence across reset. The checker was not changed. The original nine-request proposal remains failed at the host contract; recovery of actual model text was posthoc, with no new proposal decision.

New standalone files in `papers/method-reexecution-20261019/`: `phase2-manuscript.tex`, generated `phase2-methods.tex`, `phase2.pdf`, `phase2-binding.json`, and `render_phase2.py`. Read `docs/research/phase2-20261020/methods/actual-interpretation.json` / `.md` for the full source-bound interpretation. The binding records 26 actual evidence files, cost arithmetic, method hash encoding and paper/style/logo hashes. `paper-final/` holds admission, two-pass build logs, input recorder, text/font readback, all-four-page visual review, cleanup and final artifact receipts.

Build only this new paper: from the paper directory, run `rtk proxy /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B render_phase2.py build`. The command reads pinned evidence, compiles two TeX passes, and renders pages for visual review. It never imports/dispatches the provider, Agent, simulator or native engine. A relocated runtime evidence directory can be supplied using `--evidence-root`; hashes must still match. After checking all newly rendered pages and saving a matching visual receipt, `render_phase2.py clean` removes only its new TeX scratch and page rasters. A fresh clone or independent-host rebuild has not been tested.

The actual whole phase uses 25 settled requests (USD0.1766922 upper /0.10124004 cache-aware rate estimate), seven new local computational cases and zero native calls. The H chain is 19 requests; proposal+H′ is 14 requests and more expensive than H0's five. Estimates are not invoices; Codex assistance is UNPRICED_NONZERO and total end-to-end cost is UNKNOWN. All existing failures, A/R NO_GO, strict FIFO FAIL and NOT_ACCEPTED remain preserved; physical qualification stays UNKNOWN. No causal/statistical method advantage, holdout transfer or RSI is established.

This paper update adds **zero** provider requests, scientific executions, native calls or test runs. The recorded 22 MOCK tests are reused. Only the new paper was compiled (two passes); all four pages were inspected directly. The admission receipt checks 78 protected prior-manuscript/style/science/API files, including the old `main.pdf`. No full verification, new environment/worker, commit, push or message to another chat was performed. A is idle.

---

## Prior preparation handoff (historical; pending statements below are superseded)

# BFA-055 minimal H API handoff — A idle

Dispatch `phase-2-core-methods-bf-20261020-001`; latest focus
`phase2-actual-results-focus-20261020`. Baseline
`P2-f7ac8bfc4d5f262ff2736e25298d0c4bddd43b2f2064ae0c48b3bdb42b612977`.
Worktree remains `/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-a-20261019`.
S0 can import the three source/test files listed in `artifact-manifest.json`.
**A is idle for actual S0 execution.** No chapter, manuscript, config expansion,
new environment/worker, paid/native run, commit or push was performed.

## Exact required API

With `battery-world/packages/python/bfworld/src` on PYTHONPATH:

```python
from bfworld.agentlab.campaign20261019 import phase2_methods as m
parameters = m.tool_schema()  # dict: root type=object, oneOf three object branches
raw = {
    "changed_artifact": "H",
    "hypothesis": "MOCK: a toy spelling policy may expose an invalid word.",
    "falsifier": "MOCK: the revised toy controller never consumes the policy.",
    "method_text": "MOCK: compare a toy word to its declared alphabet before spelling it."
}
normalized = m.validate_method(raw)  # dict, or ValueError
assert normalized["method_text"] == raw["method_text"]
assert normalized["changed_artifact"] == "H"
assert normalized["impact_scope"] == "task-entry"
assert m.impact_scope({"changed_artifact": "H"}) == "task-entry"
assert m.impact_scope({"changed_artifact": "D", "changed_fields": ["tx_not_before_s"]}) == "full-feedback-response"
```

The example is MOCK only, unrelated to BF, and must not become the actual H-prime.
`api-examples.json` contains exact executed return dictionaries and full schema.
A proposed H returns hypothesis, falsifier, method_text, changed_artifact=H,
schema_version, decision=propose, normalized changes/evidence_refs, method_sha256,
impact_scope, and status=PROPOSED_REQUIRES_EXTERNAL_SEMANTIC_AND_EXECUTION_AUDIT.
`method_sha256` hashes the normalized string as canonical JSON, not raw UTF-8.
Optional changes default to H/global_prompt. The normalized result contains
computed metadata; the proposal validator expects raw schema input, not its
own enriched output. S0 consumes `normalized["method_text"]` as the H prompt.

`m.validate_method({})` yields a NO_UPDATE dict with EMPTY_PROPOSAL reason.
An explicit no update is `{"decision":"no-update","reason":"..."}`. These
are valid abstentions, not H changes, and contain no method_text or method hash.
D/G-labeled input, device-only JSON/assignments, mixed D changes, unsupported
fields, self-acceptance/qualification and malformed/unbounded data are rejected.
Required propose fields match the implementation contract; there is no required
extra field or required researcher-written method. Empty/no-update is the
explicit negative-control branch. No decisive BF H-prime was supplied by A.

## Entry / feedback and trust boundary

`classify_change(change)` distinguishes typed H/D/G/NONE, mixed/unsupported
changes and forbidden task/world/evaluator mutations. It does not prove prose
meaning. A legal schema alone does not prove a genuine H rather than a disguised
D choice: S0's external semantic audit must check actual model authorship and
method meaning before a retention claim.

`validate_reexecution(change, policy)` keeps F1b fresh task-entry decisions
separate from F1a response reuse. A changed BF D requires a complete feedback
response; fixed-trajectory and suffix reuse fail. A globally changed H restarts
Agent decisions at task entry. Independently qualified full exact-input response
cache entries may still be consumed when actual requested/cache identities match.
This pure helper does not execute or qualify a cache entry.

The additional host-only `confirmation_gate(...)` takes an out-of-band trusted
S0 resolver, never a participant-selected registry. It checks H authorship,
task/information/source/model/tools/evaluator/cache parity, fresh owners/contexts,
actual H/tool/input binding, full independent service and all three episodes'
settled accounting. Failure/UNKNOWN rejects; a fully consistent MOCK remains
MOCK_CONTROL_PASS. It never returns retained=true or a qualification authority.
This optional facts helper does not replace S0's authoritative independent
registry or actual retention decision and is not a prerequisite to invoke the
three required proposal APIs. It cannot authenticate the host resolver itself.

## Verification and pending actual work

22 meaningful MOCK structural tests PASS. They cover D-only rejection,
empty/no-update, fresh H entry, full D feedback, stale cache/replay, field and
information parity, source scope, researcher-vs-model semantic audit, absent
actual input binding, full-service failure/UNKNOWN and unresolved proposal/design
costs. CLI schema and rejection crossed a real local process boundary. Exact
command/environment, source hashes and saved log are in `verification.json`.
No BF simulation or provider call is used by these tests; no full init/health
claim is made. The final schema's explicit root type=object was rechecked.

The existing A preparation profile remains model=false/agent=false/native=false.
Local active feature copy is absent; root OWNERSHIP, local PROJECT and S0's
registered BFA-055 feature agree. Their hashes are in admission.json. A did not
create/edit that shared feature or any shared registry.

Actual proposal, H0/H-prime design, independent service and retain/reject remain
NOT_RUN by A and are S0's next finite registered chain. All phase1 manuscript,
raw science, failures, fees and UNKNOWN records remain unchanged. Phase2 chapter
and complete results report are explicitly deferred until S0 actual results.
