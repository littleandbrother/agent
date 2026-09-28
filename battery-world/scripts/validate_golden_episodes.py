#!/usr/bin/env python3
"""Independently validate and reproduce the B0-000 semantic suite."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[1]
PYTHON_SOURCE = REPO / "packages" / "python" / "bfworld" / "src"
sys.path.insert(0, str(PYTHON_SOURCE))

from bfworld.kernel.canonical import canonical_hash, file_hash  # noqa: E402
from bfworld.semantics.golden import (  # noqa: E402
    A001_BUNDLE_HASH,
    GoldenSemanticError,
    validate_suite,
    write_golden_suite,
)
from bfworld.verification.verifier import verify_bundle  # noqa: E402


DEFAULT_SUITE = REPO / "fixtures" / "golden-episodes"
CANONICAL_A = REPO / "runs" / "a-rotary-v1"
FEATURE_RECEIPT = REPO / "project" / "features" / "B0-000-semantic-golden-episodes" / "feature.yaml"


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_directory(root: Path, *, reproduce: bool) -> dict:
    manifest_path = root / "manifest.json"
    manifest = _read_json(manifest_path)
    unsigned_manifest = dict(manifest)
    claimed_manifest_hash = unsigned_manifest.pop("content_hash", None)
    if canonical_hash(unsigned_manifest) != claimed_manifest_hash:
        raise GoldenSemanticError("golden manifest content hash mismatch")
    if manifest["a001_bundle_hash"] != A001_BUNDLE_HASH:
        raise GoldenSemanticError("golden manifest changed A-001 identity")

    actual_a = verify_bundle(CANONICAL_A)
    if actual_a["bundle_hash"] != A001_BUNDLE_HASH:
        raise GoldenSemanticError("canonical A-001 bundle identity drift")

    episodes = []
    expected_paths = []
    for entry in manifest["files"]:
        path = root / entry["path"]
        expected_paths.append(entry["path"])
        if file_hash(path) != entry["file_hash"]:
            raise GoldenSemanticError(f"golden file hash mismatch: {entry['path']}")
        episode = _read_json(path)
        if episode["content_hash"] != entry["episode_hash"]:
            raise GoldenSemanticError(f"golden episode identity mismatch: {entry['path']}")
        episodes.append(episode)
    validation = validate_suite(episodes)
    if validation != manifest["validation"]:
        raise GoldenSemanticError("stored golden validation report is not reproducible")

    rebuilt_equal = None
    if reproduce:
        with tempfile.TemporaryDirectory(prefix="bfworld-golden-rebuild-") as temporary:
            rebuilt = Path(temporary)
            write_golden_suite(rebuilt)
            for relative in ["manifest.json", *expected_paths]:
                if (root / relative).read_bytes() != (rebuilt / relative).read_bytes():
                    raise GoldenSemanticError(f"golden rebuild byte drift: {relative}")
        rebuilt_equal = True

    return {
        "schema_version": "bfworld-semantic-suite-audit-v0",
        "status": "passed",
        "manifest_hash": claimed_manifest_hash,
        "a001_bundle_hash": actual_a["bundle_hash"],
        "episode_count": len(episodes),
        "byte_identical_rebuild": rebuilt_equal,
        "validation": validation,
    }


def validate_feature_receipt(report: dict) -> None:
    with FEATURE_RECEIPT.open("r", encoding="utf-8") as handle:
        feature = yaml.safe_load(handle)
    if feature["status"] != "complete":
        raise GoldenSemanticError("B0-000 feature receipt is not complete")
    evidence = feature["evidence"]
    if evidence["manifest_hash"] != report["manifest_hash"]:
        raise GoldenSemanticError("feature receipt manifest hash is stale")
    if evidence["a001_bundle_hash"] != report["a001_bundle_hash"]:
        raise GoldenSemanticError("feature receipt A-001 identity is stale")
    actual_episode_hashes = {
        episode["episode_id"]: episode["content_hash"]
        for episode in report["validation"]["episodes"]
    }
    if evidence["episode_hashes"] != actual_episode_hashes:
        raise GoldenSemanticError("feature receipt episode identities are stale")
    if not (REPO / evidence["manual_audit"]).is_file():
        raise GoldenSemanticError("feature receipt manual audit is missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    report = validate_directory(args.root, reproduce=args.rebuild)
    if args.root.resolve() == DEFAULT_SUITE.resolve():
        validate_feature_receipt(report)
        report["feature_receipt_bound"] = True
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
