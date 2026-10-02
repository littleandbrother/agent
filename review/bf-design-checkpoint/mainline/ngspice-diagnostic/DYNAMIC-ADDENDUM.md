# Four-run diagnostic: the peak occurs before electrical loading

2026-10-01. Diagnostic only; supplements STATIC-ADDENDUM.md. No original code,
test assertion, threshold, integration receipt, or frozen output was changed.

## Result

The entire original 97.5 nm peak difference is reproduced by the 10 us versus
5 us refinement within **either unchanged electrical configuration**. At
matched settings, the original and feedback configurations have identical
global displacement peaks at exported precision.

| Configuration | Maximum step | Peak absolute displacement (m) | Peak time (s) | First enabled/load time (s) |
|---|---:|---:|---:|---:|
| Original baseline | 10 us | 0.0247397317 | 0.0121150 | 0.104744812 |
| Changed PMIC/load | 10 us | 0.0247397317 | 0.0121150 | 0.0238394034 |
| Original baseline | 5 us | 0.0247398292 | 0.0121125 | 0.104744489 |
| Changed PMIC/load | 5 us | 0.0247398292 | 0.0121125 | 0.0238393307 |

- Matched 10 us feedback-minus-baseline peak: **0 m** (absolute 0 m)
- Matched 5 us feedback-minus-baseline peak: **0 m** (absolute 0 m)
- Baseline fine-minus-coarse peak: **+9.750000000072201e-8 m**
- Feedback fine-minus-coarse peak: **+9.750000000072201e-8 m**
- Original mixed comparison, feedback 10 us minus baseline 5 us:
  **-9.750000000072201e-8 m** (absolute 97.5 nm)
- Each configuration's peak refinement change is about 3.9410 ppm

The original strict `> 1e-7 m` assertion remains false. Matching settings would
also leave that assertion false; lowering its threshold would not repair its
causal validity. These data explain the observed failure without showing a
reciprocal-coupling model inconsistency.

## Causal timing and later waveform differences

Every exported load-current sample before the measured peaks is zero. The peak
storage voltage is about 0.26074 V, below both startup thresholds. The modified
power/load settings therefore have not activated the behavioral load before
the global mechanical maximum. Both matched-step runs have identical full
initial channel rows through 0.0238295133 s (10 us) and 0.0238389715 s (5 us).

The settings do become active later. The modified case first enables around
23.839 ms, then reaches its post-stage 10 mA idle configuration; the original
first enables around 104.744 ms. Post-stage idle rows were observed in all four
runs. The two trajectories do differ substantially later:

| Retained-channel comparison | 10 us | 5 us |
|---|---:|---:|
| Exact endpoint t=0.25 s, feedback-minus-baseline displacement | +0.00042027085 m | +0.00042034109 m |
| Maximum absolute trajectory difference, piecewise-linear interpolation on union of output times | 0.0005266047954 m | 0.0005266072388 m |
| Time of that interpolated maximum | 0.242327251 s | 0.242323527 s |

The endpoint comparison requires no interpolation. The maximum trajectory
differences are descriptive postprocessing, with no certified error bound.
Identical early global peaks do **not** mean absent electrical backaction in
general. The original peak statistic is insensitive to this fixture's later
modeled response. As the static analysis showed, the change is a combined
PMIC-and-load intervention rather than an isolated idle-current effect.

## Execution and boundaries

Exactly four ngspice solves ran, all exited 0 and reached 0.25 s. No extra
solves, solver substitutions, commercial tools, participants, providers, or
hardware were run. `analyze_retained_channels.py` reads those four outputs only.
All six original summary checks are true for these four runs; that fact is
diagnostic and does not change any integration gate or physical qualification.

- Executable: local official Debian ngspice **44.2**, KLU build;
  full version output in `ngspice-version.txt`, binary SHA256 in the receipt
- Python: the same isolated CPython **3.11.16** used in integration
- Source: pinned `338d60384d5805abf1e02252a4513860066a2c39`
- Each input is the original literal test fixture or its exact original
  feedback modifications. Only the requested maximum step differs
- Duration 0.25 s, original initial conditions/UIC, Gear method,
  reltol=1e-5, abstol=1e-11, vntol=1e-8
- Original `Btimer` reset time constant step/10 retained. Consequently the
  refinement comparison is not generally a pure discretization error estimate.
  In these runs the timer is still zero at the global peak
- Raw export uses nine displayed significant digits in these runs. “Identical”
  means identical recorded output, not a claim about unexported internal bits

The full per-run source/input/deck/raw-output hashes, exact commands and return
codes are in `DIAGNOSTIC-RESULT.json`. `CHANNEL-ANALYSIS.json` contains peak,
startup, endpoint, prefix-identity and interpolation evidence. All raw channels,
netlists, inputs, process logs, scripts and summary JSON are retained under this
separate addendum directory; its manifest hashes every delivered file.

## Recommended disposition

Keep the current gate failure and cache-integration equivalence intact. Record
this as an upstream test-design problem: a fixed lower bound on an early global
peak cannot validate a perturbation that activates only later. Any replacement
criterion requires a separate reviewed change with a matched-setting causal
control and a justified numerical uncertainty budget. The four-run diagnostic
does not establish asymptotic convergence, calibrated physics, LTC3588 behavior,
target-device execution, or product readiness.

For that future change, predeclare the observable and tolerances before new
results are examined: use matched solver settings; verify actual load
activation inside the measurement window; measure a post-activation trajectory
or energy observable rather than an earlier global peak; and justify acceptance
margins against an independently assessed numerical uncertainty budget. Make
the event-timer reset time constant an explicit parameter independent of step
before calling a step-refinement study a pure convergence check. These are
prospective recommendations, not a retroactive replacement of the original
assertion or a claim that this diagnostic was a pre-registered passing test.
