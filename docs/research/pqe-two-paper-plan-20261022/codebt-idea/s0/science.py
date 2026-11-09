"""Run the already frozen new-idea finite comparison through real accounted Pi."""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import time

import run as host
from run import APP, BASE, DB, HERE, OUT, PACKAGE, ROOT, digest, save

RUNTIME = DB.parents[2]
profile = json.loads((RUNTIME/'profile.json').read_text())
os.environ.update(BF_RUNTIME_ROOT=str(RUNTIME), BF_RUNTIME_CONFIG=str(RUNTIME/'runtime.json'),
    BF_HOME=profile['home'], BF_PI_ROOT=profile['pi_root'],
    BF_DEVELOPMENT_PROFILE=str(RUNTIME/'profile.json'),
    PI_CODING_AGENT_DIR=str(Path(profile['home'])/'pi-config'), PYTHONDONTWRITEBYTECODE='1')
spec = importlib.util.spec_from_file_location('codebt_existing_accounted_transport', BASE/'lc-service-learning/s0/runtime.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
p = transport.p
from bfworld.agentlab import historical_usage
from bfworld.agentlab.pqe20261024debt import adapter, facts, task
from bfworld.agentlab.pqe20261024debt.baselines import GenericJointAgent, MixedJointSearch
from bfworld.agentlab.pqe20261024debt.search import DebtSearch, family_result
from bfworld.agentlab.pqe20261024debt.obligations import derive_obligations

LIMITS = dict(model_requests=12, tool_calls=24, numerical_inputs=18, candidates=6,
    wall_s=900, output_tokens=32768, generated_tokens=131072, usd=5, bytes=40000000)
PROTOCOL = OUT/'shared/protocol.json'
p.OUT, p.PACKAGE, p.LIMITS, p.APP = OUT, PACKAGE, LIMITS, APP
p.CELLS = [('generic_agent',), ('debt_agent',)]
p.TOTAL_CAPS = dict(requests=24, tool_calls=48, numerical_inputs=63, usd=10, retained_bytes=100000000)
p.validate_wire = transport.legacy.validate_wire
p.callback_payload = transport.legacy.callback_payload


def now():
    return datetime.now(timezone.utc).isoformat()


def ref(path):
    raw = Path(path).read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def capacity():
    fs = os.statvfs(ROOT)
    available = fs.f_bavail*fs.f_frsize
    allocated = sum(x.stat().st_blocks*512 for x in OUT.rglob('*') if x.is_file())
    if available < 11000000000 or allocated >= 100000000:
        raise RuntimeError('CODEBT_STORAGE_CAP')
    return dict(at=now(), available_bytes=available, retained_allocated_upper_bound_bytes=allocated,
        peak_cap_bytes=1000000000, retained_cap_bytes=100000000, reclaimed_bytes=0,
        new_backups_environments_worktrees=0)


def journal(name, value):
    with (HERE/name).open('a') as stream:
        stream.write(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')


class PublicObjects(transport.legacy.PublicObjects):
    """Same factual paging policy, canonical gzip objects instead of full copies."""
    def register(self, value, *, path=None):
        identifier = 'pub-'+transport.legacy.digest(value) if hasattr(transport.legacy,'digest') else None
        # The original public-object identity is based on compact UTF-8 bytes.
        encoded = json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        sha = hashlib.sha256(encoded).hexdigest()
        identifier = 'pub-'+sha
        if identifier not in self.objects:
            target = Path(path) if path else self.folder/(identifier+'.json.gz')
            if path is None and not target.exists():
                adapter._write_gzip(target,value)
            self.objects[identifier] = dict(path=str(target),sha256=sha,serialized_bytes=len(encoded))
            if isinstance(value,dict) and value.get('result_sha256') and 'facts' in value:
                self.results[value['result_sha256']] = identifier
        return identifier

    def _get(self, identifier):
        item = self.objects[identifier]
        path = Path(item['path'])
        if path.suffix == '.gz':
            with gzip.open(path,'rt') as stream:
                value = json.load(stream)
        else:
            value = json.loads(path.read_text())
        encoded = json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        if hashlib.sha256(encoded).hexdigest() != item['sha256']:
            raise RuntimeError('PUBLIC_OBJECT_HASH_CHANGED')
        return value


class ScienceEpisode(p.Episode):
    start_server = transport.LCEpisode.start_server
    paid_callback = transport.LCEpisode.paid_callback

    def __init__(self, ident, credentials, protocol, family, common_results):
        self.ident, self.owner, self.token = ident, credentials['owner'], credentials['token']
        self.limits, self.protocol, self.condition = LIMITS, protocol, ident
        self.root = HERE/'episodes'/ident
        self.root.mkdir(parents=True,exist_ok=False)
        self.started = time.monotonic()
        self.model_calls = self.tools = self.numerical = 0
        self.candidates, self.actions = set(), []
        self.fatal, self.server, self.thread = None,None,None
        self.access_token = secrets.token_urlsafe(32)
        self.objects = PublicObjects(self.root/'public-objects')
        self.common_results = common_results
        self.family = family
        self.public_history = []
        with p.dbconnect() as db:
            grant = db.execute('SELECT * FROM grants WHERE owner=?',(self.owner,)).fetchone()
            assert grant and grant['expires'] <= time.time()
            assert not db.execute('SELECT 1 FROM model_requests WHERE owner=?',(self.owner,)).fetchone()
            db.execute('UPDATE grants SET expires=? WHERE owner=?',(time.time()+900,self.owner))
        save(self.root/'owner.json',dict(owner=self.owner,episode=ident,finite_usd=5,
            wall_s=900,requests=12,tools=24,output_tokens=131072,activated_at=now()))
        self.start_server()

    def ready(self, paid=False):
        host.require_scientific_admission()
        capacity()
        if self.fatal:
            raise RuntimeError(self.fatal)
        b = self.budget()
        if b['wall_s'] >= 900 or self.tools > 24 or b['output_tokens'] > 131072:
            raise RuntimeError('FINITE_EPISODE_CAP')
        with p.dbconnect() as db:
            if historical_usage.new_batch_usage_blockers(db,self.owner):
                self.fatal = 'NEW_USAGE_UNKNOWN_STOP'
                raise RuntimeError(self.fatal)
            rows = [dict(r) for r in db.execute('SELECT mr.* FROM model_requests mr JOIN research_model_owners ro ON mr.owner=ro.owner WHERE ro.protocol=?',(PACKAGE,))]
            held = sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows)
        if paid and (b['model_requests']>=12 or b['output_tokens']>=131072 or b['spent_usd']+.2>=5
                     or len(rows)>=24 or held+.2>=10 or self.tools>=24):
            raise RuntimeError('FINITE_PAID_CAP')
        return b

    def budget_view(self):
        b = self.ready()
        return dict(requests_used=b['model_requests'],output_tokens_used=b['output_tokens'],
            spent_usd=b['spent_usd'], remaining_wall_s=900-b['wall_s'],tool_calls_used=self.tools,
            provider_requests_remaining=12-b['model_requests'],tool_calls_remaining=24-self.tools)

    def settled(self, response):
        ids = response.get('request_ids',[])
        if not ids or len(ids)!=len(set(ids)):
            return False
        with p.dbconnect() as db:
            rows = [db.execute('SELECT * FROM model_requests WHERE id=? AND owner=?',(ident,self.owner)).fetchone() for ident in ids]
        if not all(r and r['status']=='SETTLED' and r['usage'] for r in rows):
            return False
        usage = response['usage']
        return (usage.get('model_identity')==p.MODEL_IDENTITY and
            usage.get('input_tokens')==sum(json.loads(r['usage'])['prompt_tokens'] for r in rows) and
            usage.get('output_tokens')==sum(json.loads(r['usage'])['completion_tokens'] for r in rows) and
            abs(usage.get('cost',-1)-sum(r['charged'] for r in rows))<1e-10)

    def callback(self, request):
        # Only this group's own history and common initials are made visible.
        context = deepcopy(request)
        context['common_public_context'] = dict(
            conditions=[{**p.public_task(t),'condition_id':t['condition_id']} for t in self.family],
            initial_results=self.common_results, own_evaluated_results=self.public_history,
            certificate=None, certificate_scope='UNKNOWN; no physical exclusion certificate',
            manual_prior='Cross-reset sequence safety includes the same public conservative identity-storage prior in every group.')
        total = dict(status='KNOWN',model_identity=p.MODEL_IDENTITY,input_tokens=0,output_tokens=0,cost=0.)
        ids = []
        cap = request['max_output_tokens']
        while True:
            self.ready(paid=True)
            body = self.objects.project(context)
            body['max_output_tokens'] = min(cap-total['output_tokens'],p.output_allowance(self.budget()['output_tokens'],LIMITS))
            if body['max_output_tokens']<=0:
                raise RuntimeError('PLANNER_OUTPUT_CAP')
            body['PUBLIC_TOOLS'] = [dict(name='public_object',arguments={'object_id':'pub-...','section':'RFC6901 pointer','offset':0})]
            body['public_tool_instruction'] = 'To read any public reference return {tool_calls:[{name:"public_object",arguments:{object_id,section,offset}}]}; otherwise use the controller site JSON candidate/STOPPED contract. Each page consumes one shared tool call; continuations consume real request/output/wall/cost budget.'
            response = self.paid_callback(body)
            if response.get('usage',{}).get('status')!='KNOWN':
                return response
            for key in ('input_tokens','output_tokens','cost'):
                total[key] += response['usage'][key]
            ids.extend(response['request_ids'])
            calls = response['payload'].get('tool_calls')
            if not calls:
                return {**response,'usage':total,'request_ids':ids}
            if not isinstance(calls,list) or len(calls)>24-self.tools:
                raise RuntimeError('PUBLIC_TOOL_CAP')
            pages = []
            for call in calls:
                self.tools += 1
                if call.get('name')!='public_object':
                    pages.append(dict(error='ONLY_PUBLIC_OBJECT_AVAILABLE'))
                else:
                    try:
                        pages.append(self.objects.read(call.get('arguments',{})))
                    except Exception as exc:
                        pages.append(dict(error=type(exc).__name__+':'+str(exc)))
            context['last_public_tool_results'] = pages

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        p.close_owner(self.owner,self.token)
        save(self.root/'closeout.json',dict(at=now(),budget=self.budget(),fatal=self.fatal,
            authoritative_ledger=p.ledger(DB,self.owner),grant_closed=True))


def main():
    if (HERE/'science-start.json').exists():
        raise RuntimeError('SCIENCE_PACKAGE_ALREADY_ATTEMPTED_NO_AUTOMATIC_RERUN')
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol['sources']==adapter.source_identity()
    for path,sha in protocol['method_sources'].items():
        assert ref(ROOT/path)['sha256']==sha, path
    family_bytes = Path(protocol['family_ref']['path']).read_bytes()
    assert hashlib.sha256(family_bytes).hexdigest()==protocol['family_ref']['sha256']
    family = json.loads(family_bytes)['conditions']
    contract = json.loads(Path(protocol['contract_ref']['path']).read_text())
    initial = deepcopy(family[0]['initial_design'])
    assert all(t['initial_design']==initial for t in family)
    admission = json.loads((HERE/'science-admission.json').read_text())
    assert admission['status']=='EXACT_POLICY_ACTIVE_SCIENCE_PROVIDER_BINDING_NEXT'
    save(HERE/'science-start.json',dict(at=now(),package=PACKAGE,preflight=capacity(),
        group_order=protocol['group_order'],original_authority=admission['authority'],
        provider_requests=0,new_full_inputs=0))
    credentials = {}
    episode = None
    with p.dbconnect() as db:
        assert not db.execute('SELECT 1 FROM research_model_owners WHERE protocol=?',(PACKAGE,)).fetchone()
        previous = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        previous = previous['value'] if previous else None
        db.execute("INSERT INTO settings VALUES('model_budget_scope',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps('per-owner'),))
    save(HERE/'runtime-open.json',dict(at=now(),prior_scope=previous,study_usd=10,owners_max=2))
    ledger = dict(package=PACKAGE,new_full_inputs=0,full_wall_s=0.,members=[],groups={},
        cheap_numerical_inputs=0,mechanism_scheduled=0,errors=[])
    journal_path = HERE/'scientific-members.jsonl'
    evaluated = []
    cache_paths = {}
    broker = None
    try:
        for ident in ('generic_agent','debt_agent'):
            owner,token = p.register_owner(ident)
            credentials[ident] = dict(owner=owner,token=token)
            with p.dbconnect() as db:
                assert historical_usage.new_batch_usage_blockers(db,owner)==[]
                db.execute('UPDATE grants SET expires=? WHERE owner=?',(time.time(),owner))
        protocol.update(status='FROZEN_FOR_NEW_SCIENCE',science_admitted_at=now(),
            actual_provider_binding=dict(model_identity=p.MODEL_IDENTITY,profile=p.PROFILE,sdk=ref(p.SDK),
                callback_script=ref(APP/'scripts/pqe_pi_callback.mjs'),
                owners={k:v['owner'] for k,v in credentials.items()},
                owner_cap_usd=5,study_cap_usd=10,requests_per_owner=12,
                ledger_verifier='ScienceEpisode.settled checks actual immutable SETTLED/usage/owner/request IDs/tokens/charges',
                prior_UNKNOWN_reserved=0.3686529),
            host_sources={str(path.relative_to(ROOT)):ref(path)['sha256'] for path in
                (HERE/'run.py',HERE/'science.py',HERE/'admit.py',Path(historical_usage.__file__),
                 BASE/'lc-service-learning/s0/runtime.py',BASE/'f1-conditional-learning/s0/run_learning.py',
                 BASE/'service-repair-m3/s0/public_projection.py')})
        save(PROTOCOL,protocol)
        state = json.loads((BASE/'execution-state.json').read_text())
        state.update(status='RUNNING_FROZEN_NEW_IDEA_SCIENCE',next_action='Execute frozen initials, three groups and rule-selected neighbors; old packages and cleanup paused.')
        state['execution_gate'] = dict(status='ADMITTED_NEW_IDEA',amendment=admission['authority']['id'],
            request_id=admission['authority']['request_id'],preserve_original_unknown_null_usage_reserve=True,
            new_missing_usage_stops=True,provider_binding=protocol['actual_provider_binding'])
        save(BASE/'execution-state.json',state)
        save(HERE/'science-protocol-binding.json',dict(at=now(),protocol_ref=ref(PROTOCOL),gate=host.accounting_gate()))
        current = {'group':'initial','ordinal':0}

        def member(t,design,action):
            assert ledger['new_full_inputs']<63 and ledger['full_wall_s']+120<=7560
            host.require_scientific_admission()
            ordinal = ledger['new_full_inputs']+1
            folder = HERE/'science'/f'{ordinal:02d}-{current["group"]}-{t["condition_id"]}'
            ledger['new_full_inputs'] += 1
            save(HERE/'science-resource-ledger.json',ledger)
            start = time.monotonic()
            row = dict(index=ordinal,group=current['group'],candidate_ordinal=current['ordinal'],
                task_id=t['task_id'],condition_id=t['condition_id'],design_sha256=digest(design),
                action_sha256=digest(action),folder=str(folder),status='CLAIMED',started_at=now())
            journal('scientific-claims.jsonl',row)
            try:
                public = host.scientific_member(t,design,action,folder)
                path = folder/'result/public-result.json.gz'
                key = digest(dict(task=t,design=design,sources=protocol['sources']))
                cache_paths[key] = str(path)
                row.update(status='COMPLETE',public_result=ref(path),result_sha256=public['result_sha256'],
                    model_valid=public['model_valid'],public_check=public['public_check'])
            except Exception as exc:
                row.update(status='ERROR',error=type(exc).__name__+':'+str(exc))
                ledger['errors'].append(row['error'])
                raise
            finally:
                elapsed = time.monotonic()-start
                row['wall_s'] = elapsed
                ledger['full_wall_s'] += elapsed
                ledger['members'].append(row)
                journal('scientific-members.jsonl',row)
                save(HERE/'science-resource-ledger.json',ledger)
                print(json.dumps({k:row[k] for k in ('index','group','condition_id','status','wall_s')}
                    |dict(verdict=row.get('public_check',{}).get('verdict'))),flush=True)
            return public

        broker = host.FamilyBroker(family,member,sources=protocol['sources'])
        initial_action = dict(status='ACTION',request_id='common-initial',node_id='initial',design=initial,
            base_design=initial,conditions=protocol['conditions'],decision=dict(actual_input=dict(operation='verify',design_patch={})))
        initial_result = broker.evaluate('common_initial',initial_action)
        initial_summary = family_result(initial_result,initial,protocol['conditions'])
        save(HERE/'initial-results.json',dict(at=now(),design=initial,service=initial_summary,
            canonical_results=[r['public_result'] for r in ledger['members']]))
        print(json.dumps(dict(event='REAL_INITIALS_COMPLETE',new_full_inputs=ledger['new_full_inputs'],service=initial_summary)),flush=True)
        common_results = []
        for t in family:
            key = digest(dict(task=t,design=initial,sources=protocol['sources']))
            common_results.append((broker.cache[key],cache_paths[key]))
        scope = dict(family_id=family[0]['family_id'],conditions=protocol['conditions'],
            task_sha256=[digest(t) for t in family],model_identity=p.MODEL_IDENTITY,
            fixed_service=True,certificate=None)
        facts_fn = lambda d:facts.design_facts(d,family[0])
        common = dict(scope=scope,initial_result=initial_result,
            active_variables=family[0]['initial_problem']['active_variables'],
            validate_fn=lambda d:task.validate_design(family[0],d))
        for group in protocol['group_order']:
            current['group'],current['ordinal'] = group,0
            start = time.monotonic()
            episode = None
            group_errors = []
            if group!='mixed_joint':
                episode = ScienceEpisode(group,credentials[group],protocol,family,[])
                for public,path in common_results:
                    episode.objects.register(public,path=path)
                    episode.common_results.append(public)
                planner = host.FinitePlanner(episode.callback,episode.budget_view,
                    model_identity=p.MODEL_IDENTITY,settlement_check=episode.settled)
                controller = (GenericJointAgent(initial,contract,planner,facts_fn=facts_fn,
                    model_identity=p.MODEL_IDENTITY,max_evaluated_designs=6,**common)
                    if group=='generic_agent' else DebtSearch(initial,contract,facts_fn,planner,
                    model_identity=p.MODEL_IDENTITY,seed=20261024,**common))
            else:
                controller = MixedJointSearch(initial,contract,seed=20261024,max_evaluated_designs=6,**common)
            try:
                while True:
                    host.require_scientific_admission()
                    b = episode.budget_view() if episode else dict(provider_requests_remaining=0,tool_calls_remaining=24-current['ordinal'])
                    action = controller.step(b)
                    if action.get('status')!='ACTION':
                        journal('participant-journal.jsonl',dict(group=group,event='STOP',response=action))
                        break
                    current['ordinal'] += 1
                    if episode:
                        episode.tools += 1
                        episode.candidates.add(digest(action['design']))
                        episode.ready()
                    journal('participant-journal.jsonl',dict(group=group,event='ACTION',ordinal=current['ordinal'],action=action))
                    before_full = ledger['new_full_inputs']
                    result = broker.evaluate(group,action)
                    service = family_result(result,action['design'],protocol['conditions'])
                    update = controller.update(result)
                    item = dict(group=group,ordinal=current['ordinal'],action=action,service=service,
                        update=update,new_full_inputs=ledger['new_full_inputs']-before_full,
                        cumulative_package_full_inputs=ledger['new_full_inputs'])
                    evaluated.append(item)
                    journal('participant-journal.jsonl',dict(event='RESULT',**item))
                    if episode:
                        episode.numerical += item['new_full_inputs']
                        for t in family:
                            key = digest(dict(task=t,design=action['design'],sources=protocol['sources']))
                            public = broker.cache[key]
                            episode.objects.register(public,path=cache_paths[key])
                            episode.public_history.append(public)
                    print(json.dumps(dict(event='REAL_GROUP_CANDIDATE',group=group,ordinal=current['ordinal'],
                        statuses=service['statuses'],all_pass=service['all_pass'],new_full_inputs=item['new_full_inputs'])),flush=True)
            except Exception as exc:
                group_errors.append(type(exc).__name__+':'+str(exc))
                journal('participant-journal.jsonl',dict(group=group,event='GROUP_ERROR',errors=group_errors))
                if host.accounting_gate()['status']!='ADMITTED':
                    raise
            finally:
                folder = HERE/'groups'/group
                adapter._write_gzip(folder/'snapshot.json.gz' if folder.exists() else _mkdir_file(folder,'snapshot.json.gz'),controller.snapshot())
                rows = [e for e in evaluated if e['group']==group]
                summary = dict(group=group,candidates=len(rows),results=rows,termination=controller.termination,
                    errors=group_errors,wall_s=time.monotonic()-start,
                    ledger=p.ledger(DB,episode.owner) if episode else None,
                    initial_service=initial_summary,first_all_pass_candidate=next((e['ordinal'] for e in rows if e['service']['all_pass']),None))
                save(folder/'summary.json',summary)
                ledger['groups'][group] = {k:v for k,v in summary.items() if k not in ('results','ledger')}
                save(HERE/'science-resource-ledger.json',ledger)
                if episode:
                    episode.close()
                    episode=None
        # Fixed causal-neighbor rule; neither selection nor field order uses service.
        chosen = None
        fields = []
        for e in evaluated:
            design = e['action']['design']
            dependencies = set(k for f in facts_fn(design)['facts'] if f['kind'] in {'production','consumption','handoff','reset'} for k in f['depends_on'])
            changed = sorted(k for k in design if design[k]!=initial[k] and k in dependencies)
            if len(changed)>=2:
                chosen = e
                fields = [k for k in changed if contract['design_domain'][k]['kind'] in {'enum','boolean'}][:3]
                break
        selection = dict(at=now(),rule_ref=protocol['mechanism_rule_ref'],candidate=chosen,fields=fields,
            selection_uses_service=False,scheduled_inputs=2*len(fields))
        save(HERE/'mechanism-selection.json',selection)
        if chosen:
            for field in fields:
                design = deepcopy(chosen['action']['design'])
                design[field] = deepcopy(initial[field])
                for t in family[:2]:
                    ledger['mechanism_scheduled'] += 1
                    current.update(group='mechanism-'+field,ordinal=ledger['mechanism_scheduled'])
                    try:
                        task.validate_design(t,design)
                    except ValueError as exc:
                        journal('mechanism-journal.jsonl',dict(field=field,condition=t['condition_id'],status='INVALID_NO_REPLACEMENT',error=str(exc)))
                        continue
                    action = dict(status='ACTION',request_id='mechanism-'+field+'-'+t['condition_id'],design=design,
                        base_design=chosen['action']['design'],decision=dict(actual_input=dict(operation='edit',design_patch={field:design[field]})))
                    key = digest(dict(task=t,design=design,sources=protocol['sources']))
                    reused = key in broker.cache
                    if reused:
                        public = broker.cache[key]
                    else:
                        assert broker.full_inputs<63
                        broker.full_inputs += 1
                        public = member(t,design,action)
                        broker.cache[key]=public
                    journal('mechanism-journal.jsonl',dict(field=field,condition=t['condition_id'],reused=reused,
                        verdict=public['public_check'],result_sha256=public['result_sha256'],design=design))
        ledger['status']='FINITE_SCIENCE_LIST_CLOSED'
    except Exception as exc:
        ledger['status']='STOPPED_WITH_ORIGINAL_FAILURE_NO_RETRY'
        ledger['errors'].append(type(exc).__name__+':'+str(exc))
        print(json.dumps(dict(event='SCIENCE_STOP',error=ledger['errors'][-1])),flush=True)
    finally:
        if episode:
            episode.close()
        with p.dbconnect() as db:
            for ident,cred in credentials.items():
                db.execute('UPDATE grants SET expires=? WHERE owner=?',(time.time(),cred['owner']))
                db.execute('DELETE FROM principals WHERE owner=?',(cred['owner'],))
                db.execute("UPDATE conversations SET status='IDLE',updated=? WHERE id=?",(time.time(),cred['owner']))
            db.execute('UPDATE research_model_studies SET expires=? WHERE protocol=?',(time.time(),PACKAGE))
            current_scope=db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
            assert current_scope and current_scope['value']==json.dumps('per-owner')
            if previous is None:
                db.execute("DELETE FROM settings WHERE key='model_budget_scope'")
            else:
                db.execute("UPDATE settings SET value=? WHERE key='model_budget_scope'",(previous,))
            costs = {ident:p.ledger(DB,cred['owner']) for ident,cred in credentials.items()}
            missing = [dict(r) for r in db.execute("SELECT mr.* FROM model_requests mr JOIN research_model_owners ro ON mr.owner=ro.owner WHERE ro.protocol=? AND (mr.status!='SETTLED' OR mr.usage IS NULL)",(PACKAGE,))]
        ledger['provider'] = dict(owners={k:v['owner'] for k,v in credentials.items()},ledger=costs,
            requests=sum(v['requests'] for v in costs.values()),
            settled_estimate_usd=sum(v['settled_charge_upper_bound_usd'] for v in costs.values()),
            unsettled_reserved_usd=sum(v['unsettled_reserved_usd'] for v in costs.values()),missing_usage=missing)
        ledger['postflight']=capacity()
        save(HERE/'science-resource-ledger.json',ledger)
        save(HERE/'runtime-closeout.json',dict(at=now(),scope_restored=previous,new_owner_authorizations_closed=True,
            old_billing_rows_unchanged=True,new_missing_usage=missing,retries=0))
        print(json.dumps(dict(event='FINITE_SCIENCE_CLOSED',status=ledger['status'],new_full_inputs=ledger['new_full_inputs'],
            provider_requests=ledger['provider']['requests'],usd=ledger['provider']['settled_estimate_usd'],errors=ledger['errors'])),flush=True)


def _mkdir_file(folder,name):
    folder.mkdir(parents=True,exist_ok=False)
    return folder/name


if __name__=='__main__':
    main()
