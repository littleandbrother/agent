"""Versioned product definitions and immutable, owner-scoped output registration.

An assembly is an engineering proposal, not a scientific verdict. Geometry,
energy and presentation identities are separate so a camera change never
invalidates physical results. Existing scientific evidence is not rewritten.
"""
import hashlib
import json
import math
import re
import time
from pathlib import Path
from .store import canonical, identity

ID = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,79}$')
KINDS = {'box', 'rounded_box', 'cylinder', 'sphere', 'shell'}
ROLES = {'housing', 'cover', 'solar', 'storage', 'pcb', 'controller', 'power', 'input', 'feedback', 'mount', 'connector', 'decoration'}
FILE_TYPES = {'.json', '.jsonl', '.md', '.txt', '.csv', '.gz', '.png', '.jpg', '.glb', '.blend', '.step', '.stl', '.brep', '.svg', '.pdf', '.epro2', '.zip', '.c', '.h', '.py', '.java', '.mph', '.mp4', '.gif', '.elf', '.out', '.bin', '.hex', '.map', '.ld', '.net', '.enet', '.cir', '.dsn', '.ses', '.epro-source', '.su'}


def vector(value, low, high, name):
    if not isinstance(value, list) or len(value) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) or not low <= x <= high for x in value):
        raise ValueError('ASSEMBLY_VECTOR_INVALID:' + name)
    return value


def geometry(g, cut=False):
    if not isinstance(g, dict) or g.get('kind') not in KINDS - ({'shell'} if cut else set()):
        raise ValueError('ASSEMBLY_GEOMETRY_INVALID')
    vector(g.get('size_mm'), .05, 500, 'size_mm')
    if g['kind'] in ('sphere', 'cylinder') and (g['size_mm'][0] != g['size_mm'][1] or (g['kind'] == 'sphere' and len(set(g['size_mm'])) != 1)):
        raise ValueError('ASSEMBLY_ROUND_DIMENSIONS')
    vector(g.get('center_mm', [0, 0, 0]), -1000, 1000, 'center_mm')
    vector(g.get('rotation_deg', [0, 0, 0]), -360, 360, 'rotation_deg')
    for k in ('fillet_mm', 'wall_mm'):
        v = g.get(k, 0)
        if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v < min(g['size_mm']) / 2:
            raise ValueError('ASSEMBLY_GEOMETRY_INVALID:' + k)
    if g['kind'] == 'shell' and g.get('wall_mm', 0) < .5:
        raise ValueError('ASSEMBLY_SHELL_WALL_REQUIRED')
    cuts = g.get('cutouts', [])
    if not isinstance(cuts, list) or len(cuts) > 20 or (cut and cuts):
        raise ValueError('ASSEMBLY_CUTOUT_LIMIT')
    for item in cuts:
        geometry(item, True)


def validate(payload):
    # JSON roundtrip also removes aliases; cap the accepted input before recursion.
    if not isinstance(payload, dict) or len(canonical(payload).encode()) > 100000:
        raise ValueError('ASSEMBLY_SIZE_LIMIT')
    p = json.loads(canonical(payload))
    if p.get('units') != 'mm' or not isinstance(p.get('title'), str) or not 1 <= len(p['title']) <= 200:
        raise ValueError('ASSEMBLY_TITLE_OR_UNITS')
    parts = p.get('parts')
    if not isinstance(parts, list) or not 1 <= len(parts) <= 96:
        raise ValueError('ASSEMBLY_PART_LIMIT')
    ids = set()
    for part in parts:
        if not isinstance(part, dict) or not ID.fullmatch(str(part.get('id', ''))) or part['id'] in ids:
            raise ValueError('ASSEMBLY_PART_ID')
        ids.add(part['id'])
        if part.get('role') not in ROLES or not isinstance(part.get('name'), str):
            raise ValueError('ASSEMBLY_PART_ROLE')
        try:
            geometry(part.get('geometry'))
        except ValueError as exc:
            raise ValueError(str(exc) + ':part=' + part['id']) from None
        vector(part.get('color', [.65, .65, .65]), 0, 1, 'color')
        source = part.get('source')
        if not isinstance(source, dict) or source.get('basis') not in ('datasheet-envelope', 'design-assumption', 'native-component') or not source.get('note'):
            raise ValueError('ASSEMBLY_PART_SOURCE_REQUIRED:part=' + part['id'] + '; source.basis must be datasheet-envelope, design-assumption, or native-component; source.note is required')
        if source['basis'] == 'datasheet-envelope' and not str(source.get('url', '')).startswith('https://'):
            raise ValueError('ASSEMBLY_DATASHEET_URL_REQUIRED')
    required = p.get('required_roles')
    if not isinstance(required, list) or not required or not set(required) <= ROLES:
        raise ValueError('ASSEMBLY_REQUIRED_ROLES')
    for key in ('requirements', 'assumptions', 'interfaces'):
        if not isinstance(p.get(key), list) or len(p[key]) > 100:
            raise ValueError('ASSEMBLY_RECORD_LIST:' + key)
    if not isinstance(p.get('energy'), dict):
        raise ValueError('ASSEMBLY_ENERGY_REQUIRED')
    contacts = p.get('allowed_contacts', [])
    if not isinstance(contacts, list) or any(not isinstance(pair, list) or len(pair) != 2 or len(set(pair)) != 2 or not set(pair) <= ids for pair in contacts):
        raise ValueError('ASSEMBLY_CONTACT_INVALID:allowed_contacts must be a list of two distinct existing part IDs, for example [["partA","partB"]], never prose or missing IDs')
    camera = p.get('presentation', {}).get('camera_deg', 35)
    if type(camera) not in (int, float) or not math.isfinite(camera) or not -180 <= camera <= 180:
        raise ValueError('ASSEMBLY_CAMERA_INVALID:presentation.camera_deg must be a number from -180 to 180, not a vector')
    return p


def identities(p):
    physical_parts = [{k: v for k, v in x.items() if k not in ('color', 'name')} for x in p['parts']]
    return {'definition_hash': identity(p),
            'geometry_hash': identity([{'id': x['id'], 'geometry': x['geometry']} for x in p['parts']]),
            'physical_hash': identity({'parts': physical_parts, 'interfaces': p['interfaces'], 'energy': p['energy'], 'requirements': p['requirements'], 'assumptions': p['assumptions'], 'required_roles': p['required_roles'], 'allowed_contacts': p.get('allowed_contacts', [])}),
            'energy_hash': identity({'energy': p['energy'], 'sources': [{'id': x['id'], 'source': x['source']} for x in p['parts'] if x['role'] in ('solar', 'storage', 'power', 'controller', 'feedback', 'input')]})}


class Assemblies:
    def __init__(self, app):
        self.app = app
        self.store = app.store
        self.root = self.store.root / 'product-assemblies'
        with self.store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS assembly_revisions(owner TEXT,revision INTEGER,operation TEXT,source_message TEXT,payload TEXT,hashes TEXT,created REAL,PRIMARY KEY(owner,revision),UNIQUE(owner,operation));
            CREATE TABLE IF NOT EXISTS assembly_goals(owner TEXT PRIMARY KEY,payload TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS assembly_files(owner TEXT,id TEXT,revision INTEGER,name TEXT,digest TEXT,bytes INTEGER,kind TEXT,source TEXT,created REAL,PRIMARY KEY(owner,id));
            CREATE TABLE IF NOT EXISTS assembly_verifications(owner TEXT,id TEXT,revision INTEGER,physical_hash TEXT,report TEXT,artifacts TEXT,PRIMARY KEY(owner,id));
            ''')

    def revisions(self, owner):
        self.app.products.require(owner)
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM assembly_revisions WHERE owner=? ORDER BY revision', (owner,)).fetchall()
        out = []
        for row in rows:
            r = dict(row); r['payload'] = json.loads(r['payload']); r['hashes'] = json.loads(r['hashes'])
            try:
                self.app.products.message(owner, r['source_message']); r['source_valid'] = True
            except ValueError:
                r['source_valid'] = False
            out.append(r)
        return out

    def get(self, owner, revision=None):
        rows = self.revisions(owner)
        r = next((x for x in reversed(rows) if (revision is None and x['source_valid']) or x['revision'] == revision), None)
        if not r:
            raise ValueError('ASSEMBLY_NOT_FOUND')
        return r

    def write(self, owner, body):
        self.app.products.require(owner)
        source = body['source_message_id']; self.app.products.message(owner, source)
        op = body['operation_id']
        if not isinstance(op, str) or not ID.fullmatch(op):
            raise ValueError('ASSEMBLY_OPERATION_ID')
        p = validate(body['payload']); hashes = identities(p)
        with self.app.conversations.lock:
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                old = db.execute('SELECT revision,payload,source_message FROM assembly_revisions WHERE owner=? AND operation=?', (owner, op)).fetchone()
                if old:
                    if old['payload'] != canonical(p) or old['source_message'] != source:
                        raise ValueError('ASSEMBLY_OPERATION_CONFLICT')
                    revision = old['revision']
                else:
                    current = db.execute('SELECT COALESCE(MAX(revision),0) FROM assembly_revisions WHERE owner=?', (owner,)).fetchone()[0]
                    if body.get('expected_revision') != current:
                        raise ValueError('ASSEMBLY_REVISION_CONFLICT: current revision=' + str(current) + '; read assembly_inspect and reconcile the current assembly before resubmitting with expected_revision. No revision was written.')
                    revision = current + 1
                    db.execute('INSERT INTO assembly_revisions VALUES(?,?,?,?,?,?,?)', (owner, revision, op, source, canonical(p), canonical(hashes), time.time()))
            self.app.conversations.event(owner, 'assembly-' + str(revision), {'type': 'assembly_revision', 'revision': revision, **hashes})
        return self.get(owner, revision)

    def register(self, owner, body):
        if type(body.get('revision')) is not int or body['revision'] < 1:
            current = self.get(owner)
            raise ValueError('PRODUCT_FILE_REVISION_REQUIRED: publish_file requires integer revision (assembly version, not proposal version); current assembly revision=' + str(current['revision']) + '. Read assembly_inspect, then supply revision, file_path and file_kind. No file was published.')
        if not isinstance(body.get('path'), str) or not body['path'].strip():
            raise ValueError('PRODUCT_FILE_PATH_REQUIRED: supply an existing workspace-relative file_path; no file was published')
        record = self.get(owner, body['revision'])
        if not record['source_valid']:
            raise ValueError('ASSEMBLY_SOURCE_RECALLED')
        rel = body['path']; base = self.store.root.parent / 'participants' / owner
        if not isinstance(rel, str) or Path(rel).is_absolute() or '..' in Path(rel).parts or any(x.startswith('.') for x in Path(rel).parts):
            raise PermissionError('PRODUCT_FILE_PATH_DENIED')
        path = base / rel
        kind = body.get('kind', 'document')
        if kind not in ('document', 'geometry', 'electronics', 'firmware', 'energy', 'source'):
            raise ValueError('PRODUCT_FILE_KIND: choose document, geometry, electronics, firmware, energy or source. No file was published.')
        if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
            raise PermissionError('PRODUCT_FILE_PATH_DENIED')
        if not path.is_file():
            raise ValueError('PRODUCT_FILE_NOT_FOUND: file_path must name an existing file relative to this conversation workspace; check the actual filename before publishing')
        if path.suffix.lower() not in FILE_TYPES:
            raise ValueError('PRODUCT_FILE_TYPE_UNSUPPORTED')
        if path.stat().st_size > 80 * 1024 * 1024:
            raise ValueError('PRODUCT_FILE_SIZE_LIMIT')
        data = path.read_bytes(); digest = hashlib.sha256(data).hexdigest()
        key = identity({'revision': record['revision'], 'path': rel, 'digest': digest})[:32]
        dest = self.root / owner / 'files' / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with dest.open('xb') as f: f.write(data)
        except FileExistsError:
            if hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
                raise ValueError('PRODUCT_FILE_HASH_MISMATCH')
        with self.store.connect() as db:
            prior = db.execute('SELECT kind FROM assembly_files WHERE owner=? AND id=?', (owner,key)).fetchone()
            if prior and prior['kind'] != kind:
                raise ValueError('PRODUCT_FILE_KIND_CONFLICT: this exact file is already registered with another kind')
            db.execute('INSERT OR IGNORE INTO assembly_files VALUES(?,?,?,?,?,?,?,?,?)', (owner, key, record['revision'], path.name, digest, len(data), kind, rel, time.time()))
        self.app.conversations.event(owner, 'assembly-file-' + key, {'type': 'assembly_file', 'id': key, 'revision': record['revision'], 'name': path.name, 'sha256': digest, 'kind': kind})
        return {'id': key, 'sha256': digest, 'name': path.name, 'revision': record['revision']}

    def file(self, owner, key):
        self.app.products.require(owner)
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM assembly_files WHERE owner=? AND id=?', (owner, key)).fetchone()
        if not row:
            raise PermissionError('PRODUCT_FILE_DENIED')
        p = self.root / owner / 'files' / row['id']
        if hashlib.sha256(p.read_bytes()).hexdigest() != row['digest']:
            raise ValueError('PRODUCT_FILE_HASH_MISMATCH')
        return p, dict(row)

    def set_goal(self, owner, body):
        self.app.products.require(owner)
        goal=body.get('goal')
        if not isinstance(goal,dict) or set(goal)-{'min_revision','required_paths'}!={'required_roles','file_kinds','min_parts','max_continuations'}:
            raise ValueError('DELIVERY_GOAL_SCHEMA')
        if not isinstance(goal['required_roles'],list) or not isinstance(goal['file_kinds'],list) or not all(isinstance(x,str) for x in goal['required_roles']+goal['file_kinds']) or not set(goal['required_roles'])<=ROLES or not set(goal['file_kinds'])<={'document','source','energy','firmware','electronics'}:
            raise ValueError('DELIVERY_GOAL_REQUIREMENTS')
        if type(goal['min_parts']) is not int or not 1<=goal['min_parts']<=96 or type(goal['max_continuations']) is not int or not 0<=goal['max_continuations']<=12:
            raise ValueError('DELIVERY_GOAL_LIMIT')
        if 'min_revision' in goal and (type(goal['min_revision']) is not int or goal['min_revision']<1):
            raise ValueError('DELIVERY_GOAL_REVISION')
        paths=goal.get('required_paths',[])
        if not isinstance(paths,list) or len(paths)>8 or any(not isinstance(p,str) or not p or len(p)>240 or Path(p).is_absolute() or str(Path(p))!=p or '..' in Path(p).parts or any(x.startswith('.') for x in Path(p).parts) or Path(p).suffix.lower() not in FILE_TYPES for p in paths):
            raise ValueError('DELIVERY_GOAL_PATHS')
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO assembly_goals VALUES(?,?,?)',(owner,canonical(goal),time.time()))
        self.app.conversations.event(owner,'delivery-goal-'+identity(goal),{'type':'delivery_goal','goal':goal,'source':'operator'})
        return self.projection(owner)

    def observe_delivery(self, owner, projection):
        with self.store.connect() as db:row=db.execute('SELECT payload FROM assembly_goals WHERE owner=?',(owner,)).fetchone()
        if not row:return None
        goal=json.loads(row['payload']);missing=[];current=projection.get('current')
        if not current:missing.append('no_current_assembly')
        else:
            if current['revision']<goal.get('min_revision',1):missing.append('requested_new_revision_not_published')
            parts=current['payload']['parts'];roles={p['role'] for p in parts}
            missing+=['missing_role:'+r for r in goal['required_roles'] if r not in roles]
            if len(parts)<goal['min_parts']:missing.append('too_few_parts')
            if not projection.get('digital_model_available'):missing.append('current_native_checks_not_passed')
            model=next((j for j in projection.get('jobs',[]) if not j['stale'] and j['status']=='SUCCEEDED'),None)
            if not model or not (model.get('result') or {}).get('energy',{}).get('calculation_passed'):missing.append('current_energy_screen_not_passed')
            normal=((model or {}).get('result') or {}).get('energy',{}).get('scenarios',{}).get('normal',{})
            if normal.get('accepted_events',0)<=0:missing.append('no_successful_service_event_in_normal_scenario')
            files={f['kind'] for f in projection.get('files',[]) if not f['stale'] and f.get('integrity')}
            missing+=['missing_published_file:'+k for k in goal['file_kinds'] if k not in files]
            paths={f.get('source') for f in projection.get('files',[]) if not f['stale'] and f.get('integrity')}
            missing+=['missing_published_path:'+p for p in goal.get('required_paths',[]) if p not in paths]
        return {'goal':goal,'passed':not missing,'missing':missing,
                'assembly_revision':current['revision'] if current else None,
                'publication_contract':{'action':'publish_file','revision':current['revision'] if current else None,'file_path':'existing workspace-relative file','file_kind':goal['file_kinds']},
                'scope':'Bounded digital delivery observation; visual, manufacturing and hardware acceptance remain separate.',
                'max_continuations':goal['max_continuations']}

    def projection(self, owner, include_delivery=True):
        rows = self.revisions(owner)
        current = next((r for r in reversed(rows) if r['source_valid']), None)
        if not current:
            empty={'current':None,'revisions':rows,'files':[],'checks':[]}
            return {**empty,'delivery':self.app.deliverables.inspect(owner)['verdict'] if include_delivery and hasattr(self.app,'deliverables') else self.observe_delivery(owner,empty)}
        with self.store.connect() as db:
            files = [dict(r) for r in db.execute('SELECT * FROM assembly_files WHERE owner=? ORDER BY created', (owner,))]
        for f in files:
            f['stale'] = f['revision'] != current['revision']
            path=self.root/owner/'files'/f['id']
            f['integrity']=path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==f['digest']
        jobs = [j for j in self.app.engineering.jobs(owner) if j['engine'] == 'product-model'] if hasattr(self.app, 'engineering') else []
        for j in jobs:
            h = j.get('assembly_hashes', {})
            j['stale'] = h.get('definition_hash') != current['hashes']['definition_hash']
            j['geometry_current'] = h.get('geometry_hash') == current['hashes']['geometry_hash']
            j['physical_current'] = h.get('physical_hash') == current['hashes']['physical_hash']
            j['artifact_integrity'] = False
            if j['status'] == 'SUCCEEDED':
                try:
                    artifacts = (j.get('result') or {}).get('artifacts', [])
                    for artifact in artifacts:
                        self.app.engineering.artifact(owner, j['id'], artifact['name'])
                    j['artifact_integrity'] = bool(artifacts)
                except (ValueError, PermissionError, OSError):
                    pass
        required = set(current['payload']['required_roles'])
        roles = {p['role'] for p in current['payload']['parts']}
        missing = sorted(required - roles)
        checks = [{'id': 'required-parts', 'passed': not missing, 'missing_roles': missing}]
        model = next((j for j in jobs if not j['stale'] and j['artifact_integrity'] and j['status'] == 'SUCCEEDED' and j.get('result', {}).get('digital_checks_passed')), None)
        checks.append({'id': 'current-native-model', 'passed': bool(model), 'job_id': model['id'] if model else None})
        checks.append({'id':'energy-budget-screen','passed':bool(model and model['result'].get('energy',{}).get('calculation_passed')),
                       'scope':'Daily energy and storage screening; event availability and cold start must be read separately.'})
        normal=model['result'].get('energy',{}).get('scenarios',{}).get('normal',{}) if model else {}
        checks.append({'id':'normal-service-screen','passed':normal.get('accepted_events',0)>0,
                       'accepted_events':normal.get('accepted_events'),
                       'scope':'At least one completed event in the conditional normal trajectory; no all-event or hardware guarantee.'})
        checks += [{'id': name, 'passed': False, 'status': 'NOT_EVALUATED'} for name in ('product-electrical-verification', 'target-firmware-verification', 'hardware-measurements')]
        from .product_evidence import projection
        verifications=projection(self,owner,current)
        integrated=next((v for v in reversed(verifications) if v['integrity'] and not v['stale']),None)
        if integrated:
            checks=[c for c in checks if c['id']!='target-firmware-verification']
            checks += [{'id':'native-electrical-rules','passed':True,'verification_id':integrated['id']},
                       {'id':'cross-domain-interfaces','passed':True,'verification_id':integrated['id']},
                       {'id':'target-firmware-verification','passed':True,'verification_id':integrated['id']}]
        # Do not elevate generated files, software exit or LLM statements to engineering acceptance.
        result={'current': current, 'revisions': rows, 'files': files, 'jobs': jobs, 'checks': checks,
                'digital_model_available': bool(model) and not missing, 'verifications':verifications,
                'integrated_digital_checks_passed':bool(integrated), 'engineering_verified': False, 'hardware_verified': False}
        result['delivery']=self.app.deliverables.inspect(owner)['verdict'] if include_delivery and hasattr(self.app,'deliverables') else self.observe_delivery(owner,result)
        return result
