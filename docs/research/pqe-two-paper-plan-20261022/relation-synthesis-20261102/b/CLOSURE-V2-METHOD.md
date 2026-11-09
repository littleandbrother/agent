# Actual component-contract companion expansion

New source: `semantic_closure.py`, SHA256 `dbf4152667a237c8509d23dc06d6079d70abec87a105dbf3707237bb629640d6`. Frozen v1 `semantic_search.py` and its four cells are unchanged. No S0 stage2 consequences or new A tasks/results were read for this revision. The direct authorization was S0's pre-freeze review request to implement the missing candidate → actual facts → obligations → companion edge, within the same package.

`ClosureFactory` subclasses the frozen factory and has the same generate/select interface. `DeterministicController` can receive it unchanged. For DOOR it calls the original `pqe20261024debt.facts.design_facts(design, task)` and original `obligations.semantic_checks(facts)`. A candidate's fact design hash must match. Each generation stores full actual facts/checks, newly applicable obligations, every accepted companion node and the consumed check/dependencies/refs for its transition. The original fixed holder macro is excluded from v2's semantic seeds.

The seed changes only the producer (`holding_component=lp_fifo`) when a public pending coverage question and the actual producer fact permit that conditional route. No read, durability or clear policy is bundled into that seed. The engine inspects actual resulting contracts, then enumerates authorized categorical/boolean values of a current unmet check's dependencies. A subsequent edge must satisfy that check or change its actual support so another companion can be examined. Removing the producer or disabling the release does not count as discharging its duty. Dynamic unknowns do not become static failures, and no numeric model parameter is searched as a logical proof.

The minimum actual identity-prefix chain is:

| Node | Actual candidate change | Actual source check | Interpretation |
|---|---|---|---|
| `closure-7c2766e715b69515b23b` | enable holder only | CONSUMPTION false, from `holder.production`, `program.read` | New producer lacks an enabled reader |
| `closure-dddc0856b632c5a31a84` | read_source → holding_then_contact | CONSUMPTION true | Companion derived from the preceding unmet contract |
| `closure-7d1b0da6e98db0111167` | optional clear_after → early | RELIABLE_HANDOFF false, from `holder.clear`, `pending.created` | An unguaranteed release remains an unmet static companion |
| `closure-e9552add2c8f23de53f4` | optional clear_after → save | reliable handoff supported by durable SAVE | Alternative under the actual persistent parent |
| `closure-3d9dc0cf95eea9fa9ad8` | optional clear_after → ack | reliable handoff supported by actual receiver ACK | A second supported alternative |

The three clear nodes are siblings after the read node. Global design deduplication does not separately retain early → already-present save/ack cross edges; those are not claimed as observed continuous repair edges. Both designated prefixes contain the producer → unmet reader → derived read companion chain and both supported clear alternatives. Source fact and node data are in `closure-v2/*-on.json.gz`; compact concrete trails are in `closure-v2/freeze-receipt.json`.

Capacity/retention are UNKNOWN after enabling the producer. Never/expiry is not refuted and no static need to clear is invented. Optional clear probes expose their actual handoff checks. Static companion closure admits a bounded full probe; it proves neither coverage, energy, identity recovery nor complete service. Early startup is explicitly a discriminating hypothesis with `coverage_satisfied=false`; meeting a startup bound does not satisfy coverage. Charge/headroom is also conditional and can be refuted by the original consumer.

The two new on pools contain 28 and 29 legal distinct designs, versus off 24 each. Common raw pools remain identical on/off. All four selected designs are exactly identical to frozen v1: identity-on still changes startup only, saved-on still changes C/ESR only, and both off designs are unchanged. Neither selected on candidate introduces a component duty. This demonstrates a source-factual closure generator among alternatives, not an executed component-closure mechanism or a measured benefit from that generator. S0 must keep that distinction when deciding whether formal comparison is justified.

Actual v2 generation cost: 63 original design-fact calls, 878 structural validator calls, 6 additional real geometry-cache misses, 930 cache hits, zero new software tests/full consumers/provider calls. B cumulative cheap is 12/16 and software remains the original 10-case 7 PASS / 3 FAIL receipt, with no rerun. This normal generation record is not a replacement passing test receipt. S0 retains its own narrow check allocation.

The engine is bounded to 48 fact nodes per generation and 12 nodes/depth4 per companion tree. These are developer search limits, not scientific certificates. For LC an actual source-bound fact callback must be injected to claim companion closure; without one the adapter is UNAVAILABLE and any non-component hypothesis remains unqualified. The layer does not invent a holder, independent RTC, ideal air or a new LC platform.

Reproduction uses the registered environment and `freeze_closure.py`; the script writes exclusively and intentionally refuses to overwrite the existing `closure-v2` evidence. Do not rerun it as an uncounted check. S0's original full evaluation budget and finite stop gates remain authoritative; no further B tuning or independent execution is proposed.
