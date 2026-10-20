"""Import an idle worker's owned files with baseline/conflict/hash checks.

No environment, runtime, history archive or whole checkout is copied. APFS
clones are independent inodes. A receipt preserves the imported identities.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[4]
PLAN = ROOT / "docs/research/phase-plan-20261019"
DEST = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("worker", choices=["a", "b"])
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--previous", type=Path, help="Prior reviewed import, for a bounded owner update")
    args = parser.parse_args()
    if args.receipt.exists():
        raise FileExistsError("IMMUTABLE_RECEIPT_EXISTS")
    free = shutil.disk_usage(ROOT).free
    if free < 10_900_000_000:
        raise RuntimeError("WHOLE_PHASE_STORAGE_RESERVE")
    source = ROOT / f"workbench/bf-campaign-{args.worker}-20261019/battery-world"
    manifest = json.loads((PLAN / "phase1/baseline-v2/manifest.json").read_text())
    baseline = {row["path"]: row for row in manifest["entries"]}
    previous = json.loads(args.previous.read_text()) if args.previous else None
    if previous and (previous["worker"] != args.worker or previous["baseline"] != manifest["id"] or previous["destination"] != str(DEST)):
        raise ValueError("PREVIOUS_IMPORT_IDENTITY_MISMATCH")
    ownership = json.loads((PLAN / "OWNERSHIP.json").read_text())
    owner = next(o for o in ownership["owners"] if o["owner"] == "campaign-" + args.worker)
    scopes = [x for x in owner["owned_paths"] if not Path(x).is_absolute() and not x.startswith("..")]

    def owned(relative):
        return any(relative == x.rstrip("/") or (x.endswith("/") and relative.startswith(x)) for x in scopes)

    baseline_changes = []
    checked = 0
    for relative, expected in baseline.items():
        if relative == "battery-world/PROJECT.yaml":
            continue  # Registered role overlay, never imported.
        target = source.parent / relative
        if expected["kind"] == "symlink":
            actual = hashlib.sha256(os.readlink(target).encode()).hexdigest()
            if not target.exists() or actual != expected["sha256"]:
                raise ValueError("SHARED_DEPENDENCY_LINK_DRIFT:" + relative)
            checked += 1
            continue
        if expected["kind"] != "file":
            raise ValueError("UNSUPPORTED_BASELINE_ENTRY:" + relative)
        actual = sha(target)
        checked += 1
        if actual != expected["sha256"]:
            if not relative.startswith("battery-world/") or not owned(relative[len("battery-world/"):]):
                raise ValueError("NON_OWNED_BASELINE_CHANGED:" + relative)
            baseline_changes.append(relative)

    proposed, omitted = {}, []
    for scope in scopes:
        path = source / scope
        if not path.exists():
            raise FileNotFoundError(path)
        for item in ([path] if path.is_file() else path.rglob("*")):
            if not item.is_file():
                continue
            relative = str(item.relative_to(source))
            if item.is_symlink():
                raise ValueError("WORKER_SYMLINK:" + relative)
            if "__pycache__" in item.parts or any(x.startswith("build-") for x in item.parts) or item.suffix in {".aux", ".out", ".pyc"}:
                omitted.append(relative)
                continue
            digest = sha(item)
            dest = DEST / relative
            current = sha(dest) if dest.exists() else None
            ref = baseline.get("battery-world/" + relative, {})
            prior = previous["files"].get(relative, {}).get("sha256") if previous else None
            if current not in (None, digest, ref.get("sha256"), prior):
                raise ValueError("S0_DIVERGENCE_REQUIRES_REVIEW:" + relative)
            proposed[relative] = {"sha256": digest, "bytes": item.stat().st_size, "action": "same" if current == digest else "import"}

    if sum(row["bytes"] for row in proposed.values()) > 25_000_000:
        raise RuntimeError("INTEGRATION_OUTPUT_CAP")
    for relative, row in proposed.items():
        source_file, dest = source / relative, DEST / relative
        if row["action"] == "import":
            dest.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest.with_name("." + dest.name + ".integration-tmp")
            if temporary.exists():
                raise FileExistsError(temporary)
            subprocess.run(["/bin/cp", "-c", str(source_file), str(temporary)], check=True)
            if sha(temporary) != row["sha256"] or temporary.stat().st_ino == source_file.stat().st_ino:
                temporary.unlink()
                raise ValueError("INDEPENDENT_CLONE_READBACK_FAILED")
            os.replace(temporary, dest)
        if sha(dest) != row["sha256"]:
            raise ValueError("IMPORT_READBACK_FAILED:" + relative)
    receipt = {"schema_version": "bf-phase1-worker-integration-v1", "worker": args.worker,
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "baseline": manifest["id"],
        "source": str(source), "destination": str(DEST), "checked_baseline_files": checked,
        "allowed_baseline_changes": baseline_changes, "registered_role_overlay_skipped": "battery-world/PROJECT.yaml",
        "files": proposed, "omitted_rebuildable_scratch": omitted,
        "previous_import": {"path": str(args.previous), "sha256": sha(args.previous)} if previous else None,
        "free_bytes_before": free, "free_bytes_after": shutil.disk_usage(ROOT).free,
        "paid_requests": 0, "native_dispatches": 0, "commit_or_push": False}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x") as output:
        json.dump(receipt, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"worker": args.worker, "checked_baseline_files": checked,
        "imported": sum(x["action"] == "import" for x in proposed.values()), "scoped_files": len(proposed),
        "total_scoped_bytes": sum(x["bytes"] for x in proposed.values()), "free_bytes": receipt["free_bytes_after"]}))


if __name__ == "__main__":
    main()
