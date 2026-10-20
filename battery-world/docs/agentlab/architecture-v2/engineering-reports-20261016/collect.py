#!/usr/bin/env python3
"""Copy exact public repository artifacts for a report, without creating a Workbench."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def protected_state():
    baseline = Path.home()/'.local/share/bf-agent-baselines/bf-p01-demo-20261014/manifest.json'
    manifest = json.loads(baseline.read_text())
    paths = dict(manifest['production']['database_paths'])
    paths['v2'] = str(Path.home()/'.local/share/bf-agent-architecture-v2/workbench/state/workbench.sqlite')
    if not Path(paths['v2']).is_file():
        paths['v2'] = str(Path.home()/'.local/share/bf-agent-architecture-v2/state/workbench.sqlite')
    output = {}
    for label, path in paths.items():
        connection = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
        connection.execute('PRAGMA query_only=ON')
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        snapshot = {}
        # Billing fields and design control state are small; historical model request
        # bodies/chat traces are multi-GB and are not needed to verify this read path.
        selected = {
            'model_requests':['id','owner','created','status','reserved','charged','usage','error'],
            'conversations':['id','status','harness','title'],
            'engineering_jobs':['id','owner','status','created'],
            'eda_cli_jobs':['id','owner','status','created'],
            'design_projects':None, 'design_system_commits':None,
            'design_domain_commits':None, 'design_interface_contracts':None,
            'design_repository_releases':None, 'design_adoptions':None,
            'research_usage_continuations':None, 'research_usage_carryforwards':None,
        }
        for table, columns in selected.items():
            if table not in tables:
                continue
            available = {r[1] for r in connection.execute('PRAGMA table_info("'+table+'")')}
            chosen = [c for c in columns if c in available] if columns else sorted(available)
            digest = hashlib.sha256()
            count = 0
            for row in connection.execute('SELECT '+','.join('"'+c+'"' for c in chosen)+' FROM "'+table+'" ORDER BY rowid'):
                digest.update(json.dumps(row,sort_keys=True,default=str).encode()+b'\n')
                count += 1
            snapshot[table] = {'rows':count, 'sha256':digest.hexdigest(), 'columns':chosen}
        connection.close()
        output[label] = snapshot
    native = Path(manifest['production']['native_project'])
    output['native'] = {str(p.relative_to(native)): sha(p.read_bytes()) for p in sorted(native.rglob('*')) if p.is_file()}
    return output


def collect(output, candidate='submitted'):
    output = Path(output).resolve()
    if (output/'report-input.json').exists():
        raise ValueError('INPUT_SNAPSHOT_ALREADY_EXISTS')
    output.mkdir(parents=True, exist_ok=True)
    before = protected_state()
    write_json(output/'protected-before.json', before)
    runtime = Path.home()/'.local/share/bf-agent-architecture-v2'
    identity = json.loads((runtime/'p01-project.json').read_text())
    token = (Path.home()/'.local/share/bf-agent-runtime/workbench/state/operator.token').read_text().strip()
    query = {'project': identity['project_id'], 'owner': identity['owner']}

    def get(route, params):
        request = Request('http://127.0.0.1:8768'+route+'?'+urlencode(params),
                          headers={'Authorization': 'Bearer '+token})
        with urlopen(request, timeout=60) as response:
            return response.read()

    raw = get('/api/design-repository', query)
    view = json.loads(raw)
    target = view['project'].get(candidate, candidate)
    system = next(s for s in view['systems'] if s['id'] == target)
    write_json(output/'repository-view.json', view)
    records = []

    def copy(kind, path, ref, extra=None, job=None):
        params = {**query, 'system': target, 'path': path, **(extra or {})}
        data = get('/api/design-repository/file', params)
        digest = sha(data)
        if digest != ref['sha256']:
            raise ValueError('SOURCE_HASH_MISMATCH:'+kind+':'+path)
        relative = Path('sources')/kind/(job or '')/path
        destination = output/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        records.append({'kind':kind, 'path':path, 'job_id':job, 'local_path':str(relative),
                        'sha256':digest, 'bytes':len(data), 'system_commit':target})

    # All candidate files are copied so page claims and inventory use the same frozen tree.
    for path, ref in system['files'].items():
        copy('candidate', path, ref)
    for preview in view['previews']:
        if preview['system_commit'] == target:
            copy('previews', preview['name'], preview, {'preview':1})
    selected = {'input.json','result.json','project-numeric-observations.json', 'project-trace.raw',
                'project-cad_summary.json','project-readback.json','project-preview-mesh.json'}
    for job, record in system['jobs'].items():
        for path, ref in record['artifacts'].items():
            if path in selected:
                copy('jobs', path, ref, {'job':job}, job)
    fresh = json.loads(get('/api/design-repository', query))
    if fresh['project'] != view['project']:
        raise ValueError('PROJECT_CHANGED_DURING_COLLECTION')
    after = protected_state()
    write_json(output/'protected-after.json', after)
    if before != after:
        raise ValueError('PROTECTED_STATE_CHANGED')
    report = {'schema_version':'bf-engineering-report-input-v1',
              'captured_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'report_scope':'template proof using existing candidate artifacts',
              'selection':candidate, 'project':view['project'], 'system':system,
              'current_system':view['project']['submitted'], 'adopted_system':view['project']['adopted'],
              'assets':records, 'source_endpoint':'http://127.0.0.1:8768/api/design-repository',
              'new_model_requests':0, 'new_engineering_jobs':0, 'protected_state_unchanged':True}
    write_json(output/'report-input.json', report)
    print(json.dumps({'target':target, 'assets':len(records), 'bytes':sum(x['bytes'] for x in records),
                      'gates':{k:v['status'] for k,v in system['validations'].items()},
                      'protected_state_unchanged':True}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--candidate', default='submitted')
    args = parser.parse_args()
    collect(args.output, args.candidate)
