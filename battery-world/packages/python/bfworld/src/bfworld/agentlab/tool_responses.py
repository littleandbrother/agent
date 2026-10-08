"""Backend-owned, owner/task-bound snapshots of engineering tool responses.

The snapshot is the exact JSON response before any preview; it is not a new
solver result. Pages use Unicode character offsets and never expose file paths.
"""
import hashlib
import json
import re
import time

from .store import canonical, identity

INLINE_BYTES = 22000
PAGE_BYTES = 20000


def delivery_canonical(value):
    # JSON.parse/stringify in Pi converts integral floats (1.0, -0.0) to ints.
    # Normalize only the delivery comparison; source snapshot bytes stay exact.
    def normalize(item):
        if isinstance(item, float) and item.is_integer():
            return int(item)
        if isinstance(item, list):
            return [normalize(v) for v in item]
        if isinstance(item, dict):
            return {k: normalize(v) for k, v in item.items()}
        return item
    return canonical(normalize(value))


class ToolResponses:
    def __init__(self, engineering):
        self.engineering = engineering
        self.store = engineering.store
        with self.store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS engineering_responses(
                    owner TEXT, id TEXT, task_hash TEXT, sha256 TEXT, body TEXT,
                    binding TEXT, created REAL, PRIMARY KEY(owner,id));
                CREATE TABLE IF NOT EXISTS engineering_response_deliveries(
                    owner TEXT, sha256 TEXT, response_id TEXT, body TEXT,
                    created REAL, PRIMARY KEY(owner,sha256));
            ''')

    def task_hash(self, owner):
        binding = self.engineering.tasks.binding(owner)
        return binding['task_hash'] if binding else None

    def wrap(self, owner, value):
        text = canonical(value)
        digest = hashlib.sha256(text.encode()).hexdigest()
        task_hash = self.task_hash(owner)
        # Bind actual backend job identities; participants cannot register data.
        jobs = value.get('jobs', []) if isinstance(value, dict) else []
        if isinstance(value, dict) and str(value.get('id', '')).startswith('eng-'):
            jobs = [value]
        elif isinstance(value, dict) and str(value.get('job_id', '')).startswith('eng-'):
            jobs = [self.engineering.get(owner, value['job_id'])]
        bindings = []
        for job in jobs:
            actual = self.engineering.get(owner, job['id'])
            result = actual.get('result') or {}
            bindings.append({'job_id': actual['id'], 'operation': actual['operation'],
                'candidate_sha256': identity(actual.get('parameters', {}).get('candidate')),
                'artifacts': [{k: a[k] for k in ('name', 'sha256', 'bytes') if k in a}
                              for a in result.get('artifacts', [])]})
        binding = {'owner': owner, 'task_hash': task_hash, 'jobs': bindings}
        key = identity({'binding': binding, 'sha256': digest})
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO engineering_responses VALUES(?,?,?,?,?,?,?)',
                       (owner, key, task_hash, digest, text, canonical(binding), time.time()))
        ref = {'schema': 'bf-tool-response-v1', 'response_id': key, 'sha256': digest,
               'bytes': len(text.encode()), 'task_hash': task_hash}
        result = {**value, 'full_response_inline': True, '_response': ref}
        if len(canonical(result).encode()) > INLINE_BYTES:
            result = {'_response': ref, 'full_response_inline': False,
                'instruction': 'Read the exact saved JSON with bf_engineering action=response_view, response_id, response_sha256, offset and limit. Offsets count Unicode characters; continue from next_offset.',
                **{k: value[k] for k in ('id', 'status', 'engine', 'operation') if k in value}}
            # A large input/source snapshot must not hide the build failure or
            # the small log/result files needed to decide the next action.
            # This is an index of the exact receipt, never a new verdict.
            if isinstance(value.get('error'), str):
                result['error'] = value['error'][:2000]
            outcome = value.get('result')
            if isinstance(outcome, dict):
                preview = {k: outcome[k] for k in (
                    'product_verified', 'digital_checks_passed', 'nominal_status',
                    'nominal_prediction_eligible', 'hardware_verified',
                    'physical_qualification', 'fabrication_released')
                    if isinstance(outcome.get(k), bool) or
                    isinstance(outcome.get(k), str) and len(outcome[k]) <= 120}
                artifacts = outcome.get('artifacts')
                if isinstance(artifacts, list):
                    preview['artifact_count'] = len(artifacts)
                    preview['artifacts'] = []
                    for artifact in artifacts:
                        if not isinstance(artifact, dict):
                            continue
                        entry = {k: artifact[k] for k in ('name', 'sha256', 'bytes') if k in artifact}
                        if len(canonical(preview).encode()) + len(canonical(entry).encode()) > 8000:
                            break
                        preview['artifacts'].append(entry)
                    preview['artifact_index_complete'] = len(preview['artifacts']) == len(artifacts)
                if preview:
                    result['result'] = preview
            if jobs:
                result['jobs'] = [{k: j[k] for k in ('id', 'status', 'engine', 'operation') if k in j}
                                  for j in jobs]
            # The task/catalog may be large, but the recovery index must fit.
            if len(canonical(result).encode()) > INLINE_BYTES:
                result.pop('jobs', None)
        return self.record_delivery(owner, key, result)

    def record_delivery(self, owner, key, value):
        text = delivery_canonical(value)
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO engineering_response_deliveries VALUES(?,?,?,?,?)',
                       (owner, hashlib.sha256(text.encode()).hexdigest(), key, text, time.time()))
        return value

    def view(self, owner, body):
        key, expected = body.get('response_id'), body.get('response_sha256')
        if not all(isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v) for v in (key, expected)):
            raise ValueError('RESPONSE_ID_AND_HASH_REQUIRED')
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM engineering_responses WHERE owner=? AND id=?', (owner, key)).fetchone()
        if not row:
            raise PermissionError('RESPONSE_NOT_FOUND')
        if row['task_hash'] != self.task_hash(owner):
            raise PermissionError('RESPONSE_TASK_MISMATCH')
        binding = json.loads(row['binding'])
        if (row['sha256'] != expected or hashlib.sha256(row['body'].encode()).hexdigest() != expected
                or identity({'binding': binding, 'sha256': expected}) != key):
            raise ValueError('RESPONSE_HASH_MISMATCH')
        for job in binding['jobs']:
            self.engineering.get(owner, job['job_id'])  # reauthorize, do not replace historical results
        offset, limit = body.get('offset', 0), body.get('limit', 4000)
        if type(offset) is not int or type(limit) is not int or not 0 <= offset <= len(row['body']) or not 1 <= limit <= 16000:
            raise ValueError('RESPONSE_PAGE_INVALID')
        end = min(len(row['body']), offset + limit)
        result = {'_response': {'schema': 'bf-tool-response-v1', 'response_id': key,
            'sha256': expected, 'bytes': len(row['body'].encode()), 'task_hash': row['task_hash']},
            'offset_unit': 'unicode_characters', 'offset': offset, 'total_characters': len(row['body'])}
        while True:
            result.update(text=row['body'][offset:end], next_offset=end if end < len(row['body']) else None)
            if len(canonical(result).encode()) <= PAGE_BYTES:
                break
            end = offset + max(1, (end - offset) // 2)
        return self.record_delivery(owner, key, result)
