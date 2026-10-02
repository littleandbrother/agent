# Simulation model semantic compatibility

## Decision

**Do not admit a whole-model or formal Agent comparison yet.** The current upstream native chain, cloud behavioral chain and experimental event-v2 retain separate model identities. This is a real differential harness: unchanged host C, original Python policy/receiver functions, original force functions, source-derived CAD geometry, and actual behavioral integrators were executed. Native COMSOL/LTspice and target ARM firmware were not executed.

- 30/30 checks passed; these include **expected-difference assertions**, not 30 equivalence claims
- 16 primary inputs stayed byte-identical; two additional CAD builders were fetched at commit 338d603 and verified against their Git blob identities
- Matrix: 6 narrow as-is rows, 14 rows needing explicit matched fixtures, 3 rows blocked on native evidence
- New directory only; historical campaigns, pinned source, experimental event-v2 and other workers' development checkouts remain untouched

## Most important new findings

### Gap is not a complete design identity

At gap 48 mm, both coordinate functions agree for the tested 0°,5°,30°,65° points. At other gaps the upstream moves the rotating driver while cloud moves the stationary product. The difference is exactly:

    Δ(dx,dz) = (gap−48mm) × (cos(angle)−1, −sin(angle))

For gap 40 mm at 5°, driver-tip separation differs 0.698 mm and applied transverse force differs 4.76% (0.13609678N upstream versus0.14289651N cloud). At65° the separation difference reaches 8.597 mm. For gap 60 mm at 65° it reaches 12.895 mm. These are different prescribed physical trajectories, not a solver accuracy result.

The upstream CAD check is important: pinned source creates local driver center x=100+gap, then maps it to world x=904−gap; its tip remains world x=904mm. This matches upstream force coordinates across40/48/60mm and four angles each. **No internal upstream CAD→force placement defect was demonstrated.** This checks declared source construction, not native OCCT/STEP readback or dynamic clearance.

Canonical matching binds the pivot/frame, tip world position, driver closed world position, rotation transform, magnet orientation and q sign. contracts/canonical-geometry-fixtures.json stores these explicit numeric fields for both design families. The separate src/canonical_geometry.py check passes 72 original-function comparisons; the physical-coordinate hash matches at nominal 48 mm and differs at 40/60 mm. Magnet orientation remains a declared model assumption, not a physical observation. Retain both prior design/world identities; do not choose one by renaming the gap field.

### Common force algebra does not imply common coupled world

Twelve direct evaluations at matched nominal coordinates agree within 1e-12 N using the actual unchanged force functions. Both use finite uniform cuboids, Br 1.25 T and recoil permeability 1. Upstream supports other Br values; cloud rejects them. The 66×17 versus181×49 force grids produce different interpolated values in five local-cell witnesses. This is not a full-grid or independent magnetic-FEM qualification.

Native beam ROM values are missing. The common passive fixture deliberately injects the inherited cloud ROM and tests reciprocal signs/single-Cp from the actually generated deck against an analytic matrix exponential. That deck was not executed. Its imposed 1 mm free-decay initial state is a **synthetic fixture**, not the native equilibrium/preload.

### Firmware policies are substantively different

On the same imposed 3.3 V supply/PGOOD waveform and 100 µs grid over 0.4 s, first completed TX is 72.1ms upstream and 9.5ms cloud. Both happen to emit four packets, illustrating why count alone hides the workload difference. Default payloads also differ.

A PGOOD drop 400 µs after each implementation enters its own first TX yields 0 versus 1 completed packet. The perturbation is state-relative, so absolute times intentionally differ. A 1.75 V supply perturbation exposes 1.8 V versus 1.7 V brownout thresholds. These are imposed-waveform policy tests, not physically self-consistent PMIC trajectories or target-binary results.

A cloud device-ID fixture matches BFD2 bytes exactly. With identical completed packet records and ideal delivery, receiver grouping matches. Upstream seeded loss/scan semantics and cloud's explicit early mission deadline need separate matching. Neither decoder recovers true motion direction or unique physical events.

### Event-v2 fixes one numerical semantics layer, not PMIC physics

A prospective 4 ms, 6 V/10 kΩ, 0.1 µF diagnostic with an explicitly altered 1 J auxiliary target was run through both actual behavioral integrators. The closed-form RC switching solution has five UVLO events. Event-v2 matches them within 6.2e-13s and final Vin within 5.44e-09V. The old macro implementation differs by 0.244787V at the same endpoint despite a small energy residual.

This confirms a numerical difference under a common synthetic behavioral fixture. It says nothing about vendor-PMIC truth and does not promote event-v2 or repair its inherited startup physical assumption.

## Native rail evidence gap

The pinned native deck has Ccap 1 µF between Vin/CAP and Cvin2 4.7µF to ground. Its explicit.save includes q,u,force,angle,piezo,Vin,Vout,PGOOD and two currents. **It does not save VIN2,CAP,Vin−CAP or rail capacitor currents.** waveform.csv omits them too. Incoming original RAW can support the original metrics but cannot reconstruct deliberately unsaved rail states.

The actual vendor.SUBCKT port declaration must first be mapped to the XU1 instance. Physical package pin numbers are not evidence of macro-model port order. No connection fault is inferred from that unresolved mapping.

NATIVE-RAIL-OBSERVATION-REQUEST.json specifies minimum saves, signed capacitor energy accounting and separate source-on, source-open and driven-down fixtures. src/rail_observation.py creates a NEW save-only derivative without executing a vendor tool or overwriting evidence. A passing save audit means the requested signal names are present, not that the vendor generated valid data.

The optional native-model-interface.json sidecar must be placed by the operator inside the explicit workbench root and contain only the exact interface declaration and model hash/provenance, never the vendor model body. src/settling_validator.py evaluates source-on/off traces against prospectively supplied tolerances across two observation windows; a short trace is insufficient, not settled. Four synthetic validator tests pass, without choosing a native settling time.

Do not infer transient decay/backflow from static datasheet rail relations. Negative capacitor power identifies energy release; destination/backflow needs documented port current accounting. Any revised startup physical surrogate must receive a new model identity and prospective qualification.

## Executable contract and admission

contracts/semantic-contract.schema.json and src/contract.py cover geometry, force, initial energy, trajectory, circuit, firmware, packet, receiver, mission, units and version. Unknown fields, wrong unit declarations, nonfinite quantities and late deadlines are rejected. Full source-default comparison returns admitted=false. An explicit imposed-firmware fixture can be declared comparable only in that narrow scope; this declaration is not a claim that a cloud policy port has been implemented.

MISMATCH-MATRIX.json contains row-specific provenance hashes, source URLs/line ranges, test IDs, retained observations and required matching actions. MIGRATION-GATES.json makes each remaining gate explicit. Existing circuit/firmware/receiver assumptions must be preserved as versioned references; no silent physical adjustment is part of this work.

## Reproduce

From this directory in the restored workspace:

    python -B run_alignment.py --output /tmp/NEW-UNIQUE-ALIGNMENT-RUN

The output path must be new and outside all source trees. Python, NumPy,SciPy,jsonschema and host cc are required; exact installed runtime/compiler/BLAS/source identities are recorded in runs/final-v2/run-receipt.json and host build receipts. Input source hashes are verified before execution and again afterward. The original upstream source tree is partial, so init.sh, full application tests, native CAD/COMSOL/LTspice and ARM execution are explicitly outside coverage.

Report regeneration:

    python -B build_report.py

This reads the retained final run; it does not rerun experiments. build_contracts.py is initial construction only, not part of replay; changing input roots/defaults must create a new contract identity and evidence directory.

## Migration gates

1. Preserve identities and units: portable checks pass
2. Choose a canonical physical placement fixture, preserving both old design conventions
3. Import native beam/force/ROM/preload and source-bound evidence
4. Verify vendor port order, native rail observability and startup physical assumptions
5. Freeze matched firmware, payload, low-voltage load and link/deadline mission policies
6. Run matched coupled cases and numerical/energy/fixed-point checks with retained native RAW
7. Only then consider formal Agent admission with sealed reference, held-out evaluation and cost accounting

No native execution, paid model call, license acceptance, security bypass, upstream commit, cache integration or research promotion occurred in this harness.
