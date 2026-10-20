#!/usr/bin/env python3
"""Derive finite-package receipts from sealed results; never dispatch a model."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import zlib

from summarize import OUT, SHARED, read, sha, summarize


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def seal(path, value):
    content=json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    if path.exists():
        require(path.read_text()==content, 'EXISTING_CORE_RECEIPT_DIFFERS')
    else:
        path.write_text(content)


def initial_payload(root):
    request=read_request(root/'gateway/requests/model-001.json.zlib')
    prefix='Complete the assigned ABC stage using the frozen BF tool and submit the assigned artifact.\n'
    texts=[]
    for message in request['messages']:
        content=message.get('content')
        if isinstance(content,str):
            texts.append(content)
        elif isinstance(content,list):
            texts.extend(item['text'] for item in content if isinstance(item,dict) and isinstance(item.get('text'),str))
    goals=[text for text in texts if text.startswith(prefix)]
    require(len(goals)==1, 'EXACT_INITIAL_SDK_GOAL_REQUIRED')
    actual=json.loads(goals[0][len(prefix):])
    require(actual==read(root/'participant-payload.json'), 'INITIAL_MODEL_PAYLOAD_CHANGED')
    require(request['max_tokens']==65536, 'COMMON_OUTPUT_BUDGET_CHANGED')
    return actual, request['model']


def read_request(path):
    return json.loads(zlib.decompress(path.read_bytes()))


def finalize():
    index=summarize()
    require(index['finished_model_episodes']==index['planned_model_episodes']==48, 'FINITE_LIST_NOT_FINISHED')
    require(not index['running'] and not index['completed_accounting_only']['unknown_usage'], 'UNRESOLVED_EPISODE_OR_USAGE')
    expected={
        'protocol-entry-fix-v1.1.json':'a6e511d381cde82bdd35effc55ffffb434866fe6d396477b44260bd1c38435c7',
        'protocol-B-v1.json':'62c5040f263f9be7e00d6bb2d6c2b997bd87353a506d96877bcb20f8518fbd57',
        'protocol-A-v1.json':'d9bcc1889bf94f98e692f0b621f966e0c5f1e25a18b837e1293a72e68a120d74',
    }
    bound={}
    for filename, expected_sha in expected.items():
        require(sha(SHARED/filename)==expected_sha, 'FROZEN_PROTOCOL_CHANGED')
        for path, file_sha in read(SHARED/filename)['bound_files'].items():
            require(path not in bound or bound[path]==file_sha, 'CONFLICTING_SOURCE_BINDING')
            bound[path]=file_sha
    for path, expected_sha in bound.items():
        require(sha(path)==expected_sha, 'BOUND_SOURCE_CHANGED:'+path)
    models=set()
    tasks=defaultdict(set)
    sources=defaultdict(set)
    histories=set()
    method_bindings={}
    for arm in ('ordinary','proposed'):
        path=OUT/'episodes'/('C-formation-'+arm)/'methods/method-submission.json'
        method_bindings[arm]={'path':str(path),'file_sha256':sha(path),'semantic_sha256':digest(read(path))}
    for row in index['rows']:
        require(not row.get('error') and not row.get('audit_or_check_error'), 'EXECUTION_ERROR_REQUIRES_REVIEW:'+row['episode_id'])
        root=Path(row['result_path']).parent
        payload, model=initial_payload(root)
        models.add(model)
        if row['package']=='interfaces':
            tasks[row['task_id']].add(digest(payload['task']))
            records={p.stem:read(p) for p in (root/'public/sources').glob('*.json')}
            sources[row['task_id']].add(digest(records))
            if row['arm']=='complete_information':
                require(set(payload['complete_sources'])=={'complete_inputs','component_record','excitation_record','model_law'}, 'STRONG_BASELINE_INCOMPLETE')
                require(payload['complete_sources']==records, 'STRONG_BASELINE_SOURCE_CHANGED')
        elif row['package']=='methods':
            saved=read(root/'methods/input.json')
            require(payload==saved['participant_input'], 'METHOD_CONTEXT_BINDING_CHANGED')
            if row['stage']=='formal':
                tasks[row['task_id']].add(digest(saved['task']))
            if row['arm']=='H0':
                require(payload['history'] is None, 'H0_HISTORY_CONTROL_CHANGED')
            else:
                require(payload['history']==saved['history'] and payload['history'] is not None, 'HISTORY_NOT_DELIVERED')
                histories.add(digest(payload['history']))
            if row['stage']!='formation' and row['arm'] in method_bindings:
                binding=method_bindings[row['arm']]
                require(payload['learned_H']==read(binding['path']), 'FROZEN_H_PAYLOAD_CHANGED')
                require(row.get('consumed_method_sha256')==binding['semantic_sha256'], 'FROZEN_H_NOT_CONSUMED')
    require(len(models)==1 and len(histories)==1, 'MODEL_OR_HISTORY_PARITY_FAILED')
    require(all(len(v)==1 for v in tasks.values()), 'WITHIN_TASK_INPUT_CHANGED')
    require(all(len(v)==1 for v in sources.values()), 'B_SOURCE_PERMISSION_PARITY_FAILED')
    audit={'frozen_protocol_sha256':expected,'bound_source_files_checked':len(bound),
        'actual_initial_API_payloads_checked':48,'reported_model_aliases':sorted(models),
        'underlying_weights':'UNKNOWN','common_max_output_tokens':65536,
        'equal_history_semantic_sha256':next(iter(histories)),
        'within_task_input_parity':True,'B_full_source_parity':True,
        'audit_uses_no_new_model_or_scientific_execution':True}
    for package, label, count, table in [('interfaces','B',18,'formal_interfaces'),('methods','C',24,'formal_methods')]:
        formal=[r for r in index['rows'] if r['package']==package and r['stage']=='formal']
        require(len(formal)==count, 'FORMAL_DENOMINATOR_CHANGED')
        value={'schema_version':'bf-abc-finite-formal-core-v1','dispatch_id':'BF-ABC-20261020-001',
            'package':label,'status':'FINITE_FORMAL_LIST_COMPLETE','planned_attempts':count,
            'finished_attempts':len(formal),'arms':index[table],'audit':audit,
            'episodes':[{'episode_id':r['episode_id'],'result_path':r['result_path'],'sha256':r['result_sha256'],'status':r['status']} for r in formal],
            'accounting':{'requests':sum(r['requests'] for r in formal),'conservative_rate_estimate_usd':sum(r['charge_upper_usd'] for r in formal),
                'summed_episode_wall_s':sum(r['wall_s'] for r in formal),'usage':'All linked provider rows SETTLED; no missing usage. Fixed-rate estimates are not invoices; Codex preparation UNKNOWN.'},
            'interpretation':'Report prediction, decision, typed consumption and selected service separately; cache warmth is determined by order, not algorithmic savings.' if label=='B' else 'Report all four assigned arms, frozen H relations and independently judged service separately. Structural admission and passing designs do not prove H semantics.',
            'boundary':'Prescribed-source digital B transient apparatus; physical NOT_CALIBRATED.' if label=='B' else 'Ideal continuously powered O time-semantics component; no original energy/RF/keepalive or hardware acceptance.',
            'old_evidence':'Original failures, four old32768 truncations, costs and UNKNOWN are preserved. No outcome-based repeats, no G/RSI expansion, no publication.'}
        if label=='C':
            value['frozen_methods']=method_bindings
            value['formation_validation_first_transfer']=[r for r in index['rows'] if r['package']=='methods' and r['stage']!='formal']
        target=SHARED/(label+'-formal'+str(count)+'-v1.json')
        seal(target,value)
        print(json.dumps({'package':label,'receipt':str(target),'sha256':sha(target),'attempts':count}))
    seal(SHARED/'final-input-audit.json',audit)


if __name__=='__main__':
    finalize()
