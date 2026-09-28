"""Shared deterministic phase summaries and scientific identity."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from bfworld.kernel.canonical import canonical_hash


PHASES = ("baseline", "revised", "fine_validation")


def summarize_rows(
    rows: Iterable[dict[str, Any]],
    requirements: dict[str, Any],
    phase_design_ids: dict[str, str],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["phase"]].append(row)
    summaries: dict[str, dict[str, Any]] = {}
    for phase in PHASES:
        phase_rows = grouped[phase]
        if not phase_rows:
            raise ValueError(f"missing phase rows: {phase}")
        starts = 0
        previous_active = False
        for row in phase_rows:
            active = bool(row["inference_active"])
            if active and not previous_active and not row["brownout"]:
                starts += 1
            previous_active = active
        overvoltage_count = sum(1 for row in phase_rows if row["overvoltage"])
        brownout_count = sum(1 for row in phase_rows if row["brownout"])
        required = int(requirements["required_inferences"])
        summaries[phase] = {
            "phase": phase,
            "design_id": phase_design_ids[phase],
            "dt_s": round(float(phase_rows[1]["time_s"] - phase_rows[0]["time_s"]), 12),
            "row_count": len(phase_rows),
            "peak_voltage_v": round(max(float(row["capacitor_voltage_v"]) for row in phase_rows), 12),
            "minimum_voltage_v": round(min(float(row["capacitor_voltage_v"]) for row in phase_rows), 12),
            "overvoltage_count": overvoltage_count,
            "brownout_count": brownout_count,
            "completed_inferences": starts,
            "required_inferences": required,
            "passed": overvoltage_count == 0 and brownout_count == 0 and starts >= required,
        }
    return summaries


def scientific_hash(world_hash: str, event_head: str, phases: dict[str, Any]) -> str:
    return canonical_hash(
        {
            "schema_version": "bfworld-scientific-result-v1",
            "world_hash": world_hash,
            "event_head": event_head,
            "phases": phases,
        }
    )
