#!/usr/bin/env python3
"""Create a relative-path, content-addressed inventory of the predecessor."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


EXCLUDED_DIRS = {
    ".git",
    ".external",
    ".tmp",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "runs",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def source_files(root: Path) -> Iterator[Path]:
    for directory, names, files in os.walk(root):
        names[:] = sorted(name for name in names if name not in EXCLUDED_DIRS)
        base = Path(directory)
        for name in sorted(files):
            path = base / name
            if path.is_file() and not path.is_symlink():
                yield path


def classify(relative: str) -> str:
    if relative.startswith("experiments/snapshots/"):
        return "sealed-evidence"
    if relative.startswith("experiments/preregistrations/"):
        return "protocol"
    if relative.startswith("paper/"):
        return "paper"
    if relative.startswith("legacy/"):
        return "deprecated"
    if relative.startswith("lhsai/science/") or relative.startswith("lhsai/worlds/"):
        return "domain-provider"
    if relative.startswith("lhsai/runtime/") or relative.startswith("lhsai/kernel/"):
        return "runtime-source"
    if relative.startswith("tests/"):
        return "test"
    return "repository-source"


def git_output(root: Path, arguments: list[str]) -> dict[str, object]:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired:
        return {"returncode": None, "stdout": "", "stderr": "timed out after 15 seconds"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    manifest_path = output / "source-manifest.jsonl"
    hashes_path = output / "file-hashes.sha256"
    count = 0
    total_bytes = 0
    manifest_hash = hashlib.sha256()
    with manifest_path.open("wb") as manifest, hashes_path.open("w", encoding="utf-8", newline="\n") as hashes:
        for path in source_files(source):
            relative = path.relative_to(source).as_posix()
            size = path.stat().st_size
            sha = digest(path)
            record = {
                "path": relative,
                "bytes": size,
                "sha256": "sha256:" + sha,
                "category": classify(relative),
            }
            line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            manifest.write(line)
            manifest_hash.update(line)
            hashes.write(f"{sha}  {relative}\n")
            count += 1
            total_bytes += size

    runs_path = output / "run-inventory.csv"
    with runs_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["relative_path", "bytes"])
        runs_root = source / "runs"
        if runs_root.exists():
            for path in sorted(item for item in runs_root.rglob("*") if item.is_file() and not item.is_symlink()):
                writer.writerow([path.relative_to(source).as_posix(), path.stat().st_size])

    migration_rows = [
        ["lhsai/science/teng/", "domain-provider", "bfworld.worlds.rotary", "reimplement-and-parity"],
        ["lhsai/apps/dsh_bridge.py", "harness-adapter", "future dsh-bfworld", "reference-only-until-B"],
        ["lhsai/plugins/epidesign.py", "mixed", "future verification/evolution", "split-after-A"],
        ["experiments/snapshots/", "sealed-evidence", "predecessor only", "never-move"],
        ["paper/", "paper", "future research repository", "reference-only"],
    ]
    with (output / "migration-map.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["legacy_path", "category", "target", "decision"])
        writer.writerows(migration_rows)

    git_head = git_output(source, ["rev-parse", "HEAD"])
    git_state = git_output(source, ["status", "--porcelain=v1", "--untracked-files=all"])
    (output / "git-head.json").write_text(json.dumps(git_head, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (output / "git-state.json").write_text(json.dumps(git_state, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    dependencies = {}
    for name in ("jsonschema", "pyarrow", "PyYAML"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = None
    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": dependencies,
    }
    (output / "environment.json").write_text(json.dumps(environment, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    test_status = {
        "command": "./init.sh",
        "observed_before_freeze": "2026-09-04",
        "tests": 1145,
        "failures": 4,
        "errors": 4,
        "skipped": 4,
        "status": "failed",
        "known_causes": [
            "V11 protected inventory differs from immutable lock",
            "M55 implementation byte drift",
            "phase/state preflight assertions including existing snapshot state",
        ],
    }
    (output / "test-status.json").write_text(json.dumps(test_status, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    freeze = {
        "schema_version": "bfworld-legacy-freeze-v1",
        "source_label": "Long-Horizon-AI-Agent-predecessor",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": count,
        "total_bytes": total_bytes,
        "source_manifest_sha256": "sha256:" + manifest_hash.hexdigest(),
        "git_head": git_head,
        "git_state_auditable": git_state["returncode"] == 0,
        "known_test_status": test_status,
        "claim": "content inventory of a known-red predecessor; not a healthy-repository claim",
    }
    (output / "FREEZE.json").write_text(json.dumps(freeze, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(freeze, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

