"""Read-only Lab projections of immutable repository and actual Pi receipts."""
import json
from pathlib import Path
import time

from .repository import file_hash, name
from .repository_controller import state


def trace(repo, project, owner, session, after=-1, limit=80):
    view=repo.view(project,owner)
    owners={view['project']['owner'],*[t['owner'] for t in view['professional_tasks']]}
    if session not in owners:raise PermissionError('TRACE_PROJECT_SCOPE')
    limit=max(1,min(limit,200))
    kinds=('message','user_message','tool_execution_end','repository_controller_loaded',
           'conversation_status','turn_error','command_error','repository_turn_finished')
    with repo.store.connect() as db:
        sql='SELECT seq,data,created FROM chat_events WHERE conversation=? AND json_extract(data,\'$.type\') IN ('+','.join('?' for _ in kinds)+')'
        params=[session,*kinds]
        if after>=0:sql+=' AND seq>?';params.append(after)
        rows=list(db.execute(sql+(' ORDER BY seq DESC LIMIT ?' if after<0 else ' ORDER BY seq LIMIT ?'),[*params,limit]))
        if after<0:rows.reverse()
    records=[]
    for row in rows:
        raw=json.loads(row['data']);kind=raw.get('type');entry={'seq':row['seq'],'time':row['created'],'type':kind}
        if kind=='message':
            message=raw.get('message',{})
            if not isinstance(message,dict):message={'content':message}
            entry['role']=message.get('role')
            content=message.get('content',[])
            blocks=[c for c in content if isinstance(c,dict)] if isinstance(content,list) else []
            entry['text']=(content if isinstance(content,str) else '\n'.join(c.get('text','') for c in blocks if c.get('type')=='text'))[:16000]
            entry['tool_calls']=[{'name':c.get('name'),'arguments':_public(c.get('arguments'))} for c in blocks if c.get('type')=='toolCall']
            entry['is_error']=message.get('isError',False);entry['tool']=message.get('toolName')
            if not entry['text'] and not entry['tool_calls']:continue
        elif kind=='tool_execution_end':
            entry.update(tool=raw.get('toolName'),is_error=raw.get('isError',False),
                         result=_public(raw.get('result',{})))
        elif kind=='repository_controller_loaded':
            entry.update({k:raw.get(k) for k in ('harness_id','controller','tools','model','model_profile','prompt','prompt_sha256','resume_message_count')})
        else:entry.update({k:_public(v) for k,v in raw.items() if k in ('text','error','status','state','message_id')})
        records.append(entry)
    return {'session':session,'project':project,'records':records,'cursor':rows[-1]['seq'] if rows else max(after,0),
            'scope':'public instructions, assistant text and tool results'}


def _public(value):
    if isinstance(value,dict):return {k:_public(v) for k,v in value.items() if k.lower() not in
        ('thinking','reasoning','reasoning_content','signature','token','api_key','apikey','authorization','headers')}
    if isinstance(value,list):return [_public(v) for v in value[:100]]
    if isinstance(value,str):return value[:16000]
    return value


def interface_definitions():
    fields={
      'repository_read':(['system_id','path','offset?','limit?'],'Read immutable file bytes and sha256','Read only','immutable source; bounded section'),
      'repository_commit':(['paths','expected_revision','rationale','operation_id'],'Domain Commit, parent and complete source manifest','Freeze owned workspace files','branch CAS; specialist scope; immutable blobs'),
      'repository_execute':(['domain_commit','path','operation_id'],'Execution, source fingerprint, job_id and exact-reuse flag','Fixed target build or SPICE job','global native lock; exact input reuse; terminal readback'),
      'repository_contract':(['domain_commits','parent?','rationale','operation_id'],'Versioned provides / requires and source-bound executions','Create an immutable interface contract','Lead only; two source-bound Domain Commits'),
      'repository_integrate':(['base_system','domain_commits','contracts','expected_revision','rationale','operation_id'],'System Commit, selected jobs and invalidated gates','Create a candidate and advance submitted pointer','Lead CAS; complete manifests; contract input equality'),
      'repository_validate':(['system_id','operation_id'],'Checks, issues, evaluator and frozen input identity','Store independent validation','fixed checker; actual source-derived values'),
      'repository_release':(['system_id','rationale','operation_id'],'Release, files and archive hash','Create same-version review ZIP','exact source and job manifests; preserve open gates'),
    }
    return [{'id':key,'endpoint':'/api/design-lab','method':'POST','pi_tool':'bf_repository',
        'input':{'action':key.removeprefix('repository_'),'fields':f[0]},'output':f[1],
        'side_effects':f[2],'contract':f[3], 'authentication':'owner-scoped bearer; Lab uses operator read projection',
        'implementation':'design_lab/repository_actions.py / repository_execution.py',
        'tool_schema':'pi-bf-aiot/packages/bf-agent/src/extensions/bf-repository.ts'} for key,f in fields.items()]


def previews(repo, system):
    _, baseline = repo._baseline()
    p01 = baseline['p01']
    prefix = f"private/design-previews/{p01['owner']}/{p01['submitted_design']}/"
    pointer,_ = repo.baseline_file(prefix+'current.json')
    publication = json.loads(pointer.read_text())['publication_id']
    manifest,_ = repo.baseline_file(prefix+publication+'/manifest.json')
    output=[]
    for record in json.loads(manifest.read_text())['files']:
        valid=True
        for source in record['sources']:
            key=source['id']
            if '/input/' in key:ref=system['files'].get(key.split('/input/',1)[1])
            elif '/job/' in key:
                job,path=key.split('/job/',1)[1].split('/',1)
                ref=system['jobs'].get(job,{}).get('artifacts',{}).get(path)
            else:ref=None
            valid=valid and bool(ref and ref['sha256']==source['sha256'])
        if valid:output.append({**record,'frozen_path':prefix+publication+'/'+record['name'],
             'binding':'exact source hashes','system_commit':system['id'],'origin_design_id':p01['submitted_design']})
    return output


def projection(repo, project, owner):
    view=repo.view(project,owner)
    for system in view['systems']:
        # This is a view projection, not a rewrite of the sealed System Commit.
        system['recorded_validations']=system['validations']
        system['recorded_digital_status']=system['digital_status']
        system['validations']=system['current_qualification']['gates']
        system['digital_status']=system['current_qualification']['status']
        system['qualification_projection']=True
    owners=[view['project']['owner'],*[t['owner'] for t in view['professional_tasks']]]
    with repo.store.connect() as db:
        events=[dict(r) for r in db.execute('SELECT * FROM design_events WHERE owner IN ('+','.join('?' for _ in owners)+') ORDER BY seq DESC LIMIT 250',owners)]
        for row in events:row['data']=json.loads(row['data'])
        requests=[dict(r) for r in db.execute('SELECT id,owner,created,status,reserved,charged,usage,error FROM model_requests WHERE owner IN ('+','.join('?' for _ in owners)+') ORDER BY created',owners)]
        activations=[dict(r) for r in db.execute('SELECT * FROM skill_activations WHERE owner IN ('+','.join('?' for _ in owners)+')',owners)]
        decisions=[dict(r) for r in db.execute('SELECT * FROM design_adoptions WHERE owner=? ORDER BY revision',(view['project']['owner'],))]
        conversations=[dict(r) for r in db.execute('SELECT id,status,harness,title FROM conversations WHERE id IN ('+','.join('?' for _ in owners)+')',owners)]
        operations=[dict(r) for r in db.execute('SELECT id,owner,operation,status,request,result,error,created FROM design_operations WHERE owner IN ('+','.join('?' for _ in owners)+') ORDER BY created DESC LIMIT 250',owners)]
    for row in requests:
        row['usage']=json.loads(row['usage']) if row['usage'] else None
        if row['usage']:
            from ..provider import usage_costs
            row['cost_estimate']=usage_costs(row['usage'])
    for row in operations:
        row['request']=json.loads(row['request']);row['result']=json.loads(row['result']) if row['result'] else None
        # UI operation list shows intent and IDs; large edited text stays in file viewers.
        if 'content' in row['request']:row['request']['content']='[view committed artifact]'
    methods=[]
    for row in conversations:
        if row['harness']:
            manifest=Path(row['harness'])/'manifest.json'
            if manifest.is_file():methods.append({'owner':row['id'],**json.loads(manifest.read_text())})
    from ..skill_resources import source_bundle
    skill_catalog=source_bundle()[0]
    current=repo.system(project,view['project']['submitted'])
    from .repository_node_realization import current as node_realization
    node=node_realization(repo,current)
    pins=Path(repo.profile['runtime_root'])/'tool-pins.json'
    view.update(updated=time.time(),states=[state(repo,owner,x) for x in owners],events=events,
                operations=operations,decisions=decisions,model_requests=requests,skill_activations=activations,
                skills=skill_catalog,methods=methods,interfaces=interface_definitions(),
                environment={'profile_id':repo.profile['id'],'profile_sha256':repo.profile['sha256'],
                  'capabilities':repo.profile['capabilities'],'tool_pins':json.loads(pins.read_text()) if pins.exists() else {},
                  'native_project_count':len(repo.profile.get('native_project_uuids',[])),
                  'port':repo.profile['port'],'shared_native_lock':repo.profile['shared_native_lock']},
                previews=[p for system in view['systems'] for p in previews(repo,system)],source_commit=repo.profile['base_commit'],
                node_realization=node,baseline_frozen=True,original_demo_port=repo.profile['production_port'])
    return view


def artifact(repo, project, owner, system_id, path, job=None, preview=False, domain_commit=None, realization=False):
    system=repo.system(project,system_id);repo.project(project,owner);name(path)
    if realization:
        from .repository_node_realization import current
        value=current(repo,system)
        if not value or path not in value['outputs']: raise ValueError('NODE_ARTIFACT_BINDING')
        return repo.root/'node-realizations'/value['id']/path,path
    if domain_commit:
        with repo.store.connect() as db:commit=repo._object(db,'design_domain_commits',domain_commit,project)
        ref=commit['files'].get(path)
        if not ref:raise ValueError('ARTIFACT_DOMAIN_BINDING')
        file=repo.root/'blobs'/ref['sha256']
        if file_hash(file)!=ref['sha256']:raise ValueError('ARTIFACT_TAMPER')
        return file,path
    if preview:
        record=next((x for x in previews(repo,system) if x['name']==path),None)
        if not record:raise ValueError('PREVIEW_SOURCE_BINDING_CHANGED')
        file,_=repo.baseline_file(record['frozen_path'])
        return file,record['name']
    if job:
        ref=system['jobs'].get(job,{}).get('artifacts',{}).get(path)
        if not ref:raise ValueError('ARTIFACT_JOB_BINDING')
        file=repo.root/'blobs'/ref['sha256']
        if file_hash(file)!=ref['sha256']:raise ValueError('ARTIFACT_TAMPER')
        return file,path
    file,_=repo.artifact(project,owner,system_id,path)
    return file,path


def archive(repo, project, owner, key):
    repo.project(project,owner)
    with repo.store.connect() as db:release=repo._object(db,'design_repository_releases',key,project)
    file=repo.root/'releases'/(release['id']+'.zip')
    pin=json.loads((repo.root/'releases'/(release['id']+'.seal.json')).read_text())
    if file_hash(file)!=pin['sha256']:raise ValueError('RELEASE_ARCHIVE_TAMPER')
    return file
