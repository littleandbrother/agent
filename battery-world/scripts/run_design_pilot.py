#!/usr/bin/env python3
"""Bounded native pilot. No model calls, ledger resets, or silent failed-run replacement."""
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
DEFAULT_ROOT = HOME_ROOT / 'studies/door-design-pilot-v1'


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
    with urllib.request.urlopen(request, timeout=100) as response:
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


def collect_trial(root, trial, cid, started):
    db=sqlite3.connect((HOME_ROOT/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    target=root/'trials'/trial['id'];target.mkdir(parents=True,exist_ok=True)
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
            'operator_next_candidates':0,'prompt_continuations':0,'injected_crash_tested':False}
        write_json(target/'receipt.json',receipt)
        return receipt
    finally: db.close()


def freeze_agent_runtime(root, protocol):
    """Capture the actual compiled agent and backend before any paid dispatch."""
    app = REPO/'packages/python/bfworld/src/bfworld/agentlab'
    paths = {str(p.relative_to(REPO)): file_hash(p) for p in sorted(app.rglob('*.py'))}
    pi_paths = [PI/'package.json', PI/'package-lock.json']
    for name in ['bf-agent', 'ai', 'agent', 'coding-agent', 'protocol']:
        package = PI/'packages'/name
        pi_paths += [package/'package.json']
        pi_paths += sorted((package/'dist').rglob('*.js'))
        if name == 'bf-agent': pi_paths += sorted((package/'src').rglob('*.ts'))
    value = {'model': protocol['model'], 'task_hash': prepare(root)['task']['task_hash'],
        'backend': paths, 'pi': {str(p.relative_to(PI)): file_hash(p) for p in pi_paths},
        'node': subprocess.check_output([str(NODE), '--version'], text=True).strip(),
        'runner_sha256': file_hash(Path(__file__)), 'tools': ['bf_engineering'],
        'scope': 'same compiled runtime across all four pilot trajectories; no method superiority comparison'}
    path = root/'agent-runtime-seal.json'
    if path.exists() and json.loads(path.read_text()) != value:
        raise ValueError('PILOT_AGENT_RUNTIME_DRIFT')
    if not path.exists(): write_json(path, value)
    return value


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
            cid=conversation['id'];write_json(target/'start.json',{'started':started,'conversation':cid})
        print('PI_TRIAL',trial['id'],cid,flush=True)
        while True:
            with sqlite3.connect((HOME_ROOT/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True) as db:
                status=db.execute('SELECT status FROM conversations WHERE id=?',(cid,)).fetchone()[0]
                pending=db.execute("SELECT count(*) FROM chat_messages WHERE conversation=? AND status IN ('QUEUED','SENT')",(cid,)).fetchone()[0]
            if status in ('FAILED','BLOCKED','PAUSED','INTERRUPTED') or status=='IDLE' and not pending: break
            if time.time()-started>protocol['pi_max_wall_s_per_trial'] or time.time()>=study['expires']:
                api('/api/conversations/'+cid+'/stop',{});break
            time.sleep(10)
        receipt=collect_trial(root,trial,cid,started)
        print('PI_END',json.dumps(receipt,ensure_ascii=False),flush=True)
        if not receipt['all_usage_settled']: raise ValueError('PILOT_USAGE_UNRESOLVED_STOP')
        with sqlite3.connect((HOME_ROOT/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            if db.execute("SELECT 1 FROM engineering_jobs WHERE owner=? AND status IN ('RUNNING','QUEUED','UNKNOWN')",(cid,)).fetchone():
                raise ValueError('PILOT_NATIVE_JOB_REQUIRES_RECONCILIATION')
    native_lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'map', 'child', 'authorize', 'trials'])
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
    elif args.action == 'trials': trials(args.root)
    else: child(args.root, args.name, json.loads(args.spec.read_text()), args.cache)


if __name__ == '__main__': main()
