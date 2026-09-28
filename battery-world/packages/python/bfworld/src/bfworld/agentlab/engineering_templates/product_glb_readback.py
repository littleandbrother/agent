"""Fresh GLB import: verify exported mesh identities and physical dimensions."""
import json
import sys
from pathlib import Path
import bpy

root=Path(sys.argv[sys.argv.index('--')+1])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(root/'model.glb'))
cad=json.loads((root/'cad-readback.json').read_text())
rows=[]
for p in cad['parts']:
    obj=bpy.data.objects.get(p['id'])
    if obj is None or obj.type!='MESH':raise RuntimeError('GLB_PART_MISSING:'+p['id'])
    actual=[v*1000 for v in obj.dimensions]
    error=max(abs(a-b) for a,b in zip(actual,p['size_mm']))
    rows.append({'id':p['id'],'size_mm':actual,'max_error_mm':error,'passed':error<.25})
report={'fresh_glb_import':True,'part_count':len(rows),'parts':rows,'passed':all(r['passed'] for r in rows)}
(root/'glb-readback.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'passed':report['passed'],'parts':len(rows)}))
if not report['passed']:raise RuntimeError('GLB_DIMENSION_MISMATCH')
