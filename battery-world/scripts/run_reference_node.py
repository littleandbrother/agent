#!/usr/bin/env python3
"""No-Agent qualification of the declared piezo reference using Repository entry points."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

from bf_v2_environment import APP, environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=Path.home()/'.local/share/bf-agent-architecture-v2')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    a = parser.parse_args()
    if not a.worker:
        profile, env = environment(a.runtime)
        return subprocess.call([profile['paths']['CAD_PYTHON'], __file__, '--worker', '--runtime', str(a.runtime), '--output', str(a.output)], env=env)
    from bfworld.agentlab.store import Store, canonical, identity
    from bfworld.agentlab.design_lab.service import DesignLab
    from bfworld.agentlab.design_lab.repository import Repository, file_hash
    from bfworld.agentlab.design_lab.repository_reference_node import environment as tool_environment
    from bfworld.agentlab.design_lab.repository_task_checks import evaluator_identity
    from bfworld.agentlab.design_lab.contracts import sealed
    fixture = APP/'configs/reference_cases/task-design'
    definition = json.loads((fixture/'piezo-node-v1.json').read_text())
    files = {'design.json': (fixture/'design.json').read_text(), 'firmware/main.c': (fixture/'main.c').read_text()}
    protocol = {'definition': definition, 'files': files, 'environment': tool_environment(), 'runner_sha256': file_hash(__file__),
        'checker':evaluator_identity({'task_definition':{'profile':definition['profile']}}),
        'sources': {p.name: file_hash(p) for p in sorted((APP/'packages/python/bfworld/src/bfworld/agentlab/design_lab').glob('repository_task*.py'))},
        'controls': ['nominal', 'no-energy', 'bad-frame', 'changed-firmware-source-reuse'],
        'actor': 'deterministic-reference', 'model_calls': 0}
    run_id = identity(protocol); root = a.output/run_id
    sealed(root/'protocol.json', protocol)
    store = Store(a.output/'execution-cache/state')
    seed_id = identity({'definition':definition, 'files':files, 'environment':tool_environment()})
    owner = 'reference-node-'+seed_id[:20]
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY)')
        db.execute('INSERT OR IGNORE INTO conversations VALUES(?)', (owner,))
    lab = DesignLab(SimpleNamespace(store=store, engineering=SimpleNamespace(lock=threading.Lock())), start_worker=False)
    repo = Repository(lab, {'id': 'E-reference-isolated', 'baseline': {'reference_seed': seed_id}, 'protected_owners': []})
    lab.repository = repo
    dispatches_before = set(repo.root.glob('task-executions/*/*/dispatch.json'))
    def action(name, op, operator=False, **body):
        identity_op = op+'-'+run_id[:16] if name=='validate' else op
        value = repo.handle(owner, {'action': 'repository_'+name, 'operation_id': identity_op, **body}, operator or name=='task_execute')
        sealed(root/(op+'.json'), value)
        return value
    created = action('task_create', 'create', True, title='常规压电节点 · 无 Agent 参考', definition=definition, files=files)
    original = created['id']
    nominal = action('task_execute', 'nominal-run', system_id=original)
    check = action('validate', 'nominal-check', system_id=original)
    if nominal['status'] != 'SUCCEEDED' or check['status'] != 'PASS':
        print(canonical({'status': 'FAILED', 'execution': nominal['metrics'], 'checks':check['result']['gates'], 'root': str(root)})); return 1
    # Same program schedule with a deliberately incorrect frame checksum.
    bad = action('task_commit', 'bad-frame-commit', base_system=original, expected_revision=1,
        files={'firmware/main.c': files['firmware/main.c'].replace('0xA5', '0xA4')}, rationale='declared bad-frame negative control')
    changed = action('task_execute', 'bad-frame-run', system_id=bad['id'])
    bad_check = action('validate', 'bad-frame-check', system_id=bad['id'])
    restored = action('task_commit', 'restore-valid-frame', base_system=bad['id'], expected_revision=2,
        files={'firmware/main.c':files['firmware/main.c']}, rationale='isolate energy control from frame corruption')
    # Preserve the geometry; only supply/initial state changes for the zero-energy control.
    zero = copy.deepcopy(definition)
    zero['scenario']['acceleration_peak_m_s2'] = 0
    zero['scenario']['initial_storage_v'] = 0
    zero['parameters'][1]['value'] = 0
    no_energy = action('task_define', 'no-energy-definition', True, expected_revision=3, definition=zero)
    action('task_execute', 'no-energy-run', system_id=no_energy['id'])
    zero_check = action('validate', 'no-energy-check', system_id=no_energy['id'])
    results = {'nominal': check['status']=='PASS',
        'bad-frame': bad_check['result']['gates']['receiver_service']['status']=='FAIL',
        'no-energy': zero_check['result']['gates']['power_service']['status']=='FAIL' and zero_check['result']['gates']['receiver_service']['findings']['frame_errors']==[],
        'changed-firmware-source-reuse': changed['metrics'].get('source_reused_from')==nominal['id'] and changed['metrics']['native_dispatches']==['storage']}
    certificate = {'schema_version':'bf-reference-node-qualification-v1', 'status':'PASS' if all(results.values()) else 'FAIL',
        'protocol_id':run_id, 'protocol':protocol, 'checks':results, 'nominal_system': original,
        'nominal_execution':nominal['id'], 'environment':tool_environment(), 'output_root':str(root),
        'nominal_task_definition': repo.system(created['project_id'], original)['task_definition'],
        'new_execution_dispatches': len(set(repo.root.glob('task-executions/*/*/dispatch.json')) - dispatches_before),
        'artifact_root':str(repo.root/'blobs'),
        'evidence':{p.name:file_hash(p) for p in root.glob('*.json') if p.name!='qualification.json'}, 'model_calls':0}
    sealed(root/'qualification.json', certificate)
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output/'current.json').write_text(canonical({'path':str(root/'qualification.json'), 'sha256':file_hash(root/'qualification.json')}))
    print(canonical({'status':certificate['status'], 'checks':results, 'root':str(root),
        'new_execution_dispatches': certificate['new_execution_dispatches'], 'nominal_metrics_from_original_execution':nominal['metrics']}))
    return 0 if certificate['status']=='PASS' else 1


if __name__ == '__main__': sys.exit(main())
