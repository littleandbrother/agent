"""Continuous original-consumer public observations, never a second simulator.

No predictor, solver, evaluator, program step or file I/O is called.  The
frozen M3 extractor supplies SAVE identities; this module links them to their
original global activity/uptime, power epochs, source schedule and public trace
brackets.  It never predicts candidate voltages or changes an initial state.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from copy import deepcopy
import math

from .service_relations import extract_service_facts

SCHEMA = "pqe-trajectory-service-facts-v1"
CONDITIONS = [
    "All rows belong to this single executed Task/Design/result from its original initial state.",
    "World timestamps and published gateway/source schedules are host facts, not a new device clock or future observation.",
    "Public trace is a sample projection; complete public lists are not a fine-step waveform or a continuous peak certificate.",
    "Brackets retain original sample times and indices without interpolation; a nearby sample is not exact voltage at the query time.",
    "Original full-run energy ledger is not allocated to individual records from sparse trace samples.",
    "No observed entry voltage or charge is a predicted voltage, precharge or initial state for another design.",
    "SAVE, wire, receiver arrival, ACK commit and removal remain distinct; missing or ambiguous links stay UNKNOWN.",
]


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _bracket(trace, times, time_s, gate_v):
    if not _number(time_s) or not trace:
        return {"query_s": time_s, "status": "UNKNOWN_NO_SAMPLES"}
    before, after = bisect_right(times, time_s)-1, bisect_left(times, time_s)
    def sample(index):
        if not 0 <= index < len(trace):
            return None
        original_index, row = trace[index]
        value = {k: deepcopy(row.get(k)) for k in (
            "time_s", "capacitor_v", "terminal_v", "source_a", "load_a",
            "mode", "queue_length", "program_uptime_s", "theta_deg", "omega_deg_s")}
        value.update(source_trace_index=original_index, offset_s=row["time_s"]-time_s,
                     sampled_gate_margin_v=row["capacitor_v"]-gate_v if _number(row.get("capacitor_v")) else None)
        return value
    return {"query_s": time_s, "status": "ORIGINAL_PUBLIC_SAMPLE_BRACKET",
            "at_or_before": sample(before), "at_or_after": sample(after),
            "interpolated": False}


def _movement_end(task, crossing_s):
    motion = task.get("motion", [])
    if not _number(crossing_s):
        return None
    for i, segment in enumerate(motion):
        if segment["start_s"] <= crossing_s <= segment["end_s"]:
            direction = segment["end_deg"]-segment["start_deg"]
            end_s, angle = segment["end_s"], segment["end_deg"]
            for later in motion[i+1:]:
                if (abs(later["start_s"]-end_s) > 1e-8 or
                        abs(later["start_deg"]-angle) > 1e-8 or
                        (later["end_deg"]-later["start_deg"])*direction <= 0):
                    break
                end_s, angle = later["end_s"], later["end_deg"]
            return end_s
    return None


def extract_trajectory_facts(task, design, public_result):
    """Extract continuous saved evidence; zero new scientific calculations.

    Does not consume private truth or assessment.  Factual public service checks
    are retained as observations, not recomputed.  Public contact matching has
    the same declared scope as the frozen M3 extractor.
    """
    base = extract_service_facts(task, design, public_result)
    out = {"schema": SCHEMA, "status": "PUBLIC_TRAJECTORY_FACTS",
           "scope": {**deepcopy(base["scope"]),
                     "input_sha256": public_result.get("input_sha256"),
                     "single_original_consumer_run": True,
                     "new_prediction_or_simulation": False},
           "coverage": deepcopy(base["coverage"]),
           "records": deepcopy(base["records"]), "summary": deepcopy(base["summary"]),
           "service_failures": deepcopy(base["service_failures"]),
           "timeline": [], "power_epochs": [], "source_gateway_observations": [],
           "queue_summary": deepcopy(base["queue_summary"]), "energy": {},
           "conditions": list(CONDITIONS), "unknowns": deepcopy(base["unknowns"])}
    if base["status"] != "PUBLIC_OBSERVATION":
        out["status"] = base["status"]
        return out
    if public_result.get("execution_status") != "COMPLETE":
        out["status"] = "INCOMPLETE_EXECUTION"
        out["unknowns"].append("Consumer not COMPLETE; available observations are not a complete service judgment.")
    facts = public_result.get("facts", {})
    raw_activity = facts.get("activity", [])
    activity = sorted((deepcopy(row) for row in raw_activity if
                       isinstance(row, dict) and _number(row.get("time_s"))), key=lambda row: row["time_s"])
    out["timeline"] = activity
    rows = facts.get("trace", [])
    trace = sorted(((i, row) for i, row in enumerate(rows) if
                    isinstance(row, dict) and _number(row.get("time_s"))), key=lambda pair: pair[1]["time_s"])
    times = [row["time_s"] for _, row in trace]
    boots = [row for row in activity if row.get("action") == "boot"]
    resets = [row for row in activity if row.get("action") == "brownout"]
    for i, boot in enumerate(boots):
        next_boot = boots[i+1]["time_s"] if i+1 < len(boots) else math.inf
        reset = next((row for row in resets if boot["time_s"] <= row["time_s"] < next_boot), None)
        end = reset["time_s"] if reset else None
        members = [row for row in activity if boot["time_s"] <= row["time_s"] < next_boot]
        counts = {}
        for row in members:
            name = row.get("action", "UNKNOWN")
            counts[name] = counts.get(name, 0)+1
        out["power_epochs"].append({"ordinal": i+1, "boot": deepcopy(boot),
            "reset": deepcopy(reset), "start_s": boot["time_s"], "end_s": end,
            "observed_activity_counts": counts,
            "queue_length_at_reset": reset.get("queue_length") if reset else None,
            "scope": "Observed original program epoch; no reconstructed intermediate NVM image."})
    for record in out["records"]:
        saved = record["saved_s"]
        end = record["ack_commits"][0]["time_s"] if record["ack_commits"] else math.inf
        tx = [deepcopy(row) for row in activity if row.get("action") == "tx_begin" and
              row.get("seq") == record["seq"] and saved <= row["time_s"] <= end]
        if record["identity_status"] != "OBSERVED_SAVE":
            tx = []
        wires = record["wire_attempts"]
        first_wire = wires[0]["time_s"] if wires else None
        query_start = first_wire if first_wire is not None else saved
        recovery = next((max(a, query_start) for a, b in task.get("gateway_windows", []) if b >= query_start), None)
        match = record.get("public_contact_match") or {}
        motion_end = _movement_end(task, match.get("crossing_s"))
        deadline = record.get("deadline_s")
        relevant_resets = [deepcopy(row) for row in resets if saved <= row["time_s"] <= end]
        out["source_gateway_observations"].append({
            "record_id": record["record_id"], "seq": record["seq"], "direction": record["direction"],
            "saved_s": saved, "tx_begins": tx, "wire_attempts": deepcopy(wires),
            "first_wire_s": first_wire, "contiguous_public_motion_end_s": motion_end,
            "first_available_gateway_at_or_after_query_s": recovery,
            "gateway_query_start_s": query_start,
            "actual_wires_before_gateway": sum(row["time_s"] < recovery for row in wires) if recovery is not None else None,
            "recovery_samples": _bracket(trace, times, recovery, design["tx_gate_v"]),
            "motion_end_samples": _bracket(trace, times, motion_end, design["tx_gate_v"]),
            "deadline_s": deadline, "deadline_samples": _bracket(trace, times, deadline, design["tx_gate_v"]),
            "receiver_observations": deepcopy(record["receiver_observations"]),
            "ack_commits": deepcopy(record["ack_commits"]),
            "resets_before_observed_ack_or_end": relevant_resets,
            "delivery_status": record["delivery_status"],
            "conditions": ["Existing executed point only; no new-design trajectory is inferred.",
                           "Gateway availability is a public Task schedule, not a newly observable firmware input."]})
    counts = {}
    for row in activity:
        key = row.get("action", "UNKNOWN")
        counts[key] = counts.get(key, 0)+1
    # Exact original counts override sampled activity only where available.
    exact = facts.get("activity_counts", {})
    for key in counts:
        if key in exact:
            counts[key] = exact[key]
    out["summary"].update(observed_activity_counts=counts,
        tx_count=counts.get("tx_begin", 0), ack_commit_count=counts.get("ack_commit", 0),
        original_minimum_tx_terminal_v=facts.get("minimum_tx_terminal_v") if counts.get("tx_begin", 0) else None,
        original_model_valid=public_result.get("model_valid"),
        original_domain_errors=deepcopy(public_result.get("domain_errors", [])),
        complete_public_event_lists=all(out["coverage"][name]["complete"] for name in
            ("activity", "records", "packets", "receiver_records")),
        formal_service_verdict="UNKNOWN")
    out["energy"] = {"original_full_run_ledger": deepcopy(facts.get("energy", {})),
                     "scope": "Original executed design only; per-record source/energy attribution UNKNOWN from sparse samples."}
    if not counts.get("tx_begin", 0):
        out["unknowns"].append("No observed TX: no actual TX/ACK voltage margin is available; WAIT voltage is not efficacy.")
    if not out["summary"]["complete_public_event_lists"]:
        out["unknowns"].append("Incomplete public event lists: timeline/epochs/attempt counts may be lower bounds, not complete continuity.")
    return out
