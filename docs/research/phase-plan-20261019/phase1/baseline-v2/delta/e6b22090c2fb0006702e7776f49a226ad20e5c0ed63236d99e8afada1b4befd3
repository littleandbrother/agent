"""Public development apparatus for current and legal-intervention sufficiency.

All models are ideal, explicitly uncalibrated computational examples.  The
analytic/event engines and time-stepping/event-program references are separate
implementations of declared assumptions, not independent physical evidence.
This module has no provider, native tool, database, or historical-run dependency.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROTOCOL_SCHEMA = "campaign-interface-protocol-v1"
RESULT_SCHEMA = "campaign-interface-result-v1"
BASELINE = "CB-6f1c798155bb7ca2352d362d57a7e2032dc79379450a723ea3cff2751ce5318c"
TOL = 1e-7


class DomainError(ValueError):
    """A proposed design or expression is outside the frozen public domain."""


class AuditError(ValueError):
    """Bytes or identity disagree with their immutable audit binding."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_protocol(path: Path) -> dict:
    data = json.loads(path.read_bytes())
    if data.get("schema_version") != PROTOCOL_SCHEMA or data.get("baseline") != BASELINE:
        raise AuditError("Unknown protocol or common baseline")
    if data["cost_cap"]["paid_model_requests"] or data["cost_cap"]["native_dispatches"]:
        raise DomainError("This executor permits no paid or native dispatch")
    return data


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as out:
        out.write(json.dumps(value, indent=2, sort_keys=True,
                             ensure_ascii=False, allow_nan=False).encode() + b"\n")


def number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DomainError("Expected a finite numeric design value")
    return float(value)


def changed_design(pair: dict, patch: dict) -> dict:
    """Validate the same public D patch independently of any outcome."""
    if not isinstance(patch, dict) or set(patch) - set(pair["design"]):
        raise DomainError("Undeclared design field")
    design = copy.deepcopy(pair["design"])
    design.update(copy.deepcopy(patch))
    domain = pair["legal_domain"]
    if pair["worlds"][0]["kind"] == "clamp":
        value = number(design["capacitance_uf"])
        if not domain["capacitance_uf"][0] <= value <= domain["capacitance_uf"][1]:
            raise DomainError("Capacitance outside legal interval")
    else:
        intervals = design["power_off_intervals"]
        if not isinstance(intervals, list) or len(intervals) > domain["max_intervals"]:
            raise DomainError("Unsupported power schedule")
        for interval in intervals:
            if not isinstance(interval, list) or len(interval) != 2:
                raise DomainError("Malformed power interval")
            start, end = map(number, interval)
            if (start < domain["start_min_s"] or end > domain["end_max_s"]
                    or end - start < domain["min_duration_s"] - TOL):
                raise DomainError("Power interval outside legal domain")
    return design


def _rail(time_s: float, energy: float, capacitance: float, event: str) -> dict:
    return {"time_s": time_s, "energy_uj": round(energy, 10),
            "voltage_v": round(math.sqrt(2 * max(0.0, energy) / capacitance), 10),
            "event": event}


def analytic_clamp(pair: dict, world: dict, design: dict) -> dict:
    """Closed-form ideal energy buffer with a voltage-dependent energy cap."""
    t = pair["task"]
    c = design["capacitance_uf"]
    upper = 0.5 * c * world["clamp_v"] ** 2
    floor = 0.5 * c * t["min_v"] ** 2
    incoming = t["source_power_uw"] * t["source_end_s"]
    before = min(upper, t["initial_energy_uj"] + incoming)
    available = max(0.0, before - floor)
    supplied = min(t["service_energy_uj"], available)
    passed = supplied + TOL >= t["service_energy_uj"]
    final = before - supplied
    trace = [
        _rail(0.0, t["initial_energy_uj"], c, "initial"),
        _rail(t["source_end_s"], before, c, "harvest-ended"),
        _rail(t["consume_at_s"], before, c, "before-service"),
        _rail(t["consume_at_s"], final, c, "after-service"),
        _rail(t["horizon_s"], final, c, "end"),
    ]
    return {"verdict": "PASS" if passed else "FAIL", "delivered_count": int(passed),
            "trace": trace, "input_energy_uj": incoming,
            "spill_energy_uj": max(0.0, t["initial_energy_uj"] + incoming - upper),
            "delivered_energy_uj": supplied, "final_energy_uj": final,
            "service_margin_uj": before - floor - t["service_energy_uj"]}


def numeric_clamp(pair: dict, world: dict, design: dict, step_s: float = 0.001) -> dict:
    """Projected time integration, with exact event boundaries; no analytic call."""
    step_s = number(step_s)
    if step_s <= 0 or step_s > 0.05:
        raise DomainError("Unsupported numerical step")
    t = pair["task"]
    cap = design["capacitance_uf"]
    ceiling = cap * world["clamp_v"] * world["clamp_v"] / 2
    reserve = cap * t["min_v"] * t["min_v"] / 2
    energy = t["initial_energy_uj"]
    now = 0.0
    incoming = spill = served = 0.0
    steps = 0
    trace = [_rail(0.0, energy, cap, "initial")]
    for target, event in [(t["source_end_s"], "harvest-ended"),
                          (t["consume_at_s"], "before-service"),
                          (t["horizon_s"], "end")]:
        while now < target - 1e-12:
            dt = min(step_s, target - now)
            gain = t["source_power_uw"] * max(0.0, min(now + dt, t["source_end_s"]) - now)
            incoming += gain
            overflow = max(0.0, energy + gain - ceiling)
            spill += overflow
            energy = energy + gain - overflow
            now += dt
            steps += 1
        trace.append(_rail(target, energy, cap, event))
        if event == "before-service":
            request = t["service_energy_uj"]
            # Consume small packets until either service completes or UVLO reserve is reached.
            while request > 1e-10 and energy > reserve + 1e-10:
                packet = min(0.01, request, energy - reserve)
                energy -= packet
                served += packet
                request -= packet
                steps += 1
            trace.append(_rail(target, energy, cap, "after-service"))
    passed = served >= t["service_energy_uj"] - TOL
    return {"verdict": "PASS" if passed else "FAIL", "delivered_count": int(passed),
            "trace": trace, "input_energy_uj": incoming, "spill_energy_uj": spill,
            "delivered_energy_uj": served, "final_energy_uj": energy,
            "service_margin_uj": incoming + t["initial_energy_uj"] - spill - reserve - t["service_energy_uj"],
            "steps": steps, "step_s": step_s}


def event_memory(pair: dict, world: dict, design: dict) -> dict:
    """Ordered event machine; pending memory is part of world, schedule is D."""
    t = pair["task"]
    events = [(t["event_at_s"], "capture"), (t["tx_at_s"], "send")]
    for start, end in design["power_off_intervals"]:
        events.extend([(start, "down"), (end, "up")])
    events.append((t["horizon_s"], "end"))
    powered = True
    pending = None
    received: list[str] = []
    trace = [{"time_s": 0.0, "event": "initial", "powered": True,
              "pending": None, "received": []}]
    for at, action in sorted(events):
        if action == "capture" and powered:
            pending = t["event_id"]
        elif action == "down":
            powered = False
            if not world["retains_pending"]:
                pending = None
        elif action == "up":
            powered = True
        elif action == "send" and powered and pending is not None and at <= t["deadline_s"]:
            received.append(pending)
            pending = None
        trace.append({"time_s": at, "event": action, "powered": powered,
                      "pending": pending, "received": list(received)})
    passed = received == [t["event_id"]] and t["delivery_goal"] == 1
    return {"verdict": "PASS" if passed else "FAIL", "delivered_count": len(received),
            "received": received, "trace": trace}


def event_program(pair: dict, design: dict) -> str:
    t = pair["task"]
    rows = [(t["event_at_s"], "EVENT " + t["event_id"]),
            (t["tx_at_s"], "TX"), (t["horizon_s"], "STOP")]
    for start, end in design["power_off_intervals"]:
        rows.extend([(start, "OFF"), (end, "ON")])
    return "\n".join(f"{at:.8f} {op}" for at, op in sorted(rows)) + "\n"


def numeric_memory(pair: dict, world: dict, design: dict, step_s: float = 0.001) -> dict:
    """Independent public event-program parser and tick-based interpreter."""
    step_s = number(step_s)
    if step_s <= 0 or step_s > 0.05:
        raise DomainError("Unsupported numerical step")
    parsed = []
    for line in event_program(pair, design).splitlines():
        match = re.fullmatch(r"([0-9]+\.[0-9]+) (EVENT [a-z0-9-]+|OFF|ON|TX|STOP)", line)
        if not match:
            raise DomainError("Malformed event program")
        parsed.append((float(match[1]), match[2]))
    on = 1
    memory: list[str] = []
    rx: list[str] = []
    cursor = 0
    trace = [{"time_s": 0.0, "event": "initial", "powered": True,
              "pending": None, "received": []}]
    names = {"OFF": "down", "ON": "up", "TX": "send", "STOP": "end"}
    steps = math.ceil(pair["task"]["horizon_s"] / step_s)
    for tick in range(steps + 1):
        now = tick * step_s
        while cursor < len(parsed) and parsed[cursor][0] <= now + 1e-10:
            at, instruction = parsed[cursor]
            cursor += 1
            if instruction.startswith("EVENT"):
                if on:
                    memory = [instruction.split()[1]]
                label = "capture"
            else:
                label = names[instruction]
                if instruction == "OFF":
                    on = 0
                    if world["retains_pending"] is False:
                        memory.clear()
                elif instruction == "ON":
                    on = 1
                elif instruction == "TX" and on and at <= pair["task"]["deadline_s"]:
                    rx.extend(memory)
                    memory.clear()
            trace.append({"time_s": at, "event": label, "powered": bool(on),
                          "pending": memory[0] if memory else None, "received": list(rx)})
    if cursor != len(parsed):
        raise DomainError("Program exceeds horizon")
    goal = [pair["task"]["event_id"]]
    return {"verdict": "PASS" if rx == goal else "FAIL", "delivered_count": len(rx),
            "received": rx, "trace": trace, "steps": steps, "step_s": step_s}


def evaluate(pair: dict, world: dict, design: dict, reference: bool = False,
             step_s: float = 0.001) -> dict:
    if world["kind"] == "clamp":
        return numeric_clamp(pair, world, design, step_s) if reference else analytic_clamp(pair, world, design)
    return numeric_memory(pair, world, design, step_s) if reference else event_memory(pair, world, design)


def check_agreement(primary: dict, reference: dict) -> float:
    if primary["verdict"] != reference["verdict"] or primary["delivered_count"] != reference["delivered_count"]:
        raise AuditError("Reference verdict disagreement")
    maximum = 0.0
    for key in ["input_energy_uj", "spill_energy_uj", "delivered_energy_uj",
                "final_energy_uj", "service_margin_uj"]:
        if key in primary:
            error = abs(primary[key] - reference[key])
            maximum = max(maximum, error)
            if error > TOL:
                raise AuditError("Reference energy disagreement: " + key)
    for left, right in zip(primary["trace"], reference["trace"], strict=True):
        if left.keys() != right.keys():
            raise AuditError("Reference trace schema disagreement")
        for key in left:
            if key in {"energy_uj", "voltage_v"}:
                if abs(left[key] - right[key]) > TOL:
                    raise AuditError("Reference rail disagreement")
            elif left[key] != right[key]:
                raise AuditError("Reference event disagreement")
    return maximum


def current_facts(pair: dict, current: dict) -> dict:
    return {"kind": pair["worlds"][0]["kind"], **copy.deepcopy(pair["task"]),
            **copy.deepcopy(pair["design"]), "legal_domain": copy.deepcopy(pair["legal_domain"]),
            "proposed_change": copy.deepcopy(pair["patch"]),
            "current_verdict": current["verdict"], "current_delivered_count": current["delivered_count"],
            "current_trace": copy.deepcopy(current["trace"])}


def sufficient_facts(pair: dict, world: dict, current: dict) -> dict:
    facts = current_facts(pair, current)
    key = "clamp_v" if world["kind"] == "clamp" else "retains_pending"
    facts[key] = world[key]
    return facts


def judge_facts(facts: dict) -> str:
    """Pure fixed-information decision; abstain instead of inventing a missing law."""
    if "proposed_verdict" in facts:
        return facts["proposed_verdict"]
    if facts["kind"] == "clamp":
        if "clamp_v" not in facts:
            return "UNKNOWN"
        capacitance = facts["proposed_change"].get("capacitance_uf", facts["capacitance_uf"])
        stored = min(facts["initial_energy_uj"] + facts["source_power_uw"] * facts["source_end_s"],
                     capacitance * facts["clamp_v"] ** 2 / 2)
        need = facts["service_energy_uj"] + capacitance * facts["min_v"] ** 2 / 2
        return "PASS" if stored >= need - TOL else "FAIL"
    if "retains_pending" not in facts:
        return "UNKNOWN"
    intervals = facts["proposed_change"].get("power_off_intervals", facts["power_off_intervals"])
    reset = any(facts["event_at_s"] < start < facts["tx_at_s"] for start, _ in intervals)
    passed = (facts["retains_pending"] or not reset) and facts["tx_at_s"] <= facts["deadline_s"]
    return "PASS" if passed else "FAIL"


def format_packet(facts: dict, summary: str, form: str) -> bytes:
    if form == "structured":
        return canonical({"schema_version": "campaign-equal-information-v1",
                          "facts": facts, "summary": summary}) + b"\n"
    if form != "free-text":
        raise DomainError("Unknown representation format")
    # Constrained prose serialization: no additional explanations or derived facts.
    lines = ["The shared summary is " + json.dumps(summary, ensure_ascii=False) + "."]
    for key, value in sorted(facts.items()):
        lines.append("The fact " + key + " has value " + json.dumps(value, ensure_ascii=False, allow_nan=False) + ".")
    return ("\n".join(lines) + "\n").encode()


def parse_packet(raw: bytes, form: str) -> tuple[dict, str]:
    if form == "structured":
        value = json.loads(raw)
        if value.get("schema_version") != "campaign-equal-information-v1":
            raise AuditError("Unknown packet schema")
        return value["facts"], value["summary"]
    if form != "free-text":
        raise DomainError("Unknown representation format")
    lines = raw.decode().splitlines()
    first = re.fullmatch(r"The shared summary is (.*)\.", lines[0])
    if not first:
        raise AuditError("Malformed prose summary")
    summary = json.loads(first[1])
    facts = {}
    for line in lines[1:]:
        match = re.fullmatch(r"The fact ([a-z][a-z0-9_]*) has value (.*)\.", line)
        if not match or match[1] in facts:
            raise AuditError("Malformed or duplicate prose fact")
        facts[match[1]] = json.loads(match[2])
    return facts, summary


def static_additive(control: dict, service_cost: float) -> str:
    service_cost = number(service_cost)
    if not control["legal_service_cost_uj"][0] <= service_cost <= control["legal_service_cost_uj"][1]:
        raise DomainError("Additive design cost outside legal interval")
    return "PASS" if control["initial_energy_uj"] + control["input_energy_uj"] >= service_cost else "FAIL"


def numeric_additive(control: dict, service_cost: float) -> str:
    # Independent packet accounting, with neither saturation nor state loss.
    balance = control["initial_energy_uj"]
    for _ in range(400):
        balance += control["input_energy_uj"] / 400
    remaining = service_cost
    while remaining > 1e-9 and balance > 1e-9:
        spent = min(0.1, remaining, balance)
        balance -= spent
        remaining -= spent
    return "PASS" if remaining < 1e-7 else "FAIL"


def observation_sources(root: Path, pair: dict, world: dict, current: dict) -> dict:
    """Export honest compact and complete inputs, without future outcome labels."""
    root.mkdir(parents=True, exist_ok=True)
    base = current_facts(pair, current)
    rich = sufficient_facts(pair, world, current)
    key = "clamp_v" if world["kind"] == "clamp" else "retains_pending"
    values = {
        "current": {"facts": base},
        "mechanism": {key: world[key]},
        "rich": {"facts": rich},
        "raw": {"pair": pair, "world": world, "current": current,
                "law": ("dE/dt=P until E=C*Vclamp^2/2; service stops at C*Vmin^2/2"
                        if world["kind"] == "clamp" else
                        "pending captured when on; reset clears volatile pending; TX consumes pending"),
                "evidence_type": "ideal-model-definition; not calibrated or measured"},
    }
    for name, value in values.items():
        write_json(root / (name + ".json"), value)
    operations = {}
    for op, source, coverage, executions in [
        ("uninformative", "current", [], 0),
        ("mechanism-spec", "mechanism", [key], 0),
        ("fixed-rich", "rich", [key], 0),
        ("full-raw", "raw", [key], 0),
        ("executable-dynamic", "raw", ["proposed_verdict"], 1),
    ]:
        path = root / (source + ".json")
        operations[op] = {"operation": op, "source": str(path.resolve()),
                          "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size,
                          "coverage": coverage, "declared_model_runs": executions,
                          "origin": "developer-defined legal observation"}
    return operations


def select_observation(catalog: dict, kind: str, byte_budget: int) -> dict:
    """Outcome-blind scripted set coverage; required facts are researcher supplied."""
    started = time.perf_counter_ns()
    needed = "clamp_v" if kind == "clamp" else "retains_pending"
    eligible = [item for item in catalog.values()
                if (needed in item["coverage"] or "proposed_verdict" in item["coverage"])
                and item["bytes"] <= byte_budget]
    ordered = sorted(eligible, key=lambda item: (item["bytes"], item["declared_model_runs"], item["operation"]))
    return {"operation": ordered[0]["operation"] if ordered else None,
            "status": "SELECTED" if ordered else "BUDGET_EXHAUSTED",
            "selector_wall_ns": time.perf_counter_ns() - started,
            "estimated_payload_bytes": ordered[0]["bytes"] if ordered else 0,
            "budget_bytes": byte_budget,
            "policy_origin": "researcher-supplied required fields; finite catalogue selection"}


def acquire_observation(item: dict, base: dict, byte_budget: int) -> dict:
    started = time.perf_counter_ns()
    if item["bytes"] > byte_budget:
        return {"schema_version": "campaign-observation-audit-v1", "status": "BUDGET_EXHAUSTED",
                "operation": item["operation"], "read_bytes": 0, "model_runs": 0,
                "solver_steps": 0, "wall_ns": time.perf_counter_ns() - started,
                "facts": copy.deepcopy(base), "origin": item["origin"]}
    raw = Path(item["source"]).read_bytes()
    if len(raw) != item["bytes"] or digest(raw) != item["sha256"]:
        raise AuditError("Observation source hash/byte binding failed")
    value = json.loads(raw)
    facts = copy.deepcopy(base)
    runs = steps = 0
    operation = item["operation"]
    if operation == "mechanism-spec":
        facts.update(value)
    elif operation in {"fixed-rich", "uninformative"}:
        facts.update(value["facts"])
    elif operation == "full-raw":
        facts.update(sufficient_facts(value["pair"], value["world"], value["current"]))
    elif operation == "executable-dynamic":
        design = changed_design(value["pair"], value["pair"]["patch"])
        response = evaluate(value["pair"], value["world"], design, reference=True)
        facts["proposed_verdict"] = response["verdict"]
        facts["proposed_delivered_count"] = response["delivered_count"]
        runs, steps = 1, response["steps"]
    else:
        raise DomainError("Observation not in public catalogue")
    return {"schema_version": "campaign-observation-audit-v1", "status": "OBSERVED",
            "operation": operation, "source": item["source"], "source_sha256": digest(raw),
            "read_bytes": len(raw), "model_runs": runs, "solver_steps": steps,
            "wall_ns": time.perf_counter_ns() - started, "facts": facts,
            "facts_sha256": digest(canonical(facts)), "origin": item["origin"],
            "cache_rule": "empty per-arm application cache; OS file cache uncontrolled",
            "cost_boundary": "Python payload bytes returned, host wall time, actual executions; not money or physical I/O blocks"}


def verify_observation_audit(receipt: dict) -> None:
    if receipt["status"] != "OBSERVED":
        if receipt["read_bytes"] or receipt["model_runs"]:
            raise AuditError("Budget rejection consumed an undeclared observation")
        return
    raw = Path(receipt["source"]).read_bytes()
    if digest(raw) != receipt["source_sha256"] or len(raw) != receipt["read_bytes"]:
        raise AuditError("Observation audit source mismatch")
    if digest(canonical(receipt["facts"])) != receipt["facts_sha256"]:
        raise AuditError("Observation audit facts mismatch")
    if receipt["model_runs"] != int(receipt["operation"] == "executable-dynamic"):
        raise AuditError("Observation execution count mismatch")


EXPRESSION_FIELDS = frozenset({"initial_energy_uj", "source_power_uw", "source_end_s",
                               "capacitance_uf", "clamp_v", "min_v", "service_energy_uj"})


def _field(name: str) -> dict:
    return {"op": "field", "name": name}


def _expr(op: str, *args: dict) -> dict:
    return {"op": op, "args": list(args)}


def headroom_expression() -> dict:
    """Human-specified physical relation; this builder is not an Agent discovery."""
    half = {"op": "constant", "value": 0.5}
    energy = _expr("add", _field("initial_energy_uj"),
                   _expr("mul", _field("source_power_uw"), _field("source_end_s")))
    ceiling = _expr("mul", half, _expr("mul", _field("capacitance_uf"), _expr("square", _field("clamp_v"))))
    reserve = _expr("mul", half, _expr("mul", _field("capacitance_uf"), _expr("square", _field("min_v"))))
    return _expr("sub", _expr("sub", _expr("min", energy, ceiling), reserve), _field("service_energy_uj"))


def render_expression(node: dict, depth: int = 0) -> str:
    if depth > 20 or not isinstance(node, dict):
        raise DomainError("Expression nesting outside construction domain")
    op = node.get("op")
    if op == "field" and set(node) == {"op", "name"}:
        if node["name"] not in EXPRESSION_FIELDS:
            raise DomainError("Unapproved observation input")
        return "facts[" + repr(node["name"]) + "]"
    if op == "constant" and set(node) == {"op", "value"}:
        return repr(number(node["value"]))
    if set(node) != {"op", "args"} or not isinstance(node.get("args"), list):
        raise DomainError("Malformed observation expression")
    args = [render_expression(a, depth + 1) for a in node["args"]]
    if op == "square" and len(args) == 1:
        return "(" + args[0] + " ** 2)"
    if op == "min" and len(args) == 2:
        return "min(" + ", ".join(args) + ")"
    if op in {"add", "sub", "mul"} and len(args) == 2:
        return "(" + args[0] + {"add": " + ", "sub": " - ", "mul": " * "}[op] + args[1] + ")"
    raise DomainError("Unapproved observation operation or arity")


def construct_observation(output: Path, pair: dict) -> dict:
    """Compile a new audited executable and independently qualify its domain grid."""
    start = time.perf_counter_ns()
    expression = headroom_expression()
    source = ("import json\nimport sys\n\ndef observe(facts):\n    return " + render_expression(expression) +
              "\n\nif __name__ == '__main__':\n    with open(sys.argv[1]) as stream:\n        facts = json.load(stream)\n"
              "    print(json.dumps({'energy_headroom_uj': observe(facts)}))\n")
    output.mkdir(parents=True, exist_ok=True)
    program = output / "generated_headroom.py"
    with program.open("x") as out:
        out.write(source)
    definition = {"schema_version": "campaign-observation-expression-v1", "expression": expression,
                  "inputs": sorted(EXPRESSION_FIELDS), "output_unit": "uJ",
                  "program_sha256": digest(program.read_bytes()),
                  "origin": "researcher-specified relation, deterministic compiler; no Agent invention",
                  "domain": pair["legal_domain"], "model_assumptions": "ideal clamp; no leakage; all input precedes service"}
    write_json(output / "definition.json", definition)
    construction_wall = time.perf_counter_ns() - start
    environment: dict[str, Any] = {}
    exec(compile("def observe(facts):\n    return " + render_expression(expression),
                 "<validated-observation-expression>", "exec"), {"__builtins__": {"min": min}}, environment)
    observe = environment["observe"]
    validation_start = time.perf_counter_ns()
    rows = []
    steps = 0
    for world in pair["worlds"]:
        for cap in pair["static_grid_capacitance_uf"]:
            design = changed_design(pair, {"capacitance_uf": cap})
            inputs = {**pair["task"], **design, "clamp_v": world["clamp_v"]}
            value = observe(inputs)
            reference = numeric_clamp(pair, world, design)
            steps += reference["steps"]
            verdict = "PASS" if value >= -TOL else "FAIL"
            if verdict != reference["verdict"] or abs(value - reference["service_margin_uj"]) > TOL:
                raise AuditError("Generated observation disagrees with independent integration")
            rows.append({"world": world["name"], "capacitance_uf": cap,
                         "value_uj": value, "reference_margin_uj": reference["service_margin_uj"],
                         "verdict": verdict, "reference_verdict": reference["verdict"]})
    validation_wall = time.perf_counter_ns() - validation_start
    executions = []
    for world in pair["worlds"]:
        design = changed_design(pair, pair["patch"])
        inputs = {**pair["task"], **design, "clamp_v": world["clamp_v"]}
        infile = output / (world["name"] + "-inputs.json")
        write_json(infile, inputs)
        at = time.perf_counter_ns()
        run = subprocess.run([sys.executable, str(program.resolve()), str(infile.resolve())],
                             cwd=str(output.resolve()), text=True, capture_output=True, timeout=10, check=True)
        elapsed = time.perf_counter_ns() - at
        result = json.loads(run.stdout)
        if abs(result["energy_headroom_uj"] - observe(inputs)) > TOL:
            raise AuditError("Fresh-process executable observation mismatch")
        executions.append({"world": world["name"], "result": result, "wall_ns": elapsed,
                           "input_bytes": infile.stat().st_size, "input_sha256": digest(infile.read_bytes()),
                           "program_sha256": digest(program.read_bytes()), "process_executions": 1})
    result = {"status": "PASS", "definition": definition, "construction_wall_ns": construction_wall,
              "qualification_wall_ns": validation_wall, "qualification_model_runs": len(rows),
              "qualification_solver_steps": steps, "qualification_rows": rows,
              "fresh_process_executions": executions,
              "human_intervention": "equation and relevant inputs supplied by researcher; not autonomously discovered"}
    write_json(output / "qualification.json", result)
    return result


def _domain_designs(pair: dict) -> list[dict]:
    if pair["worlds"][0]["kind"] == "clamp":
        return [changed_design(pair, {"capacitance_uf": c}) for c in pair["static_grid_capacitance_uf"]]
    return [changed_design(pair, {"power_off_intervals": intervals})
            for intervals in pair["static_grid_intervals"]]


def _source_bindings(project: Path, protocol_path: Path) -> dict:
    names = [Path(__file__), project / "scripts/campaign_interfaces.py",
             project / "tests/agentlab/test_campaign_interfaces.py", protocol_path]
    return {str(p.resolve().relative_to(project.resolve())): {"sha256": digest(p.read_bytes()),
                                                            "bytes": p.stat().st_size}
            for p in names}


def run_suite(protocol_path: Path, output: Path) -> dict:
    started = time.perf_counter_ns()
    protocol_bytes = protocol_path.read_bytes()
    protocol = load_protocol(protocol_path)
    project = Path(__file__).resolve().parents[7]
    output = output.resolve()
    runtime = Path(protocol["runtime_root"]).resolve()
    if not output.is_relative_to(runtime) or output == runtime:
        raise DomainError("New execution directory must be inside the B runtime root")
    if shutil.disk_usage(runtime.parent if runtime.parent.exists() else Path.home()).free < protocol["cost_cap"]["stop_free_bytes"]:
        raise DomainError("Less than 5 GB free; stop before creating a run")
    sources = _source_bindings(project, protocol_path)
    run_id = "IF-" + digest(canonical({"protocol": digest(protocol_bytes), "sources": sources}))[:20]
    output.mkdir(parents=True, exist_ok=False)
    (output / "protocol.json").write_bytes(protocol_bytes)
    write_json(output / "start.json", {"run_id": run_id, "protocol_sha256": digest(protocol_bytes),
                                       "source_bindings": sources, "baseline": BASELINE,
                                       "partition": "public-development", "paid_model_requests": 0,
                                       "native_dispatches": 0})
    references = []
    pairs = []
    packets = []
    observations = []
    exports = []
    static_rows = []
    max_error = 0.0
    reference_runs = 0
    reference_steps = 0
    primary_runs = 0

    def deadline() -> None:
        if (time.perf_counter_ns() - started) / 1e9 > protocol["cost_cap"]["runner_wall_s"]:
            raise DomainError("Finite execution wall-clock cap exhausted")

    for pair in protocol["pairs"]:
        deadline()
        design = changed_design(pair, {})
        modified = changed_design(pair, pair["patch"])
        cases = []
        for world in pair["worlds"]:
            primary = evaluate(pair, world, design)
            intervention = evaluate(pair, world, modified)
            primary_runs += 2
            for phase, d, expected in [("current", design, primary), ("intervention", modified, intervention)]:
                for step in pair["numeric_steps_s"]:
                    reference = evaluate(pair, world, d, reference=True, step_s=step)
                    error = check_agreement(expected, reference)
                    max_error = max(max_error, error)
                    reference_runs += 1
                    reference_steps += reference["steps"]
                    references.append({"pair": pair["id"], "world": world["name"], "phase": phase,
                                       "primary": expected, "reference": reference, "max_error_uj": error})
            base = current_facts(pair, primary)
            case = {"world": world["name"], "current": primary, "intervention": intervention,
                    "current_representation": base, "current_representation_sha256": digest(canonical(base))}
            cases.append(case)
            for level, facts in [("current", base), ("sufficient", sufficient_facts(pair, world, primary))]:
                summary = "The current task passes. The proposed design change is public and legal."
                parsed = []
                for form in ["free-text", "structured"]:
                    raw = format_packet(facts, summary, form)
                    suffix = ".txt" if form == "free-text" else ".json"
                    path = output / "packets" / pair["id"] / world["name"] / (level + "-" + form + suffix)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("xb") as stream:
                        stream.write(raw)
                    restored, restored_summary = parse_packet(path.read_bytes(), form)
                    if canonical(restored) != canonical(facts) or restored_summary != summary:
                        raise AuditError("Equal-information packet roundtrip failed")
                    parsed.append((restored, restored_summary))
                    prediction = judge_facts(restored)
                    packets.append({"pair": pair["id"], "world": world["name"], "information": level,
                                    "format": form, "file": str(path.relative_to(output)), "bytes": len(raw),
                                    "facts_sha256": digest(canonical(restored)), "summary_sha256": digest(canonical(restored_summary)),
                                    "current_verdict": restored["current_verdict"], "prediction": prediction,
                                    "reference_verdict": intervention["verdict"],
                                    "correct": prediction == intervention["verdict"],
                                    "consumer": "deterministic preparation only; Agent format effect NOT_RUN"})
                if canonical(parsed[0]) != canonical(parsed[1]):
                    raise AuditError("Formats contain different facts or summary")
            before_export = time.perf_counter_ns()
            catalog = observation_sources(output / "observation-inputs" / pair["id"] / world["name"], pair, world, primary)
            exports.append({"pair": pair["id"], "world": world["name"],
                            "export_wall_ns": time.perf_counter_ns() - before_export,
                            "unique_source_bytes": sum(p.stat().st_size for p in
                                                       (output / "observation-inputs" / pair["id"] / world["name"]).glob("*.json")),
                            "catalogue": catalog})
            for operation in list(catalog) + ["selected"]:
                deadline()
                selection = select_observation(catalog, world["kind"], 1_000_000) if operation == "selected" else None
                chosen = selection["operation"] if selection else operation
                receipt = acquire_observation(catalog[chosen], base, 1_000_000)
                audit_start = time.perf_counter_ns()
                verify_observation_audit(receipt)
                receipt["audit_wall_ns"] = time.perf_counter_ns() - audit_start
                receipt["audit_read_bytes"] = receipt["read_bytes"]
                prediction = judge_facts(receipt["facts"])
                observations.append({"pair": pair["id"], "world": world["name"], "arm": operation,
                                     "selection": selection, "receipt": receipt, "prediction": prediction,
                                     "reference_verdict": intervention["verdict"],
                                     "correct": prediction == intervention["verdict"]})
            # Static sufficient model checked on an exposed, finite legal grid.
            for trial_design in _domain_designs(pair):
                reference = evaluate(pair, world, trial_design, reference=True)
                reference_runs += 1
                reference_steps += reference["steps"]
                facts = sufficient_facts(pair, world, primary)
                facts["proposed_change"] = trial_design
                prediction = judge_facts(facts)
                if prediction != reference["verdict"]:
                    raise AuditError("Sufficient-static negative control failed")
                static_rows.append({"pair": pair["id"], "world": world["name"], "design": trial_design,
                                    "prediction": prediction, "reference_verdict": reference["verdict"]})
        if any(c["current"]["verdict"] != "PASS" for c in cases):
            raise AuditError("A current task fails; not the registered witness")
        if cases[0]["current_representation_sha256"] != cases[1]["current_representation_sha256"]:
            raise AuditError("Current representations are distinguishable")
        if cases[0]["intervention"]["verdict"] == cases[1]["intervention"]["verdict"]:
            raise AuditError("No intervention divergence")
        pairs.append({"pair": pair["id"], "mechanism": pair["mechanism"], "task": pair["task"],
                      "design": design, "shared_patch": pair["patch"], "modified_design": modified,
                      "legal_domain": pair["legal_domain"], "jointly_legal": True,
                      "current_same": True, "current_both_pass": True, "intervention_diverges": True,
                      "cases": cases})

    control = protocol["negative_control"]
    additive_rows = []
    for service_cost in [10.0, 30.0, 40.0, 45.0, 50.0]:
        primary = static_additive(control, service_cost)
        independent = numeric_additive(control, service_cost)
        if primary != independent:
            raise AuditError("Additive static-sufficiency control failed")
        additive_rows.append({"service_cost_uj": service_cost, "static": primary, "reference": independent})
    controls = {"additive_static_sufficient": True, "enriched_static_sufficient": True,
                "uninformative_returns_unknown": all(row["prediction"] == "UNKNOWN" for row in observations if row["arm"] == "uninformative")}
    illegal = []
    for pair, patch in [(protocol["pairs"][0], {"capacitance_uf": 0}),
                        (protocol["pairs"][1], {"power_off_intervals": [[0, 4]]}),
                        (protocol["pairs"][0], {"service_energy_uj": 1})]:
        try:
            changed_design(pair, patch)
        except DomainError as exc:
            illegal.append({"patch": patch, "rejected": True, "reason": str(exc)})
        else:
            raise AuditError("Illegal change accepted")
    controls["illegal_patches_rejected"] = len(illegal) == 3
    example = exports[0]["catalogue"]["mechanism-spec"]
    bad = output / "negative-controls" / "tampered-source.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(Path(example["source"]).read_bytes() + b"tampered")
    try:
        acquire_observation({**example, "source": str(bad)}, pairs[0]["cases"][0]["current_representation"], 1_000_000)
    except AuditError:
        controls["tampered_hash_rejected"] = True
    else:
        raise AuditError("Tampered source was accepted")
    exhausted = select_observation(exports[0]["catalogue"], "clamp", 0)
    controls["exhausted_budget_abstains"] = exhausted["operation"] is None
    if not all(controls.values()):
        raise AuditError("Negative control failed")
    construction = construct_observation(output / "construction", protocol["pairs"][0])
    deadline()
    observation_summary = []
    for arm in ["uninformative", "mechanism-spec", "fixed-rich", "full-raw", "executable-dynamic", "selected"]:
        subset = [r for r in observations if r["arm"] == arm]
        observation_summary.append({"arm": arm, "cases": len(subset),
                                    "correct": sum(r["correct"] for r in subset),
                                    "unknown": sum(r["prediction"] == "UNKNOWN" for r in subset),
                                    "read_bytes": sum(r["receipt"]["read_bytes"] for r in subset),
                                    "audit_read_bytes": sum(r["receipt"]["audit_read_bytes"] for r in subset),
                                    "observation_wall_ns": sum(r["receipt"]["wall_ns"] for r in subset),
                                    "audit_wall_ns": sum(r["receipt"]["audit_wall_ns"] for r in subset),
                                    "selector_wall_ns": sum((r["selection"] or {}).get("selector_wall_ns", 0) for r in subset),
                                    "model_runs": sum(r["receipt"]["model_runs"] for r in subset),
                                    "solver_steps": sum(r["receipt"]["solver_steps"] for r in subset)})
    result = {"schema_version": RESULT_SCHEMA, "run_id": run_id, "status": "PASS",
              "baseline": BASELINE, "protocol_sha256": digest(protocol_bytes), "source_bindings": sources,
              "partition": "public-development", "pairs": pairs, "reference_checks": references,
              "reference_max_error_uj": max_error, "packets": packets,
              "e4_status": "equal-information export/parser/decision prepared; Agent format effect NOT_RUN",
              "e3_boundary": "Ablating one unexcited mechanism parameter restores aliasing in this encoding; no universal field necessity or device-level E3 claim",
              "static_sufficient_rows": static_rows, "additive_static_rows": additive_rows,
              "static_sufficiency_argument": "In this no-leak, all-input-before-service domain, min(E0+Pin*t,C*Vclamp^2/2)-C*Vmin^2/2 is exactly usable energy. In the reset domain, retention OR absence of reset between capture and TX determines delivery. Additive control needs only total energy.",
              "observation_exports": exports, "observations": observations,
              "observation_summary": observation_summary, "construction": construction,
              "negative_controls": controls, "illegal_patch_controls": illegal,
              "budget_control": exhausted,
              "costs": {"primary_model_runs": primary_runs, "reference_model_runs": reference_runs,
                        "reference_solver_steps": reference_steps,
                        "observation_model_runs": sum(r["receipt"]["model_runs"] for r in observations),
                        "construction_qualification_model_runs": construction["qualification_model_runs"],
                        "construction_fresh_process_executions": len(construction["fresh_process_executions"]),
                        "paid_model_requests": 0, "native_dispatches": 0,
                        "runner_wall_ns": time.perf_counter_ns() - started,
                        "claim": "host measurements, not monetary costs; all new development computations retained"},
              "claim_boundary": protocol["claim_boundary"], "historical_runs_reexecuted": 0,
              "human_provenance": protocol["construction"]["origin"]}
    if _source_bindings(project, protocol_path) != sources:
        raise AuditError("Source inputs changed during execution")
    write_json(output / "result.json", result)
    files = {str(p.relative_to(output)): {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
             for p in sorted(output.rglob("*")) if p.is_file()}
    total_bytes = sum(v["bytes"] for v in files.values())
    if total_bytes > protocol["cost_cap"]["output_bytes"]:
        raise DomainError("Output byte cap exceeded")
    write_json(output / "seal.json", {"schema_version": "campaign-interface-seal-v1", "run_id": run_id,
                                     "files": files, "total_payload_bytes": total_bytes,
                                     "result_sha256": digest((output / "result.json").read_bytes())})
    verify_run(output)
    return result


def verify_run(output: Path) -> dict:
    """Read-only artifact validation; no new simulation, provider or native dispatch."""
    output = output.resolve()
    seal = json.loads((output / "seal.json").read_bytes())
    for name, binding in seal["files"].items():
        path = output / name
        if not path.resolve().is_relative_to(output) or path.is_symlink():
            raise AuditError("Unsafe sealed artifact path")
        raw = path.read_bytes()
        if digest(raw) != binding["sha256"] or len(raw) != binding["bytes"]:
            raise AuditError("Sealed artifact mismatch: " + name)
    result = json.loads((output / "result.json").read_bytes())
    if result["run_id"] != seal["run_id"] or result["status"] != "PASS":
        raise AuditError("Result identity mismatch")
    if digest((output / "protocol.json").read_bytes()) != result["protocol_sha256"]:
        raise AuditError("Protocol binding mismatch")
    for pair in result["pairs"]:
        if canonical(pair["cases"][0]["current_representation"]) != canonical(pair["cases"][1]["current_representation"]):
            raise AuditError("Aliasing witness changed")
        if not all(pair[key] for key in ["jointly_legal", "current_same", "current_both_pass", "intervention_diverges"]):
            raise AuditError("Witness gate failed")
    for row in result["reference_checks"]:
        check_agreement(row["primary"], row["reference"])
    for row in result["packets"]:
        facts, summary = parse_packet((output / row["file"]).read_bytes(), row["format"])
        if digest(canonical(facts)) != row["facts_sha256"] or digest(canonical(summary)) != row["summary_sha256"]:
            raise AuditError("Equal-information binding changed")
        if judge_facts(facts) != row["prediction"]:
            raise AuditError("Deterministic decision changed")
    # Relocate source bindings for a copied capsule; original run paths stay historical metadata.
    for row in result["observations"]:
        receipt = copy.deepcopy(row["receipt"])
        if receipt["status"] == "OBSERVED":
            old = Path(receipt["source"])
            pieces = old.parts
            try:
                idx = pieces.index("observation-inputs")
            except ValueError as exc:
                raise AuditError("Unknown observation source scope") from exc
            receipt["source"] = str(output.joinpath(*pieces[idx:]))
        verify_observation_audit(receipt)
    if not all(result["negative_controls"].values()):
        raise AuditError("Negative control receipt failed")
    return {"status": "PASS", "run_id": result["run_id"], "sealed_files": len(seal["files"]),
            "payload_bytes": seal["total_payload_bytes"], "new_model_runs": 0,
            "paid_model_requests": 0, "native_dispatches": 0}
