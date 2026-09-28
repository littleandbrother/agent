#!/usr/bin/env python3
"""OCCT clearance check for the candidate; kinematic envelope, not dynamics."""
import argparse
import json
from pathlib import Path
import shutil
import cadquery as cq

def run(source,out):
    out.mkdir(parents=True,exist_ok=False)
    spec=json.loads((source/'input.json').read_text())['assembly']['payload']
    solids={p['id']:cq.Shape.importBrep(str(source/(p['id']+'.brep'))) for p in spec['parts']}
    records=[]
    # Continuous swept union for a pure translation. This is conservative for
    # tip-magnet rotation, which is still unmodelled and explicitly unqualified.
    for name,axis,travel,obstacles in [
        ('tip_magnet','z',15,['housing','lid','main_pcb','power_envelope','radio_envelope','storage_envelope']),
        ('driver_magnet','z',100,['housing','lid','beam','pzt','tip_magnet','main_pcb'])]:
        part=next(p for p in spec['parts'] if p['id']==name);g=part['geometry'];size=g['size_mm'][:];size[2]+=2*travel
        envelope=cq.Workplane('XY').box(*size).val().translate(g['center_mm'])
        for obstacle in obstacles:
            volume=envelope.intersect(solids[obstacle]).Volume()
            distance=envelope.distance(solids[obstacle])
            records.append({'moving':name,'obstacle':obstacle,'axis':axis,'travel_mm':[-travel,travel],
                'intersection_mm3':volume,'clearance_mm':distance,'clear':volume<.1 and distance>=.25})
    for name in ['tip_magnet','driver_magnet']:
        # Save the actual swept-check shape as an inspectable STEP.
        part=next(p for p in spec['parts'] if p['id']==name);size=part['geometry']['size_mm'][:];size[2]+=30 if name=='tip_magnet' else 200
        shape=cq.Workplane('XY').box(*size).val().translate(part['geometry']['center_mm'])
        cq.exporters.export(shape,str(out/(name+'-swept.step')))
    read=json.loads((source/'cad-readback.json').read_text())
    report={'schema_version':'bf-pluck-candidate-clearance-v1','source':str(source),'units':'mm',
        'static_interference_free':not read['collisions'],'sweep_results':records,
        'translational_sweeps_clear':all(r['clear'] for r in records),
        'wall_nominal_mm':2,'wall_tolerance_assumed_mm':.25,'wall_minimum_measured':False,
        'full_mechanical_acceptance':False,'hardware_verified':False,
        'limitations':['Tip rotation and full deformed beam surface not evaluated.',
            '±15 mm is a candidate envelope, not the uncalibrated SMS peak displacement.',
            'PCB/component shapes are reserved envelopes, not native PCB exports.',
            'No screw preload, adhesive, fatigue, tool-access, thermal or antenna qualification.']}
    (out/'clearance.json').write_text(json.dumps(report,indent=2))
    shutil.copy2(__file__,out/'check_pluck_product.py')
    print(json.dumps({'static_interference_free':report['static_interference_free'],'translational_sweeps_clear':report['translational_sweeps_clear'],'minimum_clearance_mm':min(r['clearance_mm'] for r in records)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.source,a.output)
