"""F1-simplified load-dependent Rotary-TENG world model."""

from __future__ import annotations

import copy
import math
from typing import Any

from bfworld.kernel.canonical import canonical_hash


PROVIDER = {
    "id": "rotary-teng-norton-f1-v1",
    "version": "1.0.0",
    "fidelity": "F1-simplified",
    "terminal_voltage_dependent": True,
    "hardware_result": False,
    "equations": [
        "i_norton = I_peak * abs(sin(2*pi*f*t))",
        "i_harvest = max(0, i_norton - v_terminal/R_internal)",
        "dv/dt = (i_harvest - i_load - i_leak - i_shunt)/C",
    ],
}


def compile_world_ir(mission: dict[str, Any]) -> dict[str, Any]:
    semantic_mission = copy.deepcopy(mission)
    world = {
        "schema_version": "bfworld-ir-v1",
        "world_id": "rotary-teng-world-v1",
        "mission": semantic_mission,
        "provider": copy.deepcopy(PROVIDER),
        "requirements": copy.deepcopy(mission["requirements"]),
    }
    world["canonical_hash"] = canonical_hash(world)
    return world


def _rounded(value: float) -> float:
    return round(float(value), 12)


def simulate_phase(
    mission: dict[str, Any],
    design: dict[str, Any],
    phase: str,
    dt_s: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    duration_s = float(mission["duration_s"])
    environment = mission["environment"]
    source = mission["source"]
    storage = mission["storage"]
    load = mission["load"]

    frequency_hz = float(environment["rpm"]) / 60.0 * int(environment["pole_pairs"])
    capacitance_f = float(storage["capacitance_f"])
    voltage_v = float(storage["initial_voltage_v"])
    minimum_v = float(storage["min_operating_voltage_v"])
    maximum_v = float(storage["max_safe_voltage_v"])
    clamp_v = design.get("clamp_voltage_v")
    shunt_ohm = design.get("shunt_resistance_ohm")
    inference_starts = [float(value) for value in load["inference_times_s"]]
    completed: set[int] = set()
    rows: list[dict[str, Any]] = []

    steps = int(round(duration_s / dt_s)) + 1
    for step in range(steps):
        time_s = step * dt_s
        active_indices = [
            index
            for index, start in enumerate(inference_starts)
            if start <= time_s < start + float(load["inference_duration_s"])
        ]
        inference_active = bool(active_indices)
        source_current_a = float(source["peak_current_a"]) * abs(
            math.sin(2.0 * math.pi * frequency_hz * time_s)
        )
        harvest_current_a = max(
            0.0,
            source_current_a - voltage_v / float(source["internal_resistance_ohm"]),
        )
        load_current_a = float(load["idle_current_a"])
        if inference_active:
            load_current_a += float(load["inference_current_a"])
            for index in active_indices:
                if voltage_v >= minimum_v:
                    completed.add(index)
        leak_current_a = voltage_v / float(source["leak_resistance_ohm"])
        shunt_current_a = 0.0
        if clamp_v is not None and shunt_ohm is not None and voltage_v > float(clamp_v):
            shunt_current_a = (voltage_v - float(clamp_v)) / float(shunt_ohm)

        brownout = voltage_v < minimum_v
        overvoltage = voltage_v > maximum_v
        rows.append(
            {
                "phase": phase,
                "step": step,
                "time_s": _rounded(time_s),
                "rpm": _rounded(float(environment["rpm"])),
                "source_current_a": _rounded(source_current_a),
                "harvest_current_a": _rounded(harvest_current_a),
                "load_current_a": _rounded(load_current_a),
                "leak_current_a": _rounded(leak_current_a),
                "shunt_current_a": _rounded(shunt_current_a),
                "capacitor_voltage_v": _rounded(voltage_v),
                "storage_energy_j": _rounded(0.5 * capacitance_f * voltage_v * voltage_v),
                "inference_active": inference_active,
                "brownout": brownout,
                "overvoltage": overvoltage,
            }
        )

        if step < steps - 1:
            net_current_a = harvest_current_a - load_current_a - leak_current_a - shunt_current_a
            voltage_v = max(0.0, voltage_v + net_current_a * dt_s / capacitance_f)

    peak_v = max(row["capacitor_voltage_v"] for row in rows)
    minimum_observed_v = min(row["capacitor_voltage_v"] for row in rows)
    overvoltage_count = sum(1 for row in rows if row["overvoltage"])
    brownout_count = sum(1 for row in rows if row["brownout"])
    completed_count = len(completed)
    required_count = int(mission["requirements"]["required_inferences"])
    passed = (
        overvoltage_count == 0
        and brownout_count == 0
        and completed_count >= required_count
    )
    summary = {
        "phase": phase,
        "design_id": design["design_id"],
        "dt_s": _rounded(dt_s),
        "row_count": len(rows),
        "peak_voltage_v": _rounded(peak_v),
        "minimum_voltage_v": _rounded(minimum_observed_v),
        "overvoltage_count": overvoltage_count,
        "brownout_count": brownout_count,
        "completed_inferences": completed_count,
        "required_inferences": required_count,
        "passed": passed,
    }
    return rows, summary

