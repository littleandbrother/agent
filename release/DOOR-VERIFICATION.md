# Product results and door-case publication — 2026-09-30

This source snapshot adds BFA-026, BFA-027 and the partial BFA-028 engineering case to the previously published BFA-025 baseline. Only reviewed source paths, portable report inputs/PDF and release metadata are committed. Scientific generated reports, Pi source, credentials and runtime state are unchanged.

## Checks for this publication

- In the independent release checkout: 19 Python tests (`test_engineering_cases`, `test_product_results`, `test_system_results`) passed.
- In the same checkout: 22 Node tests (`test_product_graph.cjs`, `test_product_deliverables.cjs`, `test_product_reader.cjs`) passed.
- Original open `door-case.tex`, with `fontset=fandol`, compiled twice using existing XeLaTeX / TeX Live 2026 and `-no-shell-escape`. The original output path was updated. 36 pages, 22 landscape drawing sheets, no empty pages and no compile warnings. Rendered pages 1, 8 and 36 inspected.
- Native Codex compiler retried: Tectonic format/bundle download recovered; Mac-only STSong dependency fixed; compilation then exposed the editor's unsupported external-assets boundary. **Native editor preview remains unavailable**, not a successful compilation claim.
- PDF/source hashes and every page's checks are recorded in `cases/door-magnetic-D2/report/compile-receipt.json`. Report input files are included at their relative paths.
- Original 399-entry engineering ZIP remains byte-identical to sealed D2. It is a separate Release asset, not a Git blob; archive CRC and all inventory hashes checked before upload. D2-report-r1 changes only report font portability; original scientific values and failures remain unchanged.
- Exported source and report files are inventoried in `source-manifest.json` and checked with `verify_source.py`. A fresh remote clone will be checked after pushing; its receipt is stored locally to avoid self-referential commit metadata.

## Known failures and limits

The last complete application `./init.sh` ran 407 tests with **12 failures and 9 errors**. One isolated Pi launch failed inside the local installed `undici` dependency (`iteratorMixin is not a function`, Node 22.22.0). Other failures have not all been independently attributed. This publication does not claim full application health or resolve them by replacing dependencies silently. The earlier `VERIFICATION.md` describes the older BFA-025 passing snapshot, not this version.

D2 cold-start is failed, the magnetic mesh discrepancy is above the frozen threshold, and native EasyEDA ERC/DRC is unverified. Simulation/independent routing checks are not physical, fabrication, flashing, radio or autonomous Agent acceptance. No paid model calls were made. All original failed scientific results and immutable engineering publications remain retained.
