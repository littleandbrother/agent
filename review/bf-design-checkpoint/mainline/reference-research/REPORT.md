# Magnetic-piezo reference feasibility pass

Date: 2026-10-01. Scope: read-only source research, no simulation, no participant calls, no changes to existing task contracts or admission.

## Decision

The existing ViPSN-Pluck family remains the strongest published mainline candidate. It supports a **published physical feasibility claim**, not a successful reproduction of current D2. This pass found no newly qualified, independently executable reference that can admit the current DEVELOPMENT tasks. A public-source reconstruction task is plausible; an admitted self-powered design benchmark is not yet justified.

## Evidence matrix (three selected cases)

| Candidate | Demonstrated conditions and energy | Start / delivery evidence | Public artifacts / disposition |
|---|---|---|---|
| **ViPSN-Pluck, Li et al.**, DOI 10.1109/JIOT.2021.3098238, pp3372–3382 | Copper beam 100×10×0.53 mm; PZT area 8×50 mm; magnets 10³/20³ mm³; deployment d=150 mm, bt=30 mm. Single door action; peak acceleration 0.03–0.6 g; reported ≥400 µJ. Parallel SP-SSHI → LTC3588-1/MIC841 → nRF52832; storage 10 µF | Fig6 labels cold-start; plotted storage begins near zero. Mechanical precharging is part of actuation. Exact electrical reset/debugger-isolation procedure and absolute initial mechanical energy are not supplied. Field smartphone packet counts support actual reception; no published per-action timely/correct/deduplicated success denominator | Author PDF, generic platform Altium hardware, SolidWorks module parts, BLE/ESB code. No identified pluck-specific firmware release/raw trial corpus. Best candidate; reconstruction remains unqualified |
| **Paradiso & Feldmeier, Compact Wireless Self-Powered Pushbutton** | 35 mm×7 mm piezo igniter; 3.5 mm travel, ≤15 N, 30 mJ mechanical input. 2 mJ harvested; approximately 0.5 mJ at 3 V. 4.4 µF tank, transformer/MAX666, HT12E/HX1003 | One press; supply starts about 10 ms later and lasts ≥30 ms. Receiver requires four matching 12-bit receipts, approximately 150 µJ/20 ms. Paper says no battery/other source; no modern isolation/repetition protocol | Full schematic and parts description, no CAD/raw trial set found. Genuine independent action-powered reference, but impact mechanism and OOK/ASIC chain cannot establish magnetic D2 feasibility |
| **Jiang et al., Motion-Powered Piezoelectric Pulse Generator**, DOI 10.1109/JIOT.2014.2385891 | 75×27×25 mm; 38 mm beam; 0.5 g/5 mm rolling ball; magnetic coupling, 10 nF load. Measured 135/238 nJ per cycle without/with passive prebias | RF test explicitly replaces harvester with 3 V coin cell charging two 22 nF capacitors; received waveform measured by loop/oscilloscope. FM sensing is simulated | Schematics/model equations exist, but no verified end-to-end harvested-energy RF demonstration. Reject as qualifying reference |

Primary sources: [ViPSN-Pluck author PDF](https://metal.shanghaitech.edu.cn/publication/J40.pdf), [MIT author PDF](https://aspirin.media.mit.edu/responsive/wp-content/uploads/sites/4/2013/12/A-Compact-Wireless-Self-Powered-Pushbutton-Controller.pdf), [Jiang paper at authors' institution](https://www.imperial.ac.uk/media/imperial-college/faculty-of-engineering/electrical-and-electronic-engineering/public/optical-and-semiconductor-devices/pubs/06997986.pdf), [Jiang full paper text](https://www.researchgate.net/publication/270449426_A_Motion-Powered_Piezoelectric_Pulse_Generator_for_Wireless_Sensing_via_FM_Transmission).

Jiang institution PDF was indexed but direct retrieval returned HTTP403; the full paper text, especially journal pp9–12, was inspected through the linked public paper copy. No account or paywall was used.

## Exact phase-load provenance correction

ViPSN-Pluck p3378, Table II (PDF page7, visually checked) reports:

| Published stage | Energy (µJ) | Time (ms) | Derived mean at 3.3 V (mA) | Current model (mA) |
|---|---:|---:|---:|---:|
| MCU initialization | 72.70 | 53.8 | 0.4094851864 | 0.410 |
| Radio initialization | 68.47 | 13 | 1.5960372960 | 1.596 |
| Beacon broadcast | 60.37 | 5 | 3.6587878788 | 3.659 |

Provenance chain: **publication-reported prototype stage energy/time → constant-3.3 V phase-average current inference → rounded configurable load assumptions in our model**. Do not describe the origin as fabricated or wholly unmeasured. Do not describe our currents as measured instantaneous waveforms or our firmware as power-calibrated. The table sums to 201.54 µJ; our rounded constants yield 201.6333 µJ at constant 3.3 V. In a varying supply trace, integrate actual V(t)I(t); the constant-voltage arithmetic is only a reference check.

## Power-stage reconciliation

SP-SSHI and SP-SECE are harvesting-interface topologies. LTC3588-1 is the downstream converter/management IC; these labels are not alternatives at the same architectural layer.

- ViPSN-Pluck is the parallel-SP-SSHI implementation above
- The separate Tang et al. 2025 paper, **A unified system-level simulation framework for energy harvesting, management, and application in plucking piezoelectric energy harvesters**, DOI 10.1088/1361-665X/add8d4, describes **SP-SECE plus LTC3588-1** and a 330 µF comparison. This was verified in [HKUST's publication record](https://researchportal.hkust.edu.hk/en/publications/a-unified-system-level-simulation-framework-for-energy-harvesting/); its complete experimental protocol was not retrieved in this pass
- The restored local PROGRESS record already says the earlier SP-SECE model was NOT_QUALIFIED: predicted 14.1516/3.9810 V against reference 5.30/1.74 V. This is historical local evidence, not a new solve or a validation of the other topology
- The generic [ViPSN platform paper](https://metal.shanghaitech.edu.cn/publication/J29.pdf), pp1733–1737, explains why regulator PGOOD (output-voltage status) differs from MIC841-based stored-energy thresholds, and documents startup failures with a small capacitor when the extra energy indicator is absent. Its speaker-driven pulse test is not a door trial

## What prevents transfer to current D2

The following comparison uses the inspected local contracts/code, not a claim that any one mismatch is experimentally proven to cause the present failures.

1. **Topology and timing:** current solver.py wires piezo directly to the LTC3588-1 macro and includes Cstorage=47 µF, Cout=100 µF, Ccap=1 µF, Cvin2=4.7 µF. No SP-SSHI stage or MIC841 storage-aware controller appears. A matching PMIC part number does not make the systems equivalent. The source paper cannot justify our auxiliary 65.664 µJ stage or its charging/discharging placement
2. **Geometry and material identification:** current nominal x center-gap=48 mm, specific rotating-driver coordinate path, 2 s/65° action, remanence=1.25 T, damping=0.02, PZT-5A/perfect-bond ROM and 8 mm scope are our instantiated assumptions. PZT thickness/grade, glue, clamp, magnet grade and full trajectory are not identified by the paper's partial dimension table. Paper d is a deployment dimension; do not substitute it directly for our magnet-gap variable
3. **Initial state:** current baseline declares Vin/Vout/piezo at zero and solves a mechanical equilibrium preload. This requires a complete physical energy ledger. The publication's relative potential-energy zero is not a measured absolute zero-energy initial state
4. **Firmware:** our shared C state policy is neither execution of the paper's exact nRF52832/SoftDevice image nor a measured power trace. Borrowing phase totals leaves boot order, radio initialization, voltage dependence, inrush, interrupted operations and threshold behavior unvalidated
5. **Receiver and event semantics:** current BFD2 packets have no sequence and use ideal scanning/loss plus silence-inferred groups. This does not reconstruct a smartphone receiver and direction estimator, nor establish timely, correct, nonduplicated events per physical action
6. **Source-data limits:** static figures and summary energy margins cannot supply force trajectories, loaded ringdown, capacitor ESR/leakage, event-level failures, clock/scan behavior or independently held-out evidence. The earlier unqualified transfer must stay marked unqualified

## Artifact inventory and useful next task

[ViPSN public repository](https://github.com/METAL-ShanghaiTech/ViPSN), pinned tree **5a6b13f85c9ee8dfa40e231bae94218f9b562ac4**, was inspected without running its code. The tree contains Altium .SchDoc/.PcbDoc, module .SLDPRT parts, nRF52832/S132 BLE and ESB transmitter/receiver examples. It does not establish an exact paper-build binding. The examined BLE main.c has BMODE=0 and NON_CONNECTABLE_ADV_INTERVAL=2000 ms despite a 100 ms comment; there is also a 1000 ms application timer. This is sufficient to reject blind identity with the published pluck demonstration, not sufficient to infer its effective packet timing without execution. No pluck-named files or raw .csv/.mat/.xlsx measurement set appeared in this tree.

Recommended DEVELOPMENT-only objective: **recover a traceable ViPSN-Pluck reconstruction specification and qualify one no-Agent single-action baseline**, while keeping D2 frozen separately. Before admission, bind exact mechanics/materials/actuation/initial energy, source-matched SP-SSHI+management netlist, firmware/binary/current trace, and action-to-receiver measurement definition. If those inputs remain missing, the correct deliverable is the documented reconstruction blocker, not a fabricated positive reference. No hardware purchase, fabrication, author outreach or simulation is initiated here.
