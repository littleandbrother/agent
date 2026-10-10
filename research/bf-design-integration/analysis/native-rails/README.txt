Offline native-rail replay

Requirements: Python >= 3.10; NumPy >= 2.0. No install, network, solver or model calls are performed by the script. Tested with Python 3.12.14 / NumPy 2.3.5.

This bundle excludes waveform CSVs, vendor models, RAW files and binaries. Retain the already approved input files separately. Input identities are fixed in replay_native_rails.py and input-manifest.json. The packet and producer provenance must be the exact supplied JSONs; the evaluator and method freeze included here are byte-identical copies.

From this extracted directory, using the authorized input paths:
python replay_native_rails.py --coarse INPUT/baseline-observation.csv --fine INPUT/baseline-fine.csv --packet INPUT/bfa035-sanitized-handoff-20261001.json --evaluator settling_validator.py --provenance INPUT/bfa035-rail-producer-provenance-20261001.json --freeze method-freeze.json --out NEW_UNIQUE_DIRECTORY

The output must be a new direct-child directory name, not a path. Existing outputs, symlink path components, wrong hashes, wrong sizes and invalid traces are rejected. Output files are created exclusively with read-only permissions. Hash verification detects later modification; read-only mode is not a cryptographic or filesystem immutable-bit guarantee.

Run only the synthetic/security checks:
python replay_native_rails.py --self-test

Results are deterministic for the tested software versions. NumPy versions may differ slightly in floating-point slope arithmetic. The frozen evaluator uses polyfit; an independent centered least-squares calculation must agree on all predicate booleans. No numerical waveform convergence acceptance threshold is introduced.

Frozen method timing: method-freeze.json was exclusive-created and reported before any full CSV access. provenance-confirmation.json records mapping verification before full CSV access. This is a new replay, not a historical preregistration or replacement of old receipts.

The supplemental producer-expression reconstruction uses a fine-only peak denominator with a 1e-6 floor, as supplied in provenance. The separate frozen replay metrics use pooled peak scale and both shared coarse and union grids. Both are descriptive only. Small differences from reported summaries are retained numerically; native RAW export fidelity is unverified.

File notes:
results.json: complete metrics and checks
input-manifest.json: exact six input identities and replay-script identity, no absolute input paths
artifact-sha256.json: script-generated initial output hashes
bundle-sha256.json: all payload hashes added for this delivery
summary-zh.txt: concise interpretation and limits
safety-checks.json: four actual output/work-directory checks beyond the 21 built-in checks
