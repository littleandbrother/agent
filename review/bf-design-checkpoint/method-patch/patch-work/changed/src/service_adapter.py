"""Registry-backed service hooks. All execution routes remain fail-closed.

This uses the existing HTTP handler but not Workbench.__init__, Provider,
Store's automatic grants, or the legacy worker. No production credentials exist
in this service. The fixed bearer below is explicitly nonsecret fixture data.
"""
from __future__ import annotations
from contextlib import contextmanager
import copy
import fcntl
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

from paths import ROOT, PI, WORLD, PROTOCOL, EVALUATOR, sha, read, canonical, digest, write_once, module, verify_inputs
from bfworld.runtime.journal import HashJournal
from method_contract import bind_method, capability_admission

handoff = module('magnetic_existing_handoff', WORLD / 'pipeline-handoff-v2/prepare_request.py')
contract = module('magnetic_prospective_contract', PROTOCOL / 'preflight.py')
server = module('bfworld.agentlab.controlled_server_overlay', ROOT / 'src/server_overlay.py')
FIXTURE_BEARER = 'NONSECRET-LOCAL-TRUSTED-PROBE-ONLY'
FIXTURE_OWNER = 'trusted-probe'

def fixture_settings():
    return {'schema': 'explicit-offline-runtime-profile-v1',
        'provenance': 'fictional-offline-SDK-initialization-only',
        'authorized_task_ids': ['DEV-FEASIBLE-01'],
        'model': {'provider': 'bf-offline-fixture', 'model_id': 'offline-no-call-model',
            'revision': 'fictional-fixture-v1', 'fingerprint': 'fictional-not-a-provider-fingerprint',
            'reasoning': False, 'vision': False, 'temperature': 0, 'seed_policy': 'not-sampled',
            'context_tokens': 32000, 'max_output_tokens': 256,
            'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}},
        'budget': {'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0,
            'solver_calls': 0, 'verifier_calls': 0, 'candidate_branches': 2,
            'wall_seconds': 15, 'local_cpu_seconds': 10, 'money': 0, 'currency': 'USD'},
        'local_probe_caps': {'max_snapshots': 2, 'max_job_intents': 2},
        'native_tools': {}, 'native_identity_status': 'absent_not_substituted',
        'model_dispatch_allowed': False, 'native_dispatch_allowed': False}

class FixturePrincipal:
    def authenticate(self, token):
        if token != FIXTURE_BEARER:
            raise PermissionError('FIXTURE_AUTH_REQUIRED')
        return {'owner': FIXTURE_OWNER, 'role': 'participant'}

class RegistryService:
    def __init__(self, root, settings_path, *, method_id):
        verify_inputs()
        self.root = Path(root).resolve()
        if not self.root.is_relative_to(ROOT):
            raise ValueError('OWNED_OUTPUT_ROOT_REQUIRED')
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings_path = Path(settings_path).resolve()
        self.method_binding = bind_method(PI, method_id)
        self.inputs = {str(WORLD / 'contracts/tasks-v2.json'): sha(WORLD / 'contracts/tasks-v2.json'),
            str(PROTOCOL / 'protocol-world-bound-draft.json'): sha(PROTOCOL / 'protocol-world-bound-draft.json'),
            str(EVALUATOR): sha(EVALUATOR), str(self.settings_path): sha(self.settings_path),
            str(Path(__file__).resolve()): sha(__file__),
            str(ROOT / 'src/paths.py'): sha(ROOT / 'src/paths.py'),
            str(ROOT / 'src/method_contract.py'): sha(ROOT / 'src/method_contract.py'),
            **{str(PI / 'packages/bf-harness' / p): sha(PI / 'packages/bf-harness' / p) for p in
                ('src/method.ts', 'dist/method.js', 'src/solver.ts', 'dist/solver.js')},
            str(ROOT / 'src/server_overlay.py'): sha(ROOT / 'src/server_overlay.py')}
        self.registry = read(WORLD / 'contracts/tasks-v2.json')
        self.plan = read(PROTOCOL / 'protocol-world-bound-draft.json')
        self.profile = read(self.settings_path)
        if self.profile != fixture_settings():
            raise ValueError('UNREVIEWED_RUNTIME_PROFILE_NOT_AUTHORIZATION')
        self.tasks = {task['task_id']: task for task in self.registry['tasks']}
        if self.plan['task_manifest_hash'] != sha(WORLD / 'contracts/tasks-v2.json') or self.registry['world_id'] != self.plan['world_id']:
            raise ValueError('REGISTRY_PROTOCOL_WORLD_BINDING_MISMATCH')
        self.identity = digest({'inputs': self.inputs, 'adapter': sha(__file__), 'server': sha(ROOT / 'src/server_overlay.py')})
        self.journal = HashJournal(self.root / 'events.jsonl', self.identity)
        with self.lock():
            if not self.journal.read():
                self.journal.append('service_bound', {'identity': self.identity, 'inputs': self.inputs,
                    'provider_attached': False, 'legacy_store_instantiated': False, 'legacy_worker_started': False})

    @contextmanager
    def lock(self):
        with (self.root / 'service-adapter.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def fresh(self):
        if any(not Path(path).is_file() or sha(path) != expected for path, expected in self.inputs.items()):
            raise ValueError('STALE_REGISTRY_MODEL_BUDGET_OR_EVALUATOR')

    def owner(self, owner):
        if owner != FIXTURE_OWNER:
            raise PermissionError('NO_PRODUCTION_OR_OPERATOR_GRANT')

    def packet(self, task_id):
        self.fresh()
        if task_id not in self.tasks:
            raise ValueError('TASK_NOT_IN_SOURCE_BOUND_MAGNETIC_REGISTRY')
        if task_id not in self.profile['authorized_task_ids']:
            raise PermissionError('TASK_NOT_IN_EXPLICIT_OFFLINE_ASSIGNMENT')
        task = self.tasks[task_id]
        result = {'schema': 'magnetic-execution-packet-v1', 'scope': 'trusted-offline-protocol-probe',
            'task_id': task_id, 'task_contract_hash': handoff.aw.task_id(task),
            'task_registry_sha256': self.inputs[str(WORLD / 'contracts/tasks-v2.json')],
            'world_id': self.registry['world_id'], 'world_input_id': task['world']['input_id'],
            'evaluator_sha256': self.inputs[str(EVALUATOR)],
            'protocol_sha256': self.inputs[str(PROTOCOL / 'protocol-world-bound-draft.json')],
            'runtime_profile_sha256': self.inputs[str(self.settings_path)],
            'runtime_profile': copy.deepcopy(self.profile), 'approved_model': self.plan['model'],
            'approved_budget': self.plan['per_episode_budget'], 'approval': self.plan['approval'],
            'execution_authorized': False, 'model_dispatch_allowed': False, 'native_dispatch_allowed': False,
            'service_identity': self.identity, 'method_binding': self.method_binding,
            'capability_admission': capability_admission(task)}
        result['packet_id'] = digest(result)
        return result

    def bind(self, owner, body, task_id=None):
        self.owner(owner)
        packet = self.packet(task_id or 'DEV-FEASIBLE-01')
        if body.get('execution_packet_id') != packet['packet_id']:
            raise ValueError('EXECUTION_PACKET_IDENTITY_MISMATCH')
        return packet

    @contextmanager
    def request(self, route, owner, body):
        with self.lock():
            try:
                self.owner(owner)
                self.fresh()
                yield
            except Exception as exc:
                self.journal.append('request_rejected', {'route': route, 'owner': owner,
                    'request_hash': digest(body), 'error': str(exc), 'no_native_or_provider_dispatch': True})
                raise

    def public_task(self, owner, task_id):
        with self.request('/api/tasks', owner, {'task_id': task_id}):
            packet = self.packet(task_id)
            result = {'task_id': task_id, 'binding': {k: packet[k] for k in
                ('world_id', 'world_input_id', 'task_contract_hash', 'task_registry_sha256', 'evaluator_sha256')},
                'task': copy.deepcopy(self.tasks[task_id]), 'execution_packet_id': packet['packet_id'],
                'execution_contract': {'runtime_profile': packet['runtime_profile'], 'method_binding': packet['method_binding'],
                    'capability_admission': packet['capability_admission'], 'approved_model': None,
                    'approved_budget': None, 'execution_authorized': False}}
            self.journal.append('task_read', {'task_id': task_id, 'packet_id': packet['packet_id'], 'binding': result['binding']})
            return result

    def budget(self, owner):
        with self.request('/api/budget', owner, {}):
            packet = self.packet('DEV-FEASIBLE-01')
            self.journal.append('budget_read', {'packet_id': packet['packet_id']})
            return {'authority': 'explicit-offline-execution-packet', 'execution_packet_id': packet['packet_id'],
                'remaining_experiments': packet['runtime_profile']['budget']['solver_calls'],
                'model_calls': 0, 'budget': packet['runtime_profile']['budget'],
                'approved_budget': packet['approved_budget'], 'requests': [], 'execution_authorized': False}

    def checkpoint(self, label):
        """Fault-injection seam for local unit tests; never accepts external code."""

    def snapshot(self, owner, body):
        with self.request('/api/snapshots', owner, body):
            packet = self.bind(owner, body)
            if set(body) != {'files', 'execution_packet_id'} or set(body['files']) != {'candidate.json'}:
                raise ValueError('EXACT_MAGNETIC_CANDIDATE_FILE_REQUIRED')
            if not isinstance(body['files']['candidate.json'], str) or len(body['files']['candidate.json'].encode()) > 100000:
                raise ValueError('CANDIDATE_SIZE')
            import json
            source = json.loads(body['files']['candidate.json'])
            candidate = handoff.aw.migrate_upstream_spec(source, 'upstream-338d603')
            world = handoff.aw.load_world()
            if candidate['mechanical']['opening_s'] != world['input']['opening_s'] or candidate['mechanical']['angle_deg'] != 65:
                raise ValueError('FROZEN_INPUT_CHANGED')
            if candidate['circuit']['initial_vin_V'] != 0 or candidate['circuit']['diagnostic_input_A'] != 0:
                raise ValueError('EXTERNAL_OR_INITIAL_ENERGY_NOT_ALLOWED')
            sid = digest({'owner': owner, 'packet_id': packet['packet_id'], 'files': body['files']})
            path = self.root / 'snapshots' / sid / 'receipt.json'
            intent = {'snapshot_id': sid, 'owner': owner, 'packet_id': packet['packet_id'],
                'request_hash': digest(body), 'file_hash': digest(body['files'])}
            rows = self.journal.read()
            old = [r['payload'] for r in rows if r['type'] == 'snapshot_intent' and r['payload']['snapshot_id'] == sid]
            if not old:
                count = sum(r['type'] == 'snapshot_intent' for r in rows)
                if count >= self.profile['local_probe_caps']['max_snapshots']:
                    raise ValueError('SNAPSHOT_BUDGET_STOP')
                self.journal.append('snapshot_intent', intent)
            elif old != [intent]:
                raise ValueError('SNAPSHOT_IDENTITY_CONFLICT')
            receipt = {**intent, 'candidate': candidate, 'candidate_design_hash': digest(handoff.aw.scientific_design(candidate)),
                'uploaded_files': copy.deepcopy(body['files']),
                'binding': {k: packet[k] for k in ('world_id', 'task_contract_hash', 'evaluator_sha256')},
                'execution_authorized': False}
            self.checkpoint('snapshot_after_intent')
            if path.exists():
                if read(path) != receipt:
                    raise ValueError('SNAPSHOT_RECEIPT_TAMPER')
            else:
                write_once(path, receipt)
            self.checkpoint('snapshot_after_artifact')
            complete = [r for r in self.journal.read() if r['type'] == 'snapshot_complete' and r['payload']['snapshot_id'] == sid]
            if not complete:
                self.journal.append('snapshot_complete', {'snapshot_id': sid, 'receipt_sha256': sha(path), 'packet_id': packet['packet_id']})
            elif complete[0]['payload']['receipt_sha256'] != sha(path):
                raise ValueError('SNAPSHOT_RECEIPT_TAMPER')
            return {'snapshot_id': sid, 'execution_packet_id': packet['packet_id'], 'candidate_design_hash': receipt['candidate_design_hash']}

    def job(self, owner, body):
        with self.request('/api/jobs', owner, body):
            if set(body) != {'task_id', 'snapshot_id', 'operation_id', 'execution_packet_id'}:
                raise ValueError('EXACT_JOB_FIELDS_REQUIRED')
            packet = self.bind(owner, body, body['task_id'])
            operation = body['operation_id']
            if not isinstance(operation, str) or not 1 <= len(operation) <= 100:
                raise ValueError('OPERATION_ID_REQUIRED')
            sid = body['snapshot_id']
            if not contract.hash_ok(sid):
                raise ValueError('SNAPSHOT_ID_INVALID')
            path = self.root / 'snapshots' / sid / 'receipt.json'
            completed = [r['payload'] for r in self.journal.read() if r['type'] == 'snapshot_complete' and r['payload']['snapshot_id'] == sid]
            if len(completed) != 1 or not path.is_file() or sha(path) != completed[0]['receipt_sha256']:
                raise ValueError('UPLOAD_NOT_DURABLY_COMPLETED')
            snapshot = read(path)
            if snapshot['owner'] != owner or snapshot['packet_id'] != packet['packet_id']:
                raise ValueError('SNAPSHOT_OWNER_OR_PACKET_MISMATCH')
            import json
            source_files = snapshot.get('uploaded_files')
            if (not isinstance(source_files, dict) or set(source_files) != {'candidate.json'}
                or digest(source_files) != snapshot['file_hash']
                or digest({'owner': owner, 'packet_id': packet['packet_id'], 'files': source_files}) != sid
                or handoff.aw.migrate_upstream_spec(json.loads(source_files['candidate.json']), 'upstream-338d603') != snapshot['candidate']):
                raise ValueError('UPLOADED_SOURCE_TO_CANDIDATE_BINDING_MISMATCH')
            jid = 'job-' + digest({'owner': owner, 'operation': operation})
            intent = {'id': jid, 'owner': owner, 'operation': operation, 'request_hash': digest(body), 'request': body}
            rows = self.journal.read()
            old = [r['payload'] for r in rows if r['type'] == 'job_intent' and r['payload']['id'] == jid]
            if not old:
                if sum(r['type'] == 'job_intent' for r in rows) >= self.profile['local_probe_caps']['max_job_intents']:
                    raise ValueError('JOB_ATTEMPT_BUDGET_STOP')
                self.journal.append('job_intent', intent)
            elif old != [intent]:
                raise ValueError('DUPLICATE_OPERATION_IDENTITY_CONFLICT')
            self.checkpoint('job_after_intent')
            blockers = contract.check_plan(self.plan)['blockers']
            blockers += packet['capability_admission']['blockers']
            task = self.tasks[body['task_id']]
            if not all(task['qualification'].values()):
                blockers += ['TASK_QUALIFICATION_NOT_PASSED']
            blockers += ['TRUSTED_OFFLINE_SCOPE_NO_EXECUTION', 'ACTUAL_HOST_PARTICIPANT_ISOLATION_UNQUALIFIED']
            model = {'model_version': 'source-declared-native-model-not-qualified',
                'world_provider': handoff.aw.load_world()['circuit']['model'],
                'applicability': 'unqualified_native_contract_only', 'physical_qualified': False,
                'source_hashes': handoff.aw.load_world()['source_bindings']}
            try:
                # No native import. Missing actual identities are passed as absent,
                # so the real handoff refuses before kwargs or native dispatch.
                handoff.prepare_request(snapshot['candidate'], model, self.profile['native_tools'], task_name=body['task_id'])
                raise AssertionError('ABSENT_NATIVE_IDENTITIES_MUST_NOT_PREPARE')
            except handoff.aw.ContractError as exc:
                native_blocker = str(exc)
            result = {**intent, 'status': 'BLOCKED', 'result': None, 'snapshot_id': sid,
                'binding': snapshot['binding'], 'execution_packet_id': packet['packet_id'],
                'native_tool_identities': self.profile['native_tools'], 'native_prepare_error': native_blocker,
                'blockers': sorted(set(blockers)), 'model_calls': 0, 'native_solver_calls': 0,
                'autonomous_participant': False, 'scientific_success': False}
            output = self.root / 'jobs' / (jid + '.json')
            if output.exists():
                if read(output) != result:
                    raise ValueError('JOB_RECEIPT_TAMPER')
            else:
                write_once(output, result)
            self.checkpoint('job_after_artifact')
            terminal = [r['payload'] for r in self.journal.read() if r['type'] == 'job_blocked' and r['payload']['id'] == jid]
            if not terminal:
                self.journal.append('job_blocked', {'id': jid, 'receipt_sha256': sha(output), 'execution_packet_id': packet['packet_id'], 'native_solver_calls': 0})
            elif terminal[0]['receipt_sha256'] != sha(output):
                raise ValueError('JOB_RECEIPT_TAMPER')
            return result

    def denied(self, owner, route, body):
        with self.request(route, owner, body):
            self.journal.append('dispatch_denied', {'route': route, 'request_hash': digest(body),
                'provider_attached': False, 'native_dispatch': False})
            return {'error': 'EXPLICIT_EXECUTION_AUTHORIZATION_AND_QUALIFICATION_REQUIRED',
                'model_calls': 0, 'native_solver_calls': 0, 'execution_authorized': False}

    @contextmanager
    def serve(self):
        workbench = SimpleNamespace(controlled=self, store=FixturePrincipal())
        http = ThreadingHTTPServer(('127.0.0.1', 0), server.handler(workbench))
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            yield 'http://127.0.0.1:' + str(http.server_port)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()
