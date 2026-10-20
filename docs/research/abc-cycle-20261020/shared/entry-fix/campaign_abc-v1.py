#!/usr/bin/env python3
"""One finite ABC episode using the registered S0 runtime, ledger and Pi SDK."""
import argparse
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

from bfworld.agentlab.campaign20261019.phase1 import digest, encoded, file_hash, ledger, seal, tool_definition
from bfworld.agentlab.campaign20261019.abc_shared import ABCGateway, check_bindings, require_capacity, slot_holders

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[2]
PLAN = ROOT / 'docs/research/abc-cycle-20261020/shared/protocol.json'
OUT = Path.home() / '.local/share/bf-abc-20261020'
PROFILE = Path.home() / '.local/share/bf-campaign-20261019-s0/profile.json'
OLD_HARNESS = Path.home() / '.local/share/bf-phase1-20261020/a/ar-service/pi-episode-001/harness'


def load(path):
    return json.loads(Path(path).read_text())


def configure():
    profile = load(PROFILE)
    for key, value in profile['paths'].items():
        os.environ['BF_' + key] = value
    os.environ.update(BF_RUNTIME_ROOT=profile['runtime_root'], BF_RUNTIME_CONFIG=profile['configuration'],
                      BF_DEVELOPMENT_PROFILE=str(PROFILE), PYTHONDONTWRITEBYTECODE='1',
                      PI_CODING_AGENT_DIR=str(Path(profile['home']) / 'pi-config'))
    return profile


def runner_module():
    spec = importlib.util.spec_from_file_location('abc_existing_sdk_runner', APP / 'scripts/campaign_phase1.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build():
    source = APP / 'configs/studies/abc-20261020/episode.ts'
    old = load(OLD_HARNESS / 'manifest.json')
    check_bindings(old['sdk_runtime_files'])
    harness = OUT / 'harness'
    if (harness / 'manifest.json').exists():
        value = load(harness / 'manifest.json')
        check_bindings(value['bound_files'])
        return value
    target = harness / 'src/phase1/episode.ts'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    if not (harness / 'node_modules').is_symlink():
        (harness / 'node_modules').symlink_to(APP.parent / 'pi-bf-aiot/node_modules', target_is_directory=True)
    (harness / 'package.json').write_text('{"type":"module"}\n')
    compiled = harness / 'dist/phase1/episode.js'
    compile_result = subprocess.run([str(harness / 'node_modules/.bin/esbuild'), str(target),
        '--format=esm', '--platform=node', '--target=node22', '--outfile=' + str(compiled)],
        cwd=harness, capture_output=True, text=True, timeout=60)
    if compile_result.returncode:
        raise ValueError('ABC_SDK_BUILD:' + (compile_result.stdout + compile_result.stderr)[-4000:])
    value = dict(source_sha256=file_hash(source), compiled_sha256=file_hash(compiled),
                 sdk_version=old['sdk_version'], reused_sdk_manifest_sha256=file_hash(OLD_HARNESS / 'manifest.json'),
                 no_new_dependency_environment=True,
                 bound_files={str(source): file_hash(source), str(target): file_hash(target),
                              str(compiled): file_hash(compiled), **old['sdk_runtime_files']})
    seal(harness / 'manifest.json', value)
    return value


def b_executor(task):
    """Full frozen B input, original numerical engine and independent reference."""
    import zlib
    from bfworld.agentlab.campaign20261019 import b
    spec = importlib.util.spec_from_file_location('abc_original_reference', APP / 'scripts/campaign_reference.py')
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    key = digest(dict(task=task, producer=file_hash(b.__file__), reference=file_hash(reference.__file__)))
    root = OUT / 'exact-inputs/B' / key
    target = root / 'feedback.json'
    if target.exists():
        value = load(target)
        if value['input_sha256']!=digest(task) or file_hash(value['raw_path'])!=value['raw_sha256']:
            raise ValueError('ABC_B_EXACT_INPUT_CACHE_DRIFT')
        raw = json.loads(zlib.decompress(Path(value['raw_path']).read_bytes()))
        if raw['input_sha256']!=digest(task): raise ValueError('ABC_B_RAW_CACHE_INPUT_DRIFT')
        return {**value, 'reused':True, 'origin':'sealed-historical-exact-input'}
    plan = load(PLAN)
    profile = load(PROFILE)
    require_capacity(plan, OUT, Path(profile['home'])/'state/workbench.sqlite')
    run = b.simulate_b(task)
    energy = reference.energy_reference(task, run['trace'], 'B')
    checked = reference.reference_b(task, run, energy)
    root.mkdir(parents=True)
    raw = root / 'raw.json.zlib'
    raw.write_bytes(zlib.compress(encoded(dict(input_sha256=digest(task),task=task,run=run)),9))
    value = dict(input_sha256=digest(task), execution_key=key, energy=energy, reference=checked,
                 origin='new-full-feedback-response', reused=False, raw_path=str(raw),raw_sha256=file_hash(raw),
                 execution_fidelity='full-frozen-B-model', physical_qualification='NOT_CALIBRATED')
    seal(target,value)
    return value


def run(spec_path, slots_path, protocol_path=PLAN):
    global PLAN
    PLAN = protocol_path
    plan = load(protocol_path)
    check_bindings(plan['bound_files'])
    profile = configure()
    database = Path(profile['home']) / 'state/workbench.sqlite'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        if db.execute("SELECT count(*) FROM model_requests WHERE status NOT IN ('SETTLED','NOT_SENT')").fetchone()[0]:
            raise ValueError('PROVIDER_USAGE_UNRESOLVED')
    spec = load(spec_path)
    ident = spec['episode_id']
    registration = plan['episodes'].get(ident)
    if registration is None or spec['package'] != registration['package']:
        raise ValueError('ABC_EPISODE_UNREGISTERED')
    template = load(registration['template'])
    allowed_runtime = {'history_path', 'method_path', 'method_sha256', 'frozen_no_update_receipt'}
    if {k:v for k,v in spec.items() if k not in allowed_runtime} != {k:v for k,v in template.items() if k not in allowed_runtime}:
        raise ValueError('ABC_FROZEN_SPEC_CHANGED')
    if spec['package']=='methods' and spec['stage']!='formation' and spec['arm'] in ('ordinary','proposed'):
        formation = OUT / 'episodes' / ('C-formation-' + spec['arm'])
        formed = load(formation / 'episode-result.json')
        raw_method = formation / 'methods/method-submission.json'
        if spec.get('method_path'):
            if (Path(spec['method_path']).resolve()!=raw_method.resolve() or formed['status']!='ACTUAL_SUBMITTED' or
                    formed.get('independent_result',{}).get('status')!='STRUCTURALLY_ADMITTED' or
                    spec['method_sha256']!=file_hash(raw_method)):
                raise ValueError('ABC_METHOD_NOT_AUTHENTICATED_RAW_BF_OUTPUT')
        elif not spec.get('frozen_no_update_receipt') or (formed['status']=='ACTUAL_SUBMITTED' and
                formed.get('independent_result',{}).get('status')=='STRUCTURALLY_ADMITTED'):
            raise ValueError('ABC_NO_UPDATE_WITHOUT_ORIGINAL_FAILED_FORMATION')
    holders = slot_holders(load(slots_path))
    require_capacity(plan, OUT, database, entering=True)
    built = load(OUT / 'harness/manifest.json')
    check_bindings(built['bound_files'])
    root = OUT / 'episodes' / ident
    if root.exists():
        raise ValueError('ACTUAL_ATTEMPT_EXISTS_NO_AUTOMATIC_RETRY')
    root.mkdir(parents=True)
    started = time.monotonic()
    seal(root / 'attempt.json', dict(spec=spec, source_spec_sha256=file_hash(spec_path),
         protocol_sha256=file_hash(PLAN), started_unix=time.time(), automatic_retry=False))
    module = importlib.import_module(plan['modules'][spec['package']])
    owner = token = gateway = None
    result = dict(episode=ident, package=spec['package'], spec=spec, status='START_FAILURE',
                  automatic_retry=False, native_dispatches=0)
    tool = None
    service = plan['provider_service']
    operator = (Path(profile['home']) / 'state/operator.token').read_text().strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def api(path, value):
        request = urllib.request.Request(service + path, data=encoded(value),
            headers={'Authorization':'Bearer ' + operator, 'Content-Type':'application/json'})
        with opener.open(request, timeout=30) as response:
            return json.load(response)
    try:
        prepared = module.prepare_episode(spec, root)
        if spec['package']=='interfaces':
            payload = dict(task=load(prepared['participant_task']), common_instruction=prepared['prompt'])
            if spec.get('condition')=='complete_information':
                payload['complete_sources'] = {p.stem:load(p) for p in (root/'public/sources').glob('*.json')}
        else:
            payload = prepared['participant_input']
        seal(root / 'participant-payload.json', payload)
        definition = module.tool_definition(spec)
        tool = tool_definition(**{k:definition[k] for k in ('name','description','parameters')})
        goal = 'Complete the assigned ABC stage using the frozen BF tool and submit the assigned artifact.\n' + encoded(payload).decode()
        owner = api('/api/conversations', {'text':goal, 'operation_id':'ABC-' + ident, 'defer_dispatch':True})['id']
        seal(root / 'owner.json', dict(owner=owner, fresh_model_context=True))
        authority = api('/api/design-lab', dict(action='method_authorize', session_id=owner,
            task_id='method-study-ABC-' + ident, wall_authorization_text='持续运行 不设置时间限制',
            model_profile=plan['model_profile']))
        token = authority.pop('participant_token')
        seal(root / 'authority.json', authority)
        limits = plan['episode_limits']
        bound = {**plan['bound_files'], str(PLAN):file_hash(PLAN),
                 str(root / 'participant-payload.json'):file_hash(root / 'participant-payload.json')}
        for name in ('method_path','history_path'):
            if spec.get(name): bound[spec[name]] = file_hash(spec[name])
        protocol = dict(schema_version='bf-abc-episode-v1', id=ident, mode='public-development', owner=owner,
            output_root=str(root), provider_database=str(database), provider_service=service,
            allowed_reported_models=['deepseek-flash'], identity_scope='Provider alias only; exact upstream weights UNKNOWN',
            tool=tool, bound_files=bound, candidate_fields=[], candidate_actions=[], limits=limits)
        seal(root / 'protocol.json', protocol)
        lease = root / 'slot-lease.json'
        seal(lease, dict(status='GRANTED', episode=ident, expires=time.time()+limits['wall_seconds'],
             holders=holders, other_executor_status='idle', observation=load(slots_path)))
        extra = {'executor':b_executor} if spec['package']=='interfaces' else {}
        gateway = ABCGateway(protocol, root / 'gateway', module.create_handler(root, spec, **extra),
                             provider_token=token, lease_path=lease, batch=plan)
        result.update(runner_module().invoke(root, OUT / 'harness', dict(workspace=str(root/'participant'),
            service=gateway.start(), token=gateway.token, owner=owner, episodeId=ident, tool=tool,
            goal=goal, instruction=payload.get('common_instruction','Complete only the assigned stage.')),
            timeout=limits['wall_seconds']))
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)[:1800]
    finally:
        if gateway: gateway.close()
        token = None
        result['wall_seconds_total'] = time.monotonic()-started
        account = ledger(database, owner) if owner else dict(requests=0, rows=[], unknown_or_missing_usage=[],settled_charge_upper_bound_usd=0)
        seal(root/'provider-costs.json', account)
        result['accounting'] = {k:v for k,v in account.items() if k!='rows'}
    try:
        audit = runner_module().audit_participant(root, tool['name'])
        trace = [json.loads(s) for s in (root/'pi-public-trace.jsonl').read_text().splitlines()]
        starts = [v for v in trace if v.get('type')=='bf_episode_loaded']
        submissions = [c['arguments'] for v in trace if v.get('type')=='assistant_public' for c in v['content']
                       if c.get('type')=='toolCall' and c.get('name')==tool['name'] and
                       c['arguments'].get('action') in ('submit','submit_method')]
        result.update(trace_audit=audit, fresh_context=len(starts)==1 and starts[0].get('resume_messages')==0,
                      reported_models=sorted(gateway.models_seen), gateway_stopped=gateway.stopped)
        accepted = (result.get('exit_code')==0 and submissions and result['fresh_context'] and
                    result['reported_models']==['deepseek-flash'] and account['requests']>0 and
                    not account['unknown_or_missing_usage'] and not gateway.stopped)
        result['status'] = 'ACTUAL_SUBMITTED' if accepted else 'INCOMPLETE_OR_STOPPED'
        result['independent_result'] = module.independent_check(root, spec, **extra)
        result['independent_scope'] = 'Host only after SDK endpoint closed; submission remains distinct from acceptance.'
    except Exception as error:
        result['audit_or_check_error'] = type(error).__name__ + ': ' + str(error)[:1800]
    seal(root/'episode-result.json', result)
    print(json.dumps({k:result.get(k) for k in ('episode','status','wall_seconds_total','accounting','independent_result','error','audit_or_check_error')},ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('build')
    command = sub.add_parser('run')
    command.add_argument('--spec', required=True, type=Path)
    command.add_argument('--slots', required=True, type=Path)
    command.add_argument('--protocol', type=Path, default=PLAN)
    args = parser.parse_args()
    if args.command=='build': print(json.dumps(build()))
    else:
        lock = OUT / 'active-owner.lock'
        with lock.open('x') as stream:
            stream.write(str(os.getpid()))
        try: run(args.spec, args.slots, args.protocol)
        finally: lock.unlink()
