"""Prepare a bounded source/result publication without running any experiment.

Run from the original Long-Horizon AI Agent repository. This inventories only
the selected research evidence and hashes the bytes that would be published.
It never creates a source/worktree copy, executes a provider, or edits a run.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import signal

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/github-publication-20261109"
RESEARCH = ROOT / "docs/research/pqe-two-paper-plan-20261022"
SOURCE = ROOT / "workbench/bf-campaign-s0-20261019"
PACKAGES = ("relation-synthesis-20261102", "joint-closure-20261102")
BASE = "962ab20c7b41653c412f1932d57886a05bdabc72"
BRANCH = "codex/bf-pqe-results-20261109"
BAD_NAMES = {".DS_Store", ".env", ".env.local", "operator.token", "launch-url.txt"}
BAD_PARTS = {"__pycache__", ".git", "node_modules", ".venv", "secrets"}
SECRET_PATTERNS = {
    "github_token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9_]{20,}"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "bearer_credential": re.compile(rb'(?i)["\x27]authorization["\x27]\s*:\s*["\x27]Bearer\s+[^"\x27\s]{16,}'),
    "api_credential": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}"),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def allowed(path: Path) -> bool:
    return (path.is_file() and not path.is_symlink()
            and path.name not in BAD_NAMES and not BAD_PARTS.intersection(path.parts)
            and path.suffix not in {".sqlite", ".sqlite3", ".db", ".key", ".pyc"})


def run() -> dict:
    selected: dict[str, Path] = {}
    excluded: list[dict] = []

    def add(path: Path, destination: str | None = None) -> None:
        if not allowed(path):
            return
        if destination is None:
            destination = path.relative_to(ROOT).as_posix()
        old = selected.setdefault(destination, path)
        if old != path:
            raise RuntimeError("PUBLICATION_PATH_COLLISION: " + destination)

    # Preserve all current-result bytes, including original failures/corrections.
    for package in PACKAGES:
        for path in (RESEARCH / package).rglob("*"):
            add(path)
    for path in RESEARCH.iterdir():
        if path.is_file():
            add(path)

    # Earlier conclusions and reused executable research code stay inspectable.
    # Older large model/consumer payloads remain local rather than being repacked.
    for path in RESEARCH.rglob("*"):
        if not path.is_file() or path.relative_to(RESEARCH).parts[0] in PACKAGES:
            continue
        if path.suffix == ".py" or path.name in {
            "REPORT.md", "FINAL-INDEX.md", "HANDOFF.json", "PREREGISTRATION.md",
            "final-readback.json", "final-service-readback.json",
            "final-method-cost-readback.json", "completion.json", "MANIFEST.json",
        }:
            add(path)

    frozen_checks = []
    amendment = json.loads((RESEARCH / "joint-closure-20261102/s0/source-amendment.json").read_text())
    for package in PACKAGES:
        protocol = json.loads((RESEARCH / package / "shared/protocol.json").read_text())
        for name, expected in protocol.get("source_hashes", {}).items():
            path = Path(name)
            if not path.is_file():
                raise RuntimeError("FROZEN_SOURCE_MISSING: " + name)
            actual = sha(path.read_bytes())
            documented_amendment = (package == "relation-synthesis-20261102"
                                    and name == amendment["path"]
                                    and expected == amendment["prior_sha256"]
                                    and actual == amendment["current_sha256"])
            frozen_checks.append({"package": package, "path": name, "sha256": actual,
                                  "expected_sha256": expected, "matches": actual == expected,
                                  "documented_later_accounting_amendment": documented_amendment})
            if actual != expected and not documented_amendment:
                raise RuntimeError("FROZEN_SOURCE_CHANGED: " + name)
            if path.is_relative_to(SOURCE):
                add(path, path.relative_to(SOURCE).as_posix())
            elif path.is_relative_to(RESEARCH):
                add(path)
            else:
                excluded.append({"path": name, "sha256": actual,
                                 "reason": "Installed third-party SDK/build entry; original source/package identity retained, not newly vendored."})

    # Include the changed PQE implementation and its direct package interfaces.
    agentlab = SOURCE / "battery-world/packages/python/bfworld/src/bfworld/agentlab"
    for name in ("pqe20261022", "pqe20261023bold", "pqe20261024debt", "pqe20261024lc"):
        for path in (agentlab / name).rglob("*.py"):
            add(path, path.relative_to(SOURCE).as_posix())
    for pattern in ("test*pqe*.py", "test*debt*.py"):
        for path in (SOURCE / "battery-world/packages/python/bfworld/tests").rglob(pattern):
            add(path, path.relative_to(SOURCE).as_posix())

    for path in OUT.iterdir():
        if path.is_file() and path.name in {"README.md", "prepare_publication.py", "verify_archive.py"}:
            add(path)

    findings = []
    unavailable = []
    records = []

    def read_timeout(_signum, _frame):
        raise TimeoutError("PUBLICATION_READ_TIMEOUT")

    signal.signal(signal.SIGALRM, read_timeout)
    for dest, path in sorted(selected.items()):
        if path.stat().st_flags & 0x40000000:
            unavailable.append({"path": dest, "local_path": str(path),
                                "bytes": path.stat().st_size, "reason": "Cloud placeholder not resident at publication; not uploaded or deleted."})
            continue
        try:
            signal.alarm(5)
            raw = path.read_bytes()
        except (TimeoutError, OSError) as exc:
            unavailable.append({"path": dest, "local_path": str(path),
                                "bytes": path.stat().st_size, "reason": type(exc).__name__ + ": bounded local read unavailable; original retained."})
            continue
        finally:
            signal.alarm(0)
        decoded = gzip.decompress(raw) if path.suffix == ".gz" else raw
        for category, pattern in SECRET_PATTERNS.items():
            if pattern.search(decoded):
                findings.append({"path": dest, "category": category})
        if path.suffix in {".json", ".jsonl", ".gz"}:
            try:
                text = decoded.decode("utf-8")
                objs = [json.loads(line) for line in text.splitlines() if line] if path.name.endswith((".jsonl", ".jsonl.gz")) else [json.loads(text)]
            except (UnicodeDecodeError, ValueError):
                objs = []

            def walk(value, trail=""):
                if isinstance(value, dict):
                    for key, item in value.items():
                        if key.lower() in {"token", "api_key", "apikey", "access_token", "refresh_token", "client_secret", "password", "owner_token", "operator_token"} and isinstance(item, str) and len(item) >= 16 and not any(ch.isspace() for ch in item):
                            if item.lower() not in {"redacted", "<redacted>"}:
                                findings.append({"path": dest, "category": "credential_field", "field": trail + "." + key})
                        walk(item, trail + "." + key)
                elif isinstance(value, list):
                    for item in value:
                        walk(item, trail + "[]")
            for obj in objs:
                walk(obj)
        records.append({"path": dest, "local_path": str(path), "bytes": len(raw),
                        "sha256": sha(raw), "mode": "100755" if os.access(path, os.X_OK) and path.suffix in {".py", ".sh"} else "100644"})

    disk = os.statvfs(ROOT)
    free = disk.f_bavail * disk.f_frsize
    receipt = {
        "schema": "bf-pqe-github-publication-v1", "status": "READY" if not findings else "CREDENTIAL_REVIEW_REQUIRED",
        "repository": "littleandbrother/agent", "branch": BRANCH, "parent_commit": BASE,
        "authorization": "Direct human: 把现在的结果推送到github上",
        "scope": "Current joint-closure package in full, resident prior relation-synthesis results, current coordination/analysis documents, older compact reports and reused source code, exact frozen consumer/adapter dependencies. Unavailable cloud files individually listed.",
        "claim_boundary": "Latest joint-closure matched comparison remains BLOCKED_COMMON_CALCULATOR_INTERFACE; no method superiority, non-value, hidden-test or hardware inference.",
        "new_model_requests": 0, "new_scientific_evaluations": 0,
        "available_bytes": free, "estimated_peak_additional_bytes": 1000000000,
        "retained_publication_metadata_cap_bytes": 10000000,
        "source_copy_or_new_worktree": False, "base_working_tree_or_index_modified": False,
        "selected_file_count": len(records), "selected_bytes": sum(r["bytes"] for r in records),
        "largest_file_bytes": max(r["bytes"] for r in records),
        "frozen_checks": frozen_checks, "secret_findings": findings,
        "unavailable_files": unavailable,
        "excluded_external_dependencies": excluded, "files": records,
        "not_uploaded": ["Provider credential/database stores", "Installed environments and node_modules", "Historical large raw payloads outside the two current packages", "Unrelated dirty worktree changes and old worktree copies"],
    }
    if free < 11000000000:
        raise RuntimeError("PUBLICATION_STORAGE_BELOW_10GB_PLUS_PEAK")
    (OUT / "publication-manifest.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    if any("/joint-closure-20261102/" in x["path"] for x in unavailable):
        raise RuntimeError("LATEST_PACKAGE_INCOMPLETE: see publication-manifest.json")
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"files", "frozen_checks"}}, ensure_ascii=False, indent=2))
    return receipt


if __name__ == "__main__":
    result = run()
    if result["secret_findings"]:
        raise SystemExit(2)
