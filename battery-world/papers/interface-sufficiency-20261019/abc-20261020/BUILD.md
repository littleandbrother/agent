# Full interface manuscript, ABC increment

This folder is independently compilable from its included TeX, eleven retained
historical table sources, four new table sources, three vector PDF figures,
canonical style and official English vector mark. It preserves the complete
earlier manuscript argument and integrates the new eighteen-attempt results.
It does not duplicate the earlier raw-data package.

Run from this directory using the existing registered Python 3.11.9 runtime
(Matplotlib 3.11.2), installed pdfTeX and Poppler. No new environment is needed.
The included tables and PDF figures are sufficient for the document-only build:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B build_paper.py --render
```

To rebuild the new four tables and three figures from the included small data
views before building the document:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B build_tables.py
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B build_figures.py
```

`build_paper.py` invokes installed pdflatex twice, then Poppler checks. `--render`
temporarily renders every page under `.build/pages/` for visual inspection.
Only the final PDF and first-page preview are retained in the delivered folder;
`.build` is rebuildable scratch. The final receipt records actual visual review.

To re-extract the small new source views from the existing canonical archive:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B extract_evidence.py --root "/Users/depengsu/Documents/Long-Horizon AI Agent"
```

This extraction reads JSON, CSV and compressed saved traces and verifies the
canonical B report hash. It never imports or executes the scientific apparatus.
`data/source-manifest.json` identifies the original receipts and five deduplicated
trace inputs. `data/formal-episodes.csv` retains all eighteen attempts, including
two budget stops after correct actual submission. Rates are estimates rather
than invoices; the earlier historical costs and UNKNOWN boundaries remain.

The preserved earlier package retains its own standard-library `E_reproduce.py`
and complete raw inputs. That package is referenced, not copied here. The new
derived views reproduce this document's tables and figures; they are not a
standalone rerun of the scientific experiments. No submission, push, publication,
new model/Pi run, scientific execution, or physical measurement accompanies
this manuscript preparation.

The delivered PDF has 23 pages. The final two-pass build completed with zero
recorded LaTeX warnings, and all 23 rendered pages were visually inspected.
`build-receipt.json` records that review; `PAPER-HANDOFF.json` lists every retained
file except itself with its size and SHA-256. Rebuilding creates a fresh receipt
whose visual-inspection field stays pending until the new render is reviewed.
