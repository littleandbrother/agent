#!/usr/bin/env python3
"""Finite BF episode verification and real-SDK, zero-provider software rehearsal."""
import argparse
import http.server
import importlib.util
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

from bfworld.agentlab.campaign20261019.phase1 import (
    BFPhaseGateway, digest, encoded, file_hash, ledger, require_lease, seal, tool_definition,
)

APP = Path(__file__).resolve().parents[1]
PI = APP.parent / 'pi-bf-aiot'


def build(root):
    root.mkdir(parents=True, exist_ok=True)
    harness = root / 'harness'
    dest = harness / 'dist/phase1/episode.js'
    source = PI / 'packages/bf-agent/src/phase1/episode.ts'
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='phase1-build-', dir=root) as tmp:
        command = [str(PI / 'node_modules/.bin/tsgo'), '-p',
                   str(PI / 'packages/bf-agent/tsconfig.json'), '--outDir', tmp]
        result = subprocess.run(command, cwd=PI, capture_output=True, text=True, timeout=60)
        if result.returncode:
            seal(root / 'build-failure.json', {'exit_code': result.returncode,
                 'stdout': result.stdout[-3000:], 'stderr': result.stderr[-1000:]})
            raise ValueError('SDK_BUILD_FAILED')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((Path(tmp) / 'phase1/episode.js').read_bytes())
    frozen = harness / 'src/phase1/episode.ts'
    frozen.parent.mkdir(parents=True)
    frozen.write_bytes(source.read_bytes())
    (harness / 'node_modules').symlink_to(PI / 'node_modules', target_is_directory=True)
    sdk = (PI / 'node_modules/@earendil-works/pi-coding-agent').resolve()
    sdk_files = {str(p): file_hash(p) for p in sorted((sdk / 'dist/bundle').rglob('*.js'))}
    if str(sdk / 'dist/bundle/index.js') not in sdk_files:
        raise ValueError('PINNED_SDK_RELEASE_BUNDLE_MISSING')
    manifest = {'source_sha256': file_hash(source), 'compiled_sha256': file_hash(dest),
                'sdk_lock_sha256': file_hash(PI / 'package-lock.json'),
                'sdk_version': json.loads((sdk / 'package.json').read_text())['version'],
                'sdk_runtime_files': sdk_files,
                'sdk_entry': str(sdk / 'dist/bundle/index.js'),
                'build_wall_seconds': time.monotonic() - started,
                'installed_dependencies_reused': True, 'new_environment_installed': False}
    seal(harness / 'manifest.json', manifest)
    return harness, manifest


def invoke(root, harness, config, timeout):
    from bfworld.agentlab import launcher
    from bfworld.agentlab.runtime_config import NODE
    workspace = Path(config['workspace'])
    workspace.mkdir(parents=True)
    (workspace / '.tmp').mkdir()
    port = int(config['service'].rsplit(':', 1)[1])
    seatbelt = launcher.seatbelt(workspace, harness, port)
    start = time.monotonic()
    with (root / 'pi-public-trace.jsonl').open('w') as stdout, (root / 'pi-stderr.log').open('w') as stderr:
        process = subprocess.Popen(['/usr/bin/sandbox-exec', '-p', seatbelt, str(NODE),
                   str(harness / 'dist/phase1/episode.js')], cwd=workspace,
                   env={'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'TMPDIR': str(workspace / '.tmp'),
                        'LANG': 'en_US.UTF-8'}, stdin=subprocess.PIPE,
                   stdout=stdout, stderr=stderr, start_new_session=True)
        timed_out = False
        try:
            process.communicate(encoded(config) + b'\n', timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
    return {'exit_code': process.returncode, 'wall_seconds': time.monotonic() - start,
            'timed_out': timed_out, 'sandbox_sha256': hashlib_sha(seatbelt.encode())}


def hashlib_sha(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def smoke(root, *, ar_host=False):
    if root.exists():
        raise FileExistsError('Retain this rehearsal; use a new explicit output identity.')
    harness, built = build(root)
    dbpath = root / 'fixture-ledger.sqlite'
    with sqlite3.connect(dbpath) as db:
        db.execute('CREATE TABLE model_requests(id TEXT,owner TEXT,created REAL,status TEXT,'
                   'reserved REAL,charged REAL,usage TEXT,response_hash TEXT,error TEXT)')
    requests, tool_calls = [], []
    schema = {'type': 'object', 'properties': {'action': {'enum': ['inspect', 'check', 'submit']},
              'candidate': {'type': 'object', 'properties': {'capacitance_f': {'type': 'number', 'minimum': 1e-6}},
                            'additionalProperties': False}}, 'required': ['action'], 'additionalProperties': False}
    tool = tool_definition('bf_phase1', 'Read the BF software fixture. It is not an experiment or physical evidence.', schema)
    call = {'action': 'inspect'}
    host = None
    if ar_host:
        spec = importlib.util.spec_from_file_location('bf_phase1_ar_rehearsal', APP / 'scripts/campaign_ar_service.py')
        host = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = host
        spec.loader.exec_module(host)
        tool = tool_definition(**host.tool_definition())
        actual_handler = host.create_handler(root / 'scientific')
        call['topic'] = 'contract'

    class FakeProvider(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(payload)
            index = len(requests)
            usage = {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3,
                     'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 2}
            with sqlite3.connect(dbpath) as db:
                db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?)',
                    ('fixture-' + str(index), 'fixture-owner', time.time(), 'SETTLED', 0, 0,
                     json.dumps(usage), 'fixture-response', None))
            if index == 1:
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'fixture-inspect',
                         'type': 'function', 'function': {'name': tool['name'], 'arguments': encoded(call).decode()}}]}
                reason = 'tool_calls'
            else:
                delta = {'role': 'assistant', 'content': 'Software fixture consumed; no paid model or scientific claim.'}
                reason = 'stop'
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for data in [
                {'id': 'fixture-' + str(index), 'object': 'chat.completion.chunk', 'model': 'deepseek-flash',
                 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                {'id': 'fixture-' + str(index), 'object': 'chat.completion.chunk', 'model': 'deepseek-flash',
                 'choices': [{'index': 0, 'delta': {}, 'finish_reason': reason}], 'usage': usage}]:
                self.wfile.write(b'data: ' + encoded(data) + b'\n\n')
            self.wfile.write(b'data: [DONE]\n\n')
            self.wfile.flush()

    mock = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeProvider)
    thread = threading.Thread(target=mock.serve_forever, daemon=True)
    thread.start()
    def handler(body):
        tool_calls.append(body)
        if host:
            return actual_handler(body)
        return {'observation_id': 'fixture-supply-storage-program-receive', 'stored_j': .01,
                'scope': 'Synthetic software fixture; no experiment performed', 'consumer': 'actual Pi SDK tool result'}
    protocol = {'id': 'phase1-sdk-software-rehearsal', 'mode': 'fixture', 'owner': 'fixture-owner',
        'tool': tool, 'provider_database': str(dbpath),
        'provider_service': 'http://127.0.0.1:' + str(mock.server_port),
        'allowed_reported_models': ['deepseek-flash'],
        'bound_files': {str(harness / 'dist/phase1/episode.js'): built['compiled_sha256'],
                        **built['sdk_runtime_files'],
                        **({str(APP / path): file_hash(APP / path) for path in host.SOURCE_PATHS} if host else {})},
        'output_root': str(root),
        'candidate_fields': ['candidate'], 'candidate_actions': ['check'],
        'limits': {'model_requests': 3, 'candidates': 3, 'wall_seconds': 60, 'reserve_bytes': 0,
            'peak_remaining_bytes': 0, 'output_bytes': 5000000, 'tool_calls': 5,
            'tool_response_bytes': 96000, 'model_request_bytes': 512000,
            'model_response_bytes': 64000000, 'max_output_tokens': 32768}}
    lease = root / 'fixture-lease.json'
    seal(lease, {'status': 'GRANTED', 'episode': protocol['id'], 'expires': time.time() + 60,
                 'holders': ['S0', 'Pi'], 'other_executor_status': 'idle', 'scope': 'No actual model runs'})
    gateway = BFPhaseGateway(protocol, root / 'gateway', handler, provider_token='fixture-only', lease_path=lease)
    seal(root / 'protocol.json', protocol)
    try:
        service = gateway.start()
        result = invoke(root, harness, {'workspace': str(root / 'participant'), 'service': service,
            'token': gateway.token, 'owner': protocol['owner'], 'goal': 'Exercise the software fixture tool.',
            'instruction': 'This is a zero-provider SDK rehearsal, not a research trial.',
            'episodeId': protocol['id'], 'tool': tool}, timeout=45)
    finally:
        gateway.close()
        mock.shutdown()
        mock.server_close()
        thread.join(timeout=2)
    marker = host.load_contract()['schema_version'] if host else 'fixture-supply-storage-program-receive'
    consumed = len(requests) == 2 and marker in json.dumps(requests[1])
    result.update(status='PASS' if result['exit_code'] == 0 and consumed and tool_calls == [call] else 'FAIL',
        actual_sdk_requests=len(requests), actual_tool_calls=len(tool_calls), consumer_roundtrip=consumed,
        actual_ar_host=ar_host, paid_model_requests=0, native_dispatches=0,
        scope='Real Pi SDK and tool path, mock model only; software-path qualification')
    seal(root / 'mock-requests.json', requests)
    seal(root / 'result.json', result)
    print(json.dumps(result))
    if result['status'] != 'PASS':
        print((root / 'pi-stderr.log').read_text()[-2500:])
        raise SystemExit(1)


def verify(path):
    p = json.loads(path.read_text())
    for name, expected in p['bound_files'].items():
        if file_hash(name) != expected:
            raise ValueError('BOUND_INPUT_CHANGED:' + name)
    frozen = tool_definition(**{k: p['tool'][k] for k in ('name', 'description', 'parameters')})
    if frozen != p['tool']:
        raise ValueError('TOOL_CONTRACT_CHANGED')
    print(json.dumps({'status': 'PASS', 'protocol_sha256': digest(p), 'bound_files': len(p['bound_files']),
                      'paid_model_requests': 0, 'native_dispatches': 0}))


def audit_participant(root, tool_name):
    """Match the actual model's public tool call to the host's executed input."""
    previous = '0' * 64
    executed, generated = [], []
    for line in (root / 'gateway/gateway-events.jsonl').read_text().splitlines():
        event = json.loads(line)
        saved = event.pop('sha256')
        if event['previous'] != previous or digest(event) != saved:
            raise ValueError('GATEWAY_TRACE_CHAIN_FAILED')
        previous = saved
        if event['kind'] == 'tool_started':
            executed.append(event['data']['input'])
    for line in (root / 'pi-public-trace.jsonl').read_text().splitlines():
        event = json.loads(line)
        if event.get('type') == 'assistant_public':
            generated.extend(c['arguments'] for c in event['content']
                if c.get('type') == 'toolCall' and c.get('name') == tool_name)
    missing = [digest(v) for v in executed if v not in generated]
    if missing:
        raise ValueError('EXECUTED_INPUT_NOT_BOUND_TO_MODEL_TOOL_CALL')
    return {'gateway_chain_tip': previous, 'executed_inputs': len(executed),
            'model_tool_calls': len(generated), 'unmatched_executed_inputs': missing,
            'model_submitted': any(v.get('action') == 'submit' for v in executed)}


def run_episode(path, lease_path):
    """A single fresh paid episode; its token arrives on stdin and is never saved."""
    verify(path)
    p = json.loads(path.read_text())
    if p.get('mode') != 'public-development':
        raise ValueError('PAID_RUN_REQUIRES_PUBLIC_DEVELOPMENT_PROTOCOL')
    require_lease(lease_path, p['id'])
    if ledger(p['provider_database'], p['owner'])['requests']:
        raise ValueError('EPISODE_ALREADY_HAS_PROVIDER_ROWS_NO_RESAMPLING')
    root = Path(p['output_root'])
    if Path(p['ar_tool_script']).resolve() != (APP / 'scripts/campaign_ar_service.py').resolve():
        raise ValueError('FROZEN_AR_HOST_SCRIPT_REQUIRED')
    if str(Path(p['ar_tool_script'])) not in p['bound_files']:
        raise ValueError('AR_HOST_MUST_BE_BOUND')
    token = sys.stdin.readline().strip()
    if not token or len(token) > 4096:
        raise ValueError('PROVIDER_PARTICIPANT_TOKEN_REQUIRED_ON_STDIN')
    spec = importlib.util.spec_from_file_location('bf_phase1_ar_host', p['ar_tool_script'])
    host = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = host
    spec.loader.exec_module(host)
    actual_tool = tool_definition(**host.tool_definition())
    if actual_tool != p['tool']:
        raise ValueError('AR_HOST_TOOL_CONTRACT_CHANGED')
    context = {'episode_id': p['id'], 'model': 'deepseek-flash', 'backend': p['provider_service'],
        'provider_ledger': p['provider_database'], 'slot_receipt': str(lease_path),
        'baseline': p['baseline'], 'maximum_requests': p['limits']['model_requests'],
        'maximum_candidates': p['limits']['candidates'], 'maximum_wall_s': p['limits']['wall_seconds']}
    started = time.monotonic()
    gateway = None
    result = {'status': 'START_FAILURE', 'episode': p['id'], 'owner': p['owner'],
              'protocol_sha256': digest(p), 'native_dispatches': 0, 'automatic_retry': False}
    try:
        handler = host.create_handler(root / 'scientific', lease=context)
        gateway = BFPhaseGateway(p, root / 'gateway', handler, provider_token=token, lease_path=lease_path)
        result.update(invoke(root, Path(p['harness']), {
            'workspace': str(root / 'participant'), 'service': gateway.start(),
            'token': gateway.token, 'owner': p['owner'], 'goal': p['goal'],
            'instruction': p['instruction'], 'episodeId': p['id'], 'tool': p['tool']},
            timeout=max(1, p['limits']['wall_seconds'] - (time.monotonic() - started))))
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)[:2000]
    finally:
        if gateway:
            gateway.close()
        result['wall_seconds_total'] = time.monotonic() - started
        account = ledger(p['provider_database'], p['owner'])
        seal(root / 'provider-costs.json', account)
        result['provider_requests'] = account['requests']
        result['unresolved_usage'] = account['unknown_or_missing_usage']
        result['settled_charge_upper_bound_usd'] = account['settled_charge_upper_bound_usd']
        result['cache_aware_rate_estimate_usd'] = account['cache_aware_rate_estimate_usd']
    try:
        result['trace_audit'] = audit_participant(root, p['tool']['name'])
        submitted = (root / 'scientific/submission.json').exists() and result['trace_audit']['model_submitted']
        result['reported_models'] = sorted(gateway.models_seen) if gateway else []
        result['status'] = ('PARTICIPANT_SUBMITTED_REQUIRES_EXTERNAL_EVALUATION'
            if result.get('exit_code') == 0 and submitted and not result['unresolved_usage']
            and result['reported_models'] and not gateway.stopped else 'INCOMPLETE_OR_STOPPED')
    except Exception as error:
        result['status'] = 'TRACE_AUDIT_FAILED'
        result['trace_error'] = type(error).__name__ + ': ' + str(error)[:2000]
    result['scientific_acceptance'] = 'EXTERNAL_EVALUATION_REQUIRED'
    seal(root / 'episode-result.json', result)
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    modes = parser.add_subparsers(dest='mode', required=True)
    s = modes.add_parser('smoke')
    s.add_argument('--output', required=True, type=Path)
    s.add_argument('--ar-host', action='store_true')
    v = modes.add_parser('verify')
    v.add_argument('--protocol', required=True, type=Path)
    r = modes.add_parser('run')
    r.add_argument('--protocol', required=True, type=Path)
    r.add_argument('--lease', required=True, type=Path)
    args = parser.parse_args()
    if args.mode == 'smoke':
        smoke(args.output.resolve(), ar_host=args.ar_host)
    elif args.mode == 'verify':
        verify(args.protocol)
    else:
        run_episode(args.protocol.resolve(), args.lease.resolve())
