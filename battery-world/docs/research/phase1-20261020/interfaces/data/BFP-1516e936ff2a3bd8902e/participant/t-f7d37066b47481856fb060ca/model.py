"""Ideal public model; computational prediction, not independent qualification."""
from __future__ import annotations
import copy, json, math, re, sys
from typing import Any
TOL = 1e-7

class DomainError(ValueError):
    """A proposed design or expression is outside the frozen public domain."""

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

def predict(raw, patch):
    pair, world = raw["pair"], raw["world"]
    design = changed_design(pair, patch)
    fn = numeric_clamp if world["kind"] == "clamp" else numeric_memory
    return fn(pair, world, design, 0.001)

if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as src:
        raw = json.load(src)
    patch = json.loads(sys.argv[2]) if len(sys.argv) > 2 else raw["pair"]["patch"]
    print(json.dumps(predict(raw, patch), sort_keys=True, allow_nan=False))
