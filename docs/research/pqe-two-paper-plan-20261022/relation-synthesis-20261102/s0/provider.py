"""Actual Pi transport, fresh finite owners, persistent bounded public pages."""
from contextlib import contextmanager
import importlib.util
import secrets
import socket
import subprocess
from common import *
from bfworld.agentlab.pqe20261022 import pilot as p
from bfworld.agentlab.pqe20261024debt import adapter

runtime = DB.parents[2]
profile = load(runtime / 'profile.json')
os.environ.update(BF_RUNTIME_ROOT=str(runtime), BF_RUNTIME_CONFIG=str(runtime / 'runtime.json'),
    BF_HOME=profile['home'], BF_PI_ROOT=profile['pi_root'],
    BF_DEVELOPMENT_PROFILE=str(runtime / 'profile.json'),
    PI_CODING_AGENT_DIR=str(Path(profile['home']) / 'pi-config'), PYTHONDONTWRITEBYTECODE='1')
_spec = importlib.util.spec_from_file_location('relation_existing_transport',
    BASE / 'lc-service-learning/s0/runtime.py')
transport = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(transport)
_fmt = importlib.util.spec_from_file_location('relation_model_format',
    BASE / 'codebt-zeroapi/s0/model_format.py')
formatter = importlib.util.module_from_spec(_fmt)
_fmt.loader.exec_module(formatter)

LIMITS = dict(model_requests=12, tool_calls=64, numerical_inputs=18, candidates=6,
    wall_s=900, output_tokens=32768, generated_tokens=131072, usd=5., bytes=35_000_000)
p.OUT, p.PACKAGE, p.LIMITS, p.APP = OUT, PACKAGE, LIMITS, APP
p.SDK = ROOT / 'workbench/bf-architecture-v2/pi-bf-aiot/packages/coding-agent/dist/bundle/index.js'
p.TOTAL_CAPS = dict(requests=48, tool_calls=256, numerical_inputs=240, usd=20., retained_bytes=150_000_000)
p.callback_payload = transport.legacy.callback_payload


@contextmanager
def finite_service():
    """Reuse a matching live service or start and close this package's process."""
    process = None
    log = None
    def listening():
        with socket.socket() as sock:
            sock.settimeout(.2)
            return sock.connect_ex(('127.0.0.1',8980)) == 0
    before = load(runtime/'workbench/state/active-runtime.json')
    if not listening():
        ready()
        with connect() as db:
            if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():
                raise RuntimeError('PROVIDER_IN_FLIGHT_BEFORE_SERVICE_START')
        env = dict(os.environ, PYTHONPATH=str(LAB), PYTHONDONTWRITEBYTECODE='1')
        log = (HERE/'finite-server.log').open('w')
        process = subprocess.Popen([str(PYTHON),'-B','-m','bfworld.agentlab.server',
            '--root',str(DB.parent),'--port','8980'],
            env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        for _ in range(100):
            if listening() or process.poll() is not None:
                break
            time.sleep(.1)
        if not listening():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            log.close()
            raise RuntimeError('FINITE_SERVICE_NOT_LISTENING')
    try:
        actual = load(runtime/'workbench/state/active-runtime.json')
        if process is not None and actual['pid'] != process.pid:
            raise RuntimeError('FINITE_SERVICE_PID_BINDING')
        for key, path in [
            ('historical_usage_source_sha256',LAB/'bfworld/agentlab/historical_usage.py'),
            ('provider_source_sha256',LAB/'bfworld/agentlab/provider.py'),
            ('server_source_sha256',LAB/'bfworld/agentlab/server.py')]:
            if actual[key] != ref(path)['sha256']:
                raise RuntimeError('LOADED_RUNTIME_SOURCE_MISMATCH:'+key)
        save(HERE/'finite-service-open.json',dict(at=now(),started_by_package=process is not None,
             current_runtime=actual,prior_receipt_pid=before['pid']))
        yield
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            log.close()
        save(HERE/'finite-service-close.json',dict(at=now(),started_by_package=process is not None,
             package_process_stopped=process.poll() is not None if process else None,
             reused_service_left_running=process is None))


@contextmanager
def runtime_scope():
    ready()
    with connect() as db:
        if db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone():
            raise RuntimeError('OTHER_PROVIDER_IN_FLIGHT')
        if db.execute('SELECT 1 FROM research_model_owners WHERE protocol=?', (PACKAGE,)).fetchone():
            raise RuntimeError('PACKAGE_PROVIDER_ALREADY_DISPATCHED_NO_AUTOMATIC_RETRY')
        previous = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        previous = previous['value'] if previous else None
        db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps('per-owner'),))
    save(HERE / 'runtime-open.json', dict(at=now(), prior_scope=previous, new_package=PACKAGE,
                                        owners_registered_just_in_time=True))
    try:
        yield
    finally:
        with connect() as db:
            current = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            if not current or current['value'] != json.dumps('per-owner'):
                raise RuntimeError('CONCURRENT_BUDGET_SCOPE_CHANGE')
            if previous is None:
                db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
            else:
                db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'", (previous,))
            owners = [r[0] for r in db.execute('SELECT owner FROM research_model_owners WHERE protocol=?', (PACKAGE,))]
            for owner in owners:
                db.execute('UPDATE grants SET expires=? WHERE owner=?', (time.time(), owner))
                db.execute('DELETE FROM principals WHERE owner=?', (owner,))
                db.execute("UPDATE conversations SET status='IDLE',updated=? WHERE id=?", (time.time(), owner))
            db.execute('UPDATE research_model_studies SET expires=? WHERE protocol=?', (time.time(), PACKAGE))
        save(HERE / 'runtime-closeout.json', dict(at=now(), prior_scope_restored=previous,
             owners=owners, history_rows_deleted=0, old_unknowns_unchanged=True))


class PublicObjects(transport.legacy.PublicObjects):
    """At most 1,800 bytes/page: all 64 read pages fit in later requests."""
    def register(self, value, *, path=None):
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        sha = hashlib.sha256(raw).hexdigest()
        ident = 'pub-' + sha
        if ident not in self.objects:
            target = self.folder / (ident + '.json.gz')
            if not target.exists():
                adapter._write_gzip(target, value)
            self.objects[ident] = dict(path=str(target), sha256=sha, serialized_bytes=len(raw))
            if isinstance(value, dict) and value.get('result_sha256') and 'facts' in value:
                self.results[value['result_sha256']] = ident
        return ident

    def _get(self, ident):
        if ident not in self.objects:
            raise ValueError('UNKNOWN_PUBLIC_OBJECT')
        value = load(self.objects[ident]['path'])
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        if hashlib.sha256(raw).hexdigest() != self.objects[ident]['sha256']:
            raise RuntimeError('PUBLIC_OBJECT_CHANGED')
        return value

    def read(self, arguments):
        ident = arguments.get('object_id', arguments.get('public_object_ref'))
        section, offset = arguments.get('section', ''), arguments.get('offset', 0)
        if type(offset) is not int or offset < 0:
            raise ValueError('NONNEGATIVE_PUBLIC_OFFSET_REQUIRED')
        value = self._section(self._get(ident), section)
        result = dict(version='M3-public-objects-v1', visibility='PUBLIC_ONLY',
            object_id=ident, section=section, offset=offset, next_offset=None)
        if isinstance(value, str):
            end = min(len(value), offset + 240)
            result.update(type='string', total=len(value), text=value[offset:end],
                          next_offset=end if end < len(value) else None)
        elif isinstance(value, (list, dict)):
            keys = list(value) if isinstance(value, dict) else list(range(len(value)))
            result.update(type='dict' if isinstance(value, dict) else 'list', total=len(keys), rows=[])
            index = offset
            while index < min(len(keys), offset + 6):
                key = keys[index]
                escaped = str(key).replace('~', '~0').replace('/', '~1')
                row = {'key' if isinstance(value, dict) else 'index': key, 'value': deepcopy(value[key])}
                if len(p.encoded(row)) > 700:
                    row['value'] = self.reference(ident, section + '/' + escaped, value[key])
                trial = {**result, 'rows': result['rows'] + [row],
                         'next_offset': index + 1 if index + 1 < len(keys) else None}
                if len(p.encoded(trial)) > 1800:
                    break
                result['rows'].append(row)
                index += 1
            if offset < len(keys) and index == offset:
                raise ValueError('PUBLIC_PAGE_CANNOT_MAKE_PROGRESS')
            result['next_offset'] = index if index < len(keys) else None
        else:
            if offset:
                raise ValueError('SCALAR_OFFSET_MUST_BE_ZERO')
            result.update(type='scalar', value=value)
        if len(p.encoded(result)) > 1800:
            raise ValueError('PUBLIC_PAGE_BYTES_CAP')
        return result


class Episode(p.Episode):
    start_server = transport.LCEpisode.start_server

    def __init__(self, ident, family, initial):
        self.ident, self.family, self.initial = ident, family, initial
        self.limits = LIMITS
        self.root = HERE / 'episodes' / ident
        self.root.mkdir(parents=True, exist_ok=False)
        self.started = time.monotonic()
        self.model_calls = self.tools = self.numerical = 0
        self.candidates, self.history, self.pages, self.actions = set(), [], [], []
        self.fatal = self.server = self.thread = None
        self.token, self.access_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.objects = PublicObjects(HERE / 'public-objects')
        self.owner = p.api('/api/conversations', dict(text='Finite relation-synthesis '+ident,
            operation_id=PACKAGE+'-'+ident, defer_dispatch=True))['id']
        deadline = min(time.time() + 900, load(HERE / 'preflight.json')['absolute_deadline_epoch'])
        with connect() as db:
            assert not db.execute('SELECT 1 FROM research_model_owners WHERE owner=?', (self.owner,)).fetchone()
            assert not db.execute('SELECT 1 FROM model_requests WHERE owner=?', (self.owner,)).fetchone()
            db.execute('INSERT INTO principals VALUES(?,?,?)', (hashlib.sha256(self.token.encode()).hexdigest(), self.owner, 'participant'))
            db.execute('INSERT INTO grants VALUES(?,?,?,?)', (self.owner, json.dumps([PACKAGE]), 0, deadline))
            db.execute('INSERT INTO owner_model_caps VALUES(?,?)', (self.owner, 5.))
            db.execute('INSERT INTO settings VALUES(?,?)', ('model_profile:'+self.owner, json.dumps(p.PROFILE)))
            db.execute('INSERT OR IGNORE INTO research_model_studies VALUES(?,?,?,?,?,?)',
                (PACKAGE, time.time(), load(HERE / 'preflight.json')['absolute_deadline_epoch'], 20., 'deepseek-flash',
                 'Direct human completion of three steps, 2026-11-02; immutable two old exceptions only.'))
            db.execute('INSERT INTO research_model_owners VALUES(?,?,?)', (self.owner, PACKAGE, ident))
        accounting_gate(self.owner)
        save(self.root / 'owner.json', dict(owner=self.owner, ident=ident, limits=LIMITS,
             activated_at=now(), expires=deadline, lease_never_reset=True))
        self.start_server()

    def ready(self, paid=False):
        ready()
        require_sources(load(OUT / 'shared/protocol.json'))
        if self.fatal:
            raise RuntimeError(self.fatal)
        b = self.budget()
        accounting_gate(self.owner)
        if b['wall_s'] >= 900 or self.tools > 64:
            raise RuntimeError('EPISODE_WALL_OR_READ_CAP')
        with connect() as db:
            rows = [dict(r) for r in db.execute('SELECT mr.* FROM model_requests mr JOIN research_model_owners ro ON mr.owner=ro.owner WHERE ro.protocol=?', (PACKAGE,))]
        held = sum(r['charged'] if r['status'] == 'SETTLED' else r['reserved'] for r in rows)
        if paid and (b['model_requests'] >= 12 or b['output_tokens'] >= 131072
                     or b['spent_usd'] + .2 > 5. or len(rows) >= 48 or held + .2 > 20.):
            raise RuntimeError('FINITE_PAID_CAP')
        return b

    def paid_callback(self, request):
        result = transport.LCEpisode.paid_callback(self, request)
        folder = self.root / 'callbacks' / f'{self.callback_index:02d}'
        if result.get('provider_status') == 'COMPLETE' and result.get('usage', {}).get('status') == 'KNOWN':
            records = [json.loads(line) for line in (folder/'pi-public.jsonl').read_text().splitlines() if line.strip()]
            answers = [r for r in records if r.get('type') == 'assistant_public']
            if len(answers) == 1:
                raw = ''.join(row['text'] for row in answers[0]['content'])
                parsed = formatter.parse_model_output(raw)
                result['payload'] = parsed['payload'] if parsed['status'] == 'OK' else dict(status='FORMAT_ERROR', error=parsed.get('error'))
                result['normalization'] = dict(status=parsed['status'], format=parsed.get('format'),
                    source=ref(BASE/'codebt-zeroapi/s0/model_format.py'), raw_sha256=hashlib.sha256(raw.encode()).hexdigest())
                save(folder / 'callback-result.json', result)
        return result

    @staticmethod
    def public_result(value):
        if isinstance(value, dict):
            return {k: Episode.public_result(v) for k, v in value.items() if k not in {
                'reused', 'new_full_wall_s', 'canonical_public_path', 'cache_origin', 'provenance'}}
        if isinstance(value, list):
            return [Episode.public_result(v) for v in value]
        return deepcopy(value)

    def query(self, *, nodes, evaluated_slots, last=None):
        while True:
            budget = self.ready(paid=True)
            # Recomputed for EVERY actual request, including paging callbacks.
            context = dict(site='strong_generic_free_joint_design',
                task_family=[p.public_task(t) if not ('area_cm2' in t['initial_design'] or t.get('world_kind') == 'LC-PV') else deepcopy(t) for t in self.family],
                current_nodes=deepcopy(nodes), initial_results=self.public_result(self.initial),
                own_evaluated_results=[self.public_result(v) for v in self.history],
                public_page_history=deepcopy(self.pages), last_feedback=deepcopy(last),
                site_contract=dict(outputs=[{'design':'complete legal design object', 'parent_id':'optional evaluated node id'},
                    {'final_design':'explicit already evaluated full design object'},
                    {'tool_calls':[{'name':'public_object','arguments':{'object_id':'pub-64hex','section':'RFC6901','offset':0}}]}],
                    candidate_slots_excluding_initial=6, public_reads=64,
                    freedom='Any legal whole-design edits or restarts. Every evaluated failed ancestor remains available. Initial observations do not use candidate slots.',
                    semantics='Absent stage is UNKNOWN. Numeric seq is not globally unique. Read pages remain verbatim in public_page_history across all queries. No filesystem, private reference or code execution.'),
                remaining=dict(design_slots=6-evaluated_slots, logical_condition_evaluations=3*(6-evaluated_slots),
                    provider_requests=12-budget['model_requests'], public_reads=64-self.tools,
                    output_tokens=131072-budget['output_tokens'], usd=5.-budget['spent_usd'],
                    wall_s=max(0.,900-budget['wall_s'])))
            request = self.objects.project(context)
            request['PUBLIC_TOOLS'] = [dict(name='public_object', arguments=dict(object_id='pub-...', section='', offset=0))]
            request['public_paging'].update(row_cap=6, byte_cap=1800,
                history='All read pages retained inline, including previous design queries.')
            request['max_output_tokens'] = p.output_allowance(budget['output_tokens'], LIMITS)
            result = self.paid_callback(request)
            if result.get('usage', {}).get('status') != 'KNOWN':
                raise RuntimeError('PROVIDER_USAGE_NOT_SETTLED')
            payload = result['payload']
            calls = payload.get('tool_calls')
            if not calls:
                return payload
            if not isinstance(calls, list) or len(calls) > 64-self.tools:
                return dict(status='READ_QUOTA_REJECTED', error='PUBLIC_READ_CAP', original=payload)
            for call in calls:
                if call.get('name') != 'public_object':
                    return dict(status='TOOL_REJECTED', error='PUBLIC_TOOL_WHITELIST', original=payload)
                self.tools += 1
                try:
                    page = self.objects.read(call.get('arguments', {}))
                except Exception as exc:
                    page = dict(version='M3-public-objects-v1', visibility='PUBLIC_ONLY',
                        error=type(exc).__name__+':'+str(exc), arguments=call.get('arguments'))
                self.pages.append(page)
            save(self.root / 'public-page-history.json', self.pages)

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        p.close_owner(self.owner, self.token)
        save(self.root / 'closeout.json', dict(at=now(), budget=self.budget(),
             fatal=self.fatal, ledger=p.ledger(DB,self.owner), credentials_closed=True,
             preserved_read_pages=len(self.pages)))
