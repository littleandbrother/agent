"""Read-only collection of the new task's public outcomes and original ledger."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

APP=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(APP/'scripts'))
from v2_common import RUNTIME, action, request


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);a=parser.parse_args()
    root=RUNTIME/'task-design';who=json.loads((root/'owner.json').read_text());owner=who['owner']
    state=action(owner,'repository_state');view=action(owner,'repository_view')
    db=sqlite3.connect((RUNTIME/'workbench/state/workbench.sqlite').as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
    rows=[dict(r) for r in db.execute('SELECT id,status,charged,reserved,usage FROM model_requests WHERE owner=? ORDER BY rowid',(owner,))]
    decisions=[json.loads(r['rationale']) for r in db.execute('SELECT rationale FROM design_adoptions WHERE owner=? ORDER BY rowid',(owner,))]
    db.close()
    for row in rows:
        if isinstance(row['usage'],str):row['usage']=json.loads(row['usage'])
    source_trace=RUNTIME/'workbench/sessions'/owner/'trace.jsonl'
    skills=[];actions=[];public=[]
    if source_trace.exists():
        for line in source_trace.read_text().splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            if event.get('type')=='repository_tool_fact':
                actions.append({'action':event['action'],'input':event['input'],'result':event['result']})
                if event['action']=='skill':skills.append(event['input'].get('skill_id'))
            if event.get('type')=='text_delta':public.append(event.get('delta',''))
    systems=[{'id':s['id'],'parent':s['parent'],'changes':s.get('design_changes',[]),'rationale':s.get('rationale'),
              'qualification':s['current_qualification']} for s in view['systems']]
    executions=[{k:v[k] for k in ('id','target','execution_key','status','metrics','descriptor','artifacts')} for v in view['task_executions']]
    value={'state':state,'project':view['project'],'systems':systems,'executions':executions,'decisions':decisions,
           'releases':view['releases'],'model_requests':rows,'skills':skills,'public_text':''.join(public),'actions':actions}
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        if a.output.exists():raise ValueError('COLLECTION_OUTPUT_EXISTS')
        a.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'state':state,'skills':skills,'systems':[{k:s[k] for k in ('id','parent','rationale','changes')} for s in systems],
        'executions':[{k:e[k] for k in ('target','status','metrics')} for e in executions],
        'decisions':[{k:d[k] for k in ('decision','rationale','to_design')} for d in decisions],
        'releases':[r['id'] for r in view['releases']]},ensure_ascii=False))


if __name__=='__main__':main()
