"""Profile execution and exact raw-result reuse in the existing journal.

A durable dispatch marker precedes execution. An interrupted unknown operation
must be reconciled; another request identity cannot silently run it again.
"""
import json
import subprocess
from pathlib import Path

from ..store import canonical, identity
from .contracts import sealed
from .repository import file_hash
from .repository_profiles import system_profile, execution_identity


def descriptor(system):
    cfg = system_profile(system)
    if cfg['adapter'] == 'tabulated-curve-v1':
        paths = ['reference.csv', 'observation.csv']
        env = {'executor_sha256': file_hash(__file__), 'format': 'UTF-8 CSV x,y'}
    elif cfg['adapter'] == 'piezo-reference-v1':
        from .repository_reference_node import environment
        paths = ['design.json', 'firmware/main.c']
        env = environment()
    else: raise ValueError('TASK_USE_NATIVE_DOMAIN_EXECUTOR')
    return execution_identity(system, cfg['adapter'], env, paths)


def verify(repo, value):
    if value['id'] != 'TX-' + identity({k: v for k, v in value.items() if k != 'id'}): raise ValueError('TASK_EXECUTION_IDENTITY')
    for ref in value['artifacts'].values():
        if file_hash(repo.root/'blobs'/ref['sha256']) != ref['sha256']: raise ValueError('TASK_EXECUTION_ARTIFACT_CHANGED')
    return value


def current_execution(repo, system, db=None):
    if db is None:
        with repo.store.connect() as connection: return current_execution(repo, system, connection)
    desc = descriptor(system)
    for row in db.execute('SELECT value FROM design_task_executions WHERE project=? ORDER BY rowid DESC', (system['project_id'],)):
        value = json.loads(row['value'])
        if value['execution_key'] == desc['id'] or compatible_descriptor(value['descriptor'], desc, system): return verify(repo, value)
    return None


def compatible_descriptor(old, new, system):
    """Explicit v1→v2 reuse: only known non-executed criteria/text are removed."""
    from .repository_task_standards import VERSION, CHECK_ONLY, DISPLAY_ONLY
    task = system.get('task_definition', {})
    if task.get('standards', {}).get('version') != VERSION or task.get('case_adapter') != 'piezo-reference-v1': return False
    def consumed(d):
        return {**{k: v for k, v in d.items() if k not in ('id', 'scenario')},
                'scenario': {k: v for k, v in d['scenario'].items() if k not in CHECK_ONLY | DISPLAY_ONLY}}
    return consumed(old) == consumed(new)


def pending_execution(repo, system):
    desc = descriptor(system)
    project_root = repo.root/'task-executions'/system['project_id']
    for marker in sorted(project_root.glob('*/dispatch.json')):
        value = json.loads(marker.read_text())
        old = value.get('descriptor')
        same = marker.parent.name == desc['id'] or (old and compatible_descriptor(old, desc, system))
        if same: return marker.parent
    return None


def execute(repo, owner, body, operator=False):
    p = repo.leader(body['project_id'], owner)
    system = repo.system(p['id'], body['system_id'])
    desc = descriptor(system)
    if desc['executor']=='piezo-reference-v1':
        from ..runtime_config import require_capability
        require_capability('native')
        if not operator:
            from .repository_reference_qualification import require
            require(repo,system)
    def apply(db):
        prior = current_execution(repo, system, db)
        if prior: return {**prior, 'reused': True, 'requested_system': system['id']}
        root = pending_execution(repo, system) or repo.root/'task-executions'/p['id']/desc['id']
        root.mkdir(parents=True, exist_ok=True)
        marker, result = root/'dispatch.json', root/'completed.json'
        from .repository_task_checks import read, curve_rows
        # Verify all sources before the externally visible dispatch marker.
        inputs = {path: read(repo, system, path) for path in desc['inputs']}
        reference = None
        if desc['executor']=='piezo-reference-v1':
            from .repository_reference_qualification import reference_cache
            reference = reference_cache(repo,system)
        if result.exists():
            saved = json.loads(result.read_text())
            if saved['descriptor'] != desc and not compatible_descriptor(saved['descriptor'], desc, system): raise ValueError('TASK_EXECUTION_RECOVERY_CONFLICT')
        else:
            if marker.exists(): raise ValueError('TASK_EXECUTION_UNKNOWN_RECONCILE_REQUIRED')
            sealed(marker, {'system_id': system['id'], 'descriptor': desc})
            status = 'SUCCEEDED'
            try:
                if reference and reference['execution']['descriptor']==desc:
                    prior=reference['execution']
                    metrics={**prior['metrics'],'reference_reused_from':prior['id'],'native_dispatches':[]}
                    outputs={k:(reference['blobs']/ref['sha256']).read_bytes() for k,ref in prior['artifacts'].items()}
                elif desc['executor'] == 'tabulated-curve-v1':
                    metrics = {path: {'samples': len(curve_rows(raw))} for path, raw in inputs.items()}
                    outputs = {'samples.json': canonical({p: curve_rows(v) for p, v in inputs.items()})}
                else:
                    from .repository_reference_node import run
                    def source_lookup(netlist):
                        for row in db.execute('SELECT value FROM design_task_executions WHERE project=? ORDER BY rowid DESC', (p['id'],)):
                            candidate = json.loads(row['value'])
                            if candidate['status'] != 'SUCCEEDED' or candidate['descriptor']['environment'] != desc['environment']: continue
                            if candidate['metrics'].get('source_relative_error', 1) >= .01: continue
                            verify(repo, candidate)
                            refs = candidate['artifacts']
                            if 'source.cir' not in refs: continue
                            source = repo.root/'blobs'/refs['source.cir']['sha256']
                            if source.read_text() != netlist: continue
                            return {'execution_id': candidate['id'], 'artifacts': {
                                k: (repo.root/'blobs'/refs[k]['sha256']).read_bytes() for k in ('source.cir','source.cir.log','source.dat')}}
                        if reference:
                            candidate=reference['execution']; refs=candidate['artifacts']
                            if candidate['descriptor']['environment']==desc['environment'] and (reference['blobs']/refs['source.cir']['sha256']).read_text()==netlist:
                                return {'execution_id':candidate['id'],'artifacts':{
                                    k:(reference['blobs']/refs[k]['sha256']).read_bytes() for k in ('source.cir','source.cir.log','source.dat')}}
                        return None
                    metrics, outputs = run(root, system, inputs, source_lookup)
            except (ValueError, subprocess.TimeoutExpired) as error:
                status = 'FAILED'
                metrics = {'error': str(error), 'kind': 'execution_failure'}
                outputs = {'failure.json': canonical(metrics)}
                outputs.update({str(path.relative_to(root)): path.read_bytes() for path in root.glob('*.log')})
            output_refs = {}
            for logical, raw in outputs.items():
                path = root/logical; path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists(): path.write_bytes(raw.encode() if isinstance(raw, str) else raw)
                elif path.read_bytes() != (raw.encode() if isinstance(raw, str) else raw): raise ValueError('TASK_OUTPUT_CONFLICT')
                output_refs[logical] = {'sha256': file_hash(path)}
            saved = {'descriptor': desc, 'status': status, 'metrics': metrics, 'outputs': output_refs}
            sealed(result, saved)
        refs = {path: repo.asset(db, root/path, ref['sha256']) for path, ref in saved['outputs'].items()}
        value = {'project_id': p['id'], 'target': system['id'], 'execution_key': desc['id'],
                 'descriptor': desc, 'status': saved['status'], 'metrics': saved['metrics'], 'artifacts': refs}
        value['id'] = 'TX-' + identity(value)
        db.execute('INSERT OR IGNORE INTO design_task_executions VALUES(?,?,?,?)',
                   (value['id'], p['id'], system['id'], canonical(value)))
        return {**value, 'reused': False}
    return repo.mutate(owner, body, apply)
