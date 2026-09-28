"""Read-only inventory and development inputs from the actual workbench."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
import time

from ..store import canonical, identity
from .core import SCHEMA, checked_file, implementation_binding, sha, write_atomic
from .evidence import verifier_revision

REPO = Path(__file__).resolve().parents[7]
OWNERS = {'reference-v5': ('pi-chat-bc78abe0ca313091', 5),
          'pi-v14': ('pi-chat-7bbf6862d7109e25', 14),
          'recovered-v4': ('pi-chat-cf37636f82c771a4', 4)}


def readonly(home):
    db = sqlite3.connect((Path(home)/'state/workbench.sqlite').as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def inventory(research):
    with readonly(research.home) as db:
        limits = dict(db.execute('SELECT * FROM model_limits WHERE id=1').fetchone())
        usage = dict(db.execute("SELECT count(*) calls,sum(CASE WHEN status='SETTLED' THEN charged ELSE reserved END) upper_bound_usd FROM model_requests").fetchone())
        groups = [dict(r) for r in db.execute('SELECT engine, status, count(*) n FROM (SELECT json_extract(request,\'$.engine\') engine,status FROM engineering_jobs) GROUP BY engine,status')]
        lineages = []
        for name, (owner, revision) in OWNERS.items():
            row = db.execute('SELECT * FROM assembly_revisions WHERE owner=? AND revision=?', (owner, revision)).fetchone()
            if row is None:
                lineages.append({'name': name, 'owner': owner, 'revision': revision, 'status': 'MISSING'})
                continue
            payload = json.loads(row['payload'])
            lineages.append({'name': name, 'owner': owner, 'revision': revision, 'title': payload['title'],
                             'payload_hash': identity(payload), 'hashes': json.loads(row['hashes']),
                             'parts': len(payload['parts']), 'hardware_verified': False,
                             'evidence_inheritance': 'same owner and explicit revision only'})
    reports = []
    for name in ['PRODUCT-DELIVERY', 'DELIVERY-DEPLOYMENT']:
        p = REPO/'docs/agentlab'/(name+'.json')
        value = json.loads(p.read_text())
        reports.append({'path': str(p), 'sha256': sha(p.read_bytes()),
                        'limitations': value.get('boundaries', value.get('limitations', [])),
                        'native_reimport_verified': value.get('native_eda', {}).get('native_project_reimport_verified')})
    capabilities = [
        {'id': 'digital-product', 'label': '数字产品与三条谱系', 'state': 'recorded', 'level': 'artifact-readback', 'source': reports[0]['path']},
        {'id': 'firmware', 'label': '固件 ELF/BIN 与烧录脚本', 'state': 'compiled-not-flashed', 'level': 'target-build', 'source': reports[1]['path']},
        {'id': 'tinyml', 'label': '神经网络与 NAS', 'state': 'synthetic-data-only', 'level': 'pipeline-check', 'source': reports[1]['path']},
        {'id': 'hardware', 'label': '实物、延迟与功耗', 'state': 'not-measured', 'level': 'absent', 'source': reports[1]['path']},
        {'id': 'native-reimport', 'label': '原生工程独立重导入', 'state': 'not-verified', 'level': 'archive-only', 'source': reports[0]['path']},
    ]
    value = dict(schema_version=SCHEMA, observed=time.time(), lineages=lineages, reports=reports,
                 capabilities=capabilities, engineering_counts=groups, model_usage=usage,
                 existing_model_limits=limits, remaining_usd=limits['total_usd']-(usage['upper_bound_usd'] or 0),
                 source_policy='Read-only database snapshot and hashed existing reports; historical tests not rerun here.',
                 data_split='All prior viewed products and traces are development data, never newly blind test data.',
                 historical_research='Old scientific feature statuses, B2 protocol and dev-v1 results remain unchanged.')
    return research.put('inventories', value)


def product_checkpoint(research, name='reference-v5'):
    owner, revision = OWNERS[name]
    with readonly(research.home) as db:
        row = db.execute('SELECT * FROM assembly_revisions WHERE owner=? AND revision=?', (owner, revision)).fetchone()
        if row is None:
            raise ValueError('RESEARCH_SOURCE_ASSEMBLY_MISSING')
        active = [r['id'] for r in db.execute("SELECT id FROM engineering_jobs WHERE owner=? AND status IN ('QUEUED','RUNNING','UNKNOWN')", (owner,))]
        # An old unresolved native job is not silently reconciled. Archive-only
        # checkpoints may exclude native session state but cannot resume it.
        running = [r['id'] for r in db.execute("SELECT id FROM engineering_jobs WHERE owner=? AND status IN ('QUEUED','RUNNING')", (owner,))]
        conv = db.execute('SELECT status FROM conversations WHERE id=?', (owner,)).fetchone()
        if conv and conv['status'] in {'RUNNING', 'STARTING', 'QUEUED'}:
            running.append(owner)
        if running:
            raise ValueError('RESEARCH_SOURCE_BUSY')
        payload = json.loads(row['payload'])
        config = db.execute('SELECT config,revision,folder_id FROM chat_contexts WHERE owner=?', (owner,)).fetchone()
        published = [dict(r) for r in db.execute('SELECT * FROM assembly_files WHERE owner=? AND revision<=? ORDER BY created', (owner, revision))]
    stage = research.root/'inputs'/name
    if stage.exists():
        # Inputs have their own manifest; don't overwrite when source has moved.
        saved = json.loads((stage/'source.json').read_text())
        if saved['payload_hash'] != identity(payload):
            raise ValueError('RESEARCH_SOURCE_ASSEMBLY_DRIFT')
    else:
        stage.mkdir(parents=True)
        write_atomic(stage/'assembly.json', canonical(payload).encode())
        latest = {f['source']: f for f in published}
        selected, excluded = [], []
        for source, item in sorted(latest.items()):
            # A cross-lineage distribution bundle is not one product's state.
            if 'five-deliveries' in source:
                excluded.append({'source': source, 'reason': 'cross-lineage-distribution-bundle'})
                continue
            try:
                file = checked_file(research.home/'participants'/owner, source)
                raw = file.read_bytes()
                if sha(raw) != item['digest']:
                    raise ValueError('REGISTERED_FILE_HASH_DRIFT')
                write_atomic(stage/'artifacts'/source, raw)
                selected.append({'path': 'artifacts/'+source, 'sha256': sha(raw), 'revision': item['revision'],
                                 'kind': item['kind'], 'source_id': item['id']})
            except (ValueError, OSError) as exc:
                excluded.append({'source': source, 'reason': str(exc)})
        write_atomic(stage/'source.json', canonical(dict(owner=owner, revision=revision, payload_hash=identity(payload),
            selected=selected, excluded=excluded, unresolved_native_jobs=active)).encode())
        if config:
            # Captured revision, not a reference to a mutable shared folder.
            write_atomic(stage/'folder-context.json', canonical(dict(config)).encode())
    source = json.loads((stage/'source.json').read_text())
    files = ['assembly.json', 'source.json']+[r['path'] for r in source['selected']]
    if (stage/'folder-context.json').exists():
        files.append('folder-context.json')
    state = dict(product_revision={'owner': owner, 'revision': revision, 'hash': identity(payload)},
                 world_revision='first-order-energy-v2', harness_revision='none-read-only-product-import',
                 requirements=payload['requirements'], assumptions=payload.get('assumptions', []),
                 public_context={'assembly': payload, 'folder_context': json.loads((stage/'folder-context.json').read_text()) if 'folder-context.json' in files else None,
                                 'history_policy': 'source artifacts and captured public folder context; no opaque conversation resume'},
                 evidence={'registered_files': source['selected'], 'exclusions': source['excluded']}, split='development')
    return research.checkpoint(stage, files, state, native_state='archive-only')


def base_query(research, checkpoint):
    cp = research.verify_checkpoint(checkpoint)
    assembly = cp['state']['public_context']['assembly']
    return {'schema_version': 'bf-energy-query-v1', 'product_revision': cp['state']['product_revision'],
            'energy': copy.deepcopy(assembly['energy']), 'requirements': {'minimum_service_fraction': 1.0, 'cold_deadline_s': 172800},
            'world_revision': 'first-order-energy-v2', 'verifier_revision': verifier_revision(),
            'assumptions': assembly.get('assumptions', []), 'calibration_required': False,
            'calibration_id': None, 'duration_s': 172800,
            'requirement_origin': 'declared research predicate; not a retroactive product acceptance claim'}


def b_changes(base):
    definitions = [
        ('camera-only', 'presentation.camera', 35),
        ('small-pv-change', 'energy.pv_power_mw', base['energy']['pv_power_mw']*1.01),
        ('weak-light', 'energy.pv_power_mw', base['energy']['pv_power_mw']*.25),
        ('larger-storage', 'energy.capacitance_f', base['energy']['capacitance_f']*1.5),
        ('leakage-change', 'energy.leakage_ua', 20),
        ('event-load-change', 'energy.events_per_day', base['energy']['events_per_day']*2),
        ('requirement-only', 'requirements.minimum_service_fraction', .5),
        ('startup-deadline', 'requirements.cold_deadline_s', 3600),
        ('missing-calibration', 'calibration_required', True),
        ('verifier-change', 'verifier_revision', 'unavailable-new-verifier'),
    ]
    out = {}
    for name, path, value in definitions:
        query = copy.deepcopy(base)
        if '.' in path:
            a, b = path.split('.')
            query.setdefault(a, {})[b] = value
        else:
            query[path] = value
        query['product_revision'] = {**base['product_revision'], 'development_change': name}
        out[name] = query
    return out


def protocol(paper, units, *, paid=False):
    arms = {'A': ['fixed-local', 'fixed-global', 'adaptive-closure', 'free-scope'],
            'B': ['full-recompute', 'dependency-cache', 'fixed-transfer', 'cost-aware-transfer'],
            'C': ['observe-fixed', 'expose-fixed', 'observe-update', 'expose-update']}[paper]
    questions = {
        'A': ('Repair-scope selection changes verified search outcomes under the same generator and budget.',
              'No matched advantage, or any advantage vanishes against a strong equal-information baseline.'),
        'B': ('Checked evidence transfer preserves computational predicates at lower total verification cost.',
              'Unsupported reuse, false acceptance, or planning overhead erases the savings.'),
        'C': ('Naturally generated execution gates hide feedback needed to repair their own rules.',
              'No identifiable organic blind spot or no net value beyond equal-budget random inspection.')}
    return dict(schema_version=SCHEMA, id=paper.lower()+'-pilot-v1', paper=paper,
                hypothesis=questions[paper][0], falsifier=questions[paper][1], arms=arms, units=units,
                repetitions=3 if paper == 'A' else 1,
                checkpoints={unit: None for unit in units},
                budget={'study_usd': .8 if paid else 0, 'trial_usd': .016 if paid else 0,
                        'study_wall_s': 7200, 'trial_wall_s': 300, 'model_calls_per_trial': 3 if paid else 0},
                split='mechanism-pilot', primary_metric={'A': 'externally verified success within total trial budget',
                    'B': 'audit agreement, support coverage and measured total execution time',
                    'C': 'identifiable gate-before organic cases; later net future utility'}[paper],
                failure_rule='Retain every claimed cell, blocked run, error and timeout; no silent replacement.',
                claim_boundary='Development computational mechanism pilot; not physical product, confirmatory statistics or RSI efficacy.',
                implementation=implementation_binding(), model={'provider': 'deepseek', 'requested_id': 'deepseek-flash',
                    'identity_level': 'provider-reported alias; immutable weights unavailable'} if paid else {'kind': 'no-model'},
                world_revision='coupled-programmed-reference-v3' if paper == 'A' else 'first-order-energy-v2',
                harness_revision='scope-selector-v1' if paper == 'A' else 'shared-operator-library-v1',
                verifier_revision=verifier_revision(), randomization_seed=20260924,
                statistic_unit='starting state/change/rule; events are not independent samples',
                promotion='none; formal protocol requires later separate frozen confirmation',
                shared_knowledge='All arms receive the same public state, tool contracts and operator library.')
