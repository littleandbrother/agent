"""Assumed kinetic rectified-port transients and event retention, version 1.

ECO260's datasheet energy range does not define these synthetic waveforms.
The event latch is an ideal passive mechanical memory assumption, not free NVM.
"""
from __future__ import annotations

import binascii
import math
import struct

MODEL_ID = "b-transient-behavior-v1"


def simulate_b(task: dict) -> dict:
    d = task["device"]
    dt, c = task["dt_s"], d["capacitance_f"]
    if task["model_id"] != MODEL_ID or not 1e-7 <= dt <= 1e-3:
        raise ValueError("unsupported transient model/resolution")
    if not 1e-6 <= c <= 100e-6 or not 0 < d["off_v"] < d["ready_v"] <= d["cap_voltage_max_v"]:
        raise ValueError("storage/threshold domain")
    if d["event_latch"] not in ("passive-mechanical", "volatile"):
        raise ValueError("unsupported event memory")
    e = c * d["cap_initial_voltage_v"] ** 2 / 2
    emax, eon, eoff = (c * d[x] ** 2 / 2 for x in ("cap_voltage_max_v", "ready_v", "off_v"))
    trace, actions, packets = [], [], []
    powered, captured, done = False, False, False
    ready_at, tx_left = math.inf, 0.0
    first_boot = None
    event_id = 1
    for step in range(round(task["duration_s"] / dt)):
        t0, t = step * dt, (step + 1) * dt
        before = e
        rows = [s for s in task["source_segments"] if s["start_s"] <= t0 + 1e-12 < s["end_s"] - 1e-12]
        power = sum(s["power_w"] for s in rows)
        source_j = power * dt
        harvest_j = source_j * d["harvest_efficiency"]
        e += harvest_j
        spill_j = max(0.0, e - emax)
        e -= spill_j
        background_j = min(e, (d["idle_power_w"] if powered else d["off_power_w"]) * dt)
        e -= background_j
        shunt_j = min(e, sum(s["energy_j"] for s in task["shunts"] if t0 - 1e-12 <= s["time_s"] < t - 1e-12))
        e -= shunt_j
        boot_j = tx_j = 0.0
        contact = task["event_s"] <= t < task["event_s"] + task["contact_duration_s"]
        if d["event_latch"] == "passive-mechanical" and task["event_s"] <= t and not done:
            captured = True

        def reset(reason):
            nonlocal powered, captured, tx_left
            if powered:
                actions.append({"time_s": t, "action": "brownout", "reason": reason, "event_was_captured": captured})
            powered, tx_left = False, 0.0
            if d["event_latch"] == "volatile":
                captured = False

        if powered and e < eoff:
            reset("energy-threshold")
        if not powered and not done and e >= eon:
            boot_j = min(e, d["boot_j"])
            e -= boot_j
            powered = True
            ready_at = t + d["boot_delay_s"]
            first_boot = t if first_boot is None else first_boot
            actions.append({"time_s": t, "action": "boot", "energy_j": e})
        if powered and t >= ready_at:
            if contact:
                captured = True
                actions.append({"time_s": t, "action": "capture", "event_id": event_id})
            if captured and not done and t >= d["tx_not_before_s"]:
                if tx_left <= 0:
                    tx_left = d["tx_duration_s"]
                    actions.append({"time_s": t, "action": "tx-start", "event_id": event_id})
                loaded_v = math.sqrt(2 * e / c) - d["esr_ohm"] * d["tx_current_a"]
                requested = d["output_v"] * d["tx_current_a"] * min(dt, tx_left)
                tx_j = min(e, requested)
                e -= tx_j
                if loaded_v < d["output_v"] or e < eoff:
                    reset("tx-transient")
                else:
                    tx_left -= dt
                    if tx_left <= 1e-12:
                        # Eight-byte application body: ID, sequence, key, event, tag.
                        body = struct.pack(">HHBBH", d["id"], event_id, 1, 1, 0xB026)
                        raw = body + binascii.crc_hqx(body, 0xFFFF).to_bytes(2, "big")
                        packets.append({"time_s": t, "hex": raw.hex(), "event_id": event_id,
                                        "loaded_v": loaded_v, "application_bytes": len(body)})
                        actions.append({"time_s": t, "action": "tx-complete", "event_id": event_id})
                        done, captured = True, False
            else:
                loaded_v = math.sqrt(2 * e / c)
        else:
            loaded_v = math.sqrt(2 * e / c)
        trace.append({"time_s": t, "dt_s": dt, "source_w": power, "source_j": source_j,
                      "harvest_j": harvest_j, "conversion_j": source_j - harvest_j,
                      "background_j": background_j, "shunt_j": shunt_j, "boot_j": boot_j,
                      "tx_j": tx_j, "spill_j": spill_j, "start_j": before, "stored_j": e,
                      "voltage_v": math.sqrt(2 * e / c), "loaded_v": loaded_v,
                      "powered": int(powered), "contact": int(contact), "event_captured": int(captured)})
    return {"model_id": MODEL_ID, "trace": trace, "activity": actions, "packets": packets,
            "first_boot_s": first_boot}
