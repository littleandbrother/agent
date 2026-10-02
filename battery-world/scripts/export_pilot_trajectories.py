#!/usr/bin/env python3
"""Sanitize closed pilot attempts without claiming model reading or causality."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(study, contract_root, output):
    if output.exists():raise ValueError('PRESERVE_EXISTING_EXPORT')
    output.mkdir(parents=True)
    protocol=json.loads((contract_root/'contracts/PROTOCOL.json').read_text())
    task=json.loads((study/'task.json').read_text())
    if task['task_hash']!=protocol['normalized_task_hash']:raise ValueError('TASK_BINDING_MISMATCH')
    spec=importlib.util.spec_from_file_location('trajectory_audit',contract_root/'analysis/trajectory/audit_trajectory.py')
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    manifest={'schema':'sanitized-pilot-attempts-v1','study_protocol_sha256':file_hash(study/'protocol.json'),
              'contract_protocol_hash':protocol['protocol_hash'],'task_hash':task['task_hash'],
              'scope':'Contract-compatible observation of the local pilot, not execution of a formal Dot method comparison.',
              'feedback_policy':'No provider-request delivery linkage inferred from time or public rationale; missing linkage remains unknown.',
              'attempts':[]}
    receipts=(sorted((study/'trials').glob('*/receipt.json'))+sorted((study/'trials').glob('*/continuation-*/receipt.json'))
              +sorted((study/'trials').glob('*/final-reconciliation/receipt.json')))
    for receipt_path in receipts:
        directory=receipt_path.parent;receipt=json.loads(receipt_path.read_text())
        if receipt['status']['status'] in ('RUNNING','STARTING','STOPPING'):continue
        owner=receipt['conversation'];sources=[]
        def add(sid,kind,data):
            record={'seq':len(sources),'owner':owner,'kind':kind,'data':data}
            sources.append({'id':sid,'sha256':digest(record),'record':record})
        events=json.loads((directory/'events.json').read_text())
        activations=[]
        for event in events:
            data=json.loads(event['data']) if isinstance(event['data'],str) else event['data']
            if data.get('type')=='method_activation' and data.get('phase')=='invoked':
                activations.append((event['seq'],data))
        for seq,data in activations:
            add('configuration-'+str(seq),'configuration',{'profile':data['profile']['method_id'],
                'instruction_sha256':data['prompt_hash'],'loaded':True})
        jobs=json.loads((directory/'jobs.json').read_text())
        artifact_sources={}
        for job in jobs:
            if not job.get('result'):continue
            result=json.loads(job['result']) if isinstance(job['result'],str) else job['result']
            artifacts={a['name']:a for a in result['artifacts']}
            # Resolve immutable job artifacts from the receipt's own artifact path.
            home=Path('/Users/depengsu/Documents/bf-agent-workbench')
            job_root=home/'engineering'/job['id']
            for name in ('design-spec.json','result.json'):
                if file_hash(job_root/name)!=artifacts[name]['sha256']:raise ValueError('ARTIFACT_IDENTITY')
                artifact_sources[job['id']+'/'+name]=artifacts[name]['sha256']
            candidate=json.loads((job_root/'design-spec.json').read_text())
            action='action-'+job['id'];candidate_hash=digest(candidate)
            add(action,'candidate_action',{'operation_id':job['operation'],'request_id':None,'candidate':candidate,
                'candidate_hash':candidate_hash,'job_id':job['id'],'dispatch':'acknowledged','revision_id':None})
            terminal={'job_id':job['id'],'operation_id':job['operation'],'owner':owner,'task_hash':task['task_hash'],
                'candidate_hash':candidate_hash,'status':job['status'],'artifact_sha256':artifacts['result.json']['sha256']}
            add('terminal-'+job['id'],'terminal_result',{'action_id':action,'job_id':job['id'],'result':terminal,'result_sha256':digest(terminal)})
        usage=json.loads((directory/'usage.json').read_text())
        settled=sum(r['charged'] for r in usage if r['status']=='SETTLED')
        held=sum(r['reserved'] for r in usage if r['status']!='SETTLED')
        add('cost','cost',{'usd':settled+held,'coverage':'partial' if held else 'complete_trace'})
        add('manual','manual_intervention',{'status':'present' if receipt['prompt_continuations'] else 'none_reported','coverage':'partial'})
        trace={'schema':'bf-method-behavior-input-v1','owner':owner,'protocol_hash':protocol['protocol_hash'],
            'task_hash':task['task_hash'],'evidence_kind':'sanitized_local_receipts','sources':sources}
        name='-'.join(directory.relative_to(study/'trials').parts)
        target=output/name;target.mkdir()
        write=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
        write(target/'input.json',trace)
        report=audit.audit(trace);write(target/'audit.json',report)
        provenance={'receipt_sha256':file_hash(receipt_path),'events_sha256':file_hash(directory/'events.json'),
            'jobs_sha256':file_hash(directory/'jobs.json'),'usage_sha256':file_hash(directory/'usage.json'),
            'artifact_sources':artifact_sources,'status':receipt['status']['status'],
            'model_requests':[{'id':r['id'],'status':r['status'],'charged':r['charged'],'reserved':r['reserved']} for r in usage],
            'settled_upper_usd':settled,'unsettled_reservation_usd':held,'participant_submitted':receipt['participant_submitted'],
            'prompt_continuations':receipt['prompt_continuations'],'snapshots_are_cumulative':True,
            'cost_note':'Do not sum cumulative attempts; late settlements can differ from preserved attempt snapshots.',
            'record_order':'Grouping for consistency audit, not inferred feedback chronology. No revision or request-delivery claim.'}
        write(target/'provenance.json',provenance)
        manifest['attempts'].append({'id':name,'input_sha256':file_hash(target/'input.json'),
            'audit_sha256':file_hash(target/'audit.json'),'provenance_sha256':file_hash(target/'provenance.json'),
            'status':report['status']})
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'attempts':len(manifest['attempts']),'output':str(output),'all_audited':True}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True);p.add_argument('--contract-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();export(a.study,a.contract_root,a.output)
