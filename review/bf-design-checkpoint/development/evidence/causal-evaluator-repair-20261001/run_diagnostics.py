#!/usr/bin/env python3
"""Execute the sealed 12-cell plan once; never tune, retry or overwrite a run."""
import copy, datetime, hashlib, json, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'src'))
import event_apparatus_v2 as a
import causal_evaluator_v2 as e
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,indent=2)+'\n')
def seal_check():
    for filename in ['PLAN-SEAL.json','RUNNER-SEAL.json']:
        data=json.loads((ROOT/filename).read_text())
        for path,digest in data['files'].items():
            if sha(ROOT/path)!=digest:raise ValueError('FROZEN_SOURCE_CHANGED:'+path)
def expected_spec(mode,load):
    spec=json.loads((ROOT/'contracts/base-fixture-v2.json').read_text())
    spec['control']['feedback_mode']=mode;spec['workload']['idle_current_a']=plan['idle_current_a'][load]
    return a.validate(spec)
def bind_cases(cases):
    for mode in plan['feedback_modes']:
        for load in plan['idle_current_a']:
            for i,step in enumerate(plan['max_steps_s']):
                name=f'{mode}-{load}-{i}';c=cases[name]
                if c['spec']!=expected_spec(mode,load) or c['max_step_s']!=step:
                    raise ValueError('CASE_INPUT_IDENTITY_MISMATCH:'+name)
    if len(cases)!=plan['maximum_scientific_solves']:raise ValueError('CASE_COUNT_MISMATCH')
plan=json.loads((ROOT/'contracts/prospective-plan-v2.json').read_text())
if __name__=='__main__':
    seal_check()
    target=ROOT/'DIAGNOSTIC-RESULT.json'
    if target.exists() or any((ROOT/'runs').iterdir()):raise SystemExit('Refusing repeat/overwrite; prior run state exists')
    spice=Path(plan['solver']['path'])
    version=subprocess.run([str(spice),'--version'],capture_output=True,text=True,check=True)
    if '44.2' not in version.stdout+version.stderr:raise SystemExit('Solver version mismatch')
    (ROOT/'reports/ngspice-version.txt').write_text(version.stdout+version.stderr)
    receipt={'schema_version':'bf-causal-12cell-receipt-v2','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'plan_sha256':sha(ROOT/'contracts/prospective-plan-v2.json'),'plan_seal_sha256':sha(ROOT/'PLAN-SEAL.json'),
        'runner_seal_sha256':sha(ROOT/'RUNNER-SEAL.json'),'solver_path':str(spice),'solver_sha256':sha(spice),
        'python_version':sys.version,'scientific_runs_started':0,'scientific_runs_completed':0,'cases':{},'complete':False,
        'paid_calls':0,'commercial_solver_runs':0,'production_files_changed':False}
    write(target,receipt);cases={}
    try:
        for mode in plan['feedback_modes']:
            for load in plan['idle_current_a']:
                for i,step in enumerate(plan['max_steps_s']):
                    seal_check()
                    if sha(spice)!=receipt['solver_sha256']:raise ValueError('SOLVER_CHANGED')
                    name=f'{mode}-{load}-{i}';spec=expected_spec(mode,load)
                    out=ROOT/'runs'/name;out.mkdir(exist_ok=False)
                    write(out/'input.json',spec);deck=a.netlist(spec,step,'out.tsv');(out/'input.cir').write_text(deck)
                    if json.loads((out/'input.json').read_text())!=expected_spec(mode,load):raise ValueError('INPUT_CHANGED')
                    c={'feedback_mode':mode,'load_condition':load,'max_step_s':step,'input_sha256':sha(out/'input.json'),
                        'deck_sha256':sha(out/'input.cir'),'command':[str(spice),'-n','-b','input.cir'],'cwd':str(out)}
                    receipt['cases'][name]=c;receipt['scientific_runs_started']+=1;write(target,receipt)
                    now=time.monotonic()
                    with (out/'process.log').open('w') as f:
                        proc=subprocess.run(c['command'],cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=plan['per_run_timeout_s'])
                    c.update(returncode=proc.returncode,wall_seconds=time.monotonic()-now);write(target,receipt)
                    if proc.returncode:raise RuntimeError('SOLVER_FAILED:'+name)
                    rows=a.read_channels(out/'out.tsv')
                    if abs(rows[-1]['time_s']-plan['duration_s'])>1e-12:raise ValueError('TRANSIENT_INCOMPLETE:'+name)
                    c.update(row_count=len(rows),final_time_s=rows[-1]['time_s'],output_sha256=sha(out/'out.tsv'))
                    cases[name]={'rows':rows,'spec':spec,'max_step_s':step}
                    receipt['scientific_runs_completed']+=1;write(target,receipt)
                    print(name, 'complete',len(rows),'rows',round(c['wall_seconds'],3),'seconds',flush=True)
        seal_check();bind_cases(cases)
        result=e.evaluate(plan,cases);write(ROOT/'EVALUATION-RESULT.json',result)
        receipt['evaluation_sha256']=sha(ROOT/'EVALUATION-RESULT.json');receipt['complete']=True
        old=json.loads((ROOT/'source-binding.json').read_text())['source_files']
        receipt['upstream_sources_unchanged']=all(sha(Path(p))==h for p,h in old.items())
        receipt['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();write(target,receipt)
        print(json.dumps({'checks':result['checks'],'effects_m':result['effects_m'],'margin_m':result['causal_required_margin_m']},indent=2),flush=True)
    except BaseException as exc:
        receipt['stop_reason']=str(exc);write(target,receipt);raise
