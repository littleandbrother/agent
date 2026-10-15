"""Candidate-bound report authoring. Pi supplies content; fixed code draws/checks it.

Reports append artifacts to a System Commit; they never edit its engineering tree.
The original owner, native jobs, evidence and accounting remain authoritative.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

from ..store import canonical, identity
from .contracts import sealed
from .repository import file_hash, name

SCOPES = ('power', 'firmware', 'lead')


def document_schema(scope):
    common = {'schema_version': 'bf-report-author-content-v1', 'report_id': 'RP-...',
              'system_commit': 'SC-...', 'scope': scope}
    examples = {
        'power': {'circuit_groups': [{'id': 'input', 'title': '采能输入与检测',
                    'refs': ['J1', 'D2', 'R1', 'R2', 'C1'], 'notes': ['按冻结网表解释本组实际电流路径']}],
                  'pcb_regions': [{'name': '采能输入', 'refs': ['J1'], 'description': '接口和邻近器件的实际位置'}],
                  'energy_interpretation': ['说明当前 RAW 的电压、积分结果和异常'],
                  'conclusions': ['实际电路问题与后续工程修订分开记录']},
        'firmware': {'participants': [{'id': 'mcu', 'label': 'MCU / 策略'},
                       {'id': 'cdc', 'label': 'AD7156 / I2C'}, {'id': 'ble', 'label': 'S132 / BLE'},
                       {'id': 'pc', 'label': 'PC / 解码'}],
                     'messages': [{'from': 'mcu', 'to': 'ble', 'label': '启动广播',
                       'time': '人工接通后首次 tick', 'kind': 'start',
                       'source': {'path': 'project-fw-s132/app_policy.c', 'symbol': 'app_tick'}}],
                     'constraints': [{'label': '广播参数', 'value': '按当前源码填写',
                       'source': {'path': 'project-fw-s132/main.c', 'symbol': 'APP_ADV_INTERVAL'}}],
                     'explanations': ['解释启动、采样、通知、错误及断线恢复的时序']},
        'lead': {'summary': '当前候选的直接结论', 'task': '当前首版任务及人工操作边界',
                 'system_modules': [{'label': '机械输入', 'description': '来自当前工程的说明'}],
                 'pages': [{'page': i, 'conclusion': '该页实际结论', 'notes': ['说明来源或具体待解决工程问题']} for i in range(1, 9)],
                 'requirements': [{'requirement': '固件事件行为', 'gate': 'firmware_event_logic',
                                    'result': '读取当前独立检查后填写'}],
                 'assembly_notes': ['装配关系、运动间隙和缺失尺寸的实际情况'],
                 'handoff': ['打开工程、复核结果和继续设计的具体步骤']},
    }
    return {'scope': scope, 'example': {**common, **examples[scope]},
            'rules': ['power.circuit_groups 必须恰好覆盖冻结原理图全部器件，每个器件一次；同版网表重排，不改接线。',
                      'firmware.messages 至少12条；kind 至少包含 start/sample/notify/error/disconnect；每条有实际源码 path + symbol。',
                      'lead.pages 必须包含1–8页；requirements 覆盖全部当前工程门。',
                      '所有内容属于明确 report_id 和 system_commit；使用简洁中文，不编造物理试验或缺失尺寸。']}


def locate(repo, owner, report_id):
    name(report_id)
    root = repo.root/'reports'/report_id
    value = json.loads((root/'input/report-input.json').read_text())
    repo.project(value['project']['id'], owner)
    if value['report_id'] != report_id: raise ValueError('REPORT_ID_MISMATCH')
    from .report_assets import verify_input
    verify_input(root/'input')
    return root, value


def prepare(repo, owner, body):
    p = repo.leader(body['project_id'], owner)
    s = repo.system(p['id'], body['system_id'])
    from .repository_view import previews, artifact
    from .repository_validation import qualification
    q = qualification(repo, s)
    s = {**s, 'validations': q['gates'], 'current_qualification': q}
    sources = []
    for path, ref in s['files'].items(): sources.append(('candidate', path, ref, None, repo.root/'blobs'/ref['sha256']))
    for ref in previews(repo, s):
        src, _ = artifact(repo, p['id'], owner, s['id'], ref['name'], preview=True)
        sources.append(('previews', ref['name'], ref, None, src))
    selected = {'input.json','result.json','project-numeric-observations.json','project-trace.raw',
                'project-cad_summary.json','project-readback.json','project-preview-mesh.json'}
    for job, record in s['jobs'].items():
        for path, ref in record.get('artifacts', {}).items():
            if path in selected: sources.append(('jobs', path, ref, job, repo.root/'blobs'/ref['sha256']))
    assets = [{'kind': kind, 'path': path, 'job_id': job,
               'local_path': str(Path('sources')/kind/(job or '')/path),
               'sha256': ref['sha256'], 'bytes': ref['bytes'], 'system_commit': s['id']}
              for kind, path, ref, job, _ in sources]
    value = {'schema_version': 'bf-engineering-report-input-v1', 'project': p, 'system': s,
             'current_system': p['submitted'], 'adopted_system': p['adopted'], 'assets': assets,
             'report_scope': 'same-version engineering review', 'report_policy': 'connected-circuits-sequence-v1'}
    rid = 'RP-' + identity(value); value['report_id'] = rid
    def apply(db):
        root = repo.root/'reports'/rid
        for record, (_, _, _, _, src) in zip(assets, sources):
            if file_hash(src) != record['sha256']: raise ValueError('REPORT_SOURCE_CHANGED')
            dest = root/'input'/record['local_path']; dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and file_hash(dest) != record['sha256']: raise ValueError('REPORT_INPUT_CHANGED')
            if not dest.exists(): shutil.copyfile(src, dest); dest.chmod(0o400)
        sealed(root/'input/report-input.json', value)
        from .report_assets import fact_pack
        sealed(root/'facts.json', fact_pack(root/'input'))
        repo.lab.event(owner, 'engineering_report_prepared', {'report_id': rid, 'system_commit': s['id']}, db)
        return {'id': rid, 'report_id': rid, 'project_id': p['id'], 'system_commit': s['id'],
                'assets': len(assets), 'path': 'facts.json', 'scopes': list(SCOPES)}
    return repo.mutate(owner, body, apply)


def role(repo, owner):
    p = repo.project(repo.bound(owner), owner)
    if p['owner'] == owner: return 'lead'
    from .repository_actions import task
    return task(repo, owner)['role']


def authors(root):
    result = {}
    for scope in SCOPES:
        pointer = root/'authors'/(scope+'.json')
        if pointer.exists(): result[scope] = json.loads(pointer.read_text())
    return result


def validate_content(content, scope, value, folder):
    if content.get('schema_version') != 'bf-report-author-content-v1' or content.get('scope') != scope:
        raise ValueError('REPORT_CONTENT_SCHEMA')
    if content.get('report_id') != value['report_id'] or content.get('system_commit') != value['system']['id']:
        raise ValueError('REPORT_CONTENT_CANDIDATE')
    from .report_assets import check_author
    check_author(content, scope, value, folder)


def write(repo, owner, body):
    root, value = locate(repo, owner, body['report_id'])
    scope = body['scope']
    if scope != role(repo, owner): raise PermissionError('REPORT_AUTHOR_SCOPE')
    content = json.loads(body['content']); validate_content(content, scope, value, root/'input')
    record = {'scope': scope, 'owner': owner, 'source_author': 'Pi', 'content': content,
              'sha256': identity(content), 'report_id': value['report_id']}
    def apply(db):
        pointer = root/'authors'/(scope+'.json')
        previous = json.loads(pointer.read_text())['sha256'] if pointer.exists() else None
        if body.get('expected_sha256') != previous: raise ValueError('REPORT_AUTHOR_WRITE_CONFLICT')
        sealed(root/'author-history'/scope/(record['sha256']+'.json'), record)
        pointer.parent.mkdir(exist_ok=True); pointer.write_text(canonical(record))
        return {'id': record['sha256'], 'report_id': value['report_id'], 'project_id': value['project']['id'],
                'scope': scope, 'sha256': record['sha256'], 'status': 'CONTENT_VALIDATED'}
    return repo.mutate(owner, body, apply)


def check_build(root, value):
    pointer = root/'CURRENT-BUILD.json'
    if not pointer.exists(): raise ValueError('REQUIRED_ENGINEERING_REPORT_MISSING')
    pin = json.loads(pointer.read_text()); build = root/'builds'/pin['id']
    record = json.loads((build/'quality.json').read_text())
    if identity(record) != pin['quality_sha256']: raise ValueError('REPORT_QUALITY_TAMPER')
    if record['system_commit'] != value['system']['id'] or record['report_id'] != value['report_id']:
        raise ValueError('REPORT_BUILD_CANDIDATE')
    if record['authors'] != {k: v['sha256'] for k, v in authors(root).items()}:
        raise ValueError('REPORT_AUTHORS_CHANGED_REBUILD_REQUIRED')
    for path, ref in record['outputs'].items():
        if file_hash(build/name(path)) != ref['sha256']: raise ValueError('REPORT_OUTPUT_TAMPER')
    if record['status'] != 'PASS': raise ValueError('REQUIRED_ENGINEERING_REPORT_FAILED')
    return build, record


def required_report(repo, owner, system, report_id=None):
    if report_id is None:
        pointer = repo.root/'reports/by-system'/(system['id']+'.json')
        if not pointer.exists(): raise ValueError('REQUIRED_ENGINEERING_REPORT_MISSING')
        report_id = json.loads(pointer.read_text())['report_id']
    root, value = locate(repo, owner, report_id)
    if value['system']['id'] != system['id']: raise ValueError('REPORT_RELEASE_CANDIDATE')
    from .repository_validation import qualification
    if identity(qualification(repo, system)) != identity(value['system']['current_qualification']):
        raise ValueError('REPORT_ACCEPTANCE_CHANGED_PREPARE_AGAIN')
    build, quality = check_build(root, value)
    return build, quality


def handle(repo, owner, body):
    action = body['action']
    if action == 'repository_report_prepare': return prepare(repo, owner, body)
    if not action.startswith('repository_report_'): return None
    if action == 'repository_report_schema': return document_schema(body.get('scope') or role(repo, owner))
    root, value = locate(repo, owner, body['report_id'])
    if action == 'repository_report_read':
        path = name(body.get('path', 'facts.json'))
        if path != 'facts.json' and not path.startswith('input/sources/candidate/') and path != 'input/report-input.json' and path not in ('authors/power.json','authors/firmware.json','authors/lead.json'):
            raise ValueError('REPORT_READ_SCOPE')
        f = root/path
        if f.is_symlink() or not f.is_file(): raise ValueError('REPORT_READ_NOT_FOUND')
        text = f.read_text(errors='replace'); offset = body.get('offset', 0); limit = body.get('limit', 12000)
        if type(offset) != int or type(limit) != int or offset < 0 or not 1 <= limit <= 24000: raise ValueError('REPORT_READ_RANGE')
        return {'path': path, 'sha256': file_hash(f), 'content': text[offset:offset+limit],
                'next_offset': offset+limit if offset+limit < len(text) else None}
    if action == 'repository_report_write': return write(repo, owner, body)
    if action == 'repository_report_status':
        return {'report_id': value['report_id'], 'system_commit': value['system']['id'],
                'authors': {k: {x: v[x] for x in ('owner','sha256')} for k, v in authors(root).items()},
                'schema': document_schema(role(repo, owner))}
    if action == 'repository_report_build':
        repo.leader(value['project']['id'], owner)
        from .report_assets import build_report
        return build_report(repo, owner, body, root, value)
    raise ValueError('REPORT_ACTION_UNKNOWN')
