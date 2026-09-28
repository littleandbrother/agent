# B0-000 executable semantic golden episodes

## Decision and scope

B0-000 freezes scientific meanings through four deterministic examples before
the repository freezes B's cross-language wire schemas. It does not implement a
full coupled provider, Agent condition, DSH integration, 3D Studio, hidden task
bank, hardware validation, or RSI result. All episodes are F0 semantic fixtures.

The frozen A-001 bundle remains an independent predecessor authority with
bundle identity:

```text
sha256:6fa761099b10c9b10060a3636380e5d83221cd95272ee6ac9efa96955ad97059
```

Every suite validation independently verifies that identity before accepting
the B0 fixture manifest.

## Authority separation

Each episode contains five distinct objects:

| Object | Agent mutable | Authority |
| --- | --- | --- |
| `MissionContract` | no | visible mission requirements |
| `RealityWorld` | no | sealed fixture truth and qualification outcome |
| `CandidateWorldModel` | yes | participant's executable prediction model |
| `DesignArtifact` | yes | harvester, circuit, model, and schedule choice |
| `ObservationBroker` | no | sole path from participant to public reality observations |

`PredictionRun`, `ExperimentRun`, and `QualificationRun` are separate semantic
operations. Public prediction evidence binds the `CandidateWorldModel` hash; it
does not expose or bind the hidden `RealityWorld` as a participant capability.

## Outcome equations

Physical success is recomputed from request and trace facts:

```text
PMP = QualityValid AND Delivered AND DeadlineMet
      AND ElectricalSafe AND DeploymentFeasible
```

`Delivered` requires receiver ACK. `DeploymentFeasible` contains static Flash,
SRAM, and operation constraints; voltage dynamics belong only to
`ElectricalSafe`.

Evidence admissibility is independently recomputed:

```text
EA = IdentityCurrent AND ScopeCovered
     AND ClosureComplete AND IndependenceSatisfied
```

The final endpoint is:

```text
VMS = Submitted AND PMP AND EA
```

The fixture also reports false admission, valid design not submitted,
abstention, and no submission/timeout. In G1-G3, the deliberately incomplete
public predictor admits a candidate even though sealed reality fails it. These
are negative controls for false admission, not evidence that those designs are
scientifically valid.

## Unified execution semantics

The state vector includes simulation time, shaft speed and angle, harvester
charge, terminal voltage, PMIC state, storage voltage, MCU state, sensing
buffer, prediction, radio state, and mission state.

At equal timestamps, the only valid order is:

1. continuous electrical integration;
2. PMIC threshold transition;
3. MCU power-state transition;
4. sensing, inference, or transmission application event;
5. mission evaluation.

Changing that order invalidates the episode even if the enclosing JSON is
re-hashed. B0-002 will later freeze clock precision, interpolation, and
cross-engine tolerances after the semantics survive a real coupled slice.

## Golden truth table

| Episode | Quality | Delivered | Deadline | Electrical | Static deploy | EA | PMP | VMS | False admission |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| G0-PASS | yes | yes | yes | yes | yes | yes | yes | yes | no |
| G1-OVERVOLTAGE | yes | yes | yes | no | yes | yes | no | no | yes |
| G2-BROWNOUT | yes | no | no | no | yes | yes | no | no | yes |
| G3-WRONG-DIAGNOSIS | no | yes | yes | yes | yes | yes | no | no | yes |

G0 and G2 each receive 12.0 mJ total harvested energy and allocate identical
sensing, inference, and radio energy. G2 nevertheless browns out because its
harvest and TX burst are phase-misaligned. This twin pair rejects average-energy
closure as a sufficient electrical-safety criterion.

All deterministic ledgers implement:

```text
E_harvester = delta(E_storage) + E_sense + E_infer + E_radio
              + E_rectifier_loss + E_PMIC_loss + E_leak
              + E_dump + residual
```

The current F0 fixture gate is normalized residual below 1%. This is a fixture
consistency gate, not a calibrated solver-accuracy claim.

## Evidence and failure certainty

Evidence receipts are immutable and bind subject artifact, claim, verifier and
version, provider, scenario, device/session, fidelity, assumptions,
independence group, observed result, uncertainty, and creation time. `CURRENT`
is an expected derived state; it is not stored by mutating a receipt.

Failure Lens data has four levels:

1. observed violation from the trace;
2. structural dependency path from topology;
3. candidate explanations;
4. confirmed causal factor.

No fixture promotes a confirmed causal factor because no paired intervention or
counterfactual experiment is present.

## Visual provenance

Every expected visual binding names the visible property, source channel,
transform, unit, source kind, fidelity, and episode. Studio may project these
facts, but it must not calculate PMP, EA, VMS, or causal certainty itself.

## Reproduction

```bash
./.venv/bin/python scripts/build_golden_episodes.py
./.venv/bin/python scripts/validate_golden_episodes.py --rebuild
./init.sh
```

The second command checks the episode seals, recomputes all truth tables and
cross-episode invariants, independently verifies A-001, and requires a fresh
materialization to be byte-identical.

## Next contract boundary

Only after this feature passes may B0-001 freeze authority and bundle
lifecycle contracts for `MissionContract`, `RealityWorld`,
`CandidateWorldModel`, `DesignArtifact`, `LiveRun`, `RunBundle`, `TrialBundle`,
`QualificationReceipt`, and `StudyBundle`. Job, artifact, evidence, budget,
trace, visual, task, and arm contracts remain intentionally unfrozen here.
