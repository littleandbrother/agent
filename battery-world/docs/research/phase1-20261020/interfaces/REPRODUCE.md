# Reproduction and gate behavior

Use the registered CAD Python; do not install an environment. Run commands from this B checkout's `battery-world` directory. All Python calls use `-B` and `PYTHONDONTWRITEBYTECODE=1`. Existing sealed outputs are read-only; `prepare` requires a new owned output directory.

Readback of the delivered preparation (no solver/provider/native execution):

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/python/bfworld/src /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B scripts/campaign_bf_interfaces.py verify --output docs/research/phase1-20261020/interfaces/data/BFP-1516e936ff2a3bd8902e
```

One participant mount can be checked independently with `input --trial-dir <participant-directory>`. It must contain exactly its manifest, packet and listed assets; the gate does not read the evaluator index. The trusted runner must mount one directory alone for a future live study. The current host process is not an OS sandbox.

Capability admission (expected rejection, exit code 2):

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/python/bfworld/src /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B scripts/campaign_bf_interfaces.py gate --profile /Users/depengsu/.local/share/bf-phase1-20261020/b/profile.json --action agent
```

After the storage gate is satisfied, regenerate the finite export with `prepare --profile <registered-profile> --output <new-directory-under-docs/research/phase1-20261020/interfaces/>`. Source hashes, baseline, profile identity and live capacity are checked before the output directory is created. Never overwrite `BFP-1516e936ff2a3bd8902e`. Regeneration reuses old results and executes no old model; wall-clock/host capacity receipts naturally differ.

`replay --profile <registered-profile> --output <sealed-bundle> --trial <opaque-id> --operation read_spec` returns one active-regime observation. `read_current` is the uninformative control; `read_raw` returns complete raw; `query_model --patch '<announced-patch-json>'` reads the saved response only. Fixed regimes, unsupported operations or uncached design queries reject. Costs describe one read request; cumulative live-trial limits require a future kernel-owned ledger and are not implemented by accepting caller-supplied histories.

Targeted tests, only when capacity permits their temporary export:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/python/bfworld/src:tests/agentlab /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B -m unittest test_campaign_bf_interfaces -v
```

Repository CI must inherit all registered isolation variables: `BF_RUNTIME_ROOT`, `BF_RUNTIME_CONFIG`, `BF_HOME`, `BF_PI_ROOT`, `BF_DEVELOPMENT_PROFILE` and `PI_CODING_AGENT_DIR=<profile.home>/pi-config`. The system `HOME` is not changed. Use `BFWORLD_VERIFY_PROFILE=architecture-v2-ci` and the owned `configs/studies/phase1-20261020/interfaces/verification-python.sh` as `BFWORLD_PYTHON` to make the unmodified `./init.sh` invoke the registered Python with `-B`. The recorded run currently returns eight native-capability errors; do not turn native on to make these tests green.

The separate saved-evidence verifier is read-only:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B docs/agentlab/architecture-v2/power-feedback-20261018/verify_saved.py
```

Paper rendering was actually run after storage admission. From `battery-world`, regenerate its fragments and source bindings with:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/python/bfworld/src /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B papers/interface-sufficiency-20261019/render_phase1.py --bundle docs/research/phase1-20261020/interfaces/data/BFP-1516e936ff2a3bd8902e
```

Compile from `papers/interface-sufficiency-20261019` so the shared style/assets and local fragments resolve correctly. The actual build used two passes; only one final PDF is retained after visual/hash review:

```sh
rtk proxy mkdir -p build
rtk proxy /Library/TeX/texbin/pdflatex -interaction=nonstopmode -halt-on-error -file-line-error -output-directory=build manuscript.tex
rtk proxy /Library/TeX/texbin/pdflatex -interaction=nonstopmode -halt-on-error -file-line-error -output-directory=build manuscript.tex
```

The delivered file is `interface-sufficiency-phase1.pdf`; the build output was moved there after review. `phase1-binding.json` binds the fragments, renderer, manuscript, frozen data and shared style/logo; `delivery-manifest.json` also binds the final PDF and page/build receipts. Fresh compilation may change PDF timestamps, so the recorded PDF hash identifies this delivered build rather than promising timestamp-independent binary reproduction.

All five final pages were rendered with `pdftoppm -png -scale-to 1600`, inspected individually, and checked with `pdfinfo`, `pdffonts` and `pdftotext -bbox`. Final warnings are zero, all 14 fonts are embedded, and word boxes are within the page. The historical generated-results bytes are unchanged. Auxiliary and page-raster scratch was deleted only after PDF/source/raster hash readback; build logs, page-review records and raster hashes are retained for audit. Preserve shared assets and all earlier gate/configuration rejection logs.
