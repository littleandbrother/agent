# Reproduce the editorial readback and manuscript build

These commands consume the saved actual episode, not a provider or simulator.
Use the same A workspace and existing runtime; no install or native execution is
needed. The raw episode must still be present at its bound absolute path.

```sh
rtk proxy /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B battery-world/papers/method-reexecution-20261019/bind_pi_evidence.py
```

Then set the command working directory to the owned paper directory. Recreate the
removed output directory and run the installed engine twice:

```sh
rtk mkdir -p build-pi-final
rtk proxy /Library/TeX/texbin/pdflatex -interaction=nonstopmode -halt-on-error -file-line-error -recorder -output-directory=build-pi-final main.tex
rtk proxy /Library/TeX/texbin/pdflatex -interaction=nonstopmode -halt-on-error -file-line-error -recorder -output-directory=build-pi-final main.tex
```

The retained canonical main.pdf is byte-authoritative. A rebuild can change PDF
timestamp metadata, so compare source bindings, page content and compiler
outcome; preserve the retained PDF and its hash. To reproduce page previews,
create a fresh output directory and call `pdftoppm -scale-to 1400 -png` on the
retained canonical PDF with that directory's `page` output prefix. Hashes for
the six already-reviewed previews and the exact earlier command are retained in
`visual-review.json` and `rebuildable-cleanup.json`.

The old 21/343 test runs and all scientific/paid attempts are outside this
editorial reproduction. No new dispatch or scientific qualification is implied.
