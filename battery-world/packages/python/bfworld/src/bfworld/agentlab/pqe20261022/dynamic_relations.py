"""Public phase facts and inexpensive, conditional DOOR repair predictions.

This module is a developer model, not the reference environment.  It imports
the existing source law and coefficients, never the transient solver, evaluator
or DoorProgram.  Prediction uses at most twelve angular panels per public
linear-motion segment and closed-form constant-EMF RC propagation.  It does
not simulate resets, contact bounce, queue state or RF delivery.  Every call to
predict_candidate costs one analytic score, including rejected/unknown inputs;
the caller owns the global budget.  No prediction produces a service PASS.
"""
from __future__ import annotations

from bisect import bisect_left
from copy import deepcopy
import math

from .door_model import DEFAULT_MECHANISM, DOMAIN, MODEL_ID, source_step
from .door_program import PROGRAM_VERSION
from .engineering import model_identity

SCHEMA = "pqe-dynamic-relations-v1"
PANELS_PER_SEGMENT = 12
PHASE_LOADS = {"BOOT": "boot", "SAVE": "write", "TX": "tx", "ACK": "write"}
SERVICE_LINKS = {
    "BOOT": ["powered contact observation", "receive deadline"],
    "CAPTURE": ["event identity", "event order", "no spurious events"],
    "SAVE": ["atomic durable event", "event order"],
    "WAIT": ["TX gate", "receive deadline", "retained queue"],
    "TX": ["wire completion", "receive deadline"],
    "ACK": ["atomic queue removal", "no duplicate frames"],
    "HOLD": ["contact continuity", "event order", "state retention"],
}
APPROX_CONDITIONS = [
    "Existing constructed cam/reciprocal-generator source and constant phase loads.",
    "Public piecewise linear motion; midpoint EMF per angular panel, not a fine-step solver.",
    "One powered observation/SAVE/TX/ACK per public contact window; no reset/retry simulation.",
    "Gateway availability is checked only at the approximate first TX completion.",
    "Observed charge, waveform and old-design phase voltages are never reused for a candidate.",
]


def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _relation(name, kind, status, value, conditions, source):
    return {"relation_id": name, "kind": kind, "status": status,
            "value": value, "conditions": list(conditions), "source": source}


def _motion(task):
    motion = task.get("motion")
    if not isinstance(motion, list) or not motion:
        raise ValueError("PUBLIC_LINEAR_MOTION_REQUIRED")
    previous = 0.0
    for s in motion:
        if (not isinstance(s, dict) or not all(_number(s.get(k)) for k in
                ("start_s", "end_s", "start_deg", "end_deg")) or
                s["start_s"] < previous or s["end_s"] <= s["start_s"] or
                not 0 <= s["start_deg"] <= 90 or not 0 <= s["end_deg"] <= 90):
            raise ValueError("PUBLIC_LINEAR_MOTION_INVALID")
        previous = s["end_s"]
    return motion


def _windows(task):
    """Public contact opportunities, deliberately not hidden evaluator truth."""
    sensor = task["sensor"]
    offsets = sensor.get("bounce_offsets_s", [0.0])
    if not offsets or not all(_number(x) and x >= 0 for x in offsets):
        raise ValueError("PUBLIC_BOUNCE_OFFSETS_REQUIRED")
    out = []
    for s in _motion(task):
        a, b = s["start_deg"], s["end_deg"]
        if a == b:
            continue
        threshold = sensor["open_deg"] if b > a else sensor["closed_deg"]
        if (a < threshold <= b) or (b <= threshold < a):
            crossing = s["start_s"] + (threshold-a)/(b-a)*(s["end_s"]-s["start_s"])
            out.append({"crossing_s": crossing, "direction": int(b > a),
                        "stable_contact_s": crossing + max(offsets),
                        "public_deadline_s": crossing + task["service"]["stable_s"]
                        + task["service"]["receive_deadline_s"]})
    return out


def _phase_load(task, phase):
    c = task["components"]
    if phase in ("CAPTURE", "WAIT", "HOLD"):
        return c["idle_a"], None
    stem = PHASE_LOADS[phase]
    return c[stem + "_a"], c[stem + "_s"]


def extract_phase_facts(task, design, result):
    """Extract public observations only; sparse samples remain explicitly sparse.

    Accepts the public result, including its compact projection.  Never opens
    files or consumes host assessment/truth.  A design mismatch fails closed.
    Observation classifications describe the executed point, not new designs.
    """
    out = {"schema": SCHEMA, "scope": {"task_sha256": model_identity(task),
           "design_sha256": model_identity(design), "result_sha256": result.get("result_sha256"),
           "result_task_sha256": result.get("task_sha256"), "source_model": MODEL_ID},
           "phases": [], "failed_phases": [], "relations": [],
           "competing_explanations": [], "service": {}, "status": "PUBLIC_OBSERVATION"}
    if result.get("design") != design:
        out.update(status="UNBOUND_DESIGN", unknowns=["result design differs from supplied design"])
        return out
    facts = result.get("facts", {})
    activity = sorted((e for e in facts.get("activity", []) if _number(e.get("time_s"))),
                      key=lambda e: e["time_s"])
    trace = sorted((r for r in facts.get("trace", []) if _number(r.get("time_s"))),
                   key=lambda r: r["time_s"])
    times = [r["time_s"] for r in trace]
    starts = {"boot": ("BOOT", "boot_complete"), "capture": ("SAVE", "save_commit"),
              "tx_begin": ("TX", "wire_complete"), "ack_begin": ("ACK", "ack_commit")}
    # Queue wait and powered retention have their own service consequences.
    starts.update({"save_commit": ("WAIT", "tx_begin"), "ack_commit": ("HOLD", "capture")})
    for i, event in enumerate(activity):
        if event.get("action") not in starts:
            continue
        phase, completion = starts[event["action"]]
        end, completed, reset = None, None, None
        for later in activity[i+1:]:
            if later.get("action") == completion:
                end, completed = later, True
                break
            if later.get("action") == "brownout":
                end, completed, reset = later, False, later
                break
            if later.get("action") in starts and phase not in ("WAIT", "HOLD"):
                end = later
                break
            if phase == "HOLD" and later.get("action") in ("tx_begin", "boot"):
                end = later
                break
        if end is None:
            continue
        t0, t1 = event["time_s"], end["time_s"]
        lo, hi = bisect_left(times, t0-1e-9), bisect_left(times, t1+1e-9)
        samples = trace[lo:hi]
        entry_v = event.get("capacitor_v")
        entry_kind = "activity_exact" if _number(entry_v) else "UNKNOWN"
        if not _number(entry_v) and samples and abs(samples[0]["time_s"]-t0) <= 0.002:
            entry_v, entry_kind = samples[0].get("capacitor_v"), "nearby_public_trace"
        current, nominal_duration = _phase_load(task, phase)
        voltages = [s["terminal_v"] for s in samples if _number(s.get("terminal_v"))]
        max_gap = max((b["time_s"]-a["time_s"] for a, b in zip(samples, samples[1:])), default=None)
        covered = (len(samples) >= 2 and samples[0]["time_s"] <= t0+0.002 and
                   samples[-1]["time_s"] >= t1-0.002 and max_gap <= 0.00201)
        source_q = source_e = None
        if covered and all(_number(s.get("source_a")) and _number(s.get("capacitor_v")) for s in samples):
            source_q = sum((b["time_s"]-a["time_s"])*(a["source_a"]+b["source_a"])/2
                           for a, b in zip(samples, samples[1:]))
            source_e = sum((b["time_s"]-a["time_s"])*
                           (a["source_a"]*a["capacitor_v"]+b["source_a"]*b["capacitor_v"])/2
                           for a, b in zip(samples, samples[1:]))
        p = {"phase": phase, "start_s": t0, "end_s": t1, "duration_s": t1-t0,
             "completed": completed, "completion_action": completion,
             "entry_v": entry_v, "entry_voltage_evidence": entry_kind,
             "entry_energy_j": 0.5*design["capacitance_f"]*entry_v**2 if _number(entry_v) else None,
             "nominal_load_a": current, "nominal_duration_s": nominal_duration,
             "nominal_charge_c": current*nominal_duration if nominal_duration is not None else None,
             "load_branch_drop_v": current*design["esr_ohm"],
             "minimum_sampled_terminal_v": min(voltages) if voltages else None,
             "source_charge_c_sampled": source_q, "source_energy_j_sampled": source_e,
             "trace_sample_count": len(samples), "source_integral_status": "SAMPLED_APPROXIMATION" if source_q is not None else "UNKNOWN_SPARSE_TRACE",
             "reset": deepcopy(reset), "service_links": SERVICE_LINKS[phase]}
        out["phases"].append(p)
        if reset and phase not in ("WAIT", "HOLD") and reset.get("during") == phase:
            out["failed_phases"].append(phase)
    # Every public capture is an information acquisition opportunity; completion
    # is separately established by SAVE, not inferred from its nominal duration.
    out["phases"].extend({"phase": "CAPTURE", "start_s": e["time_s"],
        "direction": e.get("direction"), "completed": True, "service_links": SERVICE_LINKS["CAPTURE"]}
        for e in activity if e.get("action") == "capture")
    resets = [e for e in activity if e.get("action") == "brownout"]
    counts = {key: sum(e.get("action") == key for e in activity)
              for key in ("boot", "capture", "save_commit", "tx_begin", "wire_complete", "ack_commit", "brownout")}
    exact_counts = facts.get("activity_counts", {})
    for key in counts:
        if key in exact_counts:
            counts[key] = exact_counts[key]
        elif key == "brownout" and any(k.startswith("brownout:") for k in exact_counts):
            counts[key] = sum(v for k, v in exact_counts.items() if k.startswith("brownout:"))
    for phase in PHASE_LOADS:
        if exact_counts.get("brownout:"+phase, 0):
            out["failed_phases"].append(phase)
    out["failed_phases"] = sorted(set(out["failed_phases"]))
    check = result.get("public_check", {})
    out["service"] = {"public_check": deepcopy(check), "activity_counts": counts,
        "receiver_records": len(facts.get("receiver_records", [])),
        "public_contact_windows": _windows(task), "model_valid": result.get("model_valid"),
        "domain_errors": deepcopy(result.get("domain_errors", [])),
        "persistent_queue": design["persistent_queue"],
        "count_evidence": "exact public activity_counts" if exact_counts else "public activity rows",
        "brownout_counts_by_phase": {k.split(":", 1)[1]: v for k, v in exact_counts.items()
                                     if k.startswith("brownout:")},
        "truth_or_private_assessment_read": False}
    tx_resets = [e for e in resets if e.get("during") == "TX"]
    tx_entries = [p for p in out["phases"] if p["phase"] == "TX"]
    immediate = any(_number(p["entry_v"]) and
                    p["entry_v"]-task["components"]["tx_a"]*design["esr_ohm"] < design["brownout_v"]
                    for p in tx_entries)
    out["competing_explanations"] = [
        {"id": "load_terminal_uvlo", "status": "OBSERVED" if tx_resets else "NOT_DISCRIMINATED",
         "evidence": len(tx_resets), "unique_cause": False},
        {"id": "instantaneous_branch_drop", "status": "SUPPORTED_AT_ENTRY" if immediate else "NOT_DISCRIMINATED",
         "unique_cause": False},
        {"id": "phase_charge_or_energy_deficit", "status": "COMPATIBLE" if tx_resets else "NOT_DISCRIMINATED",
         "unique_cause": False},
        {"id": "source_arrival_timing", "status": "NOT_DISCRIMINATED", "unique_cause": False},
        {"id": "restart_retry_amplification", "status": "OBSERVED_PATTERN" if counts["tx_begin"] > max(1, counts["save_commit"]) else "NOT_DISCRIMINATED",
         "unique_cause": False},
        {"id": "unpowered_event_information_loss", "status": "POSSIBLE" if resets and check.get("verdict") != "PASS" else "NOT_DISCRIMINATED",
         "unique_cause": False},
    ]
    out["relations"].append(_relation("complete_service_at_executed_point", "OBSERVED", check.get("verdict", "UNKNOWN"),
        {"public_check": check, "failed_phases": out["failed_phases"]},
        ["Executed design only; no unique root cause or whole-domain conclusion."], "public Result/activity"))
    out["relations"].append(_relation("atomic_state_retention", "CONDITIONAL", "KNOWN_MODEL_RULE",
        {"SAVE_and_ACK_both_pay_write_charge": True, "persistent": design["persistent_queue"]},
        ["A reset before commit preserves only the previous persistent image; volatile state is lost."],
        "door_program.DoorProgram.advance/reset"))
    return out


def _panels(task, t0, t1):
    cuts = {t0, t1}
    motion = _motion(task)
    for s in motion:
        if s["end_s"] < t0 or s["start_s"] > t1:
            continue
        for n in range(PANELS_PER_SEGMENT+1):
            t = s["start_s"] + n/PANELS_PER_SEGMENT*(s["end_s"]-s["start_s"])
            if t0 < t < t1:
                cuts.add(t)
    cuts = sorted(cuts)
    for a, b in zip(cuts, cuts[1:]):
        mid = (a+b)/2
        segment = next((s for s in motion if s["start_s"] <= mid < s["end_s"]), None)
        if segment:
            omega = (segment["end_deg"]-segment["start_deg"])/(segment["end_s"]-segment["start_s"])
            theta = segment["start_deg"] + omega*(mid-segment["start_s"])
        else:
            omega, theta = 0.0, 0.0  # no velocity means no generator source
        yield a, b, theta, omega


def _rc(v0, duration, current, emf, design, components, mechanism):
    """Exact constant-EMF affine RC substep; branch switching keeps V feedback.

    No program or reset simulation.  Zero/clamp clipping bounds an open-loop
    phase approximation; a phase crossing UVLO is already marked inadequate.
    """
    cap, leak, coil = design["capacitance_f"], components["leakage_ohm"], mechanism["coil_resistance_ohm"]
    u = max(0.0, emf-mechanism["rectifier_drop_v"])
    remaining, voltage = duration, v0
    source_q = 0.0
    if voltage > u:
        tau = cap*leak
        denom = u+current*leak
        crossing = tau*math.log((voltage+current*leak)/denom) if denom > 0 else math.inf
        used = min(remaining, max(0.0, crossing))
        voltage = (voltage+current*leak)*math.exp(-used/tau)-current*leak
        remaining -= used
    if remaining > 1e-14:
        conductance = 1/coil+1/leak
        equilibrium = (u/coil-current)/conductance
        tau = cap/conductance
        decay = math.exp(-remaining/tau)
        integral_v = equilibrium*remaining+(voltage-equilibrium)*tau*(-math.expm1(-remaining/tau))
        source_q = max(0.0, (u*remaining-integral_v)/coil)
        voltage = equilibrium+(voltage-equilibrium)*decay
    return max(0.0, min(components["max_v"], voltage)), source_q


def _advance(task, design, v0, t0, t1, current, gate=None):
    m, c = {**DEFAULT_MECHANISM, **design["mechanism"]}, task["components"]
    voltage, minimum, charge = v0, v0, 0.0
    if gate is not None and voltage >= gate:
        return {"end_v": voltage, "minimum_v": voltage, "source_charge_c_approx": 0.0, "end_s": t0, "gate_reached": True}
    for a, b, theta, omega in _panels(task, t0, t1):
        # source_step is instantaneous public algebra, not a trajectory solver.
        source = source_step(theta, omega, voltage, m)
        end, q = _rc(voltage, b-a, current, source["emf_v"], design, c, m)
        if gate is not None and voltage < gate <= end:
            low, high = 0.0, b-a
            for _ in range(20):
                mid = (low+high)/2
                if _rc(voltage, mid, current, source["emf_v"], design, c, m)[0] >= gate:
                    high = mid
                else:
                    low = mid
            end, q = _rc(voltage, high, current, source["emf_v"], design, c, m)
            return {"end_v": end, "minimum_v": min(minimum, end), "source_charge_c_approx": charge+q,
                    "end_s": a+high, "gate_reached": True}
        voltage, minimum, charge = end, min(minimum, end), charge+q
    return {"end_v": voltage, "minimum_v": minimum, "source_charge_c_approx": charge,
            "end_s": t1, "gate_reached": False if gate is not None else None}


def _input_checks(task, design):
    failures = []
    declared = task.get("public_inputs", {}).get("source_model", {}).get("kind")
    if declared is not None:
        if declared != "constructed continuous cam and reciprocal electromagnetic generator":
            raise ValueError("UNSUPPORTED_SOURCE_MODEL")
    elif "linear-generator cam" not in task.get("geometry", {}).get("source_domain", ""):
        raise ValueError("DECLARED_DOOR_SOURCE_REQUIRED")
    for key, domain in task.get("design_domain", {}).items():
        value = design.get(key)
        if domain.get("kind") == "number":
            ok = _number(value) and domain["min"] <= value <= domain["max"]
        elif domain.get("kind") == "boolean":
            ok = type(value) is bool
        elif domain.get("kind") == "mechanism":
            editable = domain.get("editable", {})
            ok = isinstance(value, dict) and all(k in editable and _number(v)
                and editable[k][0] <= v <= editable[k][1] for k, v in value.items())
        else:
            ok = False
        if not ok:
            failures.append("Task.design_domain:"+key)
    c = task["components"]
    required = ("capacitance_f", "esr_ohm", "startup_v", "brownout_v", "tx_gate_v", "debounce_s", "retry_s")
    if not all(_number(design.get(k)) for k in required) or design["capacitance_f"] <= 0:
        raise ValueError("COMPLETE_FINITE_DESIGN_REQUIRED")
    if not 0 < design["brownout_v"] < design["startup_v"] <= c["max_v"]:
        failures.append("power_threshold_order")
    if design["esr_ohm"] < 0 or c["leakage_ohm"] <= 0:
        failures.append("nonphysical_passive_elements")
    static = source_step(0.0, 0.0, 0.0, design["mechanism"])
    failures.extend(static.get("domain_errors", []))
    for s in _motion(task):
        if abs((s["end_deg"]-s["start_deg"])/(s["end_s"]-s["start_s"])) > DOMAIN["maximum_speed_deg_s"]:
            failures.append("speed_out_of_domain")
    return list(dict.fromkeys(failures)), static


def predict_candidate(task, design, phase_facts=None):
    """One counted cheap score with necessary bounds and conditional phase margins.

    phase_facts may contribute only prior failed-phase labels.  Candidate source
    and bus voltage are recomputed from Task/current Design.  A conditional
    no-source capacitance lower bound holds only at its stated entry voltage;
    it must be re-predicted after changing C.  This function never certifies
    full service and does not use Task IDs, recorded successes or old Q.
    score is a finite numeric bottleneck margin; larger is preferred.  A hard
    necessary failure is -1e9 and an unsupported prediction remains -100.
    """
    out = {"schema": SCHEMA, "analytic_scores_consumed": 1,
           "scope": {"task_sha256": model_identity(task), "design_sha256": model_identity(design),
                     "source_model": MODEL_ID, "program_version": PROGRAM_VERSION},
           "prediction_status": "UNKNOWN", "service_verdict": "UNKNOWN", "score": -100.0,
           "necessary_failures": [], "phase_predictions": [], "relations": [],
           "predicted_received_count": None,
           "repair_intervals": {}, "unknowns": list(APPROX_CONDITIONS),
           "source_feedback": {"recomputed_for_current_design": True,
                "old_waveform_reused": False, "old_charge_reused": False,
                "panels_per_motion_segment": PANELS_PER_SEGMENT,
                "law": "C*dV/dt=max((abs(emf)-V-Vrect)/Rcoil,0)-Iphase-V/Rleak"}}
    try:
        c, m = task["components"], {**DEFAULT_MECHANISM, **design["mechanism"]}
        failures, static = _input_checks(task, design)
        windows, motion = _windows(task), _motion(task)
        peak = 0.0
        for s in motion:
            lo, hi = sorted((s["start_deg"], s["end_deg"]))
            sine = 1.0 if lo <= 45 <= hi else max(abs(math.sin(math.radians(2*lo))), abs(math.sin(math.radians(2*hi))))
            peak = max(peak, sine*abs(math.radians((s["end_deg"]-s["start_deg"])/(s["end_s"]-s["start_s"]))))
        emf = m["generator_constant_vs_per_m"]*m["stroke_m"]*peak
        initial = task["initial"]["capacitor_v"]
        ceiling = min(c["max_v"], max(initial, emf-m["rectifier_drop_v"], 0.0))
        if design["startup_v"] > ceiling+1e-12:
            failures.append("startup_above_passive_source_upper_bound")
        if emf > DOMAIN["maximum_emf_v"]+1e-12:
            failures.append("emf_rating_exceeded")
        for phase in PHASE_LOADS:
            current, _ = _phase_load(task, phase)
            if ceiling-current*design["esr_ohm"] < design["brownout_v"]:
                failures.append(phase+"_terminal_below_uvlo_even_at_bus_upper_bound")
        out["necessary_failures"] = list(dict.fromkeys(failures))
        out["necessary_checks"] = [{"name": name, "status": "FAIL", "necessary": True}
                                   for name in out["necessary_failures"]]
        out["relations"] += [
            _relation("static_model_domain", "NECESSARY", "FAIL" if failures else "NOT_REFUTED", static.get("geometry"),
                      ["No dynamic rating/service validity follows from static geometry."], "door_model.source_step/DOMAIN; Task.design_domain"),
            _relation("passive_bus_upper_bound", "NECESSARY", "KNOWN", {"maximum_emf_v": emf, "bus_upper_v": ceiling},
                      ["Nonnegative passive loads, no other energy source; an upper bound is not reachable voltage."], "door_model.source_step; Task.motion/initial"),
        ]
        if failures:
            out.update(prediction_status="REJECT_NECESSARY", score=-1e9)
            return out
        if not windows:
            out["unknowns"].append("No public contact opportunity; full service is not predicted.")
            return out
        # Optimistic constant-peak charging is a necessary cold-start C upper
        # bound.  It deliberately omits loads/leakage, never asserts reachability.
        upper = None
        u = emf-m["rectifier_drop_v"]
        if initial < design["startup_v"] < u:
            available = windows[0]["public_deadline_s"]-motion[0]["start_s"]
            upper = available/(m["coil_resistance_ohm"]*math.log((u-initial)/(u-design["startup_v"])))
            if design["capacitance_f"] > upper+1e-12:
                out["necessary_failures"].append("cold_start_capacitance_above_optimistic_deadline_bound")
                out["necessary_checks"].append({"name": out["necessary_failures"][-1], "status": "FAIL", "necessary": True})
                out["relations"].append(_relation("optimistic_cold_start_capacitance", "NECESSARY", "FAIL",
                    {"capacitance_f": design["capacitance_f"], "upper_f": upper},
                    ["Even constant maximum EMF, zero load and zero leakage must reach startup before the first public deadline."],
                    "door_model.source_step; Task.motion/initial/service"))
                out.update(prediction_status="REJECT_NECESSARY", score=-1e9)
                return out
        out["repair_intervals"]["capacitance_f"] = {"optimistic_cold_start_upper_f": upper,
            "conditional_no_source_lower_f": None, "condition_entry_voltage_v": None,
            "lower_bound_kind": "CONDITIONAL_SUFFICIENT_BOUND_FOR_DECLARED_TAIL_ONLY",
            "upper_bound_kind": "NECESSARY_OPTIMISTIC_CHARGING_BOUND",
            "requires_reprediction_after_C_change": True}
        tangent = math.tan(math.radians(DOMAIN["maximum_pressure_angle_deg"]))
        base_per_stroke = (math.sqrt(1+4/tangent**2)-1)/2
        sum_limit = DOMAIN["envelope_width_m"]/2-0.002
        domain = task.get("design_domain", {}).get("mechanism", {}).get("editable", {})
        stroke_domain = domain.get("stroke_m", [None, None])
        base_domain = domain.get("cam_base_radius_m", [None, None])
        out["repair_intervals"]["mechanism"] = {
            "minimum_base_radius_per_stroke": base_per_stroke,
            "maximum_base_plus_stroke_m": sum_limit,
            "joint_geometry_stroke_upper_m": min(sum_limit/(1+base_per_stroke), DOMAIN["envelope_length_m"]-0.044),
            "passive_startup_stroke_lower_m": (design["startup_v"]+m["rectifier_drop_v"])/(m["generator_constant_vs_per_m"]*peak) if peak else None,
            "task_stroke_interval_m": stroke_domain, "task_base_radius_interval_m": base_domain,
            "conditions": ["base >= coefficient*stroke; base+stroke <= maximum; intersect both Task intervals.",
                           "Passive startup stroke bound is necessary only for a cold source below startup; finite charging still matters."]}
        leak_upper = c["max_v"]/c["leakage_ohm"]
        out["repair_intervals"]["startup_v"] = {
            "conditional_no_source_boot_lower_v": design["brownout_v"]+c["boot_a"]*design["esr_ohm"]
                +(c["boot_a"]+leak_upper)*c["boot_s"]/design["capacitance_f"],
            "passive_source_upper_v": ceiling,
            "conditions": ["Lower bound is sufficient for BOOT only if that entry voltage is actually reached; not a required startup value."]}
        out["repair_intervals"]["tx_gate_v"] = {
            "conditional_no_source_tx_lower_v": design["brownout_v"]+c["tx_a"]*design["esr_ohm"]
                +(c["tx_a"]+leak_upper)*c["tx_s"]/design["capacitance_f"],
            "passive_source_upper_v": ceiling,
            "conditions": ["If reached, the lower value is sufficient for one isolated TX without source; SAVE/ACK/retention remain separate."]}
        lower, lower_entry = 0.0, None
        margins = []
        previous_time, voltage, booted = 0.0, initial, False
        for n, window in enumerate(windows):
            # Long quiet gaps may contain intended power loss.  A zero-residual
            # restart is conservative for charging, but retention/reset semantics
            # remain UNKNOWN rather than duplicating the device state machine.
            previous_crossing = windows[n-1]["crossing_s"] if n else 0.0
            if n and window["crossing_s"]-previous_crossing > 2*task["service"]["receive_deadline_s"]+design["debounce_s"]:
                previous_time = next(s["start_s"] for s in motion if s["start_s"] > previous_crossing)
                voltage, booted = 0.0, False
            if not booted:
                start = _advance(task, design, voltage, previous_time, window["public_deadline_s"], 0.0, design["startup_v"])
                if not start["gate_reached"]:
                    margins.append((start["end_v"]-design["startup_v"])/design["startup_v"]-1)
                    out["phase_predictions"].append({"phase": "BOOT", "window": n,
                        "status": "APPROXIMATE_STARTUP_NOT_REACHED", **start, "service_links": SERVICE_LINKS["BOOT"]})
                    continue
                previous_time, voltage, booted = start["end_s"], start["end_v"], True
                phases = [("BOOT", c["boot_s"])]
            else:
                phases = []
            capture_time = max(previous_time, window["stable_contact_s"])+design["debounce_s"]
            for phase, duration in phases:
                step = _advance(task, design, voltage, previous_time, previous_time+duration, c["boot_a"])
                margin = step["minimum_v"]-c["boot_a"]*design["esr_ohm"]-design["brownout_v"]
                out["phase_predictions"].append({"phase": phase, "window": n, "start_s": previous_time,
                    "entry_v": voltage, **step, "terminal_margin_v": margin, "kind": "APPROXIMATE",
                    "minimum_terminal_v": step["minimum_v"]-c["boot_a"]*design["esr_ohm"],
                    "startup_margin_v": margin,
                    "service_links": SERVICE_LINKS[phase]})
                margins.append(margin/design["brownout_v"])
                voltage, previous_time = step["end_v"], step["end_s"]
            capture_time = max(capture_time, previous_time)
            hold = _advance(task, design, voltage, previous_time, capture_time, c["idle_a"])
            hold_margin = hold["minimum_v"]-c["idle_a"]*design["esr_ohm"]-design["brownout_v"]
            out["phase_predictions"].append({"phase": "HOLD", "window": n, "start_s": previous_time,
                "entry_v": voltage, **hold, "terminal_margin_v": hold_margin, "kind": "APPROXIMATE", "service_links": SERVICE_LINKS["HOLD"]})
            margins.append(hold_margin/design["brownout_v"])
            voltage, previous_time = hold["end_v"], hold["end_s"]
            out["phase_predictions"].append({"phase": "CAPTURE", "window": n,
                "approximate_time_s": capture_time, "status": "POWERED_OBSERVATION_ASSUMED",
                "service_links": SERVICE_LINKS["CAPTURE"],
                "conditions": ["No reset since final contact bounce; actual contact/sequence semantics are not simulated."]})
            tail_entry = voltage
            wait_duration = 0.0
            for phase in ("SAVE", "WAIT", "TX", "ACK"):
                current, duration = _phase_load(task, phase)
                if phase == "WAIT":
                    step = _advance(task, design, voltage, previous_time,
                                    max(previous_time, window["public_deadline_s"]-c["tx_s"]), current, design["tx_gate_v"])
                else:
                    step = _advance(task, design, voltage, previous_time, previous_time+duration, current)
                margin = step["minimum_v"]-current*design["esr_ohm"]-design["brownout_v"]
                out["phase_predictions"].append({"phase": phase, "window": n, "start_s": previous_time,
                    "entry_v": voltage, **step, "terminal_margin_v": margin, "kind": "APPROXIMATE", "service_links": SERVICE_LINKS[phase]})
                out["phase_predictions"][-1]["minimum_terminal_v"] = step["minimum_v"]-current*design["esr_ohm"]
                margins.append(margin/design["brownout_v"])
                if phase == "WAIT":
                    wait_duration = step["end_s"]-previous_time
                voltage, previous_time = step["end_v"], step["end_s"]
                if phase == "WAIT" and not step["gate_reached"]:
                    margins.append(-1.0)
                if phase == "TX":
                    slack = window["public_deadline_s"]-previous_time
                    gateway = any(a <= previous_time <= b for a, b in task.get("gateway_windows", []))
                    out["phase_predictions"][-1].update(deadline_slack_s=slack, gateway_at_approx_wire_time=gateway)
                    margins.append(slack/task["service"]["receive_deadline_s"] if gateway else -1.0)
            tail_duration = 2*c["write_s"]+c["tx_s"]+wait_duration
            tail_q = 2*c["write_a"]*c["write_s"]+c["tx_a"]*c["tx_s"]+c["idle_a"]*wait_duration+leak_upper*tail_duration
            tail_floor = max(design["tx_gate_v"], design["brownout_v"]+max(c["write_a"], c["tx_a"], c["idle_a"])*design["esr_ohm"])
            if tail_entry > tail_floor:
                needed = tail_q/(tail_entry-tail_floor)
                if needed > lower:
                    lower, lower_entry = needed, tail_entry
        interval = out["repair_intervals"]["capacitance_f"]
        interval.update(conditional_no_source_lower_f=lower or None, condition_entry_voltage_v=lower_entry,
                        tail_loads="SAVE+WAIT+TX+ACK and leakage bounded by max_v/Rleak; fixed declared durations.")
        out["relations"].append(_relation("no_source_save_tx_ack_tail", "CONDITIONAL_ALGEBRA", "APPROXIMATE_ENTRY",
            interval, ["Entry voltage is recomputed approximate, not an observed voltage transplanted across C.",
                       "Given this entry voltage and durations, C>=lower keeps bus above TX gate and every load UVLO threshold with zero source; includes wait and worst-case leakage.",
                       "This is sufficient for the declared powered tail only, not capture/startup, gateway or complete service.",
                       "Source input is nonnegative; passing this algebra never establishes complete service."],
            "Task.components; engineering.Cstore/Rbranch; door_program.advance"))
        out["prediction_status"] = "CONDITIONAL"
        out["score"] = min(margins, default=-100.0)
        out["approximate_margins"] = {"minimum_normalized_phase_or_deadline_margin": out["score"]}
        out["prior_failed_phases"] = (list(phase_facts.get("failed_phases", [])) if isinstance(phase_facts, dict)
            and phase_facts.get("scope", {}).get("task_sha256") == model_identity(task) else [])
        out["unknowns"] += ["Reset/retry/atomic queue/contact semantics require the independent original consumer.",
                             "Dynamic force/current/clamp ratings between coarse panels are not certified.",
                             "Subsequent cold bursts use zero residual charge; no full-horizon service claim."]
        return out
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        out["unknowns"].append(str(exc))
        return out
