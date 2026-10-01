"""D1 parameterized CAD and dimensioned A3 drawings from actual OCCT solids.
Run with product-cad Python; outputs mm. No mesh is promoted to CAD.
"""
import argparse,csv,hashlib,importlib.util,json,re,shutil,sys
from pathlib import Path
import cadquery as cq

APP=Path(__file__).resolve().parents[2]
def build(out,design_path=None):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 design=json.loads(Path(design_path or APP/'configs/reference_cases/door-magnetic-v1/design.json').read_text())
 modspec=importlib.util.spec_from_file_location('reference',APP/'scripts/build_pluck_product.py');mod=importlib.util.module_from_spec(modspec);modspec.loader.exec_module(mod)
 spec=mod.definition();spec['title']=design['title'];spec['design_revision']='D2';spec['requirements']=design['assumptions'];spec['interfaces']=['All coordinates in local mm; x along beam, z transverse bending.','World XYZ = (1004-x,70+z,2140+y) mm. Driver rotates with door around world z.'];spec['assumptions']=design['assumptions']
 # D1 changes: actual 80x30 carrier PCB mounting interface; remove unbound chips.
 spec['parts']=[p for p in spec['parts'] if p['id'] not in ['power_envelope','radio_envelope','storage_envelope','driver_carrier']]
 for p in spec['parts']:
  g=p['geometry']
  if p['id']=='main_pcb':
   g.update(size_mm=[80,30,1.6],center_mm=[45,-12,-22],cutouts=[{'kind':'cylinder','size_mm':[2.4,2.4,8],'center_mm':[x,y,0]} for x in [-36,36] for y in [-11,11]])
   p['source']['note']='D1 routed-board outline interface; electronic copper is separately checked against native PCB.'
  if p['id']=='housing':
   g['fillet_mm']=1.5
   g['additions']=[x for x in g['additions'] if not (x['size_mm']==[5,5,7.2])]
   for x in [9,81]:
    for y in [-23,-1]:
     g['additions'].append({'kind':'cylinder','size_mm':[5,5,7.2],'center_mm':[x-44,y,-26.4],'cutouts':[{'kind':'cylinder','size_mm':[1.6,1.6,12],'center_mm':[0,0,0]}]})
  if p['id']=='driver_magnet': g['center_mm']=[126,0,-25]
  if p['id']=='pzt':p['material']='PZT-5A assumed; COMSOL library'
  if p['id'] in ['tip_magnet','driver_magnet']:p['material']='NdFeB N42 nominal Br=1.25 T'
 def add(id,size,center,material,role='mount',cuts=(),color=(.65,.68,.72),kind='box'):
  spec['parts'].append({'id':id,'name':id,'role':role,'material':material,'geometry':{'kind':kind,'size_mm':size,'center_mm':center,'cutouts':list(cuts)},'color':color,'source':{'basis':'D1 design','note':'Dimensioned prototype part; thread and material qualification not completed'}})
 # Door-top bracket is separate, slotted to set the driver alignment.
 add('driver_bracket_vertical',[32,47,3],[126,-16.5,-38.5],'PETG prototype',cuts=[{'kind':'box','size_mm':[4,10,10],'center_mm':[x,-17,0]} for x in [-11,11]])
 add('driver_bracket_shelf',[26,3,16],[126,-11.5,-32],'PETG prototype')
 add('driver_retainer',[26,26,2],[126,0,-14],'PETG prototype',cuts=[{'kind':'box','size_mm':[20.3,20.3,8],'center_mm':[0,0,0]}])
 for i,(x,y) in enumerate([(9,-23),(81,-23),(9,-1),(81,-1)]):
  add('pcb_screw_'+str(i),[2,2,5],[x,y,-23.3],'M2 nylon screw envelope','connector',kind='cylinder')
 for part in spec['parts']:
  if part['id'].startswith('driver_'):part['geometry']['center_mm'][0]+=design['magnets']['nominal_center_separation_x_mm']-26
 # No fake chip blocks: board assembly awaits native footprint/STEP import.
 spec['allowed_contacts']=[['main_pcb','pcb_screw_'+str(i)] for i in range(4)]
 spec['allowed_contacts'] += [['housing','pcb_screw_'+str(i)] for i in range(4)]
 spec['allowed_contacts'] += [['driver_bracket_vertical','driver_bracket_shelf'],['driver_magnet','driver_bracket_shelf']]
 (out/'input.json').write_text(json.dumps({'assembly':{'payload':spec}},ensure_ascii=False,indent=2))
 (out/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2))
 shutil.copy2(__file__,out/'D1_parametric_source.py');shutil.copy2(APP/'scripts/build_pluck_product.py',out/'reference_definition.py')
 source=(APP/'packages/python/bfworld/src/bfworld/agentlab/engineering_templates/product_cad.py').read_text().replace('    return shape\n','    for addition in g.get("additions", []):\n        shape = shape.fuse(transform(primitive(addition), addition))\n    return shape\n',1)
 (out/'native_builder.py').write_text(source)
 old=sys.argv;sys.argv=['native_builder.py',str(out)]
 namespace={'__name__':'__main__'};exec(compile(source,'native_builder.py','exec'),namespace);sys.argv=old
 solids=namespace['solids'];read=json.loads((out/'cad-readback.json').read_text())
 # Individual STEP files and A3 vector drawings: true projected BREP edges.
 draw=out/'drawings';draw.mkdir(exist_ok=True)
 colors='#17232b';svghead='<svg xmlns="http://www.w3.org/2000/svg" width="1587" height="1123" viewBox="0 0 1587 1123">'
 for p,r in zip(spec['parts'],read['parts']):
  shape=solids[p['id']];cq.exporters.export(shape,str(out/(p['id']+'.step')))
  b=shape.BoundingBox();center=b.center;local=shape.translate((-center.x,-center.y,-center.z))
  chunks=[svghead,'<rect width="1587" height="1123" fill="white"/><rect x="35" y="35" width="1517" height="1053" fill="none" stroke="#17232b"/>',f'<g font-family="Arial" fill="{colors}"><text x="65" y="80" font-size="26">BF DOOR / D2 / {p["id"]}</text><text x="65" y="110" font-size="17">Units mm | third-angle views | prototype drawing | projection from STEP geometry</text></g>']
  for title,direction,origin in [('TOP',(0,0,1),(70,150)),('FRONT',(0,-1,0),(70,575)),('RIGHT',(1,0,0),(825,150)),('ISOMETRIC',(1,-1,1),(825,575))]:
   inner=cq.exporters.getSVG(local,opts={'width':650,'height':345,'projectionDir':direction,'showHidden':title!='ISOMETRIC','strokeWidth':.55,'strokeColor':(23,35,43),'hiddenColor':(150,150,150),'marginLeft':55,'marginTop':30})
   inner=inner[inner.index('<svg'):];inner=inner[inner.index('>')+1:inner.rindex('</svg>')]
   scale=abs(float(re.search(r'scale\(([\d.eE+-]+)',inner).group(1)))
   inner=re.sub(r'stroke-width="[^"]+"',f'stroke-width="{1.2/scale}"',inner)
   inner=re.sub(r'stroke-dasharray="[^"]+"',f'stroke-dasharray="{3/scale},{2/scale}"',inner)
   ox,oy=origin;chunks.append(f'<g transform="translate({ox},{oy})">{inner}<text x="15" y="12" font-family="Arial" font-size="18">{title}</text></g>')
   if title in ['TOP','FRONT','RIGHT']:
    dim1=b.ylen if title=='RIGHT' else b.xlen;dim2=b.ylen if title=='TOP' else b.zlen
    chunks.append(f'<g stroke="#34526b" fill="#34526b" font-family="Arial" font-size="17"><path d="M {ox+55} {oy+355} h 535 m -535 -6 v 12 m 535 -12 v 12" fill="none"/><text x="{ox+285}" y="{oy+380}" stroke="none">{dim1:.3f}</text><text x="{ox+585}" y="{oy+165}" stroke="none">{dim2:.3f}</text></g>')
  notes=f'Material: {p["material"]} | envelope {b.xlen:.3f} x {b.ylen:.3f} x {b.zlen:.3f} mm'
  chunks.append(f'<g font-family="Arial" fill="#17232b"><text x="70" y="990" font-size="18">{notes}</text><text x="70" y="1017" font-size="16">Plastic general tolerance +/-0.25 mm; metal/ceramic tolerance requires supplier drawing.</text><text x="70" y="1042" font-size="16">Hole positions and boolean features: input.json. No IP, fatigue, thread-strength or fabrication-release certification.</text></g></svg>')
  (draw/(p['id']+'.svg')).write_text('\n'.join(chunks))
 with (out/'bom.csv').open('w') as f:
  w=csv.writer(f);w.writerow(['part','material','x_mm','y_mm','z_mm','cx_mm','cy_mm','cz_mm'])
  for p in spec['parts']:w.writerow([p['id'],p['material'],*p['geometry']['size_mm'],*p['geometry']['center_mm']])
 # Installation is a separate full-scale, manufactured-solid context assembly.
 env={}
 env['door']=cq.Workplane('XY').box(900,40,2100).translate((450,0,1050)).edges('|Z').fillet(2).val()
 env['jamb_left']=cq.Workplane('XY').box(55,60,2180).translate((-32.5,0,1090)).val()
 env['jamb_right']=cq.Workplane('XY').box(55,60,2180).translate((932.5,0,1090)).val()
 env['lintel']=cq.Workplane('XY').box(1010,60,75).translate((450,0,2142.5)).val()
 for i,z in enumerate([250,1050,1850]):env['hinge_'+str(i)]=cq.Workplane('XY').cylinder(95,7).translate((0,24,z)).val()
 env['handle_rose']=cq.Workplane('XZ').cylinder(8,25).translate((825,24,1030)).val()
 env['handle_stem']=cq.Workplane('XZ').cylinder(40,8).translate((825,42,1030)).val()
 env['handle_grip']=cq.Workplane('YZ').cylinder(115,8).translate((775,60,1030)).val()
 install=cq.Assembly(name='D1_door_installation')
 for name,s in env.items():
  cq.exporters.export(s,str(out/(name+'.stl')),tolerance=.1);install.add(s,name=name)
 for name,s in solids.items():
  # local x -> -world x, local y -> world z, local z -> world y.
  s=s.rotate((0,0,0),(0,1,1),180).translate((1004,70,2140));install.add(s,name=name)
 install.save(str(out/'installation.step'))
 (out/'drawing-index.json').write_text(json.dumps({'revision':'D2','drawings':[str(p.relative_to(out)) for p in draw.glob('*.svg')],'readback':'cad-readback.json','dimensions':'input.json','no_hardware_claim':True},indent=2))
 print(json.dumps({'case':'D2','parts':len(solids),'drawings':len(list(draw.glob('*.svg'))),'collisions':read['collisions']}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('output');p.add_argument('--design');a=p.parse_args();build(a.output,a.design)
