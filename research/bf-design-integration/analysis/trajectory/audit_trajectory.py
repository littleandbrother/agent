"""Audit sanitized recorded method behavior; never dispatch or score efficacy."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r'[a-f0-9]{64}')
FIELDS = {
    'configuration': {'profile', 'instruction_sha256', 'loaded'},
    'instruction_delivery': {'config_id', 'request_id', 'instruction_sha256', 'delivered', 'receipt_id'},
    'candidate_action': {'operation_id', 'request_id', 'candidate', 'candidate_hash', 'job_id', 'dispatch', 'revision_id'},
    'terminal_result': {'action_id', 'job_id', 'result', 'result_sha256'},
    'feedback_available': {'terminal_id', 'request_id', 'delivery_receipt_id', 'available'},
    'revision': {'previous_action_id', 'feedback_id', 'request_id', 'next_operation_id', 'candidate_hash', 'kind'},
    'h_change': {'authorship', 'artifact_sha256', 'generation_request_id', 'execution_receipt_id'},
    'cost': {'usd', 'coverage'},
    'manual_intervention': {'status', 'coverage'},
}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def sha_value(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None

def identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value) is not None

def changes(a, b):
    return {group+'.'+key: {'before':value,'after':b[group][key]}
            for group, values in a.items() if isinstance(values,dict)
            for key,value in values.items() if value != b[group][key]}

def normalize(candidate, facts):
    baseline = facts['baseline']
    require(isinstance(candidate,dict) and candidate.keys()==baseline.keys(), 'FULL_CANDIDATE_REQUIRED')
    require(candidate['schema_version']==baseline['schema_version'], 'CANDIDATE_SCHEMA')
    for group, values in baseline.items():
        if not isinstance(values,dict):
            continue
        require(isinstance(candidate[group],dict) and candidate[group].keys()==values.keys(), 'CANDIDATE_FIELDS')
        for key, value in candidate[group].items():
            require(type(value) in (float,int) and math.isfinite(value), 'CANDIDATE_NUMBER')
            rule = facts['allowed_design_variables'].get(group+'.'+key)
            if rule is None:
                require(value==values[key], 'PROTECTED_FIELD')
            elif 'values' in rule:
                require(value in rule['values'], 'DESIGN_VALUE')
            else:
                require(rule['range'][0]<=value<=rule['range'][1], 'DESIGN_RANGE')
    return candidate

def audit(trace):
    protocol = json.loads((ROOT/'contracts/PROTOCOL.json').read_text())
    require(digest({k:v for k,v in protocol.items() if k!='protocol_hash'})==protocol['protocol_hash'], 'PROTOCOL_HASH')
    require(set(trace)=={'schema','owner','protocol_hash','task_hash','evidence_kind','sources'}, 'TRACE_FIELDS')
    require(trace['schema']=='bf-method-behavior-input-v1' and identifier(trace['owner']), 'TRACE_IDENTITY')
    require(trace['protocol_hash']==protocol['protocol_hash'] and trace['task_hash']==protocol['normalized_task_hash'], 'TASK_PROTOCOL_BINDING')
    require(trace['evidence_kind'] in ('synthetic','sanitized_local_receipts'), 'EVIDENCE_KIND')
    prior, operations, deliveries, terminals = {}, {}, {}, {}
    levels = {k:[] for k in ('configuration_loaded','instruction_delivered','candidate_action_recorded','feedback_available','feedback_linked_numeric_revision','terminal_result_bound')}
    costs, manual, h_changes = [], [], []
    notes, actions = [], []
    for seq, source in enumerate(trace['sources']):
        require(set(source)=={'id','sha256','record'}, 'SOURCE_FIELDS')
        sid, record = source['id'], source['record']
        require(identifier(sid) and sid not in prior and sha_value(source['sha256']) and digest(record)==source['sha256'], 'SOURCE_ID_HASH')
        require(set(record)=={'seq','owner','kind','data'} and type(record['seq']) is int and record['seq']==seq and record['owner']==trace['owner'], 'CHRONOLOGY_OWNER')
        kind, d = record['kind'], record['data']
        require(kind in FIELDS and isinstance(d,dict) and set(d)==FIELDS[kind], 'RECORD_FIELDS')
        def reference(id, expected_kind):
            require(id in prior and prior[id]['kind']==expected_kind, 'MISSING_OR_FUTURE_REFERENCE:'+str(id))
            return prior[id]['data']
        if kind=='configuration':
            require(d['profile'] in {p['id'] for p in protocol['profiles']} and sha_value(d['instruction_sha256']) and type(d['loaded']) is bool, 'CONFIGURATION')
            if d['loaded']: levels['configuration_loaded'].append(sid)
        elif kind=='instruction_delivery':
            config = reference(d['config_id'],'configuration')
            require(identifier(d['request_id']) and type(d['delivered']) is bool and d['instruction_sha256']==config['instruction_sha256'], 'INSTRUCTION_BINDING')
            require(d['request_id'] not in deliveries, 'REQUEST_DELIVERY_DUPLICATE')
            if d['delivered']:
                require(config['loaded'] and identifier(d['receipt_id']), 'DELIVERY_RECEIPT')
                deliveries[d['request_id']] = sid
                levels['instruction_delivered'].append(sid)
        elif kind=='candidate_action':
            require(identifier(d['operation_id']) and (d['request_id'] is None or identifier(d['request_id']))
                    and (d['job_id'] is None or identifier(d['job_id'])) and d['dispatch'] in ('acknowledged','unknown'), 'ACTION_IDENTITY')
            candidate = normalize(d['candidate'],protocol['common_facts_and_freedoms'])
            require(digest(candidate)==d['candidate_hash'], 'CANDIDATE_HASH')
            require(d['job_id'] is None or all(o['job_id']!=d['job_id'] or key==d['operation_id'] for key,o in operations.items()), 'JOB_OPERATION_CONFLICT')
            op = operations.get(d['operation_id'])
            if op:
                require(op['candidate']==candidate and op['job_id'] in (None,d['job_id']), 'IDEMPOTENCY_CONFLICT')
                if d['job_id'] is not None: op['job_id'] = d['job_id']
            else:
                require(len(operations)<protocol['max_new_candidates_per_owner'], 'CANDIDATE_QUOTA')
                operations[d['operation_id']]={'candidate':candidate,'job_id':d['job_id'],'first_source':sid}
            levels['candidate_action_recorded'].append(sid)
            actions.append({'source':sid,'operation_id':d['operation_id'],'dispatch':d['dispatch'],
                'changes_from_baseline':changes(protocol['common_facts_and_freedoms']['baseline'],candidate),
                'change_class':'numeric only; not architecture','retry':op is not None})
            if d['request_id'] not in deliveries:
                notes.append({'source':sid,'issue':'instruction delivery for this request unknown'})
            if d['revision_id'] is not None:
                rev = reference(d['revision_id'],'revision')
                old = reference(rev['previous_action_id'],'candidate_action')
                fb = reference(rev['feedback_id'],'feedback_available')
                term = reference(fb['terminal_id'],'terminal_result')
                delta = changes(old['candidate'],candidate)
                require(rev['next_operation_id']==d['operation_id'] and rev['candidate_hash']==d['candidate_hash']
                        and rev['request_id']==d['request_id']==fb['request_id'], 'REVISION_ACTION_BINDING')
                require(term['action_id']==rev['previous_action_id'] and d['operation_id']!=old['operation_id'], 'REVISION_PREDECESSOR')
                if fb['available'] and d['request_id'] in deliveries and delta:
                    levels['feedback_linked_numeric_revision'].append({'source':sid,'revision_source':d['revision_id'],'changes':delta,
                        'interpretation':'recorded feedback/action linkage; model reading and causality unproven'})
                else:
                    notes.append({'source':sid,'issue':'revision linkage incomplete or candidate unchanged'})
        elif kind=='terminal_result':
            action = reference(d['action_id'],'candidate_action')
            r = d['result']
            require(isinstance(r,dict) and set(r)=={'job_id','operation_id','owner','task_hash','candidate_hash','status','artifact_sha256'}, 'TERMINAL_FIELDS')
            require(digest(r)==d['result_sha256'] and r['job_id']==d['job_id']==action['job_id']
                    and identifier(d['job_id']) and r['operation_id']==action['operation_id']
                    and r['owner']==trace['owner'] and r['task_hash']==trace['task_hash']
                    and r['candidate_hash']==action['candidate_hash'] and r['status'] in ('SUCCEEDED','FAILED')
                    and sha_value(r['artifact_sha256']), 'TERMINAL_BINDING')
            if d['job_id'] in terminals: require(terminals[d['job_id']]==r, 'TERMINAL_MUTATION')
            terminals[d['job_id']]=r
            levels['terminal_result_bound'].append({'source':sid,'status':r['status'],
                'verification':'sanitized receipt hash and identity only; external artifact bytes not provided', 'external_artifact_hash_verified':False})
        elif kind=='feedback_available':
            reference(d['terminal_id'],'terminal_result')
            require(identifier(d['request_id']) and type(d['available']) is bool, 'FEEDBACK_FIELDS')
            if d['available']:
                require(identifier(d['delivery_receipt_id']), 'FEEDBACK_DELIVERY_RECEIPT')
                levels['feedback_available'].append(sid)
        elif kind=='revision':
            reference(d['previous_action_id'],'candidate_action')
            reference(d['feedback_id'],'feedback_available')
            require(d['kind']=='numeric', 'ARCHITECTURE_UNSUPPORTED')
            require(identifier(d['request_id']) and identifier(d['next_operation_id']) and sha_value(d['candidate_hash']), 'REVISION_FIELDS')
        elif kind=='h_change':
            require(d['authorship'] in ('developer','participant','unknown') and sha_value(d['artifact_sha256']), 'H_PROVENANCE')
            # An identifier alone is not executable bytes or an independent execution receipt.
            require(all(d[k] is None or identifier(d[k]) for k in ('generation_request_id','execution_receipt_id')), 'H_RECEIPT_IDS')
            h_changes.append({'source':sid,'authorship':d['authorship'],'artifact_sha256':d['artifact_sha256'],
                'classification':'developer patch; not participant H1' if d['authorship']=='developer' else 'participant H1 provenance unverified' if d['authorship']=='participant' else 'unknown authorship',
                'executable_H1_verified':False,'H_experiment_performed':False})
        elif kind=='cost':
            require(type(d['usd']) in (int,float) and math.isfinite(d['usd']) and d['usd']>=0 and d['coverage'] in ('partial','complete_trace'), 'COST_FIELDS')
            costs.append({'source':sid,**d})
        elif kind=='manual_intervention':
            require(d['status'] in ('present','none_reported','unknown') and d['coverage'] in ('partial','complete_trace'), 'MANUAL_FIELDS')
            manual.append({'source':sid,**d})
        prior[sid]=record
    return {'schema':'bf-method-behavior-audit-v1','status':'RECORDED_EVIDENCE_ONLY',
        'evidence_kind':trace['evidence_kind'],'owner':trace['owner'],'protocol_hash':trace['protocol_hash'],
        'sources':{s['id']:s['sha256'] for s in trace['sources']},'levels':{k:{'status':'recorded' if v else 'unknown','records':v} for k,v in levels.items()},
        'actions':actions,'distinct_operations':len(operations),'operation_ids':list(operations),'candidate_action_records':len(levels['candidate_action_recorded']),
        'cost':{'status':'reported' if costs else 'unknown','records':costs,'aggregate_usd':None},
        'manual_intervention':{'status':'reported' if manual else 'unknown','records':manual},'h_changes':h_changes,'notes':notes,
        'model_read_feedback':'unknown; availability or explicit linkage is not proof of reading',
        'scientific_qualification':'not assessed or promoted','method_benefit':'not established','causality':'not established',
        'limits':'Hashes bind supplied sanitized records, not authentic authorship or omitted history. No external artifact bytes, raw transcript, runtime execution or scientific score.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if os.path.lexists(args.out) or args.out.resolve()==args.input.resolve():
        parser.error('Output must be a new path; existing files and links are protected')
    raw=args.input.read_bytes()
    try:
        result=audit(json.loads(raw));code=0
    except Exception as exc:
        result={'status':'BLOCKED','error_type':type(exc).__name__,'error':str(exc)};code=1
    require(args.input.read_bytes()==raw,'INPUT_CHANGED_DURING_AUDIT')
    result['input_sha256']=hashlib.sha256(raw).hexdigest()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'status':result['status'],'out':str(args.out)}))
    return code

if __name__=='__main__': raise SystemExit(main())
