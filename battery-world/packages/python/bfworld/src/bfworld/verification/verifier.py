"""Independent RunBundle verification using only public bundle artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bfworld.bundle.format import scientific_hash, summarize_rows
from bfworld.bundle.reader import RunBundleReader
from bfworld.contracts.validation import validate_document
from bfworld.kernel.canonical import canonical_hash, file_hash
from bfworld.runtime.journal import HashJournal, JournalError


class VerificationError(RuntimeError):
    pass


def _inventory(root: Path, excluded: set[str]) -> list[dict[str, Any]]:
    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        records.append({"path": relative, "sha256": file_hash(path), "bytes": path.stat().st_size})
    return records


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def verify_bundle(root: Path) -> dict[str, Any]:
    required = {
        "world.ir.json",
        "run-manifest.json",
        "events.jsonl",
        "channels.parquet",
        "evidence.json",
        "views.json",
        "replay.html",
        "runtime-audit.jsonl",
        "bundle-seal.json",
    }
    actual_names = {path.name for path in root.iterdir() if path.is_file()}
    _require(required <= actual_names, f"bundle missing files: {sorted(required - actual_names)}")

    reader = RunBundleReader(root)
    manifest = reader.manifest
    world = reader.json("world.ir.json")
    evidence = reader.evidence
    views = reader.views
    seal = reader.json("bundle-seal.json")
    validate_document("world.schema.json", world)
    validate_document("run-manifest.schema.json", manifest)
    validate_document("evidence.schema.json", evidence)
    validate_document("views.schema.json", views)

    unsigned_world = dict(world)
    claimed_world_hash = unsigned_world.pop("canonical_hash")
    _require(canonical_hash(unsigned_world) == claimed_world_hash, "world IR canonical hash mismatch")
    _require(manifest["world_hash"] == claimed_world_hash, "manifest world hash mismatch")

    try:
        journal = HashJournal(root / "events.jsonl", manifest["run_id"])
        events = journal.read()
    except JournalError as exc:
        raise VerificationError(str(exc)) from exc
    for event in events:
        validate_document("event.schema.json", event)
    _require(journal.head == manifest["event_head"], "manifest event head mismatch")
    event_types = [event["type"] for event in events]
    _require("constraint_violated" in event_types, "baseline failure event missing")
    _require("design_revision_applied" in event_types, "design revision event missing")
    _require("higher_fidelity_validation_passed" in event_types, "fine validation event missing")
    _require(event_types[-1] == "run_completed", "run does not end in completion")
    try:
        audit = HashJournal(
            root / "runtime-audit.jsonl",
            manifest["run_id"],
            hash_field="audit_hash",
        ).read()
    except JournalError as exc:
        raise VerificationError(f"runtime audit: {exc}") from exc
    recovery_count = sum(1 for record in audit if record["type"] == "process_recovered")
    _require(recovery_count == manifest["recovery_count"], "runtime recovery count mismatch")

    rows = reader.channels()
    mission = world["mission"]
    revised_design_id = mission["revision"]["design"]["design_id"]
    recomputed = summarize_rows(
        rows,
        world["requirements"],
        {
            "baseline": mission["baseline_design"]["design_id"],
            "revised": revised_design_id,
            "fine_validation": revised_design_id,
        },
    )
    _require(recomputed == manifest["phases"], "phase summaries do not match channels")
    _require(not recomputed["baseline"]["passed"], "baseline unexpectedly passes")
    _require(recomputed["baseline"]["overvoltage_count"] > 0, "baseline overvoltage absent")
    _require(recomputed["revised"]["passed"], "revised design does not pass")
    _require(recomputed["fine_validation"]["passed"], "fine validation does not pass")
    peak_delta = abs(
        recomputed["fine_validation"]["peak_voltage_v"]
        - recomputed["revised"]["peak_voltage_v"]
    )
    _require(
        peak_delta <= float(world["requirements"]["max_fine_coarse_peak_delta_v"]),
        "coarse/fine convergence exceeds tolerance",
    )

    result_hash = scientific_hash(claimed_world_hash, journal.head or "", recomputed)
    _require(result_hash == manifest["scientific_hash"], "scientific hash mismatch")
    _require(evidence["run_id"] == manifest["run_id"], "evidence run mismatch")
    _require(evidence["hardware_result"] is False, "A cannot claim hardware evidence")
    _require(all(claim["verdict"] is True for claim in evidence["claims"]), "evidence claim failed")
    for relative, expected in evidence["artifact_bindings"].items():
        _require(file_hash(root / relative) == expected, f"evidence binding mismatch: {relative}")
    _require(views["run_id"] == manifest["run_id"], "views run mismatch")
    _require(views["event_head"] == manifest["event_head"], "views event head mismatch")

    replay = (root / "replay.html").read_text(encoding="utf-8")
    _require(manifest["run_id"] in replay, "replay does not bind run identity")
    _require(manifest["event_head"] in replay, "replay does not bind event head")
    _require(manifest["scientific_hash"] in replay, "replay does not bind scientific hash")

    pre_manifest = _inventory(root, {"run-manifest.json", "bundle-seal.json"})
    _require(pre_manifest == manifest["inventory"], "manifest inventory mismatch")
    sealed_inventory = _inventory(root, {"bundle-seal.json"})
    _require(sealed_inventory == seal["files"], "bundle seal inventory mismatch")
    bundle_hash = canonical_hash(
        {"schema_version": "bfworld-bundle-inventory-v1", "files": sealed_inventory}
    )
    _require(bundle_hash == seal["bundle_hash"], "bundle hash mismatch")
    _require(seal["run_id"] == manifest["run_id"], "bundle seal run mismatch")

    return {
        "schema_version": "bfworld-verification-report-v1",
        "status": "passed",
        "run_id": manifest["run_id"],
        "event_head": manifest["event_head"],
        "scientific_hash": result_hash,
        "bundle_hash": bundle_hash,
        "baseline_overvoltage_observed": True,
        "revision_passed": True,
        "fine_validation_passed": True,
        "hardware_result": False,
        "model_calls": 0,
    }
