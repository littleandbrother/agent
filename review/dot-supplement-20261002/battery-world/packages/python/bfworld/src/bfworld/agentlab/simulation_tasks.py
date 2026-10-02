"""Operator-bound nominal tasks; participants cannot edit evaluation conditions."""
import json
import csv
import time
from pathlib import Path

from .runtime_config import REPO
from .simulation_chain.contracts import ChainError, digest, file_hash, validate, write_json

TASK_ROOT = REPO / 'configs/reference_cases/design-pilot'
NUMERICAL = ('energy_balance', 'force_interpolation', 'beam_mesh',
             'program_power_fixed_point', 'time_step')
PHYSICAL = ('magnetic_mesh', 'magnetic_anchor_agreement')


def load_task(task_id='door-event-nominal-v1'):
    if task_id != 'door-event-nominal-v1':
        raise ValueError('SIMULATION_TASK_NOT_FOUND')
    task = json.loads((TASK_ROOT / (task_id + '.json')).read_text())
    task['baseline'] = validate(task['baseline'])
    return {'task': task, 'task_hash': digest(task)}


def check_candidate(binding, parameters):
    task = binding['task']
    if digest(task) != binding['task_hash']:
        raise ValueError('SIMULATION_TASK_HASH_MISMATCH')
    if parameters.get('confirmation') is not True:
        raise ValueError('TASK_CONFIRMATION_REQUIRED')
    spec = validate(parameters.get('candidate', {}))
    baseline = task['baseline']
    for group, values in baseline.items():
        if not isinstance(values, dict):
            continue
        for key, base in values.items():
            field = group + '.' + key
            rule = task['allowed_design_variables'].get(field)
            value = spec[group][key]
            if rule is None and value != base:
                raise ValueError('TASK_PROTECTED_FIELD:' + field)
            if rule and 'values' in rule and value not in rule['values']:
                raise ValueError('TASK_DESIGN_VALUE:' + field)
            if rule and 'range' in rule and not rule['range'][0] <= value <= rule['range'][1]:
                raise ValueError('TASK_DESIGN_RANGE:' + field)
    return spec


def evaluate(binding, spec, result, receiver):
    """No hidden success inference: missing checks, wrong/late payloads stay explicit."""
    errors = []
    try:
        check_candidate(binding, {'candidate': spec, 'confirmation': True})
    except (ValueError, ChainError) as exc:
        errors.append(str(exc))
    task = binding['task']
    checks = result.get('checks', {})
    missing_numerical = [k for k in NUMERICAL if checks.get(k) is not True]
    missing_physical = [k for k in PHYSICAL if checks.get(k) is not True]
    if result.get('applicability', {}).get('full_rotated_FEM_coverage') is not True:
        missing_physical.append('full_rotated_FEM_coverage')
    completed = result.get('run_status') == 'completed'
    diagnostic = bool(spec['circuit']['initial_vin_V'] or spec['circuit']['diagnostic_input_A'])
    transmitted = {(e.get('capture_id'), e.get('time_s'), e.get('payload_hex'))
                   for e in receiver.get('transmitted', [])}
    valid = []
    for e in receiver.get('delivered', []):
        t = e.get('time_s')
        if ((e.get('capture_id'), t, e.get('payload_hex')) in transmitted
                and type(t) in (int, float) and 0 <= t <= task['service']['deadline_s']
                and e.get('payload_hex') == task['service']['expected_payload_hex']):
            valid.append(e)
    admissible = not errors and completed and not diagnostic and not missing_numerical
    prediction = bool(valid) and result.get('metrics', {}).get('cold_start_reached') is True
    return {
        'schema_version': 'simulation-task-evaluation-v1',
        'task_id': task['id'], 'task_hash': binding['task_hash'],
        'candidate_hash': digest(spec), 'input_violations': errors,
        'run_status': result.get('run_status'), 'diagnostic_only': diagnostic,
        'pilot_observation_eligible': not errors,
        'prediction_comparison_scope': 'fixed nominal model only; not physically qualified design ranking',
        'nominal_prediction_eligible': admissible,
        'nominal_task_status': ('satisfied' if prediction else 'unsatisfied') if admissible else 'not_evaluable',
        'design_ranking_eligible': admissible and not missing_physical,
        'unpassed_numerical_checks': missing_numerical,
        'unpassed_physical_checks': missing_physical,
        'timely_correct_packets': len(valid),
        'first_correct_packet_s': min((e['time_s'] for e in valid), default=None),
        'silence_groups': len(receiver.get('events', [])),
        'exactly_once_semantics_qualified': False,
        'product_verified': False, 'hardware_calibrated': False,
        'scope': task['claim_boundary'],
    }


class SimulationTasks:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS simulation_task_bindings(
                owner TEXT PRIMARY KEY,task_hash TEXT NOT NULL,task TEXT NOT NULL,
                max_candidates INTEGER NOT NULL,created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS simulation_task_submissions(
                owner TEXT PRIMARY KEY,job_id TEXT NOT NULL,receipt TEXT NOT NULL,created REAL NOT NULL);
            ''')

    def binding(self, owner, db=None):
        if db is None:
            with self.store.connect() as connection:
                return self.binding(owner, connection)
        row = db.execute('SELECT * FROM simulation_task_bindings WHERE owner=?', (owner,)).fetchone()
        if row is None:
            return None
        value = dict(row)
        value['task'] = json.loads(value['task'])
        if digest(value['task']) != value['task_hash']:
            raise ValueError('SIMULATION_TASK_HASH_MISMATCH')
        return value

    def bind(self, owner, task_id, max_candidates=3):
        if type(max_candidates) is not int or not 1 <= max_candidates <= 20:
            raise ValueError('TASK_CANDIDATE_CAP_INVALID')
        binding = load_task(task_id)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = self.binding(owner, db)
            if old:
                if old['task_hash'] != binding['task_hash'] or old['max_candidates'] != max_candidates:
                    raise ValueError('SIMULATION_TASK_BINDING_IMMUTABLE')
                return old
            if db.execute('SELECT 1 FROM engineering_jobs WHERE owner=?', (owner,)).fetchone():
                raise ValueError('TASK_BIND_BEFORE_FIRST_JOB')
            db.execute('INSERT INTO simulation_task_bindings VALUES(?,?,?,?,?)',
                       (owner, binding['task_hash'], json.dumps(binding['task'], sort_keys=True), max_candidates, time.time()))
        return self.binding(owner)

    def guard(self, owner, engine, parameters):
        binding = self.binding(owner)
        if binding:
            if engine != 'closed-simulation':
                raise ValueError('TASK_ENGINE_NOT_ALLOWED')
            check_candidate(binding, parameters)
        return binding

    def reserve_check(self, db, owner, binding):
        if not binding:
            return
        current = self.binding(owner, db)
        if not current or current['task_hash'] != binding['task_hash']:
            raise ValueError('SIMULATION_TASK_BINDING_CHANGED')
        if db.execute('SELECT 1 FROM simulation_task_submissions WHERE owner=?', (owner,)).fetchone():
            raise ValueError('TASK_ALREADY_SUBMITTED')
        n = db.execute('SELECT COUNT(*) FROM engineering_jobs WHERE owner=?', (owner,)).fetchone()[0]
        if n >= binding['max_candidates']:
            raise ValueError('TASK_CANDIDATE_BUDGET')

    def submit(self, engineering, owner, job_id, rationale):
        if not isinstance(rationale, str) or not 1 <= len(rationale) <= 4000:
            raise ValueError('TASK_SUBMISSION_REASON_REQUIRED')
        binding = self.binding(owner)
        if not binding:
            raise ValueError('SIMULATION_TASK_NOT_BOUND')
        job = engineering.get(owner, job_id)
        if job['status'] not in ('SUCCEEDED', 'FAILED'):
            raise ValueError('TASK_JOB_NOT_FINAL')
        if job.get('task_binding', {}).get('task_hash') != binding['task_hash']:
            raise ValueError('TASK_JOB_BINDING_MISMATCH')
        result_file = engineering.artifact(owner, job_id, 'result.json')
        result = json.loads(result_file.read_text())
        evaluation = result.get('task_evaluation')
        if not evaluation or evaluation.get('task_hash') != binding['task_hash']:
            raise ValueError('TASK_EVALUATION_MISSING')
        spec = json.loads(engineering.artifact(owner, job_id, 'design-spec.json').read_text())
        receiver = {}
        if any(a['name'] == 'receiver.json' for a in job['result'].get('artifacts', [])):
            receiver = json.loads(engineering.artifact(owner, job_id, 'receiver.json').read_text())
        if evaluate(binding, spec, result, receiver) != evaluation:
            raise ValueError('TASK_INDEPENDENT_EVALUATION_MISMATCH')
        receipt = {'owner': owner, 'job_id': job_id, 'task_hash': binding['task_hash'],
                   'result_sha256': file_hash(result_file), 'evaluation': evaluation,
                   'rationale': rationale, 'claim': 'participant selection; not product acceptance'}
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT receipt FROM simulation_task_submissions WHERE owner=?', (owner,)).fetchone()
            if old:
                if json.loads(old['receipt']) != receipt:
                    raise ValueError('TASK_SUBMISSION_IMMUTABLE')
            else:
                db.execute('INSERT INTO simulation_task_submissions VALUES(?,?,?,?)',
                           (owner, job_id, json.dumps(receipt, sort_keys=True), time.time()))
        engineering.event(owner, job_id, 'task_submitted', receipt)
        return receipt

    def create_trial(self, app, trial_id, text):
        """Operator-only preparation binds task, study and costs BEFORE the first send."""
        protocol = json.loads((TASK_ROOT/'protocol.json').read_text())
        if trial_id not in {t['id'] for t in protocol['pi_trials']}:
            raise ValueError('PILOT_TRIAL_NOT_DECLARED')
        operation = protocol['id'] + '-' + trial_id
        with self.store.connect() as db:
            study = db.execute('SELECT * FROM research_model_studies WHERE protocol=?', (protocol['id'],)).fetchone()
            if not study or time.time() >= study['expires']:
                raise ValueError('PILOT_STUDY_NOT_AUTHORIZED_OR_EXPIRED')
            old = db.execute('SELECT id FROM conversations WHERE operation=?', (operation,)).fetchone()
            if old:
                message = db.execute('SELECT text FROM chat_messages WHERE conversation=? ORDER BY created LIMIT 1', (old['id'],)).fetchone()
                if not message or message['text'] != text:
                    raise ValueError('PILOT_TRIAL_INPUT_CHANGED')
                return app.conversations.get(old['id'])
        def prepare_owner(cid):
            self.bind(cid, protocol['task_id'], protocol['pi_max_candidates_per_trial'])
            with self.store.connect() as db:
                db.execute('INSERT INTO research_model_owners VALUES(?,?,?)', (cid, protocol['id'], trial_id))
                db.execute('INSERT INTO owner_model_caps VALUES(?,?)', (cid, protocol['max_usd_per_trial']))
        return app.conversations.create(text, None, operation, preflight=prepare_owner)

    def artifact_view(self, engineering, owner, body):
        """Bounded public file slices; the participant never needs the native archive."""
        path = engineering.artifact(owner, body.get('job_id'), body.get('artifact_name'))
        if path.suffix not in ('.json', '.csv', '.txt', '.log', '.c', '.h', '.cir'):
            raise ValueError('ARTIFACT_VIEW_TEXT_ONLY')
        offset, limit = body.get('offset', 0), body.get('limit', 12000)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 16000:
            raise ValueError('ARTIFACT_VIEW_RANGE')
        channels = body.get('channels')
        if channels is not None:
            if path.suffix != '.csv' or not isinstance(channels, list) or not channels or len(channels) > 12:
                raise ValueError('ARTIFACT_CHANNELS_INVALID')
            with path.open() as f:
                reader = csv.DictReader(f)
                if set(channels) - set(reader.fieldnames or []): raise ValueError('ARTIFACT_CHANNEL_NOT_FOUND')
                selected = []; matched = 0; full = False
                start, end = body.get('time_from', 0), body.get('time_to', 1000000)
                if type(start) not in (int, float) or type(end) not in (int, float) or not 0 <= start <= end:
                    raise ValueError('ARTIFACT_TIME_RANGE')
                for row in reader:
                    if not start <= float(row.get('time_s', 0)) <= end: continue
                    if matched >= offset and not full:
                        item = {k: row[k] for k in channels}
                        if len(json.dumps(selected + [item])) < 14000 and len(selected) < 200:
                            selected.append(item)
                        else: full = True
                    matched += 1
            return {'sha256': file_hash(path), 'rows': selected, 'offset': offset,
                    'next_offset': offset+len(selected) if offset+len(selected) < matched else None,
                    'matched_rows': matched, 'units': 'CSV column names; no resampling'}
        with path.open(errors='replace') as f:
            f.seek(offset); content = f.read(limit); more = bool(f.read(1))
        return {'sha256': file_hash(path), 'content': content, 'offset': offset,
                'next_offset': offset+len(content.encode('utf-8')) if more else None, 'truncated': more}


def attach_evaluation(binding, directory, result):
    directory = Path(directory)
    spec = json.loads((directory / 'design-spec.json').read_text())
    receiver_file = directory / 'receiver.json'
    receiver = json.loads(receiver_file.read_text()) if receiver_file.exists() else {}
    evaluation = evaluate(binding, spec, result, receiver)
    write_json(directory / 'task.json', binding)
    write_json(directory / 'task-evaluation.json', evaluation)
    result['task_evaluation'] = evaluation
    result['artifacts'] = [e for e in result.get('artifacts', []) if e['name'] not in ('task.json', 'task-evaluation.json')]
    for name in ('task.json', 'task-evaluation.json'):
        path = directory / name
        result['artifacts'].append({'name': name, 'bytes': path.stat().st_size, 'sha256': file_hash(path)})
    write_json(directory / 'result.json', {k: v for k, v in result.items() if not k.startswith('_')})
    return evaluation
