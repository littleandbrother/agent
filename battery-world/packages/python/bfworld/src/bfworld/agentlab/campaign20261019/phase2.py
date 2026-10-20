"""Trusted, finite public-development observation/decision/execution apparatus.

Participant outputs are proposals. This host verifies provenance and executes
the selected D against the immutable world; an observation never edits physics.
Exact input responses are reused, including qualified pre-phase-two controls.
"""
from __future__ import annotations

import copy
import csv
import importlib.util
import json
import math
from pathlib import Path
import time
import zlib

from .b import simulate_b
from .common import digest, file_hash, seal
from .phase1 import encoded

BASELINE = 'P2-f7ac8bfc4d5f262ff2736e25298d0c4bddd43b2f2064ae0c48b3bdb42b612977'
VARIABLES = {'capacitance_f': (4e-6, 22e-6), 'tx_not_before_s': (0., .045)}


def source_units(payload):
    """Host unit registry from frozen apparatus field definitions, not proposal."""
    units = {}
    suffixes = {'_s':'s', '_j':'J', '_w':'W', '_v':'V', '_a':'A', '_f':'F', '_ohm':'ohm'}
    def visit(value, path='', name=''):
        if isinstance(value, dict):
            for key,child in value.items():
                visit(child,path+'/'+key.replace('~','~0').replace('/','~1'),key)
        elif isinstance(value, list):
            for index,child in enumerate(value): visit(child,path+'/'+str(index),name)
        elif value is not None:
            units[path] = next((unit for ending,unit in suffixes.items() if name.endswith(ending)), '1')
    visit(payload)
    return units


def design(value):
    if not isinstance(value, dict) or set(value) != set(VARIABLES):
        raise ValueError('EXACT_LEGAL_D_FIELDS_REQUIRED')
    for key, (lo, hi) in VARIABLES.items():
        v = value[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError('DESIGN_OUT_OF_DOMAIN:' + key)
    return copy.deepcopy(value)


def consume(observation, policy, current, *, registry=None):
    """Pure typed input consumer. Qualification is supplied by trusted registry."""
    current = design(current)
    if not isinstance(policy, list) or not 1 <= len(policy) <= 3:
        raise ValueError('FINITE_POLICY_REQUIRED')
    for row in policy:
        if not isinstance(row, dict) or set(row) != {'equals', 'design'}:
            raise ValueError('POLICY_SCHEMA')
        design(row['design'])
    if (observation is None or observation.get('qualification') != 'EXTERNAL_PASS'
            or registry is None or registry.get(digest(observation)) != observation):
        return {'judgment': 'UNKNOWN', 'design': current, 'used_observation': False}
    for row in policy:
        # bool and numeric identities must not alias in Python equality.
        if type(row['equals']) is type(observation['value']) and row['equals'] == observation['value']:
            return {'judgment': 'SELECTED', 'design': design(row['design']),
                    'used_observation': True, 'observation_sha256': digest(observation),
                    'policy_sha256': digest(policy)}
    return {'judgment': 'UNKNOWN', 'design': current, 'used_observation': False}


class CaseStore:
    """Single writer immutable full-input response registry, bounded to 12 new runs."""

    def __init__(self, app, root, historical, *, maximum=12):
        self.app, self.root, self.historical = map(Path, (app, root, historical))
        self.maximum = maximum
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / 'index.json'
        self.index = json.loads(path.read_text()) if path.exists() else {}
        self.registry = json.loads((self.app / 'configs/studies/phase2-20261020/shared/case-registry.json').read_text())
        self.check_sources()
        module = self.app / 'scripts/campaign_reference.py'
        spec = importlib.util.spec_from_file_location('phase2_independent_reference', module)
        self.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.checker)
        self.old_seal = json.loads((self.historical / 'seal.json').read_text())
        self.sealed = {x['path']: x['sha256'] for x in self.old_seal['files']}

    def check_sources(self):
        for path, sha in self.registry['frozen_scientific_files'].items():
            if file_hash(self.app / path) != sha:
                raise ValueError('FROZEN_SCIENTIFIC_INPUT_CHANGED:' + path)

    def original(self, world):
        if world not in (self.registry['e5_target'], self.registry['paired_reference'],
                         *self.registry['additional_saved_controls']):
            raise ValueError('UNREGISTERED_WORLD')
        result = {}
        for name in ('input.json', 'observations.json', 'result.json', 'trace.csv'):
            rel = 'cases/' + world + '/' + name
            p = self.historical / rel
            if file_hash(p) != self.sealed[rel]:
                raise ValueError('HISTORICAL_SOURCE_HASH_FAILED:' + rel)
            result[name] = p
        return result

    def task(self, world):
        return json.loads(self.original(world)['input.json'].read_text())

    @property
    def new_executions(self):
        return sum(v['origin'] == 'new-full-feedback-response' for v in self.index.values())

    def execute(self, world, patch):
        self.check_sources()
        patch = design(patch)
        old = self.original(world)
        task = json.loads(old['input.json'].read_text())
        task['device'].update(patch)
        key = digest({'task': task, 'model': self.registry['frozen_scientific_files'],
                      'checker_sha256': file_hash(self.app / 'scripts/campaign_reference.py')})
        if key in self.index:
            entry = self.index[key]
            if entry.get('status') == 'STARTED':
                raise ValueError('INCOMPLETE_EXECUTION_NO_AUTOMATIC_RESAMPLING')
            if file_hash(entry['result_path']) != entry['result_sha256']:
                raise ValueError('CACHED_RESPONSE_TAMPERED')
            for p, expected in entry['artifacts'].items():
                if file_hash(p) != expected:
                    raise ValueError('CACHED_RAW_OR_INPUT_TAMPERED')
            return {**json.loads(Path(entry['result_path']).read_text()), 'reused': True}
        if task == json.loads(old['input.json'].read_text()):
            saved = json.loads(old['result.json'].read_text())
            reference, energy = saved['reference'], saved['energy']
            origin, raw = 'sealed-historical-exact-input', None
        else:
            if self.new_executions >= self.maximum:
                raise ValueError('GLOBAL_SCIENTIFIC_EXECUTION_CAP')
            self.index[key] = {'origin': 'new-full-feedback-response', 'status': 'STARTED',
                               'input_sha256': digest(task)}
            (self.root / 'index.json').write_bytes(encoded(self.index) + b'\n')
            run = simulate_b(task)
            energy = self.checker.energy_reference(task, run['trace'], 'b')
            reference = self.checker.reference_b(task, run, energy)
            raw, origin = zlib.compress(encoded(run)), 'new-full-feedback-response'
        out = self.root / key
        out.mkdir()
        seal(out / 'input.json', task)
        if raw is not None:
            (out / 'response.json.zlib').write_bytes(raw)
        else:
            seal(out / 'historical-source.json', {n: {'path': str(p), 'sha256': file_hash(p)} for n,p in old.items()})
        value = {'input_sha256': digest(task), 'execution_key': key, 'world': world,
                 'design': patch, 'origin': origin, 'energy': energy, 'reference': reference,
                 'complete_service': 'PASS' if all(reference['verdicts'][k] == 'PASS' for k in
                    ('independent_energy', 'independent_receiver', 'event_receive', 'deduplication',
                     'transient_voltage')) else 'FAIL',
                 'physical_qualification': 'UNKNOWN', 'raw_path': str(out / 'response.json.zlib') if raw else None}
        seal(out / 'result.json', value)
        self.index[key] = {'origin': origin, 'result_path': str(out / 'result.json'),
                           'result_sha256': file_hash(out / 'result.json'),
                           'input_sha256': value['input_sha256'],
                           'artifacts': {str(p): file_hash(p) for p in out.iterdir() if p.is_file()}}
        # Index is a mutable projection; individual inputs/results remain sealed.
        (self.root / 'index.json').write_bytes(encoded(self.index) + b'\n')
        return {**value, 'reused': False}

    def source(self, source_id, world='b-volatile-reset'):
        start = time.monotonic()
        files = self.original(world)
        task = json.loads(files['input.json'].read_text())
        raw = json.loads(files['observations.json'].read_text())
        if source_id == 'component_record':
            payload, parent = task['device'], files['input.json']
        elif source_id == 'excitation_record':
            payload = {k: task[k] for k in ('duration_s', 'dt_s', 'event_s', 'contact_duration_s',
                       'deadline_s', 'source_segments', 'shunts')}
            parent = files['input.json']
        elif source_id == 'saved_activity':
            payload, parent = raw, files['observations.json']
        else:
            raise ValueError('SOURCE_ID_NOT_REGISTERED')
        return {'source_id': source_id, 'payload': payload, 'source_sha256': digest(payload),
                'field_units': source_units(payload),
                'parent_path': str(parent), 'parent_sha256': file_hash(parent),
                'acquisition': {'wall_seconds': time.monotonic() - start,
                                'bytes': len(encoded(payload)), 'native_calls': 0,
                                'new_scientific_executions': 0}}


def authoritative_consume(spec, policy, acquisition, evaluator, current, store, output):
    """Private qualification and actual service, outside the participant endpoint."""
    output = Path(output)
    source = store.source(spec['source_id'])
    if acquisition['source_sha256'] != source['source_sha256'] or acquisition['parent_sha256'] != source['parent_sha256']:
        raise ValueError('ACQUISITION_SOURCE_TAMPERED')
    replay = evaluator(spec, source['payload'], field_units=source['field_units'])
    if replay.get('status') != 'OBSERVED' or replay.get('unit_status') != 'CHECKED_AGAINST_SUPPLIED_MAPPING':
        raise ValueError('OBSERVATION_DOMAIN_OR_UNITS_UNQUALIFIED:' + str(replay.get('reason')))
    observation = {'spec_sha256': digest(spec), 'source_sha256': source['source_sha256'],
                   'parent_sha256': source['parent_sha256'], 'value': replay['value'],
                   'units': replay['units'], 'domain': spec['domain'],
                   'qualification': 'EXTERNAL_PASS'}
    paired = store.source(spec['source_id'], 'b-latched-reset')
    paired_value = evaluator(spec, paired['payload'], field_units=paired['field_units'])
    if paired_value.get('status') != 'OBSERVED':
        raise ValueError('PAIRED_DOMAIN_OR_UNITS_UNQUALIFIED')
    if type(replay['value']) is type(paired_value['value']) and replay['value'] == paired_value['value']:
        raise ValueError('UNINFORMATIVE_ON_REGISTERED_DISTINCTION')
    registry = {digest(observation): observation}
    before = consume(None, policy, current)
    after = consume(observation, policy, current, registry=registry)
    if not after['used_observation']:
        raise ValueError('OBSERVATION_NOT_CONSUMED')
    # Actual truth comes solely from frozen case input; observation is not physics.
    execution = store.execute('b-volatile-reset', after['design'])
    original = store.execute('b-volatile-reset', current)
    # Strong complete-information baseline uses identical decision table and source.
    static_config = json.loads((store.app / 'configs/studies/phase2-20261020/shared/static-rich-baseline.json').read_text())
    full_source = store.source('component_record')
    complete = {'qualification':'EXTERNAL_PASS', 'value': full_source['payload']['event_latch'],
                'source_sha256':full_source['source_sha256'], 'units':'1'}
    static = consume(complete, static_config['policy'], current, registry={digest(complete):complete})
    static_execution = store.execute('b-volatile-reset', static['design'])
    qualification = {'status': 'EXTERNAL_PASS', 'source_replay': replay,
                     'source_binding': source['source_sha256'], 'code_sha256': file_hash(Path(__file__)),
                     'paired_source_replay': paired_value,
                     'private_grid_receipt': str(store.root.parent / 'preparation-cases.json'),
                     'private_grid_sha256': file_hash(store.root.parent / 'preparation-cases.json'),
                     'scope': 'Finite public-development typed source consistency, not hardware or causal discovery proof'}
    decision = {'before': before, 'after': after, 'policy': policy,
                'observation': observation, 'input_edge_sha256': digest({'observation': observation, 'policy': policy}),
                'executed_input_sha256': execution['input_sha256'], 'world_not_modified': True,
                'design_changed': before['design'] != after['design'],
                'static_rich': static, 'static_rich_service':static_execution['complete_service'],
                'full_raw_equivalent': True,
                'researcher_formula_baseline': 'Existing phase1 human-written headroom AST remains a baseline, not this proposal'}
    seal(output / 'qualification.json', qualification)
    seal(output / 'external-observation-registry.json', registry)
    seal(output / 'consumer.json', decision)
    seal(output / 'service.json', {'current': original, 'selected': execution})
    return {'qualification': qualification, 'consumer': decision,
            'current_service': original['complete_service'], 'selected_service': execution['complete_service'],
            'independent_service_sha256': file_hash(output / 'service.json'),
            'execution_sha256': digest(execution), 'cost': acquisition['acquisition'],
            'static_rich_ties': static['design'] == after['design'],
            'superiority_claim': False}
