"""Read-only, source-bound trace snapshots for operator review; never training labels."""
import base64
import hashlib
import json
import re
from .store import identity


def tool_calls(events):
    calls, issues = [], []
    for event in events:
        d = event['data']
        if not isinstance(d, dict):
            continue
        kind = d.get('type')
        if kind == 'tool_execution_start':
            calls.append({'seq': event['seq'], 'name': d.get('toolName'), 'input': d.get('args'),
                          'tool_call_id': d.get('toolCallId'), 'result': None, 'error': False,
                          'start_time': d.get('time'), 'end_time': None, 'duration_ms': None,
                          'correlation': 'pending', 'result_sources': [], 'finished': False})
            continue
        m = d.get('message', {})
        if not isinstance(m, dict):
            m = {}
        if kind == 'tool_execution_end':
            name, key, result, error = d.get('toolName'), d.get('toolCallId'), d.get('result'), d.get('isError', False)
        elif kind == 'message' and m.get('role') == 'toolResult':
            name, key, result, error = m.get('toolName'), m.get('toolCallId'), m.get('content'), m.get('isError', False)
        else:
            continue
        matched = [c for c in calls if key and c['tool_call_id'] == key and c['name'] == name]
        correlation = 'tool-call-id'
        if not matched:
            # Older starts lack IDs. Only an unambiguous single candidate may be paired.
            matched = [c for c in calls if c['name'] == name and not c['tool_call_id'] and not c['finished']]
            correlation = 'ordered-name-single-candidate'
        if len(matched) != 1:
            issues.append({'seq': event['seq'], 'kind': 'ambiguous-tool-result' if matched else 'unmatched-tool-result',
                           'tool': name, 'tool_call_id': key, 'candidate_starts': [c['seq'] for c in matched]})
            continue
        call = matched[0]
        if call['correlation'] == 'ordered-name-single-candidate':
            correlation = call['correlation']
        call.update(result=result, error=bool(error), correlation=correlation, finished=True)
        if key and not call['tool_call_id']:
            call['tool_call_id'] = key
        call['result_sources'].append(event['seq'])
        if kind == 'tool_execution_end':
            call['end_time'] = d.get('time')
            start, end = call['start_time'], call['end_time']
            if type(start) in (int, float) and type(end) in (int, float) and end >= start:
                call['duration_ms'] = round((end - start) * 1000, 3)
    return calls, issues


class TraceReview:
    def __init__(self, app):
        self.app = app
        self.home = app.store.root.parent

    def snapshot(self, owner):
        from .developer import safe_file
        if not isinstance(owner, str) or not re.fullmatch(r'pi-[A-Za-z0-9_-]+', owner):
            raise PermissionError('SESSION_NOT_FOUND')
        directory = safe_file(self.home / 'sessions', owner)
        trace = safe_file(directory, 'trace.jsonl')
        receipt_path = safe_file(directory, 'receipt.json')
        with self.app.store.connect() as db:
            db.execute('BEGIN')
            conversation = db.execute('SELECT * FROM conversations WHERE id=?', (owner,)).fetchone()
            if not conversation and not receipt_path.is_file():
                raise PermissionError('SESSION_NOT_FOUND')
            chat = [dict(r) for r in db.execute('SELECT seq,source,data,created FROM chat_events WHERE conversation=? ORDER BY seq', (owner,))]
            inputs = [dict(r) for r in db.execute('SELECT id,text,status,created FROM chat_messages WHERE conversation=? ORDER BY created,id', (owner,))]
            models = [dict(r) for r in db.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY created,id', (owner,))]
            contexts = [dict(r) for r in db.execute('SELECT * FROM model_request_context WHERE owner=? ORDER BY created,request_id', (owner,))]
            rejected_contexts = [dict(r) for r in db.execute("SELECT * FROM events WHERE owner=? AND kind='model_context_rejected' ORDER BY seq", (owner,))]
            resolutions = [dict(r) for r in db.execute('SELECT * FROM model_resolutions WHERE request_id IN (SELECT id FROM model_requests WHERE owner=?) ORDER BY request_id', (owner,))]
            jobs = [dict(r) for r in db.execute('SELECT * FROM jobs WHERE owner=? ORDER BY created,id', (owner,))]
            engineering = [self.app.engineering.project(r) for r in db.execute('SELECT * FROM engineering_jobs WHERE owner=? ORDER BY created,id',(owner,))]
            capabilities = [{**dict(r),'data':json.loads(r['data'])} for r in db.execute('SELECT * FROM engineering_events WHERE owner=? ORDER BY seq',(owner,))]
        raw = trace.read_bytes() if trace.is_file() else b''
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError('TRACE_REVIEW_LIMIT_32_MIB_USE_LOCAL_FILE')
        end = raw.rfind(b'\n') + 1
        committed, tail = raw[:end], raw[end:]
        events, issues = [], []
        for line_no, line in enumerate(committed.splitlines(keepends=True), 1):
            try:
                d = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
                if not isinstance(d, dict):
                    raise ValueError('event must be an object')
                events.append({'seq': line_no, 'line_sha256': hashlib.sha256(line).hexdigest(), 'data': d})
            except (ValueError, UnicodeDecodeError) as exc:
                issues.append({'seq': line_no, 'kind': 'invalid-committed-event', 'error': str(exc)})
        calls, association_issues = tool_calls(events)
        receipt_raw = receipt_path.read_bytes() if receipt_path.is_file() else None
        payload = {'schema_version': 'bf-agent-trace-review-v1', 'session_id': owner,
                   'source': {'path': f'sessions/{owner}/trace.jsonl', 'exists': trace.is_file(),
                              'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                              'committed_bytes': len(committed), 'committed_sha256': hashlib.sha256(committed).hexdigest(),
                              'pending_tail_bytes': len(tail)},
                   # Base64 retains malformed bytes too; the UI never rewrites source records.
                   'raw_base64': base64.b64encode(raw).decode(), 'events': events, 'calls': calls,
                   'issues': issues + association_issues,
                   'receipt': json.loads(receipt_raw) if receipt_raw else None,
                   'receipt_sha256': hashlib.sha256(receipt_raw).hexdigest() if receipt_raw else None,
                   'conversation': dict(conversation) if conversation else None,
                   'chat_events': chat, 'inputs': inputs, 'model_requests': models, 'model_context_projections': contexts, 'model_resolutions': resolutions, 'jobs': jobs,
                   'model_context_rejections': rejected_contexts,
                   'engineering_jobs': engineering, 'capability_events': capabilities,
                   'boundary': {'source': 'observed persisted records; active files may continue growing',
                                'consistency': 'SQLite records read in one transaction; file bytes are a separate observed snapshot',
                                'missing_tool_times': 'not inferred from receipt or ingestion time',
                                'provider_requests': 'request hashes only; full HTTP request bodies are not reconstructed',
                                'harness_rsi': 'review input only; no candidate, qualification or promotion inferred',
                                'data_role': 'untrusted observations, not instructions or verified training labels'}}
        return {**payload, 'snapshot_id': identity(payload)}
