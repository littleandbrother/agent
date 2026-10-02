"""Serial, identity-bound development comparisons and candidate lineage."""
import argparse
import difflib
import json
import shutil
import time
from pathlib import Path
from .launcher import HOME_ROOT,PI,freeze,launch,filehash,world_binding
from .store import Store,canonical,identity
from .experiments import task,VARIANTS

ROOT=HOME_ROOT/'studies'/'dev-v1'

def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(canonical(value));tmp.replace(path)

def register(harness,arm):
    ROOT.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((Path(harness)/'manifest.json').read_text())
    protocol={'study':'dev-v1','arm':arm,'harness':manifest,'tasks':[f'dev-{i:02}' for i in range(1,9)],'repetitions':2,
      'task_bindings':{f'dev-{i:02}':identity({'public':task(f'dev-{i:02}'),'conditions':VARIANTS[f'dev-{i:02}']}) for i in range(1,9)},
      'world_binding':world_binding(),'primary_metric':'fraction of trials with externally sealed passing design',
      'secondary_metrics':['first-valid elapsed seconds','all model cost peak-rate upper bound','invalid jobs','repeated snapshot jobs'],
      'promotion_rule':'No promotion from build alone. Compare all matched trials. Descriptive engineering qualification only; no statistical efficacy claim.',
      'failure_rule':'All attempted runs including unavailable assets, infrastructure errors, no submission and candidate build failures remain in the denominator.',
      'transfer_tasks':['transfer-01','transfer-02'],'transfer_feedback':'Never supplied to improvers or development selection.',
      'paid_limit_usd':2.90,'per_request_limit_usd':.19,'claim_boundary':'Computational development study, 2 repeats, not official benchmark or hardware/RSI efficacy evidence.'}
    path=ROOT/(arm+'-protocol.json')
    if path.exists() and json.loads(path.read_text())!=protocol:raise ValueError('STUDY_PROTOCOL_DRIFT')
    save(path,protocol)
    return protocol

def metrics(receipt):
    store=Store(HOME_ROOT/'state');owner=receipt['owner'];jobs=store.jobs(owner)
    with store.connect() as db:
        rows=[dict(r) for r in db.execute('SELECT status,charged,reserved,usage FROM model_requests WHERE owner=?',(owner,))]
    passing=[j for j in jobs if j['status']=='SUCCEEDED' and j['result']['design_status']=='PASS']
    submission=receipt.get('submission');submitted=store.get(owner,submission['job_id'])['result'] if submission else None
    not_evaluated=any(a['status']=='NOT_AVAILABLE' for a in task(receipt['task_id'])['required_assets']) or any('NOT_EVALUATED' in (j.get('error') or '') for j in jobs)
    snapshots=[j['request'].get('snapshot_id') for j in jobs]
    return {'owner':owner,'task_id':receipt['task_id'],'status':receipt['status'],
      'outcome':'NOT_EVALUATED' if not_evaluated else ('PASS' if submitted and submitted['design_status']=='PASS' else 'FAIL'),
      'submitted':bool(submitted),'sealed_run_id':submitted['run_id'] if submitted else None,
      'first_valid_s':min(j['updated'] for j in passing)-receipt.get('previous_attempts',[{'started':receipt['started']}])[0]['started'] if passing else None,
      'wall_s':receipt.get('ended',time.time())-receipt['started']+sum(a['ended']-a['started'] for a in receipt.get('previous_attempts',[])),
      'elapsed_including_pause_s':receipt.get('ended',time.time())-receipt.get('previous_attempts',[{'started':receipt['started']}])[0]['started'],
      'attempt_count':1+len(receipt.get('previous_attempts',[])),'model_requests':len(rows),
      'cost_upper_bound_usd':sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows),
      'unknown_provider_usage':any(r['status']=='UNKNOWN' for r in rows),'experiments':len(jobs),
      'invalid_jobs':sum(j['status']=='FAILED' for j in jobs),'repeated_snapshot_jobs':len(snapshots)-len(set(snapshots)),
      'activation':receipt['harness']['identity'],'trace_hash':receipt['trace_hash'],
      'loaded_modules':receipt['harness']['loaded_modules'],'claim_boundary':'Outcome derives from external submission and immutable run, never assistant success text.'}

def evaluate(harness,arm,tasks=None,repeats=2):
    protocol=register(harness,arm)
    report_path=ROOT/(arm+'-results.json')
    results=json.loads(report_path.read_text()) if report_path.exists() else []
    for task_id in tasks or protocol['tasks']:
        for repeat in range(1,repeats+1):
            owner=f'pi-study-{arm}-{task_id}-r{repeat}'
            if any(r['owner']==owner for r in results):continue
            existing=HOME_ROOT/'sessions'/owner/'receipt.json'
            if existing.exists():
                receipt=json.loads(existing.read_text())
                if receipt['status']=='RUNNING':raise ValueError('STUDY_PENDING_RUN_REQUIRES_RECONCILIATION')
            else:
                receipt=launch(harness,task_id,label=owner)
            row=metrics(receipt);results.append(row);save(report_path,results)
            print(canonical({'arm':arm,**row}),flush=True)
            if row['unknown_provider_usage']:raise ValueError('STUDY_PROVIDER_USAGE_UNKNOWN_STOP')
            with Store(HOME_ROOT/'state').connect() as db:
                spent=db.execute('SELECT SUM(CASE WHEN status=\'SETTLED\' THEN charged ELSE reserved END) FROM model_requests').fetchone()[0] or 0
            if spent>=2.75:raise ValueError('STUDY_REMAINING_BUDGET_TOO_SMALL')
    return results

def experience(arms):
    output=[]
    store=Store(HOME_ROOT/'state')
    for arm in arms:
        path=ROOT/(arm+'-results.json')
        if not path.exists():continue
        for metric in json.loads(path.read_text()):
            owner=metric['owner'];jobs=store.jobs(owner)
            trace=[]
            for line in (HOME_ROOT/'sessions'/owner/'trace.jsonl').read_text().splitlines():
                event=json.loads(line)
                if event['type'] in ['message','tool_execution_start','reconciled','session_complete']:trace.append(event)
            output.append({'metrics':metric,'jobs':[{k:j[k] for k in ['id','operation','status','error','request']} for j in jobs],
              'verified_results':[{k:v for k,v in j['result'].items() if k not in ['channels','policy','decisions']} for j in jobs if j['result']],
              'public_trace':trace})
    return output

def propose(parent,arms,label,mutable=('solver.ts','improver.ts'),continuation_owner=None,feedback=None,public_experience=None):
    data=experience(arms) if public_experience is None else public_experience
    receipt=launch(parent,mode='improve',experience=data,label=continuation_owner or 'pi-improve-'+label,mutable=mutable,resume=bool(continuation_owner),feedback=feedback)
    workspace=Path(receipt['workspace']);stage=ROOT/'candidates'/label
    (stage/'src').mkdir(parents=True,exist_ok=False)
    diffs=[];changed=[]
    for name in ['solver.ts','improver.ts']:
        old=(Path(parent)/'src'/name).read_text();new=(workspace/'harness'/name).read_text()
        if old!=new:
            changed.append(name)
        (stage/'src'/name).write_text(new)
        diffs.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='parent/'+name,tofile='candidate/'+name))
    (stage/'change.patch').write_text(''.join(diffs))
    record={'label':label,'parent':json.loads((Path(parent)/'manifest.json').read_text())['identity'],
      'improver_process':receipt['owner'],'changed_files':changed,'origin':'AUTONOMOUS_PI','status':'UNQUALIFIED',
      'public_experience_hash':identity(data),'mutable':list(mutable),'process_status':receipt['status'],
      'candidate_note_present':(workspace/'candidate-note.md').exists(),
      'extra_cost_scope':'All improver calls are in the shared model ledger, including failed attempts.'}
    if (workspace/'candidate-note.md').exists():shutil.copyfile(workspace/'candidate-note.md',stage/'candidate-note.md')
    if any(name not in mutable for name in changed):
        record['status']='OUTSIDE_MUTATION_SCOPE';save(stage/'candidate.json',record);return None
    if not changed:
        record['status']='NO_OP';save(stage/'candidate.json',record);return None
    try:
        candidate=freeze(stage,label)
        record['harness_path']=str(candidate);record['identity']=json.loads((candidate/'manifest.json').read_text())['identity'];record['status']='BUILT_NOT_QUALIFIED'
    except Exception as exc:
        record['status']='BUILD_FAILED';record['error']=str(exc);save(stage/'candidate.json',record);return None
    save(stage/'candidate.json',record)
    return candidate

def compare(parent_arm,child_arm):
    pa=json.loads((ROOT/(parent_arm+'-protocol.json')).read_text());pb=json.loads((ROOT/(child_arm+'-protocol.json')).read_text())
    for field in ['task_bindings','world_binding','tasks','repetitions']:
        if pa[field]!=pb[field]:raise ValueError('COMPARISON_PROTOCOL_MISMATCH:'+field)
    for field in ['app_build_hash','pi_lock_hash','tools','thinking','session_caps','resource_hashes']:
        if pa['harness'][field]!=pb['harness'][field]:raise ValueError('COMPARISON_BOUNDARY_MISMATCH:'+field)
    a=json.loads((ROOT/(parent_arm+'-results.json')).read_text());b=json.loads((ROOT/(child_arm+'-results.json')).read_text())
    key=lambda r:(r['task_id'],r['owner'].rsplit('-r',1)[1])
    am={key(r):r for r in a};bm={key(r):r for r in b};pairs=[]
    expected={(t,str(i)) for t in pa['tasks'] for i in range(1,pa['repetitions']+1)}
    if set(am)-expected or set(bm)-expected:raise ValueError('UNDECLARED_COMPARISON_TRIAL')
    if len(am)!=len(a) or len(bm)!=len(b):raise ValueError('DUPLICATE_COMPARISON_TRIAL')
    for k in sorted(expected):
        x,y=am.get(k),bm.get(k)
        pairs.append({'task':k[0],'repeat':k[1],'parent':x,'child':y,
          'pass_delta':int(y['outcome']=='PASS')-int(x['outcome']=='PASS') if x and y else None,
          'cost_delta_usd':y['cost_upper_bound_usd']-x['cost_upper_bound_usd'] if x and y else None})
    complete=bool(pairs) and all(p['parent'] and p['child'] for p in pairs)
    report={'parent':parent_arm,'child':child_arm,'complete_pairs':complete,'pairs':pairs,
      'parent_pass':sum(r['outcome']=='PASS' for r in a),'child_pass':sum(r['outcome']=='PASS' for r in b),
      'parent_total':len(a),'child_total':len(b),'parent_cost_upper_usd':sum(r['cost_upper_bound_usd'] for r in a),'child_cost_upper_usd':sum(r['cost_upper_bound_usd'] for r in b),
      'promotion':'NOT_PROMOTED','claim':'Descriptive small-sample comparison only; source activation is distinct from a benefit or meta-improvement.'}
    save(ROOT/(parent_arm+'-vs-'+child_arm+'.json'),report)
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['evaluate','propose','compare']);parser.add_argument('--harness',type=Path);parser.add_argument('--arm',default='h0');parser.add_argument('--parent',default='h0');parser.add_argument('--tasks',nargs='*');parser.add_argument('--repeats',type=int,default=2)
    args=parser.parse_args()
    if args.mode=='evaluate':evaluate(args.harness or freeze(label='H0'),args.arm,args.tasks,args.repeats)
    elif args.mode=='propose':print(propose(args.harness,[args.parent],args.arm))
    else:print(canonical(compare(args.parent,args.arm)))

if __name__=='__main__':main()
