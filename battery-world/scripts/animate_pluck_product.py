"""CAD-derived illustrative motion, explicitly not a solved FEM trajectory."""
import json
from pathlib import Path
import sys
import bpy

source=Path(sys.argv[sys.argv.index('--')+1]);out=Path(sys.argv[sys.argv.index('--')+2]);out.mkdir(parents=True,exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(source/'model.blend'))
scene=bpy.context.scene
scene.frame_start=1;scene.frame_end=61;scene.render.fps=20
for name in ['housing','lid']:
    bpy.data.objects[name].hide_render=True
tip=bpy.data.objects['tip_magnet'];driver=bpy.data.objects['driver_magnet'];carrier=bpy.data.objects['driver_carrier']
for obj in [driver,carrier]:
    for frame,z in [(1,-.07),(31,0),(61,.07)]:
        obj.location.z=z;obj.keyframe_insert(data_path='location',frame=frame)
for frame,z in [(1,0),(24,.012),(31,-.01),(38,.007),(45,-.004),(52,.002),(61,0)]:
    tip.location.z=z;tip.keyframe_insert(data_path='location',frame=frame)
for name in ['beam','pzt']:
    obj=bpy.data.objects[name];obj.shape_key_add(name='Basis')
    key=obj.shape_key_add(name='illustrative bending')
    for vertex in key.data:
        u=max(0,min(1,(vertex.co.x-.004)/.096));vertex.co.z+=.012*(3*u*u-u*u*u)/2
    for frame,z in [(1,0),(24,1),(31,-.833),(38,.583),(45,-.333),(52,.167),(61,0)]:
        key.slider_min=-1;key.value=z;key.keyframe_insert(data_path='value',frame=frame)
scene.frame_set(1)
scene['evidence_scope']='Illustrative imposed trajectory only; no FEM/ROM calibration or collision certification.'
bpy.ops.wm.save_as_mainfile(filepath=str(out/'illustrative-motion.blend'))
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.data.objects:
    if obj.get('part_id') and obj.name not in ['housing','lid']:obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(out/'illustrative-motion.glb'),export_format='GLB',use_selection=True,export_animations=True,export_extras=True)
scene.render.engine='CYCLES';scene.cycles.samples=8;scene.render.resolution_percentage=40
scene.frame_set(24);scene.render.filepath=str(out/'motion-preview.png');bpy.ops.render.render(write_still=True)
(out/'scope.json').write_text(json.dumps({'source_cad':str(source),'scope':scene['evidence_scope'],'hardware_verified':False,'calibrated_motion':False},indent=2))
