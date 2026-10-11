#!/usr/bin/env python3
"""Local qualification runner: no paid inference and no new analog solves.

Run with PYTHONPATH=packages/python/bfworld/src; --native runs real sandboxed C.
Use an approved host execution when macOS prohibits nested sandbox-exec.
"""
import argparse,json,os,subprocess,sys,time
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--native',action='store_true')
parser.add_argument('--output',type=Path)
args=parser.parse_args()
out=args.output or REPO/'docs/agentlab/refactor-r0-r2-20261011/verification'/('run-'+str(time.time_ns()))
out.mkdir(parents=True,exist_ok=False)
env={**os.environ,'PYTHONPATH':str(REPO/'packages/python/bfworld/src')}
tests=['test_design_lab.py','test_design_resources.py','test_unbounded_budget.py',
       'test_context_recovery.py','test_context_compact.py','test_recovery.py',
       'test_launcher_recovery.py','test_native_recovery.py','test_runtime_architecture.py']
if args.native:tests.append('test_design_execution.py')
for test in tests:
    if not (REPO/'tests/agentlab'/test).is_file():raise RuntimeError('REQUIRED_TEST_MISSING:'+test)
commands=[(t,[sys.executable,'-m','unittest','discover','-s','tests/agentlab','-p',t,'-v'],REPO) for t in tests]
pi=REPO.parent/'pi-bf-aiot'
commands.append(('bf-agent-types',[str(pi/'node_modules/.bin/tsgo'),'-p','packages/bf-agent/tsconfig.json'],pi))
commands.append(('design-review-js',['node','--check','apps/agent-studio/design-lab.js'],REPO))
results=[]
for name,argv,cwd in commands:
    start=time.time()
    with (out/(name+'.log')).open('w') as log:
        r=subprocess.run(argv,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
    item={'name':name,'argv':argv,'cwd':str(cwd),'exit_code':r.returncode,'elapsed_s':time.time()-start}
    results.append(item);print(json.dumps(item),flush=True)
report={'scope':'BF R0-R2 finite C apparatus','model_calls':0,'new_native_solver_calls':0,
        'passed':all(r['exit_code']==0 for r in results),'checks':results,
        'full_repository_health':'NOT_GRANTED; root init and old SDK baseline tracked separately'}
(out/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'passed':report['passed'],'report':str(out/'report.json')}))
sys.exit(0 if report['passed'] else 1)
