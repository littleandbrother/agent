# Case and observation implementation handoff

This document maps a sealed digital study to portable saved records. Resolve a
`data_id` through `data/manifest.json`; verify its hash before inspection. Paths
below name archived snapshots, not live modules to import. `E_reproduce.py` reads
saved outputs only. No scientific runtime, model account or installed SDK is a
dependency of the arithmetic reproduction.

## Cases and declared laws

| Case family | Complete saved law / source | Intervention and sufficient control | Boundary |
|---|---|---|---|
| E2 storage clamp | `p1-mechanisms/structural_witnesses`, `structural-results/pairs/0`; analytical and separate step implementations in `implementation-interfaces` | Two worlds have 3 V / 5 V clamps; 20 microW for 2 s, zero initial energy, 30 microJ service and 1 V residual rail. Current C=10 microF; common legal C=4 microF separates -14 / +8 microJ margins. Complete static M(C) includes clamp, residual energy and legal domain. | Ideal capacitor, prescribed source, no leakage/intervening work. Current voltage trace cannot identify the inactive clamp. |
| E3 reset memory | `p1-mechanisms/structural_witnesses`, `structural-results/pairs/1`; `event_memory`, `numeric_memory`, `event_program` in `implementation-interfaces` | Capture at 1 s, transmit at 4 s, deadline 5 s. Common added outage from 2 to 3 s distinguishes volatile from retained pending state. Complete static transition rules also suffice. | Ideal retained latch, not a qualified powered NVM write or continuous sensor. |
| B transient controls | `p1-mechanisms/b_reference/base` plus `case_patches`; seven `reference-b-*` records | Fast/slow/late source, ESR=150 ohm, absent energy, latched/volatile reset. Base source is 7.5 mW over 0–20 ms, dt=0.1 ms, 100 ms receive deadline. Nested case patches replace/override the declared base fields. | Expected-control agreement includes intended service failures. Source calibration UNAVAILABLE; all physical qualification UNKNOWN. |
| Main four tasks | `p3-protocol/tasks`, `p3-provenance-conditions`, `p3-main-tables` | Pulse-fast, volatile reset, latched reset and C-lite query derivative. Design budget counts checks, response queries and confirmation against the same two-distinct-design allowance. | Four public digital tasks; per-task legal ranges are frozen by task, never a pooled unconstrained design space. |
| C-lite query | Complete derivative in `p3-provenance-derived-case` | Ideal 20 microW DC for 30 s, 1 microW idle, 50 microJ reply, query at 2 s, reply by 7 s and age <=5 s; C=25–100 microF, ideal 2 V ceiling. Query issuance, capture, matching, causal order, deadline and freshness are separate gates. | Synthetic single query; token 1 is one virtual query, not a secure multi-query RF system. Registration-time NOT_EXECUTED is historical; later actual results are separate. |
| O0 event service | Full parameterized task `p4-o0-task.v1`; `p4-phase4_interfaces` | Six-hour light/source segments and RMS waveform; zero initial C energy; declared RMS sample, wake and committed-write costs. Start >0.05 g for 3 s; stop <0.01 g for 60 s; equality resets confirmation. Receipt <=10 s, encoded error <=1 s, active keepalive <=120 s, no idle false events. | Lux is metadata, not converted to watts; added sensor, clock, NVM and RF costs are digital assumptions. |
| New O final | All nine original rows in `p4-final-details` with task `p4-o-unexposed-waveform-v1` | Five submissions match 8 events and pass energy. Two one-second designs fail the encoded stop times by 1.004 / 1.103 s. Three 0.75-second designs pass. Four have no submission. | Waveform withheld during formation/selection, then supplied to final designer; not a hidden final input during final design. Poll/retry differ and H0 also passes. |

The seven transient input laws are fully encoded by the saved base and patches;
raw control records bind input SHA and separate service/rail/physical verdicts.
The code snapshots preserve mechanism and evaluator versions. A portable data
check is not a replacement for source calibration or a new numerical run.

## Observation route and real consumer edge

1. Discover/propose: initially visible task, current interface, legal actions,
   general source catalogue and schemas; target fields/expressions are not given
   as relevance labels in the live E5 condition. Bind provider/run identity,
   visible-input hash, relation and applicability domain.
2. Acquire: preserve original source bytes, source hash, source-local unit map,
   costs and immutable acquisition receipt. A field selected from a supplied
   source is not a new physical measurement.
3. Construct or select: JSON Pointer selection or a bounded JSON AST, at most
   64 nodes, depth 8, 8 MB source and 32,768 vector elements. Bind units, output
   type and legal-domain constraints. These limits bound interpretation, not
   source calibration.
4. Independently qualify on the source: verify unit dimensions, declared domain,
   scalar relation and source/code identity. A self-signed success string cannot
   qualify an observation. Preserve tampered, out-of-domain, uninformative,
   exhausted-budget and complete-static controls.
5. Consume: the actual typed design policy admits no more than three strictly
   typed equality branches. Boolean true does not match numeric duration 0.001.
   Bind full executed input hash, observation input edge and execution identity.
   Echoing a value or attaching it to a score log is not consumption.
6. Decide and evaluate: preserve unchanged/changed design and independent full
   digital service. Consumption does not establish causal necessity, benefit
   over complete static information, novelty or physical qualification.

The original E5 proposal omitted the leading JSON Pointer slash and exhausted
its one-valid-proposal admission route; all six charged requests remain. The
separate `POSTHOC_HOST_ADAPTER_REEVALUATION` evaluates an already generated energy
relation: TX=28.8 microJ versus reserve=23 microJ. Its original Boolean policy
selects 15 microF/45 ms instead of 10 microF/45 ms, and saved nominal service
changes FAIL to PASS at 46.9 ms. Complete static passes already at 10 microF/0 ms
and 5.6 ms. This is an executed engineering edge with a post-hoc qualification
revision, not a prospective success to add to the formal denominator.

All twelve formal live-E5 groups are indexed in `p3-main-tables/e5_audit`.
Seven complete: six selection, one construction, six changed designs and one
unchanged. Four fail source-local unit binding; a fifth fails typed consumer
matching. The five original `p3-failure-gateway-*` JSONL files are retained.
They are not repaired/replayed in this deliverable.

## Frozen implementation map

| Saved source ID | Inspection entry points | Role |
|---|---|---|
| `implementation-b` | `simulate_b` | Transient loaded rail, stored energy, reset/program/receiver relation. |
| `implementation-interfaces` | `analytic_clamp`, `numeric_clamp`, `event_memory`, `numeric_memory`, `judge_facts`, `select_observation`, `construct_observation`, `verify_observation_audit` | Structural witnesses, strong static facts and early researcher-specified acquisition/construction controls. |
| `implementation-bf_interfaces` | `public_raw`, `rich_facts`, `model_source`, `e5_contract`, `validate_discovery`, `replay_observation` | Source-bound public interface and discovery contract preparation. |
| `implementation-phase2_discovery` | `validate_proposal`, `evaluate_proposal`, `validate_policy`, `validate_request`, `bind_acquisition` | Bounded AST/unit/domain checks and strict typed policy. |
| `implementation-phase3_interfaces` | `project_condition`, `encode_packet`, `decode_packet`, `validate_equal_information` | Equal-information initial JSON/table projection, preserving type and empty values. |
| `p4-phase4_interfaces` | `validate_case`, `validate_candidate`, `evaluate_candidate`, `reference_events`, `evaluate_service`, `public_view` | O candidate and event/encoded-time evaluator; host truth remains outside public response. |
| `p4-phase4_methods` | `formation_gate`, `select_descendant`, `arm_budget`, `model_history_packet` | Frozen parent/procedure exposure, single G1 formation and budgeted selection. |

Every snapshot SHA and its top-level definitions appear in the data dictionary.
The version/exposure index binds protocols and selected method hashes. H0 remains
unchanged. The final selected-method canonical hash is
`baa1d01ffe5a4b35fd74d5f2635f68e3f24c2b84df5b203c3168e7be51b722d5`.
No archived source is executed during this handoff. A future change requires the
coordinator's own research-feature declaration and preserved baseline, budget,
negative controls and falsifier; this final-paper task authorizes no new runs.
