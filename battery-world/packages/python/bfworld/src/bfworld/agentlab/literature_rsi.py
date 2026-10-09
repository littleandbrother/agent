"""Bounded paper-task preparation and independent algebraic qualification.

This development uses the existing Pi product launcher, proxy and trace. It does
not change the scientific apparatus, old engineering or any participant's score.
"""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import time

REPO = Path(__file__).resolve().parents[6]
CONFIG = REPO / 'configs/reference_cases/literature-rsi-v1/protocol.json'
BASE_INSTRUCTIONS = '''这是近期论文的有限数字工程任务。读取 TASK.md、task-input.json 和 sources.json，按需使用当前冻结技能；实际数字资料在 source-pages.json。只在当前工作目录生成 answer.json 与 report.md，核对单位与资料出处，区分作者原设计和新增约束。工程计算、Pi 的实际工作和物理验证分别记录。原生整机、立创和外部付费作业不属于这个局部任务。不要修改 task-input.json、sources.json 或资料来迎合答案。已有论文的手动操作和未决接口应保留。只能由独立检查器作验收，自己的通过总结不等于验收。'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with path.open('x') as stream:
        stream.write(data)


def expected(task):
    """Classical no-Agent arithmetic; never copied into participant context."""
    a = task['inputs']
    d = lambda key: Decimal(str(a[key]))
    if task['id'] == 'P01-ledger':
        total = sum(d(k) for k in ['connected_mcu_uW', 'cdc_uW', 'peak_detector_uW', 'other_management_uW', 'converter_uW'])
        return {'component_total_uW': float(total),
                'reported_nominal_margin_uW': float(d('harvest_uW') - d('reported_total_uW')),
                'component_nominal_margin_uW': float(d('harvest_uW') - total),
                'boot_and_connection_uJ': float(d('boot_uJ') + d('connection_uJ'))}
    if task['id'] == 'P01-reserve-change':
        energy = (d('boot_uJ') + d('connection_uJ')) * (1 + d('reserve_fraction'))
        per_uF = (d('upper_V')**2 - d('floor_V')**2) * d('efficiency') / 2
        selected = next((Decimal(str(c)) for c in sorted(a['capacitor_options_uF']) if Decimal(str(c))*per_uF >= energy), None)
        if selected is None:
            raise ValueError('NO_FEASIBLE_CAPACITOR')
        return {'required_energy_uJ': float(energy), 'minimum_capacitance_uF': float(energy/per_uF),
                'selected_capacitance_uF': float(selected), 'usable_energy_uJ': float(selected*per_uF),
                'margin_uJ': float(selected*per_uF - energy)}
    if task['id'] == 'P02-duty-bound':
        energy = d('capacitance_mF')/1000 * (d('upper_V')**2 - d('floor_V')**2)/2
        idle = d('node_V') * d('idle_mA')/1000
        peak = d('node_V') * d('peak_mA')/1000
        idle_energy = idle * d('window_s')
        return {'stored_energy_J': float(energy), 'idle_power_W': float(idle), 'peak_power_W': float(peak),
                'idle_window_energy_J': float(idle_energy), 'maximum_total_active_s': float((energy-idle_energy)/(peak-idle))}
    raise ValueError('TASK_NOT_DECLARED')


def evaluate_answer(task, source, answer):
    problems = []
    if answer.get('schema_version') != 'bf-literature-engineering-answer-v1':
        problems.append('ANSWER_SCHEMA')
    if answer.get('task_id') != task['id']:
        problems.append('TASK_IDENTITY')
    if answer.get('source_sha256') != source['assets']['article.pdf']['sha256']:
        problems.append('SOURCE_IDENTITY')
    values = answer.get('values', {})
    for key, target in expected(task).items():
        value = values.get(key)
        tolerance = max(abs(target)*0.0001, 0.000001)
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value-target) > tolerance:
            problems.append('VALUE:' + key)
    boundaries = answer.get('boundaries', {})
    for key, value in task['required_boundaries'].items():
        if boundaries.get(key) is not value:
            problems.append('BOUNDARY:' + key)
    if not isinstance(answer.get('source_locators'), list) or not answer['source_locators']:
        problems.append('SOURCE_LOCATORS')
    return {'status': 'PASS' if not problems else 'FAIL', 'problems': problems,
            'engineering_scope': 'source-bound algebraic checks only', 'physical_verification': 'NOT_TESTED',
            'agent_contribution': 'Requires a separately bound real Pi execution receipt and no candidate edits.'}


def verify_method(harness):
    from .store import identity
    from .skill_resources import verify
    value = load(harness / 'manifest.json')
    if identity({k: v for k, v in value.items() if k != 'identity'}) != value['identity']:
        raise ValueError('HARNESS_MANIFEST_TAMPER')
    for name, digest in value['source_files'].items():
        if sha(harness / name) != digest:
            raise ValueError('HARNESS_SOURCE_TAMPER')
    for name, digest in value['loaded_files'].items():
        if sha(harness / 'dist' / name) != digest:
            raise ValueError('HARNESS_BUILD_TAMPER')
    verify(harness / 'resources', value['resource_manifest']['sha256'])
    return value


def verify_prepared(root):
    record = load(root / 'prepared.json')
    for name, digest in record['files'].items():
        if sha(root / name) != digest:
            raise ValueError('STUDY_INPUT_TAMPER:' + name)
    for source in load(root / 'sources.json')['papers']:
        for asset in source['assets'].values():
            if sha(root / asset['path']) != asset['sha256']:
                raise ValueError('SOURCE_CONTENT_TAMPER')
    verify_method(Path(record['harness']))
    if sha(Path(__file__)) != record['evaluator_sha256']:
        raise ValueError('EVALUATOR_CHANGED_AFTER_PREPARATION')
    return record


def check_authorization(root, *, at=None, spent=0, solver_traces=0, candidates=0):
    value = load(root / 'authorization.json')
    if type(value.get('max_usd')) not in (int, float) or not math.isfinite(value['max_usd']) or value['max_usd'] <= 0:
        raise ValueError('NUMERIC_BUDGET_REQUIRED')
    deadline = datetime.fromisoformat(value['expires_at_utc'].replace('Z', '+00:00')).timestamp()
    if (time.time() if at is None else at) >= deadline:
        raise ValueError('STUDY_WALL_BUDGET')
    # With per-session authority, `spent` is the current owner's liability,
    # never a sum of unrelated sessions. Old shared protocols retain their rule.
    if spent >= value['max_usd']:
        raise ValueError('STUDY_USD_BUDGET')
    if solver_traces > value['max_solver_traces'] or candidates > value['max_candidates']:
        raise ValueError('STUDY_TRIAL_BUDGET')
    return value, deadline


def qualify_candidate(body, permitted_trials):
    required = {'target', 'instruction', 'hypothesis', 'falsifier', 'applies_to', 'evidence_trials'}
    if set(body) != required or body['target'] != 'literature_method_overlay':
        raise ValueError('CANDIDATE_SCOPE')
    if any(not isinstance(body[k], str) or not body[k].strip() for k in ['instruction', 'hypothesis', 'falsifier', 'applies_to']):
        raise ValueError('CANDIDATE_EXPLANATION_REQUIRED')
    if len(body['instruction']) > 6000:
        raise ValueError('CANDIDATE_TOO_LARGE')
    if not body['evidence_trials'] or not set(body['evidence_trials']).issubset(set(permitted_trials)):
        raise ValueError('CANDIDATE_FEEDBACK_LEAK')
    return {'status': 'BUILT_NOT_QUALIFIED', 'instruction_sha256': hashlib.sha256(body['instruction'].encode()).hexdigest(),
            'adopted': False, 'target': body['target']}


def comparison(pairs):
    if len(pairs) != 3 or {p['split'] for p in pairs} != {'development', 'new-variant', 'cross-paper'}:
        raise ValueError('PAIRED_QUALIFICATION_INCOMPLETE')
    for pair in pairs:
        if pair['parent']['task_sha256'] != pair['child']['task_sha256']:
            raise ValueError('PAIRED_TASK_MISMATCH')
        if pair['parent']['environment_sha256'] != pair['child']['environment_sha256']:
            raise ValueError('PAIRED_ENVIRONMENT_MISMATCH')
    regressions = [p['task'] for p in pairs if p['parent']['evaluation']['status'] == 'PASS' and p['child']['evaluation']['status'] != 'PASS']
    recoveries = [p['task'] for p in pairs if p['parent']['evaluation']['status'] != 'PASS' and p['child']['evaluation']['status'] == 'PASS']
    return {'status': 'REJECTED_REGRESSION' if regressions else 'LOCAL_QUALIFIED' if recoveries else 'NO_MEASURED_BENEFIT',
            'regressions': regressions, 'recoveries': recoveries, 'production_adopted': False,
            'statistical_transfer_claim': False, 'recursive_self_improvement_claim': False}


def validate_billing_liabilities(rows, permitted):
    from .store import identity
    approved = {x['id']: x['original_row_sha256'] for x in permitted}
    for row in rows:
        if row['status'] == 'UNKNOWN' and approved.get(row['id']) != identity(row):
            raise ValueError('NEW_UNKNOWN_USAGE_STOP')


def prepare(root, harness):
    protocol = load(CONFIG)
    method = verify_method(harness)
    authorization, _ = check_authorization(root)
    index = []
    for paper in protocol['papers']:
        assets = {}
        for name in ['article.pdf', 'article.xml', 'supplement.pdf']:
            path = root / 'sources' / paper['id'] / name
            if path.is_file():
                assets[name] = {'path': str(path.relative_to(root)), 'sha256': sha(path), 'bytes': path.stat().st_size}
        if not {'article.pdf', 'article.xml'}.issubset(assets):
            raise ValueError('ARTICLE_SOURCE_REQUIRED')
        pages = load(root / 'sources' / paper['id'] / 'article-pages.json')
        index.append({**paper, 'assets': assets, 'article_page_count': len(pages),
                      'supplement_acquired': 'supplement.pdf' in assets,
                      'native_cad_pcb_firmware': 'NOT_OBTAINED; no inference from article figures or analysis code'})
    write_once(root / 'sources.json', {'schema_version': 'bf-literature-reference-index-v1', 'papers': index})
    write_once(root / 'protocol.json', protocol)
    for task in protocol['tasks']:
        folder = root / 'public-tasks' / task['id']
        source = next(p for p in index if p['id'] == task['paper'])
        write_once(folder / 'task-input.json', task)
        write_once(folder / 'sources.json', source)
        pages = load(root / 'sources' / task['paper'] / 'article-pages.json')
        write_once(folder / 'source-pages.json', [p for p in pages if p['page'] in source['pages']])
        (folder / 'TASK.md').write_text(BASE_INSTRUCTIONS + '\n\n' + task['deliverable'] + '\n\nRequired answer schema:\n' + json.dumps(protocol['answer_schema'], ensure_ascii=False, indent=2) + '\n')
    reference_checks = []
    for task in protocol['tasks']:
        source = next(p for p in index if p['id'] == task['paper'])
        answer = {'schema_version': 'bf-literature-engineering-answer-v1', 'task_id': task['id'],
                  'source_sha256': source['assets']['article.pdf']['sha256'], 'values': expected(task),
                  'boundaries': task['required_boundaries'], 'source_locators': [task['paper'] + ': article pages in source index']}
        positive = evaluate_answer(task, source, answer)
        wrong_unit = json.loads(json.dumps(answer)); first = task['required_values'][0]; wrong_unit['values'][first] *= 1000
        physical = {**answer, 'boundaries': {**answer['boundaries'], 'physical_verified': True}}
        negatives = {'wrong_units': evaluate_answer(task, source, wrong_unit),
                     'wrong_source': evaluate_answer(task, source, {**answer, 'source_sha256': '0'*64}),
                     'unsupported_physical_claim': evaluate_answer(task, source, physical)}
        if positive['status'] != 'PASS' or any(v['status'] != 'FAIL' for v in negatives.values()):
            raise ValueError('NO_AGENT_REFERENCE_FAILED')
        reference_checks.append({'task': task['id'], 'expected': answer, 'positive': positive, 'negative_controls': negatives})
    write_once(root / 'private-evaluation/no-agent.json', {'actor': 'Codex classical arithmetic reference',
        'provider_calls': 0, 'native_whole_system_jobs': 0, 'checks': reference_checks})
    names = ['protocol.json', 'sources.json', 'authorization.json', 'private-evaluation/no-agent.json']
    names += [str(p.relative_to(root)) for p in sorted((root / 'public-tasks').rglob('*')) if p.is_file()]
    record = {'schema_version': 'bf-literature-study-prepared-v1', 'harness': str(harness),
              'harness_identity': method['identity'], 'method': 'M0', 'original_harness_label': method['label'],
              'evaluator_sha256': sha(__file__), 'files': {name: sha(root/name) for name in names},
              'authorization': authorization, 'no_agent_reference': 'PASS',
              'claim': 'Prepared local algebraic paper tasks; no Pi results, full reproduction, transfer efficacy or hardware verification yet.'}
    write_once(root / 'prepared.json', record)
    verify_prepared(root)
    return record


def execute(root, ledger_home=None):
    """One serial generation using the existing credential-holding proxy and Pi.

    The task guard is common to all arms. Model and native-engine billing in the
    previous workbench is never touched. Ambiguous attempts are not reissued.
    """
    import shutil
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.parse import urlparse
    from . import launcher
    from .server import Workbench, handler
    from .store import canonical, identity
    from .model_profile import ENGINEERING

    record = verify_prepared(root)
    authorization, deadline = check_authorization(root)
    readiness = load(root / 'provider-readiness.json')
    balance = next(x for x in readiness['requests'] if x['route'] == '/user/balance')
    models = next(x for x in readiness['requests'] if x['route'] == '/models')
    if balance.get('is_available') is not True or 'deepseek-flash' not in models.get('models', []):
        raise ValueError('PROVIDER_NOT_READY')
    protocol = load(root / 'protocol.json')
    harness = Path(record['harness'])
    # Operator PI path is part of executable identity, not merely source notes.
    # Reject a deployment/config mismatch before creating a participant or bill.
    from .runtime_config import PI
    manifest = load(harness/'manifest.json')
    if sha(PI/'packages/bf-agent/dist'/manifest['app_entry']) != manifest['app_build_hash']:
        raise ValueError('ACTIVE_PI_BUILD_DIFFERS_FROM_FROZEN_APP')
    runtime = Path(ledger_home) if ledger_home else root / 'runtime'
    app = Workbench(runtime / 'state')
    with app.store.connect() as db:
        old = db.execute('SELECT * FROM research_model_studies WHERE protocol=?', (protocol['id'],)).fetchone()
        if old is None:
            if db.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0]:
                raise ValueError('NEW_STUDY_REQUIRES_EMPTY_LEDGER')
            db.execute('UPDATE model_limits SET total_usd=?,max_tokens=?,expires=? WHERE id=1',
                       (authorization['max_usd'], 175000000, deadline))
            db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',
                       (protocol['id'], time.time(), deadline, authorization['max_usd'], protocol['model'], canonical(authorization)))
        elif (authorization.get('budget_scope') != 'per-session' and old['max_usd'] != authorization['max_usd']) or old['expires'] != deadline:
            raise ValueError('BUDGET_IDENTITY_CHANGED')
        liabilities = load(root/'authorized-liabilities.json') if (root/'authorized-liabilities.json').is_file() else None
        if liabilities:
            if not liabilities.get('direct_user_authorization'):
                raise ValueError('UNKNOWN_USAGE_CONTINUATION_NOT_AUTHORIZED')
            for item in liabilities['requests']:
                existing = db.execute('SELECT * FROM model_requests WHERE id=?', (item['id'],)).fetchone()
                if not existing or identity(dict(existing)) != item['original_row_sha256']:
                    raise ValueError('UNKNOWN_LIABILITY_CHANGED')
            continuation = db.execute('SELECT * FROM research_usage_continuations WHERE protocol=?', (protocol['id'],)).fetchone()
            if continuation is None:
                db.execute('INSERT INTO research_usage_continuations VALUES(?,?,?,?)',
                           (protocol['id'], time.time(), deadline, canonical(liabilities)))
    original_complete = app.provider.complete
    def guarded_complete(*args, **kwargs):
        check_authorization(root)
        # Permission to carry one known interface failure never authorizes a new
        # missing-usage request or changes its original reservation/UNKNOWN row.
        with app.store.connect() as db:
            resolved = app.provider.recovery.resolved(db)
            rows = [dict(r) for r in db.execute("SELECT * FROM model_requests WHERE status='UNKNOWN'") if r['id'] not in resolved]
            validate_billing_liabilities(rows, liabilities['requests'] if liabilities else [])
        return original_complete(*args, **kwargs)
    app.provider.complete = guarded_complete
    OriginalHandler = handler(app)
    class TaskHandler(OriginalHandler):
        def do_POST(self):
            # These local tasks cannot dispatch native engineering or EDA writes.
            if urlparse(self.path).path not in {'/v1/chat/completions', '/api/skills'}:
                self.reply(403, {'error': 'LOCAL_PAPER_TASK_MUTATION_DENIED'})
                return
            super().do_POST()
    server = ThreadingHTTPServer(('127.0.0.1', 0), TaskHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    app.conversations.port = server.server_port
    environment = identity({'harness': record['harness_identity'], 'evaluator': record['evaluator_sha256'],
                            'protocol': sha(root/'protocol.json'), 'model_profile': ENGINEERING,
                            'task_guard': 'local-paper-task-read-and-skill-only-v1'})
    write_once(root/'runtime-start.json', {'started': time.time(), 'port': server.server_port,
        'environment_sha256': environment, 'provider_source_sha256': sha(Path(__file__).parent/'provider.py'),
        'controller_source_sha256': sha(__file__), 'old_workbench_modified': False})
    trials = {}

    def run_one(trial_id, task=None, overlay='', experience=None):
        kind = 'solver' if task else 'improver'
        attempt = root/'trials'/trial_id/'attempt.json'
        if attempt.exists():
            raise ValueError('ATTEMPT_ALREADY_RECORDED_NO_AUTOMATIC_REPLAY:' + trial_id)
        started = list((root/'trials').glob('*/attempt.json'))
        counts = [load(p)['kind'] for p in started]
        status = app.provider.status()
        check_authorization(root, spent=0 if authorization.get('budget_scope') == 'per-session' else status['upper_bound_usd'],
            solver_traces=counts.count('solver') + (kind == 'solver'),
            candidates=counts.count('improver') + (kind == 'improver'))
        with app.store.connect() as db:
            resolved = app.provider.recovery.resolved(db)
            rows = [dict(r) for r in db.execute("SELECT * FROM model_requests WHERE status='UNKNOWN'") if r['id'] not in resolved]
            validate_billing_liabilities(rows, liabilities['requests'] if liabilities else [])
        if task:
            text = f"执行本轮局部任务 {task['id']}。请先读取 TASK.md 和 task-input.json，自己核对资料并计算，生成严格符合规定字段与单位的 answer.json 和简短 report.md。不要只写计划。source_locators 应明确写出页码、图号或方法段落。无需请求人工确认。"
        else:
            text = '''你是独立的 Pi-Improver。读取 experience.json、允许的真实公开轨迹与检查回执，提出一个可被推翻的通用方法改进。只允许修改 literature_method_overlay 的指令文本：它会实际加载到下一轮 Pi 的 shared context。基础模型、工具、任务、评价器、预算、权限和论文数据均不可改；不能将当前案例数值或答案作为通用默认值。若没有合理改进，写 candidate.json 为 {"status":"NO_OP","reason":"实际原因"}，不要制造升级。否则写 candidate.json，恰好包含 target、instruction、hypothesis、falsifier、applies_to、evidence_trials 六个字段；target 为 literature_method_overlay，instruction 最多6000字，evidence_trials 仅可引用 experience.json 中提供的开发任务。另写 report.md 解释预期变化与可能退化。候选不能自行通过或采用。'''
        def stage(cid):
            workspace = runtime/'participants'/cid
            workspace.mkdir(parents=True, exist_ok=True)
            if task:
                for path in (root/'public-tasks'/task['id']).iterdir():
                    shutil.copyfile(path, workspace/path.name)
            else:
                write_once(workspace/'experience.json', experience)
                (workspace/'TASK.md').write_text(text)
            with app.store.connect() as db:
                db.execute('UPDATE conversations SET harness=? WHERE id=?', (str(harness), cid))
                db.execute('INSERT INTO research_model_owners VALUES(?,?,?)', (cid, protocol['id'], trial_id))
                db.execute('INSERT INTO owner_model_caps VALUES(?,?)', (cid, authorization['max_usd']))
                db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('model_profile:' + cid, canonical(ENGINEERING['version'])))
                if authorization.get('budget_scope') == 'per-session':
                    # The existing proxy retains its fail-closed global envelope;
                    # that envelope is the sum of separately authorized caps, not
                    # one shared USD30 balance. Each owner still has its own cap.
                    envelope = db.execute('SELECT SUM(c.max_usd) FROM owner_model_caps c JOIN research_model_owners o ON o.owner=c.owner WHERE o.protocol=?', (protocol['id'],)).fetchone()[0]
                    db.execute('UPDATE model_limits SET total_usd=? WHERE id=1', (envelope,))
                    db.execute('UPDATE research_model_studies SET max_usd=? WHERE protocol=?', (envelope, protocol['id']))
        operation = protocol['id'] + '-' + identity({'revision': str(root), 'trial': trial_id})[:24]
        conversation = app.conversations.create(text, None, operation,
                                                preflight=stage, defer_dispatch=True)
        cid = conversation['id']
        context = {'folder_id': protocol['id'], 'folder_name': '论文局部工程与方法开发', 'revision': 0,
                   'memory': '', 'prompt': BASE_INSTRUCTIONS + ('\n采用的候选方法：\n' + overlay if overlay else ''),
                   'tools': ['read', 'edit', 'write', 'bash', 'bf_engineering'], 'harness_revision': None}
        method_id = identity({'harness': record['harness_identity'], 'base': BASE_INSTRUCTIONS, 'overlay': overlay})
        app.organization.bind(cid, context)
        write_once(attempt, {'trial': trial_id, 'kind': kind, 'owner': cid, 'started': time.time(),
                            'method_identity': method_id, 'task': task['id'] if task else None})
        done = threading.Event()
        watcher = None
        def ready(proc):
            nonlocal watcher
            app.conversations.processes[cid] = proc
            app.conversations.state(cid, 'RUNNING')
            app.conversations.drain(cid, proc)
            def watch():
                while not done.wait(.15):
                    app.conversations.ingest(cid)
            watcher = threading.Thread(target=watch, daemon=True); watcher.start()
        try:
            receipt = launcher.launch(harness, None, label=cid, store_root=app.store.root,
                service_port=server.server_port, home_root=runtime, shared_context=context,
                product=True, on_process=ready)
        finally:
            done.set()
            if watcher: watcher.join()
            app.conversations.processes.pop(cid, None)
        workspace = runtime/'participants'/cid
        session = runtime/'sessions'/cid
        app.conversations.ingest(cid, execution_state=False)
        with app.store.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT id,status,reserved,charged,usage,error FROM model_requests WHERE owner=?', (cid,))]
            wires = [json.loads(r['wire']) for r in db.execute('SELECT wire FROM model_request_evidence WHERE owner=?', (cid,))]
        contents = [m.get('content', '') for wire in wires for m in wire.get('messages', [])]
        contents = ['\n'.join(b.get('text', '') for b in c if isinstance(b, dict)) if isinstance(c, list) else c for c in contents]
        activated = any(isinstance(c, str) and BASE_INSTRUCTIONS in c and (not overlay or overlay in c) for c in contents)
        result = {'trial': trial_id, 'kind': kind, 'owner': cid, 'method_identity': method_id,
                  'environment_sha256': environment, 'receipt': str(session/'receipt.json'),
                  'trace': str(session/'trace.jsonl'), 'trace_sha256': sha(session/'trace.jsonl'),
                  'process_status': receipt['status'], 'model_calls': len(rows),
                  'cost_upper_bound_usd': sum(r['charged'] if r['status'] == 'SETTLED' else r['reserved'] for r in rows),
                  'usage_fully_settled': all(r['status'] == 'SETTLED' for r in rows),
                  'method_in_actual_request': activated, 'human_candidate_edits': 0,
                  'preparation_actor': 'Codex', 'design_actor': 'Pi' if task else None}
        if task:
            result['task_sha256'] = sha(root/'public-tasks'/task['id']/'task-input.json')
            try:
                source = load(root/'public-tasks'/task['id']/'sources.json')
                answer = load(workspace/'answer.json')
                result['evaluation'] = evaluate_answer(task, source, answer)
                result['answer_sha256'] = sha(workspace/'answer.json')
                for name in ['task-input.json', 'sources.json', 'source-pages.json', 'TASK.md']:
                    if sha(workspace/name) != sha(root/'public-tasks'/task['id']/name):
                        result['evaluation']['problems'].append('PARTICIPANT_INPUT_CHANGED:' + name)
                if not (workspace/'report.md').is_file():
                    result['evaluation']['problems'].append('REPORT_MISSING')
            except (OSError, ValueError, TypeError, KeyError) as exc:
                result['evaluation'] = {'status': 'FAIL', 'problems': [type(exc).__name__ + ': ' + str(exc)], 'physical_verification': 'NOT_TESTED'}
            if receipt['status'] != 'COMPLETED' or not rows or not result['usage_fully_settled'] or not activated:
                result['evaluation']['problems'].append('EXECUTION_OR_ACTIVATION_NOT_VERIFIED')
            if result['evaluation']['problems']:
                result['evaluation']['status'] = 'FAIL'
            trials[trial_id] = result
        else:
            result['candidate_path'] = str(workspace/'candidate.json')
        write_once(root/'trials'/trial_id/'result.json', result)
        print(json.dumps({'trial': trial_id, 'process': result['process_status'], 'evaluation': result.get('evaluation', {}).get('status'),
                          'model_calls': len(rows), 'cost_upper_bound_usd': result['cost_upper_bound_usd']}, ensure_ascii=False), flush=True)
        if not rows or not result['usage_fully_settled']:
            raise ValueError('MODEL_EXECUTION_OR_USAGE_UNAVAILABLE_STOP')
        return result

    try:
        tasks = {t['id']: t for t in protocol['tasks']}
        for plan in protocol['trial_plan'][:3]:
            run_one(plan['id'], tasks[plan['task']])
        # Only the predeclared development task is visible to the improver.
        experience = []
        for name in protocol['improver_visible_trials']:
            trial = trials[name]; trace = Path(trial['trace'])
            public = []
            for line in trace.read_text().splitlines():
                event = json.loads(line)
                if event.get('type') == 'message' and event.get('message', {}).get('role') == 'assistant':
                    content = event['message'].get('content', [])
                    blocks = [b.get('text', '') for b in content if b.get('type') == 'text']
                    if blocks: public.append({'type': 'assistant_public_text', 'text': '\n'.join(blocks)})
                elif event.get('type') in {'tool_execution_start', 'tool_execution_end'}:
                    public.append({k: v for k, v in event.items() if k in {'type', 'toolName', 'args', 'isError', 'result'}})
            answer_path = runtime/'participants'/trial['owner']/'answer.json'
            experience.append({'trial': name, 'evaluation': trial['evaluation'], 'raw_trace_sha256': trial['trace_sha256'],
                               'public_trace': public, 'candidate_answer': load(answer_path) if answer_path.is_file() else None,
                               'external_candidate_edits': 0})
        improver = run_one('Pi-improver-01', experience=experience)
        body = load(improver['candidate_path'])
        if body.get('status') == 'NO_OP':
            outcome = {'status': 'NO_OP', 'reason': body.get('reason'), 'production_adopted': False,
                       'recursive_self_improvement_claim': False}
        else:
            candidate = qualify_candidate(body, protocol['improver_visible_trials'])
            candidate.update(parent_method='M0', child_method='M1', actor='Pi',
                             improver_owner=improver['owner'], candidate_sha256=sha(improver['candidate_path']))
            write_once(root/'candidate-01.json', candidate)
            for plan in protocol['trial_plan'][3:]:
                run_one(plan['id'], tasks[plan['task']], body['instruction'])
            pairs = [{'task': t['id'], 'split': t['split'], 'parent': trials[a['id']], 'child': trials[b['id']]}
                     for t, a, b in zip(protocol['tasks'], protocol['trial_plan'][:3], protocol['trial_plan'][3:])]
            outcome = {**comparison(pairs), 'pairs': pairs}
        write_once(root/'comparison.json', outcome)
        return outcome
    except Exception as exc:
        failure = {'status': 'INTERRUPTED', 'reason': type(exc).__name__ + ': ' + str(exc),
                   'completed_solver_trials': len(trials), 'provider': app.provider.status(),
                   'production_adopted': False, 'recursive_self_improvement_claim': False}
        # No credentials or complete request bodies in the summary.
        write_once(root/'interruption.json', failure)
        raise
    finally:
        server.shutdown(); server.server_close(); app.stop.set(); app.thread.join(timeout=3)
        app.lock.close()
