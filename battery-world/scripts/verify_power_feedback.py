#!/usr/bin/env python3
"""Qualify the power/program adapter through isolated Repository entry points.

No model is called. Native inputs are content cached across invocations. The
certificate is admitted only when native and deterministic controls all pass.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import zipfile
from types import SimpleNamespace

from bf_v2_environment import APP, environment


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',type=Path,default=Path.home()/'.local/share/bf-agent-architecture-v2')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--control',choices=['nominal','all'],default='all')
    parser.add_argument('--worker',action='store_true')
    args=parser.parse_args()
    if not args.worker:
        profile,env=environment(args.runtime)
        env['PYTHONPATH']+=':'+str(APP/'tests/agentlab')
        return subprocess.call([profile['paths']['CAD_PYTHON'],__file__,'--worker',
            '--runtime',str(args.runtime),'--output',str(args.output),'--control',args.control],env=env)
    from bfworld.agentlab.store import Store,canonical,identity
    from bfworld.agentlab.design_lab.service import DesignLab
    from bfworld.agentlab.design_lab.repository import Repository,file_hash
    from bfworld.agentlab.design_lab.contracts import sealed
    from bfworld.agentlab.design_lab.repository_task_checks import evaluator_identity
    from bfworld.agentlab.design_lab import repository_feedback_node as executor
    from bfworld.agentlab.design_lab import feedback_native
    from bfworld.agentlab.design_lab.repository_feedback_qualification import require,CONTROLS
    fixture=APP/'configs/reference_cases/piezo-feedback'
    definition=json.loads((fixture/'task.json').read_text())
    files={'design.json':(fixture/'design.json').read_text(),'firmware/main.c':(fixture/'main.c').read_text()}
    report_sources = {name:file_hash(APP/'packages/python/bfworld/src/bfworld/agentlab/design_lab'/name)
        for name in ('repository_task_reports.py','repository_task_result.py')}
    protocol={'schema_version':'bf-feedback-qualification-plan-v1','definition':definition,'files':files,
        'environment':executor.environment(),'checker':evaluator_identity({'task_definition':{'profile':definition['profile']}}),
        'runner_sha256':file_hash(__file__),'controls':sorted(CONTROLS),'report_sources':report_sources,
        'control_tests_sha256':file_hash(APP/'tests/agentlab/test_repository_feedback.py'),
        'budget':{'model_calls':0,'new_native_dispatches':48,'wall_seconds':2400}}
    run_id=identity(protocol); root=args.output/run_id
    sealed(root/'protocol.json',protocol)
    store=Store(args.output/'execution-cache/state')
    lab=DesignLab(SimpleNamespace(store=store,engineering=SimpleNamespace(lock=threading.Lock())),start_worker=False)
    repo=Repository(lab,{'id':'E-feedback-isolated','baseline':{'reference_seed':run_id},'protected_owners':[]})
    lab.repository=repo
    def admit(path):
        pointer=repo.root/'feedback-qualification/current.json';pointer.parent.mkdir(parents=True,exist_ok=True)
        pointer.write_text(canonical({'path':str(path),'sha256':file_hash(path)}))
        certificate=json.loads(path.read_text())
        s=repo.system(certificate['nominal_project'],certificate['nominal_system'])
        return require(repo,s)
    if (root/'qualification.json').is_file():
        retained=json.loads((root/'qualification.json').read_text())
        if retained['status']!='PASS':
            print(canonical({'status':'FAIL','retained':True,'root':str(root)}));return 1
        print(canonical({'status':'PASS','reused':True,'admission':admit(root/'qualification.json'),
            'new_native_dispatches':0,'root':str(root)}));return 0
    started=time.monotonic(); new_dispatches=[]
    original_native=feedback_native.native
    def guarded_native(folder,cache,content,toolset,local_budget,duration):
        def budget():
            if sum(1 for _ in cache.glob('*/dispatch.json'))>=48 or time.monotonic()-started>=2400:
                raise ValueError('FEEDBACK_QUALIFICATION_BUDGET')
            local_budget()
            new_dispatches.append({'netlist_sha256':__import__('hashlib').sha256(content.encode()).hexdigest(),
                'elapsed_s':round(time.monotonic()-started,3)})
            (root/'native-budget.json').write_text(canonical({'new_dispatches':new_dispatches,'cap':48}))
        return original_native(folder,cache,content,toolset,budget,duration)
    feedback_native.native=guarded_native
    current_owner=None
    def owner_for(label):
        owner='feedback-reference-'+identity({'run':run_id,'control':label})[:20]
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY)')
            db.execute('INSERT OR IGNORE INTO conversations VALUES(?)',(owner,))
        return owner
    def action(name,op,operator=False,**body):
        value=repo.handle(current_owner,{'action':'repository_'+name,'operation_id':op+'-'+run_id[:16],**body},operator)
        # Reuse metadata describes this invocation, not the sealed original result.
        path=root/(op+'.json')
        stable={k:v for k,v in value.items() if k not in ('reused','requested_system')}
        sealed(path,stable)
        return value
    def create(label,task=definition,source=files):
        nonlocal current_owner
        current_owner=owner_for(label)
        return action('task_create',label+'-create',True,title='电源—程序资格 · '+label,definition=task,files=source)
    def execute_and_check(label,task=definition,source=files):
        made=create(label,task,source)
        execution=action('task_execute',label+'-run',True,system_id=made['id'])
        check=action('validate',label+'-check',system_id=made['id'])
        print(canonical({'control':label,'execution_status':execution['status'],'metrics':execution['metrics'],
            'gates':{k:{'status':v['status'],'findings':v['findings']} for k,v in check['result']['gates'].items()},
            'root':str(root)}),flush=True)
        return made,execution,check
    def package(label,made,check):
        gates=check['result']['gates'];p=gates['power_service']['findings'];r=gates['receiver_service']['findings']
        content={'conclusion':f"{label}：接收{len(r['received_sequences'])}帧；本任务验收{check['status']}。",
            'sections':{
                'task_and_model':{'text':'20秒固定工况，线性压电单模、厂商LTC3588-1、声明的状态电流、主机C程序和数字接收。', 'sources':['design.json','source_model']},
                'mechanics_and_source':{'text':'机械等效损耗显式定义，原生完整轨迹参与机电能量核对。','sources':['design.json','source_model']},
                'firmware_and_receiver':{'text':f"程序启动时间{p['first_powered_s']}秒，上电{p['boots']}次，完成发送{p['completed_tx']}次，有效序号{r['received_sequences']}。",'sources':['firmware/main.c','receiver_service']},
                'energy_and_service':{'text':f"初始储能{p['initial_energy_j']:.9g}J；实际负载能量{p['load_energy_j']:.9g}J。任务供电检查{gates['power_service']['status']}。",'sources':['power_service','load_binding','coupling_numerics']},
                'conclusion_and_files':{'text':'报告、源文件、编译产物、完整原生波形、反馈迭代和独立检查一起按本候选交付。','sources':['delivery_version']}}}
        action('task_report',label+'-report',True,system_id=made['id'],content=json.dumps(content,ensure_ascii=False))
        release=action('release',label+'-release',True,system_id=made['id'],rationale='fixed no-Agent apparatus review',)
        archive=repo.root/'releases'/(release['id']+'.zip')
        with zipfile.ZipFile(archive) as z:
            manifest=json.loads(z.read('manifest.json'))
            if z.testzip() or manifest['target']!=made['id'] or manifest['task_execution']['target']!=made['id']:
                raise ValueError('FEEDBACK_DELIVERY_BINDING')
            for logical,ref in manifest['task_execution']['artifacts'].items():
                if __import__('hashlib').sha256(z.read('execution/'+logical)).hexdigest()!=ref['sha256']:
                    raise ValueError('FEEDBACK_DELIVERY_EXECUTION_CHANGED')
            if z.read('engineering/firmware/main.c').decode()!=files['firmware/main.c']:
                raise ValueError('FEEDBACK_DELIVERY_SOURCE_CHANGED')
            pdf=z.read('reports/task-report.pdf')
            (root/(label+'.pdf')).write_bytes(pdf)
        sealed(root/(label+'-delivery.json'),{'system':made['id'],'release':release['id'],'archive':str(archive),
            'sha256':file_hash(archive),'bytes':archive.stat().st_size,'status':'PASS'})
        return True
    made,nominal,check=execute_and_check('nominal')
    results={'nominal':check['status']=='PASS' and nominal['status']=='SUCCEEDED'}
    if not results['nominal'] or args.control=='nominal':
        print(canonical({'status':'PASS' if results['nominal'] else 'FAIL','controls':results,'root':str(root)}))
        return 0 if results['nominal'] else 1
    nominal_delivery=package('nominal',made,check)
    # CRC does not change activity, so every physical iterate must come from cache.
    bad_files={**files,'firmware/main.c':files['firmware/main.c'].replace('0xA5','0xA4')}
    _,bad,bad_check=execute_and_check('bad-frame',source=bad_files)
    results['bad-frame']=(bad_check['result']['gates']['receiver_service']['status']=='FAIL' and
        bool(bad_check['result']['gates']['receiver_service']['findings']['invalid_frames']) and
        bad['metrics'].get('native_dispatches')==[])
    zero=copy.deepcopy(definition)
    for key in ('acceleration_peak_m_s2','initial_storage_v','initial_output_v'): zero['scenario'][key]=0
    for p in zero['parameters']:
        if p['name'] in zero['scenario'] and p['role']=='constraint': p['value']=zero['scenario'][p['name']]
    _,_,zero_check=execute_and_check('no-energy',zero)
    results['no-energy']=(zero_check['result']['gates']['power_service']['status']=='FAIL' and
        zero_check['result']['gates']['power_service']['findings']['completed_tx']==0)
    cold=copy.deepcopy(definition)
    cold['scenario'].update(initial_storage_v=0,initial_output_v=0)
    for p in cold['parameters']:
        if p['name'] in cold['scenario'] and p['role']=='constraint': p['value']=cold['scenario'][p['name']]
    cold_made,_,cold_check=execute_and_check('delayed-start',cold)
    results['same-version-delivery']=nominal_delivery and package('delayed-start',cold_made,cold_check)
    first=cold_check['result']['gates']['power_service']['findings'].get('first_powered_s')
    results['delayed-start']=first is not None and first>1
    current_owner=owner_for('nominal')
    repeat=action('task_execute','nominal-reuse',True,system_id=made['id'])
    expired=copy.deepcopy(definition); expired['scenario']['sample_validity_s']=.001
    changed=action('task_define','expiry-definition',True,expected_revision=1,definition=expired)
    reused=action('task_execute','expiry-run',True,system_id=changed['id'])
    expiry=action('validate','expiry-check',system_id=changed['id'])
    results['requirements-reuse']=repeat['id']==reused['id']==nominal['id'] and reused['reused']
    results['expired-sample']=expiry['result']['gates']['receiver_service']['status']=='FAIL'
    # Deterministic failure injection exercises reset, unknown dispatch and
    # unconverged/tampered evidence without repeating successful native work.
    tests=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(APP/'tests/agentlab'),
        '-p','test_repository_feedback.py','-v'],capture_output=True,text=True)
    (root/'deterministic-controls.log').write_text(tests.stdout+tests.stderr)
    if tests.returncode: print(tests.stdout+tests.stderr,flush=True)
    for control in ('brownout','nonconvergence','raw-binding','unknown-dispatch'):
        results[control]=tests.returncode==0 and ('test_'+control.replace('-','_') in tests.stderr)
    if (any(digest!=file_hash(APP/'packages/python/bfworld/src/bfworld/agentlab/design_lab'/name)
            for name,digest in report_sources.items()) or
            protocol['control_tests_sha256']!=file_hash(APP/'tests/agentlab/test_repository_feedback.py') or
            protocol['runner_sha256']!=file_hash(__file__) or protocol['environment']!=executor.environment() or
            protocol['checker']!=evaluator_identity(repo.system(made['project_id'],made['id']))):
        raise ValueError('FEEDBACK_QUALIFICATION_SOURCES_CHANGED')
    value={'schema_version':'bf-feedback-qualification-v1','status':'PASS' if all(results.values()) else 'FAIL',
        'protocol':run_id,'controls':results,'environment':executor.environment(),'checker':evaluator_identity(repo.system(made['project_id'],made['id'])),
        'nominal_project':made['project_id'],'nominal_system':made['id'],'nominal_execution':nominal['id'],'artifact_root':str(repo.root/'blobs'),
        'model_calls':0,'new_native_dispatches':len(new_dispatches),'wall_seconds':round(time.monotonic()-started,3),
        'evidence':{str(p.relative_to(root)):file_hash(p) for p in root.iterdir() if p.is_file() and p.name not in ('qualification.json',)}}
    value={'id':'FQ-'+identity(value),**value}
    sealed(root/'qualification.json',value)
    if value['status']=='PASS':
        admission=admit(root/'qualification.json')
        print(canonical({'admission':admission}),flush=True)
    print(canonical({'status':value['status'],'controls':results,'root':str(root),'new_native_dispatches':len(new_dispatches)}))
    return 0 if value['status']=='PASS' else 1


if __name__=='__main__': sys.exit(main())
