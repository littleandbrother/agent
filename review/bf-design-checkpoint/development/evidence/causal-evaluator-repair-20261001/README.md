# Causal evaluator repair and explicit rail/state contract

Status: independently reproduced generic computational diagnostic; native startup model remains blocked.

## Implemented

- `src/event_apparatus_v2.py`: explicit v2 schema, fixed 1 µs mathematical timer-reset parameter independent of numerical step, 17-digit output, a measured piezo-to-bridge current port, and explicit reciprocal/no-feedback modes
- `src/causal_evaluator_v2.py`: finite positive activation, fixed post-activation trajectory metric, no-feedback negative control, three-level refinement and separated mechanical/piezo/storage energy checks
- `src/ltc3588_rail_contract_v2.py`: independently source-justified ideal settled rail arithmetic and nominal event logic only; transient startup calls fail closed
- `contracts/prospective-plan-v2.json`: criteria frozen and hashed before exactly 12 real ngspice 44.2 solves; no retries or changes after results

## Result of the prospectively fixed 12-cell diagnostic

All five criteria passed. Maximum post-activation displacement contrast on the frozen 501-point grid is 0.537556 mm. Removing mechanical electrical backaction reduces the contrast to 0.8675 nm. The required separation margin was 7.1342 µm. Successive trajectory refinement ratios are 0.2490–0.2510; these observations support numerical adequacy for this fixture, not a certified continuum error bound.

The independent reviewer verified every plan/source/runner seal, all 12 input/deck/output hashes, exact cell settings, effects, activation and energy ledgers without producer imports or new solves. Maximum independently computed energy disagreement was 4.8919e-16 J. See `/workspace/shared/world-evaluator-independent-review-20261001/reports/evaluator-independent-readback.json`.

The 0.4 V ideal output, 0.8/0.5 V enable thresholds, load stages, timer reset and numerical criteria are generic software-fixture assumptions. They do not represent an LTC3588 or a door product. No-feedback intentionally leaves an electrical generator powered by artificial external work; it is a causal ablation, not a passive physical device.

## Rail and PGOOD boundary

Analog Devices LTC3588-1 datasheet revision C, printed page 9, describes initial PGOOD assertion at the “first time the converter reaches the sleep threshold of the programmed VOUT”. Its 92% figure is the typical falling threshold. The electrical table on printed page 3 gives 83% minimum and no maximum for that fraction. Input UVLO alone does not clear an already asserted PGOOD while output remains sufficiently charged.

The ideal relationships and capacitor connections are specified on printed pages 7–8 and 13. The executable contract uses VIN−CAP for that capacitor's voltage, with the two bypass energies tracked separately. The familiar 65.664 µJ ideal total is stored energy, not a separately justified post-UVLO lumped startup requirement. No rail charging/discharge time constant has been introduced.

Source: https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf
Research copy SHA256: f1e52b155e35b2b5fe70ee05f5cdf130a577488df648703054bf2f57395c7c1d

## What remains blocked

Real startup prediction requires verified macro-model pin order, authorized native tool/model identity, rail voltage/current observations, complete initial state and port energy evidence, and a qualified dynamic model. No vendor PMIC has been replaced, no licensed model was copied, and no native/commercial solves ran. The static helper is never admitted as a PMIC transient solver.

Authoritative door-world identity, mechanical preparation, native geometry/force and program/load boundaries remain separate. No feasible reference, firmware measurement, hardware qualification, held-out result, autonomous agent benefit or RSI claim follows from this repair.

## Reproduction and integration

Run software tests:

    /workspace/shared/current-cache-integration-20261001/venv/bin/python -m unittest discover -s tests -v

The recorded 12-run console output is in `reports/diagnostic-console.log` and each exact invocation is in `DIAGNOSTIC-RESULT.json`. `run_diagnostics.py` refuses a repeat or overwrite. Re-evaluation is read-only via `verify_retained_evidence.py`; it does not run ngspice.

This directory is an isolated opt-in v2 implementation, not an in-place production migration. The original v1 source, failing global-peak test and sealed results are unchanged. A production adoption must explicitly import the new version and bind its scope. Do not reinterpret old runs under new semantics. The full upstream `init.sh` was not run: it would modify the preserved upstream workspace and launch tests outside this 12-solve authorization. Focused checks do not imply the upstream active feature is healthy.
