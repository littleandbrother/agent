"""Sampled native BREP collision check of the actual mounted moving bracket."""
import argparse,json,math
from pathlib import Path
import cadquery as cq
def main():
    p=argparse.ArgumentParser();p.add_argument('case',type=Path);a=p.parse_args();d=a.case/'mechanical-D2';spec=json.loads((d/'input.json').read_text())['assembly']['payload'];fixed={};moving={}
    for part in spec['parts']:
        s=cq.importers.importStep(str(d/(part['id']+'.step'))).val().rotate((0,0,0),(0,1,1),180).translate((1004,70,2140))
        (moving if part['id'].startswith('driver_') else fixed)[part['id']]=s
    rows=[];collisions=[];minimum=(float('inf'),None)
    for angle in range(66):
        shapes={k:s.rotate((0,0,0),(0,0,1),angle) for k,s in moving.items()};best=float('inf')
        for mk,ms in shapes.items():
            for fk,fs in fixed.items():
                distance=ms.distance(fs);best=min(best,distance)
                if distance<1e-6:
                    volume=ms.intersect(fs).Volume()
                    if volume>1e-5:collisions.append(dict(angle_deg=angle,moving=mk,fixed=fk,overlap_mm3=volume))
                if distance<minimum[0]:minimum=(distance,dict(angle_deg=angle,moving=mk,fixed=fk))
        rows.append({'angle_deg':angle,'minimum_distance_mm':best})
    result=dict(method='OCCT BREP / sampled every 1 degree / 0..65 degrees',samples=rows,collisions=collisions,minimum_distance_mm=minimum[0],limiting_pair=minimum[1],scope='Rigid driver assembly versus fixed product solids only. Does not certify continuous swept clearance, flexing beam, wires, full building frame, or installation tolerance.')
    (d/'motion-clearance.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='samples'}))
if __name__=='__main__':main()
