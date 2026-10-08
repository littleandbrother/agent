"""Restore source-bound CAD/PCB visibility without changing a scientific result.

Run with the resident CAD Python. D5 STEP geometry is current. D3 copper is an
explicit historical reference, never a fabricated D5 layout or qualification.
"""
import argparse
import csv
import hashlib
import html
import json
import math
import os
import struct
import zipfile
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


class GLB:
    """Small glTF writer: OCCT tessellation in mm -> glTF right-handed Y-up m."""
    def __init__(self, scope):
        self.data = bytearray()
        self.doc = dict(asset=dict(version='2.0', generator='BF source-bound OCCT preview'),
                        scene=0, scenes=[dict(nodes=[], extras=dict(scope=scope))], nodes=[],
                        meshes=[], materials=[], accessors=[], bufferViews=[])

    def array(self, values, dtype, kind, target):
        import numpy as np
        v = np.asarray(values, dtype=dtype)
        while len(self.data) % 4:
            self.data.append(0)
        self.doc['bufferViews'].append(dict(buffer=0, byteOffset=len(self.data), byteLength=v.nbytes, target=target))
        self.data.extend(v.tobytes())
        a = dict(bufferView=len(self.doc['bufferViews'])-1,
                 componentType=5126 if dtype == '<f4' else 5125, count=len(v), type=kind)
        if kind == 'VEC3':
            a.update(min=v.min(axis=0).tolist(), max=v.max(axis=0).tolist())
        self.doc['accessors'].append(a)
        return len(self.doc['accessors'])-1

    def mesh(self, name, label, vertices, triangles, color, role='', offset=(0, 0, 0)):
        import numpy as np
        p = np.asarray(vertices, dtype=float)
        p = p[:, [0, 2, 1]] * [0.001, 0.001, -0.001]
        t = np.asarray(triangles, dtype=np.uint32)
        n = np.zeros_like(p)
        face = np.cross(p[t[:, 1]]-p[t[:, 0]], p[t[:, 2]]-p[t[:, 0]])
        for i in range(3):
            np.add.at(n, t[:, i], face)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        pos = self.array(p, '<f4', 'VEC3', 34962)
        normal = self.array(n, '<f4', 'VEC3', 34962)
        ix = self.array(t.flatten(), '<u4', 'SCALAR', 34963)
        mat = dict(name=label, pbrMetallicRoughness=dict(baseColorFactor=color, metallicFactor=.15, roughnessFactor=.48), doubleSided=True)
        if color[3] < 1:
            mat.update(alphaMode='BLEND')
        self.doc['materials'].append(mat)
        self.doc['meshes'].append(dict(name=name, primitives=[dict(attributes=dict(POSITION=pos, NORMAL=normal), indices=ix, material=len(self.doc['materials'])-1)]))
        self.doc['nodes'].append(dict(name=name, mesh=len(self.doc['meshes'])-1,
                                     extras=dict(label=label, role=role, explosionOffsetM=list(offset))))
        self.doc['scenes'][0]['nodes'].append(len(self.doc['nodes'])-1)

    def save(self, path):
        self.doc['buffers'] = [dict(byteLength=len(self.data))]
        text = json.dumps(self.doc, ensure_ascii=False, separators=(',', ':')).encode()
        text += b' ' * (-len(text) % 4)
        self.data.extend(b'\0' * (-len(self.data) % 4))
        path.write_bytes(struct.pack('<4sII', b'glTF', 2, 12+8+len(text)+8+len(self.data)) +
                         struct.pack('<I4s', len(text), b'JSON') + text +
                         struct.pack('<I4s', len(self.data), b'BIN\0') + self.data)


def mechanical(cad, out):
    import cadquery as cq
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from mpl_toolkits.mplot3d import proj3d
    out.mkdir(exist_ok=True)
    readback = json.loads((cad/'cad-readback.json').read_text())
    labels = {'housing': '外壳', 'lid': '透明上盖', 'beam': '铜梁 100 × 10 × 0.53 mm',
              'pzt': '压电片 50 × 8 × 0.30 mm', 'tip_magnet': '梁端磁体 10 mm',
              'driver_magnet': '驱动磁体 20 mm', 'clamp_lower': '下夹持座', 'clamp_upper': '上夹持座',
              'main_pcb': '80 × 30 mm 板位包络（待 D5 重布）', 'driver_bracket_vertical': '门侧支架',
              'driver_bracket_shelf': '磁体托架', 'driver_retainer': '磁体压板'}
    colors = {'housing': [.81,.84,.86,.22], 'lid': [.85,.91,.94,.14], 'beam': [.67,.40,.23,1],
              'pzt': [.27,.49,.48,1], 'tip_magnet': [.28,.31,.34,1], 'driver_magnet': [.28,.31,.34,1],
              'main_pcb': [.18,.35,.29,.7]}
    scope = 'D5 STEP 派生预览 · mm 原尺寸；板件是安装包络，不代表 D5 新电路已完成 PCB。'
    g = GLB(scope)
    parts, records = [], []
    for part in readback['parts']:
        key = part['id']; source = cad/(key+'.step')
        shape = cq.importers.importStep(str(source)).val()
        if not shape.isValid():
            raise ValueError('INVALID_BREP:'+key)
        bbox = shape.BoundingBox()
        sizes = [bbox.xlen, bbox.ylen, bbox.zlen]
        if max(abs(a-b) for a,b in zip(sizes, part['size_mm'])) > .015:
            raise ValueError('BREP_SIZE_DRIFT:'+key)
        verts, tris = shape.tessellate(.07, .16)
        verts = np.array([[p.x,p.y,p.z] for p in verts]); tris=np.asarray(tris)
        color=colors.get(key,[.65,.69,.73,1])
        offset = (0,.052,0) if key=='lid' or key.startswith('lid_fastener') else (0,-.038,0) if key=='main_pcb' or key.startswith('pcb_screw') else (.028,0,0) if key.startswith('driver') else (0,.021,0) if key in ('pzt','clamp_upper') else (0,0,0)
        role='housing' if key=='housing' else 'cover' if key=='lid' or key.startswith('lid_fastener') else 'component'
        g.mesh(key, labels.get(key, '紧固件 · '+key), verts, tris, color, role, offset)
        parts.append((key,verts,tris,color))
        records.append(dict(id=key,source=source.name,sha256=digest(source),size_mm=sizes,triangles=len(tris),valid=True))
    g.save(out/'mechanical-assembly.glb')
    # Native surfaces, simplified annotation; hidden shell is omitted explicitly.
    for exploded in (False, True):
        fig=plt.figure(figsize=(13,6.8),facecolor='white'); ax=fig.add_axes([.04,.12,.92,.72],projection='3d',computed_zorder=False)
        allverts=[]; centers={}
        for key,v,t,color in parts:
            if key=='housing' or key.startswith(('lid_fastener','pcb_screw','clamp_screw')) or (key=='lid' and not exploded):
                continue
            offset=np.array([0,0,46 if key=='lid' else -30 if key=='main_pcb' else 18 if key in ('pzt','clamp_upper') else 0]) if exploded else np.zeros(3)
            v=v+offset; allverts.append(v);centers[key]=v.mean(axis=0)
            ax.add_collection3d(Poly3DCollection(v[t],facecolor=(*color[:3],.55 if key=='lid' else 1),edgecolor='none',linewidth=0))
        vv=np.vstack(allverts);lo=vv.min(axis=0);hi=vv.max(axis=0)
        ax.set(xlim=(lo[0]-6,hi[0]+6),ylim=(lo[1]-5,hi[1]+5),zlim=(lo[2]-5,hi[2]+5))
        ax.set_box_aspect((hi-lo)+10);ax.view_init(elev=24,azim=-67);ax.set_axis_off()
        ax.set_proj_type('ortho');fig.canvas.draw()
        annotations=[('beam','01  Copper beam | 100 x 10 x 0.53 mm',.03,.73),('pzt','02  PZT patch | 50 x 8 x 0.30 mm',.03,.64),('clamp_upper','03  Bolted beam clamp',.03,.55),('main_pcb','04  PCB envelope | 80 x 30 x 1.6 mm',.03,.29),('tip_magnet','05  Tip magnet | 10 mm cube',.70,.75),('driver_magnet','06  Drive magnet | 20 mm cube',.70,.65),('driver_bracket_vertical','07  Door-side adjustable bracket',.70,.28)]
        for key,label,x,y in annotations:
            if key not in centers:continue
            xp,yp,_=proj3d.proj_transform(*centers[key],ax.get_proj())
            ax.annotate(label,xy=(xp,yp),xycoords='data',xytext=(x,y),textcoords='figure fraction',fontsize=9,color='#343c44',arrowprops=dict(arrowstyle='-',color='#8a959e',lw=.75),bbox=dict(fc='white',ec='none',alpha=.9,pad=2))
        fig.text(.045,.925,'D5 / '+('EXPLODED STRUCTURE' if exploded else 'MECHANICAL STRUCTURE'),size=20,weight='bold',color='#20262c')
        fig.text(.045,.875,'Native STEP surfaces | magnet centre spacing 46 mm | dimensions in millimetres',size=11,color='#53616c')
        fig.text(.045,.06,('Parts separated for viewing; offsets are not assembly positions. ' if exploded else 'Shell hidden to expose the mechanism. ')+'PCB envelope is not the D5 routed board.',size=10,color='#697680')
        name='mechanical-exploded' if exploded else 'mechanical-internal'
        fig.savefig(out/(name+'.svg'));fig.savefig(out/(name+'.png'),dpi=170);plt.close(fig)
    write_json(out/'mechanical-preview-receipt.json',dict(schema_version='bf-cad-preview-v1',units='mm',gltf_units='m',transform='(x,y,z) mm -> (x,z,-y)/1000 m',scope=scope,parts=records,
        previews=[dict(path=p.name,sha256=digest(p)) for p in sorted(out.glob('*')) if p.suffix in ('.glb','.svg','.png')]))
    return records


def pcb_reference(out):
    """Render archived routed geometry, retaining origin and revision on every view."""
    board=json.loads((out/'board.json').read_text()); copper=json.loads((out/'routed-copper.json').read_text())
    esc=lambda s:html.escape(str(s))
    width,height,thick=board['board_mm']
    parts={c['ref']:c for c in board['components']}
    for layers,stem,label in [(('F.Cu','B.Cu'),'pcb-combined','TOP + BOTTOM'),(('F.Cu',),'pcb-top','TOP LAYER'),(('B.Cu',),'pcb-bottom','BOTTOM LAYER (viewed from top)')]:
        svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 610"><rect width="1200" height="610" fill="#fff"/><g font-family="Arial,sans-serif" fill="#242b31"><text x="48" y="45" font-size="25" font-weight="bold">D3 HISTORICAL PCB / {label}</text><text x="48" y="78" font-size="15" fill="#6a747d">Actual archived copper · 80 x 30 mm · not the D5 SECE / reserve-gate layout</text></g><g transform="translate(80,140) scale(13,-13) translate(0,-30)">',f'<rect width="{width}" height="{height}" rx="1" fill="#143b30" stroke="#345f4c" stroke-width=".3"/>']
        k=board['rf_keepout_mm'];svg.append(f'<rect x="{k[0]}" y="{k[1]}" width="{k[2]-k[0]}" height="{k[3]-k[1]}" fill="#b4bcaa" opacity=".22" stroke="#dbe1c9" stroke-width=".1" stroke-dasharray=".5,.5"/>')
        for t in sorted(copper['tracks'],key=lambda x:x['layer']=='F.Cu'):
            if t['layer'] not in layers:continue
            pts=' '.join(f'{x},{y}' for x,y in t['points_mm'])
            svg.append(f'<polyline points="{pts}" fill="none" stroke="{"#d8a267" if t["layer"]=="F.Cu" else "#78afc0"}" stroke-width="{t["width_mm"]}" stroke-linejoin="round" stroke-linecap="round"><title>{esc(t["net"])} / {t["layer"]}</title></polyline>')
        for p in copper['pads']:
            if not set(layers).intersection(p['layers']):continue
            x,y=p['x'],p['y'];w,h=p['w'],p['h'];rx=min(w,h)/2 if p['shape'] in ('ELLIPSE','OVAL') else .015
            svg.append(f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="{rx}" transform="rotate({p["angle"]} {x} {y})" fill="#e5cc8b"><title>{esc(p["id"])} / {esc(p["net"])}</title></rect>')
            if p.get('drill'):svg.append(f'<circle cx="{x}" cy="{y}" r="{p["drill"]/2}" fill="#fff"/>')
        for v in copper['vias']:
            svg.append(f'<circle cx="{v["x"]}" cy="{v["y"]}" r="{v["diameter"]/2}" fill="#d9c38b"/><circle cx="{v["x"]}" cy="{v["y"]}" r="{v["drill"]/2}" fill="#fff"/>')
        for x,y,d in board['mounting_holes_mm']:svg.append(f'<circle cx="{x}" cy="{y}" r="{d/2}" fill="white" stroke="#e4d8bc" stroke-width=".1"/>')
        for c in board['components']:
            svg.append(f'<g transform="translate({c["x"]},{c["y"]+2.8}) scale(1,-1)"><text text-anchor="middle" font-family="Arial" font-size=".92" fill="white">{esc(c["ref"])}</text></g>')
        svg.append('</g><g font-family="Arial,sans-serif" fill="#57636c"><path d="M80 117H1120 M80 112V122 M1120 112V122" stroke="#819099"/><text x="600" y="111" text-anchor="middle" font-size="14">80 mm</text><text x="48" y="556" font-size="15">14 components · 89 routed paths · 9 vias · 81 pads · native ERC / DRC not qualified</text><text x="48" y="584" font-size="14">D5 requires new extraction components, gate circuitry and storage values. This board is for reference only.</text></g></svg>')
        (out/(stem+'.svg')).write_text(''.join(svg))
    # The archive contains pre-route placement records plus separate exact copper.
    # Reconstitute routed records, retaining the original JSON unchanged beside it.
    records=json.loads((out/'source-records.json').read_text())
    ticket=max(h.get('ticket',0) for h,v in records)
    def put(kind,value):
        nonlocal ticket
        ticket+=1
        records.append((dict(type=kind,id=hashlib.sha256(('restored-routing-'+str(ticket)).encode()).hexdigest()[:32],ticket=ticket),value))
    segments=0
    for t in copper['tracks']:
        for a,b in zip(t['points_mm'],t['points_mm'][1:]):
            put('LINE',dict(layerId=1 if t['layer']=='F.Cu' else 2,netName=t['net'],startX=a[0]/.0254,startY=a[1]/.0254,endX=b[0]/.0254,endY=b[1]/.0254,width=t['width_mm']/.0254,locked=False));segments+=1
    for v in copper['vias']:
        put('VIA',dict(layerId=12,netName=v['net'],centerX=v['x']/.0254,centerY=v['y']/.0254,holeDiameter=v['drill']/.0254,viaDiameter=v['diameter']/.0254,viaType=0,locked=False))
    for x,y,d in board['mounting_holes_mm']:
        put('PAD',dict(layerId=12,num='',netName='',centerX=x/.0254,centerY=y/.0254,padAngle=0,hole={'holeType':'ROUND','width':d/.0254,'height':d/.0254},defaultPad={'padType':'ELLIPSE','width':d/.0254,'height':d/.0254},plated=False,locked=True))
    text='\n'.join(json.dumps(h,separators=(',',':'))+'||'+json.dumps(v,ensure_ascii=False,separators=(',',':'))+'|' for h,v in records)+'\n'
    (out/'D3-restored.epru').write_text(text)
    with (out/'pcb-bom.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['revision','reference','part','LCSC','catalogue_url','package','x_mm','y_mm','scope'])
        for c in board['components']:
            w.writerow(['D3 historical',c['ref'],c['attrs'].get('Manufacturer Part'),c['lcsc'],'https://www.lcsc.com/product-detail/'+c['lcsc']+'.html',c['attrs'].get('Supplier Footprint') or ('2.54 mm header' if c['ref'].startswith('J') else c['attrs'].get('Value','未记录封装名称')),c['x'],c['y'],'Not the D5 circuit; stock snapshot 2026-10-03, not live availability'])
    # Copper and mounting geometry in the 3D view are real. Bodies are declared envelopes.
    import cadquery as cq
    g=GLB('D3 历史 PCB · 原始铜箔和安装孔；器件外形为封装包络。不是 D5 新版布线。')
    def solid(name,label,shape,color,role='component'):
        v,t=shape.tessellate(.06,.16);g.mesh(name,label,[[p.x,p.y,p.z] for p in v],t,color,role)
    b=cq.Workplane('XY').box(width,height,thick,centered=(False,False,False))
    for x,y,d in board['mounting_holes_mm']:
        b=b.cut(cq.Workplane('XY').center(x,y).circle(d/2).extrude(thick))
    solid('pcb','D3 / 80 × 30 × 1.6 mm 基板',b.val(),[.12,.30,.23,1])
    # Primitive geometry generation remains a display transform of the routed source.
    for idx,p in enumerate(copper['pads']):
        for layer in p['layers']:
            s=cq.Workplane('XY').box(p['w'],p['h'],.045).rotate((0,0,0),(0,0,1),p['angle']).translate((p['x'],p['y'],thick+.025 if layer=='F.Cu' else -.025)).val()
            solid('pad-'+p['id']+'-'+layer,p['id']+' / '+(p['net'] or 'NC'),s,[.74,.62,.35,1],'pad')
    for idx,t in enumerate(copper['tracks']):
        for j,(a,b) in enumerate(zip(t['points_mm'],t['points_mm'][1:])):
            dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
            if length<1e-8:continue
            s=cq.Workplane('XY').box(length,t['width_mm'],.035).rotate((0,0,0),(0,0,1),math.degrees(math.atan2(dy,dx))).translate(((a[0]+b[0])/2,(a[1]+b[1])/2,thick+.03 if t['layer']=='F.Cu' else -.03)).val()
            solid(f'track-{idx}-{j}',t['net']+' 铜箔',s,[.66,.44,.20,1],'copper')
    for i,v in enumerate(copper['vias']):
        ring=cq.Workplane('XY').center(v['x'],v['y']).circle(v['diameter']/2).circle(v['drill']/2).extrude(thick+.08).translate((0,0,-.04)).val()
        solid('via-'+str(i),v['net']+' 过孔',ring,[.74,.62,.35,1],'copper')
    for c in board['components']:
        ref=c['ref'];ps=[p for p in copper['pads'] if p['id'].startswith(ref+'-')]
        if not ps:continue
        if ref=='U2':sx,sy,h=28.7,17.5,2.0
        elif ref=='U1':sx,sy,h=3,3,1.1
        elif ref=='L1':sx,sy,h=4,4,1.8
        elif ref.startswith('J'):sx,sy,h=2.5,max(2.5,2.54*len(ps)),5
        else:
            sx=max(p['x']+p['w']/2 for p in ps)-min(p['x']-p['w']/2 for p in ps)
            sy=max(p['y']+p['h']/2 for p in ps)-min(p['y']-p['h']/2 for p in ps);sx*=.7;sy*=.7;h=.8
        s=cq.Workplane('XY').box(sx,sy,h).translate((c['x'],c['y'],thick+h/2)).val()
        solid(ref,ref+' · '+c['attrs'].get('Manufacturer Part','')+'（封装包络）',s,[.2,.22,.24,.9] if ref.startswith(('U','J','L')) else [.62,.55,.39,1])
    g.save(out/'pcb-reference.glb')
    write_json(out/'pcb-preview-receipt.json',dict(source_revision='D3.3-electronics',reference_only=True,
        geometry_source_sha256=digest(out/'routed-copper.json'),board_source_sha256=digest(out/'board.json'),
        board_mm=board['board_mm'],components=len(parts),tracks=len(copper['tracks']),vias=len(copper['vias']),pads=len(copper['pads']),
        native_erc=None,native_drc=None,manufacturing_released=False,
        component_models='Illustrative package envelopes; pad/track positions and widths from archived routing, with simplified display solids. Native routing records retained separately.',
        native_export='EPRU reconstructed from placement and exact routed-copper JSON; ground fills were not in retained source and are not invented. Live connector disconnected during read; no fresh save/reload or native DRC claimed.',
        reconstructed_track_segments=segments,reconstructed_vias=len(copper['vias']),ground_fill_restored=False))


def publish(output, base, state, owner):
    from types import SimpleNamespace
    from bfworld.agentlab.store import Store
    from bfworld.agentlab.product_results import ProductResults
    catalog=ProductResults(SimpleNamespace(store=Store(state)))
    with catalog.store.connect() as db:
        row=db.execute('SELECT payload FROM engineering_case_releases WHERE owner=? AND id=? AND version=?',(owner,'door-product-evidence','D5-selfpower')).fetchone()
    if not row:raise ValueError('D5_BASELINE_REQUIRED')
    m=json.loads(row['payload']);m['version']='D5.3';m['title']='门磁自供能 · 结构与 PCB 资料'
    for group in m['groups']:
        if group.get('evidence_story'):group['evidence_story']['baseline_version']=m['version']
        for f in group['files']:
            path=output/f['path'];source=base/f['path']
            if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);os.link(source,path)
            if digest(path)!=f['sha256']:raise ValueError('D5_SOURCE_CHANGED:'+f['path'])
    def file(path,label,sections):
        return dict(path=path,name=path.replace('/','--'),sha256=digest(output/path),label=label,sections=sections)
    design=next(g for g in m['groups'] if g['id']=='design')
    for n,label in [('mechanical-assembly.glb','三维装配 · 可旋转 / 内部 / 爆炸'),('mechanical-internal.svg','机构与尺寸'),('mechanical-exploded.svg','拆解结构'),('mechanical-preview-receipt.json','原生模型核对记录')]:
        design['files'].append(file('mechanical/'+n,label,['mechanical']))
    # Existing orthographic files become legible, without altering their bytes.
    for f in design['files']:
        if f['path'] in ['cad/top.svg','cad/front.svg','cad/side.svg']:
            f.update(label={'cad/top.svg':'俯视尺寸图','cad/front.svg':'正视尺寸图','cad/side.svg':'侧视尺寸图'}[f['path']],sections=['mechanical'])
    scope='D3.3 历史布线参考，80 × 30 mm；缺少 D5 的 SECE 提取器、MIC841L 门控和新储能配置，不能作为 D5 投板文件。原生 ERC/DRC 与制造未放行。'
    paths=[('pcb-combined.svg','双面布线 · D3 参考',['pcb']),('pcb-top.svg','顶层布线 · D3 参考',['pcb']),('pcb-bottom.svg','底层布线 · D3 参考',['pcb']),('pcb-reference.glb','PCB 三维 · D3 参考',['pcb']),('D3-restored.epru','立创 Pro 工程源码 · D3',['pcb']),('board.json','器件、焊盘与网络',['pcb']),('routed-copper.json','逐段铜箔与过孔',['pcb']),('pcb-bom.csv','PCB 物料 · D3 参考',['bom']),('pcb-preview-receipt.json','预览与版本核对',['pcb']),('restoration-receipt.json','小型归档恢复记录',['pcb'])]
    m['groups'].append(dict(id='pcb-reference',domain='circuit',kind='jlceda',title='PCB · 历史实体板参考',scope=scope,
        source_revision='D3.3-electronics',reference_only=True,design_status='insufficient_evidence',
        metrics=dict(parts=14,tracks=89,vias=9,pads=81),checks={'原生 ERC':None,'原生 DRC':None,'适配 D5 电路':False,'制造放行':False},files=[file('pcb-reference/'+n,l,s) for n,l,s in paths]))
    notes='''# 结构与 PCB 交付说明\n\n- 结构：由 D5 STEP 原生实体直接离散化为 GLB；可旋转、查看内部和爆炸分解。尺寸图及 STEP 保持原版本字节，模型预览不参与新的仿真判定。\n- PCB：恢复 D3.3 的真实 80 × 30 mm 双层布线（14 个元件，89 条走线路径，9 个过孔，81 个焊盘），提供顶层、底层、叠层、三维和立创 Pro EPRU 源码。三维器件外形为封装包络，铜箔和焊盘位置来自已归档真实布线，预览几何有简化。EPRU 由保留的布局及器件库记录合并独立铜箔数据重建；归档未保留铺铜，不虚构补回。当前未完成新一轮原生导入、ERC 或 DRC。\n- 版本边界：这块板不包含 D5 的 20 只 BAT46WJ、18 只均流电阻、提取电感及晶体管、MIC841L 和 BSS84 门控。D5 CIN 为 10 µF、COUT 为 15 µF，也与 D3 不同。它是布局与安装参考，不能投板作为 D5 的硬件实现。D5 的名义自供能仿真结论不能转移给 D3 PCB。\n- 现有 PCB 位尺寸仍是 80 × 30 × 1.6 mm 包络；D5 新板完成后需要重新做安装、间距、走线及寄生影响检查。\n- 所有 D5 六组图和独立审计原样保留。这次没有付费模型调用或原生联合计算，未声明新的物理/制造验收。\n'''
    (output/'STRUCTURE-PCB.zh.md').write_text(notes)
    with zipfile.ZipFile(output/'structure-pcb-supplement.zip','w',zipfile.ZIP_DEFLATED) as z:
        for folder in ('mechanical','pcb-reference'):
            for p in sorted((output/folder).iterdir()):
                if p.is_file():z.write(p,p.relative_to(output))
        z.write(output/'STRUCTURE-PCB.zh.md','README.zh.md')
    acceptance=next(g for g in m['groups'] if g['id']=='acceptance')
    acceptance['files'] += [file('STRUCTURE-PCB.zh.md','结构与 PCB 版本说明',['documents']),file('structure-pcb-supplement.zip','结构与 PCB 补充工程包',['documents'])]
    write_json(output/'supplement-manifest.json',m)
    saved=catalog.cases.publish(owner,output,m)
    write_json(output/'publication.json',dict(owner=owner,manifest=saved))
    return dict(owner=owner,version=m['version'],groups=len(m['groups']),files=sum(len(g['files']) for g in m['groups']),hardware_verified=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--state',type=Path);p.add_argument('--owner');p.add_argument('--publish-only',action='store_true')
    a=p.parse_args()
    if not a.publish_only:
        mechanical(a.base/'cad',a.output/'mechanical');pcb_reference(a.output/'pcb-reference')
    if a.state and a.owner:print(json.dumps(publish(a.output,a.base,a.state,a.owner),ensure_ascii=False))
