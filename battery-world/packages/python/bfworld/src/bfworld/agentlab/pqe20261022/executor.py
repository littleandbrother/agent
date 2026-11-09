"""Small hybrid consumer of door motion, loaded source and powered firmware.

The input trajectory is prescribed; its reaction force is an evaluated cost.
No evaluator truth or method policy is imported here. Component currents are
declared constructed-model loads, not measurements of a commercial product.
"""
from bisect import bisect_right
from copy import deepcopy
import hashlib
import json
import math

from .door_model import source_step
from .door_program import DoorProgram, PROGRAM_VERSION, encode_frame as frame
from .engineering import build_engineering_model, consume_engineering_model


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def kinematics(task, t):
    angle = task["initial"]["angle_deg"]
    for segment in task["motion"]:
        if t < segment["start_s"]:
            return angle, 0.0
        if t < segment["end_s"]:
            speed = (segment["end_deg"] - segment["start_deg"]) / (segment["end_s"] - segment["start_s"])
            return segment["start_deg"] + speed * (t - segment["start_s"]), speed
        angle = segment["end_deg"]
    return angle, 0.0


def contact_edges(task):
    """Construct reed-contact bounce from motion; no service-event oracle."""
    edges = []
    old = 0
    for s in task["motion"]:
        a, b = s["start_deg"], s["end_deg"]
        new = 1 if b > a else 0
        threshold = task["sensor"]["open_deg" if new else "closed_deg"]
        if new == old or not min(a, b) <= threshold <= max(a, b) or a == b:
            continue
        t = s["start_s"] + (threshold - a) / (b - a) * (s["end_s"] - s["start_s"])
        for index, offset in enumerate(task["sensor"]["bounce_offsets_s"]):
            edges.append((t + offset, new if index % 2 == 0 else old))
        old = new
    return sorted(edges)


def execute_design(task, design, dt_s=None, engineering_model=None):
    model = deepcopy(engineering_model) if engineering_model is not None else build_engineering_model(task, design)
    inputs = consume_engineering_model(model, task, design)
    d = inputs["design"]
    c = d["capacitance_f"]
    comp = inputs["components"]
    dt = dt_s or task["integration"]["dt_s"]
    mechanism = inputs["mechanism"]
    program = DoorProgram(d, comp)
    edge_list = contact_edges(task)
    edge_times = [x[0] for x in edge_list]
    v = task["initial"]["capacitor_v"]
    t = 0.0
    committed, packets, activity, trace = [], [], [], []
    counters = {k: 0.0 for k in ["mechanical_j", "source_bus_j", "copper_j", "rectifier_j",
                                "other_source_loss_j", "load_j", "leak_j", "spill_j", "esr_j"]}
    peak_force, minimum_tx_v, balance_error = 0.0, None, 0.0
    errors = set()

    def collect_events(at):
        for event in program.drain_events():
            item = {"time_s": at, **event}
            if event["action"] in {"boot", "brownout", "tx_begin"}:
                item["capacitor_v"] = v
            activity.append(item)
            if event["action"] == "save_commit":
                committed.append({**event["record"], "committed_s": at,
                                  "durable": event["durable"]})
            elif event["action"] == "wire_complete":
                packets.append({"time_s": at, "hex": event["hex"]})

    def reset(reason, at):
        program.reset(reason)
        collect_events(at)

    def idle_to(end):
        nonlocal t, v
        # No movement, no unfinished write/TX. Sleep consumes current until UVLO,
        # then only capacitor leakage remains; NVM costs were paid on SAVE.
        duration = end - t
        before_e = .5 * c * v * v
        leak_r = comp["leakage_ohm"]
        i = comp["idle_a"] if program.mode != "OFF" else 0.0
        off_after = math.inf
        if i and v > d["brownout_v"]:
            off_after = c * leak_r * math.log((v + i * leak_r) / (d["brownout_v"] + i * leak_r))
        active = min(duration, max(0.0, off_after)) if i else 0.0
        if active:
            integral_v = (v + i * leak_r) * c * leak_r * (1 - math.exp(-active / (c * leak_r))) - i * leak_r * active
            counters["load_j"] += max(0.0, i * integral_v)
            v = max(0.0, (v + i * leak_r) * math.exp(-active / (c * leak_r)) - i * leak_r)
            program.elapse_idle(active)
        if off_after <= duration:
            reset("IDLE_UVLO", t + off_after)
        v *= math.exp(-(duration - active) / (c * leak_r))
        counters["leak_j"] += max(0.0, before_e - .5 * c * v * v - max(0.0, i * integral_v if active else 0.0))
        t = end
        program.invalidate_contact_sample()

    intervals = []
    for motion in task["motion"]:
        a, b = max(0.0, motion["start_s"] - .05), min(task["duration_s"], motion["end_s"] + task["service"]["receive_deadline_s"] + .2)
        if intervals and a <= intervals[-1][1]:
            intervals[-1][1] = max(b, intervals[-1][1])
        else:
            intervals.append([a, b])
    for start, end in intervals:
        idle_to(start)
        while (t < end - 1e-10 or program.mode not in ("OFF", "IDLE")
               or (program.mode == "IDLE" and program.queue and v >= d["tx_gate_v"])):
            h = min(dt, end - t) if t < end - 1e-10 else dt
            index = bisect_right(edge_times, t) - 1
            raw = edge_list[index][1] if index >= 0 else 0
            current = program.begin_step(v, raw)
            collect_events(t)
            terminal = v - current * d["esr_ohm"]
            if program.mode == "TX":
                minimum_tx_v = terminal if minimum_tx_v is None else min(minimum_tx_v, terminal)
            if program.mode != "OFF" and terminal < d["brownout_v"]:
                reset("LOAD_TERMINAL_UVLO", t)
                current = 0.0
            angle, speed = kinematics(task, t + h / 2)
            # Implicit midpoint capacitor equation. Bus-dependent source current
            # is recomputed rather than supplying a prechosen energy pulse.
            lo, hi = 0.0, comp["max_v"]
            for _ in range(28):
                candidate = (lo + hi) / 2
                mid = (v + candidate) / 2
                src = source_step(angle, speed, mid, mechanism)
                residual = c * (candidate - v) / h - (src["current_a"] - current - mid / comp["leakage_ohm"])
                if residual > 0:
                    hi = candidate
                else:
                    lo = candidate
            after = (lo + hi) / 2
            mid = (v + after) / 2
            src = source_step(angle, speed, mid, mechanism)
            if not src["valid"]:
                errors.update(src["domain_errors"])
            force = abs(src["handle_force_n"])
            peak_force = max(peak_force, force)
            bus_j = mid * src["current_a"] * h
            load_j, leak_j = mid * current * h, mid * mid / comp["leakage_ohm"] * h
            delta = .5 * c * (after * after - v * v)
            spill = max(0.0, bus_j - load_j - leak_j - delta) if after > comp["max_v"] - 1e-4 else 0.0
            balance_error += bus_j - load_j - leak_j - delta - spill
            counters["source_bus_j"] += bus_j
            counters["mechanical_j"] += src["mechanical_power_w"] * h
            counters["copper_j"] += src["copper_loss_w"] * h
            counters["rectifier_j"] += src["rectifier_loss_w"] * h
            counters["other_source_loss_j"] += src.get("other_loss_w", 0.0) * h
            counters["load_j"] += load_j
            counters["leak_j"] += leak_j
            counters["spill_j"] += spill
            counters["esr_j"] += current * current * d["esr_ohm"] * h
            old_mode = program.mode
            v, t = after, t + h
            if old_mode == "TX":
                terminal_after = v - current * d["esr_ohm"]
                minimum_tx_v = terminal_after if minimum_tx_v is None else min(minimum_tx_v, terminal_after)
            program.advance(h, v - current * d["esr_ohm"],
                            gateway_available=any(a <= t <= b for a, b in task["gateway_windows"]))
            collect_events(t)
            if len(trace) == 0 or t - trace[-1]["time_s"] >= .02 - 1e-8 or old_mode != program.mode:
                trace.append({"time_s": round(t, 9), "theta_deg": angle, "omega_deg_s": speed,
                              "capacitor_v": v, "load_a": current, "source_a": src["current_a"],
                              "terminal_v": v - current * d["esr_ohm"], "mode": program.mode,
                              "handle_force_n": force, "program_uptime_s": program.uptime_s,
                              "queue_length": len(program.queue)})
    idle_to(task["duration_s"])
    result = {"schema_version": "pqe-door-result-v2", "execution_status": "COMPLETE",
              "task_sha256": identity(task), "design_sha256": identity(design),
              "design": deepcopy(design), "dt_s": dt, "model_valid": not errors, "domain_errors": sorted(errors),
              "engineering_model": model, "engineering_model_sha256": inputs["model_sha256"],
              "program_version": PROGRAM_VERSION, "program_state": program.snapshot(),
              "records": committed, "packets": packets, "activity": activity, "trace": trace,
              "energy": {**counters, "initial_stored_j": .5 * c * task["initial"]["capacitor_v"] ** 2,
                         "final_stored_j": .5 * c * v * v, "integration_residual_j": balance_error},
              "peak_handle_force_n": peak_force, "minimum_tx_terminal_v": minimum_tx_v,
              "boot_count": program.boot_count, "remaining_queue": program.remaining_queue,
              "physical_qualification": "UNKNOWN"}
    result["result_sha256"] = identity(result)
    return result
