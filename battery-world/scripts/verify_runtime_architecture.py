"""Bounded architecture regression. Uses temporary fixtures and stub providers.

Does not resume production conversations, run native product simulations, clear
ledgers or modify existing engineering artifacts. Logs are written to a fresh dir.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
PI=ROOT.parent/'pi-bf-aiot'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--include-monorepo-check',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'BF_PI_ROOT':str(PI),'PYTHONPATH':str(ROOT/'packages/python/bfworld/src')}
    python=str(ROOT/'.venv/bin/python')
    suites=['runtime_architecture','context_recovery','provider','recovery','launcher_recovery','deliverables','responsibility_eda','http','tool_responses','chat']
    tests=['tests.agentlab.test_'+x for x in suites]+[
        'tests.agentlab.test_product_authority.ProductAuthority.test_scoped_invalidation',
        'tests.agentlab.test_product_authority.ProductAuthority.test_same_verdict_everywhere_no_synthetic_hardware',
        'tests.agentlab.test_product_authority.ProductAuthority.test_native_outline_changes_stale_mechanical_delivery_without_rerunning_power']
    commands=[('python-regression',[python,'-m','unittest',*tests],ROOT),
              ('runtime-projection',['node','tests/agentlab/test_runtime_studio.cjs'],ROOT),
              ('pi-product-build',[str(PI/'node_modules/.bin/tsgo'),'-p','packages/bf-agent/tsconfig.json'],PI),
              ('pi-harness-build',[str(PI/'node_modules/.bin/tsgo'),'-p','packages/bf-harness/tsconfig.json'],PI)]
    validator=Path.home()/'.codex/skills/.system/skill-creator/scripts/quick_validate.py'
    if validator.is_file():
        commands += [('skill-'+p.parent.name,[python,str(validator),str(p.parent)],PI) for p in sorted((PI/'packages/bf-harness/resources/skills').glob('*/SKILL.md'))]
    if args.include_monorepo_check:commands.append(('monorepo-check',['npm','run','check'],PI))
    results=[]
    for name,command,cwd in commands:
        started=time.time()
        result=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,timeout=300)
        (args.output/(name+'.log')).write_text(result.stdout+result.stderr)
        results.append({'name':name,'command':command,'cwd':str(cwd),'exit_code':result.returncode,'seconds':round(time.time()-started,3)})
        print(name+': '+('passed' if result.returncode==0 else 'failed'),flush=True)
    value={'scope':'Architecture/software verification; stub model, no physical or autonomy qualification',
           'results':results,'targeted_passed':all(x['exit_code']==0 for x in results if x['name']!='monorepo-check'),
           'complete_repository_check_passed':any(x['name']=='monorepo-check' and x['exit_code']==0 for x in results)}
    (args.output/'report.json').write_text(json.dumps(value,indent=2)+'\n')
    return 0 if value['targeted_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
