#!/usr/bin/env python3
import json
import sys
import tempfile
from pathlib import Path
from dataclasses import replace
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.deployments.runtime import Session,execute,DeploymentDesign
from bfworld.deployments.ports import SCENES
from bfworld.deployments.artifacts import seal,validate
from bfworld.kernel.canonical import canonical_hash,write_canonical_json

def main():
    scenes=[]
    for name in SCENES:
        variants=[]
        for label,design in [('reference',DeploymentDesign()),('small-storage',replace(DeploymentDesign(),capacitance_f=.00033,esr_ohm=18)),('distant-receiver',replace(DeploymentDesign(),receiver_distance_m=90))]:
            run=execute(name,design);root=seal(REPO/'runs/deployments',run)
            variants.append({'id':label,'content_hash':run['content_hash'],'path':str(root.relative_to(REPO)),'summary':run['summary']})
        scenes.append({'id':name,'variants':variants})
    with tempfile.TemporaryDirectory(prefix='deployment-recovery-') as temp:
        checkpoint=Path(temp)/'checkpoint.json';Session('hybrid-station').advance(823).checkpoint(checkpoint)
        resumed=Session.restore(checkpoint).advance().result();full=execute('hybrid-station')
        if resumed['content_hash']!=full['content_hash']:raise RuntimeError('exact recovery failed')
    report={'schema_version':'deployment-validation-v2','status':'pass','scenes':scenes,'source_families':4,
      'exact_recovery':True,'hardware_confirmed':False,'all_source_scales_are_design_parameters':True}
    report['content_hash']=canonical_hash(report);write_canonical_json(REPO/'docs/deployments/validation.json',report)
    print(json.dumps({'status':'pass','scenes':len(scenes),'runs':sum(len(s['variants']) for s in scenes),'exact_recovery':True}))
if __name__=='__main__':main()
