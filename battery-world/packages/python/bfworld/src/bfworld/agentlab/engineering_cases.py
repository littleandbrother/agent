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
        self.catalog=catalog;self.store=catalog.store;self.root=self.store.root/'engineering-case-files'
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS engineering_case_releases(owner TEXT,id TEXT,version TEXT,payload TEXT,created REAL,PRIMARY KEY(owner,id,version))')

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
            for f in g['files']:
                rel=Path(f['path']);path=base/rel
                if rel.is_absolute() or '..' in rel.parts or any(x.startswith('.') for x in rel.parts) or path.is_symlink() or not path.resolve().is_relative_to(base):raise PermissionError('CASE_PATH_DENIED')
                name=f.get('name') or rel.name
                if Path(name).name!=name or name in names:raise ValueError('CASE_FILE_NAME_INVALID')
                names.add(name);data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
                if f.get('sha256')!=sha:raise ValueError('CASE_SOURCE_HASH_MISMATCH')
                f.update(name=name,bytes=len(data));pending.append((sha,name,data))
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
        for row in rows:
            m=json.loads(row['payload']);case_id=m['id']+'-'+m['version']
            for g in m['groups']:
                rid='case-'+case_id+'-'+g['id'];outputs=[]
                apply=dict(state='case',reason='工程案例 '+m['version']+' · '+g['scope']+'；独立于 Agent 装配验收',changed_inputs=[])
                for f in g['files']:
                    key='case/'+rid+'/'+f['name'];p=self.root/identity(owner)/f['sha256']/f['name'];ok,error=self.catalog._integrity(p,f['sha256'])
                    record=dict(id=key,result_id=rid,name=f['name'],sha256=f['sha256'],bytes=f['bytes'],domain=g['domain'],role=role(f['name']),created_revision=None,applicability=apply,integrity=ok,error=error,status='PUBLISHED',url='/api/results/file?'+urlencode({'session':owner,'id':key}),case_id=m['id'],case_version=m['version'],source_path=f['path'])
                    outputs.append(record);files.append(record);paths[key]=p
                results.append(dict(id=rid,kind=g['kind'],domain=g['domain'],label=g['title'],created=row['created'],status='PUBLISHED',error=None,source_type='engineering-case',created_revision=None,case_id=m['id'],case_title=m.get('title',m['id']),case_version=m['version'],applicability=apply,design_inputs={'sha256':m['design_sha256']},inputs=g.get('inputs',{}),conditions={},interfaces={},metrics=flatten_metrics(g.get('metrics',{})),checks=g.get('checks',{}),design_status=g.get('design_status'),scope=g['scope'],files=outputs,source_files=[],source_sha256=identity(m),readback_passed=False,hardware_verified=False,autonomous_agent_verified=False))
        return results,files,paths

    def file(self,owner,key):
        self.catalog.sources.require(owner);_,files,paths=self.collect(owner)
        f=next((f for f in files if f['id']==key),None)
        if not f:raise PermissionError('RESULT_FILE_NOT_FOUND')
        if not f['integrity']:raise ValueError('RESULT_FILE_INVALID')
        return paths[key],f['name']
