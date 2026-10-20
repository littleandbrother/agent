#!/usr/bin/env python3
"""Build readable board views and a source-bound import from native readbacks."""
import argparse
import hashlib
import html
import json
from pathlib import Path

HARDWARE={
    'U1':('LTC3588EMSE-1#TRPBF',1.1,'ADI LTC3588-1 data sheet, MSOP package maximum height'),
    'U2':('E73-2G4M04S1B',2.6,'Ebyte E73 manual, dimensions 17.5 x 28.7 x 2.6 mm'),
    'C1':('T491X686M025AT, 68uF/25V',4.3,'KEMET T491 case X, maximum height'),
    'C2':('CL10A105KB8NNNC, 1uF/50V',1.0,'0603 conservative height allowance; verify supplier tolerance'),
    'C3':('CL10A475KO8NNNC, 4.7uF/16V',1.0,'0603 conservative height allowance; verify supplier tolerance'),
    'C4':('T520B227M006ATE025, 220uF/6.3V',2.1,'KEMET T520 case B maximum height'),
    'C5':('CC0603KRX7R9BB104, 100nF/50V',.9,'Yageo CC0603KRX7R9BB104 maximum height'),
    'L1':('SWPA4030S100MT, 10uH',3.0,'Sunlord SWPA4030 series maximum height'),
    'J1':('B-2100S03P-A110, 3 pin',8.5,'Library/header envelope allowance; verify against supplier drawing before enclosure design'),
    'J2':('B-2100S05P-A110, 5 pin',8.5,'Library/header envelope allowance; verify against supplier drawing before enclosure design'),
}


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(folder,system):
    read=lambda file:json.loads((folder/file).read_text())
    board=read('pcb-readback.json')['result']['components']
    dump=read('pcb-dump.json'); tracks=read('pcb-tracks.json')['result']['lines'];vias=read('pcb-vias.json')['result']['vias']
    geometry={'board_size_mm':[50,32,1.6],'coordinate_system':'PCB mil x/right y/up, converted to mm. Z above board top.',
        'representation':'Conservative native footprint bounds with sourced height; connector allowances remain open.',
        'components':[],'mount_holes_mm':[[x,y,3.2] for x in (3,47) for y in (3,29)],
        'antenna_keepout_mm':[43.6,6,50,25.5],
        'implementation_differences':['C1: 0.7 ohm ESR at100kHz; C4:25mOhm; L1:100mOhm nominal/130mOhm max. Reference used ideal capacitors and a different inductor resistance.',
            'Capacitance under bias, mounting compliance, module current, RF receive and connector envelope need bench or supplier confirmation.']}
    for c in board:
        ref=c['designator']; part,height,basis=HARDWARE[ref];b=c['bbox']
        geometry['components'].append({'ref':ref,'part':part,'height_mm':height,'height_basis':basis,
            'bounds_mm':[round(b[k]*.0254,6) for k in ('minX','minY','maxX','maxY')],
            'native_id':c['primitiveId'],'unique_id':c['uniqueId'],'pose_mm':[c['x']*.0254,c['y']*.0254,c['rotation']],
            'xy_basis':'pcb-readback.json rendered native footprint extent'})
    (folder/'geometry.json').write_text(json.dumps(geometry,ensure_ascii=False,indent=2))
    def view(side):
        scale=15;X=lambda x:70+(50-x if side=='bottom' else x)*scale;Y=lambda y:75+(32-y)*scale
        out=['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="650" viewBox="0 0 900 650">',
            '<rect width="900" height="650" fill="white"/>',
            f'<text x="70" y="28" font-family="sans-serif" font-size="20" fill="#183a50">50 x 32 mm | {side.upper()} | native copper readback</text>',
            '<rect x="70" y="75" width="750" height="480" rx="2" fill="#f2f6f3" stroke="#577563" stroke-width="2"/>']
        ko=geometry['antenna_keepout_mm'];left=min(X(ko[0]),X(ko[2]))
        out.append(f'<rect x="{left}" y="{Y(ko[3])}" width="{(ko[2]-ko[0])*scale}" height="{(ko[3]-ko[1])*scale}" fill="#fff4de" stroke="#bc964b" stroke-dasharray="5 4"/>')
        for c in geometry['components']:
            x0,y0,x1,y1=c['bounds_mm'];left=min(X(x0),X(x1));top=Y(y1)
            out.append(f'<rect x="{left}" y="{top}" width="{(x1-x0)*scale}" height="{(y1-y0)*scale}" fill="none" stroke="#a5b4ab" stroke-width="1"/>')
        for line in tracks:
            if line['layer']!=(1 if side=='top' else 2):continue
            out.append(f'<path d="M{X(line["startX"]*.0254):.3f} {Y(line["startY"]*.0254):.3f}L{X(line["endX"]*.0254):.3f} {Y(line["endY"]*.0254):.3f}" fill="none" stroke="{"#a65353" if side=="top" else "#487bac"}" stroke-width="{line["lineWidth"]*.0254*scale:.3f}" stroke-linecap="round"/>')
        for c in board:
            for pad in c['pads']:
                if pad['layer'] not in (1 if side=='top' else 2,12):continue
                x=X(pad['x']*.0254);y=Y(pad['y']*.0254);shape=pad['shape'];w=pad['width']*.0254*scale;h=pad['height']*.0254*scale
                out.append(f'<rect x="{x-w/2:.3f}" y="{y-h/2:.3f}" width="{w:.3f}" height="{h:.3f}" rx="{min(w,h)/2 if shape[0] in ("ELLIPSE","OVAL","ROUND") else 0}" fill="#c4b17d" stroke="#8d7e54" stroke-width="0.6"/>')
                hole=pad.get('holeDiameter',0)*.0254*scale
                if hole:out.append(f'<circle cx="{x}" cy="{y}" r="{hole/2}" fill="white"/>')
        for via in vias:
            x=X(via['x']*.0254);y=Y(via['y']*.0254)
            out.append(f'<circle cx="{x}" cy="{y}" r="{via["diameter"]*.0254*scale/2}" fill="#b9a46f"/><circle cx="{x}" cy="{y}" r="{via["holeDiameter"]*.0254*scale/2}" fill="white"/>')
        for x,y,_ in geometry['mount_holes_mm']:
            out.append(f'<circle cx="{X(x)}" cy="{Y(y)}" r="{1.6*scale}" fill="white" stroke="#7a8b83"/><circle cx="{X(x)}" cy="{Y(y)}" r="{3*scale}" fill="none" stroke="#a5b4ab" stroke-dasharray="3 4"/>')
        if side=='top':
            for c in geometry['components']:
                x0,y0,x1,y1=c['bounds_mm'];x=X((x0+x1)/2);y=Y((y0+y1)/2)
                out.append(f'<rect x="{x-16}" y="{y-10}" width="32" height="18" fill="white" fill-opacity="0.95"/><text x="{x}" y="{y+4}" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#234431">{html.escape(c["ref"])}</text>')
        out.append('<text x="70" y="590" font-family="sans-serif" font-size="14" fill="#41596a">Copper, pads, vias and holes: saved native board. Component boxes: conservative footprint extents.</text>')
        out.append('<text x="70" y="617" font-family="sans-serif" font-size="14" fill="#41596a">Antenna keepout shaded amber. Original project and full readback accompany this view.</text></svg>')
        return ''.join(out)
    (folder/'pcb.svg').write_text(view('top'));(folder/'pcb-bottom.svg').write_text(view('bottom'))
    if (folder/'bom.csv').read_bytes().startswith(b'\xff\xfe'):
        (folder/'bom.csv').write_text((folder/'bom.csv').read_text(encoding='utf-16'),encoding='utf-8-sig')
    files={str(f.relative_to(folder)):{'sha256':digest(f),'bytes':f.stat().st_size} for f in folder.rglob('*')
        if f.is_file() and f.suffix.lower() in ('.json','.svg','.csv','.epro2','.png','.txt') and f.name!='receipt.json'}
    receipt={'schema_version':'bf-node-native-v1','system_id':system['id'],'project_id':system['project_id'],
        'design_sha256':system['files']['design.json']['sha256'],'manifest_sha256':system['files']['notes/engineering-realization.json']['sha256'],
        'native_project_uuid':read('pcb-readback.json')['context']['projectUuid'],
        'schematic_document':read('schematic-readback.json')['context']['documentUuid'],
        'pcb_document':read('pcb-readback.json')['context']['documentUuid'],'files':files}
    (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--system',type=Path,required=True);a=p.parse_args()
    value=prepare(a.folder,json.loads(a.system.read_text()));print(json.dumps({'system_id':value['system_id'],'files':len(value['files'])}))
