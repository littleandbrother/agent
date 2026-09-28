"""Run with Blender --background <model.blend> --python this.py -- <output.json>."""
import json
import sys
from pathlib import Path
import bpy
from mathutils import Vector

parts = [obj for obj in bpy.data.objects if obj.name == 'Base' or obj.name.startswith('Side ')]
assert len(parts) == 5
corners = [obj.matrix_world @ Vector(corner) for obj in parts for corner in obj.bound_box]
dimensions = [(max(c[i] for c in corners) - min(c[i] for c in corners))*1000 for i in range(3)]
assert all(abs(a-b) < .0001 for a,b in zip(dimensions,[80,50,25])), dimensions
assert bpy.context.scene.unit_settings.system == 'METRIC'
assert bpy.context.scene.unit_settings.scale_length == 1
output = {'native_file':bpy.data.filepath,'blender_version':bpy.app.version_string,
          'native_base_envelope_mm':dimensions,'unit_scale_metres':1,'geometry_readback_passed':True,
          'scope':'Default template geometry readback only; no manufacturing qualification.'}
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(output,indent=2))
print(json.dumps(output))
