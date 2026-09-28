# Source release verification — 2026-09-29

This release is a source snapshot of the currently developed BF-AIoT Agent and
workbench. Verification was performed in `agent-github-release`, independently
of the live application's source directory, on the original macOS host. It is
not a qualification on a new machine or a hardware/paid-Agent acceptance run.

## Completed checks

- Pi dependency installation from `package-lock.json` and `npm run bf:build`:
  passed (Pi, BF Harness and BF Agent).
- New Python 3.11 virtual environment, dependencies from `requirements.lock`,
  Python package build/install, and frozen pnpm installation: passed.
- Product graph and product deliverable projection tests: 17 passed.
- EasyEDA community MCP self-tests: 50 passed (16 websocket, 16 bridge,
  18 target selection). These use local mock windows, not a real PCB.
- Workbench started on an ephemeral loopback port with new isolated state:
  index, product scripts, Three module, health and authenticated state returned
  HTTP 200; zero jobs and zero used model tokens.
- Explicit file inventory audit found no provider key, GitHub token, private key,
  credential file, local runtime database or file over 50 MB. The exact installed
  local provider credential was also compared without printing its value.

## Clean-source initialization issue

Full application checks exposed an existing ordering bug: Studio tests loaded
coupled and B2 manifests before the generators had recreated their ignored
`runs/coupled` and `.bfworld/b2-development` directories. The first two attempts
each stopped at the Studio fixture setup with one missing-artifact error (368
tests discovered/executed; the nine Studio projection cases could not start).
The existing development workspace masked these dependencies with cached outputs.
`battery-world/init.sh` now invokes `scripts/build_coupled.py` and the existing
`scripts/build_studio.py` materializer before the tests that consume them. It
uses the same generators and leaves the scientific model and sealed fixtures
unchanged.

Full application recheck: **passed**, 377 Python tests (including the nine Studio
projection cases), TypeScript SDK check, Studio type check, self-contained
frontend build and source-to-view validation. Full command: `cd battery-world &&
./init.sh`. No additional provider calls were made.

## Boundaries

Absolute local paths in captured application code still refer to the original
workbench/toolchain setup. Some integration checks use installed local tools and
the original Pi path. Passing the checks does not prove all optional tools are
portable or that arbitrary new machines can execute the complete product task.
See the root README before relocating the runtime.

Builds can regenerate environment-specific validation reports. The release
retains the original source-bound reports rather than promoting regenerated
machine-specific copies as new scientific results. `source-manifest.json` binds
the exported bytes, including the small initialization-order correction.

The older Long-Horizon AI Agent coordination repository, its Git history, full
private workbench state and large COMSOL/engineering binaries are not part of
this source release. There were no new model calls and no physical operations.

Git remote commit and fresh-clone readback are checked after the source commit;
their receipt is retained by the local release coordinator to avoid a
self-referential commit hash in this file.
