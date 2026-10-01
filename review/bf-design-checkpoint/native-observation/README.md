# Exact native PMIC observation kit v1
2026-10-01 · private project artifact · prospective and unexecuted

## Status
This is a separately versioned implementation of the reviewed observation proposal. It preserves the original proposal and earlier Library handoff unchanged. Four exact LTC3588-1 diagnostic decks, a vendor-symbol-backed v2 interface, bounded analysis definitions, strict retained-data readers and static/synthetic tests are prepared. No LTspice or vendor macro execution occurred while building this kit.

Passing static or synthetic checks does not establish native parser compatibility, successful installation, physical behavior or execution approval. A supported runtime, independently reviewed RC installation smoke, final exact-plan review and parent execution authorization remain necessary. No script launches a simulator.

The earlier compact handoff is Library libfile_00b4edfd00648191953b59fb5edb29ec version 0. It includes our own RC smoke deck and original installation/provenance review. Existing approved EULA reference: libfile_07903b2cde948191ade0677a9fba0131, identifier 20230822-LTS-CTSLA; exact text identity is preserved in that handoff. No vendor software, model/symbol body, license text or third-party PDF is redistributed here. The approved EULA restriction covers both public publication and third-party disclosure of benchmark/comparison results without ADI written consent; this private project transfer grants neither.

## Exact four cases
| Case | Source after 0.5 s | Max step | Relative tolerance |
|---|---|---:|---:|
| source-open-coarse | 1 TΩ switch off-isolation | 5 µs | 1e-4 |
| source-open-fine | same | 2.5 µs | 5e-5 |
| driven-down-coarse | connected; 5.5→3 V over 0.5–0.6 s | 5 µs | 1e-4 |
| driven-down-fine | same | 2.5 µs | 5e-5 |

All cases run prospectively from 0 to 2 s, with external source command (seconds, volts):
(0,0), (0.005,0), (0.05,4), (0.20,4), (0.25,5.5), (0.50,5.5).
Source-open then holds source command at 5.5 V behind finite off-isolation. Driven-down reaches 3 V at 0.60 s and holds it.

The source branch is Vdrive → 100 Ω → zero-volt Vsupply → Sdrive → VIN. Switch parameters are Ron=0.01 Ω, Roff=1e12 Ω, Vt=0.5 V, Vh=0, Lser=0, Vser=0. For source-open only, control falls linearly from 1 V at 0.499999 s to 0 V at 0.500001 s; nominal threshold time is 0.5 s. The actual measured crossing bracket is retained. Equality is not assigned a hidden switch state. Driven-down control stays at 1 V. This is finite off-isolation, not infinite isolation; the source remains able to leak/sink through the declared Roff and its measured work is counted.

Common settings include UIC, no waveform compression, dependent-variable double precision (numdgt=15), trap integration, normal solver, abstol=1e-12 A, vntol=1e-9 V, chgtol=1e-14 C, gmin=1e-12 S, gshunt=0, cshunt=0 and cshuntintern=0. Ambient temperature is explicitly 25 °C; tnom=27 °C is also explicit. Neither value identifies hidden vendor-macro calibration.

## Interface and zero-stimulus boundary
The original vendor symbol's SpiceOrder is:
PZ1, PZ2, CAP, Vin, SW, Vout, Vin2, D1, D0, Pgood, GND.
It is independently bound to the original same-package binary model and original executable by SHA256 in contracts/native-model-interface-v2.json. The binary declaration is explicitly unobserved; no old declaration-required v1 sidecar is fabricated.

Every one of the eleven declared macro pins has a separate zero-volt voltage source. Each first node is the external circuit node; each second node is that pin's wrapper node. Positive sensor current flows INTO the macro. The m_* node names are our external connection nodes at declared ports, not guessed/probed hidden vendor internals.

PZ1 and PZ2 each connect to external ground through their own zero-volt sensor. This deliberately clamps both rectifier inputs at zero common-mode and zero differential voltage. It eliminates external piezo stimulus and floating-input ambiguity in this electrical diagnostic. It is not an open piezo, not the original electromechanical circuit, and not a self-powered baseline. The ground clamps cannot contribute voltage-source work at their ideal zero voltage, but their currents remain observed.

D1 is connected to external VIN2, D0 to external ground, each through its own sensor. The explicit eleventh GND model terminal also has its own sensor. PGOOD is unloaded except for a zero-volt port sensor and ideal voltage observation; no undocumented pull-up is added. If its native output behavior is unresolved, report it rather than changing the deck.

## Stores, parasitics and initial states
- Cstorage: 47 µF, VIN to ground, IC=0
- Ccap: 1 µF, VIN to CAP, differential IC=0
- Cvin2: 4.7 µF, VIN2 to ground, IC=0
- Cout: ideal 100 µF from cout_inner to ground, IC=0, preceded by explicit 0.02 Ω ESR and a zero-volt branch sensor
- L1: 10 µH, l_inner to OUT, ideal IC=0, preceded by explicit 0.4 Ω ESR and a zero-volt terminal sensor
- L1 builtin Rser=0, Cpar=0 and fixed Rpar=1e12 Ω

The finite 1 TΩ parallel inductor shunt is an explicit additive fixture choice. The official help warns about automatic damping when Rpar is unspecified; explicitly specifying this large finite Rpar avoids a hidden runtime setting. No undocumented INI key or security setting is used. Its leakage and dissipated work are included. This is not asserted to be byte-for-byte equivalent to the old native inductor.

Ideal inductor current is derived from the unambiguous external sensor:
I_L = I(V_L_TERMINAL) − [V(l_inner)−V(out)]/1e12.
Saved I(L1) is retained as a diagnostic; its built-in parasitic-current reporting convention is not assumed.
Inductor shunt loss is [V(l_inner)−V(out)]²/1e12; external series loss is 0.4*I(V_L_TERMINAL)².

Cout energy uses directly observed cout_inner voltage. It does not incorrectly use V(out) while ignoring ESR. Its series loss is 0.02*I(V_COUT_BRANCH)².
CAP energy is 0.5*1e-6*[V(vin)−V(cap)]²; VIN2 energy is 0.5*4.7e-6*V(vin2)².

All external initial states are explicit. Original RAW t=0 and first postzero sample are separately reported. No abs(time), initial-row correction, duplicate-row removal or fabricated auxiliary state is permitted. The zero-input observation window screens external stores; internal macro initial states remain unknown.

## Observability and signed accounting
Each deck saves 51 named node/current channels. VIN and CAP are saved separately and their differential is derived from the same original samples. No unverified differential .SAVE channel encoding is required. The native RAW header must contain every requested channel with an appropriate voltage/current type.

Signed source work is −integral(Vdrive*I(Vdrive)), with switch-control source work separately included. Macro absorption is the sum of each observed port potential times its inward sensor current. Zero-volt sensor work is also retained, along with load, source resistor, switch, Cout ESR, inductor ESR and explicit inductor-shunt losses.

The external ledger checks delivered source/control work against external stored-energy change, explicit losses, zero-sensor absorption and macro terminal absorption. It cannot split macro absorption into encrypted internal storage and dissipation. It does not certify full hidden PMIC loss closure.

Checks include capacitor signed charge/work identities, ideal inductor flux identity, zero-sensor voltage drops, branch KCL, summed declared-port current, resistor laws and switch behavior away from threshold. Off-state source-current residual has a separately frozen 10 pA absolute tolerance against observed switch voltage/Roff. Negative capacitor power proves release only; no destination or backflow claim is made without port accounting.

## Event and refinement definitions
EXACT-PLAN.json owns every numerical parameter and gate. They are prospective, fixture-specific numerical criteria, not physical tolerances or statistical confidence limits.

PGOOD low reference is 1–4 ms and high reference is 0.45–0.49 s, each with at least eight full-resolution samples, <=10 mV peak-to-peak spread and at least 1 V low/high separation. Event extraction uses 50% of the two observed reference medians solely as a signal-crossing rule. Missing stable references stay unresolved. Native sample brackets are retained without interpolating away transitions. A missing rise/fall by 2 s is right-censored; it is not silently inferred.

Initial PGOOD assertion and later falling are distinct. The nominal 92% value is a falling reference, never an initial-assertion substitute. VIN crossing 5.05/3.67 V references is not direct observation of a hidden UVLO latch. Sleep remains unobserved; no internal node is guessed.

Coarse/fine transition count/order must match, event time-bracket endpoints within 100 µs, and corresponding observed voltage-bracket endpoints within 10 mV. Energy differences must satisfy max(1 nJ,0.5% of the larger magnitude). Both per-trace numerical checks and external zero-state screens are required for a resolved pair. Unresolved PGOOD references cannot pass as matching zero events. Positive rail charging must exceed five times the observed coarse/fine discrepancy in both charge and energy. These are numerical detectability checks only.

Settling designation is optional and separate from execution completion. Both rails must satisfy the frozen W=0.25 s and 2W=0.5 s windows ending at 2 s, after the last command change. No asymptotic or hardware settling time is inferred.

## Budgets and retained data
- At most four native PMIC attempts, including failed starts; no automatic retries or extra cases
- 300 seconds elapsed per attempt; 1,200 seconds total
- 1 GiB RAW per attempt and 3 GiB total; preserve partial files on timeout/cap
- Analyze one case at a time, with an 8 GiB analysis memory budget
- Fine maxstep alone implies roughly 800,000 samples and ~333 MB for 52 double columns including time; adaptive stepping can increase this
- RAW reader rejects files over 1 GiB before reading, and ASCII payloads over 64 MiB before tokenization; binary-double is the frozen output default
- Do not trim, downsample, repair or silently extend a stopped run to make it pass

Retain original deck, RAW, native log, process return code, UTC start/end, elapsed time, exact plan/deck hashes and executable/model/symbol identities, RC-smoke review reference and exact-plan authorization reference. Required fields are listed in EXACT-PLAN.json. Log completion and .meas/RAW consistency are checked. Partial/missing/unsupported data fails closed.

## Consumer-local use
Materialize this Library artifact through the current Library skill into the consuming environment and verify readable local paths. The earlier handoff's absolute paths are historical provenance, not cross-environment mounts.

Dependencies used for static/synthetic tests: Python 3.12.14 and NumPy 2.3.5. NumPy is not bundled or automatically installed.

1. Run python3 -B verify_kit.py to check all sealed member hashes
2. Run python3 -B tests/test_kit.py for static/synthetic checks only
3. Run python3 -B src/static_audit.py --static-only; its output explicitly leaves runtime_ready=false
4. Without --static-only, the static identity checker requires actual model, symbol and executable paths and matching hashes. Absent files/placeholders fail. Even matching hashes do not grant runtime readiness or execution permission
5. In a separately authorized execution copy, acquire the approved official vendor payload through its supported route. Decks expect ../vendor/LTC3588-1.sub relative to their decks directory. No substitute body is included here
6. Establish and independently review actual RC smoke in the supported runtime; then obtain exact-plan execution authorization
7. A supported operator may then run only the sealed cases, enforce the fixed attempt/time/size budgets and retain all evidence
8. Analyze one retained case with src/analyze_retained.py --case CASE --receipt RECEIPT.json --output NEW.json. Outputs must be new paths. This tool never runs the circuit
9. Compare matched summaries with src/compare_refinement.py --coarse COARSE.json --fine FINE.json --output NEW.json. This also never runs the circuit

Receipt references are evidence links, not a substitute for the parent's authorization checks. Both parser and static checker expressly do not authenticate execution. Actual RAW layout and native syntax remain unqualified until RC/native runtime evidence exists. If anything differs, stop and issue a separately reviewed version; do not silently edit these sealed decks.

## Scope
The kit supports prospective external electrical observations of one vendor macro under a declared fixture. It does not authenticate missing historical native RAW, map the material tensor or mechanical modes, validate reset/preparation cost, recommend 10 µF, model a real receiver, or establish startup/mission success or physical-device feasibility.

