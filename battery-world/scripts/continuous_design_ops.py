#!/usr/bin/env python3
"""Operate the original V2 piezo task; retain every attempt and historical owner."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import urllib.request

from bf_v2_environment import APP, environment
from v2_common import RUNTIME, action, restart, request

ROOT = RUNTIME/'continuous-design'
OWNER = json.loads((RUNTIME/'task-design/owner.json').read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    if path.exists() and path.read_text() != raw:
        raise ValueError('IMMUTABLE_RECEIPT_EXISTS:'+str(path))
    if not path.exists(): path.write_text(raw)


def snapshot():
    from publish_lab_bridge import protected_state
    profile, _ = environment(RUNTIME)
    db = sqlite3.connect((Path(profile['home'])/'state/workbench.sqlite').as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    protected = {}
    for owner in profile['protected_owners']:
        rows = {}
        for table, key in [('conversations','id'),('model_requests','owner')]:
            values = [dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE {key}=? ORDER BY rowid',(owner,))]
            rows[table] = {'count':len(values), 'sha256':hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()}
        protected[owner] = rows
    return {'production':protected_state(),'v2_protected':protected,
            'busy':[dict(r) for r in db.execute("SELECT id,status FROM conversations WHERE status IN ('RUNNING','STARTING','QUEUED')")]}


def compact_artifacts():
    """Share completed artifacts; preserve paths, bytes and separate inodes."""
    import importlib.util
    helper = APP/'docs/agentlab/architecture-v2/continuous-design-20261018/clone_completed_native.py'
    spec = importlib.util.spec_from_file_location('continuous_native_storage', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.compact()
    return {'cloned_files':len(value['cloned']), 'free_bytes':value['after_free']}


def prepare():
    if (ROOT/'transition.json').exists(): return json.loads((ROOT/'transition.json').read_text())
    before = snapshot()
    if before['busy']: raise ValueError('V2_MUST_BE_IDLE')
    save(ROOT/'protected-before.json', before)
    started = restart(); save(ROOT/'service-start.json', started)
    profile, _ = environment(RUNTIME)
    key = Path(profile['paths']['PROVIDER_KEY_FILE']).read_text().strip()
    preflight = {}
    for label, url in [('balance','https://api.deepseek.com/user/balance'),('models','https://api.deepseek.com/models')]:
        req = urllib.request.Request(url, headers={'Authorization':'Bearer '+key})
        with urllib.request.urlopen(req, timeout=30) as response: preflight[label] = json.load(response)
    save(ROOT/'provider-preflight.json', {'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**preflight})
    if not preflight['balance']['is_available'] or 'deepseek-flash' not in [m['id'] for m in preflight['models']['data']]:
        raise ValueError('PROVIDER_NOT_READY')
    # Preserve the qualified native cache. Entries retain their deck/tool identity,
    # completion hashes and raw waves; the executor verifies them before reuse.
    source = RUNTIME/'power-feedback/qualification/execution-cache/design-lab/repository/feedback-native-cache'
    target = RUNTIME/'workbench/design-lab/repository/feedback-native-cache'
    copied = []
    for path in sorted(source.iterdir()):
        if not path.is_dir() or not (path/'completed.json').is_file(): continue
        value = json.loads((path/'completed.json').read_text())
        if value['status'] != 'SUCCEEDED': continue
        for name, digest in value['outputs'].items():
            if hashlib.sha256((path/name).read_bytes()).hexdigest() != digest: raise ValueError('REFERENCE_CACHE_TAMPER')
        if not (target/path.name).exists(): shutil.copytree(path,target/path.name)
        copied.append(value['key'])
    save(ROOT/'cache-import.json', {'source':str(source),'entries':copied,'new_native_solves':0})
    state = action(OWNER['owner'],'repository_state')
    save(ROOT/'original-owner-state.json',state)
    fixture = APP/'configs/reference_cases/piezo-feedback'
    task = json.loads((fixture/'task.json').read_text())
    task['intent'] = 'optimize'; task['phase'] = 'continuous-feedback-cold-start'
    task['goal'] = '零初始储能，在固定30Hz振动和20秒窗口内完成至少3次有效采样与接收；自主选择允许范围内的设计或程序修订。'
    for name in ('initial_storage_v','initial_output_v'): task['scenario'][name] = 0.0
    for p in task['parameters']:
        if p['name'] in ('initial_storage_v','initial_output_v'): p['value'] = 0.0
    task['scenario']['boundary'] = '零VIN/VOUT初态；无人工充电；厂商PMIC与电压驱动程序闭环；主机C及数字接收'
    task['scenario']['parameter_basis'] = 'BFA-040已资格化零储能控制；本次固定外部要求和模型，设计参数与程序允许修订'
    save(ROOT/'task-definition-input.json',task)
    transition = action(OWNER['owner'],'repository_task_define',project_id=OWNER['project_id'],
        expected_revision=state['revision'],operation_id='continuous-feedback-phase-v1',definition=task,
        rationale='用户批准连续反馈设计。显式切换已资格化适配器与零储能服务条件，原工程历史、采用版、会话与费用保留；初始设计/程序迁移至该ABI的固定参考输入。',
        files={'design.json':(fixture/'design.json').read_text(),'firmware/main.c':(fixture/'main.c').read_text()})
    auth = action(OWNER['owner'],'authorize',wall_authorization_text='持续运行 不设置时间限制',model_profile='engineering-reasoning-efficient-v5')
    auth.pop('participant_token',None); save(ROOT/'authority.json',auth)
    save(ROOT/'transition.json',transition)
    return {'owner':OWNER['owner'],'project_id':OWNER['project_id'],'system_id':transition['id'],'cache_entries':len(copied)}


def start(cycle, resume=False):
    assert cycle in (1,2)
    path = ROOT/(f'cycle-{cycle}-'+('resume-dispatch.json' if resume else 'dispatch.json'))
    if path.exists(): return json.loads(path.read_text())
    state = action(OWNER['owner'],'repository_state')
    if state['status'] == 'RUNNING': raise ValueError('ORIGINAL_OWNER_ALREADY_RUNNING')
    goal = ('本轮已获用户授权。读取本次task_definition/task_schema/task_state，旧node-reference程序与采用结论保留为历史，当前使用node-feedback-v1。'
            '目标为固定零初始储能、20秒内至少3帧。你独立决定观察、实验和真实修订；不改变场景、物理模型、数值协议和验收。'
            '完成至少一项有工程意义的design.json参数或firmware/main.c修改；实际task_execute、validate，根据证据decide。'
            '保留失败试验，避免重复读取大历史；task_result读取已有结果。最后task_report、release、close。报告由你完成，不能只到工具执行成功。'
            '本轮为连续设计的第'+str(cycle)+'轮。'+('基于当前反馈候选完成第一轮。' if cycle==1 else '必须从上一轮当前候选继续，只选择一项小修订并与父版比较；本轮新增一次执行后即作出结论并交付，失败也保留，不展开更多备选。'))
    if resume:
        goal='原会话从平台中断处继续本轮。当前修订的联合计算已完成，先读取已有 task_result，完成独立检查、设计决定、报告、同版交付和 close。保存本轮已有试验；相同输入不重复执行。'
    result = action(OWNER['owner'],'repository_start',goal=goal)
    record = {'cycle':cycle,'resume':resume,'base_system':state['current_system'],'goal':goal,**result}
    save(path,record); return record


def status():
    state=action(OWNER['owner'],'repository_state')
    summary=action(OWNER['owner'],'repository_summary')
    return {'state':state,'gates':summary['gates'],'current_system':summary['current_system'],
            'releases':summary['releases'][-4:]}


def drive():
    def wait(cycle):
        while True:
            state=action(OWNER['owner'],'repository_state')
            if state['unknown_requests']:raise ValueError('ORIGINAL_PROVIDER_UNKNOWN_STOP')
            if state['status'] not in ('RUNNING','STARTING'):break
            time.sleep(5)
        if state['status']=='FAILED':raise ValueError('ORIGINAL_CONTROLLER_FAILED:'+str(state['error']))
        view=action(OWNER['owner'],'repository_view')
        sid=view['project']['submitted']
        if not any(r['target']==sid for r in view['releases']):raise ValueError('ORIGINAL_CYCLE_NOT_DELIVERED')
        save(ROOT/f'cycle-{cycle}-view.json',view)
        print(json.dumps({'stage':'continuous','cycle':cycle,'status':'DELIVERED','system':sid}),flush=True)
    for cycle in (1,2):
        if (ROOT/f'cycle-{cycle}-view.json').exists():continue
        if cycle==2:start(2)
        wait(cycle)
    # New work policy is loaded only at a completed original-owner boundary.
    if not (ROOT/'pilot-service-start.json').exists():save(ROOT/'pilot-service-start.json',restart())
    from run_organization_pilot import prepare as prepare_pilot, run as run_pilot
    prepare_pilot()
    print(json.dumps(run_pilot('sources')),flush=True)
    print(json.dumps(run_pilot('organizations')),flush=True)
    return {'status':'FINITE_LIST_FINISHED'}


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','start','resume','status','capture','preservation','drive']);p.add_argument('--cycle',type=int,default=1)
    a=p.parse_args()
    if a.mode=='prepare': value=prepare()
    elif a.mode=='start': value=start(a.cycle)
    elif a.mode=='resume': value=start(a.cycle,True)
    elif a.mode=='status': value=status()
    elif a.mode=='drive': value=drive()
    elif a.mode=='capture':
        value=action(OWNER['owner'],'repository_view')
        save(ROOT/f'cycle-{a.cycle}-view.json',value)
    else:
        before=json.loads((ROOT/'protected-before.json').read_text());after=snapshot()
        passed=all(before[k]==after[k] for k in ('production','v2_protected'))
        value={'status':'PASS' if passed else 'FAIL','after':after}
        save(ROOT/'preservation'/('protected-'+str(time.time_ns())+'.json'),value)
        if not passed: raise ValueError('PROTECTED_STATE_CHANGED')
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':main()
