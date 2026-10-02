"""Pure method layer over an injected bf_engineering tool; no HTTP or providers.

The local coordinator owns authentication, dispatch authorization and backend
reservation/evaluation. The append-only local ledger is conservative bookkeeping,
not a security boundary against a writer who can replace it and its hashes.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'SUCCEEDED', 'FAILED'}
STATES = TERMINAL | {'QUEUED', 'RUNNING', 'UNKNOWN'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Rejected(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Rejected(message)


def load_protocol():
    value = json.loads((ROOT / 'contracts/PROTOCOL.json').read_text())
    require(value['protocol_hash'] == digest({k: v for k, v in value.items() if k != 'protocol_hash'}), 'PROTOCOL_HASH')
    require(value['max_new_candidates_per_owner'] == 3 and value['task_id'] == 'door-event-nominal-v1', 'PROTOCOL_SCOPE')
    return value


def verify_publication(repo):
    mapping = json.loads((ROOT / 'contracts/MIGRATION.json').read_text())
    for name, expected in mapping['inspected_source_sha256'].items():
        require(file_hash(Path(repo) / name) == expected, 'PUBLICATION_SOURCE_DRIFT:' + name)
    return mapping['baseline']


def normalize_candidate(candidate, task):
    require(isinstance(candidate, dict), 'CANDIDATE_OBJECT')
    baseline = task['baseline']
    require(not set(candidate) - set(baseline), 'CANDIDATE_FIELDS')
    require(candidate.get('schema_version', baseline['schema_version']) == baseline['schema_version'], 'CANDIDATE_SCHEMA')
    result = copy.deepcopy(baseline)
    for group, values in candidate.items():
        if group == 'schema_version':
            continue
        require(isinstance(values, dict) and not set(values) - set(baseline[group]), 'CANDIDATE_FIELDS')
        for key, value in values.items():
            require(type(value) in (int, float) and math.isfinite(value), 'CANDIDATE_NUMBER')
            rule = task['allowed_design_variables'].get(group + '.' + key)
            if rule is None:
                require(value == baseline[group][key], 'PROTECTED_FIELD')
            elif 'values' in rule:
                require(value in rule['values'], 'DESIGN_VALUE')
            else:
                require(rule['range'][0] <= value <= rule['range'][1], 'DESIGN_RANGE')
            result[group][key] = value
    return result


def method_prompt(protocol, profile_id, task, observations):
    profiles = {p['id']: p for p in protocol['profiles']}
    require(profile_id in profiles, 'METHOD_PROFILE')
    profile = profiles[profile_id]
    shared = {'task': copy.deepcopy(task), 'observations': copy.deepcopy(observations), 'max_new_candidates': 3,
              'architecture_changes': False, 'artifact_source_changes': False,
              'actions': ['inspect', 'skill', 'run', 'job', 'artifact_view', 'submit']}
    policy = ['Use the same frozen nominal task, public evidence and numeric freedoms. '
              'Preserve failed and non-evaluable outcomes. Submit an existing evaluated job; '
              'the backend owns costs, quotas and acceptance. Never broaden the task or claim physical ranking.']
    if profile['R']:
        policy.append('Represent functional requirements, resource constraints and operating conditions as explicit relations; '
                      'bind each relation to observed job/artifact evidence or label it an unverified hypothesis.')
    if profile['Q']:
        policy.append('Attribute the observed conflict before revising numeric parameters; state the predicted change and falsifier. '
                      'Architecture recomposition is unsupported here: record the limitation, never silently substitute numeric tuning.')
    return {'profile': copy.deepcopy(profile), 'shared': shared, 'shared_hash': digest(shared), 'policy': policy,
            'text': canonical(shared) + '\n' + '\n'.join(policy)}


class Ledger:
    """One exclusive writer per local ledger, with hash-linked durable events."""
    def __init__(self, directory, identity):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = self.directory / 'writer.lock'
        self.fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        self.path = self.directory / 'events.jsonl'
        self.events = []
        try:
            if self.path.exists():
                raw = self.path.read_text()
                require(not raw or raw.endswith('\n'), 'PARTIAL_LEDGER')
                for line in raw.splitlines():
                    row = json.loads(line)
                    expected = digest({k: v for k, v in row.items() if k != 'hash'})
                    require(row['hash'] == expected and row['seq'] == len(self.events)
                            and row['previous'] == (self.events[-1]['hash'] if self.events else None), 'LEDGER_HASH')
                    self.events.append(row)
            if self.events:
                require(self.events[0]['kind'] == 'identity' and self.events[0]['data'] == identity, 'LEDGER_IDENTITY')
            else:
                self.append('identity', identity)
        except BaseException:
            self.close()
            raise

    def append(self, kind, data):
        row = {'seq': len(self.events), 'previous': self.events[-1]['hash'] if self.events else None,
               'kind': kind, 'data': copy.deepcopy(data)}
        row['hash'] = digest(row)
        with self.path.open('a') as stream:
            stream.write(canonical(row) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        self.events.append(row)
        return row

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
            self.lock.unlink()


class Adapter:
    def __init__(self, owner, profile, tool, ledger_dir, *, evidence_kind='offline_fixture'):
        require(isinstance(owner, str) and bool(owner), 'OWNER_REQUIRED')
        require(evidence_kind in {'offline_fixture', 'local_coordinator_transport'}, 'EVIDENCE_KIND')
        self.protocol = load_protocol()
        verify_publication(ROOT.parents[1])
        require(profile in {p['id'] for p in self.protocol['profiles']}, 'METHOD_PROFILE')
        self.owner, self.profile, self.tool = owner, profile, tool
        self.mutex = threading.RLock()
        self.identity = {'owner': owner, 'profile': profile, 'protocol_hash': self.protocol['protocol_hash'],
                         'adapter_sha256': file_hash(__file__), 'evidence_kind': evidence_kind}
        self.ledger = Ledger(ledger_dir, self.identity)
        self.operations, self.observations, self.submission, self.pending_submission = {}, [], None, None
        for row in self.ledger.events:
            self._reduce(row)
        try:
            catalog = self._call({'action': 'inspect'})
            self._task = self._binding(catalog.get('task_binding'))['task']
            jobs = catalog.get('jobs')
            require(isinstance(jobs, list), 'INSPECT_JOBS')
            for job in jobs:
                require(job.get('owner') == owner and job.get('operation') in self.operations, 'UNACCOUNTED_OWNER_JOB')
                self._job(job, job['operation'])
        except BaseException:
            self.close()
            raise

    def close(self):
        self.ledger.close()

    @property
    def task(self):
        return copy.deepcopy(self._task)

    def _binding(self, value):
        require(isinstance(value, dict) and value.get('owner') == self.owner, 'TASK_OWNER')
        require(type(value.get('max_candidates')) is int and value['max_candidates'] == 3, 'TASK_QUOTA')
        trusted = json.loads((ROOT / 'contracts/MIGRATION.json').read_text())['normalized_main_task']
        require(digest(trusted) == self.protocol['normalized_task_hash']
                and value.get('task_hash') == self.protocol['normalized_task_hash'], 'TASK_IDENTITY')
        # The server hashes Python-normalized JSON; JavaScript loses integral
        # float spelling. Compare every field against the hash-bound template,
        # allowing only equal finite numeric values (never booleans), then use
        # the trusted server representation. Do not rehash lossy wire spelling.
        def matches(wire, expected):
            if type(expected) in (int, float):
                return type(wire) in (int, float) and math.isfinite(wire) and wire == expected
            if isinstance(expected, dict):
                return isinstance(wire, dict) and wire.keys() == expected.keys() and all(matches(wire[k], v) for k, v in expected.items())
            if isinstance(expected, list):
                return isinstance(wire, list) and len(wire) == len(expected) and all(matches(a, b) for a, b in zip(wire, expected))
            return type(wire) is type(expected) and wire == expected
        require(matches(value.get('task'), trusted), 'TASK_IDENTITY')
        require(trusted['id'] == self.protocol['task_id'], 'TASK_ID')
        return {**copy.deepcopy(value), 'task': trusted}

    def _reduce(self, row):
        d = copy.deepcopy(row['data'])
        if row['kind'] == 'reserved':
            self.operations[d['operation_id']] = {**d, 'status': 'RESERVED', 'job_id': None}
        elif row['kind'] == 'job':
            self.operations[d['operation_id']].update(status=d['job']['status'], job_id=d['job']['id'], job=d['job'])
        elif row['kind'] == 'observation':
            self.observations.append(d)
        elif row['kind'] == 'submitted':
            self.submission = d
        elif row['kind'] == 'submission_intent':
            self.pending_submission = d

    def _record(self, kind, data):
        row = self.ledger.append(kind, data)
        self._reduce(row)
        return copy.deepcopy(row)

    def _call(self, args):
        require(args['action'] in {'inspect', 'skill', 'run', 'job', 'artifact_view', 'submit'}, 'ACTION_NOT_ALLOWED')
        intent = self._record('action_intent', {'tool': 'bf_engineering', 'arguments': args})
        try:
            result = self.tool(copy.deepcopy(args))
            require(isinstance(result, dict), 'TOOL_RESULT_OBJECT')
            require(result.get('isError') is not True, 'TRANSPORT_REPORTED_ERROR')
            if isinstance(result.get('content'), list):
                blocks = result['content']
                require(len(blocks) == 1 and blocks[0].get('type') == 'text', 'TOOL_REPLY_FORMAT')
                result = json.loads(blocks[0]['text'])
            require(isinstance(result, dict) and 'error' not in result, 'TOOL_ERROR')
            if 'record_file' in result:
                self._record('transport_summary', {'intent_hash': intent['hash'],
                    'summary': result, 'summary_hash': digest(result), 'record_file_read': False})
                raise Rejected('TOOL_SUMMARY_ENVELOPE_REQUIRES_LOCAL_TRANSPORT_BRIDGE')
            self._record('action_result', {'intent_hash': intent['hash'], 'response': result, 'response_hash': digest(result)})
            return result
        except Exception as exc:
            self._record('action_error', {'intent_hash': intent['hash'], 'error_type': type(exc).__name__})
            raise

    def activate(self):
        with self.mutex:
            value = method_prompt(self.protocol, self.profile, self.task, self.observations)
            self._record('method_activation', {'function': 'method_prompt', 'profile': self.profile,
                'adapter_sha256': self.identity['adapter_sha256'], 'shared_hash': value['shared_hash'],
                'output_hash': digest(value), 'scope': 'actual Python prompt invocation; not SDK delivery or scientific efficacy'})
            return value

    def read_skill(self):
        with self.mutex:
            value = self._call({'action': 'skill', 'skill_id': 'closed-simulation'})
            require(isinstance(value.get('content'), str) and file_bytes_hash(value['content'].encode()) == value.get('sha256'), 'SKILL_HASH')
            return value

    def run_candidate(self, operation_id, candidate, *, rationale, falsifier, revision_kind='numeric'):
        with self.mutex:
            require(self.submission is None and self.pending_submission is None, 'ALREADY_SUBMITTED_OR_UNCERTAIN')
            require(revision_kind == 'numeric', 'ARCHITECTURE_UNSUPPORTED')
            require(isinstance(operation_id, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', operation_id), 'OPERATION_ID')
            require(isinstance(rationale, str) and bool(rationale) and isinstance(falsifier, str) and bool(falsifier), 'REVISION_REASON')
            spec = normalize_candidate(candidate, self.task)
            existing = self.operations.get(operation_id)
            if existing:
                require(existing['candidate'] == spec, 'OPERATION_CONFLICT')
                if existing['job_id']:
                    return self.poll(operation_id)
            else:
                require(len(self.operations) < 3, 'LOCAL_CANDIDATE_QUOTA')
                require(all(o['status'] in TERMINAL for o in self.operations.values()), 'PENDING_OR_UNKNOWN_EFFECT')
                self._binding(self._call({'action': 'inspect'}).get('task_binding'))
                self._record('reserved', {'operation_id': operation_id, 'candidate': spec, 'candidate_hash': digest(spec),
                    'rationale': rationale, 'falsifier': falsifier, 'revision_kind': revision_kind,
                    'observation_hashes': [digest(o) for o in self.observations], 'backend_authority': False})
            self.activate()
            return self._job(self._call({'action': 'run', 'engine': 'closed-simulation', 'operation_id': operation_id,
                              'parameters': {'candidate': spec, 'confirmation': True}}), operation_id)

    def _job(self, job, operation_id):
        op = self.operations[operation_id]
        require(job.get('owner') == self.owner and job.get('operation') == operation_id, 'JOB_OWNER_OPERATION')
        require(isinstance(job.get('id'), str) and re.fullmatch(r'eng-[a-f0-9]+', job['id']), 'JOB_ID')
        require(op['job_id'] in (None, job['id']), 'JOB_ID_DRIFT')
        require(job.get('engine') == 'closed-simulation' and job.get('parameters') == {'candidate': op['candidate'], 'confirmation': True}, 'JOB_CANDIDATE')
        self._binding(job.get('task_binding'))
        require(job.get('status') in STATES, 'JOB_STATUS')
        if op['status'] in TERMINAL:
            require(job == op['job'], 'TERMINAL_JOB_CHANGED')
        return self._record('job', {'operation_id': operation_id, 'job': job})['data']['job']

    def poll(self, operation_id):
        with self.mutex:
            op = self.operations[operation_id]
            require(op['job_id'] is not None, 'RETRY_SAME_OPERATION_TO_RECONCILE')
            return self._job(self._call({'action': 'job', 'job_id': op['job_id']}), operation_id)

    def read_artifact(self, operation_id, name, *, max_bytes=2_000_000):
        with self.mutex:
            require(name in {'result.json', 'design-spec.json', 'receiver.json', 'task-evaluation.json'}, 'ARTIFACT_NOT_DECLARED')
            job = self.poll(operation_id)
            require(job['status'] in TERMINAL, 'JOB_NOT_FINAL')
            entries = [a for a in (job.get('result') or {}).get('artifacts', []) if a.get('name') == name]
            require(len(entries) == 1, 'ARTIFACT_MANIFEST')
            entry = entries[0]
            require(type(entry.get('bytes')) is int and 0 <= entry['bytes'] <= max_bytes, 'ARTIFACT_SIZE')
            offset, chunks = 0, []
            while True:
                page = self._call({'action': 'artifact_view', 'job_id': job['id'], 'artifact_name': name, 'offset': offset, 'limit': 12000})
                require(page.get('sha256') == entry['sha256'] and page.get('offset') == offset and isinstance(page.get('content'), str), 'ARTIFACT_PAGE_BINDING')
                content = page['content'].encode('utf-8')
                chunks.append(content)
                size = sum(map(len, chunks))
                require(size <= entry['bytes'], 'ARTIFACT_OVERFLOW')
                next_offset = page.get('next_offset')
                if next_offset is None:
                    require(page.get('truncated') is False, 'ARTIFACT_PAGINATION')
                    break
                require(content and next_offset == offset + len(content) and page.get('truncated') is True, 'ARTIFACT_PAGINATION')
                offset = next_offset
            raw = b''.join(chunks)
            require(len(raw) == entry['bytes'] and file_bytes_hash(raw) == entry['sha256'], 'ARTIFACT_HASH')
            value = json.loads(raw)
            require(isinstance(value, dict), 'ARTIFACT_JSON_OBJECT')
            self._record('observation', {'job_id': job['id'], 'artifact_name': name, 'sha256': entry['sha256'],
                                      'value': value, 'evidence_kind': self.identity['evidence_kind']})
            return value, entry['sha256']

    def submit(self, operation_id, rationale):
        with self.mutex:
            require(isinstance(rationale, str) and 1 <= len(rationale) <= 4000, 'SUBMISSION_REASON')
            if self.submission:
                require(self.submission['receipt_hash'] == digest(self.submission['receipt'])
                        and self.submission['scientific_success'] is False, 'SUBMISSION_STATE')
                require(self.submission['operation_id'] == operation_id and self.submission['receipt']['rationale'] == rationale, 'SUBMISSION_IMMUTABLE')
                return copy.deepcopy(self.submission)
            if self.pending_submission:
                require(self.pending_submission['operation_id'] == operation_id
                        and self.pending_submission['rationale'] == rationale, 'SUBMISSION_IMMUTABLE')
            op = self.operations[operation_id]
            result, result_sha = self.read_artifact(operation_id, 'result.json')
            design, _ = self.read_artifact(operation_id, 'design-spec.json')
            require(design == op['candidate'], 'RESULT_DESIGN_BINDING')
            evaluation = result.get('task_evaluation')
            require(isinstance(evaluation, dict) and evaluation.get('task_hash') == self.protocol['normalized_task_hash']
                    and evaluation.get('candidate_hash') == digest(design) and evaluation.get('task_id') == self.protocol['task_id'], 'EVALUATION_BINDING')
            require(evaluation.get('product_verified') is False and evaluation.get('hardware_calibrated') is False, 'CLAIM_BOUNDARY')
            require(isinstance(evaluation.get('unpassed_physical_checks'), list)
                    and type(evaluation.get('design_ranking_eligible')) is bool, 'EVALUATION_FIELDS')
            require(evaluation == op['job']['result'].get('task_evaluation'), 'RESULT_JOB_EVALUATION')
            if evaluation.get('unpassed_physical_checks'):
                require(evaluation.get('design_ranking_eligible') is False, 'PHYSICAL_RANKING_FORBIDDEN')
            if self.pending_submission is None:
                self._record('submission_intent', {'operation_id': operation_id, 'rationale': rationale,
                                                  'result_sha256': result_sha})
            else:
                require(self.pending_submission['result_sha256'] == result_sha, 'SUBMISSION_RESULT_CHANGED')
            receipt = self._call({'action': 'submit', 'job_id': op['job_id'], 'rationale': rationale})
            require(receipt.get('owner') == self.owner and receipt.get('job_id') == op['job_id']
                    and receipt.get('task_hash') == self.protocol['normalized_task_hash']
                    and receipt.get('result_sha256') == result_sha and receipt.get('evaluation') == evaluation
                    and receipt.get('rationale') == rationale
                    and receipt.get('claim') == 'participant selection; not product acceptance', 'SUBMISSION_PROOF')
            return self._record('submitted', {'operation_id': operation_id, 'receipt': receipt,
                'receipt_hash': digest(receipt), 'scientific_success': False, 'evidence_kind': self.identity['evidence_kind']})['data']


def file_bytes_hash(raw):
    return hashlib.sha256(raw).hexdigest()
