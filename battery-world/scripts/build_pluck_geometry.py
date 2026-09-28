#!/usr/bin/env python3
"""Dimensioned ViPSN geometry reference; not the 2025 MFC specimen."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--render',action='store_true');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    parts=[]
    for id,size,center,color in [('copper_beam',[100,10,.53],[50,0,0],[.75,.45,.23]),('pzt_patch',[50,8,.3],[35,0,.415],[.27,.39,.65]),('tip_magnet',[10,10,10],[100,0,5.265],[.35,.39,.43]),('driver_magnet',[20,20,20],[131,0,5.265],[.65,.68,.72]),('clamp_base',[18,30,8],[0,0,-4.265],[.3,.34,.4]),('clamp_top',[18,30,8],[0,0,4.265],[.3,.34,.4])]:
        parts.append({'id':id,'role':'mechanical','geometry':{'kind':'box','size_mm':size,'center_mm':center},'color':color,'source':{'basis':'ViPSN Table I plus explicitly assumed patch thickness and support placement'}})
    payload={'parts':parts,'allowed_contacts':[['copper_beam','clamp_base'],['copper_beam','clamp_top'],['copper_beam','pzt_patch'],['copper_beam','tip_magnet']],'description':'ViPSN 2021 geometry, separate from SMS2025 MFC identified specimen. Patch thickness0.3mm, clamp dimensions and positions assumed; not fabrication-qualified.'}
    (a.output/'input.json').write_text(json.dumps({'assembly':{'payload':payload}},indent=2))
    templates=ROOT/'packages/python/bfworld/src/bfworld/agentlab/engineering_templates'
    commands=[(['/Users/depengsu/Documents/bf-agent-workbench/toolchains/product-cad/bin/python','build_cad.py',str(a.output)],'product_cad.py','build_cad.py')]
    if a.render:commands.append((['/Applications/Blender.app/Contents/MacOS/Blender','--background','--python-exit-code','1','--python','build_blender.py','--',str(a.output)],'product_blender.py','build_blender.py'))
    for command,source,dest in commands:
        shutil.copy2(templates/source,a.output/dest)
        r=subprocess.run(command,cwd=a.output,capture_output=True,text=True,timeout=240)
        (a.output/(dest+'.log')).write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('GEOMETRY_COMMAND_FAILED:'+dest)
    for name in ['assembly.step','cad-readback.json']+(['model.blend','model.glb','preview.png'] if a.render else []):
        if not (a.output/name).is_file():raise RuntimeError('GEOMETRY_OUTPUT_MISSING:'+name)
    print(a.output)
if __name__=='__main__':main()
