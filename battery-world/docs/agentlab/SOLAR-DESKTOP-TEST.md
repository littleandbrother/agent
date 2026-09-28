# Solar desktop companion: real test and developer scrolling

Date: 2026-09-18. Feature: BFA-011-solar-desktop-test.

## Outcome

The bounded real test was executed and audited. Product acceptance and autonomous
design acceptance did **not** pass. Session `pi-chat-51568ce5b0a46ee9` produced a
SolarMochi concept proposal, three energy-script iterations and one actual Blender
enclosure job. The title says v3; its persisted proposal revision is 2. The only
engineering job, `eng-30b947741ce000d1`, remains bound to revision 1 and is correctly
shown as an old proposal artifact.

There were 26 paid requests, 455,574 tokens, 32 timed tool calls, two Skill reads,
1,382 raw events, one Blender job, no MCP calls and no COMSOL calls. The conservative
settled cost upper bound is USD 0.1587249; no request remains unsettled. The final
stop was `MODEL_OWNER_USD_BUDGET`: the next conservative reservation exceeded the
remaining allowance under this test's USD 0.199 cap. Actual spending did not reach
USD 0.20. The model did not deliver its final design document or final response.

## Product findings

The revised concept uses deliberate tapping to start/end a focus timer and
low-frequency static e-ink expressions. It assumes a window-side solar panel and
a rechargeable battery; it is not a battery-free product. Independent replay of
the v3 script matches its persisted JSON. The corrected nominal battery capacity
is 7.4 Wh, with 6.29 Wh under an assumed 85% usable fraction. Segmented daylight
integration, manufacturer-reference indoor-light arithmetic and refresh-energy
sensitivity were checked. These calculations use unmeasured load and solar
assumptions, not hardware results.

Remaining defects include inconsistent dark-mode table labels, an unsupported
200 mW "physical limit", unsupported installation/thermal claims and incomplete
product geometry. The native Blender readback confirms only a 100 x 60 x 25 mm
base enclosure, not the solar panel, companion dome, screen, fasteners or assembly.
Seven engineering artifact hashes were checked. No unrelated rotary benchmark or
cantilever FEM was used as solar validation. Coordinator research, reviews and
execution reminders were necessary; this is not autonomous-design efficacy evidence.

The readable coordinator review, including real artifact links and claim limits:
`/Users/depengsu/Documents/bf-agent-workbench/verification/solar-desktop/final-design-review.md`.
The app currently lists proposal JSON and engineering artifacts; arbitrary Agent
output files still need a provenance-preserving registration mechanism.

## User-requested operational fixes

Developer pages were clipped because the viewport-fixed document did not give
the developer grid a bounded scrolling row. `apps/agent-studio/chat.css` now bounds
that row, removes vertical auto margins and gives the developer view its own
vertical overflow. Actual wheel scrolling verified all seven modules: Trace,
Memory, Harness, RSI, Tools, Context and Experiments. Long pages reach the bottom;
short pages fit without clipping. Both already-open browser tabs have the new CSS.

After the explicit 500,000-token extension, the user's further request to loosen
the test token gate raised the cumulative engineering ceiling to 20,000,000.
Global USD 3.9279102, request USD 0.19, and this test's USD 0.199 limits were kept.
The token change does not authorize additional dollar spending or remove context
limits. No additional calls were made for scroll verification.

One provider response had returned real usage but settlement failed with a
SQLite write lock. After a private database backup, exact SDK-reported usage for
`llm-81fda6e92eb6d9cc073e` was reconciled with a source-bound resolution record.
Its missing raw HTTP response hash remains null; no usage or response was invented.
An isolated two-connection control reproduced reader/writer blocking in DELETE
mode and successful writes in WAL mode. The live database was switched to WAL and
passed integrity checking. The following 11 model requests settled without a lock.
The original lock holder was not captured; this is a configuration recovery, not
proof of every concurrent failure cause. The one-off recovery script must not be
rerun. Original traces and failed design iterations remain preserved.

## Verification and handoff

- `rtk proxy ./init.sh` in `/Users/depengsu/Documents/battery-world`: 262 Python
  tests passed in 173.684 seconds, plus SDK/Studio checks, build and reproduction.
- Independent arithmetic replay: run `calc/energy_budget_v3.py` from the session
  participant directory in a separate working directory; compare the emitted JSON.
- Native readback: Blender background execution of `readback_blender.py` from the
  verification directory; dimensions and artifacts are recorded in the receipt.
- Live UI verification: all seven developer modules, real wheel input, final
  control visibility, persisted user conversation, Trace and proposal/file view.

Machine-readable evidence: `SOLAR-DESKTOP-TEST.json`. Detailed immutable-source
snapshots, calculation replay, native readback, authorizations and recovery evidence
are under `/Users/depengsu/Documents/bf-agent-workbench/verification/solar-desktop/`.
The database backup there has owner-only permissions.

This feature closes execution/reporting of a negative engineering test and the
scroll repair. It does not close product design, CAD, hardware, RSI, or the B2
scientific study. Restore B2-003 as the active scientific feature; keep its prior
gates. Future work should prioritize final-delivery checks, actual full-product
geometry and source-bound output registration before another acceptance test.
No commit was made.
