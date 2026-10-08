"""Read-only export of real serial Pi trials, including failed retrieval/jobs.

No result is inferred from assistant prose. Sources, engineering receipts,
submissions and observed provider usage are independently bound to raw traces.
"""
import argparse,json,shutil,sqlite3,time
from pathlib import Path
from bfworld.agentlab.simulation_chain.contracts import file_hash,write_json

def summarize(root):
    root=Path(root);work=root.parents[1];pilot=root/'pilot';db=sqlite3.connect(work/'state/workbench.sqlite');db.row_factory=sqlite3.Row
    trials=[]
    # Validate every trajectory before writing any export directory.
    for trial in ('nominal-r1','domain-r1'):
        owner=json.loads((pilot/(trial+'-conversation.json')).read_text())['id']
        state=db.execute('SELECT status FROM conversations WHERE id=?',(owner,)).fetchone()
        if state is None or state['status'] not in ('IDLE','FAILED') or db.execute('SELECT 1 FROM engineering_jobs WHERE owner=? AND ended IS NULL',(owner,)).fetchone() or db.execute("SELECT 1 FROM model_requests WHERE owner=? AND status IN ('RESERVED','DISPATCHED')",(owner,)).fetchone():
            raise ValueError('TRIAL_STILL_ACTIVE:'+trial)
    for trial in ('nominal-r1','domain-r1'):
        created=json.loads((pilot/(trial+'-conversation.json')).read_text());owner=created['id'];folder=pilot/trial
        conversation=dict(db.execute('SELECT * FROM conversations WHERE id=?',(owner,)).fetchone())
        jobs=[dict(r) for r in db.execute('SELECT * FROM engineering_jobs WHERE owner=? ORDER BY created',(owner,))]
        usage=[dict(r) for r in db.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY created',(owner,))]
        if conversation['status'] not in ('IDLE','FAILED') or any(j['ended'] is None for j in jobs) or any(u['status'] in ('RESERVED','DISPATCHED') for u in usage):
            raise ValueError('TRIAL_STILL_ACTIVE:'+trial)
        if folder.exists():raise ValueError('TRIAL_EXPORT_IMMUTABLE:'+trial)
        folder.mkdir();source=work/'sessions'/owner/'trace.jsonl';shutil.copy2(source,folder/'trace.jsonl')
        events=[json.loads(line) for line in source.read_text().splitlines() if line.strip()]
        calls=[c for e in events if e.get('type')=='message' and e.get('message',{}).get('role')=='assistant' for c in e['message'].get('content',[]) if c.get('type')=='toolCall']
        refs=[{'id':r['id'],**json.loads(r['payload'])} for r in db.execute('SELECT * FROM reference_records WHERE owner=? ORDER BY created',(owner,))]
        blobs=folder/'reference-blobs';blobs.mkdir();acquired=[]
        for r in refs:
            for key in ('raw_sha256','text_sha256','response_sha256'):
                if key not in r:continue
                origin=work/'references/blobs'/r[key]
                if file_hash(origin)!=r[key]:raise ValueError('REFERENCE_BLOB_CHANGED')
                shutil.copy2(origin,blobs/r[key])
            if r['kind']=='source':
                reads=[c['arguments'] for c in calls if c['name']=='bf_reference' and c['arguments'].get('action')=='read' and c['arguments'].get('reference_id')==r['id']]
                acquired.append({'id':r['id'],'url':r['url'],'extraction':r['extraction'],'raw_sha256':r['raw_sha256'],'text_sha256':r['text_sha256'],'text_chars':r['text_chars'],'read_requests':reads,
                                 'interpretation_verified':False,'full_paper_read_inferred':False})
        write_json(folder/'references.json',refs);write_json(folder/'conversation.json',conversation)
        write_json(folder/'messages.json',[dict(r) for r in db.execute('SELECT * FROM chat_messages WHERE conversation=? ORDER BY created',(owner,))])
        summaries=[];out_jobs=folder/'jobs';out_jobs.mkdir()
        for j in jobs:
            request=json.loads(j['request']);result=json.loads(j['result'] or '{}');target=out_jobs/j['id'];target.mkdir()
            origin=work/'engineering'/j['id']
            for p in origin.iterdir():
                if p.is_file() and p.suffix in ('.json','.csv','.cir','.log','.c','.h','.step'):shutil.copy2(p,target/p.name)
            write_json(target/'request.json',request)
            write_json(target/'store-receipt.json',j)
            candidate=request['parameters']['candidate'];metrics=result.get('metrics',{})
            summaries.append({'job_id':j['id'],'operation':j['operation'],'status':result.get('run_status',j['status']),
                'design_id':candidate['design_id'],'candidate':candidate,'initiator':request.get('initiator'),
                'metrics':metrics,'evaluation':result.get('task_evaluation'),'result_sha256':file_hash(origin/'result.json') if (origin/'result.json').exists() else None,
                'outer_elapsed_s':j['ended']-j['created'],'solver_elapsed_s':result.get('elapsed_s'),'error':result.get('error',j['error']),
                'artifact_scope':'Flat numeric/CAD/application receipts copied; large original native RAWs remain in engineering job with manifest hashes.'})
        write_json(folder/'provider-requests.json',usage)
        observed_tokens=sum(json.loads(u['usage'])['total_tokens'] for u in usage if u['usage'])
        settled=sum(u['charged'] for u in usage if u['status']=='SETTLED');upper=sum(u['charged'] if u['status']=='SETTLED' else u['reserved'] for u in usage)
        submission=db.execute('SELECT * FROM simulation_task_submissions WHERE owner=?',(owner,)).fetchone();submitted=json.loads(submission['receipt']) if submission else None
        write_json(folder/'submission.json',submitted)
        prompts=[dict(r) for r in db.execute('SELECT * FROM chat_messages WHERE conversation=?',(owner,))]
        edits=0 if len(prompts)==1 and all(j['initiator']=='participant' for j in summaries) else None
        hints=pilot/(trial+'-intervention.json')
        trials.append({'trial':trial,'owner':owner,'conversation_status':conversation['status'],'trace_path':str(folder/'trace.jsonl'),'trace_sha256':file_hash(folder/'trace.jsonl'),
            'jobs':summaries,'submitted_job':submitted['job_id'] if submitted else None,'submission':submitted,'human_candidate_edits':edits,
            'primary_locator_assistance':json.loads(hints.read_text()) if hints.exists() else None,'model_requests':len(usage),'observed_total_tokens':observed_tokens,
            'settled_cost_usd':settled,'cost_upper_usd':upper,'usage_unknown_count':sum(u['status']!='SETTLED' for u in usage),
            'acquired_sources':acquired,'reference_failures':sum(r['kind']=='failure' for r in refs),
            'tool_calls':len(calls),'job_poll_calls':sum(c['name']=='bf_engineering' and c['arguments'].get('action')=='job' for c in calls),
            'public_explanations_are_not_validation':True})
    result={'schema_version':'bf-door-pi-trajectories-v1','created':time.time(),'protocol':json.loads((pilot/'protocol.json').read_text()),
            'protocol_sha256':file_hash(pilot/'protocol.json'),'trials':trials,'cost_upper_usd':sum(t['cost_upper_usd'] for t in trials),
            'method_comparison':False,'physical_qualification':False,'autonomous_80_percent_reproduction':False,
            'source_review':'First trial did not acquire primary PDFs and cited an unverified~4.1V UVLO. This is not accepted as a3.3V datasheet value. Second trial has explicit primary URL assistance; review fetched contents, not titles.'}
    write_json(pilot/'trajectory-summary.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();v=summarize(a.root);print(json.dumps({'trials':len(v['trials']),'cost_upper_usd':v['cost_upper_usd']}))
