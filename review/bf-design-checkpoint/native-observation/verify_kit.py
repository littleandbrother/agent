"""Read-only member integrity verification; no simulation or dependency install."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent
manifest=json.loads((root/"FILE-MANIFEST.json").read_text())
failures=[]
for row in manifest["files"]:
    p=(root/row["path"]).resolve()
    if not p.is_relative_to(root) or not p.is_file():
        failures.append({"path":row["path"],"reason":"missing or outside root"});continue
    if p.stat().st_size!=row["bytes"] or hashlib.sha256(p.read_bytes()).hexdigest()!=row["sha256"]:
        failures.append({"path":row["path"],"reason":"size/hash mismatch"})
print(json.dumps({"sealed_files":len(manifest["files"]),"failures":failures,"native_executions":0,"runtime_ready":False,"execution_authorized":False},indent=2))
raise SystemExit(1 if failures else 0)

