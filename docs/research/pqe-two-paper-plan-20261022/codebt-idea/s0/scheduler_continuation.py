"""Only the two previously selected tool-error inputs, under common repair."""
import gzip,json,subprocess,time
from pathlib import Path
import science as s
from datetime import datetime
h=s.host

def read(p):return json.loads(p.read_text())
def main():
    marker=s.HERE/'scheduler-continuation-start.json'
    if marker.exists():raise RuntimeError('ONE_SCHEDULER_CONTINUATION_ONLY')
    deadline=datetime.fromisoformat(read(s.HERE/'episodes/debt_agent/owner.json')['activated_at']).timestamp()+900
    assert time.time()<deadline
    fix=read(s.OUT/'a/SCHEDULER-FIX-RECEIPT.json')
    protocol=read(s.PROTOCOL);before=s.ref(s.PROTOCOL)
    sources=s.adapter.source_identity();diff={k:(v,sources.get(k)) for k,v in protocol['sources'].items() if sources.get(k)!=v}
    assert diff=={'codebt/consumer.py':(fix['old_sha256'],fix['new_sha256'])}
    protocol['original_science_sources']=protocol['sources'];protocol['sources']=sources
    protocol['common_scheduler_amendment']=dict(at=s.now(),receipt=s.ref(s.OUT/'a/SCHEDULER-FIX-RECEIPT.json'),original_protocol_ref=before,original_errors_retained=True,old_initials_not_rerun=True,all_future_groups_share_repaired_consumer=True,authority='Reviewer 11:15 UTC explicitly admits corrected-consumer new calls for the same originally chosen Debt and mixed designs, within original caps/deadline.')
    s.save(s.PROTOCOL,protocol)
    ledger=read(s.HERE/'science-resource-ledger.json')
    family=read(Path(protocol['family_ref']['path']))['conditions']
    requests={}
    for group,prefix in [('mixed_joint','04-'),('debt_agent','05-')]:
        folder=next((s.HERE/'science').glob(prefix+'*'))
        requests[group]=read(folder/'input.json')
    originals={str(p.relative_to(s.ROOT)):s.ref(p) for p in [s.HERE/'science/04-mixed_joint-short-cold/input.json',next((s.HERE/'science').glob('05-*/input.json'))]}
    s.save(marker,dict(at=s.now(),deadline_utc=datetime.fromtimestamp(deadline,s.timezone.utc).isoformat(),original_inputs=originals,consumer_sources=sources,new_model_requests=0,new_owners_episodes=0,initials_rerun=0,maximum_new_full_inputs=6))
    out={}
    try:
        # Both are already-selected designs; no Generate or strategy change.
        for group in ['mixed_joint','debt_agent']:
            req=requests[group];results=[];errors=[]
            for t in family:
                remaining=deadline-time.time()
                if remaining<=1:errors.append('ORIGINAL_ABSOLUTE_DEADLINE');break
                assert ledger['new_full_inputs']<63 and ledger['full_wall_s']+min(120,remaining)<=7560
                i=ledger['new_full_inputs']+1;ledger['new_full_inputs']+=1
                folder=s.HERE/'science'/f'{i:02d}-{group}-scheduler-fixed-{t["condition_id"]}'
                folder.mkdir(parents=True,exist_ok=False)
                data=dict(package=s.PACKAGE,task=t,design=req['design'],action=req['action'])
                h.save(folder/'input.json',data)
                row=dict(index=i,group=group,condition_id=t['condition_id'],candidate_ordinal=1,attempt='COMMON_SCHEDULER_REPAIR_CONTINUATION',sources=sources,input=s.ref(folder/'input.json'),status='STARTED')
                s.journal('scientific-claims.jsonl',dict(**row,at=s.now()))
                s.save(s.HERE/'science-resource-ledger.json',ledger);start=time.monotonic()
                try:
                    with (folder/'child.stdout').open('w') as stdout,(folder/'child.stderr').open('w') as stderr:
                        proc=subprocess.run([str(h.PYTHON),'-B',str(s.HERE/'run.py'),'child',str(folder/'input.json')],cwd=s.ROOT,stdout=stdout,stderr=stderr,timeout=min(120,deadline-time.time()),check=False)
                    if proc.returncode:raise RuntimeError('CHILD_EXIT_'+str(proc.returncode))
                    with gzip.open(folder/'result/public-result.json.gz','rt') as f:pub=json.load(f)
                    assert pub['sources']==sources
                    results.append(pub);row.update(status='COMPLETE',public_result=s.ref(folder/'result/public-result.json.gz'),public_check=pub['public_check'],result_sha256=pub['result_sha256'])
                except Exception as exc:
                    row.update(status='TOOL_ERROR',error=type(exc).__name__+':'+str(exc));errors.append(row['error'])
                finally:
                    row['wall_s']=time.monotonic()-start;ledger['full_wall_s']+=row['wall_s'];ledger['members'].append(row)
                    s.journal('scientific-members.jsonl',row);s.save(s.HERE/'science-resource-ledger.json',ledger)
                    print(json.dumps(dict(event='COMMON_REPAIR_INPUT',index=i,group=group,condition=t['condition_id'],status=row['status'],public_check=row.get('public_check'))),flush=True)
                if errors:break
            service=s.family_result(dict(design=req['design'],results=results),req['design'],protocol['conditions']) if len(results)==3 else None
            out[group]=dict(original_chosen_action=req['action'],same_candidate_no_new_generate=True,results=results,service=service,errors=errors)
            s.save(s.HERE/'scheduler-continuation-summary.json',out)
    finally:
        ledger['scheduler_continuation']={k:dict(service=v['service'],errors=v['errors']) for k,v in out.items()};ledger['status']='CLOSED_AFTER_BOUNDED_DIRECT_REPAIRS';s.save(s.HERE/'science-resource-ledger.json',ledger)
        s.save(s.HERE/'scheduler-continuation-summary.json',out)
        assert all(s.ref(s.ROOT/p)['sha256']==v['sha256'] for p,v in originals.items())
        print(json.dumps(dict(event='COMMON_REPAIR_CLOSED',new_full_inputs=ledger['new_full_inputs'],groups={k:v['service'] for k,v in out.items()})),flush=True)
if __name__=='__main__':main()
