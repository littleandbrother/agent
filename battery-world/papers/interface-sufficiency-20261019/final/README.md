# When Battery-Free Interfaces Support Design Changes

Independent English development manuscript, 20 October 2026. The final PDF is
`interface-sufficiency.pdf`; editable LaTeX starts at `main.tex`. The shared
HKUST(GZ) style and official vector logo are copied byte-identically for a
standalone source package.

## Rebuild saved-data tables

From this directory, using the existing Python installation:

```sh
python3 E_reproduce.py --data-root data --output generated
```

The helper uses only the Python standard library (verified with Python 3.11).
It verifies all 80 manifest-bound saved records, rebuilds five CSVs and eleven
LaTeX tables, and writes `generated/checks.json` and `generated/summary.json`.
It fails for missing/tampered inputs. It does not import archived implementation
snapshots, follow their historical absolute paths, use an SDK, contact a model,
or execute any scientific simulator, qualifier, consumer or evaluator.
`--data-root` and `--output` accept relocated directories. Defaults are resolved
beside the script, so invocation from another working directory also works.

## Build the paper

```sh
python3 build_paper.py --output build --pdf interface-sufficiency.pdf
```

This requires existing `pdflatex`, the packages named by `main.tex` and
`hkustgz-paper.sty`, and Poppler's `pdfinfo`, `pdffonts`, `pdftotext`, `pdftoppm`.
No environment installation is performed. The helper runs two TeX passes with
shell escape disabled, checks unresolved references and layout warnings, checks
embedded fonts and required text, and renders every page at 100 dpi. Its receipt
is `build/build-receipt.json`. The deliberate epstopdf notice about disabled
shell escape is recorded; all included artwork is PDF. A failed attempt retains
`build/build-failure.json`; preserve its logs before retrying after a source fix.
Rendered pages still require direct human/agent visual inspection. The original
15-page build was inspected on every page; the coordinator handoff binds that
exact PDF, build sources and review record.

## Evidence and implementation maps

- `data/manifest.json`: 80 byte-exact historical records, relative paths and hashes.
- `data/DICTIONARY.json`: every saved file, schema, status, field and unit conventions.
- `claim-evidence-index.json`: 13 main claims, resolved saved-data pointers and limits.
- `case-observation-handoff.md`: case laws, controls, typed-observation route and code map.
- `model-exposure-cost-index.json`: model identity, versions, exposure, interventions,
  limits and usage for all 112 main groups and 77 secondary attempts.
- `citation-verification.json`: three verified primary external references.

The archived implementation snapshots are for inspection. They are not a
standalone scientific runtime or an authorization to rerun model/physical work.
Source and evaluator semantics remain frozen. The package reproduces saved-data
arithmetic and document generation, not a fresh independent science replication.

## Interpretation

Keep all twelve formal E5 groups (7 complete, 5 incomplete), all nine final O
episodes (3 PASS, 2 FAIL, 4 censored incomplete), original host incidents and the
separately labelled post-hoc repair. O0 and E4 shared cells must not be counted
again. Rate estimates are not invoices; global historical UNKNOWN usage and
full end-to-end/Codex cost remain coordinator-owned and UNKNOWN where unpriced.
Physical qualification remains UNKNOWN; original A/R and FIFO failures preserve
product NOT_ACCEPTED. No native dispatch, provider request or scientific run was
added by this final-paper work. The coordinator owns combined packaging, its
single acceptance pass and any Overleaf publication.
