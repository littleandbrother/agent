#!/usr/bin/env python3
"""Read-only reproducibility check; no subprocess or scientific solve."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'src'))
from run_diagnostics import seal_check,bind_cases,plan
from event_apparatus_v2 import read_channels
from causal_evaluator_v2 import evaluate
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
seal_check();receipt=json.loads((ROOT/'DIAGNOSTIC-RESULT.json').read_text());cases={}
assert receipt['complete'] and receipt['scientific_runs_started']==receipt['scientific_runs_completed']==12
for name,record in receipt['cases'].items():
    out=ROOT/'runs'/name
    for filename,key in [('input.json','input_sha256'),('input.cir','deck_sha256'),('out.tsv','output_sha256')]:
        assert sha(out/filename)==record[key],(name,filename)
    cases[name]={'rows':read_channels(out/'out.tsv'),'spec':json.loads((out/'input.json').read_text()),'max_step_s':record['max_step_s']}
bind_cases(cases)
actual=evaluate(plan,cases);saved=json.loads((ROOT/'EVALUATION-RESULT.json').read_text())
assert actual==saved,'EVALUATOR_RESULT_MISMATCH'
old=json.loads((ROOT/'source-binding.json').read_text())['source_files']
assert all(sha(Path(p))==h for p,h in old.items()),'UPSTREAM_CHANGED'
print(json.dumps({'retained_results_reproduced':True,'scientific_solves':0,'cases_verified':len(cases),'checks':actual['checks'],'upstream_sources_unchanged':True},indent=2))
