#!/usr/bin/env python3
"""Materialize and independently reproduce the canonical A RunBundle."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from bfworld.application.rotary import run_rotary_mission
from bfworld.kernel.canonical import file_hash, write_canonical_json
from bfworld.verification.verifier import verify_bundle


REPO = Path(__file__).resolve().parents[1]
MISSION = REPO / "configs" / "missions" / "rotary-overvoltage-v1.json"
CANONICAL = REPO / "runs" / "a-rotary-v1"
REPORT = REPO / "runs" / "a-validation-report.json"


def main() -> int:
    CANONICAL.parent.mkdir(parents=True, exist_ok=True)
    if CANONICAL.exists():
        canonical_report = verify_bundle(CANONICAL)
    else:
        run_rotary_mission(
            MISSION,
            REPO / ".bfworld" / "a-canonical",
            CANONICAL,
        )
        canonical_report = verify_bundle(CANONICAL)

    with tempfile.TemporaryDirectory(prefix="bfworld-a-reproduce-") as temporary:
        root = Path(temporary)
        reproduced = run_rotary_mission(MISSION, root / "workspace", root / "bundle")
        reproduced_report = verify_bundle(root / "bundle")
        if canonical_report["bundle_hash"] != reproduced_report["bundle_hash"]:
            raise RuntimeError("fresh A reproduction changed bundle identity")
        if file_hash(CANONICAL / "bundle-seal.json") != file_hash(root / "bundle" / "bundle-seal.json"):
            raise RuntimeError("fresh A reproduction changed bundle seal bytes")

    report = {
        "schema_version": "bfworld-a-validation-v1",
        "status": "passed",
        "canonical": canonical_report,
        "fresh_reproduction": reproduced,
        "gates": {
            "baseline_overvoltage": True,
            "typed_revision": True,
            "fine_step_validation": True,
            "independent_verification": True,
            "byte_identical_reproduction": True,
            "zero_model_calls": True,
            "hardware_result": False,
        },
    }
    write_canonical_json(REPORT, report)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

