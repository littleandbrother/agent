"""Rebuildable result read model. Jobs, assembly records and verdicts retain authority.

The index is an owner-scoped SQLite projection, not a second acceptance ledger.
Files are identified by recorded hashes; a revision number is never rewritten.
"""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import struct
import os
import tempfile
import zipfile
from urllib.parse import urlencode

from .store import canonical, identity
from .product_authority import fingerprints, dimensions

DOMAINS = {'mechanical':'机械与结构', 'circuit':'电路与 PCB', 'firmware':'固件与模型', 'system':'系统与交付'}
TASK_DOMAIN = {**dict.fromkeys(('cad','drawings','presentation','clearance','magnetics','fem','convergence','mapping'), 'mechanical'),
               **dict.fromkeys(('circuit','schematic','pcb','bom','routing','manufacturing','spice','circuit-selection','electrical-checks','pcb-checks'), 'circuit'),
               **dict.fromkeys(('firmware','firmware-resources','tinyml','flash-guide','receiver','direction','receiver-tests'), 'firmware')}


def job_kind(j):
    return (j.get('project') or {}).get('manifest', {}).get('kind') or (j.get('result') or {}).get('kind') or j['engine']


def domain(kind):
    return {'cadquery':'mechanical','product-model':'mechanical','blender':'mechanical','comsol':'mechanical',
            'spice':'circuit','jlceda':'circuit','event-transient':'circuit','beam-event':'circuit',
            'firmware-stm32l031':'firmware','mcu-firmware':'firmware','tinyml-nas':'firmware'}.get(kind,'system')


def role(name):
    suffix=Path(name).suffix.lower()
    if suffix in ('.png','.svg','.glb','.mp4') or name.endswith('preview-mesh.json'): return 'preview'
    if suffix in ('.py','.c','.h','.ld','.cir','.java','.tex') or name=='project-source.zip': return 'source'
    if suffix in ('.step','.stl','.brep','.blend','.mph','.epro2','.elf','.hex','.bin','.dsn','.ses','.net'): return 'native'
    if suffix in ('.raw','.csv','.tsv'): return 'data'
    if suffix in ('.log','.map') or name=='input.json': return 'log'
    return 'report'


def input_keys(kind, name):
    if kind=='product-model':
        if name in ('energy.json','channels.csv'):return ['energy_hash']
        if name.endswith(('.step','.stl','.brep','.glb')) or name in ('cad-readback.json',):return ['geometry_hash','interfaces']
        if role(name)=='preview':return ['geometry_hash','presentation']
        return ['definition_hash']
    if kind=='cadquery':return ['geometry_hash','interfaces']
    if kind in ('firmware-stm32l031','mcu-firmware'):return ['interfaces','energy_hash']
    return ['physical_hash']


def applicability(original, selected, keys):
    if not original or not selected or not original.get('source_valid',True) or not selected.get('source_valid',True):
        return dict(state='unbound',reason='未绑定有效装配输入；保留独立运行记录',changed_inputs=keys)
    old,new=fingerprints(original),fingerprints(selected)
    changed=[k for k in keys if old.get(k) is None or old.get(k)!=new.get(k)]
    if changed:return dict(state='stale',reason='相关输入已变化：'+', '.join(changed),changed_inputs=changed)
    if original['revision']>selected['revision']:
        return dict(state='future',reason='在所选版本之后生成；不作为该历史版本的证据',changed_inputs=[])
    return dict(state='current' if original['revision']==selected['revision'] else 'reused',
                reason='生成于此版本' if original['revision']==selected['revision'] else '相关输入未变化，可复用；保留原生成版本',changed_inputs=[])


def flatten_metrics(value, prefix='', depth=0):
    """Only recorded small scalar facts; no inferred engineering conclusions."""
    if depth>3:return []
    rows=[]
    for k,v in (value or {}).items():
        key=f'{prefix}.{k}' if prefix else k
        if k in ('artifacts','outputs','source_interfaces','checks','limitations','source','scope'):continue
        if isinstance(v,dict):rows+=flatten_metrics(v,key,depth+1)
        elif isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v):rows.append({'name':key,'value':v})
        elif k in ('bounds_mm','target','memory_fit','native_valid','readback_passed') and isinstance(v,(str,list,bool)):rows.append({'name':key,'value':v})
    return rows[:36]


class ProductResults:
    def __init__(self, app):
        self.app=app;self.store=app.store;self._checked={}
        from .result_sources import ResultSources
        self.sources=ResultSources(self)
        from .engineering_cases import EngineeringCases
        self.cases=EngineeringCases(self)
        with self.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS product_result_index (
                owner TEXT NOT NULL, result_id TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(owner,result_id))''')
            db.execute('CREATE INDEX IF NOT EXISTS product_results_owner ON product_result_index(owner)')

    def _integrity(self,path,expected):
        try:
            s=path.stat()
            if getattr(s,'st_flags',0)&0x40000000:return False,'文件未下载到本机'
            if not path.is_file() or path.is_symlink():return False,'文件缺失或链接无效'
            key=(str(path),s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,expected)
            if key not in self._checked:
                h=hashlib.sha256()
                with path.open('rb') as stream:
                    for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
                if len(self._checked)>4096:self._checked.clear()
                self._checked[key]=h.hexdigest()==expected
            return self._checked[key],'' if self._checked[key] else '文件哈希不一致'
        except OSError:return False,'文件不可读取'

    def inspect(self,owner,revision=None):
        self.sources.require(owner)
        product_enabled=self.app.products.exists(owner)
        if revision is not None and (type(revision) is not int or revision<1):raise ValueError('RESULT_REVISION_INVALID')
        revisions=self.app.assemblies.revisions(owner) if product_enabled else []
        current=next((r for r in reversed(revisions) if r['source_valid']),None)
        selected=next((r for r in revisions if r['revision']==revision),None) if revision else current
        if revision and not selected:raise ValueError('RESULT_REVISION_NOT_FOUND')
        jobs=self.app.engineering.jobs(owner);results=[];files=[]
        with self.store.connect() as db:
            for j in jobs:
                # Index immutable record bytes; projection freshness is evaluated below.
                payload={k:j.get(k) for k in ('id','engine','status','created','ended','assembly','result','error','project','parameters','event_spec')}
                sha=identity(payload)
                db.execute('''INSERT INTO product_result_index VALUES(?,?,?,?) ON CONFLICT(owner,result_id)
                    DO UPDATE SET source_sha256=excluded.source_sha256,payload=excluded.payload
                    WHERE source_sha256!=excluded.source_sha256''',(owner,j['id'],sha,canonical(payload)))
            indexed=db.execute('SELECT payload FROM product_result_index WHERE owner=? ORDER BY result_id',(owner,)).fetchall()
        live_ids={j['id'] for j in jobs}
        for record in indexed:
            j=json.loads(record['payload'])
            if j['id'] not in live_ids:continue
            k=job_kind(j);d=domain(k);old=j.get('assembly');raw=j.get('result') or {}
            old=next((r for r in revisions if old and r['revision']==old.get('revision')),old)
            outputs=[]
            for a in raw.get('artifacts',[]):
                name=a['name']
                if Path(name).name!=name:continue
                valid,error=self._integrity(self.app.engineering.root/j['id']/name,a['sha256'])
                apply=applicability(old,selected,input_keys(k,name))
                f=dict(id=j['id']+'/'+name,result_id=j['id'],name=name,sha256=a['sha256'],bytes=a['bytes'],domain=d,
                       created_revision=(old or {}).get('revision'),applies_to_revision=(selected or {}).get('revision'),
                       applicability=apply,integrity=valid,error=error,role=role(name),status=j['status'],job_id=j['id'],
                       url='/api/results/file?'+urlencode({'session':owner,'id':j['id']+'/'+name}))
                outputs.append(f);files.append(f)
            label=('受控供电 · 程序接收诊断' if raw.get('metrics',{}).get('diagnostic_only') else '门磁设计 · 全链路仿真') if k=='closed-simulation' else DOMAINS[d]
            results.append(dict(id=j['id'],kind=k,domain=d,label=label,created=j['created'],status=j['status'],error=j['error'],
                created_revision=(old or {}).get('revision'),applicability=applicability(old,selected,input_keys(k,'')),
                design_inputs=(old or {}).get('payload',{}),
                inputs=j.get('parameters') or {},interfaces=(j.get('project') or {}).get('manifest',{}).get('interfaces',{}),
                conditions=j.get('event_spec') or {},metrics=([{'name':n,'value':raw['metrics'][n]} for n in ['peak_tip_mm','peak_piezo_V','peak_storage_V','peak_supply_V','tx_completed','received_events'] if n in raw.get('metrics',{})] if k=='closed-simulation' else flatten_metrics(raw)),checks=raw.get('checks') or {},
                scope=(raw.get('summary_zh') or raw.get('scope') or '工程执行记录；尚无独立产品验收'),files=outputs,
                run_status=raw.get('run_status'),design_status=raw.get('design_status'),predicted_design_status=raw.get('predicted_design_status'),
                simulation_stages=raw.get('stages') if k=='closed-simulation' else None,
                simulation=({n:raw.get(n) for n in ('physics_hash','presentation_hash','applicability','energy_ledger','limitations','failed_stage','unreached_stages','module_diagnostic_passed')} if k=='closed-simulation' else None),
                source_files=list(((j.get('project') or {}).get('sources') or {}).keys()),
                source_sha256=identity(j),readback_passed=raw.get('readback_passed',raw.get('numerical_checks_passed',False)),
                hardware_verified=False))
        bindings=self.app.deliverables._bindings(owner) if product_enabled else {}
        with self.store.connect() as db:published=[dict(r) for r in db.execute('SELECT * FROM assembly_files WHERE owner=? ORDER BY created',(owner,))]
        for f in published:
            if f['source'].startswith('delivery-packages/'):continue # Exclude export recursion.
            old=next((r for r in revisions if r['revision']==f['revision']),None)
            tasks=[t for t,b in bindings.items() if any(x['id']==f['id'] for x in b.get('files',[]))]
            keys=sorted({k for t in tasks for k in dimensions(t)}) if tasks else ['physical_hash']
            valid,error=self._integrity(self.app.assemblies.root/owner/'files'/f['id'],f['digest'])
            d=TASK_DOMAIN.get(tasks[0],'system') if tasks else 'system'
            files.append(dict(id='file/'+f['id'],result_id='published',name=f['name'],sha256=f['digest'],bytes=f['bytes'],domain=d,
                role=role(f['name']),created_revision=f['revision'],applies_to_revision=(selected or {}).get('revision'),
                applicability=applicability(old,selected,keys),integrity=valid,error=error,status='PUBLISHED',tasks=tasks,
                url='/api/results/file?'+urlencode({'session':owner,'id':'file/'+f['id']})))
        extra,extra_files,_=self.sources.collect(owner)
        results+=extra;files+=extra_files
        case_results,case_files,_=self.cases.collect(owner)
        results+=case_results;files+=case_files
        results.sort(key=lambda r:r['created'],reverse=True)
        for f in files:
            group='current' if f['applicability']['state'] in ('current','reused') else 'history'
            if f['status'] in ('FAILED','UNKNOWN'):group='failed'
            f['archive_path']=f"成果/{f['domain']}/{group}/{f['id']}"
        inventory=self.app.deliverables.inspect(owner) if product_enabled and current else {'tasks':[],'verdict':None}
        blockers=[]
        for t in inventory['tasks']:
            if t['applicability']=='not_applicable' or (t['delivery_status']=='present' and t['validation_status']=='passed'):continue
            state='missing_files' if t['delivery_status'] in ('missing','partial') else 'stale' if t['delivery_status']=='stale' else 'failed' if t['validation_status']=='failed' else 'validator_unavailable'
            blockers.append(dict(id=t['id'],label=t['label'],state=state,detail=t['missing_files'],domain=TASK_DOMAIN.get(t['id'],'system')))
        value=dict(schema_version='bf-product-results-v1',owner=owner,revision=(selected or {}).get('revision'),current_revision=(current or {}).get('revision'),
            title=(selected or {}).get('payload',{}).get('title') or self.session_title(owner),versions=[dict(revision=r['revision'],source_valid=r['source_valid']) for r in revisions],
            verdict=inventory['verdict'] if selected==current else None,verdict_revision=(current or {}).get('revision'),results=results,files=files,blockers=blockers if selected==current else [],domains=DOMAINS,
            scope='真实执行与已发布文件的只读索引；相关输入未变化仅表示可复用，不证明产品已验收。')
        value['product_enabled']=product_enabled
        value['phase']='assembly' if current else 'engineering' if jobs else 'benchmark' if any(r['kind']=='benchmark' for r in results) else 'proposal' if results else 'empty'
        value['engineering_cases']=sorted({r['case_version'] for r in case_results})
        value['coverage']=[dict(id=d,label=label,files=sum(f['domain']==d for f in files),
            available=sum(f['domain']==d and f['integrity'] for f in files),
            current=sum(f['domain']==d and f['integrity'] and f['applicability']['state'] in ('current','reused') for f in files)) for d,label in DOMAINS.items()]
        for r in results:
            r.setdefault('source_type','engineering')
            r['presentations']=self.presentations(owner,r)
        from .design_pilot_view import projection
        pilot=projection(self.store,owner)
        if pilot['trials']:value['design_pilot']=pilot
        value['snapshot_sha256']=identity(value)
        return value

    def session_title(self,owner):
        with self.store.connect() as db:
            row=db.execute('SELECT coalesce(s.title,c.title) title FROM conversations c LEFT JOIN sidebar_entries s ON s.id=c.id WHERE c.id=?',(owner,)).fetchone()
        return row['title'] if row else owner

    @staticmethod
    def presentations(owner,result):
        """Capabilities describe files, not bespoke session names or product templates."""
        views=[]
        for f in result['files']:
            if not f['integrity']:continue
            ext=Path(f['name']).suffix.lower();kind=None
            if ext=='.glb':kind='model'
            elif f['name'].endswith('preview-mesh.json'):kind='mesh'
            elif ext in ('.png','.jpg','.jpeg','.webp','.svg'):kind='image'
            elif ext in ('.csv','.tsv','.raw') and not (ext=='.raw' and result.get('source_type')=='engineering-case'):kind='series'
            elif ext=='.pdf':kind='pdf'
            elif ext=='.mp4':kind='video'
            if kind:
                label={'model.glb':'三维模型','preview.png':'整体外观','inside.png':'内部结构','exploded.png':'爆炸视图','front.png':'正面','back.png':'背面','front.svg':'正视图','side.svg':'侧视图','top.svg':'俯视图','metrics.csv':'求解结果表','channels.csv':'仿真曲线','recorded-channels.csv':'计算波形'}.get(f['name'],f['name'])
                views.append(dict(kind=kind,file_id=f['id'],label=label))
        if result['kind']=='proposal':views.insert(0,dict(kind='proposal',label='产品方案'))
        rank={'video':-1,'model':0,'mesh':1,'proposal':0,'image':2,'series':3,'pdf':4}
        return sorted(views,key=lambda v:rank[v['kind']])

    def package(self,owner,expected_snapshot,revision=None):
        """One export for all session types, including records with no assembly."""
        catalog=self.inspect(owner,revision)
        if catalog['snapshot_sha256']!=expected_snapshot:raise ValueError('RESULT_SNAPSHOT_CHANGED_REFRESH')
        if any(not f['integrity'] for f in catalog['files']):raise ValueError('RESULT_FILE_INVALID')
        root=self.store.root/'result-archives'/identity(owner);root.mkdir(parents=True,exist_ok=True)
        dest=root/(expected_snapshot+'.zip')
        if not dest.exists():
            fd,tmp=tempfile.mkstemp(dir=root,suffix='.zip');os.close(fd)
            try:
                with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
                    z.writestr('成果清单.json',canonical(catalog))
                    z.writestr('阅读说明.txt','本包是所选会话的成果快照。未绑定装配的计算、方案与工程保留原范围；不代表产品或实物已验收。记录副本来自公开数据库，不包含私有评估或密钥。')
                    for f in catalog['files']:
                        path,_=self.file(owner,f['id']);z.write(path,f['archive_path'])
                if self.inspect(owner,revision)['snapshot_sha256']!=expected_snapshot:raise ValueError('RESULT_SNAPSHOT_CHANGED_REFRESH')
                os.replace(tmp,dest)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
        self.archive(owner,expected_snapshot)
        return dict(snapshot_sha256=expected_snapshot,files=len(catalog['files']),bytes=dest.stat().st_size,
            url='/api/results/archive?'+urlencode({'session':owner,'snapshot':expected_snapshot}))

    def archive(self,owner,snapshot):
        self.sources.require(owner)
        if not re.fullmatch('[0-9a-f]{64}',snapshot):raise PermissionError('RESULT_ARCHIVE_NOT_FOUND')
        dest=self.store.root/'result-archives'/identity(owner)/(snapshot+'.zip')
        if not dest.is_file() or dest.is_symlink():raise PermissionError('RESULT_ARCHIVE_NOT_FOUND')
        with zipfile.ZipFile(dest) as z:
            catalog=json.loads(z.read('成果清单.json'))
            original=dict(catalog);original.pop('snapshot_sha256',None)
            if catalog['owner']!=owner or identity(original)!=snapshot:raise ValueError('RESULT_ARCHIVE_MANIFEST_INVALID')
            expected={f['archive_path'] for f in catalog['files']}
            if set(z.namelist())!=expected|{'成果清单.json','阅读说明.txt'}:raise ValueError('RESULT_ARCHIVE_INVENTORY_INVALID')
            for f in catalog['files']:
                with z.open(f['archive_path']) as stream:
                    digest=hashlib.file_digest(stream,'sha256').hexdigest()
                if digest!=f['sha256']:raise ValueError('RESULT_ARCHIVE_HASH_INVALID')
        return dest

    def file(self,owner,key):
        self.sources.require(owner)
        if key.startswith('case/'):return self.cases.file(owner,key)
        if key.startswith(('record/','input/')):return self.sources.file(owner,key)
        if key.startswith('file/'):
            path,meta=self.app.assemblies.file(owner,key[5:]);return path,meta['name']
        job_id,sep,name=key.partition('/')
        if not sep or Path(name).name!=name:raise PermissionError('RESULT_FILE_NOT_FOUND')
        j=self.app.engineering.get(owner,job_id)
        meta=next((a for a in (j.get('result') or {}).get('artifacts',[]) if a['name']==name),None)
        if not meta:raise PermissionError('RESULT_FILE_NOT_FOUND')
        path=self.app.engineering.root/job_id/name
        valid,error=self._integrity(path,meta['sha256'])
        if not valid:raise ValueError('RESULT_FILE_INVALID: '+error)
        return path,name

    def source(self,owner,result_id,name=None):
        j=self.app.engineering.get(owner,result_id)
        sources=(j.get('project') or {}).get('sources',{})
        if name is None:return {'files':sorted(sources),'scope':'提交时固定的源码快照'}
        if name not in sources:raise PermissionError('RESULT_SOURCE_NOT_FOUND')
        return {'name':name,'content':sources[name],'sha256':hashlib.sha256(sources[name].encode()).hexdigest()}

    def series(self,owner,key):
        path,name=self.file(owner,key)
        if path.stat().st_size>32*1024*1024:raise ValueError('PREVIEW_TOO_LARGE_DOWNLOAD_SOURCE')
        if path.suffix=='.raw':
            data=path.read_bytes();marker=b'Values:\n' if b'Values:\n' in data else b'Binary:\n'
            if marker not in data:raise ValueError('RAW_PREVIEW_UNSUPPORTED')
            head,body=data.split(marker,1);h=head.decode()
            if 'complex' in h.split('Flags:')[1].splitlines()[0]:raise ValueError('COMPLEX_PREVIEW_DOWNLOAD_SOURCE')
            cols=[(m[0],m[1]) for m in re.findall(r'^\s*\d+\s+(\S+)\s+(\S+)\s*$',h,re.M)]
            n=int(re.search(r'No. Variables:\s*(\d+)',h)[1]);count=int(re.search(r'No. Points:\s*(\d+)',h)[1])
            if not 1<n<=64 or not 0<count<2_000_000 or len(cols)!=n:raise ValueError('RAW_PREVIEW_SIZE')
            values=[float(line.split()[-1]) for line in body.decode().splitlines() if line.split()] if marker==b'Values:\n' else list(struct.unpack('='+str(len(body)//8)+'d',body))
            if len(values)!=n*count or not all(math.isfinite(x) for x in values):raise ValueError('RAW_PREVIEW_INVALID')
            rows=[values[i:i+n] for i in range(0,len(values),n)]
            headers=[c[0] for c in cols];units=[{'time':'s','voltage':'V','current':'A','frequency':'Hz'}.get(c[1],c[1]) for c in cols]
        elif path.suffix in ('.csv','.tsv'):
            reader=csv.reader(io.StringIO(path.read_text()),delimiter='\t' if path.suffix=='.tsv' else ',')
            headers=next(reader);units=[{'s':'s','v':'V','a':'A','w':'W','j':'J','mm':'mm','m':'m','pa':'Pa'}.get(h.rsplit('_',1)[-1].lower(),'字段单位') for h in headers];rows=[];textual=False
            for row in reader:
                if len(row)!=len(headers):raise ValueError('TABLE_PREVIEW_NONNUMERIC')
                values=[]
                for x in row:
                    try:
                        value=float(x)
                        if not math.isfinite(value):raise ValueError('TABLE_PREVIEW_NONFINITE')
                        values.append(value)
                    except ValueError as e:
                        if str(e)=='TABLE_PREVIEW_NONFINITE':raise
                        textual=True;values.append(x)
                rows.append(values)
            count=len(rows)
            if not rows or len(headers)<2:raise ValueError('TABLE_PREVIEW_EMPTY')
            if textual:
                return dict(table=True,headers=headers,rows=rows[:200],total_points=count,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),scope='原始表格预览，最多显示 200 行；含分类字段，不将类别强行绘为连续曲线。')
        else:raise ValueError('SERIES_PREVIEW_UNSUPPORTED')
        # Preserve first/last and disclose downsampling; raw download is authoritative.
        step=max(1,math.ceil(len(rows)/1000));sample=rows[::step]
        if sample[-1]!=rows[-1]:sample.append(rows[-1])
        return dict(headers=headers,units=units,rows=sample,total_points=count,sample_stride=step,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),scope='原始求解器数据；等间隔抽样预览，极值判断请读取完整数据。')
