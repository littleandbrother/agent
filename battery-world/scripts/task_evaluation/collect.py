#!/usr/bin/env python3
"""Collect sealed study evidence and public model answers, excluding credentials."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile

from run import ROOT, DOC, DATA, APP, save, ledger, prepare
from v2_common import RUNTIME, action


def main():
    who=prepare(); rows=ledger(who['owner'])
    if any(r['status']!='SETTLED' for r in rows):raise ValueError('USAGE_UNRESOLVED')
    counts={}
    for label,owner in [('default','pi-chat-f6463f6b0b663ebc'),('p08','pi-chat-468e6062c32232b5')]:
        s=action(owner,'repository_summary');state=action(owner,'repository_state')
        if state['status']!='IDLE':raise ValueError('CASE_RUNNING')
        save(ROOT/label/'final-summary.json',s);save(ROOT/label/'final-state.json',state)
        if label=='default':
            for name in ['notes/default-design.json','notes/vendor-review.json']:
                all_text='';offset=0
                while True:
                    value=action(owner,'repository_read',system_id=s['current_system'],path=name,offset=offset,limit=24000)
                    all_text+=value['content']
                    if value.get('next_offset') is None:break
                    offset=value['next_offset']
                save(ROOT/label/('final-'+Path(name).name),json.loads(all_text))
        release=s['releases'][-1]
        source=RUNTIME/'workbench/design-lab/repository/releases'/(release['id']+'.zip')
        seal=json.loads(source.with_suffix('.seal.json').read_text())
        if hashlib.sha256(source.read_bytes()).hexdigest()!=seal['sha256']:raise ValueError('RELEASE_IDENTITY')
        out=DOC/'deliveries';out.mkdir(exist_ok=True)
        shutil.copyfile(source,out/(label+'-review.zip'))
        with zipfile.ZipFile(source) as z:
            files=[n for n in z.namelist() if n.endswith('.pdf')]
            for n in files:(out/(label+'-'+Path(n).name)).write_bytes(z.read(n))
        counts[label]={'owner':owner,'state':state,'release':release,'pdfs':files}
    # Retain only published response content, usage and receipt identities.
    public=[]
    for p in sorted((ROOT/'model').glob('*/result.json')):
        value=json.loads(p.read_text());request=json.loads((p.parent/'request.json').read_text())
        public.append({'id':p.parent.name,'model':value.get('model'),'request':request,
            'answer':value['choices'][0]['message'].get('content',''),
            'finish_reason':value['choices'][0]['finish_reason'],'usage':value.get('usage'),
            'elapsed_s':value['elapsed_s'],'ledger':value['ledger']})
    usage={'owner':who['owner'],'requests':len(rows),'settled':sum(r['status']=='SETTLED' for r in rows),
        'charged_upper_bound_usd':sum(r['charged'] or 0 for r in rows),'groups':{}}
    for name,prefix in [('intake-initial','intake-Q'),('intake-format-fixed','intake-v2-'),
        ('edge-regression','edge-v3-'),('method-first','method-chain'),('method-output-fixed','method-v2-')]:
        selected=[r for r in public if r['id'].startswith(prefix)]
        usage['groups'][name]={'n':len(selected),'usd':sum(x['charged'] or 0 for r in selected for x in r['ledger']),
            'prompt_tokens':sum(r['usage']['prompt_tokens'] for r in selected),
            'cached_input_tokens':sum(r['usage'].get('prompt_cache_hit_tokens',0) for r in selected),
            'completion_tokens':sum(r['usage']['completion_tokens'] for r in selected),
            'seconds':sum(r['elapsed_s'] for r in selected)}
    usage['default_increment']={'requests':counts['default']['state']['model_calls']-53,
        'usd':counts['default']['state']['cost_upper_bound_usd']-1.1036151}
    usage['p08']={'requests':counts['p08']['state']['model_calls'],'usd':counts['p08']['state']['cost_upper_bound_usd']}
    usage['total_new_model_requests']=len(rows)+usage['default_increment']['requests']+usage['p08']['requests']
    usage['total_new_upper_bound_usd']=usage['charged_upper_bound_usd']+usage['default_increment']['usd']+usage['p08']['usd']
    save(ROOT/'usage.json',usage);save(ROOT/'deliveries.json',counts)
    evidence=DOC/'data';evidence.mkdir(exist_ok=True)
    # Explicit allowlist; raw reasoning and tokens remain in the private runtime.
    for name in ['intake-results.json','intake-results-v2.json','intake-freeze.json','intake-freeze-v2.json',
                 'usage.json','deliveries.json','api-consumer.json','preservation.json']:
        shutil.copyfile(ROOT/name,evidence/name)
    (evidence/'public-model-answers.json').write_text(json.dumps(public,ensure_ascii=False,indent=2))
    for folder,names in {
        'mechanisms':['freeze.json','inputs.json','refinement.json','result.json'],
        'mechanisms-controls':['result.json','stress-freeze.json','cache-proof.json'],
        'method-pilot':['protocol.json','selection.json','result.json'],
        'method-pilot-v2':['protocol.json','selection.json','result.json'],
        'edge-checks':['freeze.json','result.json'],
        'default':['final-summary.json','final-state.json','final-default-design.json','final-vendor-review.json'],
        'p08':['readback.json','task-definition-v2.json','final-summary.json','final-state.json'],
        'default/vendor-probe':['protocol.json','result.json','system.cir','system.log','waveform.csv']}.items():
        dest=evidence/folder;dest.mkdir(parents=True,exist_ok=True)
        for name in names:shutil.copyfile(ROOT/folder/name,dest/name)
    shutil.copytree(DATA,evidence/'question-bank',dirs_exist_ok=True)
    print(json.dumps(usage,ensure_ascii=False))


if __name__=='__main__':main()
