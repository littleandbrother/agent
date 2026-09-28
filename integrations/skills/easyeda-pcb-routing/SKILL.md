---
name: easyeda-pcb-routing
description: Route and check a PCB in JLCEDA/EasyEDA Professional using the BF Agent workbench MCP adapter. Use for board placement, copper routing, DRC and native export; includes actual document and units checks.
---

# 立创专业版 PCB 布线

Use `bf_engineering` with `engine=jlceda`. `inspect` returns available capabilities and the operator-bound project/board. Read `easyeda-api` when extending an API operation. The adapter uses Nambers/easyeda-pro-mcp (Apache-2.0) over the official API Gateway; it is a community MCP, not an official PCB router.

The desktop half-offline application may not support API project creation. Open a new independent project and bind its exact window/project/board in developer Tools. The adapter refuses a changed project. Do not reuse another product's project by guessing its identifier.

## Design and routing

1. Establish supply/peak current, voltage domains, part numbers, pin/net assignments, board dimensions, stackup and manufacturing constraints. Mark assumptions. Keep energy-harvesting high-impedance nodes, switcher loops, analog sensing and antenna keepouts explicit. A toy connectivity example does not qualify a solar power circuit.
2. `components` accepts `components:[{lcsc,ref,x,y,rotation}]`. Schematic coordinates are **0.01 inch**, not mm or PCB mil. Query actual returned pins before wiring. `wires` accepts `wires:[{net,points:[x1,y1,x2,y2,...]}]`. Use real endpoints; net names alone are not evidence of electrical connectivity. The official `easyeda-schematic-net-fanout` skill assists schematic layout and pin escape, not PCB copper routing.
3. `import_pcb` requests synchronization of the bound schematic with its associated board. In V3.2.148 this opens a native confirmation dialog and the job returns `NEEDS_ACTION`: apply the changes in the EDA window, then use `inspect` to verify actual footprints and all pad/net identities. A true API acknowledgement alone does not prove import. Missing footprints or mismatched pins stop the next step.
4. `layout` takes `board_width_mm`, `board_height_mm`, `positions:[{ref,x_mm,y_mm,rotation}]`. It creates a rectangular outline and refuses an existing outline; subsequent repositioning currently requires the native editor, followed by fresh readback. Returned PCB coordinates are **mil: 1 mil = 0.0254 mm**. Check full package clearance and mounting geometry, not just component centers.
5. `tracks` takes `tracks:[{net,layer:1,x1_mm,y1_mm,x2_mm,y2_mm,width_mm}]` (top=1, bottom=2). Set widths/clearances from current and fabrication requirements; do not treat the adapter's numeric limits as manufacturing rules. Add critical power/analog routes first. No automatic copper pour or impedance qualification is implied.
6. `autoroute` requires explicit `nets:[...]` and optional `ignore_nets:[...]`. Existing copper is preserved. API availability and return fields vary with installed EDA versions. `success` means the routing operation started, not that all networks are connected. Inspect counts, failed nets, resulting copper and DRC. Do not erase protected routes to force completion.
7. `check` and `export` accept `document:schematic|pcb`. The check result is passed/failed/unavailable. Empty/undefined or thrown results are unavailable, never passed. Inspect ERC/DRC and netlist consistency; fabrication requires a separate review of actual rules, unrouted nets, clearance, drill and solder mask.
8. Export the native `.epro2`, original document source, BOM/netlist and PCB Gerber as available. All exports are from real EDA APIs with hashes, attached to the job and Trace. Export does not submit a fabrication order.

## Calling pattern

`bf_engineering({action:'run', engine:'jlceda', operation_id:'stable-unique-id', parameters:{operation:'inspect',document:'pcb'}})` then `action:'job', job_id:...`.

Reuse an operation ID only for an identical request. On unknown completion/timeout, inspect the job and actual document before any retry; never blindly repeat a mutation under a new ID. Keep partial artifacts and errors for review. Readback changes caused by manual editing are new evidence, not proof the previous run succeeded. Only report checks actually returned by the native engine; no physical test, firmware or TinyML validation is implied.
