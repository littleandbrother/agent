#!/usr/bin/env python3
import json
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.campaign.audit import audit
from bfworld.kernel.canonical import write_canonical_json
if __name__=='__main__':
 p=REPO/'docs/campaign/report.json'
 if not p.exists():print(json.dumps({'status':'not-run','paid_calls':0}))
 else:
  result=audit(json.loads(p.read_text()));write_canonical_json(REPO/'docs/campaign/audit.json',result);print(json.dumps(result))
