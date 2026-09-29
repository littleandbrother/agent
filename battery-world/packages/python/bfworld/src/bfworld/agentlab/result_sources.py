"""Read adapters for pre-assembly records. Never discover files by scanning workspaces.

Only public DB records and their explicitly published files are exposed. Derived
files retain a source digest and do not become experimental or product evidence.
"""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlencode

from .store import canonical, identity


def materialize(root, name, content):
    root.mkdir(parents=True, exist_ok=True)
    path=root/name
    if not path.exists():
        fd,tmp=tempfile.mkstemp(dir=root)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(content)
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    return path


class ResultSources:
    def __init__(self, catalog):
        self.catalog=catalog;self.app=catalog.app;self.store=catalog.store
        self.root=self.store.root/'result-snapshots'

    def require(self,owner):
        with self.store.connect() as db:
            found=db.execute('SELECT 1 FROM conversations WHERE id=? UNION SELECT 1 FROM jobs WHERE owner=? UNION SELECT 1 FROM principals WHERE owner=?',(owner,owner,owner)).fetchone()
            deleted=db.execute('SELECT deleted FROM sidebar_entries WHERE id=?',(owner,)).fetchone()
        if not found or owner in ('','operator'):raise PermissionError('RESULT_SESSION_NOT_FOUND')
        if deleted and deleted['deleted']:raise PermissionError('CONVERSATION_DELETED')

    def file_record(self,owner,result_id,name,content,state='unbound',d='system',status='PUBLISHED',reason=None):
        sha=hashlib.sha256(content).hexdigest()
        path=materialize(self.root/identity({'owner':owner,'result':result_id})/sha,name,content)
        valid,error=self.catalog._integrity(path,sha)
        from .product_results import role
        key='record/'+result_id+'/'+name
        return dict(id=key,result_id=result_id,name=name,sha256=sha,bytes=len(content),domain=d,role=role(name),
            created_revision=None,applicability={'state':state,'reason':reason or '会话的公开记录；未绑定产品装配，不代表整机验收','changed_inputs':[]},
            integrity=valid,error=error,status=status,source='record',
            url='/api/results/file?'+urlencode({'session':owner,'id':key})),path

    def experiments(self,owner):
        from .product_results import flatten_metrics
        results=[];files=[];paths={}
        for j in self.store.jobs(owner):
            raw=j['result'] or {};outputs=[]
            # Copy public JSON from the recorded result, never read run.private.json.
            documents={}
            if raw:
                documents['public-result.json']=canonical(raw).encode()
                if 'design' in raw:documents['design.json']=canonical(raw['design']).encode()
                if 'policy' in raw:documents['policy.py']=raw['policy'].encode()
                if 'decisions' in raw:documents['policy-decisions.json']=canonical(raw['decisions']).encode()
                rows=raw.get('channels',[])
                if rows:
                    preferred=['time_s','storage_voltage_v','input_voltage_v','harvest_current_a','load_power_w','energy_j']
                    headers=[k for k in preferred if all(type(row.get(k)) in (int,float) for row in rows)]
                    if len(headers)>1:
                        out=io.StringIO();writer=csv.writer(out);writer.writerow(headers);writer.writerows([[r[k] for k in headers] for r in rows]);documents['recorded-channels.csv']=out.getvalue().encode()
            for name,content in documents.items():
                f,path=self.file_record(owner,j['id'],name,content,d='firmware' if name=='policy.py' else 'circuit',status=j['status'])
                f['provenance']='数据库公开结果的可复算副本；波形保留原记录采样间隔'
                f['source_sha256']=identity(raw);outputs.append(f);files.append(f);paths[f['id']]=path
            result=dict(id=j['id'],kind='benchmark',domain='circuit',label='基准计算',created=j['created'],status=j['status'],error=j['error'],
                source_type='benchmark',created_revision=None,applicability={'state':'unbound','reason':'历史基准计算；未绑定产品装配，不能替代 CAD、电路板或实物验证','changed_inputs':[]},
                inputs=raw.get('design',{}),design_inputs={},interfaces={},conditions=j['request'],metrics=flatten_metrics({'summary':raw.get('summary',{}),'energy_ledger':raw.get('energy_ledger',{})}),
                checks=raw.get('checks',{}),design_status=raw.get('design_status'),fidelity=raw.get('fidelity'),
                scope=raw.get('description') or '固定计算环境的公开结果；非硬件验收。',files=outputs,source_files=[],source_sha256=identity(raw),readback_passed=False,hardware_verified=False)
            results.append(result)
        return results,files,paths

    def proposals(self,owner):
        results=[];files=[];paths={}
        for r in self.app.products.records(owner):
            if r['kind']!='proposal':continue
            rid='proposal-'+str(r['revision']);p=r['payload']
            content=canonical({'schema_version':'bf-product-proposal-v1','revision':r['revision'],'source_message_id':r['source_message'],'authority':'agent_proposal',**p}).encode()
            f,path=self.file_record(owner,rid,'proposal.json',content,state='stale' if r['stale'] else 'proposal',reason='方案记录，尚不代表工程产物或用户已批准')
            f['proposal_revision']=r['revision'];files.append(f);paths[f['id']]=path
            results.append(dict(id=rid,kind='proposal',domain='system',label='产品方案',created=r['created'],status='PUBLISHED',error=None,source_type='proposal',
                created_revision=None,proposal_revision=r['revision'],applicability=f['applicability'],inputs=p,design_inputs={},interfaces={},conditions={},metrics=[],checks={},
                scope='Agent 提出的场景、假设和验收目标。方案与装配版本分别保留。',files=[f],source_files=[],source_sha256=identity(r),readback_passed=False,hardware_verified=False))
        with self.store.connect() as db:
            attachments=db.execute('SELECT * FROM product_attachments WHERE owner=? ORDER BY created,id',(owner,)).fetchall()
        for a in attachments:
            name=a['id']+'.txt';path=self.app.products.root/owner/name
            valid,error=self.catalog._integrity(path,a['digest']);key='input/'+name
            files.append(dict(id=key,result_id='inputs',name=a['name'],sha256=a['digest'],bytes=path.stat().st_size if valid else 0,domain='system',role='report',
                created_revision=None,applicability={'state':'input','reason':'使用者提供的输入资料，不是设计结果','changed_inputs':[]},integrity=valid,error=error,status='PUBLISHED',source='input',
                url='/api/results/file?'+urlencode({'session':owner,'id':key})))
            paths[key]=path
        return results,files,paths

    def collect(self,owner):
        a,b,c=self.experiments(owner);d,e,f=self.proposals(owner)
        return a+d,b+e,{**c,**f}

    def file(self,owner,key):
        self.require(owner)
        _,files,paths=self.collect(owner)
        f=next((f for f in files if f['id']==key),None)
        if not f:raise PermissionError('RESULT_FILE_NOT_FOUND')
        if not f['integrity']:raise ValueError('RESULT_FILE_INVALID')
        return paths[key],f['name']
