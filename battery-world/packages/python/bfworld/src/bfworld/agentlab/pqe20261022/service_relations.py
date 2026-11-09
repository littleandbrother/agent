"""Public record delivery facts and bounded, conditional retry-tail algebra.

This is a developer approximation, not the scientific consumer.  The only
numerical primitive is the frozen M1 coarse constant-EMF RC relation (twelve
panels per motion segment).  Each contact window is an isolated saved record;
resets, atomic queue execution, contact acquisition and interacting backlog are
not simulated.  No prediction certifies service.  One external prediction costs
one cheap score; extraction costs zero.  The caller owns its budget ledger.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .dynamic_relations import _advance, _number, _windows
from .dynamic_relations import predict_candidate as _electrical_prediction
from .engineering import model_identity

SCHEMA = "pqe-service-relations-v1"
PREDICTION_SCHEMA = "pqe-service-prediction-v1"
MAX_ATTEMPTS_PER_WINDOW = 32
CONDITIONS = [
    "Public artifact times are observer facts, not a new clock in the device.",
    "Contact-window deadlines are derived from public motion/sensor/service, not private truth IDs.",
    "Only SAVE commits create observed record identities; wire completion alone is not delivery or removal.",
    "ACK commit removes the FIFO head; powered retry time resets at boot and does not run while unpowered.",
    "Missing links in sampled lists remain UNKNOWN; absence is established only in complete public lists.",
]
PREDICTION_CONDITIONS = [
    "One isolated record per public contact window; no inherited FIFO backlog.",
    "SAVE entry comes from the candidate-recomputed frozen M1 coarse nominal prefix, not an old observed waveform.",
    "Later-window prefix voltages do not account for earlier retry/queue interactions.",
    "Coarse RC integrates prescribed loads; stops at a predicted UVLO without simulating a reset or recovery.",
    "No missed contact, interrupted atomic commit, competing capture or firmware scheduling interference is modeled.",
    "Published gateway windows are off-device planning inputs; firmware still observes availability only at wire completion.",
    "A conditional timely isolated record is not a complete-service PASS or a predicted evaluator event count.",
]


def _relation(name, status, value, conditions, evidence):
    return {"relation_id": name, "status": status, "value": value,
            "conditions": list(conditions), "evidence": evidence}


def _rows(facts, name):
    value = facts.get(name, [])
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _identity(record):
    if not isinstance(record, dict):
        return None
    seq, direction = record.get("seq"), record.get("direction")
    if type(seq) is not int or seq < 0 or type(direction) is not int or direction not in (0, 1):
        return None
    return seq, direction


def _coverage(facts, name):
    rows = _rows(facts, name)
    catalog = facts.get("detail_catalog", {}).get(name, {})
    declared = catalog.get("count") if isinstance(catalog, dict) else None
    complete = isinstance(facts.get(name), list) and (declared is None or declared == len(rows))
    return {"observed_rows": len(rows), "declared_rows": declared,
            "complete": complete, "detail": deepcopy(catalog)}


def _public_windows(task):
    windows = _windows(task)
    for i, window in enumerate(windows):
        window["window"] = i
        window["public_stable_s"] = window["crossing_s"] + task["service"]["stable_s"]
    return windows


def extract_service_facts(task, design, result):
    """Join public SAVE/wire/receiver/ACK observations without private evaluation.

    A record identity includes its SAVE time.  Repeated transmissions of the
    same saved record are distinct from two SAVE identities reusing one seq.
    A seq/direction frame cannot resolve an ambiguous reused identity.
    """
    out = {"schema": SCHEMA, "status": "PUBLIC_OBSERVATION",
           "scope": {"task_sha256": model_identity(task), "design_sha256": model_identity(design),
                     "result_sha256": result.get("result_sha256"),
                     "result_task_sha256": result.get("task_sha256")},
           "coverage": {}, "records": [], "summary": {}, "service_failures": [],
           "queue_summary": {}, "retry_timing": {}, "remaining_energy": {},
           "record_relations": [], "conditions": list(CONDITIONS), "unknowns": []}
    if result.get("design") != design:
        out.update(status="UNBOUND_DESIGN", unknowns=["Result design differs from supplied design."])
        return out
    if result.get("task_id") != task.get("task_id"):
        out.update(status="UNBOUND_TASK", unknowns=["Result task ID differs from supplied public Task."])
        return out
    facts = result.get("facts", {})
    for name in ("activity", "records", "packets", "receiver_records", "trace"):
        out["coverage"][name] = _coverage(facts, name)
        if not out["coverage"][name]["complete"]:
            out["unknowns"].append("Incomplete public list: " + name)
    activity = sorted((x for x in _rows(facts, "activity") if _number(x.get("time_s"))),
                      key=lambda x: x["time_s"])
    captures = [x for x in activity if x.get("action") == "capture"]
    resets = [deepcopy(x) for x in activity if x.get("action") == "brownout"]
    try:
        windows = _public_windows(task)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        windows = []
        out["unknowns"].append("Public contact-window construction unavailable.")
    # Merge the two public views of the SAME commit, never merge distinct saves.
    saves = {}
    for row in _rows(facts, "records"):
        if _identity(row) is not None and _number(row.get("committed_s")):
            saves[(*_identity(row), row["committed_s"])] = deepcopy(row)
    for event in activity:
        record = event.get("record")
        if event.get("action") == "save_commit" and _identity(record) is not None:
            key = (*_identity(record), event["time_s"])
            saves.setdefault(key, {**deepcopy(record), "committed_s": event["time_s"],
                                   "durable": event.get("durable")})
    ordered = sorted(saves.values(), key=lambda x: x["committed_s"])
    final_time = max([0.0] + [x["time_s"] for x in activity] +
                     [x["time_s"] for x in _rows(facts, "trace") if _number(x.get("time_s"))])
    if result.get("execution_status") == "COMPLETE" and _number(task.get("duration_s")):
        final_time = max(final_time, task["duration_s"])
    seq_groups = {}
    for i, row in enumerate(ordered):
        seq_groups.setdefault(row["seq"], []).append(i)
    reused = {seq: ids for seq, ids in seq_groups.items() if len(ids) > 1}
    for i, row in enumerate(ordered):
        key, saved = _identity(row), row["committed_s"]
        ambiguous = row["seq"] in reused
        prior = [x for x in captures if x.get("direction") == row["direction"] and
                 x["time_s"] <= saved and saved-x["time_s"] <= task["components"]["write_s"] + 0.005]
        capture = prior[-1] if prior else None
        public_match = None
        if capture:
            for n, w in enumerate(windows):
                next_crossing = windows[n+1]["crossing_s"] if n+1 < len(windows) else math.inf
                if w["direction"] == row["direction"] and w["crossing_s"] <= capture["time_s"] < next_crossing:
                    public_match = deepcopy(w)
        def events(action):
            return [deepcopy(x) for x in activity if x.get("action") == action and
                    _identity(x.get("record")) == key and x["time_s"] >= saved]
        wires, ack_begin, ack_commit = events("wire_complete"), events("ack_begin"), events("ack_commit")
        receives = [deepcopy(x) for x in _rows(facts, "receiver_records") if
                    _identity(x) == key and _number(x.get("time_s")) and x["time_s"] >= saved]
        receives.sort(key=lambda x: x["time_s"])
        deadline = public_match["public_deadline_s"] if public_match else None
        received = receives[0]["time_s"] if receives and not ambiguous else None
        if ambiguous:
            delivery = "UNKNOWN_AMBIGUOUS_SEQUENCE_REUSE"
        elif received is not None and deadline is not None:
            delivery = ("BEFORE_PUBLIC_STABLE_TIME" if received < public_match["public_stable_s"] else
                        "TIMELY_PUBLIC_WINDOW" if received <= deadline+1e-9 else "LATE_PUBLIC_WINDOW")
        elif not receives and out["coverage"]["receiver_records"]["complete"]:
            delivery = "NO_OBSERVED_RECEIVE"
        else:
            delivery = "UNKNOWN"
        rec = {"record_id": "save:"+str(row["seq"])+":"+str(row["direction"])+":"+str(saved),
               "seq": row["seq"], "direction": row["direction"], "saved_s": saved,
               "durable": row.get("durable"), "identity_status": "AMBIGUOUS_REUSED_SEQ" if ambiguous else "OBSERVED_SAVE",
               "capture": deepcopy(capture), "public_contact_match": public_match,
               "deadline_s": deadline, "age_at_observation_end_s": final_time-saved,
               "wire_attempts": wires, "receiver_observations": receives,
               "first_receive_s": received, "receive_delay_from_save_s": received-saved if received is not None else None,
               "deadline_slack_s": deadline-received if deadline is not None and received is not None else None,
               "delivery_status": delivery, "ack_begin": ack_begin, "ack_commits": ack_commit,
               "queue_removal_status": "OBSERVED_ACK_COMMIT" if ack_commit and not ambiguous else
                   "NO_OBSERVED_ACK_COMMIT" if out["coverage"]["activity"]["complete"] else "UNKNOWN",
               "same_record_retransmissions_observed": max(0, len(wires)-1) if not ambiguous else None,
               "crosses_power_reset_before_ack": any(saved < x["time_s"] <
                   (ack_commit[0]["time_s"] if ack_commit else final_time) for x in resets)}
        out["records"].append(rec)
        if delivery in ("LATE_PUBLIC_WINDOW", "NO_OBSERVED_RECEIVE", "BEFORE_PUBLIC_STABLE_TIME"):
            out["service_failures"].append({"kind": delivery, "record_id": rec["record_id"],
                                            "scope": "OBSERVED_PUBLIC_RECORD_NOT_PRIVATE_TRUTH_EVENT"})
    state = facts.get("program_state", {})
    image_name = "nvm" if state.get("persistent") and state.get("mode") == "OFF" else "ram"
    image = state.get(image_name)
    queue = deepcopy(image.get("queue", [])) if isinstance(image, dict) else None
    blocking = []
    for head in out["records"]:
        if head["identity_status"] != "OBSERVED_SAVE":
            continue
        for wire in head["wire_attempts"]:
            waiting = [x["record_id"] for x in out["records"] if x["saved_s"] < wire["time_s"] and
                       x["saved_s"] > head["saved_s"] and
                       (not x["ack_commits"] or x["ack_commits"][0]["time_s"] > wire["time_s"])]
            if waiting:
                blocking.append({"head_record_id": head["record_id"], "wire_time_s": wire["time_s"],
                                 "later_saved_records_waiting": waiting})
    out["queue_summary"] = {"source": "program_state."+image_name, "records": queue,
        "length": len(queue) if isinstance(queue, list) else None,
        "head": queue[0] if queue else None, "persistent": state.get("persistent"),
        "observed_head_blocking": blocking, "remaining_seq_counter": image.get("seq") if isinstance(image, dict) else None,
        "retention_scope": "Atomic constructed program image; no physical NVM qualification."}
    if queue:
        out["service_failures"].append({"kind": "RETAINED_PENDING_QUEUE", "count": len(queue)})
    if reused:
        out["service_failures"].append({"kind": "DIFFERENT_SAVE_IDENTITIES_REUSE_SEQUENCE", "seqs": sorted(reused)})
    complete_saves = out["coverage"]["records"]["complete"] or out["coverage"]["activity"]["complete"]
    out["summary"] = {"saved_records_observed": len(out["records"]),
        "timely_public_window_records": sum(x["delivery_status"] == "TIMELY_PUBLIC_WINDOW" for x in out["records"]),
        "late_public_window_records": sum(x["delivery_status"] == "LATE_PUBLIC_WINDOW" for x in out["records"]),
        "unreceived_records": sum(x["delivery_status"] == "NO_OBSERVED_RECEIVE" for x in out["records"]),
        "same_record_retransmissions_observed": sum(x["same_record_retransmissions_observed"] or 0 for x in out["records"]),
        "different_record_sequence_reuse": {"status": "OBSERVED" if reused else "NOT_OBSERVED_COMPLETE_SAVES" if complete_saves else "UNKNOWN",
                                             "seqs": sorted(reused)},
        "service_failure_observed": bool(out["service_failures"]),
        "formal_service_verdict": "UNKNOWN", "public_check": deepcopy(result.get("public_check", {}))}
    out["retry_timing"] = {"retry_s": design["retry_s"], "resets": resets,
        "rule": "next TX start >= previous wire completion powered_uptime + retry_s AND capacitor >= TXgate; retry clock resets on boot",
        "device_has_absolute_clock": False}
    trace = sorted((x for x in _rows(facts, "trace") if _number(x.get("time_s"))), key=lambda x: x["time_s"])
    last = trace[-1] if trace else {}
    out["remaining_energy"] = {"final_stored_j": facts.get("energy", {}).get("final_stored_j"),
        "last_sample_s": last.get("time_s"), "last_sample_capacitor_v": last.get("capacitor_v"),
        "last_sample_stored_j": 0.5*design["capacitance_f"]*last["capacitor_v"]**2 if _number(last.get("capacitor_v")) else None,
        "scope": "Observed design only; sparse last sample is not final/at-deadline usable energy."}
    out["record_relations"] = [
        _relation("record_chain", "PUBLIC_OBSERVATION", [x["record_id"] for x in out["records"]],
                  ["SAVE -> repeated wire -> receiver arrival -> ACK commit -> FIFO removal are separate facts."], "public records/activity/receiver_records/program_state"),
        _relation("retained_head_blocks_later_records", "OBSERVED" if blocking else "NOT_OBSERVED",
                  blocking, ["Original FIFO only; does not prove a different order would be legal or feasible."], "wire_complete with later unacknowledged SAVE identities"),
        _relation("retry_cost", "CONDITIONAL", {"nominal_charge_per_failed_tx_c": task["components"]["tx_a"]*task["components"]["tx_s"],
                  "idle_charge_per_retry_wait_c": task["components"]["idle_a"]*design["retry_s"]},
                  ["Leakage and source change the net reserve; increasing retry_s can save attempts but miss recovery/deadline."], "public load constants and original retry rule"),
    ]
    out["unknowns"] += ["Public contact matching is not the independent evaluator truth ledger.",
                         "Observed retention does not certify a new candidate or population loss target."]
    return out


def _isolated_tail(task, design, window, save):
    c, esr, brown = task["components"], design["esr_ohm"], design["brownout_v"]
    out = {"window": window["window"], "direction": window["direction"],
           "public_deadline_s": window["public_deadline_s"], "save_end_s": save["end_s"],
           "save_end_v": save["end_v"], "attempts": [], "status": "UNKNOWN",
           "first_receive_s": None, "timely": None, "ack_completed": None,
           "minimum_terminal_margin_v": None, "retry_timing": {}, "unknowns": []}
    t, v = save["end_s"], save["end_v"]
    margins = [save.get("terminal_margin_v", -math.inf)]
    if margins[0] < 0:
        out.update(status="SAVE_UVLO_IN_NOMINAL_PREFIX", timely=False)
        return out
    for n in range(MAX_ATTEMPTS_PER_WINDOW):
        latest_start = window["public_deadline_s"]-c["tx_s"]
        if t > latest_start+1e-10:
            out.update(status="NO_TIMELY_START_IN_MODEL", timely=False)
            break
        gate = _advance(task, design, v, t, latest_start, c["idle_a"], design["tx_gate_v"])
        margins.append(gate["minimum_v"]-c["idle_a"]*esr-brown)
        t, v = gate["end_s"], gate["end_v"]
        if margins[-1] < 0:
            out.update(status="WAIT_UVLO_IN_MODEL", timely=False)
            break
        if not gate["gate_reached"]:
            out.update(status="GATE_NOT_REACHED_BY_DEADLINE_IN_MODEL", timely=False)
            break
        tx = _advance(task, design, v, t, t+c["tx_s"], c["tx_a"])
        margin = tx["minimum_v"]-c["tx_a"]*esr-brown
        margins.append(margin)
        wire = tx["end_s"]
        available = any(a <= wire <= b for a, b in task.get("gateway_windows", []))
        out["attempts"].append({"attempt": n+1, "tx_start_s": t, "entry_v": v, "wire_s": wire,
                                "end_v": tx["end_v"], "minimum_terminal_margin_v": margin,
                                "gateway_at_wire": available, "source_charge_c_approx": tx["source_charge_c_approx"]})
        t, v = wire, tx["end_v"]
        if margin < 0:
            out.update(status="TX_UVLO_IN_MODEL", timely=False)
            break
        if available:
            ack = _advance(task, design, v, t, t+c["write_s"], c["write_a"])
            ack_margin = ack["minimum_v"]-c["write_a"]*esr-brown
            margins.append(ack_margin)
            out.update(status="CONDITIONAL_RECEIVE", first_receive_s=wire,
                       timely=window["public_stable_s"] <= wire <= window["public_deadline_s"]+1e-9,
                       ack_completed=ack_margin >= 0, ack_end_s=ack["end_s"],
                       ack_end_v=ack["end_v"], deadline_slack_s=window["public_deadline_s"]-wire)
            break
        wait = _advance(task, design, v, t, min(t+design["retry_s"], window["public_deadline_s"]), c["idle_a"])
        margins.append(wait["minimum_v"]-c["idle_a"]*esr-brown)
        t, v = wait["end_s"], wait["end_v"]
        if margins[-1] < 0:
            out.update(status="RETRY_WAIT_UVLO_IN_MODEL", timely=False)
            break
    else:
        out["unknowns"].append("Bounded isolated-tail attempt cap reached; remaining attempts UNKNOWN.")
        out["status"] = "UNKNOWN_ATTEMPT_CAP"
    out["minimum_terminal_margin_v"] = min(margins)
    if out["attempts"]:
        first_wire = out["attempts"][0]["wire_s"]
        recovery = next((max(first_wire, a) for a, b in task.get("gateway_windows", []) if b >= first_wire), None)
        out["retry_timing"] = {"first_wire_s": first_wire, "next_public_gateway_s": recovery,
            "period_if_gate_and_power_persist_s": design["retry_s"]+c["tx_s"],
            "second_wire_after_recovery_retry_lower_s": max(0.0, recovery-first_wire-c["tx_s"]) if recovery is not None else None,
            "second_wire_before_deadline_retry_upper_s": window["public_deadline_s"]-first_wire-c["tx_s"],
            "conditions": ["Intervals assume first wire fixed, uninterrupted powered time and gate satisfied; not an optimum."]}
    return out


def predict_candidate(task, design, service_facts=None):
    """One cheap prediction; no solver/evaluator, file read or hidden truth.

    M1 electrical margins are retained as diagnostics, not a total service rank.
    The additional isolated-record retry approximation separates opportunities
    from unknown queue/reset consequences.  All inputs, including rejected ones,
    consume one cheap score.  Old observed voltages/charge never enter the model.
    """
    out = _electrical_prediction(task, design)
    out["electrical_schema"] = out["schema"]
    out["schema"] = PREDICTION_SCHEMA
    out["service_relations"] = []
    out["service_prediction"] = {"mode": "ISOLATED_RECORD_COARSE_RC_RETRY", "windows": [],
        "conditional_timely_windows": 0, "unknown_windows": 0,
        "max_attempts_per_window": MAX_ATTEMPTS_PER_WINDOW, "conditions": list(PREDICTION_CONDITIONS)}
    out["selection_metrics"] = {"status": "UNKNOWN", "formal_rank": None}
    out["service_verdict"] = "UNKNOWN"
    out["predicted_received_count"] = None
    out["unknowns"] += list(PREDICTION_CONDITIONS)
    bound_prior = isinstance(service_facts, dict) and service_facts.get("status") == "PUBLIC_OBSERVATION" and \
        service_facts.get("scope", {}).get("task_sha256") == model_identity(task)
    out["service_feedback"] = {"consumed": bool(bound_prior),
        "service_facts_sha256": model_identity(service_facts) if bound_prior else None,
        "observed_failure_kinds": sorted({x.get("kind", "UNKNOWN") for x in service_facts.get("service_failures", [])}) if bound_prior else [],
        "old_charge_or_voltage_reused": False}
    if out["necessary_failures"]:
        return out
    try:
        c = task["components"]
        windows = _public_windows(task)
        for window in windows:
            saves = [p for p in out["phase_predictions"] if p.get("phase") == "SAVE" and p.get("window") == window["window"]]
            if not saves:
                out["service_prediction"]["windows"].append({"window": window["window"], "status": "UNKNOWN_NO_SAVE_PREFIX", "timely": None})
            else:
                out["service_prediction"]["windows"].append(_isolated_tail(task, design, window, saves[0]))
        values = out["service_prediction"]["windows"]
        timely = sum(x.get("timely") is True for x in values)
        unknown = sum(x.get("timely") is None for x in values)
        margins = [x["minimum_terminal_margin_v"] for x in values if _number(x.get("minimum_terminal_margin_v"))]
        out["service_prediction"].update(conditional_timely_windows=timely, unknown_windows=unknown)
        out["selection_metrics"] = {"status": "CONDITIONAL_DIAGNOSTICS", "formal_rank": None,
            "conditional_timely_windows": timely, "public_contact_windows": len(windows),
            "unknown_windows": unknown, "conditional_ack_completed_windows": sum(x.get("ack_completed") is True for x in values),
            "minimum_isolated_terminal_margin_v": min(margins) if margins else None,
            "maximum_isolated_attempts": max((len(x.get("attempts", [])) for x in values), default=0),
            "scope": "Compare isolated opportunity/energy diagnostics and identify a discriminating execution; no exact full-service ordering."}
        leak = c["max_v"]/c["leakage_ohm"]
        txq, ackq = c["tx_a"]*c["tx_s"], c["write_a"]*c["write_s"]
        tx_floor = design["brownout_v"]+c["tx_a"]*design["esr_ohm"]
        ack_floor = design["brownout_v"]+c["write_a"]*design["esr_ohm"]
        gate_lower = max(tx_floor+(txq+leak*c["tx_s"])/design["capacitance_f"],
                         ack_floor+(txq+ackq+leak*(c["tx_s"]+c["write_s"]))/design["capacitance_f"])
        out["repair_intervals"]["retry_s"] = {"task_domain": deepcopy(task.get("design_domain", {}).get("retry_s")),
            "per_window": [x.get("retry_timing", {}) for x in values],
            "conditions": ["Increasing retry_s reduces attempted transmissions only while the clock stays powered; it can also miss a gateway opening or deadline."]}
        out["repair_intervals"]["tx_gate_v"]["conditional_no_source_tx_ack_lower_v"] = gate_lower
        out["service_relations"] += [
            _relation("retry_energy_deadline_joint_relation", "CONDITIONAL", {
                "failed_tx_charge_c": txq, "retry_idle_charge_c": c["idle_a"]*design["retry_s"],
                "ack_charge_c": ackq, "leakage_current_upper_a": leak,
                "no_source_tx_ack_sufficient_gate_v": gate_lower,
                "stored_energy_at_tx_gate_j": 0.5*design["capacitance_f"]*design["tx_gate_v"]**2},
                ["At reached gate, sufficient lower voltage covers one TX+ACK with zero source and bounded leakage.",
                 "Repeated failed TX consume additional charge; lowering gate may start earlier and fail energy; increasing C may delay cold start.",
                 "A larger retry interval may save reserve yet lose the last timely opportunity; no monotonic benefit is assumed."],
                "public C/ESR/load constants and retry/ACK semantics"),
            _relation("isolated_record_delivery", "APPROXIMATE", out["selection_metrics"],
                      PREDICTION_CONDITIONS, "candidate-recomputed coarse RC prefix and bounded retry tail"),
        ]
        if bound_prior:
            out["service_relations"].append(_relation("prior_public_delivery_failure", "OBSERVED_PRIOR_DESIGN",
                {"failure_kinds": out["service_feedback"]["observed_failure_kinds"],
                 "queue_length": service_facts.get("queue_summary", {}).get("length"),
                 "sequence_reuse": service_facts.get("summary", {}).get("different_record_sequence_reuse")},
                ["Past delivery failure is actionable even with no failed electrical phase; it does not certify this candidate's outcome."],
                out["service_feedback"]["service_facts_sha256"]))
        return out
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        out["unknowns"].append("Service approximation unavailable: "+str(exc))
        return out
