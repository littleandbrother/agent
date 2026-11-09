"""Same actual backend for G/G+J/G+J+C, with separate read/action budgets."""
from contextlib import contextmanager
from common import *

base=module(OLD/'s0/provider.py','joint_pinned_provider_transport')
p=base.p
LIMITS=dict(model_requests=12,tool_calls=64,numerical_inputs=18,candidates=6,
    wall_s=900,output_tokens=32768,generated_tokens=131072,usd=5.,bytes=35_000_000)
base.LIMITS=LIMITS
p.OUT,p.PACKAGE,p.LIMITS,p.APP=OUT,PACKAGE,LIMITS,APP
p.TOTAL_CAPS=dict(requests=144,tool_calls=768,numerical_inputs=240,usd=60.,retained_bytes=200_000_000)
assert Path(p.DATABASE)==DB
PublicObjects=base.PublicObjects
finite_service=base.finite_service


@contextmanager
def runtime_scope():
    with base.runtime_scope():
        with connect() as db:
            db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',
                (PACKAGE,time.time(),load(HERE/'preflight.json')['absolute_deadline_epoch'],60.,'deepseek-flash',
                 'Verified direct human 开始执行吧, 2026-11-02, one finite same-backend joint/closure package; exact original liabilities only.'))
        yield


class Episode(base.Episode):
    def __init__(self,ident,family,initial,*,condition,tools,shared_history,initial_facts):
        self.condition,self.host_tools=condition,tools
        self.shared_history,self.initial_facts=shared_history,initial_facts
        self.nonreads=0;self.tool_history=[]
        super().__init__(ident,family,initial)

    def budget(self):
        result=super().budget();result['nonread_actions']=self.nonreads
        return result

    def ready(self,paid=False):
        ready();require_sources(load(OUT/'shared/protocol.json'))
        if self.fatal:raise RuntimeError(self.fatal)
        b=self.budget();accounting_gate(self.owner)
        if b['wall_s']>=900 or self.tools>64 or self.nonreads>24:raise RuntimeError('EPISODE_WALL_OR_TOOL_CAP')
        with connect() as db:
            rows=[dict(r) for r in db.execute('SELECT mr.* FROM model_requests mr JOIN research_model_owners ro ON mr.owner=ro.owner WHERE ro.protocol=?',(PACKAGE,))]
        held=sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows)
        if paid and (b['model_requests']>=12 or b['output_tokens']>=131072 or b['spent_usd']+.2>5. or len(rows)>=144 or held+.2>60.):
            raise RuntimeError('FINITE_PAID_CAP')
        return b

    def paid_callback(self,request):
        result=super().paid_callback(request)
        folder=self.root/'callbacks'/f'{self.callback_index:02d}'
        # The transport has fully terminated this SDK process. Preserve exact
        # original bytes in one canonical compressed file per large/raw output.
        compacted=[]
        for f in sorted(folder.rglob('*')):
            if not f.is_file() or f.suffix=='.gz' or f.name in {'callback-result.json','compression.json'}:continue
            if f.stat().st_size>=4096 or f.name in {'input-public.json','wire-public.json','pi-public.jsonl'}:
                compacted.append(compact_file(f))
        save(folder/'compression.json',dict(at=now(),files=compacted,full_byte_readback=True,new_backups=0))
        return result

    def query(self,*,nodes,evaluated_slots,last=None,method_bundle=None):
        while True:
            b=self.ready(paid=True)
            context=dict(site='same_backend_free_joint_scientific_design',condition=self.condition,
                task_family=[p.public_task(t) if 'area_cm2' not in t['initial_design'] else deepcopy(t) for t in self.family],
                current_nodes=deepcopy(nodes),initial_results=self.public_result(self.initial),
                common_initial_candidate_facts=self.initial_facts,common_development_history=self.shared_history,
                common_design_history=[{k:r[k] for k in ('family','design','statuses','public_check')}
                    for r in self.shared_history['rows']],
                own_evaluated_results=[self.public_result(v) for v in self.history],
                public_page_history=deepcopy(self.pages),tool_history=deepcopy(self.tool_history),
                method_layer=dict(identity='Optional developer proposal strategy; never a scientific verdict.',
                    enabled=self.condition!='G',recursive=self.condition=='G+J+C',proposals=method_bundle),
                offered_candidates=[dict(candidate_id=c['id'],parent_id=c['parent_id'],origin=c['origin'],
                    design=c['design'],full_service=c['full_service'],model_may_refuse_or_modify=True)
                    for c in (method_bundle or {}).get('candidates',[])],
                last_feedback=last,
                site_contract=dict(outputs=[{'design':'complete legal design','parent_id':'optional evaluated parent id'},
                    {'candidate_id':'optional offered method candidate id'}, {'final_design':'already evaluated complete design'},
                    {'tool_calls':[{'name':'public_object | candidate_facts | calculate','arguments':{}}]}],
                    shared_tools='Every condition has all original facts/contracts/formulas/calculators and free legal whole-design edits. Method proposals may be rejected, modified or ignored.',
                    same_stop='Stop after first one whole design passes all three original service conditions.',
                    read_pages='Retained verbatim across requests; reads never consume a design slot.',
                    unknown='No absent stage is a proven cause. Static/conditional calculations do not prove full service.',
                    repeated_identifiers='314159/271828 identify repetitions/controller state, not a supported model seed.'),
                remaining=dict(design_slots=6-evaluated_slots,logical_condition_evaluations=3*(6-evaluated_slots),
                    provider_requests=12-b['model_requests'],public_reads=64-self.tools,nonread_actions=24-self.nonreads,
                    output_tokens=131072-b['output_tokens'],usd=5.-b['spent_usd'],wall_s=max(0.,900-b['wall_s'])))
            request=self.objects.project(context)
            request['PUBLIC_TOOLS']=[dict(name='public_object',arguments=dict(object_id='pub-...',section='',offset=0)),
                dict(name='candidate_facts',arguments=dict(design='complete legal design')),
                dict(name='calculate',arguments=dict(design='complete legal design',operation='all'))]
            request['public_paging'].update(row_cap=6,byte_cap=1800,history='Every already-read page remains inline.')
            request['max_output_tokens']=p.output_allowance(b['output_tokens'],LIMITS)
            response=self.paid_callback(request)
            if response.get('usage',{}).get('status')!='KNOWN':raise RuntimeError('NEW_USAGE_NOT_KNOWN')
            payload=response['payload'];calls=payload.get('tool_calls')
            if not calls:
                if self.nonreads>=24:raise RuntimeError('NONREAD_ACTION_CAP')
                self.nonreads+=1
                return payload
            if not isinstance(calls,list) or not calls:
                return dict(status='TOOL_FORMAT_REJECTED',original=payload)
            for call in calls:
                name=call.get('name');args=call.get('arguments',{})
                if name=='public_object':
                    if self.tools>=64:raise RuntimeError('PUBLIC_READ_CAP')
                    self.tools+=1
                    try:answer=self.objects.read(args)
                    except (ValueError,KeyError,TypeError) as exc:answer=dict(status='PUBLIC_READ_REJECTED',error=type(exc).__name__+':'+str(exc),arguments=args)
                    self.pages.append(answer)
                elif name in {'candidate_facts','calculate'}:
                    if self.nonreads>=24:raise RuntimeError('NONREAD_ACTION_CAP')
                    self.nonreads+=1
                    try:answer=self.host_tools(name,args)
                    except (ValueError,KeyError,TypeError) as exc:answer=dict(status='PUBLIC_CALCULATION_REJECTED',error=type(exc).__name__+':'+str(exc),arguments=args)
                    # A root reference remains readable; only bounded answers
                    # are inlined. This is identical for all three conditions.
                    public=self.objects.project(dict(answer=answer))
                    self.tool_history.append(dict(name=name,arguments=args,answer=public.get('answer',public)))
                else:
                    if self.nonreads>=24:raise RuntimeError('NONREAD_ACTION_CAP')
                    self.nonreads+=1
                    self.tool_history.append(dict(name=name,status='TOOL_NOT_AVAILABLE'))
            save(self.root/'public-page-history.json.gz',self.pages)
            save(self.root/'tool-history.json.gz',self.tool_history)
