"""Studio view model derived exclusively from a RunBundleReader."""

from __future__ import annotations

from bfworld.bundle.reader import RunBundleReader


def studio_snapshot(reader: RunBundleReader) -> dict[str, object]:
    manifest = reader.manifest
    return {
        "schema_version": "bfworld-studio-snapshot-v1",
        "run_id": manifest["run_id"],
        "event_head": manifest["event_head"],
        "scientific_hash": manifest["scientific_hash"],
        "views": reader.views["views"],
        "claims": reader.evidence["claims"],
    }

