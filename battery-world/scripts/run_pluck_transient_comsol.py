#!/usr/bin/env python3
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
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    # Batch Java cannot read arbitrary MPH paths under COMSOL's default file
    # policy. Rebuild the same frozen geometry instead of weakening that policy.
    baseline=(a.base.parent/'PluckCoupled.java').read_text()
    template=(ROOT/'configs/reference_cases/pluck-v1/PluckTransient.java').read_text()
    helpers=baseline[:baseline.index('  public static Model run()')].replace('public class PluckCoupled','public class PluckTransient')
    output=template[template.index('  static void output'):template.index('  public static Model run()')]
    create=baseline[baseline.index('    m=ModelUtil.create'):baseline.index('    m.study().create("stat")')]
    body=template[template.index('    m.param().set("RL"'):]
    source=helpers+output+'  public static Model run() throws Exception {\n'+create+'    m.component("comp1").mesh("mesh1").autoMeshSize(4);m.component("comp1").mesh("mesh1").run();\n'+body
    (out/'PluckTransient.java').write_text(source);shutil.copy2(__file__,out/Path(__file__).name)
    protocol={'base':str(a.base.resolve()),'base_sha256':hashlib.sha256(a.base.read_bytes()).hexdigest(),
        'load':'10 mN exp(-((t-.02)/.005)^2), magnet top; 100 kohm electrical load',
        'initial_state':'zero displacement, velocity and voltage','mechanical_damping':0,
        'scope':'Native 3D piezo/circuit transient test pulse, NOT reconstructed door motion or validated plucking.',
        'hardware_verified':False}
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2))
    for label,cmd,timeout in [('compile',[COMSOL,'compile',str(out/'PluckTransient.java')],90),('batch',[COMSOL,'-np','2','batch','-inputfile',str(out/'PluckTransient.class'),'-outputfile',str(out/'transient.mph'),'-batchlog',str(out/'solver.log')],1200)]:
        with (out/(label+'.log')).open('w') as log:r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        if r.returncode:raise RuntimeError(label.upper()+'_FAILED')
    text=(out/'batch.log').read_text();records={}
    for line in text.splitlines():
        if line.startswith('BF_TRANSIENT,'):
            row=line.split(',');records.setdefault(row[1],[]).append(list(map(float,row[2:])))
    if 'BF_TRANSIENT_COMPLETE' not in text:raise RuntimeError('INCOMPLETE_TRANSIENT')
    for key,rows in records.items():
        with (out/(key+'.csv')).open('w') as f:csv.writer(f).writerows(rows)
    rows=records['signal'];energy=sum((b[0]-a[0])*(b[2]+a[2])/2 for a,b in zip(rows,rows[1:]))
    report={'completed':True,'peak_voltage_v':max(abs(r[1]) for r in rows),'load_energy_j':energy,
        'peak_tip_displacement_m':max(abs(r[3]) for r in rows),'peak_stress_pa':max(r[1] for r in records['field']),
        'scope':protocol['scope'],'hardware_verified':False,'time_convergence_verified':False}
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
