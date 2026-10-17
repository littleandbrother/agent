#!/usr/bin/env python3
"""A/B gate against the isolated live consumer path and immutable baseline."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

from bf_v2_environment import APP, SOURCE, environment, launch
from bfworld.agentlab.baseline import digest, logical_state, readonly, verify


def wait(url):
    deadline = time.monotonic()+20
    while True:
        try:
            return urllib.request.urlopen(url, timeout=2).read()
        except (OSError, urllib.error.URLError):
            if time.monotonic() > deadline:
                raise
            time.sleep(.1)


def check(runtime, output):
    runtime, output = Path(runtime).resolve(), Path(output).absolute()
    if output.exists():
        raise ValueError('VERIFICATION_OUTPUT_ALREADY_EXISTS')
    output.mkdir(parents=True)
    p, env = environment(runtime)
    python = p['paths']['CAD_PYTHON']
    original = json.loads((Path(p['baseline']['path'])/'manifest.json').read_text())
    demo_root = Path(original['production']['runtime'])/'workbench/state'
    demo_receipt = json.loads((demo_root/'active-runtime.json').read_text())
    demo_paths = ['/', '/app.js', '/style.css', '/engineering.js', '/product.css', '/tokens.css']
    demo_before = {name: hashlib.sha256(urllib.request.urlopen('http://127.0.0.1:8768'+name, timeout=5).read()).hexdigest() for name in demo_paths}
    baseline_before = verify(p['baseline']['path'], origins=True)
    tests = subprocess.run([python, '-m', 'unittest', 'discover', '-s', 'tests/agentlab', '-p', 'test_environment_profile.py', '-v'],
                           cwd=APP, env=env, capture_output=True, text=True, timeout=60)
    (output/'unit-tests.txt').write_text(tests.stdout+tests.stderr)
    if tests.returncode:
        raise ValueError('DEVELOPMENT_UNIT_GATE_FAILED')
    # Restart only the identified development process to load exactly this source.
    active = Path(p['home'])/'state/active-runtime.json'
    if active.is_file():
        old = json.loads(active.read_text())
        command = subprocess.run(['ps', '-p', str(old['pid']), '-o', 'command='], capture_output=True, text=True).stdout
        if command:
            if (str(Path(p['home'])/'state') not in command or old['port'] != p['port'] or
                    not old['provider_file'].startswith(str(SOURCE)+os.sep) or old['pid'] == demo_receipt['pid']):
                raise ValueError('DEVELOPMENT_STOP_IDENTITY_MISMATCH')
            os.kill(old['pid'], signal.SIGTERM)
            deadline = time.monotonic()+10
            while subprocess.run(['ps', '-p', str(old['pid']), '-o', 'stat='], capture_output=True, text=True).stdout.strip().strip('Z'):
                if time.monotonic() > deadline:
                    raise ValueError('DEVELOPMENT_STOP_TIMEOUT')
                time.sleep(.1)
    started = launch(runtime, background=True)
    dev_url = 'http://127.0.0.1:'+str(p['port'])
    wait(dev_url+'/')
    token = (Path(p['home'])/'state/operator.token').read_text().strip()

    def request(method, url, body=None):
        raw = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(dev_url+url, data=raw, method=method,
              headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    live = []
    def assertion(name, condition, facts=None):
        live.append({'name': name, 'passed': bool(condition), 'facts': facts or {}})
        if not condition:
            (output/'failed-check.json').write_text(json.dumps(live, ensure_ascii=False, indent=2)+'\n')
            raise ValueError('DEVELOPMENT_LIVE_CHECK_FAILED:'+name)

    status, health = request('GET', '/api/health')
    assertion('isolated service starts with execution disabled', status == 200 and 'DEVELOPMENT_EXECUTION_NOT_ENABLED' in health['reasons'])
    status, roster = request('GET', '/api/conversations')
    assertion('original ten owners are absent from development routing', status == 200 and not any(s['id'] in p['protected_owners'] for s in roster['sessions']))
    registry = runtime/'ab-check-session.json'
    if registry.is_file():
        old_test = json.loads(registry.read_text())
        folders = {'id': old_test['folder_id']}
    else:
        _, folders = request('POST', '/api/folders', {'name': 'Architecture V2 · environment checks'})
    body = {'text': 'V2 环境验证 · P01 基线输入', 'operation_id': 'v2-ab-environment-check',
            'task_id': None, 'folder_id': folders['id'], 'defer_dispatch': True}
    status, session = request('POST', '/api/conversations', body)
    assertion('independent Pi test identity created without dispatch', status == 201 and session['id'] not in p['protected_owners'] and session['status'] == 'IDLE', session)
    owner = session['id']
    if not registry.exists():
        registry.write_text(json.dumps({'owner': owner, 'folder_id': folders['id'], 'operation_id': body['operation_id']}, indent=2)+'\n')
    status, repeated = request('POST', '/api/conversations', body)
    assertion('same operation reuses the same test identity', status == 201 and repeated['id'] == owner)
    for name, url, data, capability in [
            ('inference stopped before billing', '/v1/chat/completions', {'model':'deepseek-flash','messages':[{'role':'user','content':'environment check'}]}, 'model'),
            ('native solver stopped before dispatch', '/api/engineering', {'session_id':owner,'action':'run','engine':'product-model','operation_id':'ab-native-negative','parameters':{}}, 'native'),
            ('EDA command stopped before host access', '/api/eda-cli', {'session_id':owner,'action':'command','argv':['project','info'],'operation_id':'ab-eda-negative'}, 'native'),
            ('original native UUID cannot be bound', '/api/eda-cli', {'session_id':owner,'action':'bind','project_uuid':original['p01']['native_project_uuid'],'writable':True}, 'native')]:
        status, failure = request('POST', url, data)
        assertion(name, status == 403 and failure.get('error') == 'DEVELOPMENT_CAPABILITY_DISABLED:'+capability, failure)
    sdk = subprocess.run([p['paths']['NODE'], str(APP/'scripts/verify_v2_sdk.mjs'), str(runtime), owner],
                         cwd=SOURCE/'pi-bf-aiot', env=env, capture_output=True, text=True, timeout=30)
    (output/'pi-sdk.txt').write_text(sdk.stdout+sdk.stderr)
    if sdk.returncode:
        raise ValueError('DEVELOPMENT_PI_SDK_GATE_FAILED')
    sdk_result = json.loads(sdk.stdout)
    assertion('actual Pi SDK creates and restores isolated session', sdk_result['status'] == 'PASS', sdk_result)
    # Both processes use the production host's existing lock, despite different BF_HOME.
    os.environ.update({k:v for k,v in env.items() if k.startswith('BF_') or k == 'PI_CODING_AGENT_DIR'})
    from bfworld.agentlab.design_lab.native_slot import native_slot
    old_env = {k:v for k,v in env.items() if not k.startswith('BF_')}
    old_env['PYTHONPATH'] = str(Path(original['source']['worktree'])/'battery-world/packages/python/bfworld/src')
    probe = ('from bfworld.agentlab.design_lab.native_slot import native_slot\n'
             'try:\n with native_slot(blocking=False) as lease: print("ACQUIRED:"+lease["path"])\n'
             'except BlockingIOError: print("BUSY")\n')
    with native_slot(blocking=False) as lease:
        held = subprocess.run([python, '-c', probe], env=old_env, capture_output=True, text=True, timeout=10)
        assertion('baseline is excluded while V2 owns host native lock', held.returncode == 0 and held.stdout.strip() == 'BUSY', {'lock': lease['path']})
    released = subprocess.run([python, '-c', probe], env=old_env, capture_output=True, text=True, timeout=10)
    assertion('host lock becomes available after V2 releases it', released.returncode == 0 and released.stdout.strip() == 'ACQUIRED:'+p['shared_native_lock'])
    dev_db = Path(p['home'])/'state/workbench.sqlite'
    before_restart = logical_state(dev_db)
    current = json.loads(active.read_text()); os.kill(current['pid'], signal.SIGTERM)
    time.sleep(.2)
    restarted = launch(runtime, background=True); wait(dev_url+'/')
    status, current_roster = request('GET', '/api/conversations')
    assertion('service restart preserves deferred original test owner', status == 200 and any(s['id'] == owner and s['status'] == 'IDLE' for s in current_roster['sessions']))
    after_restart = logical_state(dev_db)
    assertion('restart preserves all development accounting and design rows', before_restart == after_restart)
    with readonly(dev_db) as db:
        counts = {t: db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['model_requests','engineering_jobs','eda_cli_jobs']}
    assertion('no inference or native jobs created', all(n == 0 for n in counts.values()), counts)
    all_inputs = json.loads((runtime/'inputs/P01/INPUTS.json').read_text())
    assertion('public baseline inputs match frozen source', all(digest(runtime/'inputs/P01'/name) == ref['sha256'] for name,ref in all_inputs['files'].items()), {'files':len(all_inputs['files'])})
    native = runtime/'native-projects/P01-B0-copy'
    native_refs = {name[len('p01/native-project/'):]:ref for name,ref in original['files'].items() if name.startswith('p01/native-project/')}
    assertion('native archival copy matches original bytes', all(digest(native/name) == ref['sha256'] for name,ref in native_refs.items()), {'files':len(native_refs),'live_opened':False})
    baseline_after = verify(p['baseline']['path'], origins=True)
    assertion('all original databases sources and native files preserved', baseline_before == baseline_after, baseline_after)
    demo_after = {name: hashlib.sha256(urllib.request.urlopen('http://127.0.0.1:8768'+name, timeout=5).read()).hexdigest() for name in demo_paths}
    assertion('Demo UI and running process preserved', demo_before == demo_after and json.loads((demo_root/'active-runtime.json').read_text()) == demo_receipt)
    command = subprocess.run(['git','bundle','verify',str(Path(p['baseline']['path'])/'source.bundle')],cwd=SOURCE,capture_output=True,text=True)
    assertion('baseline Git bundle can restore the tagged source', command.returncode == 0)
    files = subprocess.check_output(['git','diff','--name-only'],cwd=SOURCE,text=True).splitlines()
    new = subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=SOURCE,text=True).splitlines()
    source_pins = {name:digest(SOURCE/name) for name in sorted(set(files+new)) if (SOURCE/name).is_file() and not name.startswith('battery-world/docs/agentlab/architecture-v2/verification-')}
    result = {'schema_version':'bf-architecture-v2-ab-verification-v1','status':'PASS',
        'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'baseline':p['baseline'],
        'source':{'branch':p['branch'],'base_commit':p['base_commit'],'worktree':str(SOURCE),'uncommitted_source_files':source_pins},
        'profile_sha256':digest(runtime/'profile.json'),'configuration_sha256':digest(runtime/'runtime.json'),
        'live_checks':live,'unit_tests':{'status':'PASS','log':'unit-tests.txt'},
        'sdk':sdk_result,'runtime':{'port':p['port'],'home':p['home'],'server_pid':restarted['pid']},
        'baseline_verification':baseline_after,'demo':{'port':8768,'pid':demo_receipt['pid'],'asset_hashes':demo_after},
        'new_model_requests':0,'new_solver_jobs':0,'original_owners_preserved':len(original['original_owners'])}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'PASS','live_checks':len(live),'output':str(output),'dev_owner':owner,'dev_pid':restarted['pid'],
                      'baseline_files':baseline_after['files'],'original_owners_preserved':len(original['original_owners']),'new_model_requests':0,'new_solver_jobs':0},ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    check(args.runtime,args.output)


if __name__ == '__main__':
    main()
