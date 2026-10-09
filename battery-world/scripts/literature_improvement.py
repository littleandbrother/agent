#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from bfworld.agentlab.literature_improvement import prepare,run,audit
from bfworld.agentlab.literature_campaign import DEFAULT_ROOT
p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','audit','run']);p.add_argument('--root',type=Path,default=DEFAULT_ROOT);a=p.parse_args()
result=prepare(a.root) if a.command=='prepare' else run(a.root) if a.command=='run' else audit(a.root/'learning/native-generation-v1')
print(json.dumps({k:result.get(k) for k in ['schema_version','status','no_agent_reference','production_adopted','recursive_self_improvement_claim']},ensure_ascii=False))
