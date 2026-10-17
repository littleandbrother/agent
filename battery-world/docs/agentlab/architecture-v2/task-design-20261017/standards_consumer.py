#!/usr/bin/env python3
"""Replay the real Pi candidate in an isolated repository; native dispatch is forbidden."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

APP = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(APP/'scripts'))
from bf_v2_environment import environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=Path.home()/'.local/share/bf-agent-architecture-v2')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-system', help='Frozen candidate to replay in the isolated copy')
    parser.add_argument('--worker', action='store_true')
    a = parser.parse_args()
    profile, env = environment(a.runtime)
    if not a.worker:
        command = [profile['paths']['CAD_PYTHON'], __file__, '--worker', '--runtime', str(a.runtime), '--output', str(a.output)]
        if a.source_system: command += ['--source-system', a.source_system]
        return subprocess.call(command, env=env)
    from bfworld.agentlab.store import Store, canonical, identity
    from bfworld.agentlab.design_lab.service import DesignLab
    from bfworld.agentlab.design_lab.repository import Repository, file_hash
    from bfworld.agentlab.design_lab.repository_task_execution import current_execution
    from bfworld.agentlab.design_lab.repository_reference_node import environment as native_environment
    from bfworld.agentlab.design_lab.contracts import sealed
    if a.output.exists(): raise ValueError('FRESH_CONSUMER_PROBE_DIRECTORY_REQUIRED')
    a.output.mkdir(parents=True)
    who = json.loads((a.runtime/'task-design/owner.json').read_text()); owner, pid = who['owner'], who['project_id']
    original_home = Path(profile['home']); original_root = original_home/'design-lab/repository'
    original = sqlite3.connect((original_home/'state/workbench.sqlite').as_uri()+'?mode=ro', uri=True)
    original.row_factory = sqlite3.Row; original.execute('PRAGMA query_only=ON')
    selected = {}
    for table, key, value in [('design_projects', 'id', pid), ('design_tasks', 'owner', owner),
        ('design_system_commits', 'project', pid), ('design_task_executions', 'project', pid),
        ('design_repository_validations', 'project', pid)]:
        selected[table] = [dict(row) for row in original.execute('SELECT * FROM '+table+' WHERE '+key+'=? ORDER BY rowid', (value,))]
    original.close()
    store = Store(a.output/'isolated/state')
    with store.connect() as db:
        db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY)'); db.execute('INSERT INTO conversations VALUES(?)', (owner,))
    lab = DesignLab(SimpleNamespace(store=store, engineering=SimpleNamespace(lock=threading.Lock())), start_worker=False)
    repo = Repository(lab, {'id': 'task-semantics-consumer-probe', 'baseline': profile['baseline'], 'protected_owners': []})
    lab.repository = repo
    with store.connect() as db:
        for table, rows in selected.items():
            for row in rows:
                db.execute('INSERT INTO '+table+' ('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')', list(row.values()))
        refs = {}
        for row in selected['design_system_commits']: refs.update({v['sha256']: v for v in json.loads(row['value'])['files'].values()})
        for row in selected['design_task_executions']: refs.update({v['sha256']: v for v in json.loads(row['value'])['artifacts'].values()})
        for digest, ref in refs.items(): repo.asset(db, original_root/'blobs'/digest, digest)
    original_current = repo.project(pid)['submitted']
    publication = a.runtime/'task-design/standards-publication-v1/result.json'
    source = a.source_system or (json.loads(publication.read_text())['source_system'] if publication.exists() else original_current)
    before = repo.system(pid, source)
    # Select a frozen checkpoint only in this disposable copy; the live project
    # remains at its current candidate and is checked again before returning.
    with store.connect() as db:
        db.execute('UPDATE design_projects SET submitted=?,requirements=? WHERE id=?',
                   (source, canonical(before['task_definition']), pid))
    initial = repo.project(pid)
    live_env = native_environment()
    first = current_execution(repo, before)
    assert first and first['status'] == 'SUCCEEDED'
    raw = {k: v for k, v in before['task_definition'].items() if k in
        ('profile', 'intent', 'goal', 'phase', 'scenario', 'parameters', 'acceptance', 'functions', 'components', 'assignments', 'report', 'design_space', 'service')}
    records = []
    def action(name, op, operator=False, **body):
        result = repo.handle(owner, {'action': 'repository_'+name, 'project_id': pid, 'operation_id': op, **body}, operator)
        sealed(a.output/(op+'.json'), result)
        records.append({'operation': op, 'action': name, 'system': result.get('system_id', result.get('id')), 'status': result.get('status', result.get('stage'))})
        return result
    with patch('bfworld.agentlab.design_lab.repository_reference_node.environment', return_value=live_env), \
         patch('bfworld.agentlab.design_lab.repository_reference_node.run', side_effect=AssertionError('NATIVE_DISPATCH_FORBIDDEN')) as native:
        standard = action('task_define', 'standardize', True, expected_revision=initial['revision'], definition=raw,
                          rationale='Replay original Pi R7 under explicit task semantics; device files are unchanged')
        run = action('task_execute', 'reuse-original', True, system_id=standard['id'])
        assert run['id'] == first['id'] and run['reused']
        nominal = action('validate', 'nominal-check', system_id=standard['id'])
        assert nominal['status'] == 'PASS'
        strict = copy.deepcopy(raw); strict['scenario']['minimum_storage_v'] = 3.2
        strict['acceptance']['power_service']['condition'] = '每次采样与发送窗口储能电压至少为 3.2 V'
        changed = action('task_define', 'raise-service-threshold', True, expected_revision=initial['revision']+1,
                         definition=strict, rationale='Injected stricter service condition for reuse calibration')
        rerun = action('task_execute', 'reuse-strict', True, system_id=changed['id'])
        assert rerun['id'] == first['id'] and rerun['reused']
        checked = action('validate', 'strict-check', system_id=changed['id'])
        assert checked['result']['gates']['source_model']['status'] == 'PASS'
        assert checked['result']['gates']['load_binding']['status'] == 'PASS'
        assert checked['result']['gates']['power_service']['status'] == 'FAIL'
        action('decide', 'retain-failure', True, system_id=changed['id'], expected_revision=initial['revision']+2,
               decision='RETAIN_FOR_REVIEW', rationale='Deterministic stricter-condition control; preserve actual failed result')
        content = {'conclusion': '原候选满足 2.2 V 条件；同一执行波形在 3.2 V 条件下任务供电未通过。',
            'sections': {k: {'text': '操作者校准：读取 Pi R7 原始结果，保持原设计与执行输入，提高服务电压条件并重新评价。',
                            'sources': ['design.json', 'power_service', 'receiver_service']}
                         for k in ('task_and_model', 'mechanics_and_source', 'firmware_and_receiver', 'energy_and_service', 'conclusion_and_files')}}
        report = action('task_report', 'failed-review-report', True, system_id=changed['id'], content=canonical(content))
        release = action('release', 'failed-review-package', True, system_id=changed['id'], rationale='Operator consumer probe, not a new Pi design attempt')
        assert release['source_author'] == 'operator'
        state = action('task_state', 'delivered-state')
        assert state['stage'] == 'DELIVERED' and not state['qualification']['task_passed']
        assert native.call_count == 0
    after = repo.project(pid)
    with store.connect() as db: executions = db.execute('SELECT COUNT(*) FROM design_task_executions WHERE project=?', (pid,)).fetchone()[0]
    assert executions == len(selected['design_task_executions'])
    fresh = sqlite3.connect((original_home/'state/workbench.sqlite').as_uri()+'?mode=ro', uri=True)
    fresh.row_factory = sqlite3.Row; fresh.execute('PRAGMA query_only=ON')
    unchanged = dict(fresh.execute('SELECT * FROM design_projects WHERE id=?', (pid,)).fetchone()) == selected['design_projects'][0]
    fresh.close(); assert unchanged
    standard_task = repo.system(pid, standard['id'])['task_definition']
    sealed(a.output/'task-definition-example.json', standard_task)
    from bfworld.agentlab.design_lab.repository_profiles import schema, runtime_spec
    sealed(a.output/'definition-catalogue.json', schema()); sealed(a.output/'model-visible-contract.json', runtime_spec(standard_task))
    result = {'status': 'PASS', 'actor': 'deterministic operator calibration', 'source_system': before['id'],
        'original_live_current': original_current, 'isolated_checkpoint_selection': source,
        'source_execution': first['id'], 'original_project_unchanged': unchanged,
        'states': records, 'native_dispatches': 0, 'model_calls': 0, 'execution_count_before': executions,
        'execution_count_after': executions, 'raw_blobs_verified': len(refs),
        'nominal_status': nominal['status'], 'strict_power_status': checked['result']['gates']['power_service']['status'],
        'interface_source_consistency': state['interfaces']['power-runtime']['source_consistency'],
        'interface_engineering_compatibility': state['interfaces']['power-runtime']['engineering_compatibility'],
        'failed_review_delivery': {'release': release['id'], 'report': report['id'], 'state': state['stage']},
        'source_environment': live_env,
        'replay_script_sha256': file_hash(__file__),
        'source_modules': {p.name: file_hash(p) for p in (APP/'packages/python/bfworld/src/bfworld/agentlab/design_lab').glob('repository_task*.py')}}
    sealed(a.output/'result.json', result)
    print(canonical({k: result[k] for k in ('status','source_system','native_dispatches','model_calls','raw_blobs_verified',
        'nominal_status','strict_power_status','interface_source_consistency','interface_engineering_compatibility','original_project_unchanged')}))
    return 0


if __name__ == '__main__': sys.exit(main())
