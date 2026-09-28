"""Manual local adapter acceptance; no model or production session mutation."""
import json
import time
from pathlib import Path
from bfworld.agentlab.server import Workbench

root=Path('/Users/depengsu/Documents/bf-agent-workbench/verification/trace-engineering-smoke/state')
app=Workbench(root)
out={}
for engine in ('blender','comsol'):
    job=app.engineering.submit('operator',{'engine':engine,'operation_id':engine+'-'+str(time.time_ns())})
    while job['status'] in ('QUEUED','RUNNING'):
        time.sleep(1);job=app.engineering.get('operator',job['id'])
    out[engine]=job
    print(json.dumps({'engine':engine,'id':job['id'],'status':job['status'],'error':job['error'],'result':job['result']},ensure_ascii=False),flush=True)
(root.parent/'receipt.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
app.stop.set()
