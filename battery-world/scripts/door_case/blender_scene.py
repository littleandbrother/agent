"""True-scale CAD imports, articulated door and product closeups. Blender CLI."""
import bpy,json,math,sys
from mathutils import Vector,Matrix
from pathlib import Path
root=Path(sys.argv[sys.argv.index('--')+1]);cad=root/'mechanical-D2';out=root/'animation-D2';out.mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.length_unit='MILLIMETERS'
scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.world=bpy.data.worlds.new('Soft studio');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.16,.18,.22,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.45
scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=-1
def material(name,color,metallic=0,rough=.35,alpha=1):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,alpha);m.use_nodes=True;n=m.node_tree.nodes.get('Principled BSDF');n.inputs['Base Color'].default_value=(*color,1);n.inputs['Metallic'].default_value=metallic;n.inputs['Roughness'].default_value=rough
 if alpha<1:n.inputs['Transmission Weight'].default_value=.85;n.inputs['IOR'].default_value=1.49
 return m
plastic=material('Warm white PETG',(.70,.74,.77),0,.32);metal=material('Nickel plated magnet',(.35,.40,.44),.9,.21);brass=material('Copper substrate',(.62,.26,.10),.75,.26);pzt=material('PZT ceramic',(.12,.21,.31),.12,.3);glass=material('Clear polycarbonate',(.72,.88,.96),0,.12,.2);pcb=material('FR4 board',(.025,.17,.105),.1,.4);wood=material('Ash timber door',(.37,.23,.12),0,.42);frame=material('Painted jamb',(.73,.77,.78),0,.4)
def import_stl(name,mat):
 bpy.ops.wm.stl_import(filepath=str(cad/(name+'.stl')));o=bpy.context.object;o.name=name;o.scale=(.001,)*3;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat)
 for p in o.data.polygons:p.use_smooth=False
 return o
rootobj=bpy.data.objects.new('Fixed product CAD coordinates',None);scene.collection.objects.link(rootobj)
rootobj.matrix_world=Matrix(((-1,0,0,1.004),(0,0,1,.070),(0,1,0,2.140),(0,0,0,1)))
doorpivot=bpy.data.objects.new('Door hinge / prescribed rotation',None);scene.collection.objects.link(doorpivot)
spec=json.loads((cad/'input.json').read_text())['assembly']['payload'];parts={}
for p in spec['parts']:
 name=p['id'];mat=glass if name=='lid' else brass if name=='beam' else pzt if name=='pzt' else metal if 'magnet' in name or 'screw' in name or 'fastener' in name else pcb if name=='main_pcb' else plastic
 o=import_stl(name,mat);o.parent=rootobj;o['cad_part']=name;o['source_brep']=str(cad/(name+'.brep'));parts[name]=o
 if name.startswith('driver_'):
  o.matrix_world=rootobj.matrix_world@o.matrix_local;o.parent=doorpivot;o.matrix_parent_inverse=doorpivot.matrix_world.inverted()
for name in ['door','jamb_left','jamb_right','lintel','hinge_0','hinge_1','hinge_2','handle_rose','handle_stem','handle_grip']:
 o=import_stl(name,wood if name=='door' else metal if name.startswith(('hinge','handle')) else frame)
 if name=='door' or name.startswith('handle'):o.parent=doorpivot
# Native geometry bevels catch light; imported geometry already contains holes/cavities.
for name in ['door','jamb_left','jamb_right','lintel']:
 o=bpy.data.objects[name];mod=o.modifiers.new('Edge finish','BEVEL');mod.width=.001;mod.segments=3;o.modifiers.new('Normals','WEIGHTED_NORMAL')
# Floor, door panel surface detailing and wall surround are presentation context.
def cube(name,loc,size,mat):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat);return o
floor=material('Floor',(.19,.23,.25),0,.72);cube('Floor',(0.5,0,-.045),(5,5,.08),floor)
for x in [-.70,1.62]:cube('Wall', (x,-.10,1.3),(1.3,.13,2.6),frame)
cube('Wall above',(.45,-.10,2.47),(1.0,.13,.46),frame)
for z in [.55,1.50]:
 o=cube('Inset panel',(.45,.0207,z),(.69,.0015,.7),material('Panel tone'+str(z),(.33,.20,.10),0,.5));o.parent=doorpivot
def camera(name,loc,target,lens=50,ortho=None):
 bpy.ops.object.camera_add(location=loc);c=bpy.context.object;c.name=name;c.rotation_euler=(Vector(target)-c.location).to_track_quat('-Z','Y').to_euler();c.data.lens=lens
 if ortho:c.data.type='ORTHO';c.data.ortho_scale=ortho
 return c
wide=camera('Installation camera',(3.3,4.4,2.8),(.50,.0,1.20),52)
macro=camera('Engineering closeup',(1.13,.35,2.29),(.936,.073,2.14),65, .235)
for name,loc,power,size in [('Key',(1.7,2.2,3.7),1100,3),('Fill',(-1.5,1.2,2.8),800,2),('Product',(1.1,.45,2.6),55,.4)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.name=name;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((.6,0,1.5))-o.location).to_track_quat('-Z','Y').to_euler()
scene.frame_start=1;scene.frame_end=121;scene.render.fps=30
for frame,deg in [(1,0),(61,65),(121,65)]:doorpivot.rotation_euler.z=math.radians(deg);doorpivot.keyframe_insert(data_path='rotation_euler',frame=frame)
if doorpivot.animation_data:
 for action in bpy.data.actions:
  try:
   for fc in action.fcurves:
    for kp in fc.keyframe_points:kp.interpolation='LINEAR'
  except AttributeError:pass
scene['design_revision']='D2';scene['evidence_scope']='True dimensional CAD. Door angle prescribed 0..65 deg/2s. No beam deformation is invented; coupling dynamics provided separately.'
scene.frame_set(1);scene.camera=wide
bpy.ops.wm.save_as_mainfile(filepath=str(out/'door-installation.blend'))
scene.render.filepath=str(out/'installation.png');bpy.ops.render.render(write_still=True)
scene.camera=macro;parts['lid'].hide_render=True
scene.render.filepath=str(out/'mechanism.png');bpy.ops.render.render(write_still=True)
scene.frame_set(4);scene.render.filepath=str(out/'mechanism-door-open.png');bpy.ops.render.render(write_still=True)
scene.frame_set(1);parts['lid'].hide_render=False;scene.camera=wide
bpy.ops.export_scene.gltf(filepath=str(out/'door-animation.glb'),export_format='GLB',export_animations=True,export_extras=True)
# Saved scene is the editable animation; PNG sequence + MP4 are viewing derivatives.
scene.render.resolution_x=960;scene.render.resolution_y=600;scene.cycles.samples=8;scene.render.fps=15;scene.frame_end=61
for f in range(1,62):
 scene.frame_set(1+(f-1)*2);scene.render.filepath=str(out/'frames'/f'{f:04d}.png');bpy.ops.render.render(write_still=True)
(out/'scope.json').write_text(json.dumps({'revision':'D2','cad':'../mechanical-D2/assembly.step','native':'door-installation.blend','animation':'door-animation.glb','door_input':'0..65 degree over 2 seconds, then hold 2 seconds','beam_motion':'not animated until solved trajectory is bound','hardware_verified':False},indent=2))
