import hashlib, http.cookiejar, json, pathlib, sqlite3, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

OUT = pathlib.Path(__file__).parent
LIT = pathlib.Path('/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008')
OWNER = 'pi-chat-b47a35e335bc68d4'
op = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
op.open('http://127.0.0.1:8768/', timeout=20).read()

def get(route):
    return op.open('http://127.0.0.1:8768' + route, timeout=30)

def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): h.update(block)
    return h.hexdigest()

catalog = json.load(get('/api/results?session=' + OWNER))
candidate = catalog['candidate']
design = json.load(get('/api/design-lab?session_id=' + OWNER))
delivery = json.load(get('/api/studio/delivery?session=' + OWNER + '&selection=candidate'))
files = [f for f in catalog['files'] if f.get('candidate_id') == candidate['design_id']]
assert catalog['preferred_scope'] == delivery['selection'] == 'candidate'
assert design['working_design'] == candidate['design_id'], design['working_design']
assert candidate['adopted_design_id'] != candidate['design_id']
assert {f['id'] for f in delivery['files']} == {f['id'] for f in files}
assert delivery['verdict'] == candidate['verdict']
assert delivery['purposes']['report']['available']
report_ids = delivery['purposes']['report']['file_ids']
assert any(f['id'] in report_ids and f['name'] == 'P01-first-version-report.md' for f in files)
assert not any('/history/' in key for key in report_ids)
download_checks = []
for file in files:
    with get(file['url']) as response:
        h = hashlib.sha256()
        size = 0
        for block in iter(lambda: response.read(1048576), b''):
            h.update(block); size += len(block)
    assert h.hexdigest() == file['sha256'] and size == file['bytes'], file['id']
    download_checks.append({'id': file['id'], 'sha256': h.hexdigest(), 'bytes': size, 'status': 'PASS'})

series_checks = []
for name in ('native-parts-readback.csv', 'project-trace.raw'):
    file = next(f for f in files if f['name'] == name)
    data = json.load(get('/api/results/series?' + urllib.parse.urlencode({'session': OWNER, 'id': file['id']})))
    assert data['source_sha256'] == file['sha256'] and data['rows'] and data['headers']
    if name.endswith('.csv'): assert data['headers'][0] == 'Designator' and len(data['rows']) == 39
    series_checks.append({'name': name, 'headers': data['headers'], 'preview_rows': len(data['rows']), 'total_points': data['total_points'], 'source_sha256': data['source_sha256'], 'status': 'PASS'})

with get('/api/design-lab/package?session_id=' + OWNER) as response:
    h = hashlib.sha256()
    for block in iter(lambda: response.read(1048576), b''): h.update(block)
assert h.hexdigest() == '0d391028b63e6f397a97a6189beb5aaaf6f464b857107f52f3d7fb76bfd42a4e'
package_sha = h.hexdigest()
try:
    get(files[0]['url'].replace(OWNER, 'pi-chat-8ae12ef0354d33bb'))
except urllib.error.HTTPError as error:
    owner_isolation = error.code
    assert owner_isolation in (400, 403, 404)
else: raise AssertionError('FOREIGN_OWNER_FILE_EXPOSED')

baseline = json.loads((OUT / 'preservation-before.json').read_text())
after = {}
with sqlite3.connect((LIT / 'runtime/state/workbench.sqlite').as_uri() + '?mode=ro', uri=True) as db:
    for table in baseline:
        h = hashlib.sha256(); count = 0
        for row in db.execute('select * from ' + table + ' order by rowid'):
            h.update(json.dumps(list(row), ensure_ascii=False, separators=(',', ':')).encode()); h.update(b'\n'); count += 1
        after[table] = {'rows': count, 'sha256': h.hexdigest()}
assert after == baseline, {'before': baseline, 'after': after}
(OUT / 'preservation-after.json').write_text(json.dumps(after, indent=2))
sources = json.loads((OUT / 'source-index.json').read_text())
for source in sources: assert sha(source['path']) == source['sha256'], source['id']
native = pathlib.Path('/Users/depengsu/Documents/LCEDA-Pro/projects/BF-Literature-P01-Native-20261012')
native_count = 0
for source in sources:
    marker = '/native-project/'
    if marker in source['path']:
        assert sha(native / source['path'].split(marker, 1)[1]) == source['sha256'], source['id']
        native_count += 1
download = pathlib.Path('/Users/depengsu/Downloads/P01_第三轮_首版完整工程_20261014.zip')
assert sha(download) == '52e5c4efa979a55578b3fa4866f4220c9e3a392a4611bf59ad4eb471e64dbae0'

receipt = {'schema_version': 'bf-live-preview-verification-v1', 'at': datetime.now(timezone.utc).isoformat(), 'status': 'PASS', 'owner': OWNER, 'design_id': candidate['design_id'], 'adopted_design_id': candidate['adopted_design_id'], 'selected_jobs': candidate['selected_jobs'], 'publication_id': candidate['publication_id'], 'preferred_scope': catalog['preferred_scope'], 'downloads': download_checks, 'series': series_checks, 'report_file_ids': report_ids, 'sealed_package_sha256': package_sha, 'owner_isolation_http_status': owner_isolation, 'preserved_tables': after, 'preserved_source_files': len(sources), 'native_project_files_preserved': native_count, 'existing_download_zip_preserved': True, 'model_calls': 0, 'solver_runs': 0, 'participant_engineering_edits': 0}
(OUT / 'live-verification.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
print(json.dumps({k:v for k,v in receipt.items() if k not in ('downloads','preserved_tables','series')}, ensure_ascii=False))
