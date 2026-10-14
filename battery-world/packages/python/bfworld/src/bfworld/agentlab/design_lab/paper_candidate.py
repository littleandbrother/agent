"""P01 adapter for the existing DesignLab ledger, not a second controller.

The original Pi owns source selection and decisions. Native executors keep their
own immutable receipts; this adapter binds those receipts to a candidate. It
does not run case C, choose parts, turn file checks into acceptance, or retry an
unknown action. All queries use the already running application's Store.
"""
import json
from pathlib import Path, PurePosixPath
import secrets
import sqlite3
import time
from ..store import canonical, identity
from .contracts import sha, sealed

MODE = 'paper-native-P01'
GATES = ('source_domain', 'schematic_bom_pins', 'pcb_connectivity_drc',
         'geometry_fit', 'firmware_event_logic', 'board_firmware_interfaces',
         'power_load_chain', 'delivery_version')
SCHEMA = 'bf-paper-candidate-v1'


def bound(lab, owner):
    with lab.store.connect() as db:
        row = db.execute('SELECT environment FROM design_tasks WHERE owner=?', (owner,)).fetchone()
    return bool(row) and json.loads(row['environment']).get('mode') == MODE


def readonly_bound(root, owner):
    """Queue/entry guard: never construct another Workbench for a query."""
    path = Path(root)/'runtime/state/workbench.sqlite'
    with sqlite3.connect('file:'+str(path)+'?mode=ro', uri=True) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='design_tasks'").fetchone(): return False
        row = db.execute('SELECT environment FROM design_tasks WHERE owner=?', (owner,)).fetchone()
    return bool(row) and json.loads(row[0]).get('mode') == MODE


def safe_file(root, name):
    if not isinstance(name, str): raise ValueError('PAPER_SOURCE_PATH')
    rel = PurePosixPath(name)
    if (rel.is_absolute() or not rel.parts or '..' in rel.parts or
            rel.parts[0] in ('.pi', '.tmp', 'context-records', 'public-context-history')):
        raise ValueError('PAPER_SOURCE_PATH')
    root = Path(root)
    if any((root / Path(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts)+1)):
        raise ValueError('PAPER_SOURCE_SYMLINK')
    p = root / rel
    if not p.resolve().is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError('PAPER_SOURCE_MISSING: '+name)
    return p


def environment(lab, owner, root):
    """Operator binds existing identity and scope; never edits participant data."""
    root = Path(root).resolve()
    if root / 'runtime/state' != lab.store.root.resolve():
        raise ValueError('PAPER_RUNTIME_IDENTITY')
    index = json.loads((root/'campaign/parallel-20261009/pi-session-index.json').read_text())
    entries = [s for s in index['sessions'] if s['paper_id'] == 'P01']
    if len(entries) != 1 or entries[0]['owner'] != owner:
        raise ValueError('PAPER_ORIGINAL_OWNER_REQUIRED')
    scope_path = root/'campaign/acceptance/P01/scope-v1.json'
    scope = json.loads(scope_path.read_text())
    if scope['owner'] != owner or tuple(g['id'] for g in scope['required_gates']) != GATES:
        raise ValueError('PAPER_FROZEN_SCOPE_MISMATCH')
    binding = lab.app.eda_cli.binding(owner)
    if not binding: raise ValueError('PAPER_EDA_BINDING_REQUIRED')
    from .. import literature_acceptance
    value = {'mode': MODE, 'root': str(root), 'owner': owner,
             'scope': {'path': str(scope_path.relative_to(root)), 'sha256': sha(scope_path)},
             'evaluator_sha256': sha(literature_acceptance.__file__),
             'eda_project': binding['project'], 'scope_semantics_changed': False}
    return {**value, 'environment_id': 'E-'+identity(value)}


def contract(env):
    value = {'schema_version': 'bf-paper-design-task-v1', 'case': 'P01',
             'scope': 'complete-digital-system', 'environment_id': env['environment_id'],
             'validation_id': env['evaluator_sha256'], 'requirements': list(GATES),
             'goal': '在选定的名义机械输入和声明初态下，完成积能、人工接通MCU、建立连接、周期采样和PC解码；提交对应数字工程与验证证据。',
             'scenario': {'initial_state': 'BF declares and validates the chosen initial state',
                          'manual_mcu_connection': True, 'manual_gui_connection': True,
                          'manual_action_energy': 'must be declared; no undeclared auxiliary energy'},
             'separate_requirements': ['automatic MCU admission', 'zero-energy cold start',
                                       'calibrated gas concentration', 'physical verification'],
             'design_authority': 'original BF/Pi owner; device and strategy choices remain open',
             'supported_actions': ['freeze existing workspace/native receipt inputs',
                                   'execute bound native tools', 'inspect independent checks',
                                   'record continue/reject/blocked', 'adopt'],
             'physical': 'NOT_TESTED', 'method_gain': 'NOT_EVALUATED'}
    return {**value, 'task_id': 'task-P01-'+identity(value)[:20]}


def selector(sources):
    if not isinstance(sources, dict) or set(sources) != {'candidate.json'}:
        raise ValueError('PAPER_CANDIDATE_SELECTOR_REQUIRED')
    text = sources['candidate.json']
    if not isinstance(text, str) or len(text.encode()) > 64000:
        raise ValueError('PAPER_CANDIDATE_SELECTOR_SIZE')
    value = json.loads(text)
    if (value.get('schema_version') != SCHEMA or
            set(value) - {'schema_version', 'files', 'projects', 'eda_receipts', 'selected_jobs', 'decision'}):
        raise ValueError('PAPER_CANDIDATE_SELECTOR_INVALID')
    if not isinstance(value.get('decision'), str) or not value['decision'].strip() or len(value['decision']) > 4000:
        raise ValueError('PAPER_DECISION_USE_REQUIRED')
    for key in ('files', 'projects', 'eda_receipts', 'selected_jobs'):
        xs = value.get(key, [])
        if not isinstance(xs, list) or len(xs) > 128 or any(not isinstance(x, str) for x in xs) or len(set(xs)) != len(xs):
            raise ValueError('PAPER_CANDIDATE_LIST_INVALID: '+key)
    if not value.get('files') and not value.get('projects'): raise ValueError('PAPER_CANDIDATE_INPUTS_REQUIRED')
    return value


def capture(lab, owner, task, env, sources, parent=None):
    from .paper_mainline import project_snapshot
    choice = selector(sources); workspace = Path(env['root'])/'runtime/participants'/owner
    names = set(choice.get('files', [])); projects = {}
    for name in choice.get('projects', []):
        projects[name] = project_snapshot(workspace, name)
        names.add(name)
        manifest = json.loads(safe_file(workspace, name).read_text())
        names.update(str(PurePosixPath(name).parent/f) for f in manifest['files'])
    native = {}
    for jid in choice.get('eda_receipts', []):
        name = 'eda-receipts/'+jid+'.json'; p = safe_file(workspace, name)
        receipt = json.loads(p.read_text())
        if receipt.get('owner') != owner or receipt.get('project') != env['eda_project']:
            raise ValueError('PAPER_FOREIGN_EDA_RECEIPT')
        names.add(name); native[jid] = {'path': name, 'sha256': sha(p), 'status': receipt['status']}
    jobs = {}
    for jid in choice.get('selected_jobs', []):
        job = lab.app.engineering.get(owner, jid)
        jobs[jid] = {'status': job['status'], 'project_sha256': job.get('project_sha256'),
                     'request_sha256': identity(job.get('request') or {k:job[k] for k in
                         ('project', 'parameters', 'assembly_hashes') if k in job}),
                     'result_sha256': identity(job.get('result')),
                     'execution_only': True, 'functional_acceptance_inherited': False}
    if len(names) > 256: raise ValueError('PAPER_INPUT_MANIFEST_SIZE')
    files = {n: {'sha256': sha(safe_file(workspace, n)), 'bytes': safe_file(workspace, n).stat().st_size}
             for n in sorted(names)}
    if sum(v['bytes'] for v in files.values()) > 64*1024*1024: raise ValueError('PAPER_INPUT_BYTES')
    assembly = lab.app.assemblies.get(owner)
    value = {'schema_version': 'bf-paper-design-snapshot-v1', 'task_id': task['task_id'],
             'environment_id': task['environment_id'], 'scope': task['scope'], 'parent': parent,
             'sources': {'candidate.json': canonical(choice)}, 'files': files,
             'projects': projects, 'native_receipts': native, 'selected_jobs': jobs,
             'assembly': {'revision': assembly['revision'], 'hashes': assembly['hashes']},
             'eda_project': env['eda_project'], 'dimensions': {'inputs': identity(files)}}
    return {**value, 'design_id': 'D-'+identity(value)}


def persist(lab, owner, value):
    directory = lab.root/owner/'designs'/value['design_id']
    sealed(directory/'snapshot.json', value)
    sealed(directory/'candidate.json', selector(value['sources']))
    workspace = lab.store.root.parent/'participants'/owner
    for name, expected in value['files'].items():
        data = safe_file(workspace, name).read_bytes()
        import hashlib
        if hashlib.sha256(data).hexdigest() != expected['sha256']: raise ValueError('PAPER_INPUT_CHANGED_DURING_FREEZE')
        p = directory/'inputs'/name; p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.read_bytes() != data: raise ValueError('PAPER_IMMUTABLE_INPUT_CONFLICT')
        if not p.exists(): p.write_bytes(data)


def verify(lab, owner, value, live=False):
    if value['design_id'] != 'D-'+identity({k:v for k,v in value.items() if k != 'design_id'}):
        raise ValueError('PAPER_SNAPSHOT_TAMPER')
    directory = lab.root/owner/'designs'/value['design_id']
    if json.loads((directory/'snapshot.json').read_text()) != value: raise ValueError('PAPER_SNAPSHOT_TAMPER')
    root = lab.store.root.parent/'participants'/owner if live else directory/'inputs'
    for name, expected in value['files'].items():
        p = safe_file(root, name)
        if sha(p) != expected['sha256']: raise ValueError('PAPER_INPUT_CHANGED_REQUIRES_FREEZE: '+name)
    if live:
        assembly = lab.app.assemblies.get(owner)
        if {'revision': assembly['revision'], 'hashes': assembly['hashes']} != value['assembly']:
            raise ValueError('PAPER_ASSEMBLY_CHANGED_REQUIRES_FREEZE')
    return value


def working(lab, owner):
    task = lab.task(owner)
    return task['intent'].get('working_design', task['current_design'])


def frozen_view(lab, owner, *, compact=False, fields=()):
    if not getattr(lab.store, 'readonly', False):
        with lab.store.connect() as db:
            pending = [r['id'] for r in db.execute("SELECT id FROM design_operations WHERE owner=? AND status='WAITING_NATIVE'", (owner,))]
        for key in pending: refresh(lab, owner, key)
    task = lab.task(owner); design = lab.design(owner, working(lab, owner))
    with lab.store.connect() as db:
        ops = [dict(r) for r in db.execute('SELECT id,status,request,error FROM design_operations WHERE owner=? ORDER BY created DESC LIMIT 8', (owner,))]
        cursor = db.execute('SELECT COALESCE(MAX(seq),0) FROM design_events WHERE owner=?', (owner,)).fetchone()[0]
    for op in ops: op['request'] = json.loads(op['request'])
    value = {k:task[k] for k in ('owner', 'task_id', 'contract', 'current_design', 'revision', 'intent', 'plan', 'status', 'submission')} | {
        'working_design': design['design_id'], 'candidate_decision': selector(design['sources'])['decision'],
        'event_cursor': cursor,
        'input_files': len(design['files']), 'input_manifest': design['files'],
        'candidate_selector': selector(design['sources']),
        'project_inputs': design['projects'],
        'selected_jobs': design['selected_jobs'], 'operations': ops,
        'control_route': 'candidate-lifecycle', 'original_owner_preserved': True,
        'environment_id': task['environment']['environment_id'], 'environment_mode': MODE,
        'full_product_passed': False, 'physical': 'NOT_TESTED',
        'available_skills': [x['id'] for x in lab.app.skills.catalog(owner)['skills']],
        'observations': 'Native operation status is not an independent engineering verdict.'}
    if not compact:
        return value
    allowed = {'input_manifest', 'candidate_selector', 'project_inputs', 'selected_jobs', 'operations', 'contract'}
    if not isinstance(fields, (list, tuple)) or any(f not in allowed for f in fields):
        raise ValueError('PAPER_VIEW_FIELDS_INVALID: ' + ','.join(sorted(allowed)))
    current = {k:v for k,v in value.items() if k not in allowed}
    current['contract'] = {k: task['contract'][k] for k in ('goal', 'requirements', 'scenario', 'separate_requirements', 'task_id')}
    current['selected_jobs'] = design['selected_jobs']
    with lab.store.connect() as db:
        current['pending_operations'] = [dict(r) for r in db.execute(
            "SELECT id,status,error FROM design_operations WHERE owner=? AND status IN ('UNKNOWN','RUNNING','WAITING_NATIVE') ORDER BY created", (owner,))]
    current['recent_operations'] = [{k:x[k] for k in ('id', 'status', 'error')} for x in ops]
    current['inputs'] = {'files': len(design['files']), 'projects': list(design['projects']),
                         'sha256': identity(design['files'])}
    # The receipt itself is authoritative; the current packet supplies its index.
    current['checks'] = []
    for p in sorted((lab.root/owner/'checks').glob('*/check.json'), key=lambda x:x.stat().st_mtime, reverse=True):
        result = json.loads(p.read_text())
        if result.get('design_id') != design['design_id']:
            continue
        accepted = result.get('acceptance', {})
        current['checks'].append({'check_id': result['check_id'], 'design_id': result['design_id'],
            'status': accepted.get('digital_engineering_status'),
            'gates': [{k:g[k] for k in ('id', 'status', 'reason') if k in g} for g in accepted.get('functional_gates', accepted.get('gates', []))],
            'receipt': {'path': str(p), 'sha256': sha(p)}})
        break
    current['open_gates'] = [g for c in current['checks'] for g in c['gates'] if g.get('status') != 'PASS']
    current['read_fields'] = sorted(allowed)
    current['view_schema'] = 'bf-paper-current-view-v2'
    return {**current, **{k:value[k] for k in fields}}


def record_blocker(lab, owner, operation, public_fact):
    """Import an interrupted real write as a new link; retain its original row."""
    if not isinstance(public_fact, dict) or not public_fact.get('receipt_path'):
        raise ValueError('PAPER_BLOCKER_RECEIPT_REQUIRED')
    root = Path(lab.task(owner)['environment']['root'])
    path = safe_file(root, public_fact['receipt_path'])
    if sha(path) != public_fact.get('receipt_sha256'): raise ValueError('PAPER_BLOCKER_HASH')
    receipt = json.loads(path.read_text())
    if (receipt.get('schema_version') != 'bf-eda-cli-operation-v1' or
            receipt.get('owner') != owner or
            receipt.get('project') != lab.task(owner)['environment']['eda_project'] or
            receipt.get('command_entered') is not True or
            receipt.get('argv', [])[:2] != ['sch', 'replace']):
        raise ValueError('PAPER_INTERRUPTED_WRITE_IDENTITY')
    key = 'design-job-'+identity([owner, operation])[:20]
    req = {'task_id': lab.task(owner)['task_id'], 'design_id': working(lab, owner),
           'kind': 'interrupted-native-write', 'public_fact': public_fact}
    with lab.store.connect() as db:
        old = db.execute('SELECT request_hash FROM design_operations WHERE owner=? AND operation=?', (owner, operation)).fetchone()
        if old and old['request_hash'] != identity(req): raise ValueError('OPERATION_CONFLICT')
        if not old:
            db.execute('INSERT INTO design_operations VALUES(?,?,?,?,?,?,NULL,?,?)',
                       (key, owner, operation, identity(req), canonical(req), 'UNKNOWN',
                        'Interrupted native write; reconcile the host generation and fresh native scene before further mutation.', time.time()))
            lab.event(owner, 'platform_blocked', {'operation_id': key, 'design_id': req['design_id'], 'public_fact': public_fact}, db)
        intent = {'kind': 'BLOCKED', 'working_design': req['design_id'], 'job_id': key}
        db.execute("UPDATE design_tasks SET intent=?,status='BLOCKED' WHERE owner=?", (canonical(intent), owner))
    return lab.operation(owner, key)


def guard_route(lab, owner, route):
    if bound(lab, owner) and route != 'candidate-lifecycle':
        raise ValueError('PAPER_CANDIDATE_ROUTE_REQUIRED')


def reconcile_desktop(lab, owner, key, proof_reference, operator=False):
    """Release one generation blocker from operator readbacks, never replay it.

    The old native row and UNKNOWN import event remain history. This proves only
    that the prior host is gone and the new host's persisted scene is known;
    it does not declare the interrupted replacement successful.
    """
    if not operator: raise PermissionError('PAPER_RECONCILIATION_OPERATOR_REQUIRED')
    task=lab.task(owner);root=Path(task['environment']['root']);op=lab.operation(owner,key)
    if op['request'].get('kind')!='interrupted-native-write': raise ValueError('PAPER_RECONCILIATION_KIND')
    def artifact(ref):
        name=ref.get('path','')
        if not name.startswith('deployment/'): raise ValueError('PAPER_RECONCILIATION_OPERATOR_ARTIFACT')
        path=safe_file(root,name)
        if sha(path)!=ref.get('sha256'): raise ValueError('PAPER_RECONCILIATION_HASH')
        return json.loads(path.read_text())
    proof=artifact(proof_reference)
    if op['status']=='RECONCILED':
        if op['result']['proof']!=proof_reference: raise ValueError('OPERATION_CONFLICT')
        return op
    if op['status']!='UNKNOWN': raise ValueError('PAPER_RECONCILIATION_STATUS')
    original=op['request']['public_fact'];receipt_path=safe_file(root,original['receipt_path'])
    if sha(receipt_path)!=original['receipt_sha256']: raise ValueError('PAPER_BLOCKER_HASH')
    receipt=json.loads(receipt_path.read_text());old=receipt.get('native_host',{}).get('window_id')
    if (proof.get('schema_version')!='bf-desktop-native-reconciliation-v1' or
            proof.get('owner')!=owner or proof.get('original_receipt')!=original or
            proof.get('human_confirmed_full_restart') is not True or not old):
        raise ValueError('PAPER_RECONCILIATION_IDENTITY')
    from ..runtime_config import eda_policy
    policy=eda_policy();new=proof.get('window_id')
    for name in ('health_before','health_after'):
        health=artifact(proof[name]);windows=health.get('found',{}).get('raw',{}).get('windows',[])
        matches=[w for w in windows if w.get('windowId')==new]
        if any(w.get('windowId')==old for w in windows) or len(matches)!=1:
            raise ValueError('PAPER_OLD_GENERATION_NOT_RETIRED')
        w=matches[0];ctx=w.get('context',{});host=ctx.get('environment',{})
        if (new==old or w.get('connectorVersion')!=policy['connector_version'] or
                ctx.get('projectUuid')!=task['environment']['eda_project'] or
                host.get('host')!='desktop' or host.get('mode') not in policy['modes']):
            raise ValueError('PAPER_RECONCILIATION_CURRENT_HOST')
    reads=proof.get('reads',[])
    if len(reads)!=2: raise ValueError('PAPER_RECONCILIATION_READBACKS')
    scenes=[artifact(ref) for ref in reads]
    for scene in scenes:
        result=scene.get('result',{});ctx=scene.get('context',{})
        if (scene.get('ok') is not True or ctx.get('projectUuid')!=receipt['project'] or
                ctx.get('documentUuid')!=proof.get('document_uuid') or
                result.get('componentCount')!=len(result.get('components',[])) or
                not result.get('components') or result.get('netlistAvailable') is not True):
            raise ValueError('PAPER_RECONCILIATION_INCOMPLETE_SCENE')
    if scenes[0]['result']!=scenes[1]['result']: raise ValueError('PAPER_RECONCILIATION_SCENE_CHANGED')
    before=artifact(proof['persisted_before']);after=artifact(proof['persisted_after'])
    from ..literature_eda import local_destination
    binding=json.loads((root/'campaign/eda/P01/binding.json').read_text())
    creation=safe_file(root,binding['creation']['path'])
    if sha(creation)!=binding['creation']['sha256']: raise ValueError('PAPER_RECONCILIATION_BINDING')
    native=local_destination(binding,json.loads(creation.read_text()))
    if before!=after or str(native) not in before or len(before)<3:
        raise ValueError('PAPER_RECONCILIATION_PERSISTED_FILES')
    for name,record in before.items():
        path=Path(name)
        if (not path.resolve().is_relative_to(native.parent.resolve()) or path.is_symlink() or
                not path.is_file() or sha(path)!=record.get('sha256') or
                path.stat().st_size!=record.get('bytes')):
            raise ValueError('PAPER_RECONCILIATION_PERSISTED_FILES')
    result={'status':'RECONCILED','historical_status':'UNKNOWN','proof':proof_reference,
            'scene_sha256':identity(scenes[0]['result']), 'old_window':old,'new_window':new,
            'replacement_success_claimed':False,'native_writes':0,'full_product_passed':False}
    sealed(lab.root/owner/'operations'/key/'reconciliation.json',result)
    with lab.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT status FROM design_operations WHERE id=? AND owner=?',(key,owner)).fetchone()[0]!='UNKNOWN':
            raise ValueError('PAPER_RECONCILIATION_STATUS_CHANGED')
        db.execute("UPDATE design_operations SET status='RECONCILED',result=? WHERE id=? AND owner=?",(canonical(result),key,owner))
        intent={'kind':'AWAITING_PI_DECISION','working_design':working(lab,owner),'platform_restored':key}
        db.execute("UPDATE design_tasks SET intent=?,status='READY' WHERE owner=?",(canonical(intent),owner))
        lab.event(owner,'platform_restored',result,db)
    return lab.operation(owner,key)


def reconcile_admission(lab, owner, key, proof_reference, operator=False):
    """Reconcile a proven historical SPICE admission rejection, without replay."""
    import ast
    if not operator: raise PermissionError('PAPER_RECONCILIATION_OPERATOR_REQUIRED')
    root = Path(lab.task(owner)['environment']['root']); op = lab.operation(owner,key)
    def artifact(ref):
        path = safe_file(root,ref['path'])
        if sha(path) != ref['sha256']: raise ValueError('PAPER_RECONCILIATION_HASH')
        return path
    if not proof_reference['path'].startswith('deployment/'):
        raise ValueError('PAPER_RECONCILIATION_OPERATOR_ARTIFACT')
    proof = json.loads(artifact(proof_reference).read_text())
    if op['status'] == 'RECONCILED':
        if op['result']['proof'] != proof_reference: raise ValueError('OPERATION_CONFLICT')
        return op
    if (op['status'] != 'UNKNOWN' or op['request'].get('channel') != 'engineering' or
            op['error'] != 'ValueError: PROJECT_SPICE_DIRECTIVE_DENIED' or
            op['result'].get('native_result') is not None):
        raise ValueError('PAPER_ADMISSION_RECONCILIATION_STATUS')
    if (proof.get('schema_version') != 'bf-engineering-admission-reconciliation-v1' or
            proof.get('owner') != owner or proof.get('operation_id') != key or
            proof.get('error') != op['error']): raise ValueError('PAPER_RECONCILIATION_IDENTITY')
    original = lab.root/owner/'operations'/key/'result.json'
    if artifact(proof['original_result']) != original or json.loads(original.read_text()) != op['result']:
        raise ValueError('PAPER_ADMISSION_ORIGINAL_RECEIPT')
    qualification = json.loads(artifact(proof['qualification']).read_text())
    if qualification.get('status') != 'PASS': raise ValueError('PAPER_ADMISSION_QUALIFICATION')
    for field,module in [('validator','bfworld.agentlab.engineering_projects'),('dispatcher','bfworld.agentlab.engineering')]:
        artifact(proof[field])
        if qualification.get('apparatus_modules',{}).get(module) != proof[field]['sha256']:
            raise ValueError('PAPER_ADMISSION_RELEASE_IDENTITY')
    tree = ast.parse(artifact(proof['validator']).read_text())
    fn = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='request')
    allowed = next(ast.literal_eval(n.value) for n in ast.walk(fn) if isinstance(n,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=='allowed' for t in n.targets))
    design = lab.design(owner,op['request']['design_id']); verify(lab,owner,design)
    frozen = lab.root/owner/'designs'/design['design_id']/'inputs'
    relative = op['request']['body']['parameters']['project_path']
    manifest = json.loads(safe_file(frozen,relative).read_text())
    if manifest.get('kind') != 'spice': raise ValueError('PAPER_ADMISSION_KIND')
    circuit = safe_file(frozen,str(PurePosixPath(relative).parent/manifest['entrypoint'])).read_text()
    denied = [line.strip().split()[0].lower() for line in circuit.splitlines()
              if line.strip().startswith('.') and line.strip().split()[0].lower() not in allowed]
    if not denied: raise ValueError('PAPER_ADMISSION_REJECTION_NOT_REPRODUCED')
    with lab.store.connect() as db:
        if db.execute('SELECT 1 FROM engineering_jobs WHERE owner=? AND operation=?',
                      (owner,op['request']['body']['operation_id'])).fetchone():
            raise ValueError('PAPER_ADMISSION_NATIVE_JOB_EXISTS')
    result = {'status':'RECONCILED','historical_status':'UNKNOWN','proof':proof_reference,
              'original_result':proof['original_result'],'denied_directives':denied,
              'native_job_created':False,'native_replay':False,'fee_ledger_changes':0}
    sealed(lab.root/owner/'operations'/key/'admission-reconciliation.json',result)
    with lab.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT status FROM design_operations WHERE id=? AND owner=?',(key,owner)).fetchone()[0]!='UNKNOWN':
            raise ValueError('PAPER_RECONCILIATION_STATUS_CHANGED')
        db.execute("UPDATE design_operations SET status='RECONCILED',result=? WHERE id=? AND owner=?",(canonical(result),key,owner))
        intent = {'kind':'AWAITING_PI_DECISION','working_design':working(lab,owner),'platform_restored':key}
        db.execute("UPDATE design_tasks SET intent=?,status='READY' WHERE owner=?",(canonical(intent),owner))
        lab.event(owner,'platform_restored',result,db)
    return lab.operation(owner,key)


def reconcile_eda_admission(lab, owner, key, proof_reference, operator=False):
    """Close a proven rejected help query; retain its original UNKNOWN receipt."""
    if not operator: raise PermissionError('PAPER_RECONCILIATION_OPERATOR_REQUIRED')
    root = Path(lab.task(owner)['environment']['root']); op = lab.operation(owner,key)
    def artifact(ref):
        path = safe_file(root,ref['path'])
        if sha(path) != ref['sha256']: raise ValueError('PAPER_RECONCILIATION_HASH')
        return path
    if not proof_reference['path'].startswith('deployment/'):
        raise ValueError('PAPER_RECONCILIATION_OPERATOR_ARTIFACT')
    proof = json.loads(artifact(proof_reference).read_text())
    if op['status'] == 'RECONCILED':
        if op['result']['proof'] != proof_reference: raise ValueError('OPERATION_CONFLICT')
        return op
    argv = op['request'].get('body',{}).get('argv')
    allowed = ((argv == ['call','--help'] and op['error'] == 'ValueError: EDA_TYPED_ACTION_DENIED') or
               (argv == ['debug','--help'] and isinstance(op['error'],str) and op['error'].startswith('ValueError: EDA_COMMAND_DENIED:')))
    if (op['status'] != 'UNKNOWN' or op['request'].get('channel') != 'eda' or not allowed or
            op['result'].get('native_result') is not None):
        raise ValueError('PAPER_EDA_ADMISSION_RECONCILIATION_STATUS')
    if (proof.get('schema_version') != 'bf-eda-admission-reconciliation-v1' or
            proof.get('owner') != owner or proof.get('operation_id') != key or
            proof.get('error') != op['error'] or proof.get('argv') != argv):
        raise ValueError('PAPER_RECONCILIATION_IDENTITY')
    original = lab.root/owner/'operations'/key/'result.json'
    if artifact(proof['original_result']) != original or json.loads(original.read_text()) != op['result']:
        raise ValueError('PAPER_ADMISSION_ORIGINAL_RECEIPT')
    qualification = json.loads(artifact(proof['qualification']).read_text())
    artifact(proof['validator'])
    if (qualification.get('status') != 'PASS' or qualification.get('apparatus_modules',{}).get(
            'bfworld.agentlab.eda_cli') != proof['validator']['sha256']):
        raise ValueError('PAPER_ADMISSION_RELEASE_IDENTITY')
    with lab.store.connect() as db:
        if db.execute('SELECT 1 FROM eda_cli_jobs WHERE owner=? AND operation=?',
                      (owner,op['request']['body']['operation_id'])).fetchone():
            raise ValueError('PAPER_ADMISSION_NATIVE_JOB_EXISTS')
    result = {'status':'RECONCILED','historical_status':'UNKNOWN','proof':proof_reference,
              'original_result':proof['original_result'],'argv':argv,'native_job_created':False,
              'native_replay':False,'fee_ledger_changes':0}
    sealed(lab.root/owner/'operations'/key/'eda-admission-reconciliation.json',result)
    with lab.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT status FROM design_operations WHERE id=? AND owner=?',(key,owner)).fetchone()[0]!='UNKNOWN':
            raise ValueError('PAPER_RECONCILIATION_STATUS_CHANGED')
        if db.execute('SELECT 1 FROM eda_cli_jobs WHERE owner=? AND operation=?',
                      (owner,op['request']['body']['operation_id'])).fetchone():
            raise ValueError('PAPER_ADMISSION_NATIVE_JOB_EXISTS')
        db.execute("UPDATE design_operations SET status='RECONCILED',result=? WHERE id=? AND owner=?",(canonical(result),key,owner))
        intent = {'kind':'AWAITING_PI_DECISION','working_design':working(lab,owner),'platform_restored':key}
        db.execute("UPDATE design_tasks SET intent=?,status='READY' WHERE owner=?",(canonical(intent),owner))
        lab.event(owner,'platform_restored',result,db)
    return lab.operation(owner,key)


def begin(lab, owner, channel, body, readonly=False):
    """Admission at the actual original BF native consumer, before dispatch."""
    task = lab.task(owner); design_id = working(lab, owner)
    if not readonly and (body.get('candidate_id') != design_id or body.get('candidate_revision') != task['revision']):
        raise ValueError('PAPER_CANDIDATE_STALE_OR_UNBOUND')
    purpose = body.get('decision_use') or ('Read-only native observation' if readonly else None)
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 4000:
        raise ValueError('PAPER_DECISION_USE_REQUIRED')
    design = lab.design(owner, design_id)
    if not readonly: verify(lab, owner, design, live=True)
    clean = {k:v for k,v in body.items() if k not in ('candidate_id', 'candidate_revision', 'decision_use', 'session_id')}
    if channel == 'eda':
        # Match the actual typed CLI admission before a design action exists.
        # Parameter rejection never entered the native executor.
        from ..eda_cli import validate_argv
        binding = lab.app.eda_cli.binding(owner)
        if not binding: raise ValueError('EDA_PROJECT_BINDING_REQUIRED')
        validate_argv(clean.get('argv'), lab.app.eda_cli.workspace(owner), binding['project'])
    if channel == 'engineering':
        if clean.get('engine') != 'engineering-project': raise ValueError('PAPER_NATIVE_PROJECT_ONLY')
        name = clean.get('parameters', {}).get('project_path')
        if name not in design['projects']: raise ValueError('PAPER_PROJECT_NOT_IN_CANDIDATE')
        # This is the actual executor's read-only admission, before recording a
        # dispatched design action. Invalid project syntax creates no UNKNOWN.
        from ..engineering import validate
        from ..engineering_projects import request
        request(lab.app, owner, validate('engineering-project', clean.get('parameters', {})))
    operation = clean.get('operation_id')
    if not isinstance(operation, str) or not 1 <= len(operation) <= 100: raise ValueError('OPERATION_ID_REQUIRED')
    req = {'task_id': task['task_id'], 'design_id': design_id, 'candidate_revision': task['revision'],
           'channel': channel, 'body': clean, 'decision_use': purpose}
    digest = identity(req)
    with lab.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT id,request_hash FROM design_operations WHERE owner=? AND operation=?', (owner, operation)).fetchone()
        if previous:
            if previous['request_hash'] != digest: raise ValueError('OPERATION_CONFLICT')
            return previous['id'], clean, False
        if not readonly and db.execute("SELECT 1 FROM design_operations WHERE owner=? AND status IN ('RUNNING','UNKNOWN','WAITING_NATIVE')", (owner,)).fetchone():
            raise ValueError('PAPER_PENDING_OPERATION_READ_BEFORE_RETRY')
        key = 'design-job-'+secrets.token_hex(8)
        db.execute('INSERT INTO design_operations VALUES(?,?,?,?,?,?,NULL,NULL,?)',
                   (key, owner, operation, digest, canonical(req), 'RUNNING', time.time()))
        lab.event(owner, 'candidate_action_started', {'operation_id': key, 'design_id': design_id,
                    'channel': channel, 'decision_use': purpose}, db)
    return key, clean, True


def finish(lab, owner, key, result=None, error=None, known_not_dispatched=False):
    status = ('FAILED' if known_not_dispatched else 'UNKNOWN') if error is not None else result.get('status', 'SUCCEEDED')
    if status in ('QUEUED', 'RUNNING'): status = 'WAITING_NATIVE'
    if status not in ('WAITING_NATIVE', 'SUCCEEDED', 'FAILED', 'UNKNOWN'): raise ValueError('PAPER_NATIVE_STATUS')
    directory = lab.root/owner/'operations'/key
    receipt = {'operation_id': key, 'owner': owner, 'status': status, 'native_result': result, 'error': error}
    with lab.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT status FROM design_operations WHERE id=? AND owner=?', (key, owner)).fetchone()
        if not row: raise ValueError('DESIGN_OPERATION_NOT_FOUND')
        if row['status'] not in ('RUNNING', 'WAITING_NATIVE'):
            return lab.operation(owner, key)
        if row['status'] == 'WAITING_NATIVE' and status == 'WAITING_NATIVE':
            return lab.operation(owner, key)
        sealed(directory/('dispatch.json' if status == 'WAITING_NATIVE' else 'result.json'), receipt)
        db.execute('UPDATE design_operations SET status=?,result=?,error=? WHERE id=? AND owner=?',
                   (status, canonical(receipt), error, key, owner))
        lab.event(owner, 'candidate_action_observed', {'operation_id': key, 'status': status,
                 'receipt_path': str(directory/('dispatch.json' if status == 'WAITING_NATIVE' else 'result.json'))}, db)
    return lab.operation(owner, key)


def refresh(lab, owner, key):
    op = lab.operation(owner, key)
    if op['status'] != 'WAITING_NATIVE': return op
    native = op['result']['native_result']; channel = op['request']['channel']
    result = lab.app.engineering.get(owner, native['id']) if channel == 'engineering' else lab.app.eda_cli.get(owner, native['id'])
    if result['status'] in ('QUEUED', 'RUNNING'): return op
    return finish(lab, owner, key, result)


def observe_native(lab, owner, channel, value):
    """Bind the existing job lookup to its candidate without dispatching it."""
    if value.get('owner', owner) != owner: raise ValueError('PAPER_NATIVE_OWNER_MISMATCH')
    with lab.store.connect() as db:
        rows = list(db.execute('SELECT id,request,result FROM design_operations WHERE owner=? AND result IS NOT NULL', (owner,)))
    matches = []
    for row in rows:
        request = json.loads(row['request']); receipt = json.loads(row['result'])
        native = receipt.get('native_result') or {}
        if request.get('channel') != channel or native.get('id') != value.get('id'): continue
        if value['status'] not in ('QUEUED', 'RUNNING'):
            finish(lab, owner, row['id'], value)
        matches.append(row['id'])
    if len(matches) == 1:
        op = lab.operation(owner, matches[0])
        return {**value, 'candidate_operation_id': op['id'], 'candidate_id': op['request']['design_id']}
    return value


def decorate_context(lab, owner, value):
    if bound(lab, owner): return {**value, 'candidate_lifecycle': frozen_view(lab, owner, compact=True)}
    return value


def readonly_eda(body):
    argv = body.get('argv', [])
    if not isinstance(argv, list) or not argv: return False
    from ..eda_cli import offline_command
    return offline_command(argv) or tuple(argv[:2]) in {
        ('project', 'info'), ('project', 'doc'), ('board', 'list'),
        ('sch', 'list'), ('sch', 'read'), ('sch', 'connectivity'), ('sch', 'drc'), ('sch', 'check'),
        ('pcb', 'list'), ('pcb', 'read'), ('pcb', 'drc'), ('pcb', 'check'),
        ('pcb', 'dump'), ('pcb', 'board-info'), ('pcb', 'outline-get'), ('pcb', 'nets'), ('pcb', 'drc-rules'),
        ('lib', 'search'), ('lib', 'get'), ('lib', 'resolve'), ('lib', 'device'), ('lib', 'footprint')}


def reuse(lab, owner, body):
    """Reuse explicitly selected exact inputs/outputs. No functional promotion."""
    design = lab.design(owner, working(lab, owner))
    name = body.get('parameters', {}).get('project_path')
    if name not in design['projects']: return None
    from .paper_mainline import reusable_job
    try: hashes = lab.app.assemblies.get(owner)['hashes']
    except ValueError: return None
    for jid, binding in design['selected_jobs'].items():
        job = lab.app.engineering.get(owner, jid)
        if job.get('parameters', {}).get('project_path') != name: continue
        outputs = (job.get('result') or {}).get('outputs', [])
        try:
            valid = bool(outputs) and all(sha(safe_file(lab.store.root.parent/'engineering'/jid, x['name'])) == x['sha256'] for x in outputs)
        except (OSError, ValueError, KeyError): valid = False
        exact = reusable_job(design['projects'][name], job, job['status'], hashes, valid)
        if (exact['execution_reusable'] and identity(job.get('result')) == binding['result_sha256']):
            return {**job, 'candidate_input_reuse': exact, 'reused_existing_job': True}
    return None


def invoke(lab, owner, channel, body, execute):
    """Called by the original HTTP consumer; every native dispatch is bound."""
    readonly = channel == 'eda' and readonly_eda(body)
    key, clean, dispatch = begin(lab, owner, channel, body, readonly=readonly)
    if not dispatch:
        op = refresh(lab, owner, key)
        value = (op.get('result') or {}).get('native_result')
        if value is None: raise ValueError('PAPER_EXISTING_OPERATION_READ_REQUIRED: '+key)
        return {**value, 'candidate_operation_id': key, 'candidate_id': op['request']['design_id']}
    try:
        value = reuse(lab, owner, clean) if channel == 'engineering' else None
        if value is None: value = execute(clean)
    except Exception as exc:
        # Once the real executor has been entered, exception type alone cannot
        # prove no mutation occurred. Admission failures above create no action.
        finish(lab, owner, key, error=type(exc).__name__+': '+str(exc))
        raise
    finish(lab, owner, key, value)
    return {**value, 'candidate_operation_id': key, 'candidate_id': working(lab, owner)}


def inspect_check(lab, owner, operation):
    """Fixed existing P01 evaluator, exact selected inputs, no case-C verdict."""
    from ..literature_native import evaluate_native, evaluate_manifest
    from .. import literature_acceptance
    task = lab.task(owner); design = lab.design(owner, working(lab, owner))
    verify(lab, owner, design, live=True)
    if not isinstance(operation, str) or not 1 <= len(operation) <= 100: raise ValueError('OPERATION_ID_REQUIRED')
    root = Path(task['environment']['root']); workspace = root/'runtime/participants'/owner
    if sha(literature_acceptance.__file__) != task['contract']['validation_id']:
        raise ValueError('PAPER_EVALUATOR_CHANGED_RECHECK_REQUIRED')
    scope_file = safe_file(root, task['environment']['scope']['path'])
    if sha(scope_file) != task['environment']['scope']['sha256']: raise ValueError('PAPER_SCOPE_CHANGED')
    scope = json.loads(scope_file.read_text()); contract_file = safe_file(workspace, 'contract.json')
    original = json.loads(contract_file.read_text())
    if original.get('paper_id') != 'P01': raise ValueError('PAPER_ORIGINAL_CONTRACT_REQUIRED')
    assembly = lab.app.assemblies.get(owner)
    jobs = [lab.app.engineering.get(owner, jid) for jid in design['selected_jobs']]
    report = {'schema_version': 'bf-paper-native-report-v1', 'paper_id': 'P01',
              'source_identity': original['source_identity'], 'physical_verified': False,
              'full_product_passed': False, 'gaps': ['Independent core gates remain authoritative'],
              'assembly_revision': assembly['revision'], 'assembly_physical_hash': assembly['hashes']['physical_hash'],
              'jobs': [{'job_id': j['id'], 'kind': (j.get('result') or {}).get('kind')} for j in jobs]}
    stage = evaluate_native(original, owner, jobs, report, root, assembly)
    try:
        manifest = json.loads(safe_file(workspace, 'delivery/manifest.json').read_text())
        delivery = evaluate_manifest(workspace, manifest, original, assembly, stage['native_checks'])
        if 'delivery/manifest.json' not in design['files'] or any(x['path'] not in design['files'] for x in delivery['verified_files']):
            delivery = {'status': 'NOT_CHECKED', 'problems': ['Delivery inputs are not frozen in this candidate'], 'verified_files': []}
    except (OSError, ValueError, KeyError):
        delivery = {'status': 'NOT_CHECKED', 'problems': ['No current candidate-bound delivery manifest'], 'verified_files': []}
    current = {'paper': 'P01', 'owner': owner, 'candidate_id': design['design_id'],
               'evaluation': stage, 'delivery_integrity': delivery, 'live_assembly_matches': True,
               'execution': {'status': lab.app.conversations.get(owner)['status']}}
    directory = lab.root/owner/'checks'/('check-'+identity([design['design_id'], operation])[:20])
    # Reusing an operation means reusing its immutable observation, not rerunning
    # the check after reviews/inputs changed. New evidence requires a new ID.
    result_path = directory/'check.json'
    if result_path.is_file():
        prior = json.loads(result_path.read_text())
        if prior['design_id'] != design['design_id']: raise ValueError('OPERATION_CONFLICT')
        return prior
    sealed(directory/'current-input.json', current)
    current.update(result_path=str((directory/'current-input.json').relative_to(root)), result_sha256=sha(directory/'current-input.json'))
    pointer = json.loads((root/'campaign/acceptance/current.json').read_text())
    old_path = safe_file(root, pointer['path'])
    if sha(old_path) != pointer['sha256']: raise ValueError('PAPER_ACCEPTANCE_POINTER_TAMPER')
    old = next(p for p in json.loads(old_path.read_text())['papers'] if p['owner'] == owner and p['paper'] == 'P01')
    evidence = []
    for p in sorted((root/'campaign/reviews/P01/digital-gates').glob('*.json')):
        value = json.loads(p.read_text()); value['artifact'] = {'path': str(p.relative_to(root)), 'sha256': sha(p)}
        evidence.append(value)
    accepted = literature_acceptance.evaluate(root, scope, current, evidence, old.get('issues', []))
    with lab.store.connect() as db:
        pending = [dict(x) for x in db.execute("SELECT id,status FROM design_operations WHERE owner=? AND status IN ('RUNNING','UNKNOWN','WAITING_NATIVE')", (owner,))]
    if pending:
        accepted.update(full_product_passed=False, digital_engineering_status='BLOCKED_NATIVE_OPERATION')
    result = {'schema_version': 'bf-paper-candidate-check-v1', 'design_id': design['design_id'],
              'task_id': task['task_id'], 'check_id': directory.name, 'acceptance': accepted,
              'native_stage': stage, 'pending_operations': pending, 'physical': 'NOT_TESTED',
              'scope_source_sha256': sha(scope_file), 'evaluator_sha256': sha(literature_acceptance.__file__)}
    sealed(result_path, result)
    lab.event(owner, 'candidate_checked', {'design_id': design['design_id'], 'check_id': result['check_id'],
              'receipt_path': str(result_path), 'receipt_sha256': sha(result_path),
              'status': accepted['digital_engineering_status']})
    return result


def handle(lab, owner, body, operator=False):
    action = body.get('action')
    if action == 'reconcile_native':
        op = lab.operation(owner,body['job_id'])
        if op['request'].get('channel') == 'engineering':
            return reconcile_admission(lab,owner,body['job_id'],body['proof'],operator)
        if op['request'].get('body',{}).get('argv') in (['call','--help'],['debug','--help']):
            return reconcile_eda_admission(lab,owner,body['job_id'],body['proof'],operator)
        return reconcile_desktop(lab,owner,body['job_id'],body['proof'],operator)
    if action == 'inspect': return frozen_view(lab, owner, compact=body.get('view') != 'full', fields=body.get('fields', ()))
    if action == 'environment': return {'environment': lab.task(owner)['environment'], 'contract': lab.task(owner)['contract'], 'physical': 'NOT_TESTED'}
    if action == 'source': return lab.design(owner, body.get('design_id') or working(lab, owner))
    if action == 'interfaces':
        from ..interface_facts import candidate_facts
        workspace = lab.store.root.parent/'participants'/owner
        return candidate_facts(lab.design(owner, working(lab, owner)), workspace, body.get('files', ()))
    if action == 'prepare_delivery':
        if operator: raise PermissionError('PAPER_METADATA_SELECTION_PI_REQUIRED')
        from ..literature_package import prepare_candidate
        return prepare_candidate(lab, owner, body)
    if action == 'freeze':
        task = lab.task(owner)
        if body.get('parent') != working(lab, owner): raise ValueError('PAPER_WORKING_PARENT_REQUIRED')
        with lab.store.connect() as db:
            if db.execute("SELECT 1 FROM design_operations WHERE owner=? AND status IN ('UNKNOWN','RUNNING','WAITING_NATIVE')", (owner,)).fetchone():
                raise ValueError('PAPER_PENDING_OPERATION_READ_BEFORE_RETRY')
        value = lab.freeze(owner, body['sources'], body['parent'], 'operator migration' if operator else 'Pi')
        intent = {**task['intent'], 'working_design': value['design_id']}
        with lab.store.connect() as db: db.execute('UPDATE design_tasks SET intent=? WHERE owner=?', (canonical(intent), owner))
        return value
    if action == 'job': return refresh(lab, owner, body['job_id'])
    if action == 'intent':
        if body.get('kind') not in ('CONTINUE', 'BLOCKED', 'REJECT'): raise ValueError('PAPER_INTENT_INVALID')
        purpose = body.get('rationale')
        if not isinstance(purpose, str) or not purpose.strip(): raise ValueError('PAPER_DECISION_USE_REQUIRED')
        with lab.store.connect() as db:
            if body['kind'] != 'BLOCKED' and db.execute("SELECT 1 FROM design_operations WHERE owner=? AND status IN ('UNKNOWN','RUNNING','WAITING_NATIVE')", (owner,)).fetchone():
                raise ValueError('PAPER_PENDING_OPERATION_READ_BEFORE_RETRY')
            intent = {'kind': body['kind'], 'working_design': working(lab, owner), 'rationale': purpose}
            plan = body.get('plan', lab.task(owner)['plan'])
            if not isinstance(plan, list) or len(canonical(plan)) > 12000: raise ValueError('TASK_PLAN_INVALID')
            db.execute('UPDATE design_tasks SET intent=?,plan=?,status=? WHERE owner=?', (canonical(intent), canonical(plan), body['kind'], owner))
            lab.event(owner, 'candidate_decision', intent, db)
        return frozen_view(lab, owner)
    if action == 'adopt':
        if operator: raise PermissionError('PAPER_DESIGN_DECISION_PI_REQUIRED')
        if body.get('design_id') != working(lab, owner): raise ValueError('PAPER_WORKING_DESIGN_REQUIRED')
        verify(lab, owner, lab.design(owner, body['design_id']), live=True)
        with lab.store.connect() as db:
            if db.execute("SELECT 1 FROM design_operations WHERE owner=? AND status IN ('UNKNOWN','RUNNING','WAITING_NATIVE')", (owner,)).fetchone():
                raise ValueError('PAPER_PENDING_OPERATION_READ_BEFORE_RETRY')
        return lab.adopt(owner, body['design_id'], body['expected_revision'], body['rationale'], operator=operator)
    if action == 'check': return inspect_check(lab, owner, body.get('operation_id') or body.get('job_id'))
    if action in ('events', 'ack', 'skill'):
        return None  # Existing DesignLab implementation remains authoritative.
    if action == 'submit':
        from .paper_delivery import submit
        return submit(lab, owner, body.get('job_id'), body.get('rationale'), operator)
    if action in ('run', 'observe', 'start', 'qualify'):
        raise ValueError('PAPER_ACTION_NOT_QUALIFIED: native tools must enter the bound candidate path; C-case execution/evaluation is denied')
    raise ValueError('DESIGN_ACTION_INVALID')
