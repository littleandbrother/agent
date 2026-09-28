"""Agent-readable A contract. No model or Agent is executed in milestone A."""

from __future__ import annotations

from bfworld.bundle.reader import RunBundleReader


def public_observation(reader: RunBundleReader) -> dict[str, object]:
    manifest = reader.manifest
    phases = manifest["phases"]
    return {
        "schema_version": "bfworld-public-observation-v1",
        "run_id": manifest["run_id"],
        "event_head": manifest["event_head"],
        "baseline_passed": phases["baseline"]["passed"],
        "revised_passed": phases["revised"]["passed"],
        "fine_validation_passed": phases["fine_validation"]["passed"],
        "claim_boundary": manifest["claim_boundary"],
    }

