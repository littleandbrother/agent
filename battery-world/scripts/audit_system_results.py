"""Read-only live catalog coverage audit. Does not dispatch jobs or models."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import urllib.request
import urllib.error
from urllib.parse import urlencode


def main():
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=8768);args=p.parse_args()
    c=sqlite3.connect(args.home/'state/workbench.sqlite');c.row_factory=sqlite3.Row
    owners=[r[0] for r in c.execute("SELECT id FROM conversations UNION SELECT owner FROM jobs WHERE owner!='operator'")]
    token=(args.home/'state/operator.token').read_text().strip()
    def get(path):
        req=urllib.request.Request(f'http://127.0.0.1:{args.port}'+path,headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
    rows=[];errors=[]
    args.output.mkdir(parents=True,exist_ok=True)
    for owner in owners:
        try:
            a=get('/api/results?'+urlencode({'session':owner}))
            expected_engineering=c.execute('SELECT count(*) FROM engineering_jobs WHERE owner=?',(owner,)).fetchone()[0]
            expected_benchmark=c.execute('SELECT count(*) FROM jobs WHERE owner=?',(owner,)).fetchone()[0]
            expected_proposals=c.execute("SELECT count(*) FROM product_records WHERE owner=? AND kind='proposal'",(owner,)).fetchone()[0]
            assert len(a['results'])==expected_engineering+expected_benchmark+expected_proposals,(owner,'dropped results')
            assert a['owner']==owner
            assert len(a['files'])==sum(d['files'] for d in a['coverage'])
            assert all(f['integrity'] for f in a['files']),(owner,'invalid files')
            rows.append(dict(owner=owner,title=a['title'],phase=a['phase'],results=len(a['results']),files=len(a['files']),engines=sorted({r['kind'] for r in a['results']}),snapshot=a['snapshot_sha256']))
            if owner in ('pi-chat-390c76686d6d79a5','pi-chat-c1152c3ff3c7a5d8'):(args.output/(owner+'.json')).write_text(json.dumps(a,ensure_ascii=False,indent=2))
        except urllib.error.HTTPError as e:
            deleted=c.execute('SELECT deleted FROM sidebar_entries WHERE id=?',(owner,)).fetchone()
            if e.code==403 and deleted and deleted[0]:rows.append(dict(owner=owner,deleted=True,status='correctly denied'))
            else:errors.append(dict(owner=owner,error=e.read().decode()))
        except Exception as e:errors.append(dict(owner=owner,error=str(e)))
    result=dict(sessions=len(owners),checked=len(rows),errors=errors,rows=rows)
    (args.output/'all-sessions.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'sessions':len(owners),'checked':len(rows),'errors':errors},ensure_ascii=False))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
