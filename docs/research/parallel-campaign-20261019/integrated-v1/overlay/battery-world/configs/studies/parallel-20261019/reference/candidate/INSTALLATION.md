# A/R-1 nominal candidate: light-powered reusable-container temperature tag

This is an executable computational design, not fabricated or calibrated hardware.
Install a proposed 90 x 70 x 22 mm enclosure on the **outside** of a reusable
container using two removable straps through mounting ears. Keep the photovoltaic
face outward, unobstructed, parallel to the declared illumination plane. Place a
white reflector directly behind the uncut Epishine module. The antenna occupies
the upper plastic edge away from the mounting hardware. A vented sensor opening
faces the container air; this design senses local air, not sealed cargo temperature.
No washing, ingress-protection, food-contact, or mechanical rating is established.

Proposed stack: 71.5 x 40 mm LEH3_50x30_6_10 module and white backing at the front;
60 x 45 mm power/radio/sensor PCB behind it; insulated 15 mF storage with a 5.5 V
rating; sensor aperture below; plastic standoffs and antenna clearance at top.
These are an installation envelope and connection design, not a PCB/CAD export.
The 50 x 30 mm module has 88% active area (13.2 cm2); actual procurement tolerances,
mounting shadow and installed IV must be measured. Do not fold or cut the module.
Avoid hot-air/IR reflow of the PV foil; follow manufacturer assembly instructions.

The source has no battery or primary-supply fallback. PV connects to AEM10941 SRC;
BATT connects to the capacitor; HVOUT supplies the assumed 1.8 V load. Custom
ready/off/overcharge targets are 2.7/2.3/3.3 V, leaving 0.5 V from off to HVOUT.
Select actual resistor values and qualify tolerances before fabrication. The
reference executes these target thresholds, not an actual resistor network.

Program: PGOOD -> boot -> gateway time sync -> sample every 60 local seconds ->
atomic NVM commit -> send oldest unacknowledged record -> await ACK. A missing ACK
causes a 30 s retry; a good ACK permits the next pending record after 1 s. On
brownout, volatile state and the unbacked clock are lost. NVM records and sequence
identity persist. On a fresh sync, commit a conservative gap interval from the
last durable observation to sync; never fill it with fabricated samples. No
release energy, vibration, external precharge or gateway power is supplied.

The live packet has 20 body bytes plus 2 CRC bytes (ID, sequence, time bounds,
centi-degree temperature, kind, flags). The record image requires 24 bytes after
alignment; 2048 records need 49,152 bytes, so provision at least 64 KiB NVM. Atomic
write behavior, NVM idle power and longevity require device-specific qualification.
Abnormal records outrank routine samples on overflow; evictions are explicit.
All accepted history is retained for this finite task; ACK removes only pending
upload state. History packets remain distinguishable from current observations.

Reproduce with Python 3.11 and the frozen conditions.v1.json. Actual executed
programs are ar.py, b.py and scripts/campaign_reference.py, copied into every
run's candidate tree with hashes. No MCU target binary, BLE stack, native EDA,
or hardware verification is implied by successful host execution.
