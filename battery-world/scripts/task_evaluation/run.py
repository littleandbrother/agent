#!/usr/bin/env python3
"""Finite study runner through the existing V2 provider and append-only ledger."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import urllib.request

APP = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(APP/'scripts'), str(APP/'packages/python/bfworld/src')]
from bf_v2_environment import environment
from v2_common import RUNTIME, action, create_pi
from bfworld.agentlab.design_lab.repository_task_intake import prompt, validate

ROOT = RUNTIME/'task-evaluation'
DOC = APP/'docs/agentlab/architecture-v2/task-evaluation-20261017'
DATA = APP/'configs/reference_cases/task-evaluation'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    if path.exists() and path.read_text() != raw:
        raise ValueError('IMMUTABLE_RECEIPT_EXISTS: '+str(path))
    if not path.exists(): path.write_text(raw)


def ledger(owner):
    p, _ = environment(RUNTIME)
    with sqlite3.connect((Path(p['home'])/'state/workbench.sqlite').as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        return [dict(r) for r in db.execute('SELECT id,status,charged,reserved,usage,error,response_hash FROM model_requests WHERE owner=? ORDER BY created', (owner,))]


def prepare():
    ROOT.mkdir(parents=True, exist_ok=True)
    if (ROOT/'identity.json').exists(): return json.loads((ROOT/'identity.json').read_text())
    p, _ = environment(RUNTIME)
    key = Path(p['paths']['PROVIDER_KEY_FILE']).read_text().strip()
    preflight = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    for name, url in [('models','https://api.deepseek.com/models'), ('balance','https://api.deepseek.com/user/balance')]:
        req = urllib.request.Request(url, headers={'Authorization':'Bearer '+key})
        with urllib.request.urlopen(req, timeout=30) as r: preflight[name] = json.load(r)
    if not preflight['balance']['is_available'] or 'deepseek-flash' not in [m['id'] for m in preflight['models']['data']]:
        raise ValueError('PROVIDER_NOT_READY')
    save(ROOT/'provider-preflight.json', preflight)
    from task_design_ops import audit
    save(ROOT/'protected-before.json', audit())
    who = create_pi('任务评估与契约实验 · 48题', 'task-assessment-study-20261017')
    result = action(who['id'], 'method_authorize', task_id='method-study-task-assessment-20261017',
                    wall_authorization_text='持续运行 不设置时间限制', model_profile='engineering-reasoning-efficient-v5')
    token = result.pop('participant_token')
    (ROOT/'provider.token').write_text(token); (ROOT/'provider.token').chmod(0o600)
    identity = {'owner':who['id'], 'authority':result, 'model':'deepseek-flash'}
    save(ROOT/'identity.json', identity)
    return identity


def model_call(name, system, user, max_tokens=6500):
    who = prepare(); folder = ROOT/'model'/name
    if (folder/'result.json').exists(): return json.loads((folder/'result.json').read_text())
    if (folder/'started.json').exists(): raise ValueError('MODEL_CALL_RECONCILIATION_REQUIRED: '+name)
    before = ledger(who['owner'])
    if any(r['status'] in ('UNKNOWN', 'DISPATCHED') for r in before): raise ValueError('MODEL_USAGE_UNRESOLVED')
    payload = {'model':who['model'], 'max_tokens':max_tokens, 'temperature':0,
               'messages':[{'role':'system','content':system}, {'role':'user','content':user}]}
    save(folder/'request.json', payload)
    save(folder/'started.json', {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'prior_ids':[r['id'] for r in before]})
    token = (ROOT/'provider.token').read_text().strip()
    req = urllib.request.Request('http://127.0.0.1:8870/v1/chat/completions', data=json.dumps(payload,ensure_ascii=False).encode(),
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=1200) as response: result = json.load(response)
    result['elapsed_s'] = time.monotonic()-started
    result['ledger'] = [r for r in ledger(who['owner']) if r['id'] not in {r['id'] for r in before}]
    save(folder/'result.json', result)
    if not result['ledger'] or any(r['status'] != 'SETTLED' for r in result['ledger']): raise ValueError('MODEL_USAGE_UNRESOLVED')
    return result


def parse_json(result):
    raw = result['choices'][0]['message']['content'].strip()
    if raw.startswith('```'): raw = raw.split('\n',1)[1].rsplit('```',1)[0]
    return json.loads(raw)


def intake(revision='v1'):
    prepare()
    corpus = json.loads((DATA/'requests.json').read_text())
    key = {r['id']:r for r in json.loads((DATA/'evaluation-key.json').read_text())}
    suffix='' if revision=='v1' else '-'+revision
    save(ROOT/('intake-freeze'+suffix+'.json'), {'prompt_sha256':hashlib.sha256(prompt().encode()).hexdigest(),
        'corpus':json.loads((DATA/'manifest.json').read_text()), 'module_sha256':hashlib.sha256((APP/'packages/python/bfworld/src/bfworld/agentlab/design_lab/repository_task_intake.py').read_bytes()).hexdigest()})
    results=[]
    for row in corpus:
        result=model_call('intake'+suffix+'-'+row['id'], prompt(), row['request'])
        item={**row,'finish_reason':result['choices'][0]['finish_reason']}
        try:
            value=parse_json(result);item['assessment']=value
            item['validated']=validate(row['request'], value);item['schema_valid']=True
        except (ValueError, KeyError, TypeError) as exc:
            item['schema_valid']=False;item['error']=str(exc)
        a=item.get('assessment',{});g=key[row['id']]
        item['metrics']={'intent':a.get('intent')==g['intent'], 'scope':a.get('scope')==g['scope'],
            'required_domains':set(g['required_domains']).issubset(a.get('domains',[])),
            'missing_inputs':bool(a.get('missing_inputs'))==g['missing_input_expected'],
            'conflict':g['feasibility'] is None or a.get('feasibility')==g['feasibility']}
        save(ROOT/('intake'+suffix)/f"{row['id']}.json", item);results.append(item)
        print(row['id'], item['schema_valid'], item['metrics'], flush=True)
    scores={split:{k:sum(r['metrics'][k] for r in results if r['split']==split) for k in results[0]['metrics']} for split in ('development','test')}
    save(ROOT/('intake-results'+suffix+'.json'),{'count':len(results),'scores':scores,'schema_valid':sum(r['schema_valid'] for r in results),'results':results,
        'interpretation':'same-corpus engineering regression; not a new unseen generalization test' if revision!='v1' else 'initial audit'})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','intake']);parser.add_argument('--revision',default='v1');a=parser.parse_args()
    if a.mode=='prepare': print(json.dumps(prepare(),ensure_ascii=False))
    elif a.mode=='intake': intake(a.revision)
