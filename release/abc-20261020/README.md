# ABC publication, 20 October 2026

The current branch contains the full BF implementation plus the accepted finite ABC increment. Earlier five-stage artifacts remain in the existing [sealed release](https://github.com/littleandbrother/agent/releases/tag/bf-five-phase-20261020); its bytes and original billing/UNKNOWN history are unchanged.

The [ABC evidence release](https://github.com/littleandbrother/agent/releases/tag/bf-abc-20261020) supplies `BF_ABC_EVIDENCE_20261020.zip`. Its digest and size are in `asset.json`; `evidence-manifest.json` records every included original file. The archive preserves 48 episode records, model input/response captures, participant traces, attempts, failures, source documents, raw service outputs and cost observations. Authentication and provider configuration files are excluded and retained locally. The archive is an incremental evidence delivery, not another runtime or source-tree backup.

Verify source and archive without invoking any model or scientific executor:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 release/verify_source.py --manifest release/abc-20261020/source-manifest.json
PYTHONDONTWRITEBYTECODE=1 python3 release/abc-20261020/verify_evidence.py /path/to/BF_ABC_EVIDENCE_20261020.zip
```

`verify_evidence.py` checks the whole archive digest, path safety, embedded manifest and all 1,442 retained file contents. Original absolute paths remain in sealed records as provenance; extracting an archive does not authorize replaying paid or native jobs. Source-bound measurements, authoring experiments and physical acceptance retain their original boundaries.

With the dependencies in `battery-world/configs/ci/requirements-v2.txt`, a fresh checkout can run the offline software checks:

```sh
cd battery-world
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=packages/python/bfworld/src:tests/agentlab
BF_RUNTIME_ROOT=/tmp/bf-abc-unit BFWORLD_PYTHON=python3 BFWORLD_VERIFY_PROFILE=architecture-v2-ci ./init.sh
python3 -m unittest discover -s tests/agentlab -p 'test_abc_*.py' -v
```

These are fixture-based software tests, not reruns of the scientific experiments. An existing isolated development worktree must use its registered profile instead of the fresh-checkout environment above.

The current manuscript folders are `battery-world/papers/method-reexecution-20261019/abc-20261020/` and `battery-world/papers/interface-sufficiency-20261019/abc-20261020/`. Each is self-contained for a standard `pdflatex` build. Run two passes on `main.tex`, placing intermediates in one temporary output directory and removing that directory afterward. The checked PDFs have 16 and 23 pages respectively. Overleaf compile and first-page checks are recorded under `docs/abc-publication-20261020/overleaf/`.

See `docs/research/abc-cycle-20261020/reviews/FINAL-RESULTS.md` for the scientific result boundaries. In particular, the product remains unaccepted, B shows no refinement advantage, and C shows no improvement over the equal-history baseline. Request costs are frozen-rate estimates rather than invoices. Publication adds no paid requests, scientific executions or native jobs.
