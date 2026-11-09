"""Verify the published file inventory; no provider/scientific execution."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("publication-manifest.json")


def verify(root: Path = ROOT) -> dict:
    manifest = json.loads(MANIFEST.read_text())
    failures = []
    for row in manifest["files"]:
        path = root / row["path"]
        if not path.is_file():
            failures.append({"path": row["path"], "error": "MISSING"})
            continue
        raw = path.read_bytes()
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            failures.append({"path": row["path"], "error": "CONTENT_MISMATCH"})
    return {"status": "PASS" if not failures else "FAIL", "files": len(manifest["files"]),
            "failures": failures, "scope": "File bytes only; no scientific/method inference."}


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
