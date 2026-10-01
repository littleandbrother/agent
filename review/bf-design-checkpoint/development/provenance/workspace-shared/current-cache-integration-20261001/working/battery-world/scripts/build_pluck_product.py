#!/usr/bin/env python3
"""Full packaging candidate around ViPSN reference dimensions, not paper FEM.

Produces editable CadQuery input/source, native STEP/readback, fabrication
drawings and assembly BOM. Electronic blocks are declared reserved envelopes
until bound to an actual EasyEDA board. Never certifies a manufacturing release.
"""
import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CAD = '/Users/depengsu/Documents/bf-agent-workbench/toolchains/product-cad/bin/python'
TEMPLATES = ROOT/'packages/python/bfworld/src/bfworld/agentlab/engineering_templates'


def definition():
    parts = []
    def add(key, size, center, role, material, source, cuts=(), kind='box', color=(.5,.55,.6)):
        parts.append({'id':key, 'name':key, 'role':role, 'material':material,
            'geometry':{'kind':kind, 'size_mm':size, 'center_mm':center, 'cutouts':list(cuts)},
            'color':list(color), 'source':{'basis':'design-assumption','note':source}})
    def hole(x,y,z,h=100,d=3.4):
        return {'kind':'cylinder','size_mm':[d,d,h],'center_mm':[x,y,z]}
    holes = [(-17,-24),(105,-24),(-17,24),(105,24)]
    # All cut coordinates are local to the enclosing solid.
    inner = {'kind':'box','size_mm':[132,58,68],'center_mm':[0,0,4]}
    add('housing',[136,62,66],[44,0,0],'housing','PETG, prototype only','2 mm nominal walls; no ingress rating',
        [inner]+[hole(x-44,y,0) for x,y in holes],color=(.76,.79,.82))
    add('lid',[136,62,2],[44,0,34],'cover','clear polycarbonate, assumed','removable top; M3 clearance',
        [hole(x-44,y,0) for x,y in holes],color=(.35,.5,.6))
    for i,(x,y) in enumerate(holes):
        add('lid_post_'+str(i),[7,7,63],[x,y,1.5],'mount','PETG','3.4 mm through clearance; insert fastening remains provisional',[hole(0,0,0,d=3.4)])
        add('lid_fastener_'+str(i),[3,3,8],[x,y,30],'connector','M3 nylon','envelope only; no thread model',kind='cylinder')
    add('beam',[100,10,.53],[50,0,0],'input','copper','ViPSN Table I beam dimensions; assumed support at x=0',color=(.72,.41,.2))
    add('pzt',[50,8,.3],[35,0,.415],'input','PZT, exact grade unknown','ViPSN length/width; thickness 0.3 mm ASSUMED',color=(.22,.37,.63))
    add('tip_magnet',[10,10,10],[100,0,5.265],'input','NdFeB, grade unknown','ViPSN dimensions; polarization must be physically marked')
    add('driver_magnet',[20,20,20],[126,0,5.265],'input','NdFeB, grade unknown','ViPSN dimensions; candidate center separation 26 mm')
    add('driver_carrier',[5,32,32],[138.5,0,5.265],'mount','PETG','door-side separate carrier; screws outside magnet',[hole(0,12,0,d=3.4),hole(0,-12,0,d=3.4)])
    # Beam clamp holes lie outside the copper strip; adhesive is NOT assumed to carry clamp preload.
    clamp_holes=[hole(0,-10,0),hole(0,10,0)]
    add('clamp_lower',[14,30,7],[-3,0,-3.765],'mount','PETG','clamp length 4 mm on beam; compliance not simulated',clamp_holes)
    add('clamp_upper',[14,30,7],[-3,0,3.765],'mount','PETG','M3 clamp, preload to be qualified',clamp_holes)
    for i,y in enumerate((-10,10)):
        add('clamp_screw_'+str(i),[3,3,16],[-3,y,0],'connector','M3 nylon','envelope, no thread',kind='cylinder')
        add('clamp_column_'+str(i),[8,8,22.735],[-3,y,-18.6325],'mount','PETG','supports lower clamp',[hole(0,0,0)])
    add('main_pcb',[80,20,1.6],[45,-17,-22],'pcb','FR4 1.6 mm','RESERVED BOARD ENVELOPE; not an exported routed board',
        [hole(x-45,y+17,0,d=2.4) for x,y in [(10,-23),(80,-23),(10,-11),(80,-11)]],color=(.1,.35,.22))
    for i,(x,y) in enumerate([(10,-23),(80,-23),(10,-11),(80,-11)]):
        add('pcb_post_'+str(i),[5,5,7.2],[x,y,-26.4],'mount','PETG','M2 screw pilot; PCB bottom z=-22.8',[hole(0,0,0,d=1.6)])
    add('power_envelope',[23,14,5],[28,-17,-18.7],'power','component reservation','LTC3588/interface reserved space, no footprint qualification',color=(.22,.25,.28))
    add('radio_envelope',[18,12,2],[61,-17,-20.2],'controller','component reservation','nRF52832 module option not yet selected',color=(.2,.23,.26))
    add('storage_envelope',[8,8,10],[46,-17,-16.2],'storage','component reservation','capacitor envelope assumed, not selected part',kind='cylinder')
    for i,x in enumerate((-14,94)):
        add('frame_mount_'+str(i),[12,12,4],[x,36,-29],'mount','PETG','M3 frame mounting ear',[hole(0,0,0)])
    # Printed supports are one fused body, not overlapping independent parts.
    housing=parts[0]
    integral=[part for part in parts if part['id'].startswith(('lid_post_','frame_mount_','clamp_column_','pcb_post_'))]
    housing['geometry']['additions']=[]
    for part in integral:
        geom=dict(part['geometry']);geom['center_mm']=[geom['center_mm'][0]-44,*geom['center_mm'][1:]]
        housing['geometry']['additions'].append(geom)
    parts=[part for part in parts if part not in integral]
    return {'units':'mm','title':'ViPSN-size door detector packaging candidate', 'parts':parts,
        'required_roles':['housing','cover','mount','input','pcb','controller','power','storage'],
        'allowed_contacts':[], 'requirements':['All new dimensions are provisional design assumptions.', 'Reference geometry is not the identified SMS MFC specimen.'],
        'interfaces':['Driver moves in z; magnetic centers separated 26 mm in x.', 'PCB reserved rectangle 80 x 20 mm; actual native PCB mapping pending.'],
        'assumptions':['PZT thickness 0.3 mm; PETG fit tolerance ±0.25 mm; moving q envelope ±15 mm.', 'No IP rating, adhesive strength, fatigue or RF acceptance.'],
        'energy':{'basis':'unqualified; do not reuse SMS parameters as CAD-calibrated values'},'presentation':{'camera_deg':35}}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--render',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);payload=definition()
    (a.output/'input.json').write_text(json.dumps({'assembly':{'payload':payload}},indent=2))
    shutil.copy2(__file__,a.output/'product_definition.py')
    # This versioned derived builder supports positive unions before subtraction.
    # Housing inner cavity is cut BEFORE adding supports, so supports survive.
    source=(TEMPLATES/'product_cad.py').read_text().replace('    return shape\n', '    for addition in g.get("additions", []):\n        shape = shape.fuse(transform(primitive(addition), addition))\n    return shape\n',1)
    (a.output/'build_cad.py').write_text(source)
    r=subprocess.run([CAD,'build_cad.py',str(a.output)],cwd=a.output,capture_output=True,text=True,timeout=240)
    (a.output/'cad.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('CAD_FAILED')
    with (a.output/'mechanical-bom.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['part','quantity','material','size_mm','position_mm','basis','tolerance'])
        for part in payload['parts']:
            w.writerow([part['id'],1,part['material'],part['geometry']['size_mm'],part['geometry']['center_mm'],part['source']['note'],'±0.25 mm plastic; purchased parts per supplier TBD'])
    read=json.loads((a.output/'cad-readback.json').read_text())
    # Dimension schedule is bound to OCCT readback, not manually typed renders.
    rows=['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="%d">'%(150+len(read['parts'])*25),'<rect width="100%" height="100%" fill="white"/>','<g font-family="Arial" font-size="15" fill="#202630">','<text x="24" y="35">CAD dimension schedule — mm — provisional design, not manufacturing release</text>','<text x="24" y="70">Part                              X / Y / Z envelope                        Center</text>']
    for i,part in enumerate(read['parts']):
        g=payload['parts'][i]['geometry'];rows.append(f'<text x="24" y="{105+i*25}">{part["id"]}</text><text x="340" y="{105+i*25}">{" / ".join(f"{x:.3f}" for x in part["size_mm"])}</text><text x="700" y="{105+i*25}">{g["center_mm"]}</text>')
    (a.output/'dimensions.svg').write_text('\n'.join(rows+['</g></svg>']))
    (a.output/'ASSEMBLY.md').write_text('''# 装配候选与边界

1. 先确认压电片、铜梁与磁体实物尺寸。PZT 厚度/牌号、磁体牌号仍未确认。
2. 夹持端 x=-10..4 mm，铜梁从 x=0 开始；实际有效自由长度与论文模型必须重新识别。
3. 粘接 PZT 和磁体前标记极化/磁化方向。胶层厚度与强度尚待确定，当前为无厚度界面。
4. 框侧底壳通过两侧耳固定；夹持柱支持下夹具，两颗 M3 夹紧。不得让螺钉穿过铜梁。
5. PCB 为 80×20×1.6 mm 空间预留，四孔中心 (10,-23),(80,-23),(10,-11),(80,-11) mm；并未证明与真实板卡一致。
6. 在独立门侧安装驱动磁体；中心 x=126 mm，沿 z 运动；运动扫掠不得与外壳接触。
7. 顶盖为可拆件。M3 尼龙螺钉、胶、嵌件和公差需样件确认；目前没有防水或疲劳等级。

设计尺寸以 input.json 为源，build_cad.py 重建 STEP/STL/BREP，cad-readback.json 是原生读回。
此版本完成包装候选，电子占位不是实际 PCB 装配；不能拿旧 SMS 数值当本几何的已校准结果。
''')
    if a.render:
        shutil.copy2(TEMPLATES/'product_blender.py',a.output/'build_blender.py')
        r=subprocess.run(['/Applications/Blender.app/Contents/MacOS/Blender','--background','--factory-startup','--python-exit-code','1','--python','build_blender.py','--',str(a.output)],cwd=a.output,capture_output=True,text=True,timeout=240)
        (a.output/'blender.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('BLENDER_FAILED')
    print(json.dumps({'path':str(a.output),'parts':len(payload['parts']),'collisions':read['collisions'],'release_ready':False}))


if __name__=='__main__':main()
