# Battery World system architecture

## Product workbench execution path

The current port-8768 UI is `apps/agent-studio` (任务 / 控制台 / 全景 / 产品).
The older port-8766 World Studio below remains a scientific apparatus viewer.
See [product execution authority](../agentlab/PRODUCT-EXECUTION-AUTHORITY.md)
for reproducible commands and current engineering limitations.

`chat.py → launcher.freeze → Pi chat-product.ts → bf-harness/product.ts`
now loads an explicitly hashed product policy. The Python `/api/product-context`
packet supplies the current revision, input identities, pending/failing jobs and
the same stage verdict used by `/api/deliverables` and assembly projections.
Participants cannot modify stage contracts or submit acceptance decisions.

`engineering-project` snapshots participant CAD Python, self-contained SPICE,
or target C/H projects before bounded macOS execution and trusted native
readback. `beam-event` explicitly maps supported uniform beam geometry into
the existing coupled transient solver. These capabilities are not general
COMSOL authoring, board certification or calibrated physical reproduction.
Source identity, local numerical checks, complete task acceptance and hardware
measurements remain separate. Shared Memory remains unverified notes.

## Architectural center

Battery World Studio is the observable laboratory. EpiDesign is the mechanism
that proposes, tests, and reuses executable knowledge. Neither is the authority
for physical truth. The constitutional kernel, independent reference
environment, sealed records, and qualification boundary remain outside the
participant Agent and its Harness.

```text
                         immutable TaskContract
                                  |
               qualified K_g -----+----- DesignArtifact
                    |             Agent          |
                    |        /      |      \     |
                    | prediction experiment revision
                    |        \      |      /     |
                    |       public capability API |
                    |               |             |
                    |       ObservationBroker     |
                    |               |             |
CandidateWorldModel + Design ------>|<------ RealityWorld
       predicts tau_hat             |        observes tau
                                    v
                         Runtime + ExperimentRecord
                                    |
                       LiveRun --seal--> RunBundle
                                    |
                 independent explanation and use tests
                                    |
             KnowledgeCandidate -> promote/restrict/reject
                                    |
                                    v
                           qualified K_g+1

Studio <----------- reads manifests, traces, receipts, and lineage only
DSH/Codex <--------- replaceable control plane; owns no scientific truth
```

## Authority objects

- **TaskContract** is visible and immutable during a formal episode.
- **DesignArtifact** is participant-editable engineered state.
- **CandidateWorldModel** is participant-editable executable understanding.
- **RealityWorld** is the sealed reference environment. It may be an
  independent simulator, measurement dataset, or device, and always declares
  fidelity, uncertainty, and claim scope.
- **ObservationBroker** is the only participant path to reference observations.
- **ExperimentRecord** binds prediction, intervention, observation, identity,
  cost, and provenance.
- **ExecutableKnowledge** is a qualified program plus scope, uncertainty,
  evidence, tests, cost, known failures, and version.

A participant may revise the design or candidate model. It may never edit the
TaskContract, RealityWorld, sealed records, budget settlement, or qualification
decision.

## Execution and evidence lifecycle

- **LiveRun:** append-only operational state with journal, checkpoints, staged
  artifacts, provider jobs, budget reservation, and recovery audit.
- **RunBundle:** one sealed world or experiment execution.
- **TrialBundle:** one Agent episode referencing multiple RunBundles.
- **QualificationReceipt:** independent decision binding a TrialBundle without
  copying or exposing hidden evaluation internals.
- **StudyBundle:** protocol, task-arm-seed matrix, trials, receipts, exclusions,
  statistics, and paper figures.

Operational job, artifact, evidence, and budget state machines remain separate.
For external tools the recovery guarantee is at most one officially committed
and billed effect per idempotency key. A crash with unknown provider state is
reconciled before any retry.

## Knowledge lifecycle

Participant changes are typed as design, world-model, or workflow revisions.
A successful current-task patch becomes only a `KnowledgeCandidate`.

Promotion requires:

1. held-out prediction or intervention validity;
2. future-task design benefit;
3. independent information not generated solely by the candidate model;
4. explicit applicability, uncertainty, cost, and known failure bindings;
5. regression and scope checks.

Candidates may be promoted, restricted, rejected, or superseded. They cannot
self-promote. No update is a valid scientific outcome.

## Studio boundary

Studio's coordinate is one task, time, version, design, model, and evidence
state. It synchronizes topology/3D, timelines, predictions, observations,
failure certainty, receipts, and knowledge lineage. Every visible quantitative
or verdict-bearing property has a `VisualBinding` to a channel, manifest, or
receipt. Studio never computes PMP, EA, VMS, causality, or qualification.

## Current A boundary

A-001 implements one F1-simplified Rotary-TENG world. The Norton source is
terminal-voltage dependent, the load is time varying, and the revision
introduces an overvoltage clamp. A fine-step run tests numerical convergence.
This is computational apparatus evidence, not a complete coupled mission or
hardware calibration.

Studio, an Agent observation adapter, and the verifier consume sealed artifacts
through readers. None imports the Rotary provider. The architecture above is a
target contract; only capabilities listed as verified in `docs/PROGRESS.md`
exist today.

## Product result read model (BFA-026)

`ProductResults` projects existing jobs, immutable artifacts and assembly bindings into
`/api/results`, with a rebuildable `product_result_index` in the existing SQLite database.
The product page, graph and export consume this owner-scoped inventory; acceptance remains
with `product_authority`. See [result workspace](../agentlab/PRODUCT-RESULTS-WORKSPACE.md)
for APIs, scoped freshness, derivations, export integrity and verified limitations.
