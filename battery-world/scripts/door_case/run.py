"""Verify the case inventory or reproduce an explicitly selected native stage."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--stage',default='verify',choices=['verify','report','rom','spice','cad','clearance','firmware','comsol-beam','comsol-magnetic'])
    p.add_argument('--output',type=Path);p.add_argument('--cad-python');p.add_argument('--sdk-case',type=Path)
    a=p.parse_args();r=a.root.resolve();here=Path(__file__).resolve().parent;app=here.parents[1]
    if a.stage=='verify':
        m=json.loads((r/'case-files.json').read_text());bad=[]
        for item in m['files']:
            f=r/item['path']
            if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=item['sha256']:bad.append(item['path'])
        result={'files':len(m['files']),'mismatches':bad,'integrity_pass':not bad,'engineering_verdict':json.loads((r/'report/verification.json').read_text())['overall']}
        print(json.dumps(result));return 1 if bad else 0
    if a.stage in ['rom','spice']:
        cmd=[sys.executable,str(here/('coupled.py' if a.stage=='rom' else 'power.py')),str(r)]
    elif a.stage=='report':
        subprocess.run([sys.executable,str(here/'report.py'),'--root',str(r)],check=True)
        for _ in range(2):subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error','door-case.tex'],cwd=r/'report',check=True)
        return 0
    elif a.stage in ['cad','clearance']:
        if not a.cad_python:p.error('--cad-python must name the CadQuery environment')
        cmd=[a.cad_python,str(here/('build_cad.py' if a.stage=='cad' else 'clearance.py')),str(a.output or r/'mechanical-D2')]
        if a.stage=='clearance':cmd[-1]=str(r)
    elif a.stage=='firmware':
        if not a.output or not a.sdk_case:p.error('firmware requires a new --output and --sdk-case containing pinned upstream')
        cmd=[sys.executable,str(here/'build_firmware.py'),'--home',str(a.sdk_case),'--output',str(a.output)]
    else:
        if not a.output:p.error('native COMSOL rerun requires a separate --output directory')
        name='DoorBeam.java' if a.stage=='comsol-beam' else 'DoorMagnetic.java'
        cmd=[sys.executable,str(here/'native.py'),str(app/'configs/reference_cases/door-magnetic-v1'/name),str(a.output)]
    subprocess.run(cmd,check=True);return 0
if __name__=='__main__':raise SystemExit(main())
