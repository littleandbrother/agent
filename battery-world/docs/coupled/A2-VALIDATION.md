# A2 — Coupled computational mission

Implemented scope: load-dependent rectified Norton source, capacitor and leakage,
series resistance dissipation, ideal overvoltage clamp, constant-efficiency PMIC
with cold-start/on/off state, sleep/boot/sense/infer/TX load states, acquisition of
128 signed INT8 synthetic samples, actual integer feature classification, and
separate receiver-side delivery events. All run outcomes are computed.

Five controls: successful mission; unclamped surge; brownout during transmission;
wrong classification with successful delivery; successful transmission with no
receiver delivery. These are executable controls, separate from B0 fixtures.

## Reproduction

```sh
./init.sh
corepack pnpm run test:studio
```

`docs/coupled/validation.json` binds every content-addressed run and its fresh
reproduction. Each run includes world IR, run manifest, Parquet channels, event
JSONL, evidence, views, a standalone offline replay, and the complete run object.
Sealing an existing identity verifies it; it never overwrites modified evidence.

The midpoint integrator accounts for ESR, regulator, load, leakage and clamp loss.
The numerical conservation tolerance is 1e-7 relative to the largest of harvested,
consumed and initial stored energy (with a 1e-12 J floor). This remains well-defined
for the later zero-harvest burst control. It is a numerical tolerance, not hardware
calibration. Event priority is
threshold → PMIC → MCU → application → mission after continuous integration.
Rows expose post-event state and preceding-interval currents separately.

The independent ngspice check covers a constant-current passive source/storage
network, with acceptance error below 1e-4 V. It does not validate the PMIC, signal,
classifier, radio or the complete world. The circuit netlist, version, comparison
samples and tolerance are included in the validation report.

## Boundaries

No measured device, calibrated TENG, trained diagnostic classifier, transistor-level
PMIC, real RF propagation, Agent efficacy, hidden qualification or RSI claim.
Classifier confidence is an uncalibrated score, not probability. Physical mission
pass is separate from evidence admissibility: these runs cannot self-qualify VMS.
This feature consolidates the three planned A2 engineering slices into one tested
vertical implementation; it does not silently count three independent studies.
