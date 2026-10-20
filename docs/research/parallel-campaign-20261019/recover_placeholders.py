#!/usr/bin/env python3
"""Recover exact indexed content into a new cache, never into cloud placeholders."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
BASE = HERE / "baseline-v1"
HEAD = "317d40fef0137d3c1ad1873e53c3e9968b31200a"


def blob_hash(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def recover(row):
    cache = BASE / "recovered-blobs" / row["oid"]
    if cache.exists() and blob_hash(cache.read_bytes()) == row["oid"]:
        return {**row, "status": "PASS", "source": "exact-cache"}
    url = "https://raw.githubusercontent.com/littleandbrother/agent/" + HEAD + "/" + urllib.parse.quote(row["path"])
    errors = []
    for attempt in range(2):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = response.read(2_000_000)
            if blob_hash(data) != row["oid"]:
                raise ValueError("Git blob identity mismatch")
            cache.write_bytes(data)
            return {**row, "status": "PASS", "source": url, "attempt": attempt + 1}
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    return {**row, "status": "BLOCKED", "errors": errors}


if __name__ == "__main__":
    rows = json.loads((BASE / "placeholder-manifest.json").read_text())
    unique = {r["oid"]: r for r in rows}
    (BASE / "recovered-blobs").mkdir(exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(recover, row) for row in unique.values()]
        for f in as_completed(futures):
            results.append(f.result())
    (BASE / "placeholder-recovery.json").write_text(json.dumps(results, indent=2) + "\n")
    failed = [r for r in results if r["status"] != "PASS"]
    print(json.dumps({"unique": len(unique), "passed": len(results) - len(failed), "failed": failed}, indent=2), flush=True)
    raise SystemExit(bool(failed))
