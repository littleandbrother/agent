"""Read-only receipts for a Pi product run. No solver or model is dispatched.

Counts execution facts, not autonomy or engineering success. Never exports
messages, reasoning, credentials, or model wire bodies.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3


def small_record(path):
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('AUDIT_SMALL_RECORD_LIMIT')
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'value': json.loads(raw)}


def audit(runtime, owner):
    if not re.fullmatch(r'pi-chat-[a-zA-Z0-9_-]+', owner):
        raise ValueError('AUDIT_OWNER_INVALID')
    runtime = Path(runtime)
    db = sqlite3.connect((runtime / 'workbench/state/workbench.sqlite').as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    conversation = db.execute('SELECT id,title,status,error FROM conversations WHERE id=?', (owner,)).fetchone()
    if not conversation:
        raise ValueError('AUDIT_OWNER_NOT_FOUND')
    models = [dict(x) for x in db.execute(
        'SELECT id,status,reserved,charged,error FROM model_requests WHERE owner=? ORDER BY created', (owner,))]
    unknown = [x for x in models if x['status'] == 'UNKNOWN']
    outstanding = [x for x in models if x['status'] in ('UNKNOWN', 'RESERVED', 'DISPATCHED')]
    jobs = []
    for row in db.execute('SELECT id,status,created,started,ended,error,result FROM engineering_jobs WHERE owner=? ORDER BY created', (owner,)):
        item = dict(row)
        result = json.loads(item.pop('result') or '{}')
        item['result'] = {k: result[k] for k in ('run_status', 'design_id', 'qualification', 'design_status', 'predicted_design_status', 'source_stable') if k in result}
        jobs.append(item)
    eda = [dict(x) for x in db.execute('SELECT status,count(*) count FROM eda_cli_jobs WHERE owner=? GROUP BY status', (owner,))]
    interventions = [dict(x) for x in db.execute(
        'SELECT id,operation,status,created FROM chat_messages WHERE conversation=? AND operation LIKE ? ORDER BY created', (owner, 'fullflow-%'))]
    calls, failures, events = Counter(), Counter(), Counter()
    trace = runtime / 'workbench/sessions' / owner / 'trace.jsonl'
    trace_hash = hashlib.sha256()
    if trace.is_file():
        with trace.open('rb') as stream:
            for raw in stream:
                trace_hash.update(raw)
                if not raw.endswith(b'\n'):
                    continue  # A live append may not have reached its newline.
                value = json.loads(raw)
                kind = value.get('type', '')
                events[kind] += 1
                if kind == 'tool_execution_start':
                    calls[value.get('toolName', 'unknown')] += 1
                if kind == 'tool_execution_end' and value.get('isError'):
                    failures[value.get('toolName', 'unknown')] += 1
    workspace = runtime / 'workbench/participants' / owner
    analysis = small_record(workspace / 'analysis.json')
    responsibilities = []
    if analysis:
        for item in analysis['value'].get('responsibilities', []):
            responsibilities.append({'id': item.get('id'), 'declared_requirement': item.get('requirement'),
                                     'declared_status': item.get('status'), 'artifact_count': len(item.get('artifacts', []))})
    source = small_record(workspace / 'eda/source-audit.json')
    source_view = None if not source else {'sha256': source['sha256'], **{k: source['value'].get(k) for k in (
        'source_sha256', 'native_sha256', 'status', 'errors', 'unmapped', 'value_and_rating_verified', 'behavioral_realization_verified', 'engineering_passed')}}
    db.close()
    charged = sum(x['charged'] or 0 for x in models)
    reserved = sum(x['reserved'] or 0 for x in outstanding)
    return {'schema_version': 'bf-pi-fullflow-execution-audit-v1', 'conversation': dict(conversation),
            'model': {'request_count': len(models), 'status_counts': dict(Counter(x['status'] for x in models)),
                      'charged_usd': charged, 'outstanding_upper_usd': reserved, 'total_upper_usd': charged + reserved,
                      'unknown_requests': unknown},
            'engineering_jobs': jobs, 'eda_status_counts': eda,
            'tool_calls': dict(calls), 'tool_error_counts': dict(failures),
            'event_counts': dict(events), 'trace_sha256_at_read': trace_hash.hexdigest() if trace.is_file() else None,
            'recorded_followups': interventions, 'declared_responsibilities': responsibilities,
            'analysis_sha256': analysis['sha256'] if analysis else None, 'source_accounting': source_view,
            'independent_engineering_acceptance': 'not_decided_by_this_audit',
            'autonomy_claim': 'not_established_by_execution_counts',
            'scope': 'Live read-only execution/accounting snapshot. Declarations and native tool completion are not engineering acceptance. Original owner journal and liability remain unchanged.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = audit(args.runtime, args.owner)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'model': value['model'], 'engineering_jobs': value['engineering_jobs']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
