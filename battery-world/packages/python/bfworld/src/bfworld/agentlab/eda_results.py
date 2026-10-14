"""Public native EDA receipts in the product catalog; never read arbitrary workspace files."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from .store import identity
from .native_outcome import summarize,documents

COMMANDS={'sch':{'check','bridge-check','module-check','netlist','export','export-image','save'},
          'pcb':{'drc','layout-lint','export','save','autoroute','outline-get'},
          'bom':{'export','list','get'}}


class EdaResults:
    def __init__(self,catalog):
        self.catalog=catalog;self.store=catalog.store;self.root=self.store.root.parent/'eda-cli'
        self._receipts={};self._exports={}

    def receipt(self,row):
        path=self.root/(row['id']+'.json');expected=(row.get('result') or {}).get('receipt_sha256')
        if not path.is_file() or path.is_symlink() or path.stat().st_size>8*1024*1024:return None
        stat=path.stat();key=(row['owner'],row['id'],expected,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        if key not in self._receipts:
            try:
                data=path.read_bytes();value=json.loads(data)
                if value.get('owner')!=row['owner'] or value.get('job_id')!=row['id'] or identity(value)!=expected:return None
                if len(self._receipts)>256:self._receipts.clear()
                self._receipts[key]=(value,hashlib.sha256(data).hexdigest(),len(data))
            except (OSError,ValueError):return None
        return self._receipts[key]

    def exports(self,owner,receipt):
        """Only explicit receipt paths in this owner's native artifact directory.

        CLI receipts do not attest export bytes. Preserve that distinction and
        hash the observed file; packaging verifies these exact bytes again.
        """
        workspace=self.store.root.parent/'participants'/owner
        root=(workspace/'.easyeda/artifacts').resolve()
        if workspace.is_symlink() or not root.is_relative_to(workspace.resolve()):return {}
        found={}
        paths=[]
        for document in documents(receipt.get('stdout','')):
            result=document.get('result')
            if isinstance(result,dict) and isinstance(result.get('artifactPath'),str):paths.append(result['artifactPath'])
            paths.extend(a['path'] for a in document.get('artifacts',[]) if isinstance(a,dict) and isinstance(a.get('path'),str))
        for name in paths:
            path=Path(name);resolved=path.resolve()
            if not resolved.is_relative_to(root) or path.is_symlink() or not path.is_file():continue
            if path.suffix.lower() not in {'.enet','.epro2','.epru','.eprj3','.esch2','.epcb2','.zip','.json','.svg','.pdf','.png','.dsn','.ses','.csv','.glb'}:continue
            stat=path.stat()
            if stat.st_size>128*1024*1024:continue
            key=(str(path),stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
            if key not in self._exports:
                h=hashlib.sha256()
                with path.open('rb') as f:
                    for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
                if len(self._exports)>128:self._exports.clear()
                self._exports[key]=h.hexdigest()
            found[path.name]=(path,self._exports[key],stat.st_size)
        return found

    def collect(self,owner):
        with self.store.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='eda_cli_jobs'").fetchone():return [],[]
            rows=[dict(r) for r in db.execute("SELECT * FROM eda_cli_jobs WHERE owner=? AND json_extract(request,'$.argv[0]') IN ('sch','pcb','bom') ORDER BY created DESC",(owner,))]
        results=[];files=[];seen=set()
        for row in rows:
            request=json.loads(row['request']);argv=request.get('argv',[])
            if len(argv)<2 or argv[1] not in COMMANDS.get(argv[0],()) or '--help' in argv or '--dry-run' in argv:continue
            doc=argv[argv.index('--doc')+1] if '--doc' in argv and len(argv)>argv.index('--doc')+1 else ''
            group=(request.get('project'),doc,*argv[:2])
            # Keep the latest receipt for each native operation/document. The
            # complete 600+ operation history stays in its existing EDA journal.
            if group in seen:continue
            seen.add(group);row['result']=json.loads(row['result']) if row['result'] else {}
            receipt=self.receipt(row);outcome=summarize(receipt[0]) if receipt else None
            state=(outcome or {}).get('check_status','unavailable');part={'sch':'schematic','pcb':'pcb','bom':'bom'}[argv[0]]
            label={'sch':'原理图','pcb':'PCB','bom':'BOM'}[argv[0]]+' · '+argv[1]
            apply={'state':'unbound','reason':'原生工程操作回执；尚未绑定统一装配验收','changed_inputs':[]}
            outputs=[]
            if receipt:
                name='native-'+argv[0]+'-'+argv[1]+'.json';key='eda/'+row['id']+'/'+name
                f=dict(id=key,result_id=row['id'],name=name,sha256=receipt[1],bytes=receipt[2],domain='circuit',role='receipt',
                       created_revision=None,applicability=apply,integrity=True,error='',status=row['status'],sections=[part],
                       label=label+' 原生回执',url='/api/results/file?'+urlencode({'session':owner,'id':key}))
                outputs.append(f);files.append(f)
                for export_name,(path,sha,byte_count) in self.exports(owner,receipt[0]).items():
                    key='eda/'+row['id']+'/'+export_name
                    native=dict(f,id=key,name=export_name,sha256=sha,bytes=byte_count,
                                label=export_name,role='native',integrity_basis='receipt_path_and_current_file_sha256',
                                native_origin=str(path.relative_to(self.store.root.parent/'participants'/owner)),
                                url='/api/results/file?'+urlencode({'session':owner,'id':key}))
                    outputs.append(native);files.append(native)
            counts=(outcome or {}).get('counts',[])
            scope=('原生检查未通过：'+' / '.join(str(x['name'])+' '+str(x['count']) for x in counts)) if state=='failed' else '原生回执；单次操作完成不代表该专业或整机验收。'
            results.append(dict(id=row['id'],kind='easyeda-'+part,domain='circuit',label=label,source_type='eda',
                group_key='eda:'+argv[0]+':'+argv[1],created=row['created'],status=row['status'],error=None,
                created_revision=None,applicability=apply,inputs={'project':request.get('project'),'document':doc,'argv':argv},
                design_inputs={},interfaces={},conditions={},metrics=[{'name':x['name'],'value':x['count']} for x in counts],
                checks={'native_check_passed':state=='passed'} if state in ('passed','failed') else {},
                design_status='FAIL' if state=='failed' else 'PASS' if state=='passed' else None,
                native_outcome=outcome,scope=scope,files=outputs,source_files=[],source_sha256=identity(row),
                readback_passed=False,hardware_verified=False))
        return results,files

    def file(self,owner,key):
        pieces=key.split('/')
        if len(pieces)!=3 or pieces[0]!='eda' or Path(pieces[1]).name!=pieces[1]:raise PermissionError('RESULT_FILE_NOT_FOUND')
        with self.store.connect() as db:row=db.execute('SELECT * FROM eda_cli_jobs WHERE id=? AND owner=?',(pieces[1],owner)).fetchone()
        if not row:raise PermissionError('RESULT_FILE_NOT_FOUND')
        row=dict(row);request=json.loads(row['request']);argv=request.get('argv',[])
        if len(argv)<2 or argv[1] not in COMMANDS.get(argv[0],()):raise PermissionError('RESULT_FILE_NOT_FOUND')
        row['result']=json.loads(row['result']) if row['result'] else {}
        receipt=self.receipt(row)
        if not receipt:raise ValueError('RESULT_FILE_INVALID')
        if pieces[2]=='native-'+argv[0]+'-'+argv[1]+'.json':return self.root/(row['id']+'.json'),pieces[2]
        exports=self.exports(owner,receipt[0])
        if pieces[2] not in exports:raise PermissionError('RESULT_FILE_NOT_FOUND')
        return exports[pieces[2]][0],pieces[2]
