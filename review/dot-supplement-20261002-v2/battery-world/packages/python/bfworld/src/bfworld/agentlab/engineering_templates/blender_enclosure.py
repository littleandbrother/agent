"""Executed by a fresh Blender process; units are metres, inputs are millimetres."""
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector

root = Path(sys.argv[sys.argv.index('--') + 1])
p = json.loads((root / 'input.json').read_text())['parameters']
length, width, height, wall = [p[k] / 1000 for k in ('length_mm', 'width_mm', 'height_mm', 'wall_mm')]
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.unit_settings.length_unit = 'MILLIMETERS'


def material(name, color, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    node = mat.node_tree.nodes.get('Principled BSDF')
    node.inputs['Base Color'].default_value = (*color, 1)
    node.inputs['Metallic'].default_value = metallic
    node.inputs['Roughness'].default_value = .38
    return mat


shell = material('Housing · illustrative polymer', (.21, .30, .39))
board = material('PCB envelope · dimensions assumed', (.035, .32, .21))
gold = material('Component envelope', (.45, .35, .17), .55)
parts = []


def block(name, dimensions, position, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=position)
    item = bpy.context.object
    item.name = name
    item.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    item.data.materials.append(mat)
    bevel = item.modifiers.new('Edge highlight', 'BEVEL')
    bevel.width = min(wall / 7, .0004); bevel.segments = 3
    item.modifiers.new('Normals', 'WEIGHTED_NORMAL')
    parts.append({'name': name, 'dimensions_mm': [round(v*1000, 6) for v in dimensions], 'position_mm': [round(v*1000, 6) for v in position]})
    return item


block('Base', (length, width, wall), (0, 0, wall/2), shell)
for sign in (-1, 1):
    block('Side Y ' + str(sign), (length, wall, height-wall), (0, sign*(width-wall)/2, (height+wall)/2), shell)
    block('Side X ' + str(sign), (wall, width-2*wall, height-wall), (sign*(length-wall)/2, 0, (height+wall)/2), shell)
block('PCB clearance envelope', (length-4*wall, width-4*wall, .0016), (0, 0, 2*wall+.0008), board)
block('Electronics envelope', ((length-4*wall)*.30, (width-4*wall)*.45, height*.25), (0, 0, 2*wall+.0016+height*.125), gold)
block('Lid · exploded view', (length, width, wall), (0, width*1.25, height*.7), shell)
body = bpy.data.objects.new('Housing envelope', None)
scene.collection.objects.link(body)
body['outer_dimensions_mm'] = [p['length_mm'], p['width_mm'], p['height_mm']]
body['scope'] = 'Parametric visualization only. No CAD tolerances, threads, ingress or manufacturing qualification.'

# Export only product meshes; cameras and studio floor are presentation objects.
bpy.ops.object.select_all(action='DESELECT')
for item in bpy.data.objects:
    if item.type == 'MESH': item.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(root/'model.glb'), export_format='GLB', use_selection=True)
floor = material('Studio', (.84, .87, .89))
block('Studio floor', (length*9, width*9, .001), (0, width*.3, -.001), floor)
target = Vector((0, width*.45, height*.35))
bpy.ops.object.camera_add(location=(length*1.7, -width*2.5, max(length,width)*2.2))
camera = bpy.context.object
camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type='ORTHO'; camera.data.ortho_scale=max(length*2.4,width*3.6)
scene.camera=camera
for location, energy, size in [((.12,-.15,.22),1.2,.18), ((-.14,.10,.16),.7,.14)]:
    bpy.ops.object.light_add(type='AREA', location=location)
    lamp=bpy.context.object; lamp.data.energy=energy; lamp.data.shape='DISK'; lamp.data.size=size
    lamp.rotation_euler=(target-lamp.location).to_track_quat('-Z','Y').to_euler()
scene.world.color=(.35,.35,.35)
scene.render.engine='CYCLES'; scene.cycles.samples=24; scene.cycles.device='CPU'
scene.render.threads_mode='FIXED'; scene.render.threads=2
scene.render.resolution_x=1100; scene.render.resolution_y=760; scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'; scene.render.filepath=str(root/'preview.png')
bpy.ops.wm.save_as_mainfile(filepath=str(root/'model.blend'))
bpy.ops.render.render(write_still=True)
(root/'result.json').write_text(json.dumps({'engine': 'Blender', 'version': bpy.app.version_string, 'units': 'mm',
    'outer_dimensions_mm': [p['length_mm'],p['width_mm'],p['height_mm']], 'parts': parts[:-1],
    'geometry_created': True, 'rendered': True, 'manufacturing_verified': False,
    'scope': '参数化外壳与元件占位展示；尺寸来自输入假设，未进行 CAD 公差、装配干涉或防护验证。'}, ensure_ascii=False, indent=2))
