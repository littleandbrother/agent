#!/usr/bin/env python3
"""Read-only consumer verification of the published Studio/Lab integration."""
import argparse
import datetime
import hashlib
import io
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import zipfile

from bf_v2_environment import APP, environment
from publish_lab_bridge import ORIGINAL, RUNTIME, V2, BASELINE, PREFIX, protected_state
from bfworld.agentlab.baseline import logical_state, verify


def check(output):
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    profile, env = environment(V2)
    production_token = (RUNTIME/'workbench/state/operator.token').read_text().strip()
    v2_token = (Path(profile['home'])/'state/operator.token').read_text().strip()
    identity = json.loads((V2/'p01-project.json').read_text())
    before = protected_state()
    v2_db = Path(profile['home'])/'state/workbench.sqlite'
    v2_before = logical_state(v2_db)
    checks = []

    def assertion(name, passed, **facts):
        checks.append({'name': name, 'passed': bool(passed), 'facts': facts})
        if not passed:
            (output/'failed-check.json').write_text(json.dumps(checks, indent=2)+'\n')
            raise ValueError('LAB_PUBLICATION_CHECK_FAILED:'+name)

    def get(port, path, authenticated=True):
        token = production_token if port == 8768 else v2_token
        req = Request(f'http://127.0.0.1:{port}'+path,
                      headers={'Authorization': 'Bearer '+token} if authenticated else {})
        try:
            with urlopen(req, timeout=30) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    test = subprocess.run([profile['paths']['CAD_PYTHON'], '-m', 'unittest', 'discover',
        '-s', 'tests/agentlab', '-p', 'test_lab_bridge.py', '-v'],
        cwd=APP, env=env, capture_output=True, text=True, timeout=60)
    (output/'unit-tests.txt').write_text(test.stdout+test.stderr)
    assertion('bridge and public trace tests', test.returncode == 0, count=7)
    for name in ['architecture-v2/lab.js', 'studio.js', 'model-viewer.js']:
        result = subprocess.run([profile['paths']['NODE'], '--check', str(APP/'apps/agent-studio'/name)],
                                capture_output=True, text=True)
        assertion('JavaScript syntax '+name, result.returncode == 0)

    publication = Path(json.loads((RUNTIME/'workbench/state/lab-bridge.json').read_text())['publication'])
    published_before = json.loads((publication/'before-state.json').read_text())
    assertion('original rows and native files match pre-publication', before == published_before)
    static = {'/lab/v2/index.html': 'index.html', '/lab/v2/lab.js': 'lab.js', '/lab/v2/lab.css': 'lab.css'}
    for path, name in static.items():
        status, raw = get(8768, path, False)
        expected = (APP/'apps/agent-studio/architecture-v2'/name).read_bytes()
        assertion('published static '+name, status == 200 and raw == expected)
    for name in ['server.py', 'lab_bridge.py']:
        deployed = ORIGINAL/PREFIX/name
        receipt = json.loads((publication/'publication.json').read_text())['files'][str(PREFIX/name)]
        prior = json.loads((APP/'docs/agentlab/architecture-v2/lab-publication-20261015-002/restart.json').read_text())
        assertion('loaded bridge source '+name,
                  hashlib.sha256(deployed.read_bytes()).hexdigest() == receipt['after'] == receipt['before']
                  and prior['status'] == 'PASS')
    assets = list((APP/'apps/agent-studio/architecture-v2').rglob('*'))
    assertion('no raster UI assets', not any(p.suffix.lower() in ('.png','.jpg','.jpeg','.webp') for p in assets))
    query = {'project': identity['project_id'], 'owner': identity['owner']}
    endpoint = '/api/design-repository?'+urlencode(query)
    status, raw = get(8768, endpoint)
    v = json.loads(raw)
    direct = json.loads(get(8870, endpoint)[1])
    assertion('original Web reads the exact V2 project', status == 200 and v['project'] == direct['project'])
    assertion('historical and adopted identities retained',
              v['project']['adopted'] != v['project']['submitted'] and len(v['systems']) >= 2)
    assertion('unauthenticated repository denied', get(8768, endpoint, False)[0] == 403)
    wrong = '/api/design-repository?'+urlencode({**query, 'owner': 'pi-other'})
    assertion('unrelated owner denied', get(8768, wrong)[0] == 403)
    missing_status, missing_body = get(8768, '/lab/v2/assets/cropped.png', False)
    assertion('raster screenshot routes removed', missing_status == 400
              and json.loads(missing_body).get('error') == 'LAB_ASSET_NOT_FOUND')
    system = next(s for s in v['systems'] if s['id'] == v['project']['submitted'])
    base = {**query, 'system': system['id']}
    preview_count = 0
    for preview in v['previews']:
        if preview['system_commit'] != system['id']:
            continue
        status, data = get(8768, '/api/design-repository/file?'+urlencode({**base, 'path':preview['name'], 'preview':1}))
        assertion('current preview '+preview['name'], status == 200 and hashlib.sha256(data).hexdigest() == preview['sha256'])
        preview_count += 1
    assertion('schematic PCB and CAD previews exist',
              {'schematic.svg','pcb-combined.svg','cad-top.png'}.issubset(
                  {p['name'] for p in v['previews'] if p['system_commit'] == system['id']}))
    for job, record in system['jobs'].items():
        names = record['artifacts']
        filename = next((n for n in names if n == 'project-preview-mesh.json'), None)
        if filename:
            status, data = get(8768, '/api/design-repository/file?'+urlencode({**base, 'job':job, 'path':filename}))
            assertion('3D CAD mesh exact readback', status == 200 and hashlib.sha256(data).hexdigest() == names[filename]['sha256'])
    release = next(r for r in reversed(v['releases']) if r['target'] == system['id'])
    status, archive = get(8768, '/api/design-repository/archive?'+urlencode({**query, 'release':release['id']}))
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assertion('same-version release downloadable', status == 200 and z.testzip() is None,
                  release=release['id'], files=len(z.namelist()), sha256=hashlib.sha256(archive).hexdigest())
    status, raw = get(8768, '/api/design-repository/trace?'+urlencode({**query, 'session':identity['owner'], 'after':0, 'limit':100}))
    trace = json.loads(raw)
    assertion('actual original-format Pi public trace readable', status == 200 and len(trace['records']) > 0,
              records=len(trace['records']))
    baseline = verify(BASELINE, origins=False)
    assertion('frozen baseline intact', baseline['status'] == 'PASS', **baseline)
    after = protected_state()
    assertion('original sessions engineering and billing unchanged', before == after)
    assertion('V2 design and billing unchanged by UI checks', v2_before == logical_state(v2_db))
    result = {'schema_version':'bf-lab-publication-verification-v1', 'status':'PASS',
        'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'origin':'http://127.0.0.1:8768/lab#system', 'checks':checks,
        'preview_count':preview_count, 'unit_tests':7, 'baseline':baseline,
        'current_system':system['id'], 'adopted_system':v['project']['adopted'],
        'model_requests_added':0, 'simulations_rerun':0,
        'original_state_unchanged':True, 'v2_state_unchanged':True}
    (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','baseline')}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    check(parser.parse_args().output)
