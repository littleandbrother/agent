#!/usr/bin/env python3
"""Local native UI acceptance fixture. No model invocation or product certification.
Run: PYTHONPATH=packages/python/bfworld/src .venv/bin/python scripts/verify_results_workspace.py --root /tmp/bf-results-qa [--serve 8781]
"""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import time
import zipfile
from unittest.mock import patch
from bfworld.agentlab.server import Workbench, handler
from bfworld.agentlab.solar_companion import definition, changed


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--serve',type=int);args=parser.parse_args()
    args.root.mkdir(parents=True,exist_ok=True);(args.root/'paid-window-closed.json').write_text('{}')
    app=Workbench(args.root/'state')
    try:
        with patch.object(app.conversations,'start'):
            owner=app.conversations.create('本地成果验收 · CAD / SPICE / MCU（非 Agent 实验）',None,'results-native-qa')['id']
        source=app.conversations.detail(owner)['messages'][0]['id']
        current=app.assemblies.revisions(owner)
        if not current:app.assemblies.write(owner,dict(source_message_id=source,operation_id='qa-assembly',expected_revision=0,payload=definition()))
        workspace=args.root/'participants'/owner;workspace.mkdir(parents=True,exist_ok=True)
        specs=[('cadquery','cad','main.py','import cadquery as cq\ns=cq.Workplane("XY").box(40,24,3).faces(">Z").workplane().hole(4)\ncq.exporters.export(s,"assembly.step")\n'),
               ('spice','rc','main.cir','RC native UI acceptance fixture\nV1 in 0 PULSE(0 3.3 0 1u 1u 10m 20m)\nR1 in out 1k\nC1 out 0 1u\n.tran 10u 5m\n.end\n'),
               ('firmware-stm32l031','mcu','main.c','volatile unsigned ticks; int main(void){while(1){ticks++;}}\n')]
        jobs=[]
        for kind,folder,name,code in specs:
            root=workspace/folder;root.mkdir(exist_ok=True);(root/name).write_text(code)
            (root/'project.json').write_text(json.dumps(dict(schema_version='bf-engineering-project-v1',kind=kind,entrypoint=name,files=[name],interfaces={'units':'mm' if kind=='cadquery' else 'SI','scope':'UI acceptance fixture; not a complete product'})))
            old=next((j for j in app.engineering.jobs(owner) if j['operation']=='qa-'+folder),None)
            j=old or app.engineering.submit(owner,dict(operation_id='qa-'+folder,engine='engineering-project',parameters={'assembly_revision':1,'project_path':folder+'/project.json'}),initiator='operator')
            until=time.monotonic()+180
            while j['status'] in ('RUNNING','QUEUED') and time.monotonic()<until:
                time.sleep(.2);j=app.engineering.get(owner,j['id'])
            if j['status']!='SUCCEEDED':raise RuntimeError(str((j['status'],j.get('error'))))
            jobs.append(j['id'])
        if len(app.assemblies.revisions(owner))==1:app.assemblies.write(owner,dict(source_message_id=source,operation_id='qa-camera',expected_revision=1,payload=changed(definition(),camera=-35)))
        catalog=app.results.inspect(owner)
        assert all(f['applicability']['state']==('reused' if f['created_revision']==1 else 'current') for f in catalog['files'])
        step=next(f for f in catalog['files'] if f['name']=='project-assembly.step')
        mesh=next(f for f in catalog['files'] if f['name']=='project-preview-mesh.json')
        m=json.loads(app.results.file(owner,mesh['id'])[0].read_text());assert m['source_sha256']==step['sha256'] and m['triangles']
        raw=next(f for f in catalog['files'] if f['name']=='project-trace.raw');series=app.results.series(owner,raw['id']);assert series['total_points']>100
        exported=app.deliverables.package(owner,catalog['snapshot_sha256']);archive=app.assemblies.file(owner,exported['id'])[0]
        with zipfile.ZipFile(archive) as z:
            manifest=json.loads(z.read('成果清单.json'));assert manifest==catalog
            for f in catalog['files']:assert hashlib.sha256(z.read(f['archive_path'])).hexdigest()==f['sha256']
        receipt=dict(status='passed',owner=owner,jobs=jobs,files=len(catalog['files']),snapshot_sha256=catalog['snapshot_sha256'],native_mesh_triangles=len(m['triangles']),spice_points=series['total_points'],archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),model_calls=0,hardware_verified=False,scope='Native tool and UI infrastructure acceptance fixtures, not Agent autonomy or product acceptance.')
        (args.root/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt),flush=True)
        if args.serve:
            server=ThreadingHTTPServer(('127.0.0.1',args.serve),handler(app));app.conversations.port=args.serve
            print('Local acceptance server: localhost:'+str(args.serve),flush=True);server.serve_forever()
    finally:app.stop.set();app.thread.join(3);app.lock.close()


if __name__=='__main__':main()
