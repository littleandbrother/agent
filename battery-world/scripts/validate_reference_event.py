#!/usr/bin/env python3
"""No-Agent, no-model calibration and reproducible artifact receipt."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bfworld.agentlab.server import Workbench
from bfworld.agentlab import event_design
from bfworld.agentlab.store import identity
from tests.agentlab.test_reference_event import fixture

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
reports={}
with tempfile.TemporaryDirectory(prefix='bf-reference-validation-') as tmp:
    root=Path(tmp);(root/'paid-window-closed.json').write_text('{}')
    app=Workbench(root/'state')
    try:
        for name,force in [('sufficient',2),('insufficient',.001)]:
            out=args.output/name;out.mkdir(exist_ok=False)
            spec=fixture(force)
            job={'event_spec':spec,'event_spec_sha256':identity(spec),'id':name,'owner':'calibration'}
            result=event_design.run(app.engineering,job,out,time.monotonic()+90)
            reports[name]={k:result[k] for k in ('event_spec_sha256','checks','computational_checks_passed','hardware_verified','fine')}
        assert reports['sufficient']['computational_checks_passed']
        assert not reports['insufficient']['checks']['simulated_event_in_deadline']
    finally:
        app.stop.set();app.thread.join(3);app.lock.close()
manifest={str(p.relative_to(args.output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.rglob('*') if p.is_file()}
receipt={'schema_version':'bf-reference-event-calibration-v1','created':time.time(),'model_calls':0,'reports':reports,
         'artifacts':manifest,'hardware_verified':False,'scope':'Generic apparatus fixtures, not a designed product. Never seeded into Pi.'}
(args.output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
print(json.dumps({'passed':True,'model_calls':0,'receipt':str(args.output/'receipt.json'),'hardware_verified':False}))
