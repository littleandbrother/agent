#!/usr/bin/env python3
"""Bounded native and paid Pi pilot; preserve seals, costs and failed attempts."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sqlite3
import sys
import time
import urllib.request

from bfworld.agentlab.runtime_config import CAD, HOME_ROOT, REPO, PI, NODE
from bfworld.agentlab.simulation_chain.contracts import digest, file_hash, write_json
from bfworld.agentlab.simulation_tasks import load_task, check_candidate, attach_evaluation

CONFIG = REPO / 'configs/reference_cases/design-pilot/protocol.json'
DEFAULT_ROOT = HOME_ROOT / 'studies/door-integration-pilot-20261002'


def sources():
    """Freeze the apparatus and evaluator; UI/report edits cannot alter a native run."""
    paths = list((REPO/'packages/python/bfworld/src/bfworld/agentlab/simulation_chain').glob('*.py'))
    paths += list((REPO/'packages/python/bfworld/src/bfworld/agentlab/simulation_chain').glob('*.c'))
    paths += [REPO/p for p in [
        'packages/python/bfworld/src/bfworld/agentlab/simulation_tasks.py',
        'packages/python/bfworld/src/bfworld/agentlab/runtime_config.py',
        'scripts/door_case/build_cad.py', 'scripts/build_pluck_product.py',
        'scripts/pluck_receiver.py',
        'packages/python/bfworld/src/bfworld/agentlab/engineering_templates/product_cad.py',
        'configs/reference_cases/door-magnetic-v1/design.json',
        'configs/reference_cases/door-magnetic-v1/DoorBeam.java',
        'configs/reference_cases/door-magnetic-v1/DoorMagnetic.java',
    ]]
    return {str(p.relative_to(REPO)): file_hash(p) for p in sorted(paths)}


def prepare(root):
    root.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(CONFIG.read_text())
    binding = load_task(protocol['task_id'])
    manifest = {'schema_version': 'design-pilot-seal-v1', 'protocol': protocol,
                'task': binding, 'sources': sources(), 'paid_dispatch_authorized': False}
    seal = root/'seal.json'
    if seal.exists():
        if json.loads(seal.read_text()) != manifest:
            raise ValueError('PILOT_SEAL_DRIFT: preserve old study; do not overwrite')
    else:
        write_json(seal, manifest)
        for entry in protocol['mapping_candidates']:
            check_candidate(binding, {'candidate': entry['candidate'], 'confirmation': True})
        for rel in manifest['sources']:
            target = root/'source-snapshot'/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPO/rel).read_bytes())
        write_json(root/'protocol.json', protocol)
        write_json(root/'task.json', binding)
    return manifest


def verify_run(path):
    result = json.loads((path/'result.json').read_text())
    for artifact in result.get('artifacts', []):
        target = path/artifact['name']
        if target.parent != path or not target.is_file() or file_hash(target) != artifact['sha256']:
            raise ValueError('PILOT_ARTIFACT_HASH_MISMATCH:' + str(target))
    return result


def child(root, name, spec, cache):
    from bfworld.agentlab.simulation_chain.pipeline import submit_candidate
    manifest = prepare(root)
    binding = manifest['task']
    check_candidate(binding, {'candidate': spec, 'confirmation': True})
    out = root/'runs'/name
    result = submit_candidate(spec, out, cache, confirm=True,
                              event=lambda k, d: print(k, d.get('stage', ''), flush=True))
    attach_evaluation(binding, out, result)
    # Verification occurs before the outer end-to-end timer stops.
    verify_run(out)
    return result


def map_candidates(root, only=None, recover=None):
    manifest = prepare(root)
    protocol = manifest['protocol']
    entries = [(e['id'], e['candidate'], root/'mapping-cache') for e in protocol['mapping_candidates']]
    entries += [(name, {}, root/'cold-cache'/name) for name in protocol['cold_controls']]
    if recover:
        if len(recover)>3 or set(recover)-{'gap28','gap36','gap40'}:
            raise ValueError('ONLY_DECLARED_RUNTIME_RECOVERY_CONTROLS')
        entries=[]
        for name in recover:
            prior=root/'runs'/name
            original=json.loads((prior/'receipt.json').read_text())
            if original['run_status']!='tool_fail':raise ValueError('RECOVERY_REQUIRES_PRESERVED_TOOL_FAILURE')
            entry=next(e for e in protocol['mapping_candidates'] if e['id']==name)
            amendment={'id':name+'-runtime-recovery1','repeats':name,'candidate':entry['candidate'],
                       'original_result_sha256':file_hash(prior/'result.json') if (prior/'result.json').exists() else None,
                       'original_receipt_sha256':file_hash(prior/'receipt.json'),
                       'reason':'Verified same-version local runtime after observed cloud placeholder failures',
                       'new_design_choice':False,'frozen_conditions_unchanged':True}
            p=root/(amendment['id']+'.json')
            if p.exists() and json.loads(p.read_text())!=amendment:raise ValueError('RECOVERY_AMENDMENT_CHANGED')
            if not p.exists():write_json(p,amendment)
            entries.append((amendment['id'],entry['candidate'],root/'mapping-cache'))
    if only:
        if set(only) - {e[0] for e in entries}:
            raise ValueError('UNKNOWN_MAPPING_CASE')
        entries = [e for e in entries if e[0] in only]
    with (root/'mapping.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name, spec, cache in entries:
            prepare(root)  # Stop on evaluator/source drift between candidates.
            out = root/'runs'/name
            if (out/'receipt.json').exists():
                receipt = json.loads((out/'receipt.json').read_text())
                if receipt.get('result_sha256'):
                    verify_run(out)
                    if file_hash(out/'result.json') != receipt['result_sha256']:
                        raise ValueError('PILOT_RESULT_CHANGED')
                print('PRESERVED', name, receipt['run_status'], flush=True)
                continue
            if (out/'start.json').exists():
                raise ValueError('PILOT_INTERRUPTED_RUN_REQUIRES_RECONCILIATION:' + name)
            previous = [json.loads(p.read_text()) for p in (root/'runs').glob('*/receipt.json')]
            remaining = protocol['native_total_wall_s'] - sum(r['end_to_end_s'] for r in previous)
            if remaining <= 0:
                raise ValueError('PILOT_NATIVE_WALL_CAP')
            if 'cold-cache' in str(cache) and cache.exists() and any(cache.iterdir()):
                raise ValueError('COLD_CONTROL_CACHE_NOT_EMPTY')
            if shutil.disk_usage(root).free < 5 * 1024**3:
                raise ValueError('PILOT_DISK_RESERVE_BELOW_5_GIB')
            out.mkdir(parents=True, exist_ok=True)
            write_json(out/'candidate.json', spec)
            started = time.time()
            write_json(out/'start.json', {'started': started, 'candidate': spec,
                       'cache': str(cache), 'seal_sha256': file_hash(root/'seal.json')})
            print('START', name, flush=True)
            args = [str(CAD), str(Path(__file__).resolve()), 'child', '--root', str(root),
                    '--name', name, '--cache', str(cache), '--spec', str(out/'candidate.json')]
            timed_out = False
            with (out/'runner.log').open('wb') as log:
                proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                    env={**os.environ, 'PYTHONPATH': str(REPO/'packages/python/bfworld/src')}, start_new_session=True)
                try:
                    code = proc.wait(timeout=min(remaining, protocol['candidate_wall_s']))
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(proc.pid, signal.SIGTERM)
                    try: code = proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL); code = proc.wait()
            result = verify_run(out) if (out/'result.json').exists() else {}
            receipt = {'id': name, 'candidate': spec, 'cache': str(cache),
                       'started': started, 'ended': time.time(), 'end_to_end_s': time.time()-started,
                       'solver_reported_s': result.get('elapsed_s'), 'exit_code': code,
                       'timed_out': timed_out, 'run_status': result.get('run_status', 'tool_fail'),
                       'error': result.get('error', 'See runner.log' if code else None),
                       'result_sha256': file_hash(out/'result.json') if result else None,
                       'logical_stages': len(result.get('stages', {})),
                       'executed_stages': sum(not s['cache_hit'] for s in result.get('stages', {}).values()),
                       'cold_control': name in protocol['cold_controls'], 'model_calls': 0}
            write_json(out/'receipt.json', receipt)
            print('END', name, receipt['run_status'], round(receipt['end_to_end_s'], 1), flush=True)
            # Keep genuine tool/numerical/domain failures as observations; no hidden retry.


def api(route, body=None):
    token = (HOME_ROOT/'state/operator.token').read_text().strip()
    request = urllib.request.Request('http://127.0.0.1:8768'+route,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+token, 'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=100) as response:
        return json.loads(response.read())


def authorize(root, explicit_authorization):
    """Operator must provide the user's explicit answer; never called by map/trials."""
    if not explicit_authorization: raise ValueError('EXPLICIT_NEW_ALLOWANCE_REQUIRED')
    manifest=prepare(root); protocol=manifest['protocol']; now=time.time()
    db=sqlite3.connect(HOME_ROOT/'state/workbench.sqlite');db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT * FROM research_model_studies WHERE protocol=?',(protocol['id'],)).fetchone()
        if existing:
            if existing['authorization']!=explicit_authorization: raise ValueError('AUTHORIZATION_IMMUTABLE')
            return dict(existing)
        unresolved=db.execute("SELECT count(*) FROM model_requests WHERE status IN ('UNKNOWN','DISPATCHED') AND id NOT IN (SELECT request_id FROM model_resolutions WHERE kind='NOT_SENT')").fetchone()[0]
        if unresolved: raise ValueError('PROVIDER_USAGE_UNRESOLVED')
        before=dict(db.execute('SELECT * FROM model_limits WHERE id=1').fetchone())
        study={'protocol':protocol['id'],'created':now,'expires':now+43200,
               'max_usd':protocol['requested_paid_allocation_usd'],'model':protocol['model'],'authorization':explicit_authorization}
        db.execute('INSERT INTO research_model_studies VALUES(:protocol,:created,:expires,:max_usd,:model,:authorization)',study)
        db.execute('UPDATE model_limits SET total_usd=?,request_usd=?,expires=? WHERE id=1',
            (before['total_usd']+study['max_usd'],min(before['request_usd'],protocol['max_usd_per_request']),max(before['expires'],study['expires'])))
        after=dict(db.execute('SELECT * FROM model_limits WHERE id=1').fetchone())
        db.commit()
        write_json(root/'paid-authorization.json',{'study':study,'limits_before':before,'limits_after':after,
                   'existing_charges_and_reservations':'unchanged','max_tokens':'unchanged'})
        return study
    finally: db.close()


def initial_run(root, trial):
    recovery=root/'runs'/(trial['initial']+'-runtime-recovery1')
    return recovery if (recovery/'receipt.json').exists() else root/'runs'/trial['initial']


def trial_prompt(root, trial):
    run=initial_run(root,trial); initial=verify_run(run)
    if not (run/'receipt.json').exists(): raise ValueError('INITIAL_RUN_NOT_COMPLETE')
    allowed={'peak_tip_mm','peak_piezo_V','peak_storage_V','peak_supply_V','cold_start_reached','tx_completed',
             'received_events','program_states_reached','q0_m','coupling_converged'}
    facts={k:initial.get(k) for k in ['run_status','failed_stage','error','checks','task_evaluation','energy_ledger']}
    facts['metrics']={k:v for k,v in initial.get('metrics',{}).items() if k in allowed}
    facts['candidate']=json.loads((run/'design-spec.json').read_text())
    facts['result_sha256']=file_hash(run/'result.json')
    facts['initial_run_id']=run.name
    if run.name!=trial['initial']:
        facts['prior_runtime_failure']=json.loads((root/'runs'/trial['initial']/'receipt.json').read_text())['error']
        facts['recovery_scope']='Same candidate after runtime repair; original failed attempt is preserved.'
    if (run/'waveform.csv').exists():
        import csv
        with (run/'waveform.csv').open() as f: data=list(csv.DictReader(f))
        facts['waveform_preview']=[{k:round(float(v),9) for k,v in data[i].items()} for i in range(0,len(data),400)]
        facts['waveform_preview_note']='Evenly subsampled public initial data; not a substitute for reading later candidate artifacts.'
    return ('固定任务：同一次门动作、零初始储能、无外部电源，在 4 秒内由压电自供能完成至少一个正确报文。'
        '这是名义模型的设计先导，不是产品验收。以下是已运行的初始候选及公开反馈。'
        '请读取约束和反馈，自主选择实际设计修改，调用原生仿真，检查结果并据反馈继续修订。最多 3 个新候选；'
        '不要改环境、阻尼、程序电流、接收模型或求解精度。解释越界/数值失败与设计未满足的区别。'
        '必须等待自己的 job 终态并读取依据，最后用 bf_engineering submit 选择一个已运行候选并如实报告，失败也可以提交。'
        '如果没有合格正例，请明确说有限搜索未找到，不能宣称所有设计不可行。简短中文持续说明。\n'
        +json.dumps(facts,ensure_ascii=False,separators=(',',':')))


def collect_trial(root, trial, cid, started, target=None, continuations=0):
    db=sqlite3.connect((HOME_ROOT/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    target=target or root/'trials'/trial['id'];target.mkdir(parents=True,exist_ok=True)
    try:
        events=[dict(r) for r in db.execute('SELECT * FROM chat_events WHERE conversation=? ORDER BY seq',(cid,))]
        jobs=[dict(r) for r in db.execute('SELECT * FROM engineering_jobs WHERE owner=? ORDER BY created',(cid,))]
        usage=[dict(r) for r in db.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY created',(cid,))]
        selected=db.execute('SELECT receipt FROM simulation_task_submissions WHERE owner=?',(cid,)).fetchone()
        status=dict(db.execute('SELECT * FROM conversations WHERE id=?',(cid,)).fetchone())
        write_json(target/'events.json',events);write_json(target/'jobs.json',jobs);write_json(target/'usage.json',usage)
        write_json(target/'selected.json',json.loads(selected['receipt']) if selected else None)
        receipt={'trial':trial,'conversation':cid,'status':status,'model_calls':len(usage),
            'cost_usd':sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in usage),
            'all_usage_settled':all(r['status']=='SETTLED' for r in usage), 'new_candidates':len(jobs),
            'participant_submitted':bool(selected),'end_to_end_s':time.time()-started,
            'operator_next_candidates':0,'prompt_continuations':max(continuations,db.execute('SELECT COUNT(*) FROM chat_messages WHERE conversation=?',(cid,)).fetchone()[0]-1),'injected_crash_tested':False}
        write_json(target/'receipt.json',receipt)
        return receipt
    finally: db.close()


def freeze_agent_runtime(root, protocol, amendment=False):
    """Capture the actual compiled agent and backend before any paid dispatch."""
    app = REPO/'packages/python/bfworld/src/bfworld/agentlab'
    paths = {str(p.relative_to(REPO)): file_hash(p) for p in sorted(app.rglob('*.py'))}
    pi_paths = [PI/'package.json', PI/'package-lock.json']
    for name in ['bf-agent', 'bf-harness', 'ai', 'agent', 'coding-agent', 'protocol']:
        package = PI/'packages'/name
        pi_paths += [package/'package.json']
        pi_paths += sorted((package/'dist').rglob('*.js'))
        if name in ('bf-agent','bf-harness'): pi_paths += sorted((package/'src').rglob('*.ts'))
    value = {'model': protocol['model'], 'task_hash': prepare(root)['task']['task_hash'],
        'backend': paths, 'pi': {str(p.relative_to(PI)): file_hash(p) for p in pi_paths},
        'node': subprocess.check_output([str(NODE), '--version'], text=True).strip(),
        'runner_sha256': file_hash(Path(__file__)), 'tools': ['bf_engineering'],
        'scope': 'Runtime identity per attempt; transport continuation separately recorded; no method superiority comparison'}
    path = root/'agent-runtime-seal.json'
    if amendment or (root/'continuation-authorization.json').exists():
        path = root/'agent-runtime-continuation-seal.json'
    if path.exists() and json.loads(path.read_text()) != value:
        old=json.loads(path.read_text())
        allowed={'packages/python/bfworld/src/bfworld/agentlab/'+n for n in ('provider.py','recovery.py','chat.py','server.py')}
        changed={k for k in old['backend'].keys()|value['backend'].keys() if old['backend'].get(k)!=value['backend'].get(k)}
        pi_changed={k for k in old['pi'].keys()|value['pi'].keys() if old['pi'].get(k)!=value['pi'].get(k)}
        pi_allowed={}
        for name in ('tool-delivery-amendment.json','tool-capacity-amendment.json'):
            tool_amendment=root/name
            if tool_amendment.exists():pi_allowed.update({e['path']:e['new_sha256'] for e in json.loads(tool_amendment.read_text())['files']})
        if not (root/'continuation-authorization.json').exists() or not changed<=allowed or any(old[k]!=value[k] for k in ('task_hash','model','tools','node')) or not pi_changed<=pi_allowed.keys() or any(value['pi'][k]!=pi_allowed[k] for k in pi_changed):
            raise ValueError('PILOT_AGENT_RUNTIME_DRIFT')
        amended=root/'runtime-amendments'/(digest(value)+'.json')
        amended.parent.mkdir(exist_ok=True)
        if not amended.exists():write_json(amended,value)
        write_json(root/'active-runtime-amendment.json',{'runtime':str(amended.relative_to(root)),'sha256':file_hash(amended),'original_seal_sha256':file_hash(path),'allowed_transport_changes':sorted(changed)})
    if not path.exists(): write_json(path, value)
    return value


def authorize_continuation(root, explicit_authorization):
    if not explicit_authorization:raise ValueError('EXPLICIT_CONTINUATION_REQUIRED')
    protocol=prepare(root)['protocol']
    path=root/'continuation-authorization.json'
    if path.exists():
        value=json.loads(path.read_text())
        if value['authorization']!=explicit_authorization:raise ValueError('CONTINUATION_IMMUTABLE')
        freeze_agent_runtime(root,protocol)
        return value
    from bfworld.agentlab.store import Store
    from bfworld.agentlab.recovery import Recovery
    store=Store(HOME_ROOT/'state');Recovery(store)
    with store.connect() as db:
        study=dict(db.execute('SELECT * FROM research_model_studies WHERE protocol=?',(protocol['id'],)).fetchone())
        if time.time()>=study['expires']:raise ValueError('STUDY_WINDOW_EXPIRED')
        value={'protocol':protocol['id'],'created':time.time(),'expires':study['expires'],
               'authorization':explicit_authorization,'max_usd':study['max_usd'],
               'original_runtime_sha256':file_hash(root/'agent-runtime-seal.json'),
               'original_failed_receipt_sha256':file_hash(root/'trials/baseline-r1/receipt.json'),
               'policy':'UNKNOWN remains UNKNOWN and fully reserved; same-study continuation only; no quota or limit reset',
               'runtime_changes':'300s transport window; scoped continuation gate; read-only research projections and method audit binding'}
        freeze_agent_runtime(root,protocol,amendment=True)
        value['runtime_sha256']=file_hash(root/'agent-runtime-continuation-seal.json')
        db.execute('INSERT INTO research_usage_continuations VALUES(?,?,?,?)',
                   (protocol['id'],value['created'],value['expires'],explicit_authorization))
        write_json(path,value)
    return value


def wait_trial(root, trial, cid, started, study):
    while True:
        with sqlite3.connect((HOME_ROOT/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            status=db.execute('SELECT status FROM conversations WHERE id=?',(cid,)).fetchone()[0]
            pending=db.execute("SELECT count(*) FROM chat_messages WHERE conversation=? AND status IN ('QUEUED','SENT')",(cid,)).fetchone()[0]
            in_flight=db.execute("SELECT count(*) FROM model_requests WHERE owner=? AND status='DISPATCHED'",(cid,)).fetchone()[0]
        launch=HOME_ROOT/'sessions'/cid/'receipt.json'
        process_live=False
        if launch.exists():
            receipt=json.loads(launch.read_text())
            if receipt.get('status')=='RUNNING' and receipt.get('pid'):
                try:os.kill(receipt['pid'],0);process_live=True
                except ProcessLookupError:pass
        terminal=status in ('FAILED','BLOCKED','PAUSED','INTERRUPTED') or status=='IDLE' and not pending
        if terminal and not in_flight and not process_live:return
        if time.time()-started>prepare(root)['protocol']['pi_max_wall_s_per_trial'] or time.time()>=study['expires']:
            api('/api/conversations/'+cid+'/stop',{});return
        time.sleep(10)


def recover_trial(root, trial_id):
    protocol=prepare(root)['protocol'];freeze_agent_runtime(root,protocol)
    authorization=json.loads((root/'continuation-authorization.json').read_text())
    trial=next(t for t in protocol['pi_trials'] if t['id']==trial_id)
    original=root/'trials'/trial_id
    previous=json.loads((original/'receipt.json').read_text())
    if previous['participant_submitted']:raise ValueError('ALREADY_SUBMITTED')
    attempt=1
    while (original/('continuation-'+str(attempt))/'receipt.json').exists():
        prior=json.loads((original/('continuation-'+str(attempt))/'receipt.json').read_text())
        if prior['participant_submitted']:return prior
        attempt+=1
    if attempt>6:raise ValueError('TRANSPORT_CONTINUATION_ATTEMPTS_EXHAUSTED')
    target=original/('continuation-'+str(attempt));target.mkdir(exist_ok=True)
    if (target/'receipt.json').exists():return json.loads((target/'receipt.json').read_text())
    cid=previous['conversation']
    prompt=('继续完成这条固定任务。上次因模型传输中断而停止，原始记录已保留。'
            '先核对当前已有任务与结果，不要重复派发已有候选，不增加候选额度，不改变约束。'
            '继续原任务的自主设计、仿真、比较与提交。已有结果先复用，未用候选额度仍按原任务执行；用 bf_engineering submit 提交已运行候选并如实报告。'
            '不要以准备执行或重试派发的文字结束；请实际调用工具，或说明工具返回的明确阻塞。求解器忙时工具会等待，不需要重复模型请求。'
            '这是一次传输恢复续跑，不代表上次已成功。')
    if not (target/'start.json').exists():
        write_json(target/'start.json',{'started':time.time(),'conversation':cid,'original_receipt_sha256':file_hash(original/'receipt.json'),'loaded_service':json.loads((HOME_ROOT/'state/active-runtime.json').read_text())})
        write_json(target/'input.json',{'text':prompt,'operator_next_candidates':0})
    started=json.loads((target/'start.json').read_text())['started']
    api('/api/conversations/'+cid+'/messages',{'text':prompt,'operation_id':protocol['id']+'-'+trial_id+'-transport-continuation-'+str(attempt)})
    print('PI_RECOVER',trial_id,cid,flush=True)
    wait_trial(root,trial,cid,started,authorization)
    result=collect_trial(root,trial,cid,started,target,attempt)
    print('PI_RECOVERY_END',trial_id,result['status']['status'],result['participant_submitted'],result['cost_usd'],flush=True)
    return result


def trials(root):
    protocol=prepare(root)['protocol']
    db=sqlite3.connect((HOME_ROOT/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    study=db.execute('SELECT * FROM research_model_studies WHERE protocol=?',(protocol['id'],)).fetchone();db.close()
    if not study or time.time()>=study['expires']: raise ValueError('PILOT_STUDY_NOT_AUTHORIZED_OR_EXPIRED')
    native_lock=(root/'mapping.lock').open('a')
    fcntl.flock(native_lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
    for trial in protocol['pi_trials']:
        freeze_agent_runtime(root, protocol)
        target=root/'trials'/trial['id'];target.mkdir(parents=True,exist_ok=True)
        if (target/'receipt.json').exists():
            print('PRESERVED_TRIAL',trial['id'],flush=True);continue
        prompt=trial_prompt(root,trial)
        if len(prompt)>12000: raise ValueError('PILOT_PROMPT_TOO_LARGE')
        if (target/'start.json').exists():
            start=json.loads((target/'start.json').read_text()); cid=start['conversation'];started=start['started']
        else:
            write_json(target/'input.json',{'text':prompt,'initial':trial['initial'],'actual_initial_run':initial_run(root,trial).name,'initial_result_sha256':file_hash(initial_run(root,trial)/'result.json')})
            started=time.time()
            conversation=api('/api/engineering',{'action':'pilot_trial','trial_id':trial['id'],'text':prompt})
            cid=conversation['id'];write_json(target/'start.json',{'started':started,'conversation':cid,'loaded_service':json.loads((HOME_ROOT/'state/active-runtime.json').read_text())})
        print('PI_TRIAL',trial['id'],cid,flush=True)
        wait_trial(root,trial,cid,started,study)
        receipt=collect_trial(root,trial,cid,started)
        print('PI_END',json.dumps(receipt,ensure_ascii=False),flush=True)
        if not receipt['all_usage_settled'] and not (root/'continuation-authorization.json').exists(): raise ValueError('PILOT_USAGE_UNRESOLVED_STOP')
        with sqlite3.connect((HOME_ROOT/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            if db.execute("SELECT 1 FROM engineering_jobs WHERE owner=? AND status IN ('RUNNING','QUEUED','UNKNOWN')",(cid,)).fetchone():
                raise ValueError('PILOT_NATIVE_JOB_REQUIRES_RECONCILIATION')
    native_lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'map', 'child', 'authorize', 'trials','authorize-continuation','recover-trial'])
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--only', nargs='+')
    parser.add_argument('--recover', nargs='+', help='At most three preserved runtime failures; new run IDs, same design and total wall cap')
    parser.add_argument('--name'); parser.add_argument('--spec', type=Path); parser.add_argument('--cache', type=Path)
    parser.add_argument('--authorization', help='Exact explicit user approval of the additional USD2 / 12h scope')
    args = parser.parse_args()
    if args.action == 'prepare':
        value = prepare(args.root); print(json.dumps({'seal': digest(value), 'root': str(args.root)}))
    elif args.action == 'map': map_candidates(args.root, args.only, args.recover)
    elif args.action == 'authorize': print(json.dumps(authorize(args.root,args.authorization),ensure_ascii=False))
    elif args.action == 'authorize-continuation':print(json.dumps(authorize_continuation(args.root,args.authorization),ensure_ascii=False))
    elif args.action == 'recover-trial':recover_trial(args.root,args.name)
    elif args.action == 'trials': trials(args.root)
    else: child(args.root, args.name, json.loads(args.spec.read_text()), args.cache)


if __name__ == '__main__': main()
