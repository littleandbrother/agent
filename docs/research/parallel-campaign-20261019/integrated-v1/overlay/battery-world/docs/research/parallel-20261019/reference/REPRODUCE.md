# Reproduction and readback

Working directory for every command:
`/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-a-20261019/battery-world`.
Python used for validation:
`/Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python`.
The reference itself uses only the Python standard library.

Read back the existing raw result without new simulations:

```bash
rtk proxy env PYTHONPATH=packages/python/bfworld/src PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python scripts/campaign_reference.py --verify-run /Users/depengsu/.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-001
```

Expected: PASS, 81 sealed files, 17 cases, zero new simulations/model/native calls.
The run has input.json, trace.csv, observations.json and result.json per case;
results.json, results.csv, protocol.json, candidate-manifest.json and seal.json
at top level. `candidate/` contains exact executable sources, input, installation,
BOM and retrieved source documents. No connection to the original Pi runtime
or provider credential is needed.

Produce a fresh deterministic run only if reexecution is desired. The following
directory is intentionally unused; an existing directory is rejected:

```bash
rtk proxy env PYTHONPATH=packages/python/bfworld/src PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python scripts/campaign_reference.py --output /Users/depengsu/.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-002
```

Finite runner limits are frozen in conditions.v1.json: 120 s, 500 MB, >=5 GB
free space, zero paid model/native/hardware dispatches. New runs are public
development evidence under the same frozen assumptions. Do not relabel them
unseen qualification or overwrite an earlier failure.

Targeted tests, then requested integration profile:

```bash
rtk proxy env PYTHONPATH=packages/python/bfworld/src PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -m unittest discover -s tests/agentlab -p test_campaign_reference.py -v
rtk proxy env BFWORLD_VERIFY_PROFILE=architecture-v2-ci BF_V2_RUNTIME=/Users/depengsu/.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a PYTHONDONTWRITEBYTECODE=1 ./init.sh
```

Actual logs and bounded process receipts:
`/Users/depengsu/.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/verification-002/`.
The original failed check is separately retained in verification-001; it must
not be deleted when importing the successful second verification.

The optional API for S0 is `simulate_ar(task)` / `simulate_b(task)` in the two
owned modules. `merge(base, patch)` in the runner materializes a complete input
from conditions.v1.json. The functions return raw trace/activity and records or
packets, not natural-language action advice. `read_case` and `verify_saved`
perform offline independent readback. These are local reference artifacts,
not registered platform RunBundles or a native/physical qualification receipt.
