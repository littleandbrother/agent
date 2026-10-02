#!/usr/bin/env python3
"""Export reference actions and exact request presence, never private wire bodies."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from collections import Counter


def digest(text):return hashlib.sha256(text.encode()).hexdigest()


def export(database,owner,output):
    db=sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    events=[json.loads(r['data']) for r in db.execute('SELECT data FROM chat_events WHERE conversation=? ORDER BY seq',(owner,))]
    starts={};actions=[];delivered={}
    for v in events:
        if v.get('type')=='tool_execution_start' and v.get('toolName')=='bf_reference':starts[v['toolCallId']]=v
        if v.get('type')=='tool_execution_end' and v.get('toolCallId') in starts:
            start=starts[v['toolCallId']];content=v['result'].get('content',[])
            text='\n'.join(x['text'] for x in content if x.get('type')=='text')
            action={'tool_call_id':v['toolCallId'],'args':start['args'],'started':start.get('time'),'ended':v.get('time'),
                    'error':v.get('isError',False),'response_sha256':digest(text),'request_presence':[]}
            try:
                value=json.loads(text)
                action['response_identity']={k:value[k] for k in ('id','sha256','raw_sha256','offset','next_offset','total_chars','arithmetic_check','value','unit') if k in value}
            except ValueError:action['error_text']=text[:500]
            actions.append(action);delivered[(v['toolCallId'],digest(text))]=action
    wire_errors=[];requests=[]
    for r in db.execute('SELECT * FROM model_request_evidence WHERE owner=? ORDER BY created',(owner,)):
        if digest(r['wire'])!=json.loads(r['receipt'])['wire_sha256']:
            wire_errors.append(r['request_id']);continue
        wire=json.loads(r['wire']);requests.append(r['request_id'])
        for i,m in enumerate(wire.get('messages',[])):
            if m.get('role')!='tool' or not isinstance(m.get('content'),str):continue
            action=delivered.get((m.get('tool_call_id'),digest(m['content'])))
            if action is not None:action['request_presence'].append({'request_id':r['request_id'],'message_index':i})
    sources=[{'id':r['id'],'kind':r['kind'],'created':r['created'],**json.loads(r['payload'])}
             for r in db.execute('SELECT * FROM reference_records WHERE owner=? ORDER BY created,id',(owner,))]
    charges=[dict(r) for r in db.execute('SELECT id,status,reserved,charged,usage FROM model_requests WHERE owner=? ORDER BY created',(owner,))]
    value={'schema':'reference-review-evidence-v1','owner':owner,'actions':actions,'sources':sources,
        'counts':dict(Counter(a['args'].get('action') for a in actions)),
        'sources_read_in_later_request':sorted(set(a['args']['reference_id'] for a in actions if a['args'].get('action')=='read' and a['request_presence'] and not a['error'])),
        'model_calls':len(charges),'upper_usd':sum(c['charged'] if c['status']=='SETTLED' else c['reserved'] for c in charges),
        'request_ids':requests,'wire_errors':wire_errors,'scope':'Exact tool-response presence, not proof of understanding, numerical correctness or source applicability.'}
    with Path(output).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:value[k] for k in ('counts','model_calls','upper_usd','wire_errors')},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--owner',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();export(a.database,a.owner,a.output)
