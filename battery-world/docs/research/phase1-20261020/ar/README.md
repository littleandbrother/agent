Current result (20 October 2026): final A/R paper and owned-doc handoff is
complete; A is idle for S0 integration. The actual continued Pi episode contains
three candidates and seven settled requests. Rank-hook timing improves, strict
FIFO fails, and product status is NOT_ACCEPTED. See `HANDOFF.md`, `CHANGESET.md`
and `final-pi-20261020/`; commands below document the existing preparation tool,
not a new dispatch authorization.

# Frozen A/R public tool

The single definition is `scripts/campaign_ar_service.py::tool_definition()`.
The trusted host calls `create_handler(output_root, lease=...)` once and retains
the callable, or keeps the `serve` JSON-lines process alive. Arguments contain
no output path, source patch, lease, model selector, shell or acceptance field.
`REQUESTS.json` gives the exact S0 boundary.

`inspect` exposes the frozen task/legal space, candidate schema and original
FIFO candidate, historical facts, or analytical necessary bounds. `check`
accepts a full candidate JSON and materializes the same four task profiles.
It returns public facts and a sealed raw bundle. Exact original JSON reuses
old sealed cases with immutable references and **zero new simulations**.
Changed inputs execute v2; no old success is proof for a changed input.
`submit` saves a reasoned candidate or no-go proposal. Every distinct attempted
candidate, including illegal ones, consumes one of three local revisions.
Interrupted artifacts are retained.

The original template is `configs/studies/phase1-20261020/ar/original-candidate.v1.json`.
The full schema is returned by `inspect(schema)`. Minimum rank wins; ties use
the smallest sequence number. An expression is `{"const": number}`,
`{"field": name}`, or `{"op": name, "args": [...]}`. Arithmetic, min/max and
comparisons take two operands; `if` takes three. Limits are 63 nodes and eight
levels. Fields are `seq`, `kind`, `age_known`, and `age_s`; unknown age is zero
with `age_known=0`. Constants are finite in [-1000000,1000000]. There is no
Python eval, I/O, mutable environment or evaluator-label access. This JSON
program executes in the behavioral scheduler; it is not an MCU binary.

The external consumer runs `verify --bundle ... --receipt ... --expected-seal ...`
after the participant stops. It verifies raw/source identities, reconstructs
frozen inputs without the producer's task materializer, and recomputes
energy/debit/CRC/payload/ACK/program and service facts. It saves a separate
receipt with execution integrity and service outcomes. Unknown time and
hardware remain visible. Empty dark/recovery/dedup/event sets are explicitly
`NOT_APPLICABLE`.

Output is isolated in the registered A runtime `ar-service/` directory. Gzip
writers, metadata and trace horizons are bounded. Sealed and failed outputs are
not overwritten. A fresh host cannot reopen an old episode as a new attempt.
S0 owns real requests, usage/cost availability, three-model slots and episode
admission. Lease JSON does not prove Pi authorship or settled billing.

The model ID is `ar-service-program-v2`: selection/timing hooks over the v1
physical loop. Short injected controls compare FIFO with v1 and independently
consume alternative toy expressions. Those fixtures qualify the apparatus;
they are not proposed product solutions. `ASSISTANCE.json` separates developer
help from later Pi work.
