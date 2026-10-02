"""Check preserved base evidence plus additive integration/axial notes."""
import hashlib
import json
from pathlib import Path
from verify_package import verify

root=Path(__file__).resolve().parent
base=verify(root)
seal=json.loads((root/'FINAL-SEAL.json').read_text())
if seal['schema']!='bf-static-rom-final-composite-seal-v1' or seal['dynamic_admitted'] is not False:
    raise ValueError('Invalid composite seal')
for row in seal['files']:
    rel=Path(row['path'])
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Invalid path in seal')
    f=(root/rel).resolve()
    if not f.is_relative_to(root) or hashlib.sha256(f.read_bytes()).hexdigest()!=row['sha256']:
        raise ValueError('Composite hash mismatch: '+str(rel))
print(json.dumps({'base_files_verified':base['files_checked'],'composite_files_verified':len(seal['files']),'new_dynamic_runs':0,'dynamic_admitted':False},indent=2))
