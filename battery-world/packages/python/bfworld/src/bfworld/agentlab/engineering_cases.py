"""Owner-scoped, immutable engineering case publications.

Case versions are distinct from Agent assembly versions. Publishing a solver
receipt never promotes it to product acceptance or autonomous Agent evidence.
"""
import hashlib,json,re,time
from pathlib import Path
from .store import canonical,identity
from .result_sources import materialize

ID=re.compile(r'^[a-zA-Z][a-zA-Z0-9_.-]{0,79}$')
class EngineeringCases:
    def __init__(self,catalog):
        self.catalog=catalog;self.store=catalog.store
        self.legacy_root=self.store.root/'engineering-case-files'
        self.root=self.legacy_root
        # An operator can keep immutable deliverables outside a cloud-synced
        # Documents directory. Old case IDs and hashes remain usable in place.
        config=self.store.root/'engineering-case-storage.json'
        if config.is_file():
            value=json.loads(config.read_text());root=Path(value.get('root',''))
            if value.get('schema_version')!='bf-engineering-case-storage-v1' or not root.is_absolute():
                raise ValueError('CASE_STORAGE_CONFIG_INVALID')
            self.root=root.resolve()
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS engineering_case_releases(owner TEXT,id TEXT,version TEXT,payload TEXT,created REAL,PRIMARY KEY(owner,id,version))')
            db.execute('CREATE TABLE IF NOT EXISTS engineering_case_retirements(owner TEXT,id TEXT,version TEXT,receipt TEXT,created REAL,PRIMARY KEY(owner,id,version))')

    def retired(self, owner):
        """Retention is separate from immutable scientific publication payloads."""
        with self.store.connect() as db:
            return {(r['id'], r['version']) for r in db.execute(
                'SELECT id,version FROM engineering_case_retirements WHERE owner=?', (owner,))}

    def archive_path(self,owner,sha,name):
        """Prefer the configured archive; never hide corruption with fallback."""
        path=self.root/identity(owner)/sha/name
        if path.exists() or path.is_symlink() or self.root==self.legacy_root:
            return path
        return self.legacy_root/identity(owner)/sha/name

    def publish(self,owner,base,manifest):
        """Local coordinator import only; no unauthenticated publish endpoint."""
        self.catalog.sources.require(owner);base=Path(base).resolve();m=json.loads(canonical(manifest))
        if m.get('schema_version')!='bf-engineering-case-v1' or not ID.fullmatch(m.get('id','')) or not ID.fullmatch(m.get('version','')):raise ValueError('CASE_ID_INVALID')
        if m.get('authority')!='operator-assisted' or m.get('hardware_verified') is not False or m.get('autonomous_agent_verified') is not False:raise ValueError('CASE_CLAIM_INVALID')
        if not re.fullmatch('[a-f0-9]{64}',m.get('design_sha256','')):raise ValueError('CASE_DESIGN_HASH_REQUIRED')
        groups=m.get('groups',[])
        if not groups or len(groups)>32:raise ValueError('CASE_GROUPS_INVALID')
        used=set();pending=[]
        for g in groups:
            if not ID.fullmatch(g.get('id','')) or g['id'] in used or g.get('domain') not in ('mechanical','circuit','firmware','system'):raise ValueError('CASE_GROUP_INVALID')
            used.add(g['id']);names=set()
            if 'reference_only' in g and type(g['reference_only']) is not bool:
                raise ValueError('CASE_REFERENCE_INVALID')
            if g.get('reference_only') and (not isinstance(g.get('source_revision'),str) or not 0<len(g['source_revision'])<=80):
                raise ValueError('CASE_REFERENCE_REVISION_REQUIRED')
            if not isinstance(g.get('files'),list) or not g['files']:raise ValueError('CASE_FILES_INVALID')
            # Validate every path before opening panel provenance or any bytes.
            for f in g['files']:
                if 'label' in f and (not isinstance(f['label'],str) or not 0<len(f['label'])<=160):
                    raise ValueError('CASE_FILE_LABEL_INVALID')
                if 'sections' in f and (not isinstance(f['sections'],list) or not f['sections'] or
                    any(s not in ('schematic','pcb','mechanical','simulation','bom','documents') for s in f['sections'])):
                    raise ValueError('CASE_FILE_SECTIONS_INVALID')
                rel=Path(f['path']);path=base/rel
                if rel.is_absolute() or '..' in rel.parts or any(x.startswith('.') for x in rel.parts) or path.is_symlink() or not path.resolve().is_relative_to(base):raise PermissionError('CASE_PATH_DENIED')
            story=g.get('evidence_story')
            if story is not None:
                if (not isinstance(story,dict) or type(story.get('order')) is not int or
                    story['order'] not in range(1,7) or story.get('baseline_id')!=m['id'] or
                    story.get('baseline_version')!=m['version'] or
                    story.get('baseline_source_identity')!=m['design_sha256'] or
                    not re.fullmatch('[a-f0-9]{64}',story.get('source_identity','')) or
                    not all(isinstance(story.get(k),str) and 0<len(story[k])<=2000 for k in ('title','question','conclusion')) or
                    not all(isinstance(story.get(k,''),str) and len(story.get(k,''))<=2000 for k in ('baseline_conclusion','component_summary')) or
                    not isinstance(story.get('dependencies'),list) or not all(isinstance(x,str) and len(x)<=1024 for x in story['dependencies']) or
                    not isinstance(story.get('limitations'),list) or not all(isinstance(x,str) for x in story['limitations']) or
                    story.get('figure') not in {f['path'] for f in g['files']}):
                    raise ValueError('CASE_EVIDENCE_STORY_INVALID')
                panels=story.get('panels',[])
                if not isinstance(panels,list) or len(panels)>26:raise ValueError('CASE_EVIDENCE_PANEL_BOUNDS')
                paths_in_group={f['path']:f for f in g['files']}
                panel_ids=set()
                for panel in panels:
                    if (not isinstance(panel,dict) or panel.get('id') in panel_ids or
                        not re.fullmatch(str(story['order'])+'[a-z]',panel.get('id','')) or
                        panel.get('label')!=panel['id'][1] or panel.get('status') not in ('available','missing','not_applicable') or
                        not all(isinstance(panel.get(k),str) and 0<len(panel[k])<=2000 for k in ('title','question','caption','evidence_kind')) or
                        not re.fullmatch('[a-f0-9]{64}',panel.get('source_identity','')) or
                        any(panel.get(k) not in paths_in_group for k in ('figure','pdf','svg','provenance')) or
                        not isinstance(panel.get('dependencies'),list) or not panel['dependencies'] or
                        len(set(panel['dependencies']))!=len(panel['dependencies']) or
                        not all(isinstance(x,str) and x in paths_in_group for x in panel['dependencies']) or
                        (panel['status']!='available' and not panel.get('reason'))):
                        raise ValueError('CASE_EVIDENCE_PANEL_INVALID')
                    panel_ids.add(panel['id'])
                    provenance=json.loads((base/panel['provenance']).read_text())
                    if any(provenance.get(k)!=panel.get(k) for k in ('id','label','title','question','caption','status','reason','evidence_kind','source_identity')):
                        raise ValueError('CASE_PANEL_PROVENANCE_MISMATCH')
                    records=panel.get('source_records',[])
                    if (not records or {s.get('published_path') for s in records}!=set(panel['dependencies']) or
                       len({s.get('id') for s in records})!=len(records) or any(s.get('published_path') not in panel['dependencies'] or
                       paths_in_group[s['published_path']]['sha256']!=s.get('sha256') for s in records)):
                        raise ValueError('CASE_PANEL_SOURCE_BINDING')
                    declared=[{k:v for k,v in s.items() if k!='published_path'} for s in records]
                    expected=hashlib.sha256(json.dumps(declared,sort_keys=True).encode()).hexdigest()
                    if expected!=panel['source_identity']:raise ValueError('CASE_PANEL_SOURCE_IDENTITY')
            for f in g['files']:
                rel=Path(f['path']);path=base/rel
                if rel.is_absolute() or '..' in rel.parts or any(x.startswith('.') for x in rel.parts) or path.is_symlink() or not path.resolve().is_relative_to(base):raise PermissionError('CASE_PATH_DENIED')
                name=f.get('name') or rel.name
                if Path(name).name!=name or name in names:raise ValueError('CASE_FILE_NAME_INVALID')
                names.add(name);data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
                if f.get('sha256')!=sha:raise ValueError('CASE_SOURCE_HASH_MISMATCH')
                f.update(name=name,bytes=len(data));pending.append((sha,name,data))
        stories=[g['evidence_story'] for g in groups if g.get('evidence_story')]
        if stories and sorted(s['order'] for s in stories)!=list(range(1,7)):
            raise ValueError('CASE_EVIDENCE_SEQUENCE_INVALID')
        with self.store.connect() as db:
            old=db.execute('SELECT payload FROM engineering_case_releases WHERE owner=? AND id=? AND version=?',(owner,m['id'],m['version'])).fetchone()
            if old and old['payload']!=canonical(m):raise ValueError('CASE_VERSION_IMMUTABLE')
            for sha,name,data in pending:
                p=materialize(self.root/identity(owner)/sha,name,data)
                if hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('CASE_ARCHIVE_CORRUPT')
            db.execute('INSERT OR IGNORE INTO engineering_case_releases VALUES(?,?,?,?,?)',(owner,m['id'],m['version'],canonical(m),time.time()))
        return m

    def collect(self,owner):
        from urllib.parse import urlencode
        from .product_results import role,flatten_metrics
        with self.store.connect() as db:rows=db.execute('SELECT * FROM engineering_case_releases WHERE owner=? ORDER BY created',(owner,)).fetchall()
        results=[];files=[];paths={}
        retired=self.retired(owner)
        for row in rows:
            m=json.loads(row['payload']);case_id=m['id']+'-'+m['version']
            if (m['id'],m['version']) in retired:continue
            for g in m['groups']:
                rid='case-'+case_id+'-'+g['id'];outputs=[]
                apply=dict(state='case',reason='工程案例 '+m['version']+' · '+g['scope']+'；独立于 Agent 装配验收',changed_inputs=[])
                if g.get('reference_only'):
                    apply.update(state='reference',reason='历史工程 '+g['source_revision']+' · '+g['scope'])
                for f in g['files']:
                    key='case/'+rid+'/'+f['name'];p=self.archive_path(owner,f['sha256'],f['name']);ok,error=self.catalog._integrity(p,f['sha256'])
                    record=dict(id=key,result_id=rid,name=f['name'],sha256=f['sha256'],bytes=f['bytes'],domain=g['domain'],role=role(f['name']),created_revision=None,applicability=apply,integrity=ok,error=error,status='PUBLISHED',url='/api/results/file?'+urlencode({'session':owner,'id':key}),case_id=m['id'],case_version=m['version'],source_path=f['path'])
                    record.update({k:f[k] for k in ('label','sections') if k in f})
                    if g.get('reference_only'):
                        record.update(reference_only=True,source_revision=g['source_revision'])
                    outputs.append(record);files.append(record);paths[key]=p
                story=g.get('evidence_story')
                story={**story,'file_id':next(f['id'] for f in outputs if f['source_path']==story['figure'])} if story else None
                if story and story.get('panels'):
                    bypath={f['source_path']:f for f in outputs}
                    story['panels']=[{**p,**{k+'_id':bypath[p[k]]['id'] for k in ('figure','pdf','svg','provenance')},
                                     'source_files':[bypath[s]['id'] for s in p['dependencies']]} for p in story['panels']]
                results.append(dict(evidence_story=story,id=rid,kind=g['kind'],domain=g['domain'],label=g['title'],created=row['created'],status='PUBLISHED',error=None,source_type='engineering-case',created_revision=None,case_id=m['id'],case_title=m.get('title',m['id']),case_version=m['version'],applicability=apply,design_inputs={'sha256':m['design_sha256']},inputs=g.get('inputs',{}),conditions={},interfaces={},metrics=flatten_metrics(g.get('metrics',{})),checks=g.get('checks',{}),design_status=g.get('design_status'),scope=g['scope'],files=outputs,source_files=[],source_sha256=identity(m),readback_passed=False,hardware_verified=False,autonomous_agent_verified=False))
                if g.get('reference_only'):
                    results[-1].update(reference_only=True,source_revision=g['source_revision'])
        return results,files,paths

    def file(self,owner,key):
        self.catalog.sources.require(owner)
        # A report with hundreds of panels must not rebuild and hash its whole
        # owner's catalogue for every image or exported file. Resolve only the
        # registered key, retaining the same owner and content-integrity gate.
        with self.store.connect() as db:
            rows=db.execute('SELECT payload FROM engineering_case_releases WHERE owner=? ORDER BY created',(owner,)).fetchall()
        retired=self.retired(owner)
        for row in rows:
            m=json.loads(row['payload'])
            for g in m['groups']:
                prefix='case/case-'+m['id']+'-'+m['version']+'-'+g['id']+'/'
                if not key.startswith(prefix):continue
                if (m['id'],m['version']) in retired:raise ValueError('CASE_RETIRED_BY_RETENTION_POLICY')
                name=key[len(prefix):]
                f=next((f for f in g['files'] if f['name']==name),None)
                if f is None:continue
                path=self.archive_path(owner,f['sha256'],name)
                valid,_=self.catalog._integrity(path,f['sha256'])
                if not valid:raise ValueError('RESULT_FILE_INVALID')
                return path,name
        raise PermissionError('RESULT_FILE_NOT_FOUND')
