# BFA-061 phase4 minimal preparation — A idle for S0 import

Dispatch `phase-4-transfer-and-improver-bf-20261020-001`; owner `campaign-a`.
Prepared in the existing A workspace; import only the seven new core files below and these small new preparation receipts. Root feature/state/ownership and S0's feature remain S0 single-writer. A's old local PROJECT still names phase3; it was not rewritten. No phase1/2/3 source, paper, shared style, logo or old handoff was modified. No phase4 paper was written.

The module/configuration is ready for S0 integration. Actual G1 formation, H descendants, selection and final tests are NOT_RUN by A. A is idle; S0 uses the existing configured SDK after its own registered source/model/usage/slot gates. Do not hand-write a G1/H/D as a substitute, create another owner or rescue a failed attempt.

## Exact imports and hashes

Paths are relative to the existing `battery-world` root. `artifact-manifest.json` binds every new core/receipt file, including this handoff, and excludes only itself.

| Import file | Bytes | SHA-256 |
| --- | ---: | --- |
| `packages/python/bfworld/src/bfworld/agentlab/campaign20261019/phase4_methods.py` | 22914 | `7520be24a7e23084005a806b54a274a232c94238b22af1d6d2e1a0a8616af752` |
| `tests/agentlab/test_campaign_phase4_methods.py` | 16092 | `2891d364ca03aee20d71c7e23dc068ede3c40056fe43662f9b54c72ef489e33b` |
| `configs/studies/phase4-20261020/methods/frozen-parents.json` | 1939 | `d535ca972aef4cc061d3100b981d676cd502d0d843cf53d223f39c67c7e95386` |
| `configs/studies/phase4-20261020/methods/history-sources.json` | 5123 | `b0b1edc54d7ae584ab493e306dac3b2636403680f8ebb30c286aabb49a4a3958` |
| `configs/studies/phase4-20261020/methods/model-history.json` | 75955 | `7e7f379d80746d0572f6ef75214129a4c08292a4dfe8270b4d9f953308318cf9` |
| `configs/studies/phase4-20261020/methods/protocol.json` | 4144 | `992cb8bfc9611e440e5e3f20abe3b78e944246c1d4c022f0bcd10527ada810d0` |
| `configs/studies/phase4-20261020/methods/public-history.json` | 257661 | `6732821ef52b8006eebd2d19a2c0b313dac822299f49c8747c9c3abfe59c33db` |

`frozen-parents.json` is byte-bound by the module. G0 is the unchanged phase3 **ordinary reflection proposal procedure**, with the same immutable proposal prefix; H0 is the unchanged phase3 base design instruction. There is no actual G1 in any preparation file.

## Exact ABI

Set PYTHONPATH to `battery-world/packages/python/bfworld/src`, then:

```python
from bfworld.agentlab.campaign20261019 import phase4_methods as m
m.g_proposal_schema() -> dict
m.validate_improver(value: dict) -> dict  # raw G or explicit no-update
m.frozen_parent_methods() -> dict  # H0, G0, immutable_proposal_prefix and hashes
m.model_history_packet() -> dict  # MODEL-facing, identical bytes for both arms
m.model_history_packet_bytes() -> bytes  # canonical UTF-8, 75,955 bytes
m.public_history_packet() -> dict  # HOST-ONLY complete public-trace audit packet
m.history_packet_bytes() -> bytes  # HOST-ONLY 257,661-byte original packet
m.formation_gate(value: dict, *, receipt: dict) -> dict  # trusted S0 facts only
m.formation_allocation(actual_requests: int, wall_s, usd) -> list[dict]  # 3 shares
m.select_descendant(rows: list[dict]) -> dict  # exactly 2 registered siblings
m.arm_budget(arm: str, lineage: int, *, usage_rows: list[dict], formation_actual=None) -> dict
```

`validate_improver` accepts raw `changed_artifact=G`, `hypothesis`, `falsifier`, `proposal_procedure`, optional decision=propose/schema_version; or `{decision: no-update, reason: ...}` / empty object. Only a natural-language proposal procedure can vary. H/D fields, changed selection/budget/model/evaluator, participant retention and mixed updates are rejected. An unchanged G0 procedure normalizes to no-update. Legal prose is not independently proved to be a genuine G change. Do not feed enriched normalized output back as raw proposal input.

## Participant history: use the 75,955-byte projection

`model-history.json` and `model_history_packet_bytes()` are byte-identical. SHA-256 `7e7f379d80746d0572f6ef75214129a4c08292a4dfe8270b4d9f953308318cf9`. The canonical UTF-8 dict plus frozen-parent wrapper was checked below the existing 96,000-byte tool-response cap. S0 must also bound the complete actual tool response envelope; use the existing UTF-8 compact serializer. Do not return the 257 KB complete audit packet through a G/H tool.

The full unchanged host packet SHA is `6732821ef52b8006eebd2d19a2c0b313dac822299f49c8747c9c3abfe59c33db`. It contains four complete original public episodes: the phase2 original failed H proposal, then the first phase3 formal pulse-task complete-raw D and ordinary-reflection H/D pair. It is a declared fixed sample, not the full campaign. Phase2 remains INCOMPLETE_OR_STOPPED with its original 9 charged requests; no posthoc rescue is relabelled as the original success.

Projection is mechanical and outcome-independent: retain actual goal/instruction/limits/tool hash, **all 29 tool actions** (9/7/5/8 by episode) in order with unaltered complete input objects, all H proposal attempts and errors, actual final status and every recorded episode cost. Decode serialized JSON; replace Python definitions and repeated proposal-schema bodies with their original canonical SHA/byte count; tool-result arrays longer than 12 retain count/SHA/first6/last6; deduplicate identical projected results in a SHA-indexed pool; omit startup/core wrappers and assistant prose. Every call keeps its original full result SHA and original trace index. Original protocol, entire public trace and result hashes remain bound per episode in both packets. `history-sources.json` binds 12 raw episode files plus two original parent/instruction config files, read back unchanged.

No O0 input/result, final-test payload, reserved phase3/stage4 input or final feedback was read or inserted. The actual G0/G1 formation/descendant prompts all use this **same projected information condition**, H0 and source bytes. No researcher-written correct strategy or final answer replaces a historical observation. Full originals remain host-side for audit.

The first projection draft was 84,637 bytes and the export gate rejected it. Removing all assistant prose under one fixed rule brought it to 75,955 bytes; all tool actions, method proposals, costs and final statuses remain. Receipt: `model-history-export.json`.

## G1 actual formation receipt and authority

S0 performs exactly one prospective actual SDK formation event, maximum 8 provider requests / 400 seconds, then freezes its raw response and procedure once for all three G1 lineages. This is **one G1 formation event**, not three independent trainings. Three pairs of fresh G0/G1 descendant lineages are conditional on that common event. G1 may change only proposal_procedure; immutable prefix, H0, tasks, evaluator, budgets, source access, tools and model stay fixed. Neither G nor H proposal roles may check or submit D.

`formation_gate(raw, receipt=...)` requires: evidence_kind=ACTUAL_PROVIDER; author=participant-model; semantic_component=proposal_procedure_only; usage_status=SETTLED; automatic_retry=false; reported_models=[deepseek-flash]; unknown_usage=[]; formation_event_count=1; nonempty formation_event_id equal registered_formation_event_id; 1..8 distinct provider_request_ids with requests equal their count; finite wall_s<=400 and usd; model_configuration_sha256; raw proposal_sha256=m.digest(raw); history_sha256=m.HISTORY_SHA256; model_history_sha256=m.MODEL_HISTORY_SHA256; H0_sha256 and G0_sha256 equal frozen-parent hashes. It returns normalized G/no-update, shares, one common event count, retained=false and qualification_authority=NONE.

Those supplied facts must be verified from S0's real provider ledger, actual input/output/tool/trace and independent semantic audit. A dictionary or passing MOCK test cannot authenticate model authorship, prove no disguised H/D prose, prove model weights identity, or grant a freeze/promotion. Bind actual SDK/config hashes and retain alias-only model limits. Invalid/failed/no-update G1 and actual charges are kept; never manufacture a successful G1 or resample a replacement. Any fallback use must retain its failed/no-update G1 label and full allocated cost, not count as G improvement.

## Descendant selection ABI and final-exposure gate

Every H sibling is independently proposed from the same H0/history using frozen G0 or G1, never by editing its sibling. H raw schema/validation is the unchanged phase2 `tool_schema()` / `validate_method()`. Every selection/final D starts from fresh task-entry decisions, with the same complete information, model/tool/evaluator identity, immutable initial exact-input cache and isolated overlays. Cache hits do not reuse Agent decisions or enlarge the logical two-D exposure.

`select_descendant` takes exactly two rows with these exact fields:

```text
descendant_index: 1 or 2
proposal: original raw H proposal or retained invalid/no-update raw value
proposal_status: SUBMITTED only for an admitted actual submission; otherwise original failure/status
semantic_H_eligible: trusted external bool
proposal_usage: {requests, wall_s, usd, status: SETTLED}
selection: [
  {task_id: b-pulse-fast, service_status, wrong_service_judgment: bool, usage},
  {task_id: b-volatile-reset, service_status, wrong_service_judgment: bool, usage}
]
```

Failed/no-update proposals may have empty selection arrays; every actual consumed episode still appears with its cost. Independent service_status is PASS/FAIL/UNKNOWN/INCOMPLETE/CENSORED. The wrong-service-judgment flag is S0's independent diagnostic, not the participant's claim. Missing/UNKNOWN accounting stops instead of becoming zero. Unexpected fields (including final results), other/duplicate task IDs, duplicate descendant indices or third siblings are rejected.

Among admitted H descendants with both selection records, choose more complete-service PASS, fewer wrong service judgments, fewer **proposal plus both selection charged requests**, then smaller descendant index. Equal formation share within the arm does not affect sibling ranking, but is charged in arm accounting. The result retains both raw rows and per-candidate metrics/costs, selected_method_text, and exact selected_H_text = unchanged H0 + two newlines + selected method_text. If neither is admissible, the exact unchanged H0 is returned as H0_FALLBACK_NO_ADMISSIBLE_DESCENDANT, without changing default H0. A valid zero-PASS descendant may win the registered ranking; selection is not promotion or success.

S0 seals all six arm/lineage selected_H texts and hashes before exposing **any** final input to actual participants. This module does not read final results or implement a runner. `select_descendant` must never be re-invoked to tune from final feedback. The anonymous final-1/2/3 budget slots carry usage only, not final task content or verdicts.

## Complete cost and finite slots

`formation_allocation(q, wall_s, usd)` returns three lineage-indexed shares. Requests use floor(q/3)+one for the first q%3 slots; wall/USD use decimal-string thirds with the final division residue retained in slot3 so totals conserve. Do not count these as three global events. Count actual global formation usage exactly once. Zero is allowed only for pre-dispatch arithmetic, not as evidence of a real G1.

`arm_budget(G0|G1, lineage=1|2|3, usage_rows=..., formation_actual=...)` requires usage rows `{slot, usage}` with unique slots from ARM_SLOTS in protocol.json: two H proposals, each descendant's two selection D episodes, three final D episodes. Each usage is `{requests, wall_s, usd, status: SETTLED}`; numeric wall/USD may be numeric scalars or decimal strings. Per-proposal cap8/400 and per-D cap12/800; complete per-arm cap120/6600/USD10. All failed/no-update/unselected proposal, design, check and confirmation costs stay charged. G1 receives the same complete actual formation object `{requests, wall_s, usd}` on each lineage; the helper allocates its respective share. G0 must not receive/recharge the G1 formation event, and its own proposal/selection/design/failure costs must not be omitted. Returned remaining budgets have no dispatch authority.

At all per-episode maxima, an arm's nine episode slots use100 requests/6400s before its allocated formation share. H0 controls are separately registered common episodes counted once globally, not free unreported comparisons or copied costs in both arms. The registration's 73-episode /860-request/54400s global ceilings and USD100 cap remain S0's responsibility. Request estimates are not invoices; Codex assistance is nonzero unpriced and full end-to-end cost UNKNOWN.

## Actual preparation verification, limits and next handoff

Eight distinct new pure/MOCK contract controls PASS on the final source/config versions (`targeted-tests-attempt3.json` binds all seven core hashes). Three software suite invocations occurred: first7 PASS/one test-scope false positive; second8 PASS before the model-projection supplement; third8 PASS on the final projection ABI. Do not sum repeated invocations as24 distinct tests. The first error/log and pre-projection verification remain preserved. The erroneous assertion scanned exclusion metadata saying phase4/O0 were absent; the corrected assertion checks actual original participant input/public-trace payloads. No history bytes were changed to pass.

Final controls cover G/H/D mixing and forbidden edits; actual-author/source/usage/one-event gate; unchanged G0/H0 and source-bound entire host histories; same-byte independent return values and hash-tamper/oversize rejection; <=80000-byte model export and <=96000-byte parent wrapper with every original tool input/cost/status preserved; PASS/error/full-request/stable-index ranking; final-feedback/duplicate-task/unsettled-cost rejection; invalid/no-update/censored fallback and retained charges; formation allocation and complete arm caps/no replacement slots.

Exact final command/environment/log are in verification.json and targeted-tests-attempt3.json. Reproduce only this changed surface with the existing interpreter, PYTHONDONTWRITEBYTECODE=1, PYTHONPATH=<battery-world>/packages/python/bfworld/src, and `python -B -m unittest discover -s tests/agentlab -p test_campaign_phase4_methods.py -v`. No old test suite, full init, SDK smoke, provider request, simulation, native dispatch, new environment/worktree/worker, commit/push/upload was run. All20 directly relevant frozen old files and14 raw history/parent sources read back unchanged; this is a targeted audit, not an all-tree audit or repository health claim.

The preparation checks do not establish model-authored G1, H descendants, service improvement, statistical evidence, heldout transfer, physical qualification or RSI. No actual phase4 O0/final result was inspected. Preserve A/R NO_GO, FIFO FAIL, NOT_ACCEPTED, old failures and UNKNOWN. All actual registered execution belongs to S0. A is idle for the next actual Pi slot; no manuscript or longer report is pending in this package.
