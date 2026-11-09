"""Host-only door truth and receiver; never imported by participant methods."""
from binascii import crc_hqx
from .executor import identity


def event_truth(task):
    """Exact piecewise-linear angle crossings plus external stable dwell.

    This implementation reads only prescribed motion and the frozen service.
    It does not read contact bounce, program events, device power or packets.
    """
    service = task["service"]
    boundaries = {0.0, task["duration_s"]}
    for s in task["motion"]:
        boundaries.update((s["start_s"], s["end_s"]))
        for threshold in (service["open_deg"], service["closed_deg"]):
            if min(s["start_deg"], s["end_deg"]) < threshold < max(s["start_deg"], s["end_deg"]):
                boundaries.add(s["start_s"] + (threshold - s["start_deg"]) / (s["end_deg"] - s["start_deg"]) * (s["end_s"] - s["start_s"]))
    intervals = sorted(boundaries)
    events, state, pending, since = [], task["initial"]["logical_state"], None, None
    for left, right in zip(intervals, intervals[1:]):
        midpoint = (left + right) / 2
        angle = task["initial"]["angle_deg"]
        for s in task["motion"]:
            if midpoint < s["start_s"]:
                break
            if midpoint < s["end_s"]:
                angle = s["start_deg"] + (s["end_deg"] - s["start_deg"]) * (midpoint - s["start_s"]) / (s["end_s"] - s["start_s"])
                break
            angle = s["end_deg"]
        target = 1 if angle >= service["open_deg"] else (0 if angle <= service["closed_deg"] else None)
        if target is None or target == state:
            pending = since = None
            continue
        if pending != target:
            pending, since = target, left
        at = since + service["stable_s"]
        if at <= right + 1e-9:
            events.append({"event_id": len(events) + 1, "direction": target, "time_s": at})
            state, pending, since = target, None, None
    return events


def decode(hex_frame):
    try:
        raw = bytes.fromhex(hex_frame)
    except (TypeError, ValueError):
        return None
    if len(raw) != 7 or raw[4] not in (0, 1) or crc_hqx(raw[:-2], 65535) != int.from_bytes(raw[-2:], "big"):
        return None
    return {"seq": int.from_bytes(raw[:4], "big"), "direction": raw[4]}


def receive_frames(task, packets):
    """Same CRC, gateway and sequence deduplication for every semantic version."""
    failures = []
    seen, accepted, duplicate_frames, invalid_frames = {}, [], [], []
    for packet in packets:
        item = decode(packet.get("hex"))
        if item is None:
            invalid_frames.append(packet)
            continue
        if not any(a <= packet["time_s"] <= b for a, b in task["gateway_windows"]):
            continue
        if item["seq"] in seen:
            duplicate_frames.append({**item, "time_s": packet["time_s"]})
            if seen[item["seq"]] != item["direction"]:
                failures.append("SEQUENCE_PAYLOAD_CONFLICT")
            continue
        seen[item["seq"]] = item["direction"]
        accepted.append({**item, "time_s": packet["time_s"]})
    return {"failures": failures, "accepted": accepted,
            "duplicates": duplicate_frames, "invalid": invalid_frames}


def receiver_identity(result, truth):
    """Host-only diagnoses; never changes wire acceptance or service matching.

    SAVE occurrence is an observation identifier, not an extra field sent to or
    retained by the device. A reused sequence cannot be repaired by this label.
    """
    records = result.get("records", [])
    seen, retransmissions, reused, conflicts = {}, [], [], []
    for packet in result.get("packets", []):
        item = decode(packet.get("hex"))
        if item is None:
            continue
        possible = [(i, record) for i, record in enumerate(records)
                    if record["seq"] == item["seq"] and record["direction"] == item["direction"]
                    and record["committed_s"] <= packet["time_s"] + 1e-9]
        origin = possible[-1][0] if possible else None
        row = {**item, "time_s": packet["time_s"], "host_save_ordinal": origin}
        if origin is not None:
            saved = records[origin]
            preceding = [e for e in truth if e["direction"] == item["direction"]
                         and e["time_s"] <= saved["committed_s"] + 1e-9]
            row["preceding_truth_event_id"] = preceding[-1]["event_id"] if preceding else None
        if item["seq"] in seen:
            old = seen[item["seq"]]
            if old["direction"] != item["direction"]:
                conflicts.append({"first": old, "later": row})
            if old["host_save_ordinal"] == origin:
                retransmissions.append(row)
            else:
                reused.append({"first": old, "later": row})
        else:
            seen[item["seq"]] = row
    return {"same_record_wire_retransmissions": retransmissions,
            "different_saved_record_sequence_reuse": reused,
            "sequence_direction_conflicts": conflicts,
            "diagnostic_scope": "Observer SAVE ordinals and preceding same-direction truth distinguish provenance; receiver remains sequence-deduplicated. These annotations do not recover lost events or establish a new frame identity."}


def evaluate(task, design, result):
    failures, unknown = [], []
    if result.get("task_sha256") != identity(task) or result.get("design_sha256") != identity(design):
        failures.append("INPUT_BINDING")
    if result.get("result_sha256") != identity({k: v for k, v in result.items() if k != "result_sha256"}):
        failures.append("RESULT_BINDING")
    if result.get("execution_status") != "COMPLETE":
        unknown.append("INCOMPLETE_EXECUTION")
    if not result.get("model_valid"):
        unknown.append("MODEL_DOMAIN")
    truth = event_truth(task)
    rx = receive_frames(task, result.get("packets", []))
    failures.extend(rx["failures"])
    accepted, duplicate_frames, invalid_frames = rx["accepted"], rx["duplicates"], rx["invalid"]
    matches, unmatched, used = [], [], set()
    for item in accepted:
        possible = [e for e in truth if e["event_id"] not in used and e["direction"] == item["direction"]
                    and -1e-8 <= item["time_s"] - e["time_s"] <= task["service"]["receive_deadline_s"] + 1e-8]
        if possible:
            event = possible[0]
            used.add(event["event_id"])
            matches.append({"event_id": event["event_id"], "seq": item["seq"], "latency_s": item["time_s"] - event["time_s"]})
        else:
            unmatched.append(item)
    missed = [e["event_id"] for e in truth if e["event_id"] not in used]
    if missed:
        failures.append("MISSED_OR_LATE_EVENT")
    if unmatched:
        failures.append("SPURIOUS_OR_DUPLICATE_EVENT_ID")
    if [m["event_id"] for m in matches] != sorted(m["event_id"] for m in matches):
        failures.append("EVENT_ORDER")
    if invalid_frames:
        failures.append("INVALID_WIRE_FRAME")
    if result.get("peak_handle_force_n", float("inf")) > task["service"]["handle_force_max_n"] + 1e-9:
        failures.append("HANDLE_FORCE")
    energy = result["energy"]
    mechanical_residual = energy["mechanical_j"] - energy["source_bus_j"] - energy["copper_j"] - energy["rectifier_j"] - energy["other_source_loss_j"]
    storage_residual = energy["initial_stored_j"] + energy["source_bus_j"] - energy["load_j"] - energy["leak_j"] - energy["spill_j"] - energy["final_stored_j"]
    energy_tolerance = max(2e-6, abs(energy["mechanical_j"]) * .002)
    if abs(mechanical_residual) > energy_tolerance or abs(storage_residual) > energy_tolerance:
        failures.append("ENERGY_CLOSURE")
    # A model-domain breach or incomplete tool execution cannot establish a
    # physical service failure. Definite input/content tampering remains FAIL.
    binding_failure = any(x in failures for x in ("INPUT_BINDING", "RESULT_BINDING"))
    verdict = "FAIL" if binding_failure else ("UNKNOWN" if unknown else ("FAIL" if failures else "PASS"))
    return {"schema_version": "pqe-door-assessment-v2", "verdict": verdict,
            "failures": sorted(set(failures)), "unknown": unknown, "truth": truth,
            "receiver_records": accepted, "matches": matches, "missed_event_ids": missed,
            "unmatched_records": unmatched, "duplicate_wire_frames": duplicate_frames,
            "receiver_identity": receiver_identity(result, truth),
            "mechanical_residual_j": mechanical_residual, "storage_residual_j": storage_residual,
            "energy_tolerance_j": energy_tolerance, "physical_qualification": "UNKNOWN",
            "loss_rate_statistical_claim": "NOT_ESTABLISHED"}
