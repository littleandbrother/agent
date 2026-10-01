# Simulation semantic alignment

Start with [COMPATIBILITY-REPORT.md](COMPATIBILITY-REPORT.md). Machine decisions are in `MISMATCH-MATRIX.json` and `MIGRATION-GATES.json`.

Run the differential suite in a new output directory:

```sh
python -B run_alignment.py --output /tmp/alignment-replay-NEW
```

`runs/final-v2/run-receipt.json` records 30/30 checks. Expected mismatches are tested as mismatches. Full-model and formal Agent comparison are blocked. `runs/initial` preserves the earlier 27-check development run.

No source evidence, native tools, vendors, paid models, upstream repositories or other workers' checkouts are modified. The test includes real host compilation of unchanged C, original Python implementations, selected exact source-derived CAD input geometry and two actual behavioral integrator solves. Native/ARM execution is deliberately absent.

For a new native observation deck, after verifying its source and applicable authorization:

```sh
python -B src/rail_observation.py --input retained/system.cir --output NEW/observation-only.cir
```

This only adds `.save` observables, refuses overwrites and never executes the deck. See `NATIVE-RAIL-OBSERVATION-REQUEST.json` for required port mapping and new evidence.
