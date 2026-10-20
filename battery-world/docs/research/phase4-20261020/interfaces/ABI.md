# BFA-062 minimal O service adapter

Preparation handoff only. No full O0 execution or Agent episode has occurred.
S0 owns protocol admission, split freezing, actual episodes and shared state.

## Import and explicit input

```python
from bfworld.agentlab.campaign20261019 import phase4_interfaces as o
```

Load `configs/studies/phase4-20261020/interfaces/o0-task.v1.json` explicitly.
No API discovers task files, contacts a provider or dispatches a native solver.
All inputs/outputs are JSON-compatible objects. Canonical bytes use sorted
keys, compact separators and forbidden NaN; `o.identity(value)` is SHA-256.

| Function | Contract |
|---|---|
| `validate_case(case)` | Validate schema, source hash, original AR module hash, legal hardware and unchanged O service. Raises `ValueError` on a bad binding/domain. |
| `candidate_schema(case)` | Return the closed typed D schema. |
| `validate_candidate(case, candidate)` | Validate numeric ranges, threshold ordering, enum choices and AR electrical limits. No extra event table or Boolean numbers. |
| `evaluate_candidate(case, candidate)` | Recompute the complete supplied case. Return energy ledger, powered activity, compressed actual samples, committed records, state, wire packets and receiver facts. No service verdict or expected events. |
| `evaluate_service(case, response)` | Host-only independent Decimal energy audit, bitwise CRC/wire receiver, external continuous RMS truth and each-event service checks. Return `verdict`/`complete_service` = `PASS`, `FAIL` or `UNKNOWN`, reasons, per-event results and keepalive gaps. Never calls the producer. |
| `public_view(case, response=None, source=None)` | Participant facts. With `source`, return that complete source payload, canonical hash and JSON-pointer unit map. Without it, return full task, typed D schema and source directory; optional response contains raw facts only. |
| `fixed_periodic(case)` | Frozen A-style control candidate plus method text: one powered RMS snapshot every 60 s, FIFO upload, no confirmation state machine. |
| `rich_state(case)` | Frozen rich-state control candidate plus method text: powered 1 s RMS samples, 3/60 s confirmation, 120 s active keepalive, NVM FIFO retry. |
| `with_waveform(case, task_id, rms_segments)` | Host-only clone and rebind of a supplied waveform; other service/hardware/source/bounds unchanged. Never reads a heldout file. |
| `bind_case(case)` | Host-only construction helper. Participants submit D only; they cannot rebind a frozen case. |

Public source IDs are `task`, `ar_hardware`, `photovoltaic_source`,
`rms_waveform`, `wake_sample_cache`, `model_law`. Model source includes the
producer, its support functions/constants/imports and unchanged AR source;
the O truth routine and service evaluator are not in the public source.

## Original O0 and legal D

O0 is the original six-hour A0 light/power/zero-initial-energy profile, 15 cm²
PV and 15 mF storage. Source rows are 200 lux/90 µW, darkness/0,
50 lux/20 µW, 200 lux/90 µW, darkness/0, 50 lux/20 µW at the original
0/120/150/180/300/330/360 minute boundaries. Lux and 3500 K are metadata;
there is no lux-to-watts conversion or calibrated spectrum/IV curve.

External RMS is 0.08 g during 70–75, 130–135, 190–200 and 280–282 minutes,
0.005 g otherwise. Start requires continuously >0.05 g for 3 s; stop requires
continuously <0.01 g for 60 s. Equality resets that confirmation. Event time is
confirmation time. Each start/stop must be received within 10 s with ≤1 s
timestamp error. Received active-state messages cover active intervals with
gaps ≤120 s, including darkness. Idle false events/keepalives fail. Correct
final state does not cancel missing history.

D requires exactly `schema_version="bf-o-candidate-v1"`, `capacitance_f`,
`sample_period_s`, `threshold_on_g`, `threshold_off_g`, `retry_s`,
`tx_backoff_s`, `cache`, `program`. Ranges are in the case:
C=[0.015,0.015] F for all first-three O0 arms; sampling [0.25,120] s;
on [0.01,0.05] g; off [0.001,0.02] g with off < on; retry [0.25,120] s;
backoff [0,120] s; cache `nvm`/`volatile`; program
`confirmed_events`/`periodic_snapshot`. A separately frozen future case may
declare another legal C range. Participants cannot modify any case field.

Powered observations hold their measured RMS until the next successful
sample. Confirmation runs only on successful powered samples and resets
across failed observations/brownouts. Discrete sampling can miss or alias a
short excursion; the independent continuous service evaluator detects that.

## Power, wire and evidence boundary

Original qualified **digital** parameter sources are the unchanged
`campaign20261019/ar.py` and
`configs/studies/parallel-20261019/reference/conditions.v1.json`
(`ar_base` composed with `ar-light-dark`). Their hashes and the original
catalog hash are bound in O0 provenance and the handoff manifest.

The adapter uses analytic piecewise integration of the same assumed AR
source/cold-start/PMIC/ideal capacitor/ESR equations: 0.8 efficiency,
0.38 V/3 µW cold-start gates, ready/off 2.7/2.3 V, 3.3 V maximum,
5.5 V rating, ESR 0.3 ohm, 1.8 V output +0.3 V dropout,
1/5 µW off/sleep load, 100 µJ boot, 130 µJ TX, 8 mA peak and ideal
atomic transmission. Numerical integration is new; no original simulator was
modified or used to manufacture O truth.

RMS additions are explicitly **proposed ideal digital assumptions**:
0.5 µW powered standby, 1 µJ wake, 20 µJ sample and 5 µJ atomic write.
The sample cost borrows the AR temperature sample's numerical cost; it is
not qualification of a vibration sensor. NVM preserves committed queue/state
only and supplies no sensing power. Physical qualification remains `UNKNOWN`
even when nominal digital service is `PASS`.

Packets reuse the exact AR big-endian 20-byte `>IIiihBB` body plus 2-byte
CRC-CCITT. ID/sequence/time interval fields are unchanged; the old signed
measurement field carries O state as 0/100 and kinds are 3=start, 4=stop,
5=keepalive, 6=periodic snapshot. This versioned O interpretation is a
deterministic digital receiver, not a qualified BLE protocol. Receiver,
clock-sync assumptions, source schedule and hardware are shared across arms.

Responses bind source, case, candidate and current engine hashes, with an
execution key and content hash. Changed inputs require a fresh computation.
Energy is compressed by source/powered interval and observations by sampling
runs; no six-hour pointwise output grid is retained. The scheduler stops at
250,000 internal events as `RESOURCE_CAP_UNKNOWN`; no incomplete result can
pass service. A forged ledger is not a physical proof: the independent audit
checks balance/costs/UVLO/sampling/source/receiver facts, not an external
instrument measurement.

## S0 continuation and verification

1. Import the manifest-listed files after B is idle; verify SHA-256 and the
   unchanged local AR module. Preserve the frozen case payload when importing.
2. Before any actual O0 result, S0 alone freezes
   `p4-o-unexposed-waveform-v1`. The supplied waveform ABI is contiguous finite
   `[{"start_s": ..., "end_s": ..., "rms_g": ...}, ...]`, exactly covering the
   unchanged case horizon. B has not read this file or either reserved task.
3. S0 admits and executes the first three matched O0 D episodes under the
   registered 24-request/1200 s/2-D limits: candidate, periodic, rich state.
   O0 remains development-only and excluded from G/H formation/selection.
4. S0 owns the external tools/feedback policy and shared feature/progress/
   session state. B supplies no paid dispatch, final-test result or paper edit.

The retained test receipt reports 18 passing adversarial software tests,
0 failures/errors/skips. Every execution is a short altered/precharged
fixture ≤600 s; original O0 is validated only. Negative cases cover 3/60 s
boundaries and equality, dark missed events and false keepalive, brownout
NVM/volatile loss, CRC/sequence/state/time/late receive, lost keepalive despite
correct final stop, source/energy/UVLO/sample tampering and public/private
separation and complete public-source JSON roundtrip. This does not establish O0 success or repository health.

Reproduce only these tests from the B project directory:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/python/bfworld/src /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B -c 'import signal,unittest; signal.alarm(60); s=unittest.defaultTestLoader.discover("tests/agentlab",pattern="test_campaign_phase4_interfaces.py"); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful())'
```
