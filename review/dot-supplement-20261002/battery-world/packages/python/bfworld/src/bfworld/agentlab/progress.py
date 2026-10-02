"""Read-only product progress assembled from versioned artifacts and real events."""
import json


def project(app, owner):
    app.products.require(owner)
    a=app.assemblies.projection(owner);current=a.get('current');rev=current['revision'] if current else None
    checks={c['id']:c for c in a.get('checks',[])}
    stages=[]
    def stage(key,title,state,detail,module,evidence=None):
        stages.append(dict(id=key,title=title,state=state,detail=detail,module=module,evidence=evidence or []))
    stage('definition','产品定义与版本','passed' if current else 'missing',f'装配 v{rev}' if current else '尚无装配定义','sessions')
    for key,title in [('current-native-model','CAD 与三维模型'),('energy-budget-screen','能源计算初筛')]:
        check=checks.get(key,{})
        stage(key,title,'passed' if check.get('passed') else 'missing','数字检查，不代表实物验证','tools',[check] if check else [])
    files=[f for f in a.get('files',[]) if not f['stale'] and f['integrity']]
    for kind,title in [('document','说明文档发布'),('source','设计源码发布')]:
        found=[f for f in files if f['kind']==kind]
        stage(kind,title,'passed' if found else 'missing',f'产品 v{rev} 已发布 {len(found)} 份' if found else f'缺少当前装配版本的 {kind} 文件','sessions',found)
    for index,path in enumerate((a.get('delivery') or {}).get('goal',{}).get('required_paths',[])):
        found=[f for f in files if f.get('source')==path]
        stage('required-file-'+str(index),'指定交付文件','passed' if found else 'missing',path+' · '+('已发布并校验' if found else '尚未发布到当前版本'),'sessions',found)
    deployment=[]
    for job in app.engineering.jobs(owner):
        if job['engine'] not in ('mcu-firmware','tinyml-nas'):continue
        result=job.get('result') or {}
        stale=not current or job.get('assembly_hashes',{}).get('definition_hash')!=current['hashes']['definition_hash']
        integrity=True
        for artifact in result.get('artifacts',[]):
            try:app.engineering.artifact(owner,job['id'],artifact['name'])
            except (ValueError,PermissionError,OSError):integrity=False
        deployment.append(dict(job_id=job['id'],engine=job['engine'],status=job['status'],stale=stale,integrity=integrity,result=result,error=job.get('error')))
    for engine,title,key in [('mcu-firmware','MCU 固件与烧录包','firmware'),('tinyml-nas','网络架构与 NAS','tinyml')]:
        j=next((j for j in deployment if j['engine']==engine and not j['stale']),None)
        passed=bool(j and j['integrity'] and j['status']=='SUCCEEDED')
        inherited=engine=='mcu-firmware' and checks.get('target-firmware-verification',{}).get('passed')
        stage(key,title,'passed' if passed or inherited else 'running' if j and j['status'] in ('RUNNING','QUEUED') else 'missing',
              '已有目标编译证据；烧录和板上测量分开验收' if passed or inherited else '尚无当前版本的可复现部署包',key,[j] if j else [])
    stage('hardware','板上延迟、功耗与功能','unmeasured','需要实际目标板、采集记录及固件／模型哈希绑定','firmware')
    with app.store.connect() as db:
        conv=dict(db.execute('SELECT id,status,error FROM conversations WHERE id=?',(owner,)).fetchone())
        rows=db.execute('SELECT seq,data FROM chat_events WHERE conversation=? ORDER BY seq DESC LIMIT 1200',(owner,)).fetchall()
    failures=[];latest=None
    for row in rows:
        d=json.loads(row['data']);kind=d.get('type')
        if latest is None and kind in ('tool_execution_start','tool_execution_end','turn_error','turn_complete','delivery_continuation'):
            latest=dict(seq=row['seq'],type=kind,tool=d.get('toolName'),time=d.get('time'))
        if kind=='tool_execution_end' and d.get('isError') and len(failures)<5:
            text='\n'.join(c.get('text','') for c in d.get('result',{}).get('content',[]) if c.get('type')=='text')
            failures.append(dict(seq=row['seq'],tool=d.get('toolName'),call_id=d.get('toolCallId'),time=d.get('time'),error=text[:1200],module='sessions' if d.get('toolName')=='bf_product' else 'tools'))
    return dict(schema_version='bf-product-progress-v1',owner=owner,revision=rev,conversation=conv,stages=stages,
                delivery=a.get('delivery'),latest=latest,failures=failures,deployments=deployment,
                scope='版本绑定的工程进展；历史错误保留，编译、发布、烧录和实物测量分别记录。')
