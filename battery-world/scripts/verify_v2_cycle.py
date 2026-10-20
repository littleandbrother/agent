#!/usr/bin/env python3
"""Read-only audit of actual V2 candidate consumption and review delivery."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

from bf_v2_environment import environment


def digest(data):
    return hashlib.sha256(data).hexdigest()


def continuous_chain(proofs, start_system):
    """A review fork is history, not a completed revision of the requested root."""
    children = {}
    for proof in proofs:
        children.setdefault(proof['parent'], []).append(proof)

    def walk(parent, seen):
        best = []
        for proof in children.get(parent, []):
            sid = proof['system_commit']
            if sid in seen:
                raise ValueError('AUDIT_SYSTEM_PARENT_CYCLE')
            if not (proof['actual_changed_sources'] and proof['releases']
                    and proof['validation_ids'] and proof['decisions']):
                continue
            candidate = [sid, *walk(sid, seen | {sid})]
            if len(candidate) > len(best):
                best = candidate
        return best

    return walk(start_system, {start_system})


def audit(runtime, dispatch, output, system=None):
    profile, _ = environment(Path(runtime))
    start = json.loads(Path(dispatch).read_text())
    since = datetime.datetime.fromisoformat(start['time_utc']).timestamp()
    home = Path(profile['home'])
    repo = home/'design-lab/repository'
    db = sqlite3.connect(f'file:{home}/state/workbench.sqlite?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    project = dict(db.execute('SELECT * FROM design_projects WHERE owner=?', (start['owner'],)).fetchone())
    pid = project['id']

    def rows(table):
        return [json.loads(r['value']) for r in db.execute('SELECT value FROM '+table+' WHERE project=? ORDER BY rowid', (pid,))]

    systems = {v['id']: v for v in rows('design_system_commits')}
    commits = {v['id']: v for v in rows('design_domain_commits')}
    events = [dict(r) for r in db.execute('SELECT * FROM design_events WHERE owner=? AND created>=? ORDER BY seq', (start['owner'], since))]
    ids = [json.loads(r['data'])['system_commit'] for r in events if r['kind'] == 'system_integrated']
    if system:
        ids = [system]  # Explicit read-only checker calibration on an existing candidate.
    executions = rows('design_domain_executions')
    releases = rows('design_repository_releases')
    validations = rows('design_repository_validations')
    decisions = [json.loads(r['rationale']) for r in db.execute('SELECT rationale FROM design_adoptions WHERE owner=? AND created>=? ORDER BY rowid', (start['owner'], since))]
    proofs = []

    def blob(ref):
        data = (repo/'blobs'/ref['sha256']).read_bytes()
        if digest(data) != ref['sha256']:
            raise ValueError('AUDIT_BLOB_CONFLICT')
        return data

    previous = start['state_before']['current_system']
    for sid in dict.fromkeys(ids):
        s = systems[sid]
        source_proof = {p: digest(blob(ref)) for p, ref in s['files'].items()}
        jobs = {}
        changed_sources = {}
        parent_files = systems[s['parent']]['files'] if s.get('parent') else {}
        for jid, record in s['jobs'].items():
            refs = record['artifacts']
            if 'input.json' not in refs:
                raise ValueError('AUDIT_JOB_INPUT_MISSING')
            request = json.loads(blob(refs['input.json']))
            kind = request['project']['manifest']['kind']
            prefix = {'spice': 'project-chain', 'firmware-nrf52832-s132': 'project-fw-s132', 'cadquery': 'project-cad'}[kind]
            # Manifest plus every C/H/netlist source is compared with actual worker bytes.
            if json.loads(blob(s['files'][prefix+'/project.json'])) != request['project']['manifest']:
                raise ValueError('AUDIT_WORKER_MANIFEST_CONFLICT')
            source_hashes = {}
            archive_path = repo/'blobs'/refs['project-source.zip']['sha256']
            blob(refs['project-source.zip'])
            with zipfile.ZipFile(archive_path) as z:
                for path, source in request['project']['sources'].items():
                    encoded = source.encode()
                    if blob(s['files'][prefix+'/'+path]) != encoded or z.read(path) != encoded:
                        raise ValueError('AUDIT_ACTUAL_SOURCE_CONFLICT: '+path)
                    source_hashes[path] = digest(encoded)
                    logical = prefix+'/'+path
                    before = parent_files.get(logical, {}).get('sha256')
                    if before != source_hashes[path]:
                        changed_sources[logical] = {'before': before, 'after': source_hashes[path],
                                                    'consumed_by': jid}
            jobs[jid] = {'kind': kind, 'project_sha256': request['project_sha256'], 'sources': source_hashes,
                         'input_sha256': refs['input.json']['sha256'], 'source_zip_sha256': refs['project-source.zip']['sha256']}
        r = [v for v in releases if v['target'] == sid]
        packages = []
        for v in r:
            path = repo/'releases'/(v['id']+'.zip')
            seal = json.loads(path.with_suffix('.seal.json').read_text())
            if digest(path.read_bytes()) != seal['sha256']:
                raise ValueError('AUDIT_REVIEW_ZIP_CONFLICT')
            with zipfile.ZipFile(path) as z:
                manifest = json.loads(z.read('manifest.json'))
                if manifest['target'] != sid or manifest['files'] != s['files'] or manifest['jobs'] != s['jobs']:
                    raise ValueError('AUDIT_REVIEW_VERSION_CONFLICT')
                for name, ref in s['files'].items():
                    if digest(z.read('engineering/'+name)) != ref['sha256']:
                        raise ValueError('AUDIT_REVIEW_SOURCE_CONFLICT')
                for jid, job in s['jobs'].items():
                    for name, ref in job['artifacts'].items():
                        if digest(z.read('jobs/'+jid+'/'+name)) != ref['sha256']:
                            raise ValueError('AUDIT_REVIEW_RESULT_CONFLICT')
            packages.append({'id': v['id'], 'path': str(path), 'sha256': seal['sha256'],
                             'digital_status': v['digital_status'], 'physical': v['physical']})
        evidence = [v for v in validations if v['target'] == sid and v['result'].get('gates')]
        proofs.append({'system_commit': sid, 'parent': s['parent'], 'continues_previous': s['parent'] == previous,
                       'domain_commits': s['domain_commits'], 'contracts': s['contracts'], 'files': source_proof,
                       'changes': s['design_changes'], 'jobs': jobs, 'releases': packages,
                       'actual_changed_sources': changed_sources,
                       'validation_ids': [v['id'] for v in evidence],
                       'decisions': [v for v in decisions if v['to_design'] == sid]})
        previous = sid
    owners = [start['owner'], *[r['owner'] for r in db.execute('SELECT owner FROM design_professional_tasks WHERE project=?', (pid,))]]
    cost = {}
    for owner in owners:
        records = list(db.execute('SELECT id,status,charged,reserved FROM model_requests WHERE owner=?', (owner,)))
        before = start['state_before']['model_calls'] if owner == start['owner'] else None
        cost[owner] = {'requests_total': len(records), 'lead_requests_before': before,
                       'cost_upper_bound_usd': sum(r['charged'] if r['status'] == 'SETTLED' else r['reserved'] for r in records),
                       'unknown': [r['id'] for r in records if r['status'] == 'UNKNOWN']}
    selected = {k: v for k, v in commits.items() if any(k in p['domain_commits'].values() for p in proofs)}
    partial = []
    for child in selected.values():
        parent = commits.get(child.get('parent'))
        changed = {v['path'] for v in child['changes']}
        if parent and changed and all(p.startswith('interfaces/') for p in changed):
            retained = {p: ref['sha256'] for p, ref in parent['files'].items() if p not in changed}
            if any(child['files'].get(p, {}).get('sha256') != h for p, h in retained.items()):
                raise ValueError('AUDIT_PARTIAL_COMMIT_LOST_SOURCE')
            partial.append({'parent': parent['id'], 'child': child['id'], 'retained_files': retained,
                            'parent_changes': parent.get('cumulative_changes',parent['changes']), 'new_declarations': sorted(changed)})
    session_copies = []
    task_history = [json.loads(row['value']) for table in
                    ('design_professional_tasks', 'design_professional_task_history')
                    for row in db.execute('SELECT value FROM '+table+' WHERE project=?', (pid,))]
    for t in {t['id']: t for t in task_history}.values():
        marker = repo/'workspaces'/t['id']/'.pi/rebase-session.json'
        if marker.exists():
            v = json.loads(marker.read_text())
            source, destination = Path(v['source']), Path(v['destination'])
            raw = source.read_bytes()
            if digest(raw) != v['source_sha256'] or not destination.read_bytes().startswith(raw):
                raise ValueError('AUDIT_REBASE_SESSION_HISTORY_CONFLICT')
            session_copies.append({**v, 'history_prefix_preserved': True, 'source_unchanged': True})
    chain = continuous_chain(proofs, start['state_before']['current_system'])
    value = {'schema_version': 'bf-v2-cycle-consumer-audit-v2', 'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'mode': 'reference_calibration' if system else 'actual_continuous_cycles',
             'project': project, 'start_system': start['state_before']['current_system'], 'systems': proofs,
             'selected_commits': selected, 'partial_commit_proofs': partial, 'session_copies': session_copies,
             'executions': executions, 'cost': cost, 'queries': 'SQLite mode=ro; no Workbench',
             'model_calls_started': 0, 'native_jobs_started': 0,
             'continuous_chain': chain,
             'other_review_history': [p['system_commit'] for p in proofs if p['system_commit'] not in chain],
             'two_continuous_cycles': len(chain) >= 2,
             'source_consumer_passed': bool(proofs)}
    db.close()
    output = Path(output)
    with output.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: value[k] for k in ('two_continuous_cycles', 'source_consumer_passed', 'model_calls_started', 'native_jobs_started')}))
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--dispatch', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--system', help='Calibrate the read-only verifier against one existing system')
    args = parser.parse_args()
    audit(args.runtime, args.dispatch, args.output, args.system)
