# BF design validation: source checkpoint (2026-10-01)

This directory preserves selected UTF-8 source, tests, contracts, dependency declarations, and small provenance records from seven existing BF exports. Original selected files are byte-identical to their archive members. This is a review/integration checkpoint, not a complete evidence archive or a claim of native execution, completed scientific validation, or a production-ready agent.

## Component directories

- `mainline`: alignment implementation, task gates, simulation-chain sources and root cache integration patch
- `development`: authoritative world, causal evaluator repair, controlled protocol, their tests and source inputs
- `static-rom`: beam ROM and generalized magnetic-force interface, static inputs and tests
- `passive`: conditional passive model, structured-Jacobian repair, source inputs, tests and native evidence contracts
- `controlled-integration`: authoritative inputs, dependency locks, Pi launcher layer 01 and magnetic-service layer 02, source fixtures, overlays and tests
- `method-patch`: final method-contract/activation implementation changes and independent offline tests
- `native-observation`: native observation deck generators/readers, contracts, tests and prospective observation plan

Each component preserves its original internal paths after removal of one archive wrapper directory where present. The file manifest records the exact archive/member mapping, byte size and SHA-256. Historical manifests inside components describe their original full archives and will refer to intentionally omitted files; they are provenance, not manifests of this subset.

## Dependency and integration order

1. Inspect the target repository and its existing dependencies before integrating. Apply the root cache patch from `mainline/integration/cache-v2-integrated.patch` against the matching baseline, checking context; do not blindly overwrite unrelated changes.
2. Integrate authoritative world, evaluator and controlled protocol from `development/evidence/` and reconcile the byte-preserved `controlled-integration/authority-inputs/` copies.
3. Integrate beam/static magnetic and passive models as needed by the service; retain their scientific qualification boundaries. The native observation kit is prospective; its decks do not prove vendor execution.
4. Integrate Pi layer 01 from `controlled-integration/layer-01-launcher/`.
5. Integrate layer 02 from `controlled-integration/layer-02-magnetic-service/`.
6. Apply `method-patch/patch-work/changed/` LAST to the layer-02 source/overlay targets described in its original README and diff. Preserve `method_contract.py`, `method-activation.ts`, `method.ts` and associated tests. Older `build_overlay.py` scripts overwrite method sources and must not be rerun after this final patch without reconciliation.
7. Relocate machine-specific paths deliberately, then run source/unit/offline checks. Do not mistake old receipts for fresh validation. Build/test dependency declarations are preserved under `controlled-integration/dependency-locks/`, the Pi overlay package files and mainline requirements files.

## Intentional exclusions and limitations

Excluded: vendor `.sub`/`.asy` payloads and installers; executables/binaries; bytecode and environment folders; generated build/dist/runtime trees; raw trace arrays, TSV/NPZ and bulk CSV; large reports/manifests; most historical run outputs; obsolete revisions; credential/auth store files and credential-collector audit fixtures; third-party text/log evidence; historical workspace instruction files and oversized project narratives. See `EXCLUSIONS.json` for every omitted archive member and reason.

No source logic was changed. No software was installed and no tests, decks or vendor tools were executed while assembling this checkpoint. Some original scripts regenerate omitted fixture-runtime directories; full evidence replay and historical seal verification need the original archive bytes. Generated fixture authentication data are omitted. Source code retains the explicit NONSECRET local probe sentinel needed by its offline tests; it is not a usable external credential. Never replace it with a real secret in committed files.

The selection was scanned for common private-key and credential-token patterns, suspicious literal credential assignments, and accidental assistant-private process markers. No actual credential or private assistant-note content was found in the selected files. This is a bounded packaging audit, not a guarantee against all possible secret formats. Follow normal repository secret scanning before publication and integration.
