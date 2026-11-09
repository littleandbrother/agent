# Frozen B interface and handoff

Frozen algorithm: `semantic_search.py`, SHA256 `37d118f6c984194c2b8df5be4091114928a5c7993ce0485411f99c8220d80e81`. The full source manifest, per-prefix hashes and actual generation costs are in `frozen-prefixes/freeze-receipt.json`. Source is frozen before B sees new A tasks/results or any new complete evaluation consequences.

## Small API

Load this directory's `semantic_search.py` via importlib with the registered bfworld PYTHONPATH. It imports DomainSpace but executes no consumer or provider. Public facts and static validation are injected by S0; complete original family results are required.

```python
factory = SemanticFactory(public_contract, common_initial_design,
                          validate_fn=common_static_validator)
state = build_state(family_result, prior_result, public_contract)
pool = factory.generate(parent_design, state, seed=314159, round_index=0,
                        relations_enabled=True)
chosen = factory.select(pool, seen_keys=[factory.semantic_key(parent_design)],
                        parent_id=public_parent_id)
# chosen includes design, parent_id, raw_patch, effective design_patch,
# normalized_inactive_fields, derivations and full selection ordering.

controller = DeterministicController("R", factory, common_initial_result,
                                     scope=public_scope, seed=314159,
                                     max_new_candidates=6)
action = controller.step()
# S0 evaluates action['design'] on the entire unchanged original family.
controller.update(unchanged_public_family_result)
controller.snapshot()  # contains all generation records, states and ancestry
controller.stop()

# D uses the same class, replacing only condition="D".
# G submits arbitrary authorized whole designs through the common validator.
g = FreeJointInterface(factory, common_initial_result, scope=public_scope,
                       seed=314159, max_new_candidates=6)
action = g.submit(full_design, parent_id=g.root_id)
g.update(unchanged_public_family_result)
g.finalize(previously_evaluated_full_design)
```

`update` must include the exact submitted `design` and every original `condition_id` or `task_id`. Every member must bind to the same complete design. Invalid/incomplete execution remains UNKNOWN and ends dependent deterministic dispatch. An initial all-condition PASS stops with zero new slots. The initial is always excluded from the six new design slots. No evaluated failed parent is deleted; all conditions can expand failed parents or restart from the initial. G may use `candidate_tool` for the same ordinary joint pool without semantic suggestions, or freely submit outside that pool. The G wrapper's zero-model field describes the wrapper only; actual G model requests remain externally accounted by S0.

## What is consumed

State retains raw operation occurrence counts, source pointers, original public service gates, supported observations, explicit bound negative relations, model-domain status and pending service with cause UNKNOWN. Stage counts differ from the old distinct-record capability signature. Identity progress is a prior explicit conflict no longer observed under the new complete public result, without claiming global identity repair. It does not require count gain. A SAVE-to-wire shortfall remains pending rather than an inferred physical failure.

General candidates: 32 proposals, interleaved seeded axis and joint actions including four full-domain draws before truncation. The same parent, seed and round produce identical common raw proposals and RNG state with either switch. Normalization removes only source-declared physically inactive holder fields. Enabling a holder with active read/clear is permitted. The injected common validator rejects static domain/assembly violations equally.

Semantic candidates: the on condition consumes pending kind, public domain/component coefficients and actual program contracts. It adds at most the available rule interventions and preregisters predictions, side effects and expected observations. Selection checks design-level predicates (equalities, bounds, TX charge algebra); field intersection and candidate hashes never rank candidates. General candidates that happen to satisfy a semantic constraint can also be selected, with the constraint consumption recorded. Priorities are fixed developer choices, not learned policy weights or proven causal strengths.

TX probe algebra: `Q = I_tx*t_tx + I_write*t_write`; available planned margin is `tx_gate_v - brownout_v - tx_reserve_v - ESR*I_tx`. Reduce ESR within the public domain and size C so `C*margin >= Q`, when representable. This is a conservative conditional probe of the declared load with the existing gate, not a voltage-coverage certificate. Larger C can delay boot and change source loading; full consequences may refute it. An early-start probe uses the legal startup lower bound above brownout and preserves other active settings.

Holding alternatives include durable-SAVE release and actual-ACK release. Both retain source-bound paid operations, load/retention/overflow uncertainty, and no future gateway oracle. LC uses its existing domain and public program; no holder, separate RTC or ideal air is introduced. LC early-start references the actual LC consumer; sample cadence uses explicit numeric service intervals only, never assumes that a domain maximum meets service. Unsupported clock causes remain pending. This interface is executable synthesis over a few developer rules, not a learned H/G mechanism, certificate, or universal cause diagnosis.

D/R share parent/archive/restart logic: best observed complete-service progress, initial restart and least-expanded behavior-diverse parent alternate deterministically. All failed nodes remain eligible. Ordinary selection rotates joint, full restart and axis preference with parameter novelty. R alone consumes semantic constraints in generation and selection. These are zero-model developer algorithms; their comparison with G is not a same-model causal ablation.

## Four frozen candidates

`frozen-prefixes/candidates.json` is the direct S0 input. Each cell links the original compressed public prefix and a full compressed generation/selection artifact. Each prefix must use its own three original tasks. B did not run a complete consumer.

| Prefix | Relation on patch | Relation off patch | Actual generation change |
|---|---|---|---|
| identity-progress | startup_v 3.2 → 1.9 from current legal domain | brownout, mechanism, startup, tx reserve and holder enable | 24 → 27 distinct legal pool designs; selected designs differ |
| saved-undelivered | C .0001 → .00025702811244979917 F; ESR 49.80630328737728 → .1 Ω | debounce, mechanism, persistent queue, tx gate and backoff | 24 → 28 distinct legal pool designs; selected designs differ |

Both pairs have identical common raw proposals, facts hash and RNG before/after. The first on candidate is a simple one-field change, not forced component complexity. The second is an explicitly uncertain charge/headroom intervention. Original complete service and scientific benefit are UNKNOWN until S0's original 12 full inputs; no comparison task was read to choose these rules.

## Verification and actual cost boundary

The first and only B software run is preserved as `direct-checks.json`: 10 cases, 7 PASS / 3 FAIL. The first failure incorrectly required equality of raw operation counts when the old distinct-stage signature was equal; actual raw capture/SAVE/TX occurrences decrease after repeated identities disappear. Two later cases used a state cache populated after that assertion, and therefore stopped at KeyError before their substance. The check source now uses non-increase and independent state construction; B did not rerun it. S0 may perform the required narrow readback in its own remaining software allocation. The corrected source does not turn the old receipt into a pass.

Frozen normal generation independently records three prior-conflict disappearance observations, both SAVE/ACK handoff alternatives, identical common RNG/facts and actual selected-design changes. These are normal work outputs, not a replacement software-suite pass or full scientific evaluation.

Actual freeze: 716 pure structural validator calls, 6 real static-geometry cache misses (B cheap 6/16), 705 geometry cache hits, 20 caught static rejections. Some validation failures occur before geometry, so hits+misses need not equal validator calls. Full consumers 0; provider requests 0. The first software fixtures make no scientific calls. No init/full suite or repository-health claim was made.

The corrected assertion was a test correction. A pre-freeze direct source audit additionally bound negative relations to design/result/condition, rehashed state after update, and constrained LC references/cadence to its actual public program. These occurred before new complete outcomes; no result-driven tuning. Old failed receipts, sources and results remain unchanged. Root feature/progress/session-handoff are S0-owned; this document is the B-side handoff.
