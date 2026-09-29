"""Read actual Freerouting SES; export editable EDA traces and draft Gerbers.

Connectivity/clearance are checked geometrically, independently of router logs.
This does not substitute JLCEDA's native ERC/DRC or fabrication release.
"""
import argparse,json,re,math,hashlib
from pathlib import Path
from shapely.geometry import Point,box,LineString
from shapely import affinity
from shapely.ops import unary_union
from shapely.geometry.polygon import orient
from board import MIL,uid,write_project

def sexp(text):
    stack=[];root=None
    for t in re.findall(r'\(|\)|"[^"\\]*(?:\\.[^"\\]*)*"|[^\s()]+',text):
        if t=='(':
            a=[]
            if stack:stack[-1].append(a)
            stack.append(a)
        elif t==')':root=stack.pop()
        else:stack[-1].append(t.strip('"'))
    return root
def children(a,key):return [v for v in a if isinstance(v,list) and v and v[0]==key]
def main():
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);a=p.parse_args();out=a.folder;b=json.loads((out/'board.json').read_text());tree=sexp((out/'door.ses').read_text());routes=children(tree,'routes')[0];res=children(routes,'resolution')[0];assert res[1]=='um';scale=1/(1000*float(res[2]));tracks=[];vias=[]
    for net in children(children(routes,'network_out')[0],'net'):
        for w in children(net,'wire'):
            pa=children(w,'path')[0];nums=list(map(float,pa[3:]));tracks.append(dict(net=net[1],layer=pa[1],width_mm=float(pa[2])*scale,points_mm=[[nums[i]*scale,nums[i+1]*scale] for i in range(0,len(nums),2)]))
        for v in children(net,'via'):vias.append(dict(net=net[1],x=float(v[2])*scale,y=float(v[3])*scale,diameter=.65,drill=.3))
    copper=[];pads=[]
    for c in b['components']:
        for p in c['pads']:
            w=p['defaultPad']['width']*MIL;h=p['defaultPad']['height']*MIL;x=c['x']+p['centerX']*MIL;y=c['y']+p['centerY']*MIL;ang=p.get('padAngle',0);shape=p['defaultPad']['padType']
            if shape in ('OVAL','ELLIPSE'):
                if abs(w-h)<1e-6:g=Point(0,0).buffer(w/2)
                elif w>h:g=LineString([(-(w-h)/2,0),((w-h)/2,0)]).buffer(h/2)
                else:g=LineString([(0,-(h-w)/2),(0,(h-w)/2)]).buffer(w/2)
            else:g=box(-w/2,-h/2,w/2,h/2)
            g=affinity.translate(affinity.rotate(g,ang),x,y);net=b['nets'][c['ref']].get(p['num'],'NC_'+c['ref']+'_'+p['num']);layers=['F.Cu','B.Cu'] if p.get('hole') else ['F.Cu'];key=c['ref']+'-'+p['num']
            pads.append(dict(id=key,x=x,y=y,w=w,h=h,angle=ang,shape=shape,net=net,layers=layers,drill=1 if p.get('hole') else None))
            for ly in layers:copper.append((net,ly,g,'pad:'+key))
    for i,t in enumerate(tracks):copper.append((t['net'],t['layer'],LineString(t['points_mm']).buffer(t['width_mm']/2),'trace:'+str(i)))
    for i,v in enumerate(vias):
        for ly in ['F.Cu','B.Cu']:copper.append((v['net'],ly,Point(v['x'],v['y']).buffer(.325),'via:'+str(i)))
    violations=[];minimum=100
    for i,(n,ly,g,tag) in enumerate(copper):
        for n2,ly2,g2,tag2 in copper[i+1:]:
            if ly!=ly2 or n==n2:continue
            dist=g.distance(g2);minimum=min(minimum,dist)
            if dist<.1651-.002:violations.append(dict(a=tag,b=tag2,net_a=n,net_b=n2,clearance_mm=dist))
    # Connectivity graph includes each pad/trace/via, with inter-layer links only
    # through plated headers and vias. A 2um tolerance covers DSN/SES quantization.
    disconnect=[]
    for net in sorted({n for m in b['nets'].values() for n in m.values()}):
        items=[c for c in copper if c[0]==net];parent=list(range(len(items)))
        def find(i):
            while parent[i]!=i:i=parent[i]
            return i
        for i,(_,l,g,tag) in enumerate(items):
            for j in range(i):
                _,l2,g2,tag2=items[j]
                if (l==l2 and g.distance(g2)<.002) or tag==tag2:parent[find(i)]=find(j)
        terminals={find(i) for i,c in enumerate(items) if c[3].startswith('pad:')}
        if len(terminals)>1:disconnect.append(dict(net=net,components=len(terminals)))
    keep=unary_union([box(*b['rf_keepout_mm']),box(*b['rf_notch_mm'])]);outside=[]
    for n,ly,g,tag in copper:
        if g.intersection(keep).area>1e-8:outside.append(tag)
    planes={};plane_clearance={}
    for ly in ['F.Cu','B.Cu']:
        obstacles=unary_union([g.buffer(.20) for n,l,g,_ in copper if l==ly and n!='GND']+[keep]+[Point(x,y).buffer(d/2+.3) for x,y,d in b['mounting_holes_mm']])
        region=box(.5,.5,79.5,29.5).difference(obstacles).buffer(-.10).buffer(.10)
        gnd=unary_union([g for n,l,g,_ in copper if n=='GND' and l==ly])
        polygons=list(region.geoms) if region.geom_type=='MultiPolygon' else [region]
        planes[ly]=[g for g in polygons if g.intersects(gnd) and g.area>1]
        plane=unary_union(planes[ly]);plane_clearance[ly]=min(plane.distance(g) for n,l,g,_ in copper if n!='GND' and l==ly)
    report=dict(schema='door-board-checks-v1',ses_sha256=hashlib.sha256((out/'door.ses').read_bytes()).hexdigest(),tracks=len(tracks),vias=len(vias),pads=len(pads),unconnected=disconnect,clearance_violations=violations,minimum_clearance_mm=minimum,minimum_trace_width_mm=min(t['width_mm'] for t in tracks),antenna_keepout_violations=sorted(set(outside)),native_erc=None,native_drc=None,ground_plane_present=True,plane_clearance_mm=plane_clearance,plane_area_mm2={k:sum(g.area for g in v) for k,v in planes.items()},manufacturing_released=False,scope='Independent 2D copper check, no solder/paste/thermal/RF qualification. Router neckdown is allowed and measured; not native EDA DRC.')
    (out/'routing-checks.json').write_text(json.dumps(report,indent=2));(out/'routed-copper.json').write_text(json.dumps(dict(tracks=tracks,vias=vias,pads=pads),indent=2))
    rr=json.loads((out/'source-records.json').read_text());ticket=max(h.get('ticket',0) for h,v in rr)
    def put(t,v):
        nonlocal ticket
        ticket+=1;rr.append((dict(type=t,id=uid('routing'+str(ticket)),ticket=ticket),v))
    for t in tracks:
        for start,end in zip(t['points_mm'],t['points_mm'][1:]):put('LINE',dict(layerId=1 if t['layer']=='F.Cu' else 2,netName=t['net'],startX=start[0]/MIL,startY=start[1]/MIL,endX=end[0]/MIL,endY=end[1]/MIL,width=t['width_mm']/MIL,locked=False))
    for v in vias:put('VIA',dict(layerId=12,netName=v['net'],centerX=v['x']/MIL,centerY=v['y']/MIL,holeDiameter=.3/MIL,viaDiameter=.65/MIL,viaType=0,locked=False))
    for x,y,d in b['mounting_holes_mm']:put('PAD',dict(layerId=12,num='',netName='',centerX=x/MIL,centerY=y/MIL,padAngle=0,hole={'holeType':'ROUND','width':d/MIL,'height':d/MIL},defaultPad={'padType':'ELLIPSE','width':d/MIL,'height':d/MIL},plated=False,locked=True))
    def poly_path(g):
        g=orient(g,sign=-1)
        return [[r.coords[0][0]/MIL,r.coords[0][1]/MIL,'L',*[v/MIL for xy in list(r.coords)[1:] for v in xy]] for r in [g.exterior,*g.interiors]]
    for ly,polygons in planes.items():
        for g in polygons:put('FILL',dict(layerId=1 if ly=='F.Cu' else 2,netName='GND',path=poly_path(g),width=0,fillStyle=0,locked=True,zIndex=0))
        for g in [box(*b['rf_keepout_mm']),box(*b['rf_notch_mm'])]:put('REGION',dict(layerId=1 if ly=='F.Cu' else 2,path=poly_path(g),width=1,prohibitType=[3,5,6,7,8],name='Antenna copper keepout',locked=True))
    write_project(out,rr)
    for layer,label in [('F.Cu','top'),('B.Cu','bottom'),('both','combined')]:
        s=['<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="720" viewBox="-5 -6 90 40"><rect x="-5" y="-6" width="90" height="40" fill="white"/><g transform="translate(0,30) scale(1,-1)"><rect width="80" height="30" rx="1" fill="#153e36" stroke="#152938" stroke-width=".15"/><rect x="52" y="24.2" width="18" height="5.8" fill="#d7c098" opacity=".65"/>']
        for ly,polygons in planes.items():
            if layer not in ('both',ly):continue
            for g in polygons:
                path=' '.join('M '+' L '.join(','.join(map(str,xy)) for xy in r.coords)+' Z' for r in [g.exterior,*g.interiors]);s.append(f'<path d="{path}" fill="'+('#9e693c' if ly=='F.Cu' else '#316488')+'" opacity=".32" fill-rule="evenodd"/>')
        for t in tracks:
            if layer not in ('both',t['layer']):continue
            pts=' '.join(','.join(map(str,xy)) for xy in t['points_mm']);s.append(f'<polyline points="{pts}" fill="none" stroke="'+('#dd7049' if t['layer']=='F.Cu' else '#4e9dd9')+f'" stroke-width="{t["width_mm"]}" stroke-linecap="round" stroke-linejoin="round"/>')
        for p in pads:
            if layer!='both' and layer not in p['layers']:continue
            s.append(f'<rect x="{-p["w"]/2}" y="{-p["h"]/2}" width="{p["w"]}" height="{p["h"]}" rx="{min(p["w"],p["h"])/2 if p["shape"] in ("OVAL","ELLIPSE") else 0}" transform="translate({p["x"]},{p["y"]}) rotate({p["angle"]})" fill="#e5c47f"/>')
        for v in vias:s.append(f'<circle cx="{v["x"]}" cy="{v["y"]}" r=".325" fill="#d8b774"/><circle cx="{v["x"]}" cy="{v["y"]}" r=".15" fill="#102e28"/>')
        for x,y,d in b['mounting_holes_mm']:s.append(f'<circle cx="{x}" cy="{y}" r="{d/2}" fill="white"/>')
        s.append('</g><g font-family="Arial" fill="#dce9e4" font-size=".9">')
        for c in b['components']:s.append(f'<text x="{c["x"]-1}" y="{30-c["y"]-2}">{c["ref"]}</text>')
        s.append(f'</g><text x="0" y="-3" font-family="Arial" font-size="1.6">D2 · {label} copper · 80 × 30 mm · routing draft / NOT FOR FABRICATION</text><text x="0" y="33" font-family="Arial" font-size="1.2">Red: top / Blue: bottom. Antenna keepout shaded. Native ERC/DRC and RF review pending.</text></svg>');(out/f'pcb-{label}.svg').write_text('\n'.join(s))
    # RS-274X derived directly from the routed copper, as draft manufacturing
    # interchange. No ground plane is invented; release gate remains closed.
    gerber=out/'gerber-draft';gerber.mkdir(exist_ok=True)
    for ly,name in [('F.Cu','F_Cu.gtl'),('B.Cu','B_Cu.gbl')]:
        s=['G04 D2 ENGINEERING DRAFT - NOT FOR FABRICATION*','%FSLAX46Y46*%','%MOMM*%','%LPD*%'];apertures={};draw=[]
        def aperture(shape,w,h=None):
            key=(shape,round(w,6),round(h or w,6))
            if key not in apertures:
                no=len(apertures)+10;apertures[key]=no;s.append(f'%ADD{no}{shape},{w:.6f}'+(f'X{h:.6f}' if shape in ('R','O') else '')+'*%')
            draw.append('D'+str(apertures[key])+'*')
        def coord(x,y,op):return f'X{round(x*1e6)}Y{round(y*1e6)}D{op:02d}*'
        for g in planes[ly]:
            for ring,polarity in [(g.exterior,'D')]+[(r,'C') for r in g.interiors]:
                draw+=['%LP'+polarity+'*%','G36*',coord(*ring.coords[0],2)]+[coord(*xy,1) for xy in list(ring.coords)[1:]]+['G37*']
        draw.append('%LPD*%')
        for t in tracks:
            if t['layer']!=ly:continue
            aperture('C',t['width_mm']);draw.append(coord(*t['points_mm'][0],2));draw.extend(coord(*p,1) for p in t['points_mm'][1:])
        for p in pads:
            if ly not in p['layers']:continue
            w,h=p['w'],p['h']
            if round(p['angle'])%180==90:w,h=h,w
            aperture('O' if p['shape'] in ('OVAL','ELLIPSE') else 'R',w,h);draw.append(coord(p['x'],p['y'],3))
        for v in vias:aperture('C',.65);draw.append(coord(v['x'],v['y'],3))
        (gerber/name).write_text('\n'.join(s+draw+['M02*']))
    (gerber/'outline.gko').write_text('\n'.join(['%FSLAX46Y46*%','%MOMM*%','%ADD10C,0.1*%','D10*',*[coord(x,y,2 if i==0 else 1) for i,(x,y) in enumerate([(0,0),(80,0),(80,30),(0,30),(0,0)])],'M02*']))
    for name,holes in [('plated.drl',[(v['x'],v['y'],.3) for v in vias]+[(p['x'],p['y'],p['drill']) for p in pads if p['drill']]),('nonplated.drl',b['mounting_holes_mm'])]:
        sizes=sorted({h[2] for h in holes});s=['M48','METRIC,TZ']+[f'T{i+1:02d}C{d:.3f}' for i,d in enumerate(sizes)]+['%','G90']
        for i,d in enumerate(sizes):s+=[f'T{i+1:02d}']+[f'X{x:.4f}Y{y:.4f}' for x,y,dd in holes if dd==d]
        (gerber/name).write_text('\n'.join(s+['M30']))
    (gerber/'README.txt').write_text('DRAFT copper, outline and drill interchange. No manufacturing release. Missing native ERC/DRC, RF ground plane review, solder/paste masks, plating/fabricator stack-up. Use original EDA project and resolve gates before ordering.')
    print(json.dumps(report))
if __name__=='__main__':main()
