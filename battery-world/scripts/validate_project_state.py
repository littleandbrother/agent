#!/usr/bin/env python3
"""Validate the evidence-gated research roadmap and current progress state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[1]
EXPECTED_MILESTONES = ["A1", "A2", "B1", "B2", "C1", "C2"]
ALLOWED_MILESTONE_STATES = {"ready", "in-progress", "blocked", "complete"}
REQUIRED_NEXT_FEATURE_FIELDS = {
    "objective",
    "owned_paths",
    "hypothesis",
    "falsifier",
    "tests",
    "negative_controls",
    "exit_gates",
    "command",
    "artifacts",
    "cost_cap",
    "claim_boundary",
    "stop_condition",
    "handoff",
    "limitations",
}


class ProjectStateError(RuntimeError):
    """The roadmap, feature registry, or evidence anchors disagree."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProjectStateError(message)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_repository_state(repo: Path = REPO) -> dict[str, Any]:
    features = {}
    for path in sorted((repo / "project" / "features").glob("*/feature.yaml")):
        feature = _read_yaml(path)
        feature["_path"] = str(path.relative_to(repo))
        features[feature["id"]] = feature
    return {
        "project": _read_yaml(repo / "PROJECT.yaml"),
        "roadmap": _read_yaml(repo / "project" / "ROADMAP.yaml"),
        "features": features,
        "a_report": _read_json(repo / "runs" / "a-validation-report.json"),
        "b0_manifest": _read_json(repo / "fixtures" / "golden-episodes" / "manifest.json"),
        "progress_text": (repo / "docs" / "PROGRESS.md").read_text(encoding="utf-8"),
    }


def validate_loaded(state: dict[str, Any]) -> dict[str, Any]:
    project = state["project"]
    roadmap = state["roadmap"]
    features = state["features"]
    a_report = state["a_report"]
    b0_manifest = state["b0_manifest"]
    progress_text = state["progress_text"]

    _require(project["product"] == roadmap["program"]["product"], "product identity disagrees")
    _require(project["method"] == roadmap["program"]["method"], "method identity disagrees")
    _require(
        project["central_scientific_question"] == roadmap["program"]["central_scientific_question"],
        "central scientific question disagrees",
    )
    _require(project["authorities"]["research_roadmap"] == "project/ROADMAP.yaml", "roadmap authority changed")

    active_feature = project.get("active_feature")
    in_progress = sorted(feature_id for feature_id, feature in features.items() if feature["status"] == "in-progress")
    if active_feature is None:
        _require(not in_progress, "in-progress feature exists while PROJECT has no active feature")
    else:
        _require(active_feature in features, "active feature is missing from registry")
        _require(features[active_feature]["status"] == "in-progress", "active feature is not in progress")
        _require(in_progress == [active_feature], "multiple in-progress features exist")

    milestones = roadmap["milestones"]
    milestone_ids = [milestone["id"] for milestone in milestones]
    _require(milestone_ids == EXPECTED_MILESTONES, "milestone sequence or identity changed")
    _require(len(milestone_ids) == len(set(milestone_ids)), "duplicate milestone identifier")
    by_milestone = {milestone["id"]: milestone for milestone in milestones}
    completed = []
    for milestone in milestones:
        status = milestone["status"]
        _require(status in ALLOWED_MILESTONE_STATES, f"invalid milestone status: {milestone['id']}")
        gate_states = [gate["status"] for gate in milestone["exit_gates"]]
        if status == "complete":
            _require(gate_states and all(value == "passed" for value in gate_states), f"{milestone['id']} completed with open gate")
            _require(bool(milestone.get("evidence")), f"{milestone['id']} completed without evidence")
            completed.append(milestone["id"])
        if status == "blocked":
            blockers = milestone.get("blocked_by", [])
            _require(bool(blockers), f"{milestone['id']} blocked without dependency")
            _require(all(blocker in by_milestone for blocker in blockers), f"{milestone['id']} has unknown blocker")
            _require(any(by_milestone[blocker]["status"] != "complete" for blocker in blockers), f"{milestone['id']} remains blocked after dependencies passed")
    _require(completed == roadmap["current"]["research_milestones_completed"], "completed milestone projection is stale")

    completed_foundations = roadmap["current"]["foundation_features_completed"]
    _require(len(completed_foundations) == len(set(completed_foundations)), "duplicate completed foundation")
    for feature_id in completed_foundations:
        _require(feature_id in features, f"completed foundation missing: {feature_id}")
        _require(features[feature_id]["status"] == "complete", f"foundation is not complete: {feature_id}")
        _require(bool(features[feature_id].get("evidence")), f"foundation lacks evidence: {feature_id}")

    next_feature_id = roadmap["current"]["next_feature"]
    _require(project["next_milestone"] == next_feature_id, "PROJECT next milestone disagrees with roadmap")
    _require(next_feature_id in features, "next feature missing from registry")
    next_feature = features[next_feature_id]
    _require(next_feature["status"] in {"ready", "in-progress"}, "next feature is not actionable")
    _require(REQUIRED_NEXT_FEATURE_FIELDS <= next_feature.keys(), "next feature contract is incomplete")
    _require(bool(next_feature["exit_gates"]), "next feature lacks exit gates")
    _require(next_feature["hypothesis"] and next_feature["falsifier"], "next feature is not falsifiable")

    a_anchor = roadmap["evidence_anchors"]["A-001"]["bundle_hash"]
    actual_a = a_report["canonical"]["bundle_hash"]
    _require(a_anchor == actual_a, "A-001 roadmap evidence identity is stale")
    b0_anchor = roadmap["evidence_anchors"]["B0-000"]["manifest_hash"]
    actual_b0 = b0_manifest["content_hash"]
    _require(b0_anchor == actual_b0, "B0-000 roadmap evidence identity is stale")

    _require(actual_a in progress_text, "progress view omits A-001 identity")
    _require(actual_b0 in progress_text, "progress view omits B0-000 identity")
    _require(f"{len(completed)} / {len(milestones)}" in progress_text, "progress view milestone count is stale")
    if 'B2' not in completed:
        _require("No executable knowledge object" in progress_text, "progress view hides the knowledge gap")
    _require(roadmap["progress_policy"]["manual_percent_complete_forbidden"] is True, "manual progress percentage enabled")
    _require(roadmap["knowledge_lifecycle"]["self_promotion_allowed"] is False, "knowledge self-promotion enabled")

    return {
        "schema_version": "battery-world-project-state-validation-v1",
        "status": "passed",
        "product": project["product"],
        "method": project["method"],
        "foundation_features_complete": len(completed_foundations),
        "research_milestones_complete": len(completed),
        "research_milestones_total": len(milestones),
        "next_feature": next_feature_id,
        "a001_bundle_hash": actual_a,
        "b0_manifest_hash": actual_b0,
        "active_feature": active_feature,
    }


def validate_repository(repo: Path = REPO) -> dict[str, Any]:
    return validate_loaded(read_repository_state(repo))


def main() -> int:
    print(json.dumps(validate_repository(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
