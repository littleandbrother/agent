# Multi-harvester deployments — D2-001

Four voltage-dependent raw/converter/bus port families execute six scenarios:
rotary factory, outdoor PV, indoor PV, vibration bridge, thermal pipeline and
three-source hybrid station. Each reference executes three acquisition,
integer inference, transmission and distinct receiver-delivery requests.
Reference, small-storage and distant-receiver designs yield 18 sealed runs.

Validation: `./init.sh` (68 tests), `node apps/world-studio/deployment-test.mjs`.
Source report: `docs/deployments/validation.json`. Content-addressed bundles
include IR, event JSONL, Parquet channels, evidence, view bindings and inventory.
Checkpoint continuation preserves the full run hash; atomic bundle directory
promotion prevents partial artifacts from appearing sealed. Interrupted staging
directories remain non-authoritative and can be inspected.

Studio: `?view=deployments`. All samples remain available offline. The selected
scene, design variant, cursor, source port, energy state and request events share
one run identity. Source bars show integrated bus energy; capacitor fill uses
usable energy, not a linear voltage fraction. Context hiding is presentation-only.

Boundaries: precharged storage, synthetic forcing and INT8 windows, simplified
source equations, fixed-ratio converters, no MPPT or mechanical/thermal feedback,
illustrative geometry and a deterministic receiver range threshold. A physical
mission pass is explicitly not independent evidence admission or hardware success.
Frozen A/B0 and the earlier rejected transfer capsule are unchanged.
