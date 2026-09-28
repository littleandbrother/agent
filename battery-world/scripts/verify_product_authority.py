"""Scripted Pi integration, real native jobs, zero external model calls.

This is a deterministic transport/execution test, NOT autonomous design evidence.
Run with PYTHONPATH=packages/python/bfworld/src and an unused --output directory.
"""
import argparse
import json
from pathlib import Path
import threading
import time
from http.server import ThreadingHTTPServer

from bfworld.agentlab.server import Workbench, handler
from bfworld.agentlab.provider import MODEL
from bfworld.agentlab.solar_companion import definition
from bfworld.agentlab.store import identity


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    root=Path(args.output).resolve();root.mkdir(parents=True,exist_ok=False)
    (root/'paid-window-closed.json').write_text('{}')
    app=Workbench(root/'state');server=ThreadingHTTPServer(('127.0.0.1',0),handler(app));app.conversations.port=server.server_port
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    calls=[];owner=None
    manifest={'schema_version':'bf-engineering-project-v1','kind':'spice','entrypoint':'main.cir','files':['main.cir'],'interfaces':{'units':'SI','load_source':'synthetic RC transport fixture'}}
    netlist='RC transport fixture\nV1 a 0 PULSE(0 1 0 1u 1u 1m 2m)\nR1 a b 1k\nC1 b 0 1u\n.tran 10u 1m\n.end\n'
    sequence=[('bf_engineering',{'action':'skill','skill_id':'engineering-project'}),
              ('write',{'path':'main.cir','content':netlist}),
              ('write',{'path':'project.json','content':json.dumps(manifest)}),
              ('bf_engineering',{'action':'run','engine':'engineering-project','parameters':{'assembly_revision':1,'project_path':'project.json'},'operation_id':'pi-authored-circuit'})]
    def fixture(who,payload,on_chunk=None):
        index=len(calls);calls.append({'owner':who,'request_hash':identity(payload)})
        base={'id':'scripted-'+str(index),'object':'chat.completion.chunk','created':int(time.time()),'model':MODEL}
        if index<len(sequence):name,arguments=sequence[index]
        else:
            jobs=app.engineering.jobs(who)
            if jobs and jobs[0]['status'] in ('QUEUED','RUNNING'):
                time.sleep(.15);name,arguments='bf_engineering',{'action':'job','job_id':jobs[0]['id']}
            else:name=None
        if name:
            on_chunk({**base,'choices':[{'index':0,'delta':{'role':'assistant','tool_calls':[{'index':0,'id':'call-'+str(index),'type':'function','function':{'name':name,'arguments':json.dumps(arguments)}}]},'finish_reason':None}]})
            finish='tool_calls'
        else:
            on_chunk({**base,'choices':[{'index':0,'delta':{'role':'assistant','content':'脚本化链路检查结束；工程结果按真实 Job 记录。'},'finish_reason':None}]});finish='stop'
        on_chunk({**base,'choices':[{'index':0,'delta':{},'finish_reason':finish}]})
        on_chunk({**base,'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}})
        return {'model':MODEL,'usage':{'prompt_tokens':20,'completion_tokens':3,'total_tokens':23}}
    app.provider.complete=fixture
    try:
        owner=app.conversations.create('以脚本化工具序列验收电路工程入口',None,'scripted-native')['id']
        source=app.conversations.detail(owner)['messages'][0]['id']
        app.assemblies.write(owner,{'source_message_id':source,'operation_id':'declared-fixture','expected_revision':0,'payload':definition()})
        (root/'paid-window-closed.json').unlink();app.conversations.retry(owner)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            events=app.conversations.events(owner)
            if any(e['data']['type']=='turn_complete' for e in events):break
            if len(calls)>30:raise RuntimeError('SCRIPTED_SEQUENCE_LIMIT')
            time.sleep(.1)
        jobs=app.engineering.jobs(owner)
        assert len(jobs)==1 and jobs[0]['status']=='SUCCEEDED', [(j['status'],j.get('error')) for j in jobs]
        job=jobs[0];assert job['initiator']=='participant'
        assert job['project']['sources']['main.cir']==netlist
        loaded=next(e['data'] for e in events if e['data']['type']=='harness_loaded')
        assert loaded['source']['loaded_modules']['product']==loaded['loaded']['product']
        assert any(e['data']['type']=='product_context_snapshot' for e in events)
        assert any(e['data']['type']=='turn_complete' for e in events)
        for artifact in job['result']['artifacts']:app.engineering.artifact(owner,job['id'],artifact['name'])
        receipt={'schema_version':'bf-product-authority-acceptance-v1','status':'passed','owner':owner,'job':job['id'],
                 'loaded_product_sha256':loaded['loaded']['product'],'project_sha256':job['project_sha256'],
                 'readback':job['result']['independent_readback'],'scripted_responses':len(calls),'external_model_calls':0,
                 'scope':'Real Pi public tools and native ngspice; scripted model responses, no autonomy efficacy or physical product claim.',
                 'verdict':app.deliverables.inspect(owner)['verdict']}
        (root/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(receipt,ensure_ascii=False))
    finally:
        if owner and owner in app.conversations.processes:app.conversations.stop(owner)
        limit=time.monotonic()+6
        while app.conversations.starting and time.monotonic()<limit:time.sleep(.1)
        server.shutdown();server.server_close();app.stop.set();app.thread.join(3);app.lock.close()


if __name__=='__main__':main()
