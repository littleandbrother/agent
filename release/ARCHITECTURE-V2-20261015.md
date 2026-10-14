# BF Architecture V2 source checkpoint

Branch: `codex/bf-architecture-v2`.
Base: `3dc8a72056e85b71998c4160da309474c2cbee1c`.

This checkpoint adds the project design repository, immutable system/domain
commits, source-bound interface contracts, specialist Pi transport and scoped
execution. The Lab now lives alongside the existing Studio, uses native SVG
icons, and links the six views through the selected project and system commit.
System history is a horizontal four-track timeline. Engineering previews,
public Pi trace and same-version release downloads use the repository read API.

The original Web endpoint is `http://127.0.0.1:8768/lab#system`. Its read-only Lab
bridge points to the independent V2 service at port 8870. Original Studio data
and the ten original paper sessions remain in the existing runtime.

## Verification

- 109 targeted Python checks passed.
- Pi `npm run check` passed, including TypeScript and browser entry checks.
- The Lab publication profile passed 30 live checks and seven bridge tests.
- Seven preview hashes and the same-version ZIP were read through the original
  Web service. The 6,388-file frozen Baseline was verified.
- No model request or unchanged successful simulation was dispatched for this
  publication.

Evidence: `battery-world/docs/agentlab/architecture-v2/github-publication-20261015/`.
UI report: `battery-world/docs/agentlab/architecture-v2/lab-ui-20261015/REPORT.md`.

## Source and runtime

`source-manifest-20261015.json` records exported checkout bytes. Verify with:

```bash
python3 release/verify_source.py --manifest release/source-manifest-20261015.json
```

Credentials, live SQLite databases, native project originals, runtime histories,
large solver data and deployment rollback copies stay outside this source
checkpoint. Environment setup is documented in
`battery-world/docs/agentlab/architecture-v2/AB-REPORT.md`.

V2 candidate import is complete. Contract integration and the specialist Pi
pilot are still under development; complete parent-source inheritance needs a
new Pi consumption run. Comparative method experiments remain pending. The
original Baseline branch stays at its previous published commit.
