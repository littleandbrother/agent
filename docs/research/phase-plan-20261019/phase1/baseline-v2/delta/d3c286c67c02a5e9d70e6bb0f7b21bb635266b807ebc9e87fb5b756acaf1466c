"""Finite public-development light/storage/program reference, version 1.

Power is an explicitly assumed port input in watts. Illuminance is never
converted to power. This module is not a calibrated Epishine or AEM10941 model.
The consumer checks saved traces independently in scripts/campaign_reference.py.
"""
from __future__ import annotations

import binascii
import math
import struct
from typing import Any


MODEL_ID = "ar-light-behavior-v1"
WIRE = struct.Struct(">IIiihBB")
OFFLINE_RETRY_S = 30


def _at(segments: list, t: float, key: str | None = None, default=0):
    for row in segments:
        if isinstance(row, dict):
            if row["start_s"] <= t < row["end_s"]:
                return row.get(key, default) if key else row
        elif row[0] <= t < row[1]:
            return row[2]
    return default


def frame(record: dict, device_id: int, historical: bool = False) -> bytes:
    lo, hi = record["time_interval_s"]
    flags = int(record["time_known"]) | (int(historical) << 1)
    body = WIRE.pack(device_id, record["seq"], round(lo * 1000),
                     round(hi * 1000) if hi is not None else -1,
                     round(record["temperature_c"] * 100), record["kind"], flags)
    return body + binascii.crc_hqx(body, 0xFFFF).to_bytes(2, "big")


def _receiver(raw: bytes, now: float, record: dict, task: dict) -> tuple[bool, str]:
    """Digital endpoint only: no RF propagation, BLE stack, or hardware claim."""
    if len(raw) != WIRE.size + 2:
        return False, "length"
    if binascii.crc_hqx(raw[:-2], 0xFFFF) != int.from_bytes(raw[-2:], "big"):
        return False, "crc"
    device, seq, lo, hi, temp, kind, flags = WIRE.unpack(raw[:-2])
    if device != task["device"]["id"] or seq != record["seq"]:
        return False, "identity"
    if kind == 2:
        return (hi >= lo, "gap")
    if not flags & 1:
        return True, "uncertain-history"
    # Old queued history is accepted as history, never as a fresh live sample.
    if not flags & 2 and now - lo / 1000 > task["required_sample_period_s"]:
        return False, "stale"
    return True, "history" if flags & 2 else "live"


def validate(task: dict) -> None:
    d = task["device"]
    if task["model_id"] != MODEL_ID or task["dt_s"] <= 0:
        raise ValueError("unsupported reference model or time step")
    if not 0 < d["capacitance_f"] <= 1 or not 0 <= d["cap_initial_voltage_v"] <= d["cap_voltage_max_v"]:
        raise ValueError("storage outside declared domain")
    if not (2.2 <= d["off_v"] < d["ready_v"] < d["cap_voltage_max_v"] <= 4.5):
        raise ValueError("AEM10941 threshold domain")
    if d["output_v"] > d["off_v"] - d["dropout_v"]:
        raise ValueError("HV LDO dropout domain")
    if not 0 < d["harvest_efficiency"] <= 1:
        raise ValueError("efficiency outside (0,1]")
    if d["sample_period_s"] < task["dt_s"] or d["nvm_capacity_records"] < 1:
        raise ValueError("unsupported scheduler/storage resolution")
    previous = 0.0
    for row in task["source_segments"]:
        if row["start_s"] != previous or row["end_s"] <= previous or row["power_w"] < 0:
            raise ValueError("source segments must cover horizon in order")
        if row["power_w"] and not 0 < row["mpp_ratio"] * row["voc_v"] <= 4.5:
            raise ValueError("source operating point outside input domain")
        previous = row["end_s"]
    if previous != task["duration_s"]:
        raise ValueError("source horizon mismatch")


def simulate_ar(task: dict[str, Any]) -> dict[str, Any]:
    """Execute the supplied immutable task and design; return raw observations.

    One-second default steps integrate background energy; sense/write/TX are
    storage-side energy impulses with an additional ESR/dropout guard. This is
    suitable for service chronology, not regulator switching or RF transients.
    """
    validate(task)
    d = task["device"]
    dt, horizon, c = task["dt_s"], task["duration_s"], d["capacitance_f"]
    e = c * d["cap_initial_voltage_v"] ** 2 / 2
    emax, eon, eoff = (c * d[x] ** 2 / 2 for x in ("cap_voltage_max_v", "ready_v", "off_v"))
    trace, actions, committed, packets, arrivals, gaps, evictions = [], [], [], [], [], [], []
    memory: dict[int, dict] = {}
    pending: list[int] = []
    seq = 0
    powered = False
    next_sample = next_tx = boot_ready = math.inf
    sync_at: float | None = None
    last_durable = 0.0
    reset_since_sync = False
    gap_start = 0.0
    high_since = None
    high_reported = False
    receiver_seen = set()
    ack_loss = d["ack_drop_first_n"]
    first_boot = None

    for step in range(round(horizon / dt)):
        t0, t = step * dt, (step + 1) * dt
        start_e = e
        src = _at(task["source_segments"], t0)
        source_j = src["power_w"] * dt
        vsrc = src["voc_v"] * src["mpp_ratio"]
        permitted = vsrc >= d["cold_start_voltage_v"] and src["power_w"] >= d["cold_start_power_w"]
        harvest_j = source_j * d["harvest_efficiency"] if permitted else 0.0
        e += harvest_j
        spill_j = max(0.0, e - emax)
        e -= spill_j
        background_j = min(e, (d["sleep_power_w"] if powered else d["off_power_w"]) * dt)
        e -= background_j
        boot_j = sense_j = write_j = tx_j = 0.0
        gateway = any(a <= t < b for a, b in task["gateway_windows"])
        temperature = float(_at(task["temperature_segments"], t))

        def turn_off(reason: str):
            nonlocal powered, next_sample, next_tx, sync_at, reset_since_sync, gap_start, high_since, high_reported
            if not powered:
                return
            actions.append({"time_s": t, "action": "brownout", "reason": reason, "energy_j": e})
            powered = False
            next_sample = next_tx = math.inf
            high_since, high_reported = None, False
            gap_start = last_durable
            reset_since_sync = True
            if not d["clock_persistent"]:
                sync_at = None
            if not d["nvm_persistent"]:
                memory.clear()
                pending.clear()

        if powered and e < eoff:
            turn_off("background-threshold")
        if not powered and e >= eon:
            if e - d["boot_storage_j"] >= eoff:
                e -= d["boot_storage_j"]
                boot_j += d["boot_storage_j"]
                powered = True
                first_boot = t if first_boot is None else first_boot
                boot_ready = next_sample = t + d["boot_delay_s"]
                next_tx = boot_ready
                actions.append({"time_s": t, "action": "boot", "energy_j": e})

        def store(kind: int, temp: float, interval: list, known: bool) -> bool:
            nonlocal e, seq, write_j, last_durable
            if e - d["write_storage_j"] < eoff:
                actions.append({"time_s": t, "action": "write-blocked", "kind": kind})
                return False
            if len(memory) >= d["nvm_capacity_records"]:
                routine = [s for s in memory if memory[s]["kind"] == 0]
                victim = min(routine) if routine else min(memory)
                # Priority protects events; no silent loss: every eviction is durable output.
                evictions.append({"time_s": t, "seq": victim, "kind": memory[victim]["kind"], "reason": "capacity"})
                memory.pop(victim)
                if victim in pending:
                    pending.remove(victim)
            seq += 1
            record = {"seq": seq, "kind": kind, "created_s": t, "temperature_c": temp,
                      "time_interval_s": interval, "time_known": known, "acked": False}
            memory[seq] = dict(record)
            committed.append(dict(record))
            pending.append(seq)
            e -= d["write_storage_j"]
            write_j += d["write_storage_j"]
            last_durable = t
            actions.append({"time_s": t, "action": "commit", "seq": seq, "kind": kind})
            return True

        if powered and t >= boot_ready:
            if gateway and sync_at is None:
                if reset_since_sync:
                    interval = [gap_start, t]
                    if store(2, 0, interval, False):
                        gaps.append({"start_s": gap_start, "end_s": t, "basis": "last-durable-observation-to-sync; outage edges unknown"})
                        reset_since_sync = False
                sync_at = t
                actions.append({"time_s": t, "action": "clock-sync"})
            if t >= next_sample:
                next_sample = t + d["sample_period_s"]
                if e - d["sense_storage_j"] - d["write_storage_j"] >= eoff:
                    e -= d["sense_storage_j"]
                    sense_j += d["sense_storage_j"]
                    measured = round(temperature + d["temperature_bias_c"], 2)
                    stamp = t + ((t - sync_at) * d["clock_ppm"] / 1e6 if sync_at is not None else 0)
                    stamp -= d["stamp_age_fault_s"]
                    interval = [stamp, stamp] if sync_at is not None else [gap_start, None]
                    store(0, measured, interval, sync_at is not None)
                    actions.append({"time_s": t, "action": "sample", "temperature_c": measured})
                    event = task["temperature_event"]
                    if event["enabled"] and measured > event["threshold_c"]:
                        high_since = t if high_since is None else high_since
                        if not high_reported and t - high_since >= event["minimum_duration_s"]:
                            high_reported = store(1, measured, interval, sync_at is not None)
                    else:
                        high_since, high_reported = None, False
                else:
                    actions.append({"time_s": t, "action": "sample-blocked"})
            if pending and t >= next_tx:
                vcap = math.sqrt(2 * e / c)
                loaded_v = vcap - d["esr_ohm"] * d["tx_peak_output_a"]
                if loaded_v < d["output_v"] + d["dropout_v"]:
                    turn_off("tx-dropout")
                elif e - d["tx_storage_j"] >= eoff:
                    rec = memory[pending[0]]
                    old = t - rec["created_s"] > task["required_sample_period_s"]
                    raw = frame(rec, d["id"], old)
                    e -= d["tx_storage_j"]
                    tx_j += d["tx_storage_j"]
                    pkt = {"time_s": t, "seq": rec["seq"], "hex": raw.hex(), "gateway": gateway,
                           "loaded_v": loaded_v, "storage_energy_j": d["tx_storage_j"]}
                    packets.append(pkt)
                    valid, reason = _receiver(raw, t, rec, task) if gateway else (False, "no-gateway")
                    duplicate = rec["seq"] in receiver_seen
                    accepted = valid and (not duplicate or not d["receiver_dedup"])
                    ack = False
                    if valid:
                        receiver_seen.add(rec["seq"])
                        if ack_loss:
                            ack_loss -= 1
                        else:
                            ack = True
                    if gateway:
                        arrivals.append({**pkt, "valid": valid, "reason": reason, "duplicate": duplicate,
                                         "accepted": accepted, "ack": ack})
                    if ack:
                        rec["acked"] = True
                        pending.pop(0)
                    next_tx = t + (d["upload_period_s"] if ack else OFFLINE_RETRY_S)
                    actions.append({"time_s": t, "action": "tx", "seq": rec["seq"], "ack": ack})
                else:
                    next_tx = t + 1
        trace.append({"time_s": t, "dt_s": dt, "lux": src["illuminance_lux"], "source_v": vsrc,
                      "source_a": src["power_w"] / vsrc if vsrc else 0, "source_j": source_j,
                      "harvest_j": harvest_j, "conversion_j": source_j - harvest_j,
                      "background_j": background_j, "boot_j": boot_j, "sense_j": sense_j,
                      "write_j": write_j, "tx_j": tx_j, "spill_j": spill_j,
                      "start_j": start_e, "stored_j": e, "voltage_v": math.sqrt(2 * e / c),
                      "powered": int(powered), "gateway": int(gateway), "pending_records": len(pending),
                      "retained_records": len(memory), "temperature_c": temperature})
    return {"model_id": MODEL_ID, "trace": trace, "activity": actions, "records": committed,
            "final_history": list(memory.values()), "packets": packets, "receiver": arrivals,
            "gaps": gaps, "evictions": evictions, "first_boot_s": first_boot}
