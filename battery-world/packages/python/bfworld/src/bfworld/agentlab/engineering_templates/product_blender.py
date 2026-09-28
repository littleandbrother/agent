"""Presentation derived from native CAD meshes; no independent geometry guesses."""
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector

root = Path(sys.argv[sys.argv.index('--') + 1])
payload = json.loads((root / 'input.json').read_text())['assembly']['payload']
cad = json.loads((root / 'cad-readback.json').read_text())
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1
scene.unit_settings.length_unit = 'MILLIMETERS'
objects = []
for part in payload['parts']:
    bpy.ops.wm.stl_import(filepath=str(root / (part['id'] + '.stl')))
    obj = bpy.context.object; obj.name = part['id']
    obj.scale = (.001, .001, .001)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj['part_id'] = part['id']; obj['role'] = part['role']; obj['source_basis'] = part['source']['basis']
    mat = bpy.data.materials.new(part['id']); mat.diffuse_color = (*part.get('color', [.6, .6, .6]), 1)
    mat.use_nodes = True
    node = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if node is None:
        node = mat.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
        output = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None) or mat.node_tree.nodes.new('ShaderNodeOutputMaterial')
        mat.node_tree.links.new(node.outputs['BSDF'], output.inputs['Surface'])
    node.inputs['Base Color'].default_value = mat.diffuse_color
    node.inputs['Roughness'].default_value = .3 if part['role'] in ('solar', 'feedback') else .58
    node.inputs['Metallic'].default_value = .3 if part['role'] in ('solar', 'connector') else 0
    obj.data.materials.append(mat); objects.append(obj)
    for f in obj.data.polygons:
        f.use_smooth = False

bpy.ops.object.select_all(action='DESELECT')
for obj in objects:
    obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(root / 'model.glb'), export_format='GLB', use_selection=True, export_extras=True)
bb = cad['assembly_bounds']; low = Vector(bb['min_mm']) * .001; high = Vector(bb['max_mm']) * .001
target = (low + high) * .5; size = max((high-low))
bpy.ops.mesh.primitive_plane_add(size=size * 30, location=(0, 0, low.z - .0008))
floor = bpy.context.object; floor.name = 'Studio floor'
mat = bpy.data.materials.new('warm paper'); mat.diffuse_color = (.79, .77, .72, 1); floor.data.materials.append(mat)
world = scene.world; world.use_nodes = True
background = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
background.inputs['Color'].default_value = (.8,.85,.94,1)
background.inputs['Strength'].default_value = .25
for location, power, width in [((-.23,-.24,.38),2,.3),((.22,.03,.25),1.3,.25),((0,.28,.4),2.4,.22)]:
    bpy.ops.object.light_add(type='AREA', location=location)
    lamp=bpy.context.object;lamp.data.energy=power;lamp.data.shape='DISK';lamp.data.size=width
    lamp.rotation_euler=(target-lamp.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(); camera=bpy.context.object;scene.camera=camera
camera.data.type='ORTHO'; camera.data.ortho_scale=size*1.8
scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.device='CPU'
scene.render.threads_mode='FIXED';scene.render.threads=2
scene.render.resolution_x=1200;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
def render(name, position):
    camera.location=target+Vector(position)*size
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/name)
    bpy.ops.render.render(write_still=True)

angle=math.radians(payload.get('presentation',{}).get('camera_deg',35))
render('preview.png',(math.sin(angle)*2,-math.cos(angle)*2,1.1))
render('front.png',(0,-3,.35))
render('back.png',(1,3,1.3))
bpy.ops.wm.save_as_mainfile(filepath=str(root/'model.blend'))
for part,obj in zip(payload['parts'],objects):
    if part['role'] in ('housing','cover'):
        obj.hide_render=True
render('inside.png',(.8,-3,1.4))
for obj in objects:obj.hide_render=False
for i,obj in enumerate(objects):
    if payload['parts'][i]['role'] in ('housing','cover','solar'):
        obj.location.y += .045 if payload['parts'][i]['role']=='cover' else -.045
render('exploded.png',(1.2,-3,1.2))
print('PRODUCT_RENDER_COMPLETE')
