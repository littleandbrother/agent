#!/usr/bin/env python3
"""Materialize and reproduce five executable coupled controls."""
import json
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.coupled.engine import execute,reference_cases
from bfworld.coupled.artifacts import seal_run,verify_bundle
from bfworld.coupled.independent import circuit_check
from bfworld.kernel.canonical import write_canonical_json

def main():
    cases=[]
    for name,(design,reference) in reference_cases().items():
        run=execute(design,reference)
        root=seal_run(REPO/'runs/coupled',run)
        report=verify_bundle(root,reproduce=True)
        cases.append({'id':name,'path':str(root.relative_to(REPO)),'content_hash':run['content_hash'],'verification':report,'physical_mission_pass':run['physical_mission_pass']})
    independent=circuit_check()
    if independent['status']=='fail':raise RuntimeError('independent circuit gate failed')
    report={'status':'pass' if independent['status']=='pass' else 'partial','cases':cases,'independent_circuit_check':independent,
            'formal_agent_experiment':False,'hidden_qualification':False,'hardware_confirmation':False}
    write_canonical_json(REPO/'docs/coupled/validation.json',report)
    print(json.dumps({'status':report['status'],'cases':len(cases),'cross_solver_error_v':independent.get('maximum_absolute_error_v')}))
if __name__=='__main__':main()
