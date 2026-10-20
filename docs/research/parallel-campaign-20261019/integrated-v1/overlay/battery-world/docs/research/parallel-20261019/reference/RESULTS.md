# BFA-045: actual finite A/R and B reference results

2026-10-19. Owner campaign-a. **The finite public-development work package is
complete; hardware qualification and a complete R product are not established.**
Raw run: `/Users/depengsu/.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-001`.
Candidate: `CR-f7d7d4fc3b1d830ea36f96ea11671e927de9f55748d842d10385b7f693cf0183`.
Frozen conditions SHA-256:
`19757a1c9aa8a889dbb7258276121d3621c0faa7d468aa47ff95ac9a1a201fdb`.
All six registered tasks were executed in 17 fixed conditions. **17/17 is the
agreement of predeclared positive/negative controls, not 17 successful devices.**
All 17 energy and independent digital receiver readbacks agreed. Results and
gate-level CSV are alongside this document; the raw traces are in the run root.

## Current engineering judgment

The 15 mF single-light-source candidate supports the declared A/R-1 nominal
service chain. Its 1 h cold-start profile boots at 771 s and delivers a first
fresh sample at 773 s, within the unchanged 1800 s requirement. An independent
capacitor-energy calculation gives 0.5 C Vready^2 / (0.8 Pin - Poff) = 770.0704 s;
the discrete ready edge is 771 s with a 1 s integration step. The six-hour
light/dark profile produces 348 samples, with no brownout, no missed sampling
windows and live digital service PASS. It is an executable host computation
with a normal strapped installation envelope, BOM and program, not a PCB, MCU
binary, calibrated source or BLE hardware realization.

The same design does **not** satisfy the 12 h darkness/history service. It
browns out at 7920 s, after darkness begins at 3600 s. All 170 durable records
survive in ideal NVM, while 660 required one-minute sample windows are missed
and one of two temperature events is missed. The reported conservative gap is
[7913,47561] s, based on last durable observation and new synchronization;
these are not inferred precise outage edges. Retention PASS, new sampling FAIL,
gap reporting PASS, absolute-time continuity UNKNOWN, event coverage FAIL, and
120 s recovery upload FAIL coexist. Seventy-three pending records miss the
recovery deadline; they eventually upload. The volatile-history control retains
only 49 of 170 records and fails retention. No added energy or relaxed deadline
was used to make this candidate pass.

The gateway-recovery profile uploads its 60 queued records in **82 s** after
coverage returns. Two actual lost ACKs produce two duplicate arrivals; correct
receiver deduplication accepts each sequence once, while the naive receiver
accepts two duplicates. However, FIFO upload delays one newly generated sample
(sequence 109, created at 7253 s, accepted at 7283 s) by **30 s**, violating the
unchanged 10 s live deadline. Recovery upload and deduplication PASS therefore
do not establish the combined A/R-2 live/history service. Keep this failure as
the concrete scheduling issue for a future version; no scheduling revision was
introduced in this finite package.

## B mechanism controls

| Condition | Assumed source integral | Actual digital reception | Conclusion |
| --- | ---: | ---: | --- |
| Fast pulse, 0.3 ohm ESR | 150 uJ | 15.8 ms | PASS before 100 ms |
| Slow pulse, 0.3 ohm ESR | 150 uJ | 54.8 ms | PASS before 100 ms |
| Same fast pulse, 150 ohm ESR | 150 uJ | none | FAIL; transient voltage, eight pre-deadline resets |
| No energy | 0 | none | FAIL |
| Energy delayed to 90 ms | 150 uJ | 105.8 ms | FAIL deadline despite eventual packet |
| Split pulse, passive latch, injected shunt/reset | 210 uJ | 46.9 ms | PASS; captured event survives reset |
| Same split pulse/shunt, volatile memory | 210 uJ | none | FAIL; event was captured before reset and then lost |

The memory pair uses identical source segments, 10 uF storage and a declared
40 uJ shunt at 12 ms (discrete reset edge 12.1 ms). Both observe the short press
before the reset. Only the ideal passive mechanical latch preserves it. This
does not assume a powered digital write at zero stored energy. No release pulse
contributes energy. The 150/210 uJ source integrals are synthetic inputs with
datasheet-range consistency; they are not measured ECO260 waveforms.

## Paper facts and competing explanations

P1 may cite two limited counterexamples: equal source energy does not determine
the transient outcome when ESR changes, and equal supplied energy does not
determine event reception when reset destroys event memory. A/R additionally
shows why retention, new sampling, time knowledge and received service require
separate observations. These are nominal mechanism illustrations; they do not
demonstrate novel physical laws, interface-learning benefit or Agent superiority.

P2 may use the source-bound candidate and raw traces as explicit D inputs for
F1a. These computations do not execute an H change, demonstrate F1b, establish
method improvement or support RSI. The source-port power is fixed within its
declared operating points; it is not a load-dependent PV/PMIC response cache.
Any such physics extension needs a new qualified model and input identity.

## Evidence and remaining qualification

- 12 targeted tests PASS, including all 17 predeclared controls, CRC corruption,
  correct-CRC payload mismatch, stale history, energy tampering, invalid PMIC
  threshold, and two step-size refinements.
- `BFWORLD_VERIFY_PROFILE=architecture-v2-ci ./init.sh`: 343 repository tests
  PASS; existing 44-file/11-control evidence readback PASS. This is the requested
  profile, not a claim that the default full-repository init or hardware passed.
- New run: 81 sealed files, 42,987,337 bytes before seal, 3.635 s runner wall
  time. Independent saved readback PASS with zero new simulations.
- The copied candidate, executed with site packages disabled, reproduced
  A-cold and B-fast observations and CSV trace bytes exactly. These were two
  explicit nominal portability reexecutions, not native solver calls.
- Maximum Decimal ledger residual is at most 7e-17 J across this list. This is
  arithmetic agreement within the assumed model, not a physical error bound.
- All 5,544 baseline files were rehashed; only the pre-existing S0 active-feature
  overlay differs. No original V2 Git operation, commit or push was performed.

No installed IV calibration, AEM10941 native transient model, ECO260 port model,
measured temperature error, atomic NVM qualification, backed RTC, MCU binary,
BLE air-interface measurement, mechanical qualification, full R0 shock/24 h
lifecycle, formal holdout or Agent comparison was obtained. Physical gates
remain UNKNOWN. Official-source constraints and download limits are in
[SOURCES.md](SOURCES.md). The missing Epishine direct PDF download is recorded
as HTTP 403; its PDF was read through browsing.

Some flat logical properties are vacuous when unexercised (e.g. no history to
lose, no recovery/event/dark period); they are not product acceptance evidence.
Use the task and applicability fields when consuming the CSV. B's
`event_preserved_after_reset` is only a required gate in B-event-memory;
its default FAIL outside a reset experiment is not an additional B-pulse task.

The first targeted test run failed because historical arrival was incorrectly
counted as first fresh reception. Its original source, input, raw trace,
incorrect result and failure receipt remain under
`a/verification-001/stale-failure/`. The implementation was corrected against
the already-frozen freshness requirement; inputs and thresholds were unchanged.
The second targeted run passed. All candidate/service failures above remain.

Experiment paid-model requests: **0**. New native EDA/simulator dispatches: **0**.
Hardware writes: **0**. Original Pi resumption: **0**. No other chat or sub-agent
was created or messaged. S0 owns shared integration and project-state updates.
