"""Application composition for the Rotary-TENG vertical slice."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from bfworld.bundle.writer import write_run_bundle
from bfworld.contracts.validation import validate_document
from bfworld.kernel.canonical import canonical_hash
from bfworld.runtime.live import LiveRun
from bfworld.worlds.rotary.model import compile_world_ir, simulate_phase


class WorldFalsified(RuntimeError):
    pass


def load_mission(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        mission = json.load(handle)
    required = {
        "schema_version",
        "mission_id",
        "duration_s",
        "coarse_dt_s",
        "verification_dt_s",
        "environment",
        "source",
        "storage",
        "load",
        "baseline_design",
        "revision",
        "requirements",
    }
    missing = sorted(required - mission.keys())
    if missing:
        raise ValueError(f"mission missing fields: {missing}")
    return mission


def _run_id(mission: dict[str, Any]) -> str:
    identity = {
        "schema_version": "bfworld-run-identity-v1",
        "mission": mission,
        "runner": "rotary-world-kernel-a1",
    }
    return "run-" + canonical_hash(identity).split(":", 1)[1]


def _phase_files(phase: str) -> tuple[str, str]:
    return f"{phase}-rows.json", f"{phase}-summary.json"


def _execute_phase(
    live: LiveRun,
    mission: dict[str, Any],
    phase: str,
    design: dict[str, Any],
    dt_s: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    live.events.append(
        "phase_started",
        {"phase": phase, "design_id": design["design_id"], "dt_s": dt_s},
    )
    rows, summary = simulate_phase(mission, design, phase, dt_s)
    rows_name, summary_name = _phase_files(phase)
    live.write_artifact(rows_name, rows)
    live.write_artifact(summary_name, summary)
    live.events.append("phase_completed", summary)
    if not summary["passed"]:
        live.events.append(
            "constraint_violated",
            {
                "phase": phase,
                "overvoltage_count": summary["overvoltage_count"],
                "brownout_count": summary["brownout_count"],
            },
        )
    return rows, summary


def run_rotary_mission(
    mission_path: Path,
    workspace: Path,
    output: Path,
    *,
    resume: bool = False,
    crash_after: str | None = None,
) -> dict[str, Any]:
    mission = load_mission(mission_path)
    world_ir = compile_world_ir(mission)
    validate_document("world.schema.json", world_ir)
    run_id = _run_id(mission)
    plan = {
        "schema_version": "bfworld-run-plan-v1",
        "run_id": run_id,
        "mission": mission,
        "world_hash": world_ir["canonical_hash"],
    }
    live = LiveRun.resume(workspace, run_id, plan) if resume else LiveRun.create(workspace, run_id, plan)
    checkpoint = live.checkpoint_state()
    phase = checkpoint["phase"] if checkpoint else "new"

    if phase == "new":
        live.events.append("run_started", {"mission_id": mission["mission_id"]})
        live.events.append(
            "world_compiled",
            {"world_id": world_ir["world_id"], "world_hash": world_ir["canonical_hash"]},
        )
        live.write_artifact("world.ir.json", world_ir)
        _, baseline = _execute_phase(
            live,
            mission,
            "baseline",
            mission["baseline_design"],
            float(mission["coarse_dt_s"]),
        )
        if baseline["overvoltage_count"] <= 0:
            raise WorldFalsified("baseline did not expose the frozen overvoltage failure")
        live.checkpoint(
            "baseline_complete",
            ["world.ir.json", "baseline-rows.json", "baseline-summary.json"],
        )
        phase = "baseline_complete"
        if crash_after == "baseline":
            live.audit.append("intentional_process_death", {"after": "baseline_complete"})
            os._exit(91)

    if phase == "baseline_complete":
        live.events.append(
            "design_revision_applied",
            {
                "revision_id": mission["revision"]["revision_id"],
                "reason": mission["revision"]["reason"],
                "from_design": mission["baseline_design"]["design_id"],
                "to_design": mission["revision"]["design"]["design_id"],
            },
        )
        _, revised = _execute_phase(
            live,
            mission,
            "revised",
            mission["revision"]["design"],
            float(mission["coarse_dt_s"]),
        )
        if not revised["passed"]:
            raise WorldFalsified("revised coarse simulation did not pass")
        live.checkpoint(
            "revision_complete",
            [
                "world.ir.json",
                "baseline-rows.json",
                "baseline-summary.json",
                "revised-rows.json",
                "revised-summary.json",
            ],
        )
        phase = "revision_complete"

    if phase == "revision_complete":
        _, fine = _execute_phase(
            live,
            mission,
            "fine_validation",
            mission["revision"]["design"],
            float(mission["verification_dt_s"]),
        )
        revised = live.read_artifact("revised-summary.json")
        peak_delta = round(abs(fine["peak_voltage_v"] - revised["peak_voltage_v"]), 12)
        tolerance = float(mission["requirements"]["max_fine_coarse_peak_delta_v"])
        if not fine["passed"] or peak_delta > tolerance:
            raise WorldFalsified("fine-step validation failed or did not converge")
        convergence = {
            "coarse_peak_voltage_v": revised["peak_voltage_v"],
            "fine_peak_voltage_v": fine["peak_voltage_v"],
            "absolute_delta_v": peak_delta,
            "maximum_allowed_delta_v": tolerance,
            "passed": True,
        }
        live.write_artifact("convergence.json", convergence)
        live.events.append("higher_fidelity_validation_passed", convergence)
        live.events.append("run_completed", {"result": "verified_revision"})
        live.checkpoint(
            "scientific_complete",
            [
                "world.ir.json",
                "baseline-rows.json",
                "baseline-summary.json",
                "revised-rows.json",
                "revised-summary.json",
                "fine_validation-rows.json",
                "fine_validation-summary.json",
                "convergence.json",
            ],
        )
        phase = "scientific_complete"

    if phase != "scientific_complete":
        raise WorldFalsified(f"unsupported checkpoint phase: {phase}")
    result = write_run_bundle(live, mission, output)
    live.audit.append("bundle_materialized", {"bundle_hash": result["bundle_hash"]})
    return result
