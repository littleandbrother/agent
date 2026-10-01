# AGENTS.md

This repository implements a controlled, evidence-governed Battery World.

The single program question is whether a fixed general coding Agent can convert
past experimental cost into executable, independently testable knowledge that
improves future design capability and amortized cost. Battery World Studio is
the product; EpiDesign is the method. World, Studio, Harness, evidence, and
evolution infrastructure serve this question rather than competing with it.

## Startup

1. Read `PROJECT.yaml`, `docs/VISION.md`, `docs/ROADMAP.md`,
   `docs/PROGRESS.md`, and `docs/architecture/SYSTEM.md`.
2. Read `project/ROADMAP.yaml` and the active feature under
   `project/features/`.
3. Run `./init.sh` before claiming the active feature is healthy.
4. Work only in paths owned by the active feature.

## Constitutional boundaries

- Contracts are language-neutral and implementation-free.
- Kernel identity, budgets, evidence binding, and qualification cannot be
  replaced by a participant Agent or Harness.
- Runtime owns the live journal, checkpoint, artifacts, and exact recovery.
- Worlds implement typed ports and never import Agent, DSH, Studio, or private
  evaluation code.
- Studio is a projection of the trace and never computes scientific verdicts.
- DSH is a replaceable control plane and never owns scientific persistence.
- Hidden qualification remains outside participant profiles.
- Evolution can propose candidates but cannot self-promote.
- No Agent experiment starts before the no-Agent A reference is sealed.
- Design, candidate world model, reference reality, workflow, and executable
  knowledge are distinct versioned objects.
- Current-task repair is not knowledge promotion. Promotion requires held-out
  explanation and future-task use evidence from an independent reference.
- No update, scope restriction, and rejection are valid scientific outcomes.

## Evidence rules

- `.bfworld/` and `runs/` are generated and ignored.
- Small deterministic fixtures may be committed only with a feature receipt.
- A semantic change creates a new schema/provider/world version.
- Never overwrite a sealed RunBundle or qualification receipt.
- Computational F1 results are not hardware results.
- Legacy prototypes do not count as current progress unless reproduced under a
  current Feature receipt.
- Milestones have no manual completion percentage. A milestone is complete only
  when every exit gate in `project/ROADMAP.yaml` is evidence-bound and passed.

## Definition of done

A feature is complete only when its hypothesis, falsifier, owned paths, schema
changes, tests, negative controls, command, artifacts, cost boundary, claim
boundary, limitations, and handoff are recorded in its `feature.yaml`.

Do not commit unless the user asks.
