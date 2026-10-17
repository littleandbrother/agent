"""Read back complete candidate trees, actual inputs, report archives and costs."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

APP=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(APP/'scripts'))
from v2_common import RUNTIME,action


def digest(raw):return hashlib.sha256(raw).hexdigest()


def main():
    who=json.loads((RUNTIME/'task-design/owner.json').read_text());owner=who['owner']
    state=action(owner,'repository_state')
    if state['status']!='IDLE':raise ValueError('COLLECT_AFTER_IDLE')
    snapshot=HERE/'final-public-snapshot.json'
    if not snapshot.exists():
        subprocess.run([sys.executable,str(HERE/'collect.py'),'--output',str(snapshot)],check=True,capture_output=True,text=True)
    public=json.loads(snapshot.read_text());view=action(owner,'repository_view')
    prior=json.loads((RUNTIME/'task-design/before-report-correction.json').read_text())['view']
    assert view['project']==prior['project']
    assert view['systems']==prior['systems']
    assert view['task_executions']==prior['task_executions']
    systems={s['id']:s for s in view['systems']};root=RUNTIME/'workbench/design-lab/repository'
    references=0
    for system in systems.values():
        for ref in system['files'].values():
            assert digest((root/'blobs'/ref['sha256']).read_bytes())==ref['sha256'];references+=1
        if system['parent']:
            parent=systems[system['parent']];changed={d['path'] for d in system['design_changes']}
            assert set(parent['files'])<=set(system['files'])
            for path,ref in parent['files'].items():
                if path not in changed:assert ref==system['files'][path]
    native=Counter();source_inputs=set();storage_inputs=set()
    for run in view['task_executions']:
        system=systems[run['target']]
        for path,sha in run['descriptor']['inputs'].items():assert system['files'][path]['sha256']==sha
        for path,ref in run['artifacts'].items():
            assert digest((root/'blobs'/ref['sha256']).read_bytes())==ref['sha256'];references+=1
        for path,artifact in [('firmware/main.c','main.c'),('design.json','design.json')]:
            assert system['files'][path]['sha256']==run['artifacts'][artifact]['sha256']
        for kind in run['metrics']['native_dispatches']:
            hashes=source_inputs if kind=='source' else storage_inputs
            h=run['artifacts'][kind+'.cir']['sha256']
            assert h not in hashes,'unchanged native input was dispatched twice'
            hashes.add(h);native[kind]+=1
    adopted=[d['to_design'] for d in public['decisions'] if d['decision']=='ADOPT_PASSED']
    assert len(adopted)==2
    destination=HERE/'deliverables';destination.mkdir(exist_ok=True)
    deliveries=[]
    for index,target in enumerate(adopted,1):
        release=next(r for r in reversed(view['releases']) if r['target']==target)
        archive=root/'releases'/(release['id']+'.zip')
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            manifest=json.loads(z.read('manifest.json'))
            report=json.loads(z.read('reports/input.json'))
            quality=json.loads(z.read('reports/quality.json'))
            assert manifest['target']==report['system_id']==quality['system_commit']==target
            assert report['measured_facts']
            assert '2.5' in z.read('reports/task-report.md').decode()
            for path,ref in manifest['files'].items():assert digest(z.read('engineering/'+path))==ref['sha256']
            for path,ref in manifest['task_execution']['artifacts'].items():assert digest(z.read('execution/'+path))==ref['sha256']
            for path,ref in quality['outputs'].items():assert digest(z.read('reports/'+path))==ref['sha256']
            pdf=destination/f'Pi-cycle-{index}.pdf';pdf.write_bytes(z.read('reports/task-report.pdf'))
            (destination/f'Pi-cycle-{index}.md').write_bytes(z.read('reports/task-report.md'))
            qa=HERE/'verification'/f'cycle-{index}-corrected-pdf';qa.mkdir(exist_ok=True)
            subprocess.run(['pdftoppm','-r','90','-png',str(pdf),str(qa/'page')],check=True,capture_output=True)
        package=destination/f'Pi-cycle-{index}-review.zip';shutil.copyfile(archive,package)
        deliveries.append({'cycle':index,'system':target,'release':release['id'],'archive_sha256':digest(package.read_bytes()),
            'archive_entries':len(zipfile.ZipFile(package).namelist()),'pdf':str(pdf),'package':str(package),'pages':quality['pages']})
    requests=public['model_requests'];stages=[('design-cycle-1',requests[:25]),('design-cycle-2',requests[25:39]),('report-review',requests[39:])]
    costs={name:{'requests':len(rows),'local_registered_usd':sum(r['charged'] for r in rows),
                 'statuses':dict(Counter(r['status'] for r in rows))} for name,rows in stages}
    trace=[json.loads(line) for line in (RUNTIME/'workbench/sessions'/owner/'trace.jsonl').read_text().splitlines()]
    restores=[e for e in trace if e.get('type')=='repository_state_restored']
    result={'status':'PASS','owner':owner,'project_id':who['project_id'],'current':state['current_system'],
        'systems':len(systems),'executions':len(view['task_executions']),'validated_file_references':references,
        'native_dispatches':dict(native),'reference_execution_reuses':sum(bool(e['metrics'].get('reference_reused_from')) for e in view['task_executions']),
        'source_result_reuses':sum(bool(e['metrics'].get('source_reused_from')) for e in view['task_executions']),
        'report_correction_design_and_execution_unchanged':True,'costs':costs,'skills':public['skills'],
        'controller_restores':len(restores),'deliveries':deliveries,
        'intervention':{'reference_and_platform':'Codex','device_revisions':'Pi','report_review':'Codex unit/wording feedback, Pi corrections'},
        'scope':'nominal-reference-chain','physical':'NOT_TESTED'}
    path=HERE/'result.json'
    if path.exists():raise ValueError('FINAL_RESULT_EXISTS')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
