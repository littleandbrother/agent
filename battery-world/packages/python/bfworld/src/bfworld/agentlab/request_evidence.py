"""Passive receipts of the final provider request, after context projection.

Presence in a submitted request does not prove attention, use, or causality.
Raw request bodies stay in private local state, never in default exports.
"""
import hashlib
import json

from .store import canonical, identity
from .tool_responses import delivery_canonical


def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ''.join(part.get('text', '') for part in value
                       if isinstance(part, dict) and part.get('type') == 'text')
    return ''


def describe(db, owner, body, raw):
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    messages = body.get('messages', [])
    systems = [text_content(m.get('content')) for m in messages if m.get('role') in ('system', 'developer')]
    method = {'status': 'unknown', 'reason': 'no_source_bound_instruction_text'}
    if 'chat_events' in tables:
        rows = db.execute("SELECT seq,data FROM chat_events WHERE conversation=? AND json_extract(data,'$.type')='method_activation' AND json_extract(data,'$.phase')='invoked' ORDER BY seq DESC LIMIT 1", (owner,))
        for row in rows:
            event = json.loads(row['data'])
            instruction = event.get('instruction_text')
            if isinstance(instruction, str) and instruction and identity(instruction) == event.get('prompt_hash'):
                method = {'status': 'present_in_wire' if any(instruction in s for s in systems) else 'absent_from_wire',
                    'configuration_event_seq': row['seq'], 'instruction_sha256': event['prompt_hash'],
                    'profile': event.get('profile'), 'build_sha256': event.get('method_build_sha256'),
                    'configuration_event_sha256': identity(event)}
    feedback = []
    for index, message in enumerate(messages):
        if message.get('role') != 'tool':
            continue
        content = text_content(message.get('content'))
        item = {'message_index': index, 'tool_call_id': message.get('tool_call_id'),
                'content_sha256': hashlib.sha256(content.encode()).hexdigest(),
                'status': 'unverified_tool_content'}
        try:
            value = json.loads(content)
        except (TypeError, ValueError):
            value = None
        if isinstance(value, dict) and isinstance(value.get('_response'), dict) and 'engineering_response_deliveries' in tables:
            delivery_text = delivery_canonical(value)
            digest = hashlib.sha256(delivery_text.encode()).hexdigest()
            delivery = db.execute('SELECT * FROM engineering_response_deliveries WHERE owner=? AND sha256=?', (owner, digest)).fetchone()
            snapshot = db.execute('SELECT * FROM engineering_responses WHERE owner=? AND id=?', (owner, value['_response'].get('response_id'))).fetchone()
            if (delivery and snapshot and delivery['body'] == delivery_text
                    and delivery['response_id'] == snapshot['id']
                    and snapshot['sha256'] == value['_response'].get('sha256')
                    and hashlib.sha256(snapshot['body'].encode()).hexdigest() == snapshot['sha256']
                    and identity({'binding': json.loads(snapshot['binding']), 'sha256': snapshot['sha256']}) == snapshot['id']):
                item.update(status='backend_response_present_in_wire', delivery_sha256=digest,
                    response_id=snapshot['id'], response_sha256=snapshot['sha256'],
                    binding=json.loads(snapshot['binding']), offset=value.get('offset'),
                    next_offset=value.get('next_offset'), full_response_inline=value.get('full_response_inline', 'text' not in value))
        feedback.append(item)
    return {'schema': 'bf-request-evidence-v1', 'owner': owner,
        'wire_sha256': hashlib.sha256(raw).hexdigest(), 'wire_bytes': len(raw),
        'method': method, 'feedback': feedback, 'phase': 'prepared_for_dispatch',
        'scope': 'Exact post-projection request presence only; not provider acknowledgement, model attention, use or causal benefit.'}
