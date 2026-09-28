#!/usr/bin/env python3
"""Execute native 3D COMSOL and retain failures without relaxing assertions."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
COMSOL='/Applications/COMSOL62/Multiphysics/bin/comsol'

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'configs/reference_cases/pluck-v1/PluckCoupled.java';shutil.copy2(source,out/source.name)
    protocol={'geometry':'ViPSN-size CAD candidate, free copper x=4..100 mm, partial PZT x=10..60 mm; 10 mm cubic tip mass',
        'PZT':'COMSOL 6.2 PZT-5A library, assumed grade, 0.3 mm assumed thickness; poling +z',
        'copper':'E=110 GPa, nu=.34, rho=8960 kg/m3, assumed',
        'magnet':'E=160 GPa, nu=.25, rho=7500 kg/m3, assumed; magnetostatics not included',
        'load':'1 mN z-force, top magnet surface; R=100k and 1M ohm, 5:2:45 Hz',
        'mechanical_damping':'zero; only coupled electrical load dissipates energy',
        'mesh':'auto size6 and4 static; finest used for eigen/frequency',
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'library_sha256':hashlib.sha256(Path('/Applications/COMSOL62/Multiphysics/data/comsol_piezo_lib.mph').read_bytes()).hexdigest(),
        'scope':'Linear electromechanical candidate verification; NOT calibrated magnetic plucking, nonlinear impact, adhesive or prototype acceptance.',
        'hardware_verified':False,'wall_limit_seconds':1200}
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2))
    shutil.copy2(__file__,out/'run_pluck_coupled_comsol.py')
    for name,cmd,timeout in [('compile',[COMSOL,'compile',str(out/source.name)],90),('batch',[COMSOL,'-np','2','batch','-inputfile',str(out/'PluckCoupled.class'),'-outputfile',str(out/'coupled.mph'),'-batchlog',str(out/'solver.log')],1200)]:
        with (out/(name+'.log')).open('w') as log:r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        if r.returncode:raise RuntimeError(name.upper()+'_FAILED: '+str(out/(name+'.log')))
    text=(out/'batch.log').read_text()+'\n'+(out/'solver.log').read_text()
    records={}
    for line in text.splitlines():
        if line.startswith('BF_DATA,'):
            row=line.split(',');value=list(map(float,row[2:]));records.setdefault(row[1],[])
            if value not in records[row[1]]:records[row[1]].append(value)
    if 'BF_COMPLETE,PluckCoupled' not in text:raise RuntimeError('COMSOL_DID_NOT_COMPLETE')
    for key,rows in records.items():
        with (out/(key+'.csv')).open('w') as f:csv.writer(f).writerows(rows)
    report={'records':records,'scope':protocol['scope'],'native_solver_completed':True,'hardware_verified':False,
        'mesh_relative_change':abs(records['static0'][0][0]-records['static1'][0][0])/records['static1'][0][0],
        'magnetic_plucking_validated':False,'paper_calibrated':False}
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
