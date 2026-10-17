"""Versioned product methods. Plugins package resources; they grant no permissions.

Only frozen, operator-owned resources can become protected model context. Global
skill folders, participant files and tool-returned instructions are never scanned.
"""
import hashlib
import json
import re
import time
from pathlib import Path
from .store import canonical, identity
from .runtime_config import PI

SOURCE = PI / 'packages/bf-harness/resources'
MAX_ACTIVE_BYTES = 60000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_file(root, name):
    if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('RESOURCE_PATH_INVALID')
    path = root / name
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('RESOURCE_FILE_UNAVAILABLE')
    return path


def source_bundle():
    from .engineering import SKILLS
    files = {str(p.relative_to(SOURCE)): p.read_bytes() for p in sorted(SOURCE.rglob('*')) if p.is_file()}
    plugins = json.loads(files['plugins.json'])['plugins']
    entries = []
    for plugin in plugins:
        for item in plugin['skills']:
            upstream = item.get('upstream_skill')
            if upstream:
                if upstream not in files: raise ValueError('SKILL_UPSTREAM_MISSING: '+upstream)
                # One pinned source package supplies the professional manual.
                # Only its entry document is activated; references stay paged.
                # The complete upstream package stays frozen and readable.
                # Its manual is loaded for the actual operation, not every request.
            content = files[item['path']]
            entries.append({**item, 'plugin_id': plugin['id'], 'version': plugin['version'],
                            'sha256': digest(content), 'adapter': plugin['adapter'],
                            **({'upstream_sha256':digest(files[upstream])} if upstream else {})})
    # Existing engine manuals remain the implementation's single source. The
    # frozen copy replaces runtime reads of mutable global skill installations.
    for key, content in sorted(SKILLS.items()):
        if key == 'pcb-offline-routing': continue  # legacy jlceda contract
        name = 'engines/' + key + '/SKILL.md'
        description = content.splitlines()[0].lstrip('# ')
        text = '---\nname: ' + key + '\ndescription: ' + json.dumps(description, ensure_ascii=False) + '\n---\n' + content
        files[name] = text.encode()
        entries.append({'id': key, 'description': description, 'path': name, 'plugin_id': 'bf-engineering',
                        'version': '1.1.0', 'sha256': digest(files[name]), 'adapter': 'bf-engineering-v1'})
    plugins.append({'id':'bf-engineering','version':'1.1.0','adapter':'bf-engineering-v1','tools':['bf_engineering'],
                    'permissions':'existing owner-bound backend authority; no new grants',
                    'skills':[{k:x[k] for k in ('id','description','path')} for x in entries if x['plugin_id']=='bf-engineering']})
    ids = [x['id'] for x in entries]
    if len(ids) != len(set(ids)): raise ValueError('SKILL_ID_COLLISION')
    for entry in entries:
        if not re.fullmatch(r'[a-z0-9-]+', entry['id']): raise ValueError('SKILL_ID_INVALID')
    manifest = {'schema_version': 'bf-resource-manifest-v1', 'skills': entries, 'plugins': plugins,
                'files': {name: digest(value) for name, value in sorted(files.items())},
                'policy': 'frozen project resources; no global discovery or executable plugin hooks'}
    manifest['sha256'] = identity(manifest)
    return manifest, files


def freeze_resources(root, bundle):
    manifest, files = bundle
    root.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(value)
    (root / 'manifest.json').write_text(canonical(manifest))
    verify(root, manifest['sha256'])


def verify(root, expected=None):
    manifest = json.loads(safe_file(root, 'manifest.json').read_text())
    if identity({k:v for k,v in manifest.items() if k != 'sha256'}) != manifest['sha256']:
        raise ValueError('RESOURCE_MANIFEST_TAMPER')
    if expected and manifest['sha256'] != expected: raise ValueError('RESOURCE_VERSION_MISMATCH')
    for name, sha in manifest['files'].items():
        if digest(safe_file(root, name).read_bytes()) != sha: raise ValueError('RESOURCE_CONTENT_TAMPER: ' + name)
    return manifest


def frozen_for(db, owner):
    row = db.execute('SELECT harness FROM conversations WHERE id=?', (owner,)).fetchone()
    if not row or not row['harness']: return None
    harness = Path(row['harness'])
    # The conversation path is server-owned, never taken from tool parameters.
    value = json.loads((harness / 'manifest.json').read_text())
    if not value.get('resource_manifest'): return None
    if value.get('schema_version') in ('bf-design-controller-v1','bf-repository-controller-v2'):
        if 'H-'+identity({k:v for k,v in value.items() if k!='harness_id'})!=value['harness_id']:
            raise ValueError('HARNESS_MANIFEST_TAMPER')
    elif identity({k:v for k,v in value.items() if k != 'identity'}) != value['identity']:
        raise ValueError('HARNESS_MANIFEST_TAMPER')
    root = harness / 'resources'
    return root, verify(root, value['resource_manifest']['sha256'])


def active_records(store, owner):
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='skill_activations'").fetchone(): return []
        frozen = frozen_for(db, owner)
        if not frozen: return []
        root, manifest = frozen
        rows = db.execute('SELECT skill_id FROM skill_activations WHERE owner=? AND manifest=? AND active=1 ORDER BY updated',
                          (owner, manifest['sha256'])).fetchall()
    by_id = {x['id']: x for x in manifest['skills']}
    return [{**by_id[row['skill_id']], 'manifest_sha256': manifest['sha256'],
             'content': safe_file(root, by_id[row['skill_id']]['path']).read_text()} for row in rows]


class SkillResources:
    def __init__(self, app):
        self.app, self.store = app, app.store
        with self.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS skill_activations(
                owner TEXT NOT NULL, manifest TEXT NOT NULL, skill_id TEXT NOT NULL,
                active INTEGER NOT NULL, updated REAL NOT NULL,
                PRIMARY KEY(owner,manifest,skill_id))''')

    def catalog(self, owner):
        self.app.conversations.get(owner)
        with self.store.connect() as db: frozen = frozen_for(db, owner)
        manifest = frozen[1] if frozen else source_bundle()[0]
        with self.store.connect() as db:
            records = db.execute('SELECT skill_id,manifest,active FROM skill_activations WHERE owner=? ORDER BY updated DESC, manifest=? DESC',
                                 (owner, manifest['sha256'])).fetchall()
        latest = {}
        for row in records:
            latest.setdefault(row['skill_id'], row)
        prior = [key for key,row in latest.items() if row['active'] and row['manifest'] != manifest['sha256']]
        return {'schema_version': 'bf-skill-catalog-v1', 'manifest_sha256': manifest['sha256'],
                'previous_active': [x for x in prior if x in {s['id'] for s in manifest['skills']}],
                'frozen': bool(frozen), 'skills': manifest['skills'], 'plugins': manifest['plugins'],
                'active': [{k:v for k,v in x.items() if k != 'content'} for x in active_records(self.store, owner)]}

    def action(self, owner, body):
        action = body.get('action')
        fields = {'catalog': set(), 'activate': {'skill_id'}, 'deactivate': {'skill_id'},
                  'resource': {'path', 'offset', 'limit', 'offset_unit'}}
        if action not in fields: raise ValueError('SKILL_ACTION_INVALID')
        unexpected = set(body) - (fields[action] | {'action','session_id'})
        if unexpected: raise ValueError('SKILL_UNEXPECTED_FIELDS: '+','.join(sorted(unexpected))+'; '+action+' accepts '+','.join(sorted(fields[action]))+'; activate example={"action":"activate","skill_id":"easyeda-agent"}')
        catalog = self.catalog(owner)
        if action == 'catalog': return catalog
        if hasattr(self.app,'engineering') and self.app.engineering.tasks.binding(owner):
            raise ValueError('SKILL_PRODUCT_ONLY: frozen research methods retain their existing interface')
        with self.store.connect() as db: frozen = frozen_for(db, owner)
        if not frozen: raise ValueError('SKILL_FROZEN_RUN_REQUIRED: resume with a resource-enabled harness')
        root, manifest = frozen
        if action == 'resource':
            name = body.get('path')
            if name not in manifest['files']: raise ValueError('RESOURCE_NOT_FOUND: use an exact path from the frozen skill')
            unit=body.get('offset_unit','lines')
            offset, limit = body.get('offset', 0), body.get('limit', 12000 if unit=='characters' else 200)
            if unit not in ('lines','characters') or type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= (18000 if unit=='characters' else 400):
                raise ValueError('RESOURCE_RANGE_INVALID')
            text=safe_file(root, name).read_text()
            parts=text if unit=='characters' else text.splitlines()
            content=parts[offset:offset+limit] if unit=='characters' else '\n'.join(parts[offset:offset+limit])
            return {'path': name, 'sha256': manifest['files'][name], 'offset': offset, 'offset_unit':unit,'total':len(parts),
                    'content': content, 'next_offset':offset+limit if offset+limit<len(parts) else None,'manifest_sha256': manifest['sha256']}
        key = body.get('skill_id')
        entry = next((x for x in manifest['skills'] if x['id'] == key), None)
        if not entry: raise ValueError('SKILL_NOT_FOUND: ' + str(key) + '; available=' + ','.join(x['id'] for x in manifest['skills']))
        content = safe_file(root, entry['path']).read_text()
        active = active_records(self.store, owner)
        already_active = any(x['id'] == key and x['sha256'] == entry['sha256'] for x in active)
        if action == 'activate' and sum(len(x['content'].encode()) for x in active if x['id'] != key) + len(content.encode()) > MAX_ACTIVE_BYTES:
            raise ValueError('ACTIVE_SKILL_CONTEXT_LIMIT: deactivate finished methods before loading more')
        if not (action == 'activate' and already_active):
            with self.store.connect() as db:
                db.execute('INSERT OR REPLACE INTO skill_activations VALUES(?,?,?,?,?)',
                           (owner, manifest['sha256'], key, int(action == 'activate'), time.time()))
        value = {**entry, 'schema_version': 'bf-skill-activation-v1', 'active': action == 'activate',
                 'manifest_sha256': manifest['sha256'], 'content': content if action == 'activate' and not already_active else None,
                 'already_active': already_active, 'body_in_protected_skill_context': action == 'activate',
                 'resources': [p for p in manifest['files'] if p.startswith(str(Path(entry['path']).parent)+'/') and p != entry['path']] + ([entry['upstream_skill']] if entry.get('upstream_skill') else []),
                 'status': 'loaded_not_execution', 'engineering_passed': False}
        self.store.event(owner, owner, 'skill_' + action, {k:v for k,v in value.items() if k != 'content'})
        return value
