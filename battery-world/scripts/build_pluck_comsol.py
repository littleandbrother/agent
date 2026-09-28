#!/usr/bin/env python3
"""Copper substrate static sanity check. Not a coupled piezoelectric FEM."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
COMSOL='/Applications/COMSOL62/Multiphysics/bin/comsol'

def source():
    s=(ROOT/'packages/python/bfworld/src/bfworld/agentlab/engineering_templates/Cantilever.java').read_text()
    for k,v in {'L':'100','B':'10','H':'0.53','E':'110','F':'0.01'}.items():s=s.replace('__'+k+'__',v)
    return s.replace('7800[kg/m^3]','8960[kg/m^3]')

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--source-only',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);java=a.output/'Cantilever.java';java.write_text(source())
    if a.source_only:return
    logs=[]
    for command in ([COMSOL,'compile',str(java.resolve())],[COMSOL,'-np','2','batch','-inputfile',str(java.with_suffix('.class').resolve()),'-outputfile',str((a.output/'beam.mph').resolve()),'-batchlog',str((a.output/'solver.log').resolve())]):
        result=subprocess.run(command,cwd=a.output,capture_output=True,text=True,timeout=180)
        logs.append(result.stdout+result.stderr);(a.output/'process.log').write_text('\n'.join(logs))
        if result.returncode:raise RuntimeError('COMSOL_PROCESS_FAILED')
    combined='\n'.join(logs)+(a.output/'solver.log').read_text()
    metrics={m[0]:list(map(float,m[1:])) for m in re.findall(r'BF_METRICS,(coarse|fine),([0-9.eE+-]+),([0-9.eE+-]+)',combined)}
    # COMSOL batch appends the Java model tag to the requested basename.
    if not (a.output/'beam.mph').is_file():
        models=list(a.output.glob('beam_*.mph'))
        if len(models)==1:models[0].rename(a.output/'beam.mph')
    if set(metrics)!={'coarse','fine'} or not (a.output/'beam.mph').is_file():raise RuntimeError('COMSOL_OUTPUT_MISSING')
    if not all(math.isfinite(v) and v>0 for row in metrics.values() for v in row):raise ValueError('COMSOL_NONFINITE')
    analytic=.01*.1**3/(3*110e9*(.01*.00053**3/12));coarse=metrics['coarse'][0];fine=metrics['fine'][0]
    receipt={'scope':'ViPSN copper-substrate static stiffness only; excludes PZT, magnets and dynamics','parameters':{'L_mm':100,'b_mm':10,'t_mm':.53,'E_GPa':110,'tip_force_N':.01},'youngs_modulus_origin':'engineering copper assumption','metrics':metrics,'analytical_displacement_m':analytic,'checks':{'mesh_change_under_5_percent':abs(coarse-fine)/fine<.05,'analytic_error_under_10_percent':abs(fine-analytic)/analytic<.1},'hardware_verified':False}
    (a.output/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))

if __name__=='__main__':main()
