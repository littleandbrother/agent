# Battery World Studio and EpiDesign

## One program, one scientific question

Battery World Studio is an observable and experimental laboratory for
battery-free intelligent systems. EpiDesign is the method that turns experience
from that laboratory into independently tested executable design knowledge.

The program has one central scientific question:

> Can a fixed general-purpose coding agent convert the cost of past experiments
> into executable, verifiable, and transferable knowledge that reduces trial
> and error and expands capability on future scientific design tasks?

Battery-free design is the physical domain in which this question is tested.
Code is the knowledge carrier. Studio is the observation and intervention
surface. EpiDesign is the learning and qualification mechanism. DeepSeek
Harness, Codex, or another runner is a replaceable control plane.

The dual product promise is deliberately concrete:

1. the current task ends with a verified system design;
2. future tasks inherit a measurably more capable designer.

Current-task success without future benefit is design search, not continual
learning. More plugins, patches, tokens, or iterations are not evidence of
greater capability.

## Four layers serving one loop

| Layer | Constructed object | Success criterion |
| --- | --- | --- |
| Engineering | an executable battery-free intelligent-edge environment | energy, information, delivery, and mission truth close in one system |
| Interface | a replayable World Studio | a user understands state, failure, evidence, and revision without reading source |
| Agent method | executable knowledge acquisition and reuse | the same base model improves on later tasks under controlled information and cost |
| Paper | a causal continual-design study | executable knowledge beats equal-history alternatives on future tasks and independent conditions |

The shared loop is:

```text
TaskContract + qualified K_g
        |
        v
predict -> design -> experiment -> compare prediction/observation
                                  |
                 design revision, world-model revision,
                    workflow revision, or no update
                                  |
                                  v
                    candidate executable knowledge
                                  |
                    explanation test + use test
                                  |
                                  v
                     promote/restrict/reject
                                  |
                                  v
                                K_g+1
```

## Objects that must never collapse into one another

- **TaskContract:** visible mission, constraints, interventions, and budgets;
  frozen during a formal task.
- **DesignArtifact:** the physical and computational system being designed;
  editable by the participant.
- **CandidateWorldModel:** executable participant understanding used to make
  predictions; editable by the participant.
- **RealityWorld / ReferenceEnvironment:** independent simulator,
  measurement, or device used to generate observations and final truth;
  inaccessible for participant modification.
- **ExperimentRecord:** append-only prediction, intervention, observation,
  cost, identity, and provenance; immutable after sealing.
- **ExecutableKnowledge:** a qualified program, scope, uncertainty, evidence,
  tests, cost, and known failures that runs without its originating session.

This separation prevents an Agent from improving its score by editing the
world that decides whether it is correct.

## Three distinct kinds of learning

- **Design revision** changes capacitance, topology, TinyML model, sampling,
  schedule, or communication policy.
- **World-model revision** changes the executable understanding of ESR, PMIC
  state, transient load, temperature, contact rate, or another mechanism.
- **Workflow revision** changes experiment choice, search, tool routing,
  recovery, or knowledge retrieval.

Every change is typed. A successful patch is not automatically a new physical
insight. A solver-recovery helper is an execution skill, not world knowledge.
No update, narrower scope, or rejection of a plausible revision may be the
scientifically correct result.

## What counts as knowledge

A knowledge object is provisionally defined as:

```text
program + input contract + applicability domain + uncertainty
+ source evidence + independent tests + known failures
+ acquisition cost + execution cost + version
```

It may be a prediction model, experiment procedure, design rule, or execution
skill. Promotion requires two different tests:

- **Explanation test:** predict held-out observations or interventions that
  were not used to construct the candidate.
- **Use test:** improve a future design decision or task relative to fair
  alternatives.

The candidate must receive independent information. A model generating data,
training on those data, and passing its own simulator is not reality-grounded
learning.

## Evaluation center

PMP, EA, and VMS remain current-task endpoints. The central longitudinal
endpoint is future-task capability under total cost:

```text
C_total = C_learning + C_qualification + sum(C_solve(task))
```

The study must report when an initially expensive learning mechanism amortizes
its cost. It must also test removal, transplant, and scope recognition:

- removing a learned module should selectively remove its benefit;
- transplanting it to an Agent without the source conversation should preserve
  relevant benefit;
- applying it outside its domain should trigger abstention, restriction, or
  failure rather than unjustified confidence.

## Claim boundary

The main program targets world-knowledge growth and design-method growth.
Self-modification of the learning mechanism is a later controlled experiment,
not a default capability and not self-certifying RSI.

Rotary-TENG is the first scientific anchor. A later source or device tests
transfer of storage, startup, scheduling, and verification knowledge; it does
not imply that source-specific TENG mechanisms should transfer unchanged.

The desired first complete story is therefore:

> Observe a real execution, locate a prediction failure, use an experiment to
> distinguish explanations, qualify a new executable knowledge object, and
> show that a new task succeeds with less trial and error because it used that
> object.
