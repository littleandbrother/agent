"""Fresh actual Pi process -> existing bf_experiment -> registry service -> BLOCKED.

The tool invocation is scripted by the trusted controller. No model selects it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import secrets
import signal
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from paths import ROOT, PI, read, sha, digest, write_once, module, verify_inputs
from service_adapter import RegistryService, fixture_settings, FIXTURE_BEARER, FIXTURE_OWNER
from trace_readback import validate_trace

launcher = module('bfworld.agentlab.explicit_launcher_overlay', ROOT / 'src/launcher_overlay.py')

def run(output):
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to(ROOT):
        raise ValueError('NEW_OWNED_OUTPUT_REQUIRED')
    output.mkdir(parents=True)
    write_once(output / 'offline-runtime-profile.json', fixture_settings())
    service = RegistryService(output / 'service', output / 'offline-runtime-profile.json')
    packet = service.packet('DEV-FEASIBLE-01')
    write_once(output / 'EXECUTION-PACKET.json', packet)
    harness = launcher.freeze(source=PI / 'packages/bf-harness', label='EXPLICIT-PACKET-H0-v2', home_root=ROOT / 'fixture-runtime')
    manifest = read(harness / 'manifest.json')
    if manifest['model'] is not None or manifest['session_caps'] is not None:
        raise ValueError('LEGACY_MODEL_OR_BUDGET_DEFAULT_NOT_ALLOWED')
    if manifest['world'] is not None or manifest['world_authority'] != 'explicit-execution-packet':
        raise ValueError('LEGACY_WORLD_LABEL_NOT_AUTHORITY')
    build = read(ROOT / 'reports/BUILD-RECEIPT.json')
    if sha(PI / 'packages/bf-agent/dist/main.js') != build['main_build']:
        raise ValueError('BUILD_DRIFT')
    workspace = output / 'process'
    workspace.mkdir()
    (workspace / '.pi').mkdir()
    (workspace / 'home').mkdir()
    # This requests only the frozen canonical default spec, not a feasible
    # reference or a supplied solution. The service keeps admission false.
    write_once(workspace / 'candidate.json', {})
    loaded = {key: manifest['loaded_modules'][key] for key in ('solver', 'improver')}
    nonce = secrets.token_hex(24)
    config = {'workspace': str(workspace), 'taskId': packet['task_id'], 'mode': 'solve',
        'dryRun': True, 'trustedControllerProbe': True, 'executionPacket': packet,
        'token': FIXTURE_BEARER, 'sourceManifest': manifest,
        'solverModule': str(harness / 'dist/solver.js'), 'improverModule': str(harness / 'dist/improver.js'),
        'controlledActivation': {'nonce': nonce, 'harnessSourceHash': manifest['source_hash'],
            'appBuildHash': manifest['app_build_hash'], 'loaded': loaded, 'bindingHash': digest(packet)}}
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic()
    with service.serve() as url:
        config['service'] = url
        with (workspace / 'stdout.jsonl').open('x') as stdout, (workspace / 'stderr.log').open('x') as stderr:
            proc = subprocess.Popen([launcher.NODE, str(PI / 'packages/bf-agent/dist/main.js'), '-'],
                cwd=workspace, env={'PATH': str(Path(launcher.NODE).parent) + ':/usr/bin:/bin',
                    'HOME': str(workspace / 'home'), 'LANG': 'C.UTF-8'},
                stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                proc.communicate(json.dumps(config).encode(), timeout=packet['runtime_profile']['budget']['wall_seconds'])
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    lines = (workspace / 'stdout.jsonl').read_text().splitlines()
    events = [json.loads(line) for line in lines if line.startswith('{')]
    controls = [e for e in events if e.get('type') == 'controlled_activation']
    for event in controls:
        if (event['nonce'] != nonce or event['pid'] != proc.pid or event['loaded'] != loaded
            or event['binding_hash'] != digest(packet) or event['app_build_hash'] != manifest['app_build_hash']):
            raise ValueError('ACTIVATION_BINDING_MISMATCH')
        if event['phase'] == 'invoked':
            raw = json.dumps(event['output'], ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            if hashlib.sha256(raw).hexdigest() != event['output_hash']:
                raise ValueError('INVOCATION_OUTPUT_MISMATCH')
    bound = [e for e in events if e.get('type') == 'controlled_task_bound']
    probes = [e for e in events if e.get('type') == 'trusted_controller_probe']
    if proc.returncode != 0 or len(bound) != 1 or len(probes) != 1:
        write_once(output / 'FAILED-PROCESS.json', {'exit_code': proc.returncode, 'events': len(events),
            'stdout_sha256': sha(workspace / 'stdout.jsonl'), 'stderr_sha256': sha(workspace / 'stderr.log')})
        raise ValueError('TRUSTED_PROTOCOL_PROCESS_FAILED:' + (workspace / 'stderr.log').read_text()[-1600:])
    result = validate_trace(events, packet, manifest, proc.pid, nonce, proc.returncode)
    if result['status'] != 'BLOCKED' or result['request']['task_id'] != 'DEV-FEASIBLE-01' or result['execution_packet_id'] != packet['packet_id']:
        raise ValueError('NATIVE_BLOCK_OR_TASK_BINDING_MISMATCH')
    if result['native_tool_identities'] != {} or not result['native_prepare_error'].startswith('TOOL_IDENTITY_MISSING_OR_INVALID:'):
        raise ValueError('MISSING_NATIVE_TOOLS_WERE_SUBSTITUTED')
    service_rows = service.journal.read()
    receipt = {'schema': 'magnetic-service-trusted-probe-v1', 'status': 'transport_and_identity_pass_native_blocked',
        'task_id': packet['task_id'], 'task_contract_hash': packet['task_contract_hash'], 'world_id': packet['world_id'],
        'evaluator_sha256': packet['evaluator_sha256'], 'execution_packet_id': packet['packet_id'],
        'pid': proc.pid, 'supervisor_pid': os.getpid(), 'exit_code': proc.returncode,
        'post_import': [e['entrypoint'] for e in controls if e['phase'] == 'post_import'],
        'invoked': [e['entrypoint'] for e in controls if e['phase'] == 'invoked'],
        'job_id': result['id'], 'job_status': result['status'], 'native_prepare_error': result['native_prepare_error'],
        'native_tool_identities': {}, 'provider_calls': 0, 'model_calls': 0, 'native_solver_calls': 0,
        'autonomous_participant': False, 'approved_model': None, 'approved_budget': None,
        'fixture_model_id': packet['runtime_profile']['model']['model_id'],
        'actual_existing_http_handler_used': True, 'actual_existing_bf_experiment_body_used': True,
        'legacy_workbench_store_provider_worker_instantiated': False,
        'service_loopback_closed_before_receipt': True,
        'service_event_types': [r['type'] for r in service_rows], 'service_journal_head': service.journal.head,
        'source_verification': verify_inputs(),
        'main_source_sha256': sha(PI / 'packages/bf-agent/src/main.ts'),
        'adapter_source_sha256': sha(ROOT / 'src/service_adapter.py'),
        'stdout_sha256': sha(workspace / 'stdout.jsonl'), 'stderr_sha256': sha(workspace / 'stderr.log'),
        'process_wall_seconds': time.monotonic() - start,
        'process_child_cpu_seconds': after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
        'claim_boundary': 'scripted trusted transport/identity test through real Pi; no model-selected action, native experiment, qualification, or scientific success'}
    write_once(output / 'RESULT.json', receipt)
    return receipt

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))
