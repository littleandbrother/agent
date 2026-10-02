"""Verify an immutable static-package manifest before using this candidate."""
import hashlib
import json
from pathlib import Path

def verify(root):
    root=Path(root).resolve()
    manifest=json.loads((root/'MANIFEST.json').read_text())
    if manifest.get('schema')!='bf-static-rom-package-manifest-v1':
        raise ValueError('invalid manifest schema')
    if manifest.get('new_dynamic_runs')!=0 or manifest.get('dynamic_admitted') is not False:
        raise ValueError('incorrect static-only gate')
    for row in manifest['files']:
        rel=Path(row['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('manifest path escapes package')
        f=(root/rel).resolve()
        if not f.is_relative_to(root) or not f.is_file():
            raise ValueError('missing/unsafe manifest path: '+str(rel))
        if hashlib.sha256(f.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('hash mismatch: '+str(rel))
    return {'files_checked':len(manifest['files']),'static_package_verified':True,'native_equivalent':False,'dynamic_admitted':False}

if __name__=='__main__':
    print(json.dumps(verify(Path(__file__).resolve().parent),indent=2))
