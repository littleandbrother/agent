"""Public A/R v2 apparatus: a bounded, participant-authored queue program.

The physical loop is versioned from ar-light-behavior-v1. Only the selected
pending record and the explicit program timing change. This is a nominal
behavioral model, not a deployed MCU binary or qualified hardware model.
Independent readback lives outside this producer in campaign_ar_service.py.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any

from .ar import MODEL_ID as LEGACY_MODEL_ID, _at, _receiver, frame, validate as legacy_validate

MODEL_ID = "ar-service-program-v2"
CANDIDATE_SCHEMA = "bf-ar-candidate-v1"
PROGRAM_SCHEMA = "bf-ar-rank-program-v1"
FIELDS = ("seq", "kind", "age_known", "age_s")
ARITY = {"+": 2, "-": 2, "*": 2, "min": 2, "max": 2, "lt": 2, "le": 2, "eq": 2, "if": 3}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def identity(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def candidate_schema() -> dict:
    """One schema used by the host tool and inspect, with runtime arity checks."""
    return {
        "type": "object", "additionalProperties": False,
        "required": ["schema_version", "device", "program"],
        "properties": {
            "schema_version": {"const": CANDIDATE_SCHEMA},
            "device": {"type": "object", "additionalProperties": False,
                       "required": ["capacitance_f", "off_v", "ready_v"],
                       "properties": {"capacitance_f": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
                                      "off_v": {"type": "number", "minimum": 2.2, "exclusiveMaximum": 3.3},
                                      "ready_v": {"type": "number", "exclusiveMinimum": 2.2, "exclusiveMaximum": 3.3}}},
            "program": {"type": "object", "additionalProperties": False,
                        "required": ["schema_version", "sample_period_s", "ack_spacing_s", "retry_s", "rank"],
                        "properties": {"schema_version": {"const": PROGRAM_SCHEMA},
                                       "sample_period_s": {"type": "integer", "minimum": 1, "maximum": 60},
                                       "ack_spacing_s": {"type": "integer", "minimum": 1, "maximum": 10},
                                       "retry_s": {"type": "integer", "minimum": 1, "maximum": 3600},
                                       "rank": {"$ref": "#/$defs/expression"}}}},
        "$defs": {"expression": {"oneOf": [
            {"type": "object", "additionalProperties": False, "required": ["const"],
             "properties": {"const": {"type": "number", "minimum": -1000000, "maximum": 1000000}}},
            {"type": "object", "additionalProperties": False, "required": ["field"],
             "properties": {"field": {"enum": list(FIELDS)}}},
            {"type": "object", "additionalProperties": False, "required": ["op", "args"],
             "properties": {"op": {"enum": list(ARITY)}, "args": {"type": "array", "minItems": 2,
                             "maxItems": 3, "items": {"$ref": "#/$defs/expression"}}}}
        ]}}
    }


def _keys(value, expected: set[str], name: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("CANDIDATE_KEYS:" + name)


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def validate_candidate(candidate: dict) -> None:
    _keys(candidate, {"schema_version", "device", "program"}, "root")
    if candidate["schema_version"] != CANDIDATE_SCHEMA:
        raise ValueError("CANDIDATE_SCHEMA")
    d, p = candidate["device"], candidate["program"]
    _keys(d, {"capacitance_f", "off_v", "ready_v"}, "device")
    if not all(_number(v) for v in d.values()):
        raise ValueError("CANDIDATE_FINITE_NUMBER")
    if not 0 < d["capacitance_f"] <= 1 or not 2.2 <= d["off_v"] < d["ready_v"] < 3.3:
        raise ValueError("CANDIDATE_DEVICE_DOMAIN")
    _keys(p, {"schema_version", "sample_period_s", "ack_spacing_s", "retry_s", "rank"}, "program")
    if p["schema_version"] != PROGRAM_SCHEMA:
        raise ValueError("PROGRAM_SCHEMA")
    for key, maximum in (("sample_period_s", 60), ("ack_spacing_s", 10), ("retry_s", 3600)):
        if type(p[key]) is not int or not 1 <= p[key] <= maximum:
            raise ValueError("PROGRAM_TIMING:" + key)
    count = 0

    def visit(node, depth=1):
        nonlocal count
        count += 1
        if count > 63 or depth > 8 or not isinstance(node, dict):
            raise ValueError("PROGRAM_COMPLEXITY")
        if set(node) == {"const"} and _number(node["const"]) and abs(node["const"]) <= 1000000:
            return
        if set(node) == {"field"} and isinstance(node["field"], str) and node["field"] in FIELDS:
            return
        if (set(node) == {"op", "args"} and isinstance(node["op"], str) and node["op"] in ARITY
                and isinstance(node["args"], list) and len(node["args"]) == ARITY[node["op"]]):
            for arg in node["args"]:
                visit(arg, depth + 1)
            return
        raise ValueError("PROGRAM_EXPRESSION")

    visit(p["rank"])
    if len(canonical(candidate)) > 16384:
        raise ValueError("CANDIDATE_BYTE_CAP")


def rank_value(node: dict, fields: dict) -> float:
    if "const" in node:
        return node["const"]
    if "field" in node:
        return fields[node["field"]]
    a = [rank_value(n, fields) for n in node["args"]]
    op = node["op"]
    if op == "if":
        value = a[1] if a[0] else a[2]
    else:
        x, y = a
        value = {"+": lambda: x + y, "-": lambda: x - y, "*": lambda: x * y,
                 "min": lambda: min(x, y), "max": lambda: max(x, y),
                 "lt": lambda: int(x < y), "le": lambda: int(x <= y), "eq": lambda: int(x == y)}[op]()
    if not math.isfinite(value):
        raise ValueError("PROGRAM_NONFINITE_RESULT")
    return value


def visible_fields(record: dict, now: float, sync_at: float | None, ppm: float) -> dict:
    known = sync_at is not None and record["time_known"]
    local_now = now + (now - sync_at) * ppm / 1e6 if sync_at is not None else 0
    return {"seq": record["seq"], "kind": record["kind"], "age_known": int(known),
            "age_s": max(0.0, local_now - record["time_interval_s"][0]) if known else 0.0}


def apply_candidate(task: dict, candidate: dict) -> dict:
    validate_candidate(candidate)
    result = copy.deepcopy(task)
    result["model_id"] = MODEL_ID
    result["program"] = copy.deepcopy(candidate["program"])
    result["device"].update(candidate["device"])
    result["device"]["sample_period_s"] = candidate["program"]["sample_period_s"]
    result["device"]["upload_period_s"] = candidate["program"]["ack_spacing_s"]
    return result


def validate(task: dict) -> None:
    if task["model_id"] != MODEL_ID or task["dt_s"] != 1 or not 0 < task["duration_s"] <= 50400:
        raise ValueError("SERVICE_WORLD_DOMAIN")
    p = task["program"]
    validate_candidate({"schema_version": CANDIDATE_SCHEMA,
                        "device": {k: task["device"][k] for k in ("capacitance_f", "off_v", "ready_v")},
                        "program": p})
    if task["device"]["sample_period_s"] != p["sample_period_s"] or task["device"]["upload_period_s"] != p["ack_spacing_s"]:
        raise ValueError("PROGRAM_DEVICE_TIMING_MISMATCH")
    physical = {**task, "model_id": LEGACY_MODEL_ID}
    legacy_validate(physical)


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
                    selected = min(pending, key=lambda s: (rank_value(task["program"]["rank"], visible_fields(memory[s], t, sync_at, d["clock_ppm"])), s))
                    rec = memory[selected]
                    actions.append({"time_s": t, "action": "program-dispatch", "seq": selected,
                                    "fields": visible_fields(rec, t, sync_at, d["clock_ppm"]),
                                    "score": rank_value(task["program"]["rank"], visible_fields(rec, t, sync_at, d["clock_ppm"]))})
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
                        pending.remove(rec["seq"])
                    next_tx = t + (d["upload_period_s"] if ack else task["program"]["retry_s"])
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
    return {"model_id": MODEL_ID, "program_sha256": identity(task["program"]), "trace": trace, "activity": actions, "records": committed,
            "final_history": list(memory.values()), "packets": packets, "receiver": arrivals,
            "gaps": gaps, "evictions": evictions, "first_boot_s": first_boot}
