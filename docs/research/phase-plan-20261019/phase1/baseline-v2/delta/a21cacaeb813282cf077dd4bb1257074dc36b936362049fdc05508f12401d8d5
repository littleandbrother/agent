# Physical anchors and qualifications

Access date: 2026-10-19. Official pages/PDFs were browsed before implementation.
Local PDF hashes/download receipts are in sources/receipts.json. A direct local
Epishine PDF download returned HTTP 403; the browsing tool read its 11-page PDF
and rendered the specification page. This availability limit is retained.

| Anchor | Decisive relation, units and domain | What this supports | What remains unknown |
| --- | --- | --- | --- |
| [Epishine LEH3 v1.1](https://kb.epishine.com/wp-content/uploads/2021/08/LEH3-Data-Sheet.pdf), printed pp.1-2 | LEH3_50x30_6_10 has typical Voc 3.8 V, Isc 88 uA and output 250 uW under 500 lux warm-white LED, 22 +/-2 C, 45 +/-2% RH and white background. The illuminance plots use 3500 K, 22 C and 40% RH. Six-cell active area is 88% of module area. | Source power is tied to spectrum, area, temperature and loading. A lux value alone is insufficient. Proposed module footprint 71.5 x 40 mm and indoor mounting are source-bound. | No installed IV at 200/50 lux; no measured cold-start waveform, shadow/spectrum calibration or selected production module. The assumed 90/20 uW points are not manufacturer guarantees. |
| [e-peas AEM10941 DS v2.3](https://e-peas.com/documents/AEM10941/DS-AEM10941.pdf), p.1 and section 6.1.1 (PDF page 28, printed page 29) | Cold-start typical input requirements are 380 mV and 3 uW. Custom storage thresholds must respect Voff >=2.2 V, Vready between Voff+0.05 and Vmax-0.05 V, Vmax <=4.5 V and VHV <=Voff-0.3 V. HV LDO efficiency depends on VHV/VBATT. | A zero-energy source cannot start. Frozen 2.3/2.7/3.3 V and 1.8 V output targets stay inside the documented configuration domain. An invalid 2.1 V off threshold is rejected by a negative test. | No vendor executable transient model obtained; no resistor/tolerance implementation. Constant 0.8 harvesting efficiency and storage-side activity costs are assumptions, not measured or curve-fitted AEM10941 efficiency. |
| [EnOcean ECO260 November 2025](https://www.enocean.com/wp-content/uploads/downloads-produkte/en/products/enocean_modules/ECO-260/ECO_260_Datasheet_Datasheet_Nov2025.pdf), p.1; [official product page](https://www.enocean.com/en/product/eco-260/) | Output energy 120-210 uJ at 2 V with suitable power management and recommended 0-40 C operation. Each push/release can generate an event. Actuating travel 1.5-1.6 mm and force 1.6-2.7 N are device constraints. | 150 and 210 uJ synthetic input integrals can be checked for range consistency at the declared 25 C. Press/release accounting must be separate. | The energy range supplies neither port waveform nor load response, rectifier losses, contact timing or event memory. No measured V/I, vendor transient model, native simulation or hardware actuation was obtained. |

Both computations therefore have physical_qualification=UNKNOWN. B is a
synthetic rectified-port energy model, not a simulated ECO260. Its mechanical
latch is an explicit passive idealization; the injected shunt is recorded in
the energy ledger. Source range consistency is distinct from physical validation.
The digital receiver establishes byte/CRC/identity/sequence/age behavior only.
No BLE radio success probability, antenna range, sensor calibration, atomic NVM,
RTC continuity, enclosure qualification or MCU binary is established.

The pre-existing piezo/PMIC results, native engineering project and 699 prior
request records were read as history only; none is a new A/R/B result. No native
solver was rerun. These source-level anchors satisfy the finite E7 document
check; they are not low-cost physical measurement or high-fidelity validation.
