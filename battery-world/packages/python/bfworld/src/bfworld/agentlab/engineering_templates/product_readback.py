"""Reopen saved Blender output in a fresh process and compare it with native CAD."""
import json
import sys
from pathlib import Path
import bpy

root = Path(sys.argv[sys.argv.index('--')+1])
cad = json.loads((root/'cad-readback.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(root/'model.blend'))
rows=[]
for part in cad['parts']:
    obj=bpy.data.objects.get(part['id'])
    if obj is None or obj.type!='MESH':raise RuntimeError('PART_MISSING:'+part['id'])
    actual=[float(x)*1000 for x in obj.dimensions]
    error=max(abs(a-b) for a,b in zip(actual,part['size_mm']))
    rows.append({'id':part['id'],'size_mm':actual,'cad_dimension_error_mm':error,'passed':error<.25})
if not all(x['passed'] for x in rows):raise RuntimeError('CAD_BLENDER_SIZE_MISMATCH')
(root/'blender-readback.json').write_text(json.dumps({'parts':rows,'passed':all(x['passed'] for x in rows),'native_reopened':True,'units':'mm'},indent=2))
print('PRODUCT_READBACK_COMPLETE')
