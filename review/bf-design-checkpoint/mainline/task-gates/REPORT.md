# Development-task admission and startup-model sufficiency

## Decision

**Neither development task is currently admitted.** The package supplies executable, fail-closed task gates and two public-contract drafts. It does not claim a known-feasible battery-free design, physical impossibility, Agent superiority, or new native validation. No dynamic solver, participant model, license acceptance, hardware action or Git operation was performed.

- **DEV-FEASIBLE-01, Commission a first-opening switch:** ordinary end-to-end design with an independently feasible reference inside the same permitted design space. No mechanism is selected to force architecture recomposition. The required witness is missing.
- **DEV-COUPLING-01, Recover cold-start event delivery:** continuation from the actual gap42/Cin0.1/Cout100 failure, with identical service/world boundaries. It is a natural source/storage/startup bottleneck, but no independent successful intervention has been established. The observed Cout null effect is not evidence of successful co-design.

These are a design-run template and a same-state-continuation template, **not two independent commissions** or interchangeable statistical units. A second full commission needs a genuinely different, requirement-owner-frozen installation/service brief. Inventing one here would conceal the missing facts.

## Recovered public facts, and what still needs agreement

Historical baseline JSON and pinned native nominal source agree on a 2 s opening to 65°, zero electrical initial conditions and zero external electrical injection. The historical mission gives a 4 s observation/deadline and at least one received event. The initial force equilibrium is nonzero; electrical cold start never meant zero stored mechanical energy.

The historical 900 × 2100 × 40 mm door, mounting placement and 136 × 62 × 66 mm housing are explicitly design assumptions, not measured customer limits. The 8 mm displacement boundary belongs to the inherited linear ROM. It is neither a task-enforced physical limit for every possible architecture nor a safety qualification. The weak-motion acceptance requirement has no frozen numeric trajectory. Installation envelope/clearance, actuation-force limit, allowed parts/materials, receiver action semantics and mechanical preparation/reset boundary remain unresolved.

Correct event attribution and zero duplicates are proposed acceptance requirements consistent with the paper's valid-event metric. They are not falsely labeled as already implemented by the historical silence-group decoder. All these facts must be available in the initial request or fixed-facts clarification sheet before a task is admitted.

## What the existing negative cohort actually establishes

Read-only recomputation from the sealed CSV selects the 20 original fine-step designs, excluding the separately labeled spatial addendum. All 20 have zero received events; all 20 coarse/fine comparisons passed their declared checks. This is conditional evidence under the existing behavioral assumptions, not global design-space exclusion.

The gap42/Cin0.1 case reaches UVLO 44 times but never auxiliary-ready, Vout, boot or reception. `pmic_started=true` only means a UVLO-enable occurred. Its peak auxiliary energy is 11.104952 µJ versus the model's 65.664 µJ target. Cout1/10/47/100 has identical checked upstream metrics for each fixed Cin. That invariance follows the blocked downstream path: output current is zero until auxiliary readiness, and zero Vout makes output load/leakage zero.

This case begins with **2.147485 mJ mechanical equilibrium energy** and produces approximately **40.050823 µJ net piezo electrical work** in its old trajectory. The spring's 8 mm energy is about 2.790449 mJ. None of these quantities can be equated with harvestable load energy, imported into a changed topology without reciprocal recomputation, or supplied for free as an artificial release. The old model lacks explicit nonlinear latch/contact/release and closed-cycle reset accounting.

## Startup: preserve the energy, question the timing

[ADI LTC3588-1 Rev C](https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf), printed pp7–8/Fig1, distinguishes VIN2 and CAP, with 4.7 µF to ground and 1 µF across VIN–CAP. Its ideal rail relation loads both capacitors before UVLO. Their ideal stored energy at 4.8 V differential is **65.664 µJ**. That energy is real under this topology; an independent post-UVLO lumped barrier and 0.1 s off-decay are not established by the datasheet. Printed p13/Fig6 permits rail rewiring for input kept below6 V and flags clamp leakage; the figure's output is1.8 V. Our retained3.3 V hypothesis therefore needs separate validation.

The official primary-source PDF was independently downloaded for local research only, SHA-256 `f1e52b155e35b2b5fe70ee05f5cdf130a577488df648703054bf2f57395c7c1d`; no PDF or screenshot is redistributed in this package.

The historical model reaches VIN5.05 while Eaux can still be zero, then charges its separate auxiliary store at an assumed1 mA. Under the ideal quasi-static rail relation, Cin0.1 plus the two bypass capacitors would already contain approximately66.939125 µJ at that VIN, rather than just1.275125 µJ in Cin. This is an explanatory static comparison, **not a universal hard startup threshold or native transient prediction**. Finite rail charging, regulator loss, source impedance and decay must come from an actual model or data. The vendor deck contains separate capacitor nodes but its native evidence is currently unavailable here. Its saved-variable list omits CAP/VIN2 observables, so old RAW alone cannot settle those dynamics. The macro-model .SUBCKT port declaration/order is also unverified; package pin numbering must not substitute for it. A new versioned observable extension and bounded diagnostic are needed.

An exact old-model counterexample requires no dynamics: below5.05 V, its auxiliary equation is dE/dt=−E/0.1 with E(0)=0, so E stays0 indefinitely. At settled2.5 V and4.5 V, the datasheet ideal rail relation instead implies17.8125 µJ and57.7125 µJ in the bypass capacitors. No undocumented finite settling time is assumed.

Do not remove the stored energy, set the old barrier to zero, relax the mission or declare native truth. Preserve old outcomes under their original model identity and create a new version for any semantic change.

## Frozen program cost comparison

Source arithmetic in `STARTUP-MODEL-ANALYSIS.json` extracts actual constants without importing/executing solver or firmware libraries:

| Chain | Mandatory first-TX states | Time | Charge | Energy at constant3.3 V |
|---|---|---:|---:|---:|
| Historical behavioral | reset1 + clock1 + boot3 + init2 + read1 + payload0.2 ms at3 mA; TX1.2 ms at5.3 mA |9.4 ms|30.96 µC|102.168 µJ|
| Pinned native | boot53.8 ms at0.410 mA; init13 ms at1.596 mA; TX5 ms at3.659 mA |71.8 ms|61.101 µC|201.6333 µJ|

These are **executable but unmeasured assumptions**. They exclude WAIT/off/reset sampling overhead, voltage variation, quantization, interrupted TX, repeated boots, capacitor charge and all power-path losses. The C policies differ on PGOOD loss, so the totals are not matched firmware improvements or actual transient energy budgets. A faster firmware design requires corresponding source/build and independent timing/current bounds. Lowering only assumed currents or durations cannot qualify a reference.

## Architecture openness without unsupported physics

Every main method receives identical permission to change mechanical structure, circuit topology, firmware and their interactions, including passive release if properly modeled. No strong baseline is fixed to the inherited architecture. The current providers cannot execute all those freedoms: the old chain accepts only the inherited beam/materials and fixed3.3 V behavioral topology; the new native spec has a fixed beam/topology and bounded parameters. This mismatch blocks an architecture-open task. Unsupported candidates must yield model-extension/insufficient-evidence status, not be miscounted as failed physical designs.

Numerical and native checks are provider-specific and must be frozen before reference evaluation. The historical5% mesh/step targets and stricter event-model checks are preserved separately. A source-test pass, native connectivity, external-power positive control or dummy witness cannot satisfy mission qualification.

## Minimal next work, finite and gated

1. Import the already requested native evidence; inspect actual rails and raw trajectories, initial/reset energy, native model/ROM identities and missing magnetic qualification. Freeze mission/installation/weak-motion/receiver facts.
2. Qualify a **specific real power topology**, rather than tune an auxiliary-energy parameter. `HYP-LOWVIN-3V3-v1` in the startup JSON is a blocked hypothesis: same Cin47/Cout100/L10 and native firmware, CAP→GND, VIN2→VIN,3.3 V selection retained. A real protection BOM must prove worst-case VIN≤5.8 V, strictly below the source's6 V condition, including tolerance/overshoot/temperature. The5.8 V guard is our proposed engineering margin, not a supplier specification. Actual clamp leakage, capacitance, dynamic resistance and pulse-energy limits enter both the dynamics and ledger. No ideal zero-leak clamp or numerical voltage clipping is permitted.
3. Proposed **at most four matched joint solves**, default versus qualified low-input topology, coarse/fine each, fixed common native mechanics/firmware/W. These are not authorized or run; exact models, leakage budget, solver resource caps and independent reviewer are still needed. Reuse exact matching baseline evidence. Stop at this cohort or an applicability/voltage/qualification failure.
4. Only if necessary and independently justified, propose one qualified mechanical patch and one electrical/program patch; at most eight coarse/fine D,D+a,D+b,D+a+b cells. Do not force synergy, exclude a valid single-domain repair or expand adaptively. A real feasible no-Agent reference must be sealed before participant runs. No successful reference means admission remains blocked.

The four-cell topology diagnostic and eight-cell mechanical/circuit decomposition are **conditional proposals, not an automatic12-run campaign**.

## Holdouts and verification

All existing20 designs, source comparisons, diagnostics and these reasoning results are development-exposed. Future confirmation tasks/changes must be separately frozen and independent by parent commission; paraphrases do not create independence. Keep reference solutions and acceptance traces outside participant paths. All methods get the same public facts/checkers. A final independent/held-out result must not select a historical candidate or feed back into the same run.

Run `python -m unittest test_admission -v` inside this directory. Run `python admission.py --output ADMISSION-RECEIPT.json`; exit2 intentionally means valid contracts with blocked readiness, exit1 means malformed/changed sources, exit0 requires all admitted. The gate checks source digests, energy and mission preservation, equal architecture permissions, evidence roles, numerical/domain assertions, independent-reference lineage and no synthetic/powered witness. It is a trusted-operator validation contract, not cryptographic authentication or a substitute for scientific review.

Sealed source and data files were read only. The package changes only its new directory. No existing receipt, failed outcome or protocol ledger was rewritten.
