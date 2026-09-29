# Battery World Studio

## Current BF Agent workbench (port 8768)

The current product application is `apps/agent-studio`: **任务 / 控制台 / 全景 / 产品**.
It is served by Python, not by the older World Studio command below.

```bash
# Run from battery-world; install dependencies using ./init.sh first.
export BF_HOME="$HOME/Documents/bf-agent-workbench"
export BF_PI_ROOT="$(cd ../pi-bf-aiot && pwd)"
PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m bfworld.agentlab.server --port 8768
```

Open the local link written to `$BF_HOME/state/launch-url.txt`; it contains an
operator credential and must not be committed or shared. Optional toolchain and
provider configuration, scoped project execution, stage acceptance, verification
commands and outstanding physical gaps are documented in
[Product execution authority](docs/agentlab/PRODUCT-EXECUTION-AUTHORITY.md).
Results, revision comparison, source browsing and complete downloads are described in
[Product results workspace](docs/agentlab/PRODUCT-RESULTS-WORKSPACE.md).
The architecture entry is [docs/architecture/SYSTEM.md](docs/architecture/SYSTEM.md).
Source installation does not install COMSOL, Blender, EDA, MCU SDKs or credentials.

## Scientific apparatus and earlier World Studio

Battery World Studio is an observable laboratory for executable battery-free
intelligent systems. **EpiDesign** is the method for converting experimental
experience into executable knowledge that is independently tested and reused on
future design tasks.

The program asks one question: can the same general coding Agent turn the cost
of past experiments into verifiable and transferable knowledge, so future
scientific designs require less trial and error and previously unsolved tasks
become solvable?

The two intended outputs are:

1. a verified design for the current task;
2. a measurably more capable designer for future tasks.

Rotary-TENG is the first physical anchor. Code is the knowledge carrier. Studio
is the observation and intervention interface. DeepSeek Harness, Codex, or
another runner is a replaceable control plane, not the scientific runtime,
trace authority, or qualification authority.

## Earlier World Studio (port 8766)

```bash
./init.sh
corepack pnpm run studio
```

Open **http://127.0.0.1:8766** for the 3D Studio, coupled missions, live local
experiments, and executable-knowledge lineage. The single HTML export at
`apps/world-studio/dist/index.html` also works offline. Start with
`docs/studio/DEMO-GUIDE.md`.

The A validation writes a RunBundle under `runs/a-rotary-v1/` with:

```text
world.ir.json
run-manifest.json
events.jsonl
channels.parquet
evidence.json
views.json
replay.html
runtime-audit.jsonl
bundle-seal.json
```

The implemented Rotary-TENG model is an F1-simplified, load-dependent
computational model. Passing validation is not hardware evidence and is not a
complete digital-twin claim.

The scientific vision is in [`docs/VISION.md`](docs/VISION.md), the
evidence-gated plan is in [`docs/ROADMAP.md`](docs/ROADMAP.md), and the current
claimable state is in [`docs/PROGRESS.md`](docs/PROGRESS.md).

The frozen A validation record is in
[`docs/protocols/A-VALIDATION.md`](docs/protocols/A-VALIDATION.md). The B
semantic foundation and truth tables are in
[`docs/semantics/B0-GOLDEN-EPISODES.md`](docs/semantics/B0-GOLDEN-EPISODES.md).
Later work cannot change A's scientific semantics in place.

Implemented: A1 Studio, A2 coupled computational world, durable experiment tools,
and scoped knowledge/qualification software. The guided reference study reduces
search on three new tasks, but the fourth remains unsolved and its overall
knowledge qualification is rejected. These are not autonomous Agent/RSI results.

Next research feature: `B1-002-single-agent-pilot`. Fixed model/version, budgets,
provider usage, participant isolation and sealed evaluation remain open. See
`docs/SESSION-HANDOFF.md` and `studies/protocols/fixed-model-pilot.yaml`.

## Repository truth

- `PROJECT.yaml` identifies the active phase and feature.
- `project/ROADMAP.yaml` is the machine-readable research and progress graph.
- `project/features/*/feature.yaml` contains feature contracts and evidence.
- `contracts/schemas/` is the cross-language wire-contract authority.
- `packages/python/bfworld/src/bfworld/` contains implementation modules.
- `fixtures/golden-episodes/` contains deterministic B semantic authorities,
  expected outcomes, and UI provenance—not formal Agent results.
- `migration/legacy-freeze/` records the predecessor repository without making
  it a runtime dependency.
# Current Studio and real Agent pilot

Open `http://127.0.0.1:8766/?view=deployments` for six multi-harvester 3D scenarios,
or `?view=campaign` for the real fixed-model B–C pilot, costs, rejected knowledge
and selected-submission replay. Start locally with `pnpm studio`; build with
`pnpm build:studio`. The compressed single HTML also replays offline.

Current evidence: 18 deployment runs; 36 Agent trials / 63 DeepSeek V4 Flash
calls; CNY 1.463445 conservative cost upper bound. Three knowledge candidates
were rejected: **no knowledge-transfer or RSI success claim**. Research progress
is A1/A2/B1 complete, B2 open, C1/C2 blocked. See `docs/PROGRESS.md` and
`docs/campaign/IMPLEMENTATION.md`. `./init.sh` never launches paid calls.
