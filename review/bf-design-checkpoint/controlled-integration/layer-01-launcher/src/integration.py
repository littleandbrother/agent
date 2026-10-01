"""Fail-closed adapter over the existing launcher, Pi runtime and journal.

The only executable route on this host is a fixed, trusted dry-run fixture.
It is not a sandbox and cannot execute participant-authored source.
"""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import http.server
import hashlib
import json
import os
from pathlib import Path
import resource
import secrets
import shutil
import signal
import subprocess
import threading
import time

from paths import ROOT, PI, PI_SOURCE, REPO, PROTOCOL, WORLD, EVALUATOR, sha, digest, read, write_once, module, verify_sources
from bfworld.agentlab import launcher, recursive
from bfworld.runtime.journal import HashJournal
from bfworld.campaign.budget import Ledger, BudgetStop
from bfworld.campaign import splits

contract = module('controlled_contract', PROTOCOL / 'preflight.py')
handoff = module('controlled_pipeline_handoff', WORLD / 'pipeline-handoff-v2/prepare_request.py')

VARIANTS = {'h0', 'h1-manual-fixture', 'import-failure', 'invoke-failure', 'improver-failure', 'timeout', 'build-failure'}
TERMINAL = {'activation_pass', 'build_failed', 'import_failed', 'invocation_failed', 'process_failed', 'timed_out', 'blocked', 'budget_exhausted'}

def fixture_sources(variant):
    if variant not in VARIANTS:
        raise ValueError('ARBITRARY_SOURCE_FORBIDDEN')
    files = {p.name: p.read_text() for p in (PI_SOURCE / 'packages/bf-harness/src').glob('*.ts')}
    if variant == 'h1-manual-fixture':
        files['solver.ts'] = files['solver.ts'].replace('plan: [],', 'plan: ["trusted-fixture-only"],')
    if variant == 'import-failure':
        files['solver.ts'] = 'throw new Error("TRUSTED_FIXTURE_IMPORT_FAILURE");\n' + files['solver.ts']
    if variant in {'invoke-failure', 'timeout'}:
        injected = 'throw new Error("TRUSTED_FIXTURE_INVOCATION_FAILURE");' if variant == 'invoke-failure' else 'while (true) {}'
        files['solver.ts'] = files['solver.ts'].replace('export function initialState(): SolverState {',
            'export function initialState(): SolverState {\n' + injected)
    if variant == 'improver-failure':
        files['improver.ts'] = files['improver.ts'].replace('export function improvementPrompt(context: any): string {',
            'export function improvementPrompt(context: any): string {\nthrow new Error("TRUSTED_FIXTURE_IMPROVER_FAILURE");')
    if variant == 'build-failure':
        files['solver.ts'] += '\nconst broken: = ;\n'
    return files

def build_fixture(variant):
    verify_sources()
    source = ROOT / 'fixture-sources' / variant
    (source / 'src').mkdir(parents=True, exist_ok=True)
    for name, text in fixture_sources(variant).items():
        target = source / 'src' / name
        if target.exists() and target.read_text() != text:
            raise ValueError('FIXTURE_SOURCE_DRIFT')
        if not target.exists():
            target.write_text(text)
    # This is the actual existing freeze/build implementation, not a substitute.
    return launcher.freeze(source=source, label='TRUSTED-' + variant,
                           home_root=ROOT / 'fixture-runtime')

def verify_harness(harness, variant):
    harness = Path(harness)
    if not harness.resolve().is_relative_to((ROOT / 'fixture-runtime/harnesses').resolve()):
        raise ValueError('NONFIXTURE_HARNESS_FORBIDDEN')
    manifest = read(harness / 'manifest.json')
    if launcher.identity({k: v for k, v in manifest.items() if k != 'identity'}) != manifest['identity']:
        raise ValueError('HARNESS_MANIFEST_TAMPER')
    sources = fixture_sources(variant)
    if set(manifest['source_files']) != {'src/' + name for name in sources}:
        raise ValueError('UNALLOWLISTED_SOURCE')
    for name, expected in sources.items():
        if (harness / 'src' / name).read_text() != expected or sha(harness / 'src' / name) != manifest['source_files']['src/' + name]:
            raise ValueError('FIXTURE_SOURCE_OR_BUILD_STALE')
    for name, expected in manifest['loaded_files'].items():
        if sha(harness / 'dist' / name) != expected:
            raise ValueError('HARNESS_BUILD_STALE')
    build = read(ROOT / 'reports/BUILD-RECEIPT.json')
    if sha(PI / 'packages/bf-agent/dist/main.js') != build['overlay_main_build'] or manifest['app_build_hash'] != build['overlay_main_build']:
        raise ValueError('APP_BUILD_STALE')
    if sha(PI / 'packages/bf-agent/src/main.ts') != build['overlay_main_source']:
        raise ValueError('APP_SOURCE_STALE')
    if manifest['pi_lock_hash'] != sha(PI_SOURCE / 'package-lock.json') or manifest['world_binding'] != launcher.world_binding():
        raise ValueError('HARNESS_BOUNDARY_DRIFT')
    return manifest

def current_binding():
    plan = read(PROTOCOL / 'protocol-world-bound-draft.json')
    return {'protocol_sha256': sha(PROTOCOL / 'protocol-world-bound-draft.json'),
        'world_id': plan['world_id'], 'task_manifest_sha256': sha(WORLD / 'contracts/tasks-v2.json'),
        'task_id': 'DEV-FEASIBLE-01', 'evaluator_source_sha256': sha(EVALUATOR),
        'adapter_source_sha256': sha(__file__),
        'evaluator_status': 'development_evaluator_not_formal_qualification',
        'input_lock_sha256': sha(ROOT / 'INPUT-LOCK.json'),
        'binding_scope': 'prospective_target_identity_only_not_executed_by_fixture'}

class AttemptBook:
    """Locked existing runtime HashJournal; one intent before any process effect.

    Unknown attempts are retained and prohibit retry. A durable receipt can be
    reconciled without repeating the process. Assignment is never inferred from
    only successful attempts.
    """
    def __init__(self, root, assignments, binding, max_attempts=20):
        self.root = Path(root).resolve()
        if not self.root.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('ADAPTER_OUTPUT_ROOT_REQUIRED')
        if not assignments or len(set(assignments)) != len(assignments):
            raise ValueError('ASSIGNMENTS_REQUIRED')
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError('EXPLICIT_ATTEMPT_CAP_REQUIRED')
        self.root.mkdir(parents=True, exist_ok=True)
        self.contract = {'assignments': list(assignments), 'binding': binding,
                         'max_attempts': max_attempts, 'purpose': 'trusted-integration-controls-only'}
        self.journal = HashJournal(self.root / 'events.jsonl', digest(self.contract))
        with self.lock():
            rows = self.journal.read()
            if not rows:
                self.journal.append('assigned', self.contract)
            elif rows[0]['payload'] != self.contract:
                raise ValueError('ASSIGNMENT_OR_BINDING_DRIFT')

    @contextmanager
    def lock(self):
        with (self.root / 'supervisor.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def attempts(self):
        result = {}
        for row in self.journal.read():
            p = row['payload']
            if row['type'] == 'attempt_reserved':
                if p['attempt_id'] in result:
                    raise ValueError('DUPLICATE_ATTEMPT')
                result[p['attempt_id']] = {**p, 'status': 'unknown'}
            elif row['type'] == 'attempt_finished':
                if p['attempt_id'] not in result or result[p['attempt_id']]['status'] != 'unknown':
                    raise ValueError('INVALID_TERMINAL_TRANSITION')
                result[p['attempt_id']].update(p)
        return result

    def begin(self, episode_id, attempt_id, request):
        with self.lock():
            if episode_id not in self.contract['assignments']:
                raise ValueError('UNASSIGNED_EPISODE')
            attempts = self.attempts()
            old = attempts.get(attempt_id)
            if old:
                if old['request_hash'] != digest(request) or old['episode_id'] != episode_id:
                    raise ValueError('IDEMPOTENCY_CONFLICT')
                if old['status'] == 'unknown':
                    raise ValueError('RECONCILIATION_REQUIRED_NO_REDISPATCH')
                path = self.root / old['receipt_file']
                if sha(path) != old['receipt_sha256']:
                    raise ValueError('RECEIPT_TAMPER')
                return self.validate_receipt(read(path))
            if any(x['status'] == 'unknown' for x in attempts.values()):
                raise ValueError('UNKNOWN_COST_OR_EFFECT_BLOCKS_NEXT_ATTEMPT')
            payload = {'episode_id': episode_id, 'attempt_id': attempt_id,
                'request_hash': digest(request), 'request': request}
            self.journal.append('attempt_reserved', payload)
            if len(attempts) >= self.contract['max_attempts']:
                receipt = self._receipt(payload, 'budget_exhausted', {'process_started': False})
                self._save_and_finish(receipt)
                raise BudgetStop('ALL_ATTEMPT_BUDGET_STOP')
            return None

    def _receipt(self, attempt, status, details):
        return {'schema': 'controlled-attempt-receipt-v1', 'episode_id': attempt['episode_id'],
            'attempt_id': attempt['attempt_id'], 'request_hash': attempt['request_hash'],
            'binding': self.contract['binding'], 'status': status, 'details': details,
            'provider_calls': 0, 'participant_calls': 0, 'scientific_success': False}

    def receipt_file(self, attempt_id):
        return 'receipts/' + digest(attempt_id) + '.json'

    def _save_and_finish(self, receipt, artifact_only=False):
        self.validate_receipt(receipt)
        path = self.root / self.receipt_file(receipt['attempt_id'])
        write_once(path, receipt)
        if not artifact_only:
            self.journal.append('attempt_finished', {'attempt_id': receipt['attempt_id'],
                'status': receipt['status'], 'receipt_file': self.receipt_file(receipt['attempt_id']), 'receipt_sha256': sha(path)})

    def validate_receipt(self, receipt):
        attempt = self.attempts()[receipt['attempt_id']]
        if (receipt.get('schema') != 'controlled-attempt-receipt-v1'
            or receipt.get('episode_id') != attempt['episode_id']
            or receipt.get('request_hash') != attempt['request_hash']
            or receipt.get('binding') != self.contract['binding']
            or receipt.get('status') not in TERMINAL
            or receipt.get('provider_calls') != 0 or receipt.get('participant_calls') != 0
            or receipt.get('scientific_success') is not False):
            raise ValueError('ATTEMPT_RECEIPT_BINDING_MISMATCH')
        details = receipt['details']
        if details.get('process_started'):
            if details.get('expected', {}).get('binding_hash') != digest(self.contract['binding']):
                raise ValueError('PROCESS_TARGET_BINDING_MISMATCH')
            actual = verify_process_receipt(details)
            if (receipt['status'] == 'activation_pass') != actual['activation_passed']:
                raise ValueError('ATTEMPT_ACTIVATION_STATUS_MISMATCH')
        elif receipt['status'] == 'activation_pass':
            raise ValueError('ACTIVATION_REQUIRES_ACTUAL_PROCESS')
        return receipt

    def finish(self, attempt_id, status, details, artifact_only=False):
        if status not in TERMINAL:
            raise ValueError('INVALID_STATUS')
        with self.lock():
            attempt = self.attempts()[attempt_id]
            if attempt['status'] != 'unknown':
                raise ValueError('TERMINAL_ATTEMPT_IMMUTABLE')
            receipt = self._receipt(attempt, status, details)
            self._save_and_finish(receipt, artifact_only)
            return receipt

    def recover(self, attempt_id):
        with self.lock():
            a = self.attempts()[attempt_id]
            path = self.root / self.receipt_file(attempt_id)
            if a['status'] != 'unknown':
                if sha(path) != a['receipt_sha256']:
                    raise ValueError('RECEIPT_TAMPER')
                return self.validate_receipt(read(path))
            if not path.exists():
                raise ValueError('UNKNOWN_EFFECT_REQUIRES_EXTERNAL_RECONCILIATION')
            r = read(path)
            if r['request_hash'] != a['request_hash'] or r['binding'] != self.contract['binding'] or r['attempt_id'] != attempt_id or r['episode_id'] != a['episode_id'] or r['status'] not in TERMINAL:
                raise ValueError('RECOVERY_RECEIPT_MISMATCH')
            # For process receipts, recovery independently re-reads immutable logs
            # and validates the actual receipt against recorded process identity.
            if r['details'].get('process_started'):
                verify_process_receipt(r['details'])
            self.validate_receipt(r)
            self.journal.append('attempt_finished', {'attempt_id': attempt_id, 'status': r['status'],
                'receipt_file': self.receipt_file(attempt_id), 'receipt_sha256': sha(path), 'recovered_without_process': True})
            return r

    def summary(self):
        attempts = self.attempts()
        return {'assigned_episode_count': len(self.contract['assignments']),
            'attempt_count': len(attempts), 'journal_head': self.journal.head,
            'episodes': [{'episode_id': e, 'attempt_ids': [a for a, r in attempts.items() if r['episode_id'] == e],
                'statuses': [r['status'] for r in attempts.values() if r['episode_id'] == e] or ['not_started']}
                for e in self.contract['assignments']], 'provider_calls': 0, 'participant_calls': 0,
            'denominator': 'all_assigned_episodes_including_failures_retries_and_not_started'}

@contextmanager
def fixture_service():
    requests = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({'method': 'GET', 'path': self.path})
            if self.path != '/api/budget':
                self.send_error(403)
                return
            body = json.dumps({'remaining_experiments': 0, 'fixture': True}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            requests.append({'method': 'POST', 'path': self.path})
            self.send_error(403, 'FIXTURE_HAS_NO_MODEL_OR_EXPERIMENT_ROUTE')
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port), requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

def verify_process_receipt(details):
    if sha(details['trace_file']) != details['trace_sha256'] or sha(details['stderr_file']) != details['stderr_sha256']:
        raise ValueError('PROCESS_EVIDENCE_TAMPER')
    events = [json.loads(line) for line in Path(details['trace_file']).read_text().splitlines() if line.startswith('{')]
    activation = [e for e in events if e.get('type') == 'controlled_activation']
    expected = details['expected']
    for event in activation:
        for key in ['pid', 'nonce', 'harness_source_hash', 'app_build_hash', 'loaded', 'binding_hash', 'mode']:
            if event.get(key) != expected.get(key):
                raise ValueError('PROCESS_ACTIVATION_BINDING:' + key)
        if event.get('phase') == 'invoked':
            if 'output' not in event:
                raise ValueError('INVOCATION_OUTPUT_MISSING')
            # JSON emitted by Node preserves object order. These fixed fixtures
            # contain no float-format ambiguities or unsupported JS values.
            actual = hashlib.sha256(json.dumps(event['output'], ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            if event.get('output_hash') != actual:
                raise ValueError('INVOCATION_OUTPUT_HASH_MISMATCH')
    imports = [e['entrypoint'] for e in activation if e['phase'] == 'post_import']
    invoked = [e['entrypoint'] for e in activation if e['phase'] == 'invoked']
    required = ['solver.initialState', 'solver.solverPrompt' if expected['mode'] == 'solve' else 'improver.improvementPrompt']
    for name in invoked:
        target = name.split('.')[0]
        index = next(i for i, e in enumerate(activation) if e['phase'] == 'invoked' and e['entrypoint'] == name)
        if not any(e['phase'] == 'post_import' and e['entrypoint'] == target for e in activation[:index]):
            raise ValueError('INVOCATION_WITHOUT_PRIOR_IMPORT')
    success = (details['exit_code'] == 0 and imports == ['solver', 'improver'] and invoked == required
        and type(expected['pid']) is int and expected['pid'] > 0
        and expected['pid'] != details.get('supervisor_pid')
        and len([e for e in events if e.get('type') == 'session_complete']) == 1)
    if details['activation_passed'] != success:
        raise ValueError('ACTIVATION_VERDICT_MISMATCH')
    normalized = {'harness_source_hash': expected['harness_source_hash'],
        'harness_build_hash': digest(expected['loaded']), 'controller_hash': expected['controller_hash'],
        'nonce': expected['nonce'], 'entrypoint': required[-1], 'pid': expected['pid'],
        'fresh_process': expected['pid'] != details['supervisor_pid'],
        'clean_context': details['clean_context'], 'post_import': imports == ['solver', 'improver'],
        'invoked': invoked == required, 'exit_code': details['exit_code'],
        'invocation_output_hash': digest([e['output_hash'] for e in activation if e['phase'] == 'invoked']) if invoked else None,
        'loaded_modules': expected['loaded']}
    errors = contract.activation_errors(normalized, {**normalized, 'author_pid': details['supervisor_pid']})
    if success and errors:
        raise ValueError('PROSPECTIVE_ACTIVATION_CONTRACT_REJECTED:' + ';'.join(errors))
    if details.get('activation_contract') is not None and details['activation_contract'] != normalized:
        raise ValueError('NORMALIZED_ACTIVATION_RECEIPT_DRIFT')
    return {'activation_passed': success, 'imports': imports, 'invoked': invoked,
            'activation_contract': normalized, 'prospective_contract_errors': errors}

def run_trusted_fixture(book, episode_id, attempt_id, variant='h0', mode='improve', timeout=15, artifact_only=False):
    if variant not in VARIANTS or mode not in {'solve', 'improve'}:
        raise ValueError('TRUSTED_FIXTURE_ROUTE_ONLY')
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 30:
        raise ValueError('FIXTURE_WALL_CAP_REQUIRED')
    request = {'variant': variant, 'mode': mode, 'timeout': timeout, 'binding': book.contract['binding']}
    cached = book.begin(episode_id, attempt_id, request)
    if cached is not None:
        details = cached['details']
        if details.get('process_started'):
            verify_process_receipt(details)
        return cached
    total_start = time.monotonic()
    total_parent_before = resource.getrusage(resource.RUSAGE_SELF)
    total_child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        verify_sources()
        harness = build_fixture(variant)
        manifest = verify_harness(harness, variant)
    except Exception as exc:
        after_parent = resource.getrusage(resource.RUSAGE_SELF)
        after_child = resource.getrusage(resource.RUSAGE_CHILDREN)
        return book.finish(attempt_id, 'build_failed' if 'CANDIDATE_BUILD_FAILED' in str(exc) else 'blocked',
            {'process_started': False, 'error': str(exc), 'local_cost': {
                'wall_seconds': time.monotonic() - total_start,
                'parent_cpu_seconds': after_parent.ru_utime + after_parent.ru_stime - total_parent_before.ru_utime - total_parent_before.ru_stime,
                'child_cpu_seconds': after_child.ru_utime + after_child.ru_stime - total_child_before.ru_utime - total_child_before.ru_stime,
                'scope': 'source checks plus freeze/build for this trusted attempt only', 'money': 0}})
    preparation_wall = time.monotonic() - total_start
    workspace = book.root / 'processes' / digest(attempt_id)
    workspace.mkdir(parents=True, exist_ok=False)
    (workspace / '.pi').mkdir()
    (workspace / 'home').mkdir()
    if mode == 'solve':
        write_once(workspace / 'task.json', {'task': 'TRUSTED_ACTIVATION_FIXTURE_ONLY', 'scientific_result': False})
    nonce = secrets.token_hex(24)
    loaded = {k: manifest['loaded_modules'][k] for k in ('solver', 'improver')}
    expected = {'nonce': nonce, 'harness_source_hash': manifest['source_hash'],
        'app_build_hash': manifest['app_build_hash'], 'loaded': loaded,
        'binding_hash': digest(book.contract['binding']), 'mode': mode,
        'controller_hash': sha(__file__)}
    cfg = {'workspace': str(workspace), 'token': 'NONSECRET-OFFLINE-FIXTURE', 'taskId': 'TRUSTED-FIXTURE',
        'mode': mode, 'dryRun': True, 'sourceManifest': manifest,
        'solverModule': str(harness / 'dist/solver.js'), 'improverModule': str(harness / 'dist/improver.js'),
        'improvementContext': {'fixture': True, 'history': [], 'heldout': 'not_provided'},
        'controlledActivation': {'nonce': nonce, 'harnessSourceHash': manifest['source_hash'],
            'appBuildHash': manifest['app_build_hash'], 'loaded': loaded,
            'bindingHash': expected['binding_hash']}}
    start = time.monotonic()
    child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    trace = workspace / 'trace.jsonl'
    stderr = workspace / 'stderr.log'
    command = [launcher.NODE, str(PI / 'packages/bf-agent/dist/main.js'), '-']
    timed_out = False
    with fixture_service() as (url, requests):
        cfg['service'] = url
        with trace.open('x') as stdout_file, stderr.open('x') as stderr_file:
            proc = subprocess.Popen(command, cwd=workspace, env={'PATH': os.path.dirname(launcher.NODE) + ':/usr/bin:/bin',
                'HOME': str(workspace / 'home'), 'LANG': 'C.UTF-8'}, stdin=subprocess.PIPE,
                stdout=stdout_file, stderr=stderr_file, start_new_session=True)
            expected['pid'] = proc.pid
            try:
                proc.communicate(json.dumps(cfg).encode(), timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    parent_after = resource.getrusage(resource.RUSAGE_SELF)
    events = [json.loads(line) for line in trace.read_text().splitlines() if line.startswith('{')]
    invocations = [e['entrypoint'] for e in events if e.get('type') == 'controlled_activation' and e['phase'] == 'invoked']
    imports = [e['entrypoint'] for e in events if e.get('type') == 'controlled_activation' and e['phase'] == 'post_import']
    required = ['solver.initialState', 'solver.solverPrompt' if mode == 'solve' else 'improver.improvementPrompt']
    passed = proc.returncode == 0 and imports == ['solver', 'improver'] and invocations == required and any(e.get('type') == 'session_complete' for e in events)
    status = ('timed_out' if timed_out else 'activation_pass' if passed else 'import_failed' if len(imports) < 2 else 'invocation_failed' if invocations != required else 'process_failed')
    details = {'process_started': True, 'activation_passed': passed, 'expected': expected,
        'supervisor_pid': os.getpid(), 'clean_context': True,
        'clean_context_evidence': {'fresh_workspace_required': True, 'fresh_home_required': True,
            'session_manager': 'existing Pi SessionManager.inMemory', 'resources': 'existing explicit-empty ResourceLoader',
            'child_environment_keys': ['HOME', 'LANG', 'PATH'], 'auth_directory_initially_empty': True},
        'harness_path': str(harness), 'manifest_sha256': sha(harness / 'manifest.json'),
        'trace_file': str(trace), 'trace_sha256': sha(trace), 'stderr_file': str(stderr), 'stderr_sha256': sha(stderr),
        'exit_code': proc.returncode, 'command': command, 'fresh_workspace': str(workspace),
        'wall_seconds': time.monotonic() - start,
        'child_cpu_seconds': (after.ru_utime + after.ru_stime) - (child_before.ru_utime + child_before.ru_stime),
        'cost_scope': 'fresh process and local fixture service only; excludes source checks and freeze/build, not complete H-loop cost',
        'attempt_local_cost': {'wall_seconds': time.monotonic() - total_start,
            'preparation_wall_seconds': preparation_wall,
            'parent_cpu_seconds': parent_after.ru_utime + parent_after.ru_stime - total_parent_before.ru_utime - total_parent_before.ru_stime,
            'child_cpu_seconds': after.ru_utime + after.ru_stime - total_child_before.ru_utime - total_child_before.ru_stime,
            'scope': 'this trusted adapter attempt including source checks and freeze/build; not historical or complete H-loop costs', 'money': 0},
        'provider_calls': 0, 'model_prompt_called': False, 'service_requests': requests,
        'trusted_only': True, 'participant_isolation_qualified': False,
        'interpretation': 'Pi import and harness function activation only; no participant solve, authored H1, or scientific success'}
    activation = verify_process_receipt(details)
    details['activation_contract'] = activation['activation_contract']
    details['prospective_contract_errors'] = activation['prospective_contract_errors']
    return book.finish(attempt_id, status, details, artifact_only)

def rollback_h0(h0, current, receipt):
    a = verify_harness(h0, 'h0')
    b = verify_harness(current, 'h1-manual-fixture')
    recursive.compatible(a, b)
    details = receipt['details']
    checked = verify_process_receipt(details)
    if not checked['activation_passed'] or details['expected']['harness_source_hash'] != a['source_hash'] or details['harness_path'] != str(h0):
        raise ValueError('ROLLBACK_REQUIRES_ACTUAL_H0_INVOCATION')
    return {'selected_harness_identity': a['identity'], 'from_identity': b['identity'],
        'exact_h0_restored': True, 'activation_receipt_hash': digest(receipt),
        'generation_created': False, 'fixture_only': True}

def validate_lineage(records, root_hash, task_registry, exposed_hashes, receipt_reader):
    errors = contract.lineage_errors(records, root_hash)
    if errors:
        raise ValueError(';'.join(errors))
    splits.validate_registry(task_registry, exposed_hashes=exposed_hashes)
    for row in records:
        parent_receipt = receipt_reader(row['generator_invocation_receipt_hash'])
        if digest(parent_receipt) != row['generator_invocation_receipt_hash']:
            raise ValueError('GENERATOR_RECEIPT_DIGEST_MISMATCH')
        if parent_receipt.get('fixture_only') or parent_receipt.get('participant_execution') is not True:
            raise ValueError('FIXTURE_CANNOT_ESTABLISH_PARTICIPANT_LINEAGE')
        if parent_receipt.get('activated_harness_hash') != row['parent_hash'] or parent_receipt.get('post_import') is not True or parent_receipt.get('invoked') is not True:
            raise ValueError('ACTUAL_PARENT_INVOCATION_REQUIRED')
        if parent_receipt.get('hidden_feedback_exposed') is not False:
            raise ValueError('HELDOUT_FEEDBACK_EXPOSURE')
    return {'lineage_consistent': True, 'promotion_granted': False,
            'participant_authorship_independently_verified': False}

def live_readiness():
    """Read-only. Does not call launch(), Store.grant(), Store.issue(), or a key API."""
    verify_sources()
    plan = read(PROTOCOL / 'protocol-world-bound-draft.json')
    result = contract.check_plan(plan)
    tasks = read(WORLD / 'contracts/tasks-v2.json')['tasks']
    blockers = list(result['blockers'])
    if not Path('/usr/bin/sandbox-exec').is_file():
        blockers.append('ACTUAL_HOST_SEATBELT_UNAVAILABLE')
    qualified = sum(t.get('formal_trials_authorized') is True and all(t['qualification'].values()) for t in tasks)
    if qualified != len(tasks):
        blockers.append('QUALIFIED_DEVELOPMENT_TASKS:' + str(qualified) + '/' + str(len(tasks)))
    # Existing launcher has old finite dev-01/dev-02 task routes and literal
    # model/request limits. Never silently map the new magnetic task to those.
    blockers += ['MAGNETIC_TASK_NOT_REGISTERED_IN_LEGACY_EXPERIMENT_SERVICE',
                 'LEGACY_MODEL_AND_CAPS_NOT_NEW_PROTOCOL_AUTHORIZATION',
                 'TRUSTED_OVERLAY_NOT_PARTICIPANT_ISOLATION']
    return {'schema': 'controlled-launch-readiness-v1', 'live_launch_allowed': False,
        'blockers': sorted(set(blockers)), 'binding': current_binding(),
        'qualified_tasks': qualified, 'total_tasks': len(tasks),
        'provider_calls': 0, 'participant_calls': 0, 'credential_accesses': 0}

def launch_participant(*args, **kwargs):
    readiness = live_readiness()
    # Intentionally no callable injection or force flag. Launch integration is
    # stopped before the old launcher would grant capabilities or issue tokens.
    raise RuntimeError('CONTROLLED_LAUNCH_BLOCKED:' + ';'.join(readiness['blockers']))

def prepare_native_handoff(candidate, model, tools, task_name='DEV-FEASIBLE-01'):
    verify_sources()
    request = handoff.prepare_request(candidate, model, tools, task_name=task_name)
    if request['identity']['world_id'] != current_binding()['world_id']:
        raise ValueError('WORLD_IDENTITY_MISMATCH')
    return {'request': request, 'evaluator_binding': current_binding(), 'native_execution': False}
