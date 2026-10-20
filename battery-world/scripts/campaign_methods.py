#!/usr/bin/env python3
"""Finite S0 pilot in a fresh runtime; never imports or resumes an old owner."""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request

from bfworld.agentlab.campaign20261019.common import digest, file_hash, seal, usage_summary
from bfworld.agentlab.campaign20261019.reexecution import qualify

APP = Path(__file__).resolve().parents[1]
SOURCE = APP.parent
ROOT = SOURCE.parents[1]
CAMPAIGN = ROOT/'docs/research/parallel-campaign-20261019'
RUNTIME = Path.home()/'.local/share/bf-campaign-20261019-s0'
ORIGINAL = Path.home()/'.local/share/bf-agent-architecture-v2'
OUT = APP/'docs/research/parallel-20261019/methods'
CONFIG = APP/'configs/studies/parallel-20261019/methods'
PORT = 8980


def load(path):
    return json.loads(Path(path).read_text())


def profile():
    return load(RUNTIME/'profile.json')


def request(method, path, body=None):
    p = profile()
    token = (Path(p['home'])/'state/operator.token').read_text().strip()
    req = urllib.request.Request(f'http://127.0.0.1:{p["port"]}'+path, method=method,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+token, 'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError(json.loads(error.read()).get('error', str(error))) from None


def action(owner, name, **params):
    return request('POST', '/api/design-lab', {'session_id':owner, 'action':name, **params})


def db():
    con = sqlite3.connect((RUNTIME/'workbench/state/workbench.sqlite').as_uri()+'?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def protected_snapshot():
    old = load(ORIGINAL/'profile.json')
    result = {}
    # Include every original owner and all original ledger rows, including UNKNOWN.
    for label, database in [('v2', ORIGINAL/'workbench/state/workbench.sqlite'),
                            ('production', Path.home()/'.local/share/bf-agent-runtime/workbench/state/workbench.sqlite')]:
        if not database.exists():
            raise ValueError('PROTECTED_DATABASE_MISSING:'+label)
        con = sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows = {}
        for table in ('conversations', 'model_requests', 'design_projects'):
            if table in tables:
                data = [dict(r) for r in con.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                rows[table] = {'rows':len(data), 'sha256':digest(data)}
        con.close()
        result[label] = rows
    result['baseline_manifest_sha256'] = file_hash(Path(old['baseline']['path'])/'manifest.json')
    return result


def clone_tree(source, target):
    if target.exists():
        raise ValueError('CACHE_TARGET_ALREADY_EXISTS')
    subprocess.run(['/bin/cp', '-cR', str(source), str(target)], check=True)


def cache_manifest(path):
    values = []
    for folder in sorted(Path(path).iterdir()):
        if not folder.is_dir() or not (folder/'completed.json').is_file():
            continue
        value = load(folder/'completed.json')
        if value['status'] != 'SUCCEEDED':
            continue
        for name, expected in value['outputs'].items():
            if file_hash(folder/name) != expected:
                raise ValueError('CACHE_OUTPUT_CHANGED:'+str(folder/name))
        values.append({'key':value['key'], 'completed_sha256':file_hash(folder/'completed.json'),
                       'outputs':value['outputs']})
    return values


def prepare():
    if (RUNTIME/'prepared.json').exists():
        return load(RUNTIME/'prepared.json')
    if shutil.disk_usage(SOURCE).free < 5_000_000_000:
        raise ValueError('DISK_HEADROOM')
    RUNTIME.mkdir(parents=True, exist_ok=True)
    seal(RUNTIME/'protected-before.json', protected_snapshot())
    old = load(ORIGINAL/'profile.json')
    p = copy.deepcopy(old)
    home = RUNTIME/'workbench'
    p.update(id='campaign-s0-20261019', stage='finite public development',
        source_root=str(SOURCE), branch='codex/campaign-s0-20261019',
        base_commit='317d40fef0137d3c1ad1873e53c3e9968b31200a',
        runtime_root=str(RUNTIME), home=str(home), configuration=str(RUNTIME/'runtime.json'),
        pi_root=str(SOURCE/'pi-bf-aiot'), port=PORT,
        baseline={'path':str(CAMPAIGN/'baseline-v1'),
                  'manifest_sha256':file_hash(CAMPAIGN/'baseline-v1/manifest.json')})
    p['protected_roots'] += [old['source_root'], str(ORIGINAL)]
    p['paths'].update(HOME=str(home), PI_ROOT=p['pi_root'],
        PROVIDER_KEY_FILE=str(home/'secrets/deepseek.key'),
        EDA_LOCAL_PROJECT_ROOT=str(RUNTIME/'native-projects'))
    key = Path(p['paths']['PROVIDER_KEY_FILE'])
    key.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(old['paths']['PROVIDER_KEY_FILE'], key)
    key.chmod(0o600)
    seal(RUNTIME/'profile.json', p)
    ref = {'path':str(RUNTIME/'profile.json'), 'sha256':file_hash(RUNTIME/'profile.json')}
    seal(RUNTIME/'runtime.json', {'schema_version':'bf-runtime-layout-v1', 'paths':p['paths'],
                                'eda':p['eda'], 'development_profile':ref})
    seal(SOURCE/'.bf-development-profile.json', ref)
    modules = SOURCE/'pi-bf-aiot/node_modules'
    if not modules.exists():
        modules.symlink_to(Path(old['pi_root'])/'node_modules', target_is_directory=True)
    if not (modules/'.bin/tsgo').is_file():
        raise ValueError('PI_DEPENDENCIES_MISSING')
    # Source-bound certificate and its evidence are copied, never modified in place.
    pin = load(ORIGINAL/'workbench/design-lab/repository/feedback-qualification/current.json')
    src = Path(pin['path']).parent
    cert = load(src/'qualification.json')
    target = RUNTIME/'qualification'/src.name
    target.mkdir(parents=True, exist_ok=True)
    for name in ['qualification.json', *cert['evidence']]:
        shutil.copyfile(src/name, target/name)
    for name, expected in cert['evidence'].items():
        if file_hash(target/name) != expected:
            raise ValueError('REFERENCE_EVIDENCE_CHANGED')
    if file_hash(target/'qualification.json') != pin['sha256']:
        raise ValueError('REFERENCE_CERTIFICATE_CHANGED')
    repo = home/'design-lab/repository'
    seal(repo/'feedback-qualification/current.json', {'path':str(target/'qualification.json'),
                                                   'sha256':pin['sha256']})
    warm = ORIGINAL/'power-feedback/qualification/execution-cache/design-lab/repository/feedback-native-cache'
    manifest = cache_manifest(warm)
    clone_tree(warm, RUNTIME/'cache-start')
    seal(RUNTIME/'cache-start.json', {'entries':manifest, 'sha256':digest(manifest),
        'new_native_solves':0, 'construction':'verified APFS clones of successful qualified cache',
        'prior_build_cost':'historical qualification construction; not claimed free scientific computation'})
    task = load(APP/'configs/studies/continuous-design-20261018/T1-fixed-power-scheduling.json')
    task['id'] = 'P2-public-fixed-power-v1'
    task['split'] = 'public-development'
    task['definition']['phase'] = 'campaign-20261019-public-fixed-power'
    task['request'] = '固定电源板，在20秒内完成六帧有效数据；仅修订程序，并交付与执行同版的结果。'
    task['definition']['goal'] = task['request']
    seal(CONFIG/'task.json', task)
    base = ('本次为新项目的一次完整设计尝试，从任务入口开始。读取当前任务定义和源码，'
        '在允许设计空间内完成至少一项有意义的firmware/main.c修订。'
        '实际task_execute、validate、decide，最后task_report、release、close。'
        '固定任务、物理装置、检查器和数值协议；保留失败及工具错误；'
        '相同且有效的输入复用，不重复求解。共享上限80次模型请求、4次不同候选执行；'
        '完成后停止，不追加备选，不生成子任务。')
    h1 = ('先建立公开要求、约束与可变文件清单，核对时间基准和采样/发送窗口，'
        '在修改前检查可行性。只选择一项有依据的程序修订，说明它影响的反馈依赖，'
        '执行并比较修改前后；有失败时保留诊断，只在剩余配额内修正。'
        '每个判断引用工具返回的字段与输入版本，达到目标即停止探索并完成交付。')
    protocol = {'schema_version':'campaign-method-pilot-v1', 'task':digest(task),
        'partition':'public-development', 'information':'same complete public task and sources; no extra H1 facts',
        'backend':'DeepSeek official API / deepseek-flash / engineering-reasoning-efficient-v5',
        'cache_start':digest(manifest), 'organization':'single', 'replicates':2,
        'order':['H0-r1','H1-r1','H1-r2','H0-r2'],
        'limits':{'requests_per_trial':80,'candidate_evaluations_per_trial':4,
                  'decision_wall_s':1200},
        'prompts':{'H0':base,'H1':base+h1},
        'H1_origin':'Early development experience: 8ms validity task infeasible under public minimum windows; '
                    'prior fixed scheduling pilot and wasted reads. This is an operator-proposed H change, not autonomous G.',
        'selection':'retain only as development candidate if both paired full confirmations deliver admissible results '
                    'with no worse failure rate; cost/gain descriptive, no significance or transfer claim',
        'formal_holdout':'none; historical T1 is exposed and explicitly demoted to public development',
        'frozen_before_model_dispatch':True, 'automatic_resampling':False}
    seal(CONFIG/'protocol.json', protocol)
    seal(OUT/'f1a-controls.json', qualify())
    result = {'runtime':str(RUNTIME), 'port':PORT, 'profile_sha256':ref['sha256'],
              'protocol_sha256':file_hash(CONFIG/'protocol.json'),
              'qualification_id':cert['id'], 'cache_entries':len(manifest), 'model_requests':0}
    seal(RUNTIME/'prepared.json', result)
    return result


def launch():
    from bf_v2_environment import launch as start_service
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1', PORT)) == 0:
            return request('GET', '/api/health')
    result = start_service(RUNTIME, background=True)
    seal(RUNTIME/'service-start.json', result)
    for _ in range(100):
        try:
            return request('GET', '/api/health')
        except (OSError, ValueError):
            time.sleep(.2)
    raise ValueError('ISOLATED_SERVICE_START_FAILED')


def preflight():
    p = profile()
    key = Path(p['paths']['PROVIDER_KEY_FILE']).read_text().strip()
    result = {'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    for label, url in [('balance','https://api.deepseek.com/user/balance'),
                       ('models','https://api.deepseek.com/models')]:
        req = urllib.request.Request(url, headers={'Authorization':'Bearer '+key})
        with urllib.request.urlopen(req, timeout=30) as response:
            result[label] = json.load(response)
    if not result['balance']['is_available'] or 'deepseek-flash' not in [m['id'] for m in result['models']['data']]:
        raise ValueError('PROVIDER_NOT_READY')
    seal(RUNTIME/'provider-preflight.json', result)
    return {'available':True, 'model_present':True}


def register():
    path = RUNTIME/'registry.json'
    if path.exists():
        return load(path)
    task = load(CONFIG/'task.json')
    protocol = load(CONFIG/'protocol.json')
    entries = []
    for name in protocol['order']:
        arm = name.split('-')[0]
        owner = request('POST','/api/conversations', {'text':'P2 campaign '+name,
            'operation_id':'campaign-20261019-'+name, 'task_id':None,
            'folder_id':None, 'defer_dispatch':True})['id']
        made = action(owner, 'repository_task_create', operation_id='campaign-create',
                      definition=task['definition'], title=task['id'], files=task['files'])
        policy = action(owner, 'repository_work_configure', operation_id='campaign-policy',
            policy={'organization':'single', 'kind':'design',
                    'limits':{k:v for k,v in protocol['limits'].items() if k!='decision_wall_s'},
                    'protocol_sha256':file_hash(CONFIG/'protocol.json')})
        auth = action(owner, 'authorize', wall_authorization_text='持续运行 不设置时间限制',
                      model_profile='engineering-reasoning-efficient-v5')
        auth.pop('participant_token', None)
        entry = {'key':name, 'arm':arm, 'owner':owner, 'project_id':made['project_id'],
                 'initial_system':made['id'], 'task_definition_id':made['task_definition']['id'],
                 'input_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in task['files'].items()},
                 'goal':protocol['prompts'][arm], 'goal_sha256':digest(protocol['prompts'][arm]),
                 'policy':policy, 'authority':auth}
        seal(RUNTIME/'trials'/name/'registration.json', entry)
        entries.append(entry)
    if len({e['task_definition_id'] for e in entries}) != 1:
        raise ValueError('UNMATCHED_TASKS')
    return seal(path, {'protocol_sha256':file_hash(CONFIG/'protocol.json'), 'trials':entries})


def start(key):
    entry = next(x for x in load(RUNTIME/'registry.json')['trials'] if x['key']==key)
    trial = RUNTIME/'trials'/key
    if (trial/'dispatch.json').exists():
        raise ValueError('TRIAL_ALREADY_DISPATCHED_NO_AUTOMATIC_RESAMPLING')
    with db() as con:
        if con.execute("SELECT 1 FROM conversations WHERE status IN ('RUNNING','STARTING','QUEUED')").fetchone():
            raise ValueError('ISOLATED_RUNTIME_BUSY')
        if con.execute("SELECT 1 FROM model_requests WHERE status='UNKNOWN' OR (status='SETTLED' AND usage IS NULL)").fetchone():
            raise ValueError('PROVIDER_USAGE_UNAVAILABLE_STOP')
    if shutil.disk_usage(SOURCE).free < 5_000_000_000:
        raise ValueError('DISK_HEADROOM')
    cache = RUNTIME/'workbench/design-lab/repository/feedback-native-cache'
    if cache.exists():
        raise ValueError('PREVIOUS_CACHE_NOT_CAPTURED')
    clone_tree(RUNTIME/'cache-start', cache)
    actual = digest(cache_manifest(cache))
    if actual != load(RUNTIME/'cache-start.json')['sha256']:
        raise ValueError('CACHE_START_MISMATCH')
    result = action(entry['owner'], 'repository_start', goal=entry['goal'])
    return seal(trial/'dispatch.json', {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'started_epoch':time.time(), 'cache_start_sha256':actual, 'entry':key,
        'goal_sha256':entry['goal_sha256'], **result})


def collect(key):
    e = next(x for x in load(RUNTIME/'registry.json')['trials'] if x['key']==key)
    state = action(e['owner'], 'repository_state')
    if state['status'] in ('RUNNING','STARTING','STOPPING'):
        return {'key':key, 'status':state['status']}
    view = action(e['owner'], 'repository_view')
    with db() as con:
        rows = [dict(r) for r in con.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY rowid',(e['owner'],))]
        executions = [json.loads(r[0]) for r in con.execute('SELECT value FROM design_task_executions WHERE project=? ORDER BY rowid',(e['project_id'],))]
        events = [json.loads(r[0]) for r in con.execute("SELECT data FROM events WHERE owner=? AND kind='model_settled' ORDER BY seq", (e['owner'],))]
        identities = [json.loads(r[0])['model_id'] for r in con.execute("SELECT data FROM events WHERE owner=? AND kind='model_dispatched' ORDER BY seq", (e['owner'],))]
    for row in rows:
        if row.get('usage'):
            row['usage'] = json.loads(row['usage'])
    current = view['project']['submitted']
    system = next(s for s in view['systems'] if s['id']==current)
    trial = RUNTIME/'trials'/key
    stop = load(trial/'stop.json') if (trial/'stop.json').exists() else None
    ended = stop['epoch'] if stop else time.time()
    result = {'key':key, 'owner':e['owner'], 'status':state['status'], 'error':state.get('error'),
        **usage_summary(rows), 'tokens':sum(r['usage'].get('total_tokens',0) for r in rows if r.get('usage')),
        'actual_models':sorted(set(identities)),
        'cache_aware_estimate_usd':sum(v['cost_breakdown']['cache_aware_estimate_usd'] for v in events)
            if len(events)==len(rows) and all(v.get('cost_breakdown',{}).get('cache_aware_estimate_usd') is not None for v in events) else None,
        'candidate_evaluations':len(executions), 'current_system':current,
        'changed_design':any(c['path']=='firmware/main.c' for s in view['systems'] for c in s['design_changes']),
        'qualification':system['current_qualification'],
        'delivered':any(r['target']==current for r in view['releases']),
        'decision_wall_s':ended-load(trial/'dispatch.json')['started_epoch'],
        'fresh_owner':True, 'fresh_initial_input':e['input_hashes'], 'goal_sha256':e['goal_sha256']}
    if stop:
        result.update(stop_reason=stop['reason'], resource_censored=True,
                      completion='STOPPED_WITHOUT_RESAMPLING', decision_end_epoch=ended)
    seal(trial/'state.json', state)
    seal(trial/'view.json', view)
    seal(trial/'ledger.json', rows)
    seal(trial/'settled-usage-events.json', events)
    seal(trial/'executions.json', executions)
    seal(trial/'final.json', result)
    cache = RUNTIME/'workbench/design-lab/repository/feedback-native-cache'
    if cache.exists():
        cache.rename(trial/'cache-after')
    seal(OUT/'paid'/key/'result.json', result)
    return result


def status():
    results = []
    for e in load(RUNTIME/'registry.json')['trials']:
        path = RUNTIME/'trials'/e['key']/'final.json'
        if path.exists():
            results.append(load(path))
        else:
            s = action(e['owner'], 'repository_state')
            results.append({'key':e['key'], 'status':s['status'], 'error':s.get('error')})
    return results


def preservation():
    before = load(RUNTIME/'protected-before.json')
    after = protected_snapshot()
    result = {'status':'PASS' if before==after else 'FAIL', 'before':before, 'after':after}
    seal(OUT/'protected-state-final.json', result)
    return {'status':result['status']}


def halt(entry, reason):
    """Stop only this fresh pilot process; retain uncertain native/provider work."""
    seal(RUNTIME/'trials'/entry['key']/'stop.json', {'reason':reason, 'epoch':time.time()})
    request('POST', '/api/conversations/'+entry['owner']+'/stop', {})
    time.sleep(2)
    attempts = sorted((RUNTIME/'workbench/sessions'/entry['owner']/'repository-attempts').glob('*/dispatch.json'))
    if attempts:
        record = load(attempts[-1])
        pid = record.get('pid')
        if pid:
            cmd = subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True).stdout
            if 'repository-task.js' in cmd and str(RUNTIME) in cmd:
                os.killpg(pid, signal.SIGTERM)
    raise ValueError(reason+'; no further trial dispatched; outstanding native/provider work retained')


def drive():
    """Run the frozen list serially, with periodic compact output and hard stops."""
    registry = load(RUNTIME/'registry.json')
    for e in registry['trials']:
        trial = RUNTIME/'trials'/e['key']
        if (trial/'final.json').exists():
            continue
        if not (trial/'dispatch.json').exists():
            print(json.dumps(start(e['key'])), flush=True)
        began = load(trial/'dispatch.json')['started_epoch']
        last = 0
        while True:
            state = action(e['owner'], 'repository_state')
            elapsed = time.time()-began
            if state.get('unknown_requests'):
                halt(e, 'PROVIDER_USAGE_UNKNOWN_STOP')
            if elapsed > 1200:
                halt(e, 'FINITE_DECISION_WALL_EXHAUSTED')
            if shutil.disk_usage(SOURCE).free < 5_000_000_000:
                halt(e, 'DISK_HEADROOM_STOP')
            if state['status'] not in ('RUNNING','STARTING','STOPPING'):
                result = collect(e['key'])
                print(json.dumps(result, ensure_ascii=False), flush=True)
                if result['unknown_or_missing_usage']:
                    raise ValueError('PROVIDER_USAGE_UNAVAILABLE_STOP')
                if result['actual_models'] and result['actual_models']!=['deepseek-flash']:
                    raise ValueError('ACTUAL_MODEL_IDENTITY_STOP')
                break
            if elapsed-last >= 30:
                with db() as con:
                    calls = con.execute('SELECT count(*) FROM model_requests WHERE owner=?',(e['owner'],)).fetchone()[0]
                print(json.dumps({'key':e['key'],'status':state['status'],'elapsed_s':round(elapsed),'requests':calls}),flush=True)
                last = elapsed
            time.sleep(5)
    return {'status':'FINITE_LIST_FINISHED', 'preservation':preservation()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['qualify','prepare','launch','preflight','register','start','status','collect','preservation','drive'])
    p.add_argument('--trial')
    p.add_argument('--free-session-slot', action='store_true',
                   help='S0 verified <=2 other active model sessions before dispatch')
    a = p.parse_args()
    if a.mode=='qualify':
        value=qualify();seal(OUT/'f1a-controls.json',value)
    elif a.mode in ('start','drive'):
        if not a.free_session_slot:
            raise ValueError('MODEL_SESSION_SLOT_REQUIRES_SUPERVISOR_CHECK')
        value=start(a.trial) if a.mode=='start' else drive()
    elif a.mode=='collect':
        value=collect(a.trial)
    else:
        value=globals()[a.mode]()
    print(json.dumps(value, ensure_ascii=False))


if __name__=='__main__':
    main()
