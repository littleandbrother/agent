# BFA-058 minimal phase3 contracts — A idle for Pi

Dispatch: `phase-3-controlled-comparison-bf-20261020-001`. Owner: campaign-a. The root phase-state, OWNERSHIP and S0 registered BFA-058 feature were read before implementation. Only the new owned phase3 paths were written. The existing A profile remains model=false/agent=false/native=false. No new environment, worktree or worker; no commit/push or message to the review chat. This is preparation, not completion of the actual comparison/paper feature.

## Minimal entry

From `battery-world/`, using the existing interpreter:

```sh
rtk proxy /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B scripts/campaign_phase3_methods.py conditions
rtk proxy /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B scripts/campaign_phase3_methods.py comparisons --change-json '{"changed_artifact":"D","changed_fields":["timing"]}'
rtk proxy /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B scripts/campaign_phase3_methods.py event-contract
```

The standalone script resolves its own package/config paths and also works from a different cwd. It has four read-only commands: `conditions`, `comparisons`, `event-contract`, `budget`. The conditions JSON is the prompt/condition source. It is prepared for S0's prospective frozen dispatch, not a standalone provider-tool schema. The role action names `check_D`, `submit_D`, `submit_H` describe role separation; S0 maps them to its v2 host tool actions and keeps H and D payload/slot validation distinct.

With packages/python/bfworld/src on PYTHONPATH:

```python
from bfworld.agentlab.campaign20261019 import phase3_methods as m
assert m.classify_change({"changed_artifact": "H"}) == "H"
assert m.impact_scope({"changed_artifact": "H"}) == "task-entry"
assert m.impact_scope({"changed_artifact": "D"}) == "full-feedback-response"
rows = m.comparison_registry({"changed_artifact": "D"})
assert rows[0]["control_only"] and not rows[0]["eligible_as_changed_input_service"]
remaining = m.remaining_budget("ordinary_reflection", total_requests=8, total_wall_s=400,
                               proposal_requests=8, proposal_wall_s=400)
assert remaining["remaining_group_requests"] == 16
assert remaining["remaining_group_wall_s"] == 800
requirements = m.ordered_event_requirements()
```

`classify_change` reuses the frozen pure phase2 classifier (f89b6af3e91136f18ed1bed58fdae20b2e811fc393aa28acec351441b2df5edf). Scope/planning rejects mixed, unknown, forbidden and G changes. Typed classification is not a semantic audit of prose. No actual method text or correct device parameter values were supplied here.

## Three conditions and accounting

`configs/studies/phase3-20261020/methods/conditions.json` defines fixed_h, ordinary_reflection and proposed_method. They share the base H, task/facts/source access, tool/model/evaluator configuration and initial-cache requirements. Ordinary reflection and the proposed structured dependency/event-order method differ only in proposal procedure instructions. Their actual H text must come from the model; no retained successful design, numeric feasible band, hidden label or researcher-written winning H is injected. The shared base instruction plus actual submitted method_text becomes the design H; proposal common prefix plus the condition proposal instruction becomes the proposal prompt.

Every group has one shared 24-request/1200-second cap and at most two distinct D. Fixed H has no proposal stage. Each other group has a proposal subcap of 8 requests/400 seconds; proposal, acquisition, failures, fresh design and confirmation all consume the same group totals. Using the full proposal subcap leaves at most 16 requests/800 seconds, not another 24/1200. All parent/child usage and all elapsed stages count. A valid proposal cap is one; malformed syntax does not consume that valid slot but still consumes requests/time. No automatic new owner or resampling. No-update or no valid proposal retains its actual outcome and costs; unchanged H may receive a fresh design only from the remaining budget. S0 owns complete usage, USD reservations, batch limits and run leases. The pure helper grants no dispatch authority.

Before paid dispatch, S0 must bind matching task/source/information/base-H/model/tool/evaluator identities and a frozen initial cache manifest with separate overlays for each condition. Later cache writes cannot warm another condition. Preserve failed/no-update outcomes and provider identity limits. No prefilled successful values appear in the condition prompts.

## Re-execution controls and event order

The four registered strategies are frozen-trajectory, dependency-recompute, scope-recompute and full-feedback. Registry rows are plans, not executions or service verdicts. Frozen trajectory is a retained negative control only. For this coupled D, both dependency and scope recomputation conservatively expand to a full feedback response, as does the full strategy; there is no claimed computational saving. Global H starts fresh Agent decisions at task entry independently of valid physical exact-input response reuse. A cache hit requires the actual requested input and every consumed identity to match; it is not a new scientific execution.

`evidence-refs.json` binds existing phase1 positive unchanged-input and negative threshold replay data, phase2 full-feedback controls, ordered state and the two existing compressed raw responses. It is HOST ONLY and must not be attached to participant inputs. No simulator or scientific result was created. Historical `replay_admissible=True` can coexist with a wrong changed-input result; it is retained as a historical label, not a new service acceptance. `comparison-registry.json` records all four registered strategies for H and D.

`ordered-event-requirements.json` supplies the contract for S0's new independent evaluator. A cross-reset pending-state witness requires the same captured event source and state lineage with capture < reset < delivery, and no substitute event or postreset reacquisition. Equal timestamps need a sequence/total order. Missing identity/order is UNKNOWN. Delivery before all resets, reset before capture or no reset supplies no cross-reset witness; service is evaluated separately under the fixed task. Phase2 H0 RX46.9ms has no pre-deadline reset; Hprime RX5.6ms precedes its 12.1ms reset. Both latches remain volatile. Success-and-any-reset is not proof of pending-state preservation. These historical values appear only in external host evidence, not condition prompts. S0 implements the evaluator and runs the actual comparisons.

## Verification and next handoff

Nine new pure-contract/CLI tests PASS. They cover stale-trajectory exclusion, H task-entry restart, mixed/forbidden changes, shared proposal budget, failed/acquisition/confirmation costs, exhausted and invalid usage, fixed-H no-proposal, condition cap consistency, and the actual CLI process from another cwd. Exact command/environment, hashes and log are in verification.json. Only the new test_campaign_phase3_methods.py was run; old tests/full init/scientific executions/provider/native dispatches are zero. Eight directly relevant old source/manuscript/PDF files were read back unchanged; there was no all-tree hash scan.

A is idle for S0's actual Pi slot. When the first S0 results arrive, continue with the source-bound main table, failure interpretation and only the new phase3 manuscript/PDF. No phase3 paper was written now. S0 owns shared feature/state updates and import.
