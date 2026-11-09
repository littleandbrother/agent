"""Paid holder extension; original source, wire, program and evaluator retained.

The old executor has no always-on-domain/idle hook. Only the enabled branch
therefore needs a new integration loop: common midpoint source algebra and
closed-form no-motion decay, with holder events and both load domains. It does
not copy the old run lifecycle, adapter, evaluator, tasks or method cycle.
"""
from bisect import bisect_right
from copy import deepcopy
import math
from collections import deque

from ..pqe20261022 import executor as original
from ..pqe20261023bold import consumer as bold
from ..pqe20261023bold.firmware import DoorProgram as BoldProgram
from .holding import EventHolding, PROFILE
from .task import HOLDING_DOMAIN, base_design, validate_design

VERSION = "codebt-door-consumer-v1"
PROGRAM_VERSION = "codebt-door-program-v1"
identity = original.identity


class SolverToolError(RuntimeError):
    """Numerical guard failure is not a service or energy verdict."""
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__("CODEBT_SOLVER_GUARD:" + diagnostic["reason"])


def build_engineering_model(task, design):
    validate_design(task, design)
    return {"schema_version": "codebt-door-engineering-v1", "task_sha256": identity(task),
            "design_sha256": identity(design), "base": bold.build_engineering_model(task, base_design(design)),
            "holding": {"version": VERSION, "profile": deepcopy(PROFILE),
                        "parameters": {k: deepcopy(design[k]) for k in HOLDING_DOMAIN}},
            "scope": "One shared supply branch. Holder and read/clear currents enter the original bus equation. Constructed assumptions; hardware UNKNOWN."}


def consume_engineering_model(model, task, design):
    if model != build_engineering_model(task, design):
        raise ValueError("CODEBT_ENGINEERING_BINDING")
    resolved = bold.consume_engineering_model(model["base"], task, base_design(design))
    resolved["design"].update(deepcopy(model["holding"]["parameters"]))
    resolved["model_sha256"] = identity(model)
    return resolved


class HoldingDoorProgram(BoldProgram):
    """Independent read/clear placements over the unchanged paid SAVE/TX/ACK."""
    def __init__(self, design, components, holder):
        super().__init__(design, components)
        self.holder = holder
        self.read_token = self.last_read = self.clear_seq = None
        self.after_clear = None

    def _event(self, action, **fields):
        self.events.append({"action": action, "uptime_s": self.uptime_s,
                            "device_event_order": self.holder.next_audit_order(), **fields})

    @property
    def current_a(self):
        if self.mode == "HREAD":
            return PROFILE["read_a"]
        if self.mode == "HCLEAR":
            return PROFILE["clear_a"]
        return super().current_a

    def reset(self, reason):
        super().reset(reason)
        self.read_token = self.last_read = self.clear_seq = None
        self.after_clear = None

    def _clear(self, seq, continuation=None):
        self.clear_seq, self.after_clear = seq, deepcopy(continuation)
        self.mode, self.remaining_s = "HCLEAR", PROFILE["clear_s"]
        self._event("holding_clear_begin", seq=seq, placement=self.design["clear_after"])

    def _save(self, record):
        self.pending = {"seq": record["assigned_seq"], "direction": record["direction"]}
        self.mode, self.remaining_s = "SAVE", self.components["write_s"]
        self._event("capture", direction=record["direction"], source="paid_holder_read")

    def begin_step(self, capacitor_v, contact):
        if self.design["read_source"] == "holding_then_contact" and (self.holder.ready or self.holder.busy):
            if self.mode == "IDLE":
                if self.holder.ready and (self.last_read is None or self.holder.unread_ready):
                    self.read_token = self.holder.latch_read_transaction()
                    self.mode, self.remaining_s = "HREAD", PROFILE["read_s"]
                    self._event("holding_read_begin", token=self.read_token)
                    return self.current_a
                # A held prefix owns capture order until cleared; only original
                # FIFO transport may proceed. This is not a second fresh queue.
                contact = self.ram["last_direction"]
            elif self.mode in ("HREAD", "HCLEAR"):
                return self.current_a
        if self.mode in ("HREAD", "HCLEAR"):
            return self.current_a
        return super().begin_step(capacitor_v, contact)

    def advance(self, elapsed_s, terminal_v, gateway_available=False):
        if elapsed_s < 0:
            raise ValueError("NEGATIVE_POWERED_TIME")
        before = self.mode
        record = deepcopy(self.pending) if before == "SAVE" else (deepcopy(self.queue[0]) if before == "ACK" and self.queue else None)
        if before in ("HREAD", "HCLEAR"):
            self.uptime_s += elapsed_s
            if terminal_v < self.design["brownout_v"]:
                self.reset("LOAD_TERMINAL_UVLO")
                return
            self.remaining_s -= elapsed_s
            if self.remaining_s > 1e-12:
                return
            self.mode, self.remaining_s = "IDLE", 0.
            if before == "HREAD":
                held = self.holder.read_commit(self.read_token, self.ram["seq"]+1)
                if held is None:
                    self.last_read = None
                    return
                self.last_read = (held["token"], held["assigned_seq"])
                seq = held["assigned_seq"]
                if seq > self.ram["seq"]:
                    if self.design["clear_after"] == "early":
                        self._clear(seq, held)
                    else:
                        self._save(held)
                else:
                    self._event("holding_already_committed", seq=seq)
                    queued = any(r["seq"] == seq for r in self.queue)
                    if self.design["clear_after"] in ("early", "save") or (self.design["clear_after"] == "ack" and not queued):
                        self._clear(seq)
            else:
                self.holder.clear_commit(self.clear_seq)
                continuation, self.after_clear = self.after_clear, None
                self.last_read = None
                if continuation is not None:
                    self._save(continuation)
            return
        super().advance(elapsed_s, terminal_v, gateway_available)
        if self.mode == "IDLE" and record is not None:
            placement = self.design["clear_after"]
            if (before == "SAVE" and placement == "save") or (before == "ACK" and placement == "ack"):
                if self.last_read is not None and self.last_read[1] == record["seq"]:
                    self._clear(record["seq"])

    def snapshot(self):
        value = super().snapshot()
        value.update(program_version=PROGRAM_VERSION, holding=self.holder.snapshot(),
                     read_source=self.design["read_source"], clear_after=self.design["clear_after"],
                     read_token=self.read_token, clear_seq=self.clear_seq,
                     clear_continuation=deepcopy(self.after_clear))
        return value


def _idle_decay_step(v, h, current, c, leak_r):
    """Exact no-source constant-load RC flow, including sub-dt intervals."""
    tau = c*leak_r
    decay = -math.expm1(-h/tau)
    after = max(0., v-(v+current*leak_r)*decay)
    integral_v = (v+current*leak_r)*tau*decay-current*leak_r*h
    return after, integral_v


def _midpoint_step(v, h, current, c, comp, angle, speed, mechanism):
    """Original 28-bisection loaded-source equation, without a trajectory cache."""
    lo, hi = 0., comp["max_v"]
    for _ in range(28):
        candidate = (lo+hi)/2
        mid = (v+candidate)/2
        src = original.source_step(angle, speed, mid, mechanism)
        residual = c*(candidate-v)/h-(src["current_a"]-current-mid/comp["leakage_ohm"])
        if residual > 0:
            hi = candidate
        else:
            lo = candidate
    after = (lo+hi)/2
    mid = (v+after)/2
    return after, mid, original.source_step(angle, speed, mid, mechanism)


def execute_design(task, design, dt_s=None, engineering_model=None):
    """Full science entry. Not called by offline logic checks or on import."""
    model = deepcopy(engineering_model) if engineering_model is not None else build_engineering_model(task, design)
    inputs = consume_engineering_model(model, task, design)
    if design["holding_component"] == "off":
        # Exact original execution route; only outer version/input identity changes.
        result = bold.execute_design(task, base_design(design), dt_s=dt_s, engineering_model=model["base"])
        result.update(schema_version="codebt-door-result-v1", design=deepcopy(design),
                      design_sha256=identity(design), engineering_model=model,
                      engineering_model_sha256=identity(model), base_program_version=result["program_version"],
                      program_version=PROGRAM_VERSION, holding_loads={"monitor_j": 0., "capture_j": 0., "read_j": 0., "clear_j": 0.},
                      holding_route="OFF_EXACT_ORIGINAL_FUNCTION")
        result["result_sha256"] = identity({k: v for k, v in result.items() if k != "result_sha256"})
        return result
    return _execute_enabled(task, design, dt_s, model, inputs)


def _execute_enabled(task, design, dt_s, model, inputs):
    d, comp, mechanism = inputs["design"], inputs["components"], inputs["mechanism"]
    dt, c, horizon = dt_s or task["integration"]["dt_s"], d["capacitance_f"], task["duration_s"]
    if dt not in task["integration"]["allowed_dt_s"]:
        raise ValueError("CODEBT_UNREGISTERED_REFINEMENT")
    holder = EventHolding(d["holding_capacity"], d["holding_overflow"])
    program = HoldingDoorProgram(d, comp, holder)
    edges = original.contact_edges(task)
    edge_times = [x[0] for x in edges]
    boundaries = sorted({0., float(horizon), *edge_times,
        *(x[k] for x in task["motion"] for k in ("start_s", "end_s")),
        *(x for window in task["gateway_windows"] for x in window)})
    t, v = 0., task["initial"]["capacitor_v"]
    committed, packets, activity, trace = [], [], [], []
    energy = {k: 0. for k in ("mechanical_j", "source_bus_j", "copper_j", "rectifier_j",
        "other_source_loss_j", "load_j", "leak_j", "spill_j", "esr_j")}
    holding_loads = {k: 0. for k in ("monitor_j", "capture_j", "read_j", "clear_j")}
    phases = {k: 0. for k in ("BOOT", "SAVE", "TX", "ACK")}
    phase_esr = dict(phases)
    errors, peak_force, minimum_tx_v, balance_error = set(), 0., None, 0.

    iterations, tiny_steps = 0, 0
    last_steps = deque(maxlen=12)

    def diagnostic(reason):
        return {"schema": "codebt-solver-diagnostic-v1", "reason": reason,
                "iterations": iterations, "tiny_steps": tiny_steps,
                "time_s": t, "capacitor_v": v, "program": program.snapshot(),
                "holder": holder.snapshot(), "holder_raw": holder.raw,
                "holder_stable_since_s": holder.stable_since_s,
                "holder_last_direction": holder.last_direction,
                "last_steps": list(last_steps), "last_events": activity[-16:],
                "partial_energy": dict(energy), "domain_errors": sorted(errors),
                "full_service_verdict": None, "guard_changes_physics": False}

    def collect(at):
        for event in sorted(program.drain_events()+holder.drain_events(), key=lambda e: e["device_event_order"]):
            activity.append({"time_s": at, **event})
            if event["action"] == "save_commit":
                committed.append({**event["record"], "committed_s": at, "durable": event["durable"]})
            elif event["action"] == "wire_complete":
                packets.append({"time_s": at, "hex": event["hex"]})

    while t < horizon-1e-10:
        iterations += 1
        if iterations > 200000:
            raise SolverToolError(diagnostic("STEP_CAP_200000"))
        idx = bisect_right(edge_times, t+1e-12)-1
        raw = edges[idx][1] if idx >= 0 else 0
        holder.prepare(v-(program.current_a+holder.current_a)*d["esr_ohm"], raw)
        core_a = program.begin_step(v, raw)
        if program.mode != "OFF" and v-(core_a+holder.current_a)*d["esr_ohm"] < d["brownout_v"]:
            program.reset("LOAD_TERMINAL_UVLO")
            core_a = 0.
        holder.prepare(v-(core_a+holder.current_a)*d["esr_ohm"], raw)
        collect(t)
        current = core_a+holder.current_a
        old_mode = program.mode
        angle, speed = original.kinematics(task, t)
        next_external = boundaries[min(bisect_right(boundaries, t+1e-10), len(boundaries)-1)]
        limit = min(horizon-t, next_external-t)
        idle = speed == 0 and old_mode in ("OFF", "IDLE") and holder.capture is None
        voltage_events = []
        if idle:
            limit = min(limit, holder.next_boundary_s())
            if old_mode == "IDLE":
                if program.queue and v >= program.effective_tx_gate():
                    limit = min(limit, max(0., program.retry_due_s-program.uptime_s))
                # begin_step masks direct contact while the holder is ready or
                # busy; only a consumable direct-contact deadline belongs here.
                if (d["read_source"] == "contact_only" or not (holder.ready or holder.busy)) and raw != program.ram["last_direction"]:
                    limit = min(limit, max(0., d["debounce_s"]-(program.uptime_s-program.stable_since_s)))
            thresholds = []
            if old_mode != "OFF":
                thresholds.append(("mcu", d["brownout_v"]+current*d["esr_ohm"]))
            if holder.powered:
                thresholds.append(("holder", PROFILE["voltage_min_v"]+current*d["esr_ohm"]))
            for component, threshold in thresholds:
                if v > threshold:
                    hit = c*comp["leakage_ohm"]*math.log((v+current*comp["leakage_ohm"])/(threshold+current*comp["leakage_ohm"]))
                    limit = min(limit, hit)
                    voltage_events.append((hit, component, threshold))
                else:
                    limit = min(limit, dt)
        proposed_h = limit if idle and limit > 0 else min(dt, max(1e-9, limit), horizon-t)
        tiny_steps = tiny_steps+1 if proposed_h <= 1e-8 else 0
        last_steps.append({"time_s": t, "v": v, "mode": old_mode,
                           "current_a": current, "raw": raw, "idle": idle,
                           "next_external_s": next_external, "holder_boundary_s": holder.next_boundary_s() if holder.powered else None,
                           "limit_s": limit, "proposed_h_s": proposed_h,
                           "holder_ready": holder.ready, "holder_busy": holder.busy,
                           "program_uptime_s": program.uptime_s,
                           "program_retry_due_s": program.retry_due_s,
                           "program_stable_since_s": program.stable_since_s})
        if tiny_steps >= 128:
            raise SolverToolError(diagnostic("128_CONSECUTIVE_STEPS_LE_1E-8_S"))
        falling_events = set()
        if idle and limit > 0:
            h = limit
            after, integral_v = _idle_decay_step(v, h, current, c, comp["leakage_ohm"])
            # A predicted falling crossing is an event at the original threshold.
            # Consume it after paying this exact interval, without a voltage gap
            # or an arbitrary time increment to force the state transition.
            for hit, component, threshold in voltage_events:
                if hit <= h:
                    after = min(after, threshold)
                    falling_events.add(component)
            load_j = max(0., current*integral_v)
            leak_j = .5*c*(v*v-after*after)-load_j
            bus_j, spill, delta = 0., 0., .5*c*(after*after-v*v)
            src = None
        else:
            h = min(dt, max(1e-9, limit), horizon-t)
            if old_mode not in ("OFF", "IDLE"):
                h = min(h, max(1e-9, program.remaining_s))
            if holder.capture:
                h = min(h, max(1e-9, holder.capture["remaining_s"]))
            angle, speed = original.kinematics(task, t+h/2)
            after, mid, src = _midpoint_step(v, h, current, c, comp, angle, speed, mechanism)
            integral_v = mid*h
            bus_j, load_j = mid*src["current_a"]*h, mid*current*h
            leak_j, delta = mid*mid/comp["leakage_ohm"]*h, .5*c*(after*after-v*v)
            spill = max(0., bus_j-load_j-leak_j-delta) if after > comp["max_v"]-1e-4 else 0.
            if not src["valid"]:
                errors.update(src["domain_errors"])
            peak_force = max(peak_force, abs(src["handle_force_n"]))
            for output, field in (("mechanical_j", "mechanical_power_w"), ("copper_j", "copper_loss_w"), ("rectifier_j", "rectifier_loss_w"), ("other_source_loss_j", "other_loss_w")):
                energy[output] += src.get(field, 0.)*h
        energy["source_bus_j"] += bus_j
        energy["load_j"] += load_j
        energy["leak_j"] += leak_j
        energy["spill_j"] += spill
        energy["esr_j"] += current*current*d["esr_ohm"]*h
        balance_error += bus_j-load_j-leak_j-delta-spill
        if holder.powered:
            holding_loads["monitor_j"] += PROFILE["monitor_a"]*integral_v
            if holder.capture:
                holding_loads["capture_j"] += PROFILE["capture_a"]*integral_v
        if old_mode in ("HREAD", "HCLEAR"):
            holding_loads["read_j" if old_mode == "HREAD" else "clear_j"] += core_a*integral_v
        if old_mode in phases:
            phases[old_mode] += core_a*integral_v
            phase_esr[old_mode] += core_a*current*d["esr_ohm"]*h
        terminal = after-current*d["esr_ohm"]
        if old_mode == "TX":
            minimum = min(v-current*d["esr_ohm"], terminal)
            minimum_tx_v = minimum if minimum_tx_v is None else min(minimum_tx_v, minimum)
        v, t = after, t+h
        holder.advance(h, terminal)
        if "holder" in falling_events:
            holder.power_loss("IDLE_FALLING_VOLTAGE_BOUNDARY")
        if idle and program.mode == "IDLE":
            program.elapse_idle(h)
            if terminal < d["brownout_v"] or "mcu" in falling_events:
                program.reset("IDLE_UVLO")
        else:
            program.advance(h, terminal, any(a <= t <= b for a, b in task["gateway_windows"]))
        program.phase_energy_j, program.phase_esr_j = dict(phases), dict(phase_esr)
        collect(t)
        if not trace or t-trace[-1]["time_s"] >= .02-1e-8 or old_mode != program.mode:
            trace.append({"time_s": t, "theta_deg": angle, "omega_deg_s": speed, "capacitor_v": v,
                "terminal_v": terminal, "load_a": current, "source_a": src["current_a"] if src else 0.,
                "mode": program.mode, "queue_length": len(program.queue), "holder_count": len(holder.records),
                "holder_powered": holder.powered, "program_uptime_s": program.uptime_s})
    result = {"schema_version": "codebt-door-result-v1", "execution_status": "COMPLETE",
        "task_sha256": identity(task), "design_sha256": identity(design), "design": deepcopy(design),
        "dt_s": dt, "model_valid": not errors, "domain_errors": sorted(errors),
        "engineering_model": model, "engineering_model_sha256": inputs["model_sha256"],
        "program_version": PROGRAM_VERSION, "program_state": program.snapshot(), "records": committed,
        "packets": packets, "activity": activity, "trace": trace, "holding_loads": holding_loads,
        "energy": {**energy, "initial_stored_j": .5*c*task["initial"]["capacitor_v"]**2,
                   "final_stored_j": .5*c*v*v, "integration_residual_j": balance_error},
        "peak_handle_force_n": peak_force, "minimum_tx_terminal_v": minimum_tx_v,
        "boot_count": program.boot_count, "remaining_queue": program.remaining_queue,
        "physical_qualification": "UNKNOWN", "holding_route": "PAID_ENABLED_DOMAIN",
        "solver_diagnostics": {"iterations": iterations, "step_cap": 200000, "guard_triggered": False}}
    result["result_sha256"] = identity(result)
    return result
