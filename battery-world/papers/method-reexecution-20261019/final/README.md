# Complete methods paper and F saved-data reproduction

`main.pdf` is the complete English paper. `main.tex` and `body.tex` are its editable sources. The established HKUST(GZ) style and official vector mark are included byte for byte. This directory is portable; it does not need the original workbench, private runtime, databases, model access, or scientific apparatus to reproduce its saved-data conclusions.

Run from this directory with Python 3.9 or later:

```bash
python3 -B reproduce.py --data-root data --output rebuilt --negative-controls
```

The command verifies all 643 saved input files, rebuilds `analysis.json`, CSV tables and five manuscript table fragments, and rejects modified, missing and foreign-candidate inputs. The output directory must be outside `data`. It uses only the Python standard library. The core never opens historical absolute paths embedded in original JSON and performs no model request, SDK startup, simulation, native-design mutation or network call.

The F-series scope is explicit:

| Series | Saved-data output | Meaning |
| --- | --- | --- |
| F1 | Response controls | Six early controls; 107 admitted actual responses, including 91 changed-D and 16 exact controls. Valid strategies conservatively share full feedback. No speedup. |
| F2 | Fresh-context/parity audit | 112 fresh design groups and 28 matched proposal groups. No decision-span ablation was performed. |
| F3 | Organization boundary | Single participant Agent per episode. No multi-Agent/organization comparison was performed. |
| F4 | Method comparison | Original prompt probe, rejected posthoc recovery, and formal 12/12 versus 12/12 versus 12/12. Keep unchanged base H. |
| F5 | Selection and transfer | All siblings, six frozen choices, original host incidents plus recoveries, 27 final entries including four censored. H0 7/9, G0 6/9, G1 8/9; descriptive and conditional on one G1 formation. |
| F6 | Failed A/R baseline | Candidate-bound programs, strict FIFO witness and disjoint saved necessary bounds. NO_GO, dark FAIL, FIFO FAIL, NOT_ACCEPTED, physical UNKNOWN. |

`data/manifest.json` lists exact original byte hashes. Embedded absolute artifact locators are preserved as historical provenance only. `data-dictionary.md` explains fields and units. `claim-evidence.json` links claims to inputs and generated results. `cost-exposure-index.json` separates model alias, model exposure, all request costs, developer intervention and unknowns. `AR-HANDOFF.json` binds the selected A/R candidate and both rejected alternatives. The coordinator receives the exact original collection filenames in its separate `source-dependencies.json` receipt; those filenames are not runtime dependencies.

The finite ledger contains 1,238 unique SETTLED requests and USD 10.0268025 at frozen upper token rates. It includes all formation, sibling, selection, original failure, recovery, censored and confirmation requests. Shared interface cells are counted once. Historical UNKNOWN remains 24 outside that denominator; Codex assistance is UNPRICED_NONZERO and end-to-end cost UNKNOWN. Estimates are not invoices.

To rebuild the manuscript after regenerating its tables:

```bash
python3 -B reproduce.py --data-root data --output generated --negative-controls
python3 -B build.py --output-dir build --log-dir build-logs --attempt local-001
```

The second command needs an existing `pdflatex` installation and the packages declared in the sources. It performs two TeX passes and retains logs; it runs no science. Use a new attempt identifier for each build. The delivered table fragments already match the saved data, so a TeX-only service can compile `main.tex` without Python.

For the existing authorized Overleaf project, synchronize **only** these nine paper-source assets, preserving the paths:

```text
main.tex
body.tex
hkustgz-paper.sty
assets/hkustgz-english.pdf
generated/methods.tex
generated/choices.tex
generated/final.tex
generated/ar.tex
generated/costs.tex
```

Set `main.tex` as the main document. References are inline in `body.tex`; no BibTeX or additional graphics are required. The data, Python scripts and local QA logs belong in the reproducibility delivery, not in the minimum paper compile set. This A owner does not publish; S0 manages the existing authorized project and detached acceptance.

The delivered paper is locally compiled and reviewed separately from coordinator detached acceptance. No hardware, root-wide health, fresh scientific replication, repeated G1 formation or stable RSI is implied. The original phases 1–4 are frozen.
