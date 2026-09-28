"""Verify exported source bytes, without reading credentials or running models."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "release/source-manifest.json").read_text())
failures = []
for entry in manifest["files"]:
    path = (ROOT / entry["path"]).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        failures.append({"path": entry["path"], "error": "missing or outside checkout"})
        continue
    data = path.read_bytes()
    if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        failures.append({"path": entry["path"], "error": "content differs from source snapshot"})
print(json.dumps({"files": len(manifest["files"]), "ok": not failures,
                  "failures": failures}, ensure_ascii=False, indent=2))
raise SystemExit(1 if failures else 0)
