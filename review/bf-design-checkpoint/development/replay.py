#!/usr/bin/env python3
"""Recheck immutable files, 152 bounded test cases and retained results; no solve.

Requires Python 3.11, jsonschema and a host C compiler for exact replay. No installation,
network, commercial tool, model provider, upstream init or ngspice call occurs.
"""
from pathlib import Path
import argparse, datetime, hashlib, json, os, re, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parent
E=ROOT/'evidence'
WORLD=E/'authoritative-world-20261001'
EVALUATOR=E/'causal-evaluator-repair-20261001'
PROTOCOL=E/'controlled-agent-protocol-20261001'
REVIEW=E/'world-evaluator-independent-review-20261001'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def verify():
    manifest=ROOT/'FILE-MANIFEST.json'
    if not manifest.exists():raise SystemExit('FILE-MANIFEST.json required')
    checkpoint=ROOT/'CHECKPOINT-RECEIPT.json'
    if checkpoint.exists():
        pinned=json.loads(checkpoint.read_text())
        for name,key in [('FILE-MANIFEST.json','file_manifest_sha256'),('SHA256SUMS.txt','sha256sums_sha256')]:
            if sha(ROOT/name)!=pinned[key]:raise SystemExit('Checkpoint manifest mismatch: '+name)
    records=json.loads(manifest.read_text())['files']
    for row in records:
        p=ROOT/row['path']
        if not p.is_file() or p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:
            raise SystemExit('Immutable evidence mismatch: '+row['path'])
    return len(records)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verify-only',action='store_true')
    a=parser.parse_args()
    count=verify()
    if a.verify_only:
        print(json.dumps({'verified_files':count,'scientific_solves':0}));return
    if sys.version_info[:2]!=(3,11):
        raise SystemExit('Exact retained-result replay requires Python 3.11; Python 3.12 exact equality was not verified. Integrity-only mode remains available.')
    output=a.output or Path(tempfile.mkdtemp(prefix='bf-checkpoint-replay-'))
    if a.output:output.mkdir(parents=True,exist_ok=False)
    adapter=ROOT/'tools/replay_entry.py'
    cases=[
      ('world-producer',WORLD/'tests/test_authoritative_world.py',[],0,43),
      ('world-independent',REVIEW/'tests/audit_world.py',[str(WORLD)],0,15),
      ('evaluator-producer',EVALUATOR/'tests/test_causal_evaluator.py',[],0,None),
      ('rail-producer',EVALUATOR/'tests/test_rail_contract.py',[],0,None),
      ('runner-producer',EVALUATOR/'tests/test_runner_bindings.py',[],0,None),
      ('protocol-producer',PROTOCOL/'test_preflight.py',[],0,36),
      ('protocol-independent',REVIEW/'tests/audit_protocol.py',[],0,9),
      ('pipeline-handoff-v2-producer',WORLD/'pipeline-handoff-v2/test_handoff.py',[],0,14),
      ('pipeline-handoff-v2-independent',REVIEW/'tests/audit_pipeline_handoff_v2.py',[],0,6),
      ('world-source-verification',WORLD/'src/authoritative_world.py',['verify','--originals'],0,None),
      ('evaluator-retained-readback',EVALUATOR/'verify_retained_evidence.py',[],0,None),
      ('world-bound-protocol-blocked',PROTOCOL/'preflight.py',[str(PROTOCOL/'protocol-world-bound-draft.json')],2,None),
    ]
    outcomes=[];total=0
    for name,script,args,expected,n in cases:
        command=[sys.executable,'-B',str(adapter),str(script),*args]
        proc=subprocess.run(command,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=180)
        text=proc.stdout+proc.stderr;(output/(name+'.log')).write_text(text)
        found=re.findall(r'Ran (\d+) tests? in',text)
        tests=int(found[-1]) if found else 0
        ok=proc.returncode==expected and (n is None or tests==n)
        if name=='evaluator-retained-readback':
            r=json.loads(proc.stdout) if proc.returncode==0 else {}
            ok=ok and r.get('retained_results_reproduced') is True and r.get('cases_verified')==12
        if name=='world-bound-protocol-blocked':
            r=json.loads(proc.stdout) if proc.returncode==2 else {}
            ok=ok and r.get('live_launch_allowed') is False and r.get('contract_complete') is False
            ok=ok and r==json.loads((PROTOCOL/'receipts/world-bound-preflight.json').read_text())
        total+=tests
        outcomes.append({'name':name,'returncode':proc.returncode,'expected_returncode':expected,'tests':tests,'passed':ok,'log':name+'.log'})
        print(name,proc.returncode,'PASS' if ok else 'FAIL',flush=True)
    verified_after=verify()
    result={'schema':'bf-checkpoint-portable-replay-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'all_passed':all(r['passed'] for r in outcomes) and total==152,'test_cases_passed':total,
            'checks':outcomes,'files_verified_before':count,'files_verified_after':verified_after,
            'scientific_solves':0,'provider_calls':0,'full_upstream_init_run':False,
            'original_source_paths_redirected_to_exact_included_copies':True,
            'python_open_guard_rejects_original_source_reads':True,
            'independent_evaluator_recomputed_in_original_review_not_rerun_here':True,
            'ngspice_binary_included':False,'python':sys.version,'platform':sys.platform}
    (output/'REPLAY-RECEIPT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result['all_passed']:raise SystemExit(1)

if __name__=='__main__':main()
