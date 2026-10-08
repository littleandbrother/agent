"""Scientific presentation from exact D4 CAD STL, run with Blender --background.

Cutaway/explosion are presentation transforms. The sampled beam pose is a
first-mode projection of returned ROM displacement, explicitly not a FEM field.
"""
import bpy,bmesh,hashlib,json,math,sys
from pathlib import Path
from mathutils import Vector

args=sys.argv[sys.argv.index('--')+1:];cad,inputs,out=map(Path,args[:3]);out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
scene.unit_settings.system='METRIC';scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
scene.render.resolution_x=1800;scene.render.resolution_y=1200;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.film_transparent=True
scene.world=bpy.data.worlds.new('White scientific studio');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(1,1,1,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.7
scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=-1.5
def mat(name,color,metal=0,rough=.5):
 m=bpy.data.materials.new(name);m.use_nodes=True;n=m.node_tree.nodes['Principled BSDF'];n.inputs['Base Color'].default_value=(*color,1);n.inputs['Metallic'].default_value=metal;n.inputs['Roughness'].default_value=rough;return m
materials={'housing':mat('PETG / neutral',(.65,.68,.70)), 'beam':mat('Copper',(.59,.29,.12),.65,.32),
 'pzt':mat('PZT / functional contrast',(.12,.26,.32)), 'magnet':mat('Nickel',(.37,.43,.46),.7,.25),
 'main_pcb':mat('FR4',(.05,.18,.12)), 'lid':mat('Polycarbonate / opaque drawing',(.85,.88,.89))}
objects={};sources=[]
for item in json.loads((cad/'cad-readback.json').read_text())['parts']:
 name=item['id'];path=cad/(name+'.stl')
 if not path.is_file():continue
 bpy.ops.wm.stl_import(filepath=str(path));o=bpy.context.object;o.name=name;o.scale=(.001,)*3
 bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 m=materials.get(name,materials['magnet'] if 'magnet' in name or 'screw' in name or 'fastener' in name else materials['housing'])
 o.data.materials.append(m);o['cad_source_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();o['units_source']='mm, converted to m'
 objects[name]=o;sources.append({'part':name,'sha256':o['cad_source_sha256']})
context=[]
for name in ['door','jamb_left','jamb_right','lintel','hinge_0','hinge_1','hinge_2','handle_rose','handle_stem','handle_grip']:
 path=cad/(name+'.stl')
 if not path.exists():continue
 bpy.ops.wm.stl_import(filepath=str(path));o=bpy.context.object;o.name=name;o.scale=(.001,)*3;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 o.data.materials.append(materials['lid'] if name=='door' else materials['housing']);context.append(o)
# Context meshes are exact CAD. Product transform matches the recorded D4 frame.
root=bpy.data.objects.new('Recorded CAD placement',None);scene.collection.objects.link(root)
from mathutils import Matrix
root.matrix_world=Matrix(((-1,0,0,1.004),(0,0,1,.070),(0,1,0,2.140),(0,0,0,1)))
for o in objects.values():o.parent=root
def camera(loc,target,scale):
 bpy.ops.object.camera_add(location=loc);c=bpy.context.object;c.data.type='ORTHO';c.data.clip_start=.001;c.data.ortho_scale=scale;c.rotation_euler=(Vector(target)-c.location).to_track_quat('-Z','Y').to_euler();scene.camera=c;return c
c=camera((3.1,4.4,2.65),(.5,0,1.1),2.65)
lights=[]
for loc,power,size in [((1.5,2.3,3.5),650,2),((-1.2,1.5,2.8),450,2)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.size=size;o.rotation_euler=(Vector((.5,0,1.4))-o.location).to_track_quat('-Z','Y').to_euler();lights.append(o)
views=[]
def render(name,scope):
 scene.render.filepath=str(out/(name+'.png'));bpy.ops.render.render(write_still=True)
 from bpy_extras.object_utils import world_to_camera_view
 landmarks={}
 for part in ['clamp_upper','beam','pzt','tip_magnet','driver_magnet','main_pcb']:
  o=objects[part];center=sum((o.matrix_world@Vector(v) for v in o.bound_box),Vector())/8
  p=world_to_camera_view(scene,scene.camera,center)
  landmarks[part]=[p.x,1-p.y]
 views.append({'name':name+'.png','scope':scope,'landmarks':landmarks,'ortho_width_m':scene.camera.data.ortho_scale,'visible_parts':[n for n,o in objects.items() if not o.hide_render],'sha256':hashlib.sha256((out/(name+'.png')).read_bytes()).hexdigest()})
render('installation','Exact D4 door/product CAD, recorded placement, prescribed closed pose. Dimensions are design inputs, not measurements.')
c.location=(1.19,.48,2.39);c.rotation_euler=(Vector((.948,.062,2.14))-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=.265
render('installation-detail','Exact placement at top door edge, no undeclared geometry or deformation.')
# Switch to isolated local frame; same native geometries and dimensions.
for o in context:o.hide_render=True
root.matrix_world=Matrix.Identity(4)
for o in lights:o.hide_render=True
for loc,power,size in [((.10,-.15,.3),18,.4),((-.15,.05,.18),12,.4)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.size=size;o.rotation_euler=(Vector((.06,0,0))-o.location).to_track_quat('-Z','Y').to_euler()
c.location=(.24,-.24,.19);c.rotation_euler=(Vector((.065,0,0))-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=.235
objects['lid'].hide_render=True
for name,o in objects.items():
 if name.startswith('lid_fastener'):o.hide_render=True
# Remove near half of the housing only in presentation mesh. Native CAD unchanged.
housing=objects['housing'];original=housing.data.copy();bm=bmesh.new();bm.from_mesh(housing.data)
bmesh.ops.delete(bm,geom=[v for v in bm.verts if v.co.y<-.0001],context='VERTS');bm.to_mesh(housing.data);bm.free()
render('section','Presentation cut at local y=0; source CAD unchanged. Copper, PZT, magnet, PCB are distinct functional parts.')
housing.hide_render=True
render('mechanism','Functional assembly, housing suppressed for visibility; exact native geometry, no field result.')
original_positions={name:o.location.copy() for name,o in objects.items()}
for name,o in objects.items():
 if name=='lid':o.hide_render=False;o.location.z+=.065
 elif name.startswith('lid_fastener'):o.hide_render=False;o.location.z+=.065
 elif name=='pzt':o.location.z+=.025
 elif name=='main_pcb':o.location.z-=.028
 elif name.startswith('clamp_upper') or name.startswith('clamp_screw'):o.location.z+=.045
 elif name=='tip_magnet':o.location.z+=.04
c.data.ortho_scale=.26
render('exploded','Functional exploded view. Separation is a presentation transform, not an assembly gap or manufacturable new revision.')
for name,o in objects.items():o.location=original_positions[name]
objects['lid'].hide_render=True
for name,o in objects.items():
 if name.startswith('lid_fastener'):o.hide_render=True
for view,loc,target,scale in [('top',(.064,0,.3),(.064,0,0),.22),('side',(.07,-.3,.005),(.07,0,.005),.225),('clamp',(.025,-.055,.045),(-.002,0,0),.065),('pzt',(.09,-.09,.07),(.035,0,.001),.105)]:
 c.location=loc;c.rotation_euler=(Vector(target)-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=scale;render(view,'Native orthographic detail; design dimensions from CAD. No simulated field overlaid.')
# One camera for every state. No auto-fit hides the driver leaving the coupling region.
import csv
wave=list(csv.DictReader((inputs/'waveform.csv').open()))
design=json.loads((inputs/'design-spec.json').read_text());mech=design['mechanical']
X=.904-mech['gap_mm']/1000;Y=.075265+mech['closed_dz_mm']/1000
beam=objects['beam'];flat=beam.data.copy();pzt=objects['pzt'];pztflat=pzt.data.copy();tip=objects['tip_magnet']
for name in objects:
 if name.startswith('driver_') and name!='driver_magnet':objects[name].hide_render=True
c.location=(.08,-.4,.08);c.rotation_euler=(Vector((.08,0,-.005))-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=.215
for i,t in enumerate([0,1.9,2.543125,3.]):
 row=min(wave,key=lambda r:abs(float(r['time_s'])-t));q=float(row['tip_m']);angle=math.radians(65)*(1-t/2 if t<2 else 0 if t<2.5 else min((t-2.5)/2,1))
 for obj,reference in [(beam,flat),(pzt,pztflat)]:
  obj.data=reference.copy()
  for v in obj.data.vertices:
   x=max(0,min(1,(v.co.x-.004)/.096));v.co.z+=q*x*x*(3-x)/2
 tip.location.z=q
 drv=objects['driver_magnet'];origin=Vector((.100+mech['gap_mm']/1000,0,.005265+mech['closed_dz_mm']/1000))
 center=Vector((1.004-(X*math.cos(angle)-Y*math.sin(angle)),0,X*math.sin(angle)+Y*math.cos(angle)-.070))
 rotation=Matrix.Rotation(-angle,4,'Y');drv.matrix_world=Matrix.Translation(center)@rotation@Matrix.Translation(-origin)
 render('state-'+str(i),f't={t:g}s, prescribed angle={math.degrees(angle):.3f}deg, q={q*1000:.4f}mm. Beam/PZT shape is first-mode projection of solved tip, not 3D FEM; driver rigid pose from recorded kinematics.')
bpy.ops.wm.save_as_mainfile(filepath=str(out/'scientific-mechanics.blend'))
(out/'render-receipt.json').write_text(json.dumps({'engine':'Blender','version':bpy.app.version_string,'sources':sources,'views':views,'source_cad':str(cad),'design_id':design['design_id'],'reference_waveform_sha256':hashlib.sha256((inputs/'waveform.csv').read_bytes()).hexdigest(),'hardware_verified':False,'native_CAD_changed':False,'dynamic_shape_scope':'first-mode projection; no FEM deformation claim'},ensure_ascii=False,indent=2))
