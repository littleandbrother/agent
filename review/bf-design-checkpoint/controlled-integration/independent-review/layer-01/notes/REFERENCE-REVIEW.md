# Independent review: public reference reconstruction

Status: passes the declared source-reconstruction and static-algebra scope. This does not admit dynamic execution, an independently feasible reference, or any native/physical equivalence.

## What was independently checked

- All 13 retained public artifacts were rehashed using Git's blob framing and compared with the previously pinned repository tree and size entries, at commit `5a6b13f85c9ee8dfa40e231bae94218f9b562ac4`.
- The sealed package's 62 base-file hashes/sizes and the 3 additive review-file hashes/sizes verify. No producer file was changed.
- Tests were rerun in an independent copy: 29 base plus 4 additive tests pass. These are static source/software checks, not circuit runs.
- A separate CFB FileHeader parser reconstructed component text/property records. The 2.0 source's six diode comments are literally NRS0240H and their symbol-library identities are Diode 1N4004; older 1.0 harvesting sources have SS14/SS16 comments. The package does not silently combine these versions or turn model-library names into authenticated device models.
- A separate two-node conductance matrix gave ideal-divider storage thresholds 10.664 V and 2.9622222222 V. Enumerating both inputs' signed 10 nA leakage corners gave 0.189 V and 0.0958333333 V maximum absolute threshold shifts. Exact source resistor-property strings are Rc1=7.5M, Rc2=3.9M, Rc3=1.5M.
- The manufacturer MIC841 sheet independently confirms the nominal reference, full-temperature reference interval, leakage maximum, output-variant distinction and 3 Mohm recommended total input resistance. The source's 12.9 Mohm total is a design/provenance caveat, not itself proof the published physical board failed.
- The onsemi sheet identifies NSR0240H and physical cathode/anode pin ordering. The report properly leaves the NRS spelling, inherited diode symbol numbering and actual footprint mapping unresolved rather than accusing a manufactured board of a proved error.
- Firmware source constants BMODE=0, 2000 ms advertising constant and 1000 ms timer are visible. They do not bind the built author prototype or establish executed packet timing.

## Scope safeguards

MIC841 is powered by LTC VOUT while its divider monitors Vsto. Thus the stated thresholds assume an adequately powered comparator and do not specify cold-start behavior before VOUT exists. MB6S is encoded as a Header 2X2 symbol with an MB6S footprint, without a qualified bridge SIM model. The additive tests preserve this distinction and explicitly check mirrored multi-part T2 endpoints.

The generic platform source is not an exact ViPSN-Pluck board/BOM/binary release. Native Altium/PCB netlist verification, component/pad mapping, exact MIC841 suffix, semiconductor/loss models, inductance behavior, native macro port binding, load/receiver behavior and independent same-mission witness remain open. The new asynchronous-buck equations are instantaneous power-accounting algebra only, with no dynamic controller, component selection, calibrated efficiency or startup claim. `interface_blockers` cannot self-authorize or admit a reference even when its synthetic fields are filled.

The prospective plan preserves the action, geometry, deadline, mission, no precharge and no external electrical energy. No scientific trajectory, commercial execution or paid model call was performed in this review.

## Review artifacts

- `outputs/REFERENCE-SOURCE-AND-NODAL-READBACK.json`: independently recomputed Git blobs, source property rows and nodal calculation
- `outputs/REFERENCE-BYTE-VERIFICATION.json`: producer manifest/addendum identities
- `outputs/reference-base-tests.log` and `outputs/reference-addendum-tests.log`: isolated reruns
- `tests/review_static_reference.py`: reproducible independent checks

## Primary references

[ViPSN pinned source](https://github.com/METAL-ShanghaiTech/ViPSN/tree/5a6b13f85c9ee8dfa40e231bae94218f9b562ac4), [Microchip MIC841/2 datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/20005758A.pdf), [onsemi NSR0240H datasheet](https://www.onsemi.com/download/data-sheet/pdf/nsr0240h-d.pdf)
