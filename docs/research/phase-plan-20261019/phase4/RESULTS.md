# Phase 4: frozen transfer and improver lineages

Status: finite work packages complete; independent phase exit review pending. Paid and new participant dispatch closed.

## Result and decision

Keep the unchanged base method H0. All 30 effective selection cells passed. On the 27 final cells, H0 passed 7/9, G0 descendants passed 6/9, and G1 descendants passed 8/9. The 18 final digital task cells all passed; differences occur on the new O waveform. These are three descendant-lineage pairs conditional on one common model-authored G1 formation, not three independent G1-training replicates. The small descriptive difference establishes neither stable RSI nor physical product acceptance.

| Final arm | PASS / all cells | Submitted FAIL | Incomplete (retained) | Nominal judgment disagreements | Final requests | Final USD upper estimate |
|---|---:|---:|---:|---:|---:|---:|
| H0 | 7/9 | 1 | 1 | 1 | 45 | 0.3416751 |
| G0 | 6/9 | 1 | 2 | 1 | 40 | 0.4800981 |
| G1 | 8/9 | 0 | 1 | 0 | 45 | 0.5159961 |

Incomplete cells are not zero-error successes. The two submitted failures claimed PASS despite failing the independent event-time gate. All four incomplete final cells ended at SDK stopReason `length`, with 32,768 output/reasoning tokens and no submitted D; no extra attempt or extended response allowance was added.

## All final cells

| Lineage / method | Stretched volatile port | Half-power virtual query | New O waveform |
|---|---|---|---|
| L1 H0 | PASS | PASS | FAIL |
| L1 G0 | PASS | PASS | TOKEN-CENSORED |
| L1 G1 | PASS | PASS | PASS |
| L2 H0 | PASS | PASS | PASS |
| L2 G0 | PASS | PASS | TOKEN-CENSORED |
| L2 G1 | PASS | PASS | TOKEN-CENSORED |
| L3 H0 | PASS | PASS | TOKEN-CENSORED |
| L3 G0 | PASS | PASS | FAIL |
| L3 G1 | PASS | PASS | PASS |

The final D participant receives the complete frozen facts for its current task, including the waveform. Unexposed means withheld from G/H formation and selection; it does not mean that the final design participant could never inspect its current task. The two digital input files and O waveform were frozen before the first O0 participant episode. S0 had host custody of the inputs; host blinding is not claimed.

## O0 controls and final O transfer

O keeps the original A0 hardware, six-hour solar source and zero initial energy: capacitance 15 mF, PV area 15 cm², confirmed start above 0.05 g for 3 s and stop below 0.01 g for 60 s, event delivery within 10 s, timestamp error at most 1 s, and active keepalive at most 120 s. Wake, sample, sensing, NVM and transmission energy are included in this digital model. Powered RMS and wake laws are uncalibrated ideal assumptions.

The initial O0 candidate submitted the same 1 s sampling design and reused the same physical response as the fixed rich-state control: both pass all 8 events with 18 accepted packets. Fixed periodic 60 s reporting matches 0/8 events and fails. The candidate also checked a 1.5 s design that failed event timing; that negative check is retained. Its final UNKNOWN self-judgment cited dark-observation and inherited A/R requirements. The independent O event gate PASS does not override that broader product boundary or make UNKNOWN a physical-acceptance error. The candidate shows no advantage over the rich-state control.

On the new O waveform, H0 is 1 PASS / 1 submitted FAIL / 1 token-censored; G0 is 0 / 1 / 2; G1 is 2 / 0 / 1. All five submitted designs pass the energy gate and match all eight events, but two 1 s sampling designs fail event-time accuracy. For L1 H0, encoded timestamp errors of 1.004 s and 1.103 s exceed the 1 s limit despite 18 accepted packets. The three passing submitted designs use 0.75 s sampling; H0 independently finds one of them. Therefore the data do not establish a mechanism unique to G1. Full per-event timestamps, independent checks, submitted D, checked alternatives and cache provenance are in `final-details.json`.

The O event gate does not implement every inherited A/R metadata/reporting requirement or uninterrupted dark-segment observation. Original A/R fixed-space NO_GO, dark service FAIL, strict FIFO FAIL and product NOT_ACCEPTED remain. There is no physical qualification.

## Formation, selection and information boundaries

One actual G1 formation consumes 3 requests / USD 0.0269157. All twelve actual H proposals consume 43 requests / USD 0.4491399. All twelve are retained as procedurally eligible; eligibility is not semantic correctness. Fifteen UNKNOWN_PUBLIC_SOURCE tool failures occur in five H episodes, three each, including L3-G0-h2; these are charged tool errors, not UNKNOWN provider usage. No parent or sibling was rewritten after outcomes.

| Arm | Selected H child | Effective selection cells | Selection PASS |
|---|---:|---:|---:|
| L1-G0 | 2 | 4 | 4 |
| L1-G1 | 2 | 4 | 4 |
| L2-G0 | 1 | 4 | 4 |
| L2-G1 | 2 | 4 | 4 |
| L3-G0 | 1 | 4 | 4 |
| L3-G1 | 2 | 4 | 4 |

All six selected H texts were frozen together before any final episode began. The fixed ranking uses more service passes, fewer wrong nominal judgments, fewer charged proposal-plus-two-selection requests, then stable child index. All six H0 selection controls also pass, giving 30/30 effective selection cells. Both selected and unselected children, both selection tasks, and formation are charged. G0/G1 proposer inputs use identical H0 and identical seen-history packets; O0 and final tasks were excluded. Final H0 and learned-H conditions do not have identical embedded historical text, so this is not an isolated pure-procedure effect against H0.

## Full actual accounting and host amendment

All 77 actual attempts account for 73 logical cells, 367 SETTLED requests, USD 3.1767228 upper estimate, and 5951.639484037 summed episode seconds. There are 25 new digital scientific responses, zero unfinished physical-cache executions, zero native dispatches and zero new UNKNOWN usage. Exact-input cache reuse does not constitute another physical trial.

| Actual stage | Attempts | Requests | USD upper estimate | Summed episode seconds |
|---|---:|---:|---:|---:|
| O-transfer | 3 | 18 | 0.1579020 | 240.418 |
| final | 27 | 130 | 1.3377693 | 2781.598 |
| formation | 1 | 3 | 0.0269157 | 38.723 |
| proposal | 12 | 43 | 0.4491399 | 862.946 |
| selection | 34 | 173 | 1.2049959 | 2027.954 |

| Pipeline cohort | Full requests | Full USD estimate | Effective requests excluding only four host incidents | Effective USD estimate |
|---|---:|---:|---:|---:|
| H0 selection + final | 76 | 0.5154765 | 76 | 0.5154765 |
| G0 all H + selection + final | 135 | 1.2585825 | 123 | 1.1843580 |
| G1 formation + all H + selection + final | 138 | 1.2447618 | 129 | 1.1871390 |

The remaining O0 three episodes consume 18 requests / USD 0.1579020. The G1 formation is counted once globally and allocated as one request and one third of its USD/wall to each of three G1 arms. Lower final request counts in a cohort containing non-submissions are not evidence of efficient successful work. The slightly lower full G1 USD total is affected by unequal host-incident overhead (9 G1 versus 12 G0 requests). Excluding only those incidents, G1 uses six more requests and USD 0.0027810 more while passing two more final cells; a stable successful-work efficiency advantage is not established. All costs include failures, censored calls, proposal, unselected sibling, selection, design checks and confirmation. They use frozen rates and provider-reported usage, not invoices or full end-to-end cost. Codex assistance and historical experience acquisition are unpriced; provider identity is the reported deepseek-flash alias, not independently pinned model weights.

The original historical-CSV adapter omitted separately stored trace.csv on exact historical 22 µF / TX 0 cache hits, producing KeyError trace. New dispatch was held; four original fault/censored attempts (21 requests / USD 0.1318473 / 216.654733334 s) were retained. Authorized amendment phase4-cache-trace-amendment-20261020-001 preserves V1 protocol/components and the two changed source files exactly, verifies sealed input/observation/CSV binding using the original CSV reader semantics, and leaves compressed raw responses and all scientific laws/evaluators unchanged. Six targeted existing-data checks pass without new model calls or simulations, including all five prior valid selection cells. Only the four named fresh recovery identities were allowed; each retained the exact original payload, cache, 12-request/800 s/two-D budget. They consume 20 additional requests / USD 0.1182666 and all pass. No G/H was regenerated. The effective pipeline excludes only the four original host incidents; full/global accounting includes every charge.

## Evidence and verification

- `actual-results.json`: all 77 actual records and 73 canonical dispositions, full costs and physical-cache counts.
- `final-details.json` and `analysis-summary.json`: all 27 final cells, D and event checks, all denominators and finite descriptive cost tables.
- `selection-complete.json` and private `final-selection-freeze.json`: all effective selections and the freeze before first final input.
- `host-error-hold.json`, `amendment-registration.json`, `protocol-v1.1.json`, `cache-repair-qualification.json`, `recovery-results.json`, `v1-source-preservation.json`: original incident, approved bounded repair and source preservation.
- `preservation-final.json`: source/cache/cost/causal-payload readback PASS for 77 actual attempts / 367 live provider ledger rows / 30 used exact physical response keys; prior S0 871-row ledger prefix and four protected database table prefixes unchanged, including 24 old UNKNOWN records.

The stretched-port file retains a legacy descriptive event_latch_scope string inconsistent with its active volatile device field. Its bytes and model semantics were not edited; the active device field is authoritative. The half-power C-lite task is one virtual query with supplied source/state semantics, not RF integration, cryptographic security or multiple-query system qualification.

Reproduce the finite saved-data readback without dispatching any participant:

```sh
rtk proxy /opt/homebrew/opt/python@3.14/bin/python3.14 -B '/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/phase-plan-20261019/phase4/summarize_v11.py'
rtk proxy /opt/homebrew/opt/python@3.14/bin/python3.14 -B '/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/phase-plan-20261019/phase4/final_details.py'
rtk proxy /opt/homebrew/opt/python@3.14/bin/python3.14 -B '/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/phase-plan-20261019/phase4/analyze_closed.py'
rtk proxy /opt/homebrew/opt/python@3.14/bin/python3.14 -B '/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/phase-plan-20261019/phase4/verify_actual.py'
```

## Final local closure

Both new local papers are compiled and visually checked on every page: A is 8 pages (PDF SHA-256 `e6be17735085ecb003856bda24e8a7ae5b537b91ce36aefda1770ab5e4c560ce`); B is 7 pages (`f857898b4d0c67a120d16ff603d8180c4868687e775b28ea861d9e3e4ac27345`). S0 imported exactly 58 new owned paper/QA files (2907236 logical bytes), verified source/PDF hashes, all embedded fonts and actual final text, and visually checked both first pages. The upper-left corner is blank and the official English horizontal HKUST(GZ) vector logo is at upper right. Shared style/PDF/SVG bytes are unchanged in all three existing apps. Final TeX and PDF paths are in `paper-readback.json`. Paper-local contemporaneous S0-CI-pending notes describe the author handoff; the later coordinator receipt below resolves the integration gate.

The correctly configured registered S0 command `rtk proxy bash ./init.sh` passes 343 architecture-v2-ci tests, plus 44 saved files and 11 controls, in 15.175720 s. No new model calls, native dispatches or study scientific executions occur. This is scoped to S0 and this verification profile. One earlier operator invocation omitted required PI_CODING_AGENT_DIR and was rejected during imports (49 loader/test entries, 11 errors). The original receipt/log are retained under final-integration-attempt1; only the environment mapping to the existing profile home/pi-config was corrected, with no scientific source changes, before the successful invocation. No healthy root-wide or worker environment claim is made. Separately, 37 prior targeted unit tests and six v1.1 existing-data repair checks are source-bound in `targeted-verification.json`; they are not relabeled as 380 CI tests.

All paper build/high-resolution page scratch and both S0 first-page previews are removed. The recorded logical deletion is 5656847 bytes; this is not credited as measured APFS release. Final observed APFS availability is 23660961792 bytes (23.66 GB), above the 10.9 GB reserve-plus-peak admission rule. Private phase4 actual evidence retains 39223712 logical bytes; the existing provider workbench grows 24828490 bytes, both under their caps. There are no new environments, worktrees or full tree backups. Only the two amended V1 source files are preserved as required protocol history. All unique experiments, raw results, prior failures and billing records remain.

The prior central cleanup has a verified before/after APFS increase of 12,261,535,744 bytes (12.26 GB / 11.42 GiB), from 10,733,174,784 to 22,994,710,528 available bytes. Its report and receipt are bound by `storage-final.json`. Later system background availability changes are not attributed to cleanup, and paper scratch bytes are not added to that net release.

Phase4 publication remains local only: zero commits, pushes or Overleaf updates in this phase. Original A and B are idle. The next gate is independent phase4 exit review, followed by a separately dispatched phase5 publication/closure step under the existing plan. No additional participant experiment is authorized by this completed report. Physical qualification stays UNKNOWN; H0 and the original failed A/R product baseline stay unchanged.

