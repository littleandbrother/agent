# BF D/H/G entry material — actual continued Pi episode

The final A/R section uses the preserved original reference and one actual Pi
episode, including its explicit continuation. The original four H attempts and
68 settled requests remain a separate, unchanged experiment.

| Object | Concrete change | Present evidence | Claim boundary |
|---|---|---|---|
| D | Executed queue rank `0-seq`, retry 2/30/8 s; C=0.015 F, off/ready=2.3/2.7 V, sample=60 s, ACK=1 s | Three Pi tool proposals, twelve local case executions, independent final receipts; candidate-002 selected | Conditional rank-hook freshness repair; all three violate strict FIFO; product NOT_ACCEPTED |
| H | Check joint startup/dark feasibility; separate backlog completion from fresh-receive delay | Proposed rule informed by exposed public failures and Codex bounds | No fresh A/R H comparison or retained update |
| G | Propose and select a reusable H change from BF failures | No lineage experiment | Method benefit, RSI and held-out transfer NOT_TESTED |

The selected candidate's upload profile passes freshness, retention, 120 s
backlog recovery and deduplication under the rank hook. Independent queue replay
still finds a strict FIFO violation at 833 s: selected seq 2, oldest pending seq 1.
The frozen text requires oldest unacknowledged first; it is unchanged. A human
must resolve the ordering contract before a changed policy can be accepted.

All three history profiles retain four failures: continuous sampling, dark new
sampling, recovery upload and event coverage. Absolute time after reset remains
UNKNOWN. Whole-profile sample counts are 106/168/129; these are not dark-only
counts. The selected candidate retains 170 records (168 samples), reports the
gap, misses one of two events, and has all 73 recovery backlog records late.

The independent final sleep-only proof gives C <= 0.052809917 F for cold startup
and C >= 0.071203306 F for the twelve-hour dark service, allowing 122 s of edge
slack and omitting sensing/write/radio costs. This weaker external proof is
separate from the stronger Codex-exposed preparation bound C >= 0.077247934 F.
Both concerns are limited to the fixed ideal single-capacitor/fixed-sleep model;
neither establishes physical impossibility or a sufficient replacement design.

Optimistic necessary human tradeoff limits from the external proof are cold
startup >=2426.93 s (40.45 min), dark duration <=32072 s (8.91 h), or sleep power
below about 3.7084 uW. Changing any service or apparatus needs a new human-approved
contract and qualification. No change is applied to the frozen contract here.

The original segment hit a 2 MB SSE transport envelope before submitting a D.
Its two requests and original UNKNOWN snapshot are preserved; upstream usage
later settled. `continuation-001` retains the original owner/session, eight
messages, four tool results, original deadline, and cumulative 60-request /
3-candidate / 3600 s caps. It is not an independent resample. Only the response
envelope grows to 64 MiB. The provider alias `deepseek-flash` does not pin weights.

The complete episode has seven SETTLED requests, zero native dispatches, charge
upper USD 0.082605, and cache-aware rate estimate USD 0.058482888. Neither is an
invoice. Codex construction/repair assistance remains UNPRICED_NONZERO and full
end-to-end cost is unknown. The paper update adds no model calls or simulations.

`phase1-pi-evidence.json`, the two CSVs and generated result table are produced
by `bind_pi_evidence.py`, which only reads and hashes saved evidence. It checks
all 81 candidate sealed files, 180 service-matrix rows, exact tool inputs,
continued session prefix, seven ledger rows and necessary-bound arithmetic.
`source-data-binding.json` and `hash-comparison-notes.json` under the final owned
documents distinguish canonical JSON hashes from byte hashes and distinguish
the analytical proof checker from the service checker. Both initial apparent
differences are resolved against their actual source paths; no source drift is
reported from those comparisons.
