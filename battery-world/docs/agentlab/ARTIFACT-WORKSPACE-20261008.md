# Product artifacts, delivery and runtime workspace — 2026-10-08

Implemented locally in BFA-035 on `codex/integrate-dot-20261002`; preserved existing uncommitted changes. This is interface and artifact projection work. It does not accept the engineering product, prove Pi autonomy or establish physical validation.

## Visible changes

- The right pane has two peer tabs: **工程工作区 / 运行动画**. The animation fills the entire right pane, with tabs and controls floating over the canvas. It pauses when hidden; returning to it retains the scene instead of creating a second renderer. Engineering keeps its discipline tabs, now including firmware.
- Camera controls restore full view, collaboration, product and five specialist viewpoints. Mode controls switch between live runtime events (default) and an explicitly labeled preset demo. Play/pause and demo replay operate only on the renderer; no task execution is dispatched. Returning from demo reprojects the actual task state, including failed native checks. The collapsible runtime record retains authoritative status and resource details without consuming canvas height.
- Product opens the latest actual records and files for six disciplines. Each card links to the engineering pane and shows file source, applicability and check status. Native EDA failures remain failures even when their CLI process succeeded.
- Delivery uses the same selected file scope as Product and the engineering pane. It shows searchable files, source job/version, readability and preview/download links. Packaging freezes and verifies the snapshot; a new artifact cannot silently replace an export already being assembled.
- The two main delivery actions use clear glass backgrounds and readable dark text instead of blue fills.
- Global navigation defaults to a small handle. Entering the top edge with a mouse reveals a compact glass bar; leaving closes it after a short delay. Clicking or keyboard activation also reveals it. Escape and the close button collapse it. Hidden controls are inert; keyboard focus within the open bar is retained. Touch targets and reduced-motion/transparency preferences are supported. The overlay does not push or resize the workspace.
- The scene no longer creates five duplicate floating specialist labels or the central Dot name, English description and speech bubble. After visual review, workstation plates retain their compact original proportions: titles use Inter Regular vector outlines at a consistent 0.28 cap-height-normalized font size, subdued dark ink and pixel ratio up to 2. Small taglines are removed. Title geometry avoids raster-texture minification without oversized bold text. The textual runtime/check summary below remains authoritative. Original standalone animation files were preserved; host-adapted source, pinned build dependencies and hashes are recorded in `apps/agent-studio/runtime-scene/`.

## What caused stale or missing output

The old default assembly scope omitted unbound but real output. Different screens fetched their own projections, and Product held new results behind a manual update action. Native typed EasyEDA receipts were not included, while firmware domain detection primarily knew older target names. Heavy conversation history reads delayed the product path.

`ResultCatalog` now shares requests by owner/revision across screens. Runtime events invalidate the catalog with a 200 ms debounce. A lightweight owner-scoped version query checks every 2 seconds while the page is visible; full file integrity is periodically rechecked at 30 seconds. An invalidation during an in-flight request schedules another read. Late responses cannot replace a different owner's view. Product avoids fetching full conversation history except when its graph needs that data.

`latest`, `session`, `assembly` and archived case scopes are explicit. Latest includes recent attempts and available successful artifacts per category; it does **not** make different source versions a single accepted assembly. The assembly view retains its separate acceptance criteria.

## Native file authority

`eda_results.py` reads owner-bound command receipts and verifies their receipt hashes. It does not rerun native tools, infer an entire workspace tree or load all historical traces. Latest relevant receipt per project/document/command is presented.

Native exports are included only when a receipt explicitly names `result.artifactPath`, under the selected participant's `.easyeda/artifacts` directory with a permitted suffix and size. Path escapes and foreign owner receipts are rejected. The current export bytes are hashed and rechecked for download/packaging. This proves receipt path association and current-file integrity: the original CLI did not provide a creation-time export hash, so historical byte identity is not claimed.

## Verification

From the Battery World root:

```sh
rtk proxy env PYTHONPATH=packages/python/bfworld/src:tests/agentlab .venv/bin/python -m unittest test_artifact_workspace test_product_results test_studio_delivery test_system_results test_engineering_workspace test_runtime_architecture
rtk proxy node --test tests/agentlab/test_result_catalog.cjs tests/agentlab/test_engineering_workspace.cjs tests/agentlab/test_studio_model.cjs tests/agentlab/test_delivery_view_lifecycle.cjs tests/agentlab/test_runtime_studio.cjs
rtk proxy env BF_STUDIO_DEPENDENCIES=/Users/depengsu/.local/share/bf-agent-runtime/ui-tools/agent-studio-scene/node_modules node apps/agent-studio/runtime-scene/build.mjs
rtk proxy git diff --check
```

- 51 Python tests passed. Negative cases include foreign/tampered receipts, export path escape, unbound output, mixed target firmware and owner-scoped version changes.
- 19 Node tests/groups passed, including 27 engineering projection assertions, shared requests, event refresh, invalidation during requests, stale responses and export view lifecycle.
- Live browser: matching 103 latest files in Product and Delivery; native DRC failure counts visible; peer workspace/animation tabs; clear glass actions; default collapsed navigation; Enter reveal and Escape collapse; zero floating specialist labels; no browser console errors in the final check. At the observed viewport, the right pane was 703×688 px and canvas 702×688 px (one-pixel border), confirming full coverage. PCB camera, demo mode, pause/play and return to live were exercised; the actual paused task and DRC 24/36/1 counts remained intact.
- Generated and downloaded the engineering archive through the UI: 105 ZIP entries (103 artifacts plus manifest/offline entry). ZIP integrity and all 103 per-file SHA-256/byte counts passed. ZIP SHA-256: `bf4c8d616714a9cc1e62df25a3843cc81d56092bcbb35167471ef3556c119ee4`.
- Local read timings, observations rather than a controlled benchmark: initial catalog 3.410 s; a warm updated catalog 0.454 s; final catalog including native exports 0.784 s. Final lightweight version 0.084 s, latest-scope delivery 0.533 s. Scope payload changed, so these should not be treated as an isolated speedup measurement.

Evidence lives under `/Users/depengsu/.local/share/bf-agent-runtime/ui-rollouts/20261008-artifacts-live/`, including final catalog/delivery JSON, timing records, `archive-verification.json`, `runtime-full-pane.jpg` and `delivery-glass.jpg`. Service was restarted earlier only after read-only checks found no active jobs. Later static changes required browser refresh only. No new paid requests, native operations, simulations, fee reset, commit or push were performed. Full repository `init.sh` was not run and repository-wide health is not claimed.

## Current product and handoff

Owner `pi-chat-8ae12ef0354d33bb` is **PAUSED / CHAT_TURN_WALL_BUDGET**. Model request count remained 4196 through final read-only checks. Prior HTTP 402 is historical and is not the current task status; provider spending authorization was not expanded by this UI task.

- Reuse `eng-28deaae4839d843d` nominal coupled simulation; no relevant design change or rerun here.
- Latest actual target firmware is `eng-e0516772a5a40e54`, including nRF52832 ELF/HEX/BIN and prior host checks. This UI work does not rerun or newly accept its physical timing.
- Native PCB DRC receipt `eda-c9ea821d5d400dbc94c9` still reports 24 clearance, 36 connection and 1 netlist errors despite CLI success.
- Mechanical/PCB consistency, BOM/interfaces and acceptance of one coherent product version remain unresolved. Physical qualification remains unverified.
- A readable engineering archive is a snapshot of available records, including stale/unbound/failed ones with labels. It is not the accepted unified product delivery. The technical-report option remains explicitly unavailable when no corresponding PDF has been produced.

Continue product closure under the existing owner and budget after resolving its pause/authorization conditions. Do not infer completion from this interface deployment, archive generation or decorative scene.

### Title clarity revision

User rejected the first oversized bold-outline treatment. Final version retains 3.86×0.81 world-unit plates and muted blue-gray ink, with Inter Regular outlines at 0.28 cap-height-normalized size. Visible title heights are 0.285–0.294 (about 20% smaller than the compact Helvetiker revision); all five fit within the plates. The pinned upstream static Inter 4.1 webfont has resolved overlapping contours, avoiding the triangulation defects found in the first variable-font conversion. Live overview and firmware close-up reviewed after refresh; vector counters and edges are intact, Dot labels/bubble count 0 and browser console errors 0. Final evidence: `runtime-inter-titles.jpg` and `inter-title-fit.json`. Font glyph subset and original license/source hash are bundled locally; no font network request at runtime. [Three.js FontLoader](https://threejs.org/docs/pages/FontLoader.html) is used only to parse the pinned outline data.
