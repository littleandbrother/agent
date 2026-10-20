"""Fixed CadQuery consumer of node dimensions; run by the pinned CAD Python."""
import hashlib
import json
import math
from pathlib import Path
import sys

import cadquery as cq


def build(folder):
    data=json.loads((folder/'cad-input.json').read_text()); d=data['design']; m=data['manifest']['mechanical']
    length=d['length_m']*1000; width=d['width_m']*1000
    substrate=d['substrate_m']*1000; piezo=d['piezo_m']*1000
    clamp=m['clamp_length_mm']; base=m['base_thickness_mm']
    bw,bh,bt=m['board_size_mm']; bx,by,bz=m['board_origin_mm']
    gap=data['peak_motion_mm']+m['motion_clearance_mm']
    parts=[]
    def box(w,h,z,x,y,bottom): return cq.Workplane('XY').box(w,h,z,centered=(False,False,False)).translate((x,y,bottom))
    def add(label,shape,color): parts.append((label,shape.val(),color))
    right=max(length,bx+bw)+6; back=by+bh+6
    holes=[(bx+x,by+y) for x in (3,bw-3) for y in (3,bh-3)]
    root_holes=[(-clamp/2,-4),(-clamp/2,width+4)]
    def drill(shape,points,z,height,r=1.6):
        for x,y in points:
            tool=cq.Workplane('XY').circle(r).extrude(height).translate((x,y,z))
            shape=shape.cut(tool)
        return shape
    add('mounting-base',drill(box(right+clamp+6,back+8,base,-clamp-6,-8,-gap-base),holes+root_holes,-gap-base,base),'#c5ced5')
    add('root-support',drill(box(clamp,width+16,gap,-clamp,-8,-gap),root_holes,-gap,gap),'#8696a4')
    add('substrate',box(length+clamp,width,substrate,-clamp,0,0),'#aab4bf')
    add('piezo-layer',box(length+clamp,width,piezo,-clamp,0,substrate),'#b5c8d9')
    add('root-clamp',drill(box(clamp,width+16,3,-clamp,-8,substrate+piezo),root_holes,substrate+piezo,3),'#74899a')
    if d['tip_mass_kg']:
        # Optional brass mass: volume derives from declared mass and stated density.
        thickness=d['tip_mass_kg']/8500*1e9/(width*10)
        add('tip-mass',box(10,width,thickness,length-10,0,substrate+piezo),'#c3a36a')
    add('pcb-envelope',drill(box(bw,bh,bt,bx,by,bz),holes,bz,bt),'#477a69')
    native=data.get('native_geometry'); component_sources=[]
    if native:
        if native['board_size_mm']!=[bw,bh,bt]: raise ValueError('NODE_CAD_BOARD_SIZE_MISMATCH')
        for part in native['components']:
            x0,y0,x1,y1=part['bounds_mm']; height=part['height_mm']
            if not all(math.isfinite(v) for v in (x0,y0,x1,y1,height)) or height<=0 or x1<=x0 or y1<=y0:
                raise ValueError('NODE_CAD_COMPONENT_GEOMETRY')
            if min(x0,y0)<0 or x1>bw or y1>bh: raise ValueError('NODE_CAD_COMPONENT_OUTSIDE_BOARD:'+part['ref'])
            for hx,hy in holes:
                dx=max(bx+x0-hx,0,hx-(bx+x1));dy=max(by+y0-hy,0,hy-(by+y1))
                if math.hypot(dx,dy)<3: raise ValueError('NODE_CAD_FASTENER_CLASH:'+part['ref'])
            add(part['ref']+'-component-envelope',box(x1-x0,y1-y0,height,bx+x0,by+y0,bz+bt),
                '#667b91' if part['ref']=='U2' else '#353f49' if part['ref'].startswith('U') else '#b7a687')
            component_sources.append(part)
    for i,(x,y) in enumerate(holes):
        spacer=cq.Workplane('XY').circle(2.7).circle(1.6).extrude(bz+gap).translate((x,y,-gap))
        add('standoff-'+str(i+1),spacer,'#98a6b5')
    for i,(x,y) in enumerate(holes+root_holes):
        top=bz+bt if i<len(holes) else substrate+piezo+3
        shaft=cq.Workplane('XY').circle(1.45).extrude(top+gap+base+2.4).translate((x,y,-gap-base-2.4))
        head=cq.Workplane('XY').circle(2.85).extrude(2).translate((x,y,top))
        add('M3-fastener-'+str(i+1),shaft.union(head),'#a6adb3')
        nut=cq.Workplane('XY').polygon(6,5.5/math.cos(math.pi/6)).circle(1.5).extrude(2.4).translate((x,y,-gap-base-2.4))
        add('M3-nut-'+str(i+1),nut,'#a6adb3')
    assembly=cq.Assembly(name='piezo-node')
    for label,shape,color in parts:
        rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
        assembly.add(shape,name=label,color=cq.Color(*rgb))
    assembly.save(str(folder/'assembly.step'))
    read=cq.importers.importStep(str(folder/'assembly.step')).val()
    if not read.isValid() or len(read.Solids())!=len(parts): raise ValueError('NODE_STEP_READBACK')
    mesh=[]
    for label,shape,color in parts:
        points,triangles=shape.tessellate(.15,.1)
        mesh.append({'name':label,'color':color,'vertices':[[v.x,v.y,v.z] for v in points],
                     'triangles':triangles,'edges':[[[p.x,p.y,p.z] for p in edge.sample(2 if edge.geomType()=='LINE' else 32)[0]] for edge in shape.Edges()],
                     'bounds':list(shape.BoundingBox().toTuple()) if hasattr(shape.BoundingBox(),'toTuple') else
                     [shape.BoundingBox().xmin,shape.BoundingBox().ymin,shape.BoundingBox().zmin,shape.BoundingBox().xmax,shape.BoundingBox().ymax,shape.BoundingBox().zmax]})
    sha=hashlib.sha256((folder/'assembly.step').read_bytes()).hexdigest()
    (folder/'assembly-mesh.json').write_text(json.dumps({'units':'mm','source_sha256':sha,'parts':mesh}))
    overlaps=[]
    for i,(a,sa,_) in enumerate(parts):
        for b,sb,_ in parts[i+1:]:
            volume=sa.intersect(sb).Volume()
            if volume>1e-6: overlaps.append({'a':a,'b':b,'volume_mm3':volume})
    if overlaps: raise ValueError('NODE_ASSEMBLY_INTERFERENCE:'+json.dumps(overlaps))
    readback={'native_valid':True,'source_sha256':sha,'solid_count':len(read.Solids()),
        'beam_free_length_mm':length,'beam_width_mm':width,'substrate_mm':substrate,'piezo_mm':piezo,
        'root_extension_mm':clamp,'root_plane_x_mm':0,'measured_peak_motion_mm':data['peak_motion_mm'],
        'minimum_motion_clearance_mm':m['motion_clearance_mm'],'base_gap_mm':gap,'interferences':overlaps,
        'board_size_mm':[bw,bh,bt],'board_origin_mm':[bx,by,bz],'mount_holes_mm':[[x,y,3.2] for x,y in holes],
        'source_assumption':'ideal root plane x=0; added clamp compliance requires material/contact model qualification',
        'components':component_sources,'component_representation':'Conservative native footprint XY envelopes extruded to datasheet/library heights',
        'board_scope':'native footprint envelopes and sourced heights' if native else 'drilled PCB envelope',
        'fasteners':'four board and two root M3 clearance fits; 3.2 mm holes; conservative button-head envelopes D5.7 x H2 mm and hex nuts AF5.5 x H2.4 mm'}
    (folder/'assembly-readback.json').write_text(json.dumps(readback,ensure_ascii=False))
    for view in ('top','side','isometric','exploded'):
        if view in ('isometric','exploded'):
            technical_view(parts,view,folder/('cad-'+view+'.svg'),readback)
        else:
            render(mesh,view,folder/('cad-'+view+'.svg'),readback)


def technical_view(parts,view,path,readback):
    """Use the CAD kernel's hidden-line projection, avoiding triangle depth artifacts."""
    from xml.etree import ElementTree as ET
    shapes=[]
    for label,shape,_ in parts:
        shift=0
        if view=='exploded':
            shift=28 if 'component-envelope' in label or label=='pcb-envelope' or label.startswith('M3') else 20 if label=='root-clamp' else 16 if label=='piezo-layer' else 12 if label=='substrate' else 6 if label.startswith(('standoff','root-support')) else 0
        shapes.append(shape.translate((0,0,shift)))
    svg=cq.exporters.getSVG(cq.Compound.makeCompound(shapes),{'width':1000,'height':540,
        'marginLeft':100,'marginTop':40,'projectionDir':(-1.75,1.1,3),
        'showAxes':False,'showHidden':False,'strokeColor':(52,77,93),'strokeWidth':.13})
    ns='http://www.w3.org/2000/svg';ET.register_namespace('',ns)
    root=ET.fromstring(svg);root.set('height','600');root.set('viewBox','0 0 1000 600')
    root.insert(0,ET.Element('{'+ns+'}rect',{'width':'1000','height':'600','fill':'white'}))
    for y,text in [(565,f'Free beam {readback["beam_free_length_mm"]:g} x {readback["beam_width_mm"]:g} mm | PCB {readback["board_size_mm"][0]:g} x {readback["board_size_mm"][1]:g} mm'),
        (588,f'Root x=0 | Extra motion clearance {readback["minimum_motion_clearance_mm"]:g} mm | CAD hidden-line view: {view}')]:
        label=ET.SubElement(root,'{'+ns+'}text',{'x':'45','y':str(y),'font-family':'sans-serif','font-size':'16','fill':'#274059'})
        label.text=text
    path.write_text(ET.tostring(root,encoding='unicode'))


def render(parts,view,path,readback):
    def project(p,shift=0):
        x,y,z=p; z+=shift
        if view=='top': return x,-y,z
        if view=='side': return x,-z,y
        return .866*x-.866*y, .5*x+.5*y-z, x+y+z
    faces=[]; coords=[]
    for n,part in enumerate(parts):
        label=part['name'];shift=0
        if view=='exploded':
            shift=28 if 'component-envelope' in label or label=='pcb-envelope' or label.startswith('M3') else 20 if label=='root-clamp' else 16 if label=='piezo-layer' else 12 if label=='substrate' else 6 if label.startswith(('standoff','root-support')) else 0
        points=[project(p,shift) for p in part['vertices']]; coords+=points
        for triangle in part['triangles']:
            p=[points[i] for i in triangle]
            faces.append((sum(v[2] for v in p)/3,part['color'],p,False))
        for edge in part.get('edges',[]):
            p=[project(v,shift) for v in edge]
            faces.append((sum(v[2] for v in p)/len(p)+1e-5,'#617181',p,True))
    xmin=min(p[0] for p in coords); xmax=max(p[0] for p in coords)
    ymin=min(p[1] for p in coords); ymax=max(p[1] for p in coords)
    scale=min(860/(xmax-xmin),460/max(ymax-ymin,1)); transform=lambda p:(55+(p[0]-xmin)*scale,50+(p[1]-ymin)*scale)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600" viewBox="0 0 1000 600"><rect width="1000" height="600" fill="white"/>']
    for _,color,face,is_edge in sorted(faces,key=lambda f:f[0]):
        points=' '.join('%.3f,%.3f'%transform(p) for p in face)
        svg.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="0.7"/>' if is_edge else
            f'<polygon points="{points}" fill="{color}" stroke="{color}" stroke-width="0.15"/>')
    if view=='top':
        def dimension(a,b,label):
            x1,y1=transform(project(a));x2,y2=transform(project(b))
            svg.append(f'<path d="M{x1} {y1}L{x2} {y2}" fill="none" stroke="#247ba4" stroke-width="1.2"/>')
            for x,y in ((x1,y1),(x2,y2)):
                svg.append(f'<path d="M{x-3} {y-5}l6 10" stroke="#247ba4" stroke-width="1.2"/>')
            svg.append(f'<text x="{(x1+x2)/2+5}" y="{(y1+y2)/2-7}" font-family="sans-serif" font-size="14" fill="#17587a">{label}</text>')
        length=readback['beam_free_length_mm'];width=readback['beam_width_mm']
        bx,by,bz=readback['board_origin_mm'];bw,bh,_=readback['board_size_mm']
        dimension((0,-3,.5),(length,-3,.5),f'Free length {length:g} mm')
        dimension((length+3,0,.5),(length+3,width,.5),f'{width:g} mm')
        dimension((bx,by+bh+3,bz),(bx+bw,by+bh+3,bz),f'PCB {bw:g} x {bh:g} mm')
    svg.append('<g font-family="sans-serif" font-size="16" fill="#274059">')
    svg.append(f'<text x="45" y="565">Free beam {readback["beam_free_length_mm"]:g} x {readback["beam_width_mm"]:g} mm | Layers {readback["substrate_mm"]:g} + {readback["piezo_mm"]:g} mm</text>')
    svg.append(f'<text x="45" y="588">Root x=0 | Clearance beyond saved motion: {readback["minimum_motion_clearance_mm"]:g} mm | {view}</text></g></svg>')
    path.write_text(''.join(svg))


if __name__=='__main__': build(Path(sys.argv[1]))
