"""Native tool runner. Never infer solver success from process exit alone."""
import argparse, hashlib, json, subprocess, time
from pathlib import Path

COMSOL='/Applications/COMSOL62/Multiphysics/bin/comsol'
def run_java(source, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source=Path(source).resolve(); target=output/source.name
    if target!=source: target.write_text(source.read_text().replace('__OUTPUT__',str(output.resolve())))
    receipt={'source_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'started':time.time(),'tool':'COMSOL 6.2'}
    for stage,args in [('compile',[COMSOL,'compile',str(target)]),('solve',[COMSOL,'-np','2','batch','-inputfile',str(target.with_suffix('.class')),'-outputfile',str(output/'model.mph'),'-batchlog',str(output/'solver.log')])]:
        receipt[stage+'_command']=args
        p=subprocess.run(args,cwd=output,capture_output=True,text=True,timeout=2400)
        (output/(stage+'.log')).write_text(p.stdout+p.stderr)
        receipt[stage+'_exit']=p.returncode
        if p.returncode: break
    receipt['completed']=any('BF_COMPLETE' in f.read_text(errors='replace') for f in [output/'solve.log',output/'solver.log'] if f.exists())
    receipt['finished']=time.time()
    (output/'native-receipt.json').write_text(json.dumps(receipt,indent=2))
    if not receipt['completed']:raise RuntimeError('NATIVE_SOLVER_INCOMPLETE: '+str(output))
    print(json.dumps(receipt))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');a=p.parse_args();run_java(a.source,a.output)
