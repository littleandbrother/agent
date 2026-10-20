"""O service transfer, v1: explicit digital A/R power and powered RMS program.

No file dispatch, provider, native solver or implicit task loading. O0 and any
later waveform are explicit case payloads. The producer never calls the truth
routine. Storage/PMIC/TX are the existing A/R behavioral equations and wire;
new RMS/wake costs are proposed digital values, never physical qualification.
"""
from __future__ import annotations

import copy
from decimal import Decimal
import hashlib
import inspect
import json
import math
from pathlib import Path

from . import ar

MODEL_ID = "o-ar-powered-rms-v1"
CANDIDATE_SCHEMA = "bf-o-candidate-v1"
KINDS = {"start": 3, "stop": 4, "keepalive": 5, "periodic_snapshot": 6}
EPS = 1e-8
MAX_EVENTS = 250000
DEBITS = ("background_j", "boot_j", "wake_j", "sense_j", "write_j", "tx_j", "spill_j")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _engine_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def bind_case(case):
    """Host-only case construction; a participant cannot change a frozen case."""
    out = copy.deepcopy(case)
    out["bindings"] = {"source_payload_sha256": identity({k: v for k, v in out.items() if k != "bindings"})}
    return out


def with_waveform(case, task_id, rms_segments):
    """Parameterizable host ABI; never loads a final-test file or changes service."""
    out = copy.deepcopy(case)
    out["task_id"], out["rms_segments"] = task_id, copy.deepcopy(rms_segments)
    out = bind_case(out)
    validate_case(out)
    return out


def _finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def validate_case(case):
    if case.get("schema_version") != "bf-o-case-v1":
        raise ValueError("O_CASE_SCHEMA")
    if case["bindings"] != {"source_payload_sha256": identity({k: v for k, v in case.items() if k != "bindings"})}:
        raise ValueError("O_SOURCE_BINDING")
    if hashlib.sha256(Path(ar.__file__).read_bytes()).hexdigest() != case["provenance"]["ar_module_sha256"]:
        raise ValueError("O_AR_MODEL_BINDING")
    task = case["ar_task"]
    ar.validate(task)
    if not 0 < case["duration_s"] <= 21600 or task["duration_s"] != case["duration_s"]:
        raise ValueError("O_HORIZON")
    if not 0 < case["photovoltaic_area_cm2"] <= 25 or task["device"]["rated_voltage_v"] > 5.5:
        raise ValueError("O_HARDWARE_LIMIT")
    s = case["service"]
    required = {"start_threshold_g": .05, "stop_threshold_g": .01, "start_continuous_s": 3,
                "stop_continuous_s": 60, "event_delivery_s": 10,
                "keepalive_interval_s": 120, "event_time_error_s": 1}
    if any(s.get(k) != value for k, value in required.items()):
        raise ValueError("O_ORIGINAL_SERVICE_CHANGED")
    t = 0
    if not 1 <= len(case["rms_segments"]) <= 10000:
        raise ValueError("O_WAVEFORM_SIZE")
    for row in case["rms_segments"]:
        if (set(row) != {"start_s", "end_s", "rms_g"} or not all(_finite(v) for v in row.values())
                or row["start_s"] != t or row["end_s"] <= t or row["rms_g"] < 0):
            raise ValueError("O_RMS_WAVEFORM")
        t = row["end_s"]
    if t != case["duration_s"]:
        raise ValueError("O_WAVEFORM_HORIZON")
    comp = case["components"]
    for key in ("standby_power_w", "wake_storage_j", "sense_storage_j", "write_storage_j"):
        if not _finite(comp[key]) or comp[key] < 0:
            raise ValueError("O_COMPONENT_DOMAIN:" + key)
    if type(comp["cache_capacity_records"]) is not int or not 1 <= comp["cache_capacity_records"] <= 2048:
        raise ValueError("O_CACHE_DOMAIN")
    if not _finite(case["link_delay_s"]) or case["link_delay_s"] < 0:
        raise ValueError("O_LINK_DOMAIN")
    canonical(case)


def candidate_schema(case):
    space = case["design_space"]
    properties = {"schema_version": {"const": CANDIDATE_SCHEMA}}
    for key in ("capacitance_f", "sample_period_s", "threshold_on_g", "threshold_off_g", "retry_s", "tx_backoff_s"):
        properties[key] = {"type": "number", "minimum": space[key][0], "maximum": space[key][1]}
    for key in ("cache", "program"):
        properties[key] = {"enum": space[key]}
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


def validate_candidate(case, candidate):
    schema = candidate_schema(case)
    if not isinstance(candidate, dict) or set(candidate) != set(schema["required"]):
        raise ValueError("O_CANDIDATE_KEYS_NO_EVENT_TABLE")
    if candidate["schema_version"] != CANDIDATE_SCHEMA:
        raise ValueError("O_CANDIDATE_SCHEMA")
    for key, spec in schema["properties"].items():
        if spec.get("type") == "number" and (not _finite(candidate[key]) or not spec["minimum"] <= candidate[key] <= spec["maximum"]):
            raise ValueError("O_CANDIDATE_DOMAIN:" + key)
        if "enum" in spec and candidate[key] not in spec["enum"]:
            raise ValueError("O_CANDIDATE_ENUM:" + key)
    if not .25 <= candidate["sample_period_s"] <= 120 or not .001 <= candidate["retry_s"]:
        raise ValueError("O_PROGRAM_TIME_DOMAIN")
    if not 0 < candidate["threshold_off_g"] < candidate["threshold_on_g"]:
        raise ValueError("O_THRESHOLD_ORDER")
    physical = copy.deepcopy(case["ar_task"])
    physical["device"]["capacitance_f"] = candidate["capacitance_f"]
    ar.validate(physical)


def _control(case, program, period):
    c = {"schema_version": CANDIDATE_SCHEMA, "capacitance_f": case["ar_task"]["device"]["capacitance_f"],
         "sample_period_s": period, "threshold_on_g": .05, "threshold_off_g": .01,
         "retry_s": 1, "tx_backoff_s": 0, "cache": "nvm", "program": program}
    validate_candidate(case, c)
    return c


def fixed_periodic(case):
    return {"candidate": _control(case, "periodic_snapshot", 60),
            "method_text": "Frozen A-style periodic control: powered 60 s RMS snapshots and immediate FIFO upload; no start/stop confirmation state machine.",
            "hardware": "Same case-bound A/R hardware and RMS/wake catalog as candidate and rich-state arms."}


def rich_state(case):
    return {"candidate": _control(case, "confirmed_events", 1),
            "method_text": "Frozen rich event control: powered 1 s RMS observations, continuous held observations for 3 s start/60 s stop, 120 s active keepalive, NVM pending records and FIFO retry.",
            "hardware": "Same case-bound A/R hardware and RMS/wake catalog as candidate and periodic arms."}


def evaluate_candidate(case, candidate):
    """Execute a legal D from supplied source, energy and sampled program state.

    No expected-event table is read. Regular polling is computed internally but
    observations and energy are run-length/piecewise compressed. Every sampling
    impulse, boot, write and TX is charged. NVM restores committed state/queue;
    continuous-confirmation timers never bridge an unpowered/failed sample gap.
    """
    validate_case(case)
    validate_candidate(case, candidate)
    task, p, comp = case["ar_task"], candidate, case["components"]
    d = copy.deepcopy(task["device"])
    d["capacitance_f"] = p["capacitance_f"]
    c, horizon = d["capacitance_f"], case["duration_s"]
    e = c * d["cap_initial_voltage_v"] ** 2 / 2
    emax, eon, eoff = (c * d[k] ** 2 / 2 for k in ("cap_voltage_max_v", "ready_v", "off_v"))
    costs = {"boot_j": d["boot_storage_j"], "wake_j": comp["wake_storage_j"],
             "sense_j": comp["sense_storage_j"], "write_j": comp["write_storage_j"], "tx_j": d["tx_storage_j"]}
    t, source_index = 0., 0
    powered, ready, sync_at = False, math.inf, None
    next_sample = next_tx = next_keepalive = math.inf
    active, durable_active, seq = False, False, 0
    high_since = low_since = last_rms = last_sample = None
    ledger, activity, sample_runs, records, pending, packets, receiver = [], [], [], [], [], [], []
    seen, ack_left, iterations = set(), d["ack_drop_first_n"], 0

    def energy_row(start, end, before, after, **values):
        row = {"start_s": start, "end_s": end, "source_index": source_index, "powered": powered,
               "start_j": before, "stored_j": after, "minimum_j": min(before, after),
               "voltage_v": math.sqrt(max(0., 2 * after / c)), "source_j": 0., "harvest_j": 0.,
               "background_j": 0., "spill_j": 0., **{k: 0. for k in costs},
               **{k.replace("_j", "_count"): 0 for k in costs}}
        row.update(values)
        if (ledger and ledger[-1]["end_s"] == start and ledger[-1]["source_index"] == source_index
                and ledger[-1]["powered"] == powered):
            old = ledger[-1]
            old.update(end_s=end, stored_j=after, voltage_v=row["voltage_v"], minimum_j=min(old["minimum_j"], row["minimum_j"]))
            for key in ("source_j", "harvest_j", *DEBITS, *[k.replace("_j", "_count") for k in costs]):
                old[key] += row[key]
        else:
            ledger.append(row)

    def pay(key):
        nonlocal e
        amount = costs[key]
        if e - amount < eoff - EPS:
            return False
        before, e = e, e - amount
        energy_row(t, t, before, e, **{key: amount, key.replace("_j", "_count"): 1})
        return True

    def off(reason):
        nonlocal powered, active, durable_active, seq, high_since, low_since, last_rms, last_sample
        nonlocal next_sample, next_tx, next_keepalive, sync_at
        activity.append({"time_s": t, "action": "brownout", "reason": reason,
                         "pending_lost": len(pending) if p["cache"] == "volatile" else 0})
        powered = False
        high_since = low_since = last_rms = last_sample = None
        next_sample = next_tx = next_keepalive = math.inf
        sync_at = None
        if p["cache"] == "volatile":
            pending.clear()
            active, durable_active, seq = False, False, 0
        else:
            active = durable_active

    def commit(kind, state):
        nonlocal seq, next_tx, durable_active
        activity.append({"time_s": t, "action": "detected", "kind": kind, "state": state})
        if len(pending) >= comp["cache_capacity_records"] or not pay("write_j"):
            activity.append({"time_s": t, "action": "write-blocked", "kind": kind})
            return
        seq += 1
        stamp = t + (t - sync_at) * d["clock_ppm"] / 1e6 if sync_at is not None else None
        rec = {"seq": seq, "kind": kind, "state": int(state), "observed_s": t,
               "stamp_s": stamp, "time_known": stamp is not None, "last_sample_s": last_sample}
        records.append(rec)
        pending.append(rec)
        durable_active = bool(active)
        activity.append({"time_s": t, "action": "commit", "seq": seq, "kind": kind})
        if not math.isfinite(next_tx):
            next_tx = t + p["tx_backoff_s"]

    status = "COMPLETE"
    while t < horizon - EPS:
        iterations += 1
        if iterations > MAX_EVENTS:
            status = "RESOURCE_CAP_UNKNOWN"
            break
        while source_index + 1 < len(task["source_segments"]) and task["source_segments"][source_index]["end_s"] <= t + EPS:
            source_index += 1
        src = task["source_segments"][source_index]
        permitted = src["voc_v"] * src["mpp_ratio"] >= d["cold_start_voltage_v"] and src["power_w"] >= d["cold_start_power_w"]
        hp = src["power_w"] * d["harvest_efficiency"] if permitted else 0.
        bg = d["sleep_power_w"] + comp["standby_power_w"] if powered else d["off_power_w"]
        net = hp - bg
        threshold = max(eon, eoff + d["boot_storage_j"])
        if powered and net < 0 and e <= eoff + EPS:
            off("background-threshold")
            continue
        if not powered and e >= threshold - EPS:
            powered = True
            if not pay("boot_j"):
                powered = False
                raise ValueError("O_BOOT_ENERGY_INCONSISTENT")
            active = durable_active if p["cache"] == "nvm" else False
            ready = next_sample = t + d["boot_delay_s"]
            next_tx = ready + p["tx_backoff_s"] if pending else math.inf
            next_keepalive = ready + 120 if active else math.inf
            activity.append({"time_s": t, "action": "boot", "ready_s": ready, "restored_active": active})
            continue
        if powered and t >= ready - EPS:
            gateway = any(a <= t < b for a, b in task["gateway_windows"])
            if sync_at is None and gateway:
                sync_at = t
                activity.append({"time_s": t, "action": "clock-sync", "basis": "Same ideal A/R digital gateway synchronization"})
            if t >= next_sample - EPS:
                next_sample = t + p["sample_period_s"]
                woke = pay("wake_j")
                sampled = woke and pay("sense_j")
                if not sampled:
                    high_since = low_since = last_rms = last_sample = None
                    activity.append({"time_s": t, "action": "sample-blocked"})
                else:
                    measured = next(row["rms_g"] for row in case["rms_segments"] if row["start_s"] <= t < row["end_s"])
                    if (sample_runs and sample_runs[-1]["rms_g"] == measured
                            and abs(sample_runs[-1]["last_s"] + p["sample_period_s"] - t) < EPS):
                        sample_runs[-1]["last_s"], sample_runs[-1]["count"] = t, sample_runs[-1]["count"] + 1
                    else:
                        sample_runs.append({"first_s": t, "last_s": t, "period_s": p["sample_period_s"], "count": 1, "rms_g": measured})
                    # Confirm the held interval BEFORE applying this new sample.
                    # Exact 3/60 s boundaries therefore do not lose a transition.
                    if p["program"] == "confirmed_events":
                        if not active and high_since is not None and t - high_since >= 3 - EPS:
                            active, high_since, next_keepalive = True, None, t + 120
                            commit("start", True)
                        if active and low_since is not None and t - low_since >= 60 - EPS:
                            active, low_since, next_keepalive = False, None, math.inf
                            commit("stop", False)
                        if active:
                            low_since = (t if low_since is None else low_since) if measured < p["threshold_off_g"] else None
                            high_since = None
                        else:
                            high_since = (t if high_since is None else high_since) if measured > p["threshold_on_g"] else None
                            low_since = None
                        last_rms, last_sample = measured, t
                        if active and t >= next_keepalive - EPS:
                            commit("keepalive", True)
                            next_keepalive += 120
                    else:
                        last_rms, last_sample = measured, t
                        commit("periodic_snapshot", measured > p["threshold_on_g"])
            if pending and t >= next_tx - EPS:
                loaded_v = math.sqrt(2 * e / c) - d["esr_ohm"] * d["tx_peak_output_a"]
                if loaded_v < d["output_v"] + d["dropout_v"]:
                    off("tx-dropout")
                    continue
                if pay("tx_j"):
                    rec = pending[0]
                    # Exact original AR envelope; O kind/state interpretation is versioned.
                    wire_record = {"seq": rec["seq"], "kind": KINDS[rec["kind"]], "temperature_c": rec["state"],
                                   "time_interval_s": [rec["stamp_s"] or 0., rec["stamp_s"] or 0.], "time_known": rec["time_known"]}
                    raw = ar.frame(wire_record, d["id"])
                    pkt = {"time_s": t, "receive_s": t + case["link_delay_s"], "seq": rec["seq"],
                           "hex": raw.hex(), "loaded_v": loaded_v, "storage_energy_j": d["tx_storage_j"]}
                    packets.append(pkt)
                    valid, reason = ar._receiver(raw, pkt["receive_s"], wire_record, task) if gateway else (False, "no-gateway")
                    duplicate = rec["seq"] in seen
                    accepted = valid and not duplicate
                    ack = valid and ack_left == 0
                    if valid:
                        seen.add(rec["seq"])
                        if ack_left:
                            ack_left -= 1
                    if gateway:
                        receiver.append({**pkt, "valid": valid, "reason": reason, "accepted": accepted, "duplicate": duplicate, "ack": ack})
                    activity.append({"time_s": t, "action": "tx", "seq": rec["seq"], "ack": ack})
                    if ack:
                        pending.pop(0)
                    next_tx = t + (d["upload_period_s"] if ack else p["retry_s"]) if pending else math.inf
                else:
                    next_tx = t + p["retry_s"]
                    activity.append({"time_s": t, "action": "tx-blocked"})
        # Analytic source/background integration between program/power events.
        bg = d["sleep_power_w"] + comp["standby_power_w"] if powered else d["off_power_w"]
        net = hp - bg
        crossing = math.inf
        if powered and net < 0:
            crossing = t + max(0., (e - eoff) / -net)
        elif not powered and net > 0:
            crossing = t + max(0., (threshold - e) / net)
        target = min(horizon, src["end_s"], crossing, next_sample if powered else math.inf, next_tx if powered else math.inf)
        if target <= t + 1e-10:
            raise ValueError("O_NONADVANCING_SCHEDULER")
        dt, before = target - t, e
        source_j, harvest_j = src["power_w"] * dt, hp * dt
        background_j = min(bg * dt, e + harvest_j)
        unclipped = e + harvest_j - background_j
        spill_j = max(0., unclipped - emax)
        e = max(0., unclipped - spill_j)
        energy_row(t, target, before, e, source_j=source_j, harvest_j=harvest_j,
                   background_j=background_j, spill_j=spill_j)
        t = target
    response = {"schema_version": "bf-o-response-v1", "model_id": MODEL_ID, "engine_sha256": _engine_hash(),
                "case_sha256": identity(case), "source_payload_sha256": case["bindings"]["source_payload_sha256"],
                "candidate": copy.deepcopy(candidate), "candidate_sha256": identity(candidate),
                "status": status, "energy": ledger, "activity": activity, "sample_runs": sample_runs,
                "records": records, "state": {"active": active, "durable_active": durable_active, "pending": pending,
                                             "powered": powered, "stored_j": e, "end_s": t},
                "packets": packets, "receiver": receiver, "internal_scheduler_events": iterations,
                "physical_qualification": "UNKNOWN", "source_scope": case["provenance"]["qualification"]}
    response["execution_key"] = identity({"case": identity(case), "candidate": identity(candidate), "engine": _engine_hash()})
    response["response_sha256"] = identity(response)
    return response


def reference_events(case):
    """Host evaluator only: continuous external RMS, independent of program/state."""
    events, active, high, low = [], False, None, None
    for segment in case["rms_segments"]:
        a, b, value = segment["start_s"], segment["end_s"], segment["rms_g"]
        if value > .05:
            low = None
            if not active:
                high = a if high is None else high
                if high + 3 <= b + EPS:
                    events.append({"kind": "start", "time_s": high + 3, "state": 1})
                    active, high = True, None
        elif value < .01:
            high = None
            if active:
                low = a if low is None else low
                if low + 60 <= b + EPS:
                    events.append({"kind": "stop", "time_s": low + 60, "state": 0})
                    active, low = False, None
        else:
            high = low = None
    return events


def _crc(raw):
    value = 65535
    for byte in raw:
        value ^= byte << 8
        for _ in range(8):
            value = ((value << 1) ^ (0x1021 if value & 0x8000 else 0)) & 65535
    return value


def _decode(raw_hex):
    try:
        raw = bytes.fromhex(raw_hex)
    except (ValueError, TypeError):
        return None
    if len(raw) != 22 or _crc(raw[:-2]) != int.from_bytes(raw[-2:], "big"):
        return None
    return {"id": int.from_bytes(raw[:4], "big"), "seq": int.from_bytes(raw[4:8], "big"),
            "stamp_s": int.from_bytes(raw[8:12], "big", signed=True) / 1000,
            "stamp_hi_s": int.from_bytes(raw[12:16], "big", signed=True) / 1000,
            "state": int.from_bytes(raw[16:18], "big", signed=True) / 100,
            "kind": raw[18], "known": bool(raw[19] & 1), "flags": raw[19]}


def _energy_check(case, response):
    """Decimal replay of compressed ledger, independent input integrals/costs."""
    D = lambda x: Decimal(str(x))
    d, comp = case["ar_task"]["device"], case["components"]
    c = response["candidate"]["capacitance_f"]
    previous = D(c) * D(d["cap_initial_voltage_v"]) ** 2 / 2
    maximum = D(c) * D(d["cap_voltage_max_v"]) ** 2 / 2
    costs = {"boot": d["boot_storage_j"], "wake": comp["wake_storage_j"], "sense": comp["sense_storage_j"],
             "write": comp["write_storage_j"], "tx": d["tx_storage_j"]}
    totals, errors, cursor = CounterValues(costs), [], 0.
    for i, row in enumerate(response["energy"]):
        a, b = row["start_s"], row["end_s"]
        if abs(a - cursor) > EPS or b < a or b > case["duration_s"] + EPS:
            errors.append([i, "ledger-time-coverage"])
        src = case["ar_task"]["source_segments"][row["source_index"]]
        if a < src["start_s"] - EPS or b > src["end_s"] + EPS:
            errors.append([i, "source-segment"])
        dt = D(b) - D(a)
        source_j = dt * D(src["power_w"])
        permitted = src["voc_v"] * src["mpp_ratio"] >= d["cold_start_voltage_v"] and src["power_w"] >= d["cold_start_power_w"]
        harvest_j = source_j * D(d["harvest_efficiency"]) if permitted else D(0)
        background = D(d["sleep_power_w"]) + D(comp["standby_power_w"]) if row["powered"] else D(d["off_power_w"])
        background = background * dt if row["powered"] else min(background * dt, previous + harvest_j)
        if any(abs(D(row[key]) - expected) > D("1e-8") for key, expected in (("source_j", source_j), ("harvest_j", harvest_j), ("background_j", background))):
            errors.append([i, "independent-source-background"])
        for name, cost in costs.items():
            count = row[name + "_count"]
            if type(count) is not int or count < 0 or abs(D(row[name + "_j"]) - D(cost) * count) > D("1e-8"):
                errors.append([i, "impulse-cost:" + name])
            totals[name] += count
        if not row["powered"] and any(row[name + "_count"] for name in costs):
            errors.append([i, "unpowered-execution"])
        end = D(row["stored_j"])
        predicted = previous + D(row["harvest_j"]) - sum((D(row[k]) for k in DEBITS), D(0))
        if (abs(previous - D(row["start_j"])) > D("1e-8") or abs(predicted - end) > D("1e-8")
                or not -1e-8 <= float(end) <= float(maximum) + 1e-8
                or row["minimum_j"] < -EPS or row["minimum_j"] > min(row["start_j"], row["stored_j"]) + EPS
                or (row["powered"] and row["minimum_j"] < c * d["off_v"] ** 2 / 2 - EPS)
                or any(not _finite(row[k]) or row[k] < -EPS for k in ("source_j", "harvest_j", *DEBITS))):
            errors.append([i, "energy-balance-or-range"])
        if abs(math.sqrt(max(0., 2 * float(end) / c)) - row["voltage_v"]) > EPS:
            errors.append([i, "capacitor-voltage"])
        previous, cursor = end, b
    if abs(cursor - case["duration_s"]) > EPS:
        errors.append([None, "incomplete-energy-horizon"])
    counts = {"sense": sum(r["count"] for r in response["sample_runs"]), "write": len(response["records"]),
              "tx": len(response["packets"]), "boot": sum(a["action"] == "boot" for a in response["activity"])}
    for key, count in counts.items():
        if count != totals[key]:
            errors.append([None, "activity-count:" + key])
    if totals["wake"] < totals["sense"]:
        errors.append([None, "sense-without-powered-wake"])
    previous_sample = -math.inf
    for i, run in enumerate(response["sample_runs"]):
        first, last, period, count = (run[k] for k in ("first_s", "last_s", "period_s", "count"))
        if (type(count) is not int or count < 1 or not all(_finite(run[k]) for k in ("first_s", "last_s", "period_s", "rms_g"))
                or period != response["candidate"]["sample_period_s"] or first < 0 or last >= case["duration_s"]
                or first <= previous_sample or abs(last - first - period * (count - 1)) > EPS):
            errors.append([i, "sample-run-shape"])
            continue
        # Check a compressed sampling grid against external RMS and powered
        # intervals without expanding a six-hour point-by-point trace.
        def intersects(a, b):
            index = max(0, math.ceil((a - first - EPS) / period))
            point = first + index * period
            return index < count and point < b - EPS
        for segment in case["rms_segments"]:
            if intersects(segment["start_s"], segment["end_s"]) and run["rms_g"] != segment["rms_g"]:
                errors.append([i, "sample-source-value"])
        for row in response["energy"]:
            # A zero-duration boot row is powered; interval interiors exclude
            # an adjacent ready/UVLO boundary already represented by the ledger.
            if not row["powered"] and intersects(row["start_s"] + 2 * EPS, row["end_s"] - EPS):
                errors.append([i, "sample-while-unpowered"])
        previous_sample = last
    if abs(response["state"]["stored_j"] - float(previous)) > EPS or abs(response["state"]["end_s"] - cursor) > EPS:
        errors.append([None, "final-state-ledger-binding"])
    return {"verdict": "FAIL" if errors else "PASS", "errors": errors[:50], "impulse_counts": totals,
            "source_integral_j": sum((s["end_s"] - s["start_s"]) * s["power_w"] for s in case["ar_task"]["source_segments"]),
            "final_storage_j": float(previous), "ledger_rows": len(response["energy"])}


def CounterValues(costs):
    return {name: 0 for name in costs}


def evaluate_service(case, response):
    """Independent receiver/energy/each-event service facts; no producer rerun.

    PASS is nominal digital service only; physical_qualification remains UNKNOWN.
    Definite missed/false/late events FAIL even if some time evidence is UNKNOWN.
    """
    def result(status, reasons, **fields):
        return {"schema_version": "bf-o-service-v1", "complete_service": status, "verdict": status,
                "reasons": reasons, "physical_qualification": "UNKNOWN", **fields}
    try:
        validate_case(case)
    except (KeyError, ValueError, TypeError) as error:
        return result("UNKNOWN", ["SOURCE_OR_MODEL_UNAVAILABLE:" + str(error)])
    try:
        validate_candidate(case, response["candidate"])
        if (response["case_sha256"] != identity(case) or response["source_payload_sha256"] != case["bindings"]["source_payload_sha256"]
                or response["engine_sha256"] != _engine_hash() or response["candidate_sha256"] != identity(response["candidate"])
                or response["model_id"] != MODEL_ID):
            return result("FAIL", ["RESPONSE_SOURCE_OR_DESIGN_BINDING"])
        if response["response_sha256"] != identity({k: v for k, v in response.items() if k != "response_sha256"}):
            return result("FAIL", ["RESPONSE_CONTENT_BINDING"])
        if response["status"] != "COMPLETE":
            return result("UNKNOWN", ["PRODUCER_INCOMPLETE:" + response["status"]])
        energy = _energy_check(case, response)
        errors = ["ENERGY_AUDIT"] if energy["verdict"] == "FAIL" else []
        unknown = []
        records = {r["seq"]: r for r in response["records"]}
        if len(records) != len(response["records"]) or any(b["seq"] != a["seq"] + 1 for a, b in zip(response["records"], response["records"][1:])):
            errors.append("SEQUENCE_REUSE_OR_GAP")
        arrivals, seen, accepted = [], set(), []
        d = case["ar_task"]["device"]
        ack_left, previous_tx = d["ack_drop_first_n"], -math.inf
        for packet in response["packets"]:
            dec, t = _decode(packet["hex"]), packet["time_s"]
            rec = records.get(packet["seq"])
            gateway = any(a <= t < b for a, b in case["ar_task"]["gateway_windows"])
            valid = bool(dec and rec and dec["id"] == d["id"] and dec["seq"] == rec["seq"]
                         and dec["kind"] == KINDS[rec["kind"]] and dec["state"] == rec["state"]
                         and dec["known"] == rec["time_known"] and dec["flags"] in (0, 1)
                         and abs(dec["stamp_s"] - (rec["stamp_s"] or 0)) <= .00051
                         and abs(dec["stamp_hi_s"] - dec["stamp_s"]) <= EPS)
            if t < previous_tx - EPS or not 0 <= t <= case["duration_s"] or abs(packet["receive_s"] - (t + case["link_delay_s"])) > EPS:
                errors.append("PACKET_ORDER_OR_RECEIVE_TIME")
            if rec and (t < rec["observed_s"] - EPS or packet["loaded_v"] < d["output_v"] + d["dropout_v"] - EPS):
                errors.append("CAUSALITY_OR_TX_VOLTAGE")
            if rec and ((rec["kind"] in ("start", "keepalive") and rec["state"] != 1)
                        or (rec["kind"] == "stop" and rec["state"] != 0)):
                errors.append("WRONG_MESSAGE_STATE")
            previous_tx = t
            if valid and dec["known"] and packet["receive_s"] - dec["stamp_s"] > case["ar_task"]["required_sample_period_s"]:
                valid = False
            duplicate = packet["seq"] in seen
            accept = valid and gateway and not duplicate
            ack = valid and gateway and ack_left == 0
            if valid and gateway:
                seen.add(packet["seq"])
                if ack_left:
                    ack_left -= 1
            if gateway:
                arrivals.append((packet["time_s"], packet["hex"], valid, accept, duplicate, ack, packet["receive_s"]))
                if not valid:
                    errors.append("INDEPENDENT_CRC_ID_SEQUENCE_OR_PAYLOAD")
            if accept:
                accepted.append({**rec, "receive_s": packet["receive_s"], "decoded": dec})
                if not dec["known"]:
                    unknown.append("MESSAGE_TIME_BASIS_UNKNOWN")
        actual = [(r["time_s"], r["hex"], r["valid"], r["accepted"], r["duplicate"], r["ack"], r["receive_s"]) for r in response["receiver"]]
        if actual != arrivals:
            errors.append("INDEPENDENT_RECEIVER_DISAGREEMENT")
        expected, per_event, used = reference_events(case), [], set()
        for event in expected:
            options = [r for r in accepted if r["kind"] == event["kind"] and r["seq"] not in used
                       and abs(r["observed_s"] - event["time_s"]) <= 1 + EPS]
            match = min(options, key=lambda r: r["observed_s"], default=None)
            reasons = []
            if match is None:
                reasons.append("MISSING_EVENT")
            else:
                used.add(match["seq"])
                if not match["decoded"]["known"]:
                    reasons.append("EVENT_TIME_UNKNOWN")
                    unknown.append("EVENT_TIME_UNKNOWN")
                elif abs(match["decoded"]["stamp_s"] - event["time_s"]) > 1 + EPS:
                    reasons.append("WRONG_EVENT_TIME")
                if match["receive_s"] > event["time_s"] + 10 + EPS or match["receive_s"] < event["time_s"] - 1 - EPS:
                    reasons.append("LATE_OR_NONCAUSAL_RECEIVE")
            definite = [r for r in reasons if r != "EVENT_TIME_UNKNOWN"]
            if definite:
                errors.extend(definite)
            per_event.append({**event, "matched_seq": match["seq"] if match else None,
                              "receive_s": match["receive_s"] if match else None,
                              "verdict": "FAIL" if definite else "UNKNOWN" if reasons else "PASS", "reasons": reasons})
        false_events = [r["seq"] for r in accepted if r["kind"] in ("start", "stop") and r["seq"] not in used]
        if false_events:
            errors.append("FALSE_OR_MISTIMED_EVENT")
        intervals, beginning = [], None
        for event in expected:
            if event["kind"] == "start":
                beginning = event["time_s"]
            else:
                intervals.append((beginning, event["time_s"]))
                beginning = None
        if beginning is not None:
            intervals.append((beginning, case["duration_s"]))
        heartbeat_gaps, false_keepalive = [], []
        for rec in accepted:
            if rec["kind"] == "keepalive" and not any(a - 1 <= rec["observed_s"] < b + EPS for a, b in intervals):
                false_keepalive.append(rec["seq"])
        if false_keepalive:
            errors.append("FALSE_KEEPALIVE_WHILE_IDLE")
        for a, b in intervals:
            # End-point is the confirmed stop, not the final reported device state.
            points = [a, *sorted(r["receive_s"] for r in accepted if r["kind"] in ("start", "keepalive")
                                and a - EPS <= r["observed_s"] < b and r["receive_s"] <= b), b]
            heartbeat_gaps.extend([{"start_s": x, "end_s": y, "gap_s": y - x} for x, y in zip(points, points[1:]) if y - x > 120 + EPS])
        if heartbeat_gaps:
            errors.append("MISSING_KEEPALIVE")
        verdict = "FAIL" if errors else "UNKNOWN" if unknown else "PASS"
        return result(verdict, sorted(set(errors + unknown)), energy=energy, per_event=per_event,
                      expected_event_count=len(expected), matched_event_count=sum(e["matched_seq"] is not None for e in per_event),
                      false_event_sequences=false_events, false_keepalive_sequences=false_keepalive,
                      keepalive_gaps=heartbeat_gaps, accepted_packets=len(accepted),
                      case_sha256=identity(case), response_sha256=response["response_sha256"])
    except (KeyError, ValueError, TypeError, IndexError, OverflowError) as error:
        return result("FAIL", ["MALFORMED_RESPONSE:" + str(error)])


def _units(payload, pointer=""):
    out = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            out.update(_units(value, pointer + "/" + str(key).replace("~", "~0").replace("/", "~1")))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            out.update(_units(value, pointer + "/" + str(index)))
    else:
        parts = pointer.split("/")
        suffix = next((part for part in reversed(parts) if part and not part.isdigit()), "")
        unit = next((unit for ending, unit in (("_w", "W"), ("_storage_j", "J"), ("_s", "s"), ("_j", "J"), ("_v", "V"), ("_f", "F"), ("_a", "A"), ("_g", "g"), ("_ohm", "ohm"), ("_cm2", "cm2"), ("_lux", "lux"), ("_ppm", "ppm"), ("_k", "K"), ("_c", "degC")) if suffix.endswith(ending)), "1")
        if "gateway_windows" in parts:
            unit = "s"
        if "temperature_segments" in parts and parts[-1].isdigit():
            unit = "degC" if parts[-1] == "2" else "s"
        out[pointer] = unit
    return out


def public_view(case, response=None, source=None):
    """Public facts only; no reference truth list, final verdict or next-step advice.

    A source selection returns the complete payload/hash/units for that record.
    Later final-test payload routing and G/H selection isolation are S0-owned.
    """
    validate_case(case)
    payloads = {
        "task": copy.deepcopy(case), "ar_hardware": copy.deepcopy(case["ar_task"]["device"]),
        "photovoltaic_source": {"segments": copy.deepcopy(case["ar_task"]["source_segments"]), "light_metadata": copy.deepcopy(case["light_metadata"]),
                                "area_cm2": case["photovoltaic_area_cm2"], "source_calibration": case["ar_task"]["source_calibration"]},
        "rms_waveform": {"segments": copy.deepcopy(case["rms_segments"]), "units": "g RMS"},
        "wake_sample_cache": copy.deepcopy(case["components"]),
        "model_law": {"model_id": MODEL_ID, "engine_sha256": _engine_hash(), "producer_python": inspect.getsource(evaluate_candidate),
                      "producer_dependencies_python": "\n\n".join(inspect.getsource(fn) for fn in (canonical, identity, _engine_hash, _finite, validate_case, candidate_schema, validate_candidate)),
                      "producer_globals": {"MODEL_ID": MODEL_ID, "CANDIDATE_SCHEMA": CANDIDATE_SCHEMA, "KINDS": KINDS, "EPS": EPS, "MAX_EVENTS": MAX_EVENTS, "DEBITS": list(DEBITS)},
                      "producer_imports": ["copy", "hashlib", "json", "math", "pathlib.Path", "bfworld.agentlab.campaign20261019.ar"],
                      "ar_python": Path(ar.__file__).read_text(), "scope": "Powered sample/hold observation, independent of host continuous truth; ideal digital AR chain only"},
    }
    sources = {key: {"source_id": key, "payload": value, "sha256": identity(value), "field_units": _units(value)} for key, value in payloads.items()}
    if source is not None:
        if source not in sources:
            raise ValueError("O_SOURCE_ID")
        return sources[source]
    out = {"schema_version": "bf-o-public-v1", "case_sha256": identity(case), "task": payloads["task"],
           "candidate_schema": candidate_schema(case), "sources": [{k: value[k] for k in ("source_id", "sha256")} for value in sources.values()],
           "physical_qualification": "UNKNOWN"}
    if response is not None:
        if response["case_sha256"] != identity(case):
            raise ValueError("O_PUBLIC_RESPONSE_BINDING")
        out["response"] = {key: copy.deepcopy(response[key]) for key in ("model_id", "case_sha256", "candidate_sha256", "response_sha256", "status", "energy", "activity", "sample_runs", "records", "state", "packets", "receiver")}
    return out
