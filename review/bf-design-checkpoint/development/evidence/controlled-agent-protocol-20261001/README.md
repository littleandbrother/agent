# Controlled Agent protocol preparation

The additive prospective protocol separates fair device-design (D) comparison from participant-authored Harness (H) improvement. The original E0–E7 ledger is preserved. No frozen 768-run matrix, model or budget is inferred.

Read `PROTOCOL.md`, `REUSE-MAP.md`, `protocol.schema.json` and `protocol-draft.json`.

Run:

    python -m unittest test_preflight -v
    python preflight.py protocol-draft.json

Exit 2 is the expected blocked result for the draft. Exit 0 means a populated offline contract passes consistency checks, never authorization to execute. `live_launch_allowed` is always false; there is no model/provider/solver dispatch code. For an immutable saved receipt choose a NEW output path with `--output`; existing receipts are not overwritten.

The tests use synthetic manifests and trusted, fixed source fixtures. Positive fixture contracts are intentionally fictional and are never stored as formal approval. Tests prove guard behavior, clean fixture import/invocation, stale/pre-import rejection, and exact H0 rollback. They do not qualify the existing Pi/macOS sandbox, participant behavior, hidden evaluation, native physics or scientific improvement.

All source/existing evidence was read only. New files are confined to this directory. No full `init.sh` was rerun or application-wide health claimed: the current integration receipt records the actual macOS isolation and scoped native limitations. There are no unrelated STM32 test requirements added.
