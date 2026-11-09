"""Thin new accounting/execution adapter around the unchanged original consumers."""
import signal
from common import *

prior=module(OLD/'s0/apparatus.py','joint_original_consumer_adapter')
door,lc_adapter,door_task,bridge=prior.door,prior.lc_adapter,prior.door_task,prior.bridge
is_lc,condition_id,action_for,public_copy=prior.is_lc,prior.condition_id,prior.action_for,prior.public_copy


class Apparatus(prior.Apparatus):
    def __init__(self,*,resume=False):
        super().__init__(resume=resume)
        self.ledger['external_stage1']=dict(full_attempts=0,full_wall_s=0.)
        self.ledger.setdefault('numeric_calls',[])
        self.ledger.setdefault('numeric_cache_hits',0)
        self.ledger.setdefault('meter_events',{})
        self.persist()

    def meter(self,kind,key,details=None):
        events=self.ledger['meter_events'];events[kind]=events.get(kind,0)+1
        if kind in {'cache_hit','structural','fact_read','memo_hit','geometry_hit','geometry_announced_miss'}:
            self.ledger['numeric_cache_hits']+=1
        elif kind in {'cheap_numeric','geometry_miss'}:
            if self.ledger['cheap_numeric']>=72:raise RuntimeError('S0_CHEAP_CAP')
            self.ledger['cheap_numeric']+=1
            self.ledger['numeric_calls'].append(dict(at=now(),kind=kind,key=key,details=details))
        else:raise RuntimeError('UNREGISTERED_METER_KIND:'+kind)
        self.persist()

    def fact_meter(self,kind,key,details=None):
        # A announces a geometry miss immediately before calling the same
        # original cache function hooked below. Charge its actual execution
        # once in static_geometry, rather than charging both announcements.
        return self.meter('geometry_announced_miss' if kind=='geometry_miss' else kind,key,details)

    def static_geometry(self,mechanism):
        from bfworld.agentlab.pqe20261022 import door_model
        f=door_model.source_step
        key=(f,getattr(f,'__code__',None),json.dumps(dict(mechanism=mechanism,
            defaults=door_model.DEFAULT_MECHANISM,domain=door_model.DOMAIN),sort_keys=True,separators=(',',':'),allow_nan=False))
        if key in door_task._STATIC_GEOMETRY_CACHE:self.ledger['static_hits']+=1
        else:self.meter('geometry_miss',digest(dict(mechanism=mechanism)))
        try:return self.original_static(mechanism)
        finally:self.persist()

    def ready(self):
        ready()
        frozen=OUT/'shared/protocol.json'
        if frozen.exists():
            p=load(frozen);require_sources(p)
            assert p['consumer_sources']==dict(DOOR=door.source_identity(),LC=lc_adapter.source_identity())
        if self.ledger['full_attempts']>=240 or self.ledger['full_wall_s']>=4800:
            raise RuntimeError('GLOBAL_FULL_RESOURCE_CAP')

    def member(self,task,design,*,group,slot,phase,context=None):
        self.ready()
        cap=dict(development=24,comparison=216)[phase]
        prior_log=[json.loads(x) for x in (HERE/'logical-inputs.jsonl').read_text().splitlines()] if (HERE/'logical-inputs.jsonl').exists() else []
        if sum(x['phase']==phase for x in prior_log)>=cap:raise RuntimeError('LOGICAL_PHASE_CAP:'+phase)
        self.ledger['logical_inputs']+=1
        key=self.key(task,design,context)
        if key in self.cache:
            source=self.cache[key];value=load(source['path'])
            self.ledger['cache_reuses']+=1
            journal(HERE/'logical-inputs.jsonl',dict(group=group,slot=slot,phase=phase,
                condition_id=condition_id(task),cache_key=key,reused=True,source=ref(source['path']),new_full_wall_s=0.))
            self.persist()
            value.update(condition_id=condition_id(task),reused=True,new_full_wall_s=0.,
                         canonical_public_path=source['path'],cache_origin=source['origin'])
            return public_copy(value,task)
        index=self.ledger['full_attempts']+1
        folder=HERE/'science'/f'{index:03d}';folder.mkdir(parents=True,exist_ok=False)
        decision=action_for(task,design)
        save(folder/'input.json',dict(task=task,design=design,decision=decision,group=group,
             slot=slot,phase=phase,lc_context_binding=digest(context) if context else None))
        timeout=min(120.,4800-self.ledger['full_wall_s'],load(HERE/'preflight.json')['absolute_deadline_epoch']-time.time())
        row=dict(index=index,group=group,slot=slot,phase=phase,task_id=task['task_id'],
            condition_id=condition_id(task),design_sha256=digest(design),cache_key=key,path=str(folder),status='STARTED',reused=False)
        self.ledger['full_attempts']+=1;self.ledger['rows'].append(row);self.persist()
        start=time.monotonic();before=signal.getsignal(signal.SIGALRM)
        def expire(*args):raise TimeoutError('FULL_OR_PACKAGE_DEADLINE')
        signal.signal(signal.SIGALRM,expire);signal.setitimer(signal.ITIMER_REAL,max(.001,timeout))
        try:
            kwargs=dict(task_resolver=lambda ident:task if ident==task['task_id'] else None)
            if is_lc(task):value=lc_adapter.execute(task,task['initial_design'],task['initial_problem'],decision,folder/'result',context=context,**kwargs)
            else:value=door.execute(task,task['initial_design'],task['initial_problem'],decision,folder/'result',**kwargs)
            value['condition_id']=condition_id(task)
            path=folder/'result/public-result.json.gz';door._write_gzip(path,value)
            (folder/'result/public-result.json').unlink()
            if is_lc(task):
                for name in ('raw','assessment'):compact_file(folder/'result'/f'{name}.json')
            row.update(status='COMPLETE',model_valid=value['model_valid'],verdict=value['public_check']['verdict'],public_path=str(path))
            self.cache[key]=dict(path=str(path),origin='THIS_PACKAGE_NEW_FULL')
        except Exception as exc:
            row.update(status='TOOL_ERROR',error=type(exc).__name__+':'+str(exc))
            value=dict(task_id=task['task_id'],design=deepcopy(design),condition_id=condition_id(task),
                execution_status='TOOL_ERROR',model_valid=False,public_check=dict(verdict='UNKNOWN'),error=row['error'])
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,before)
            elapsed=time.monotonic()-start;row['full_wall_s']=elapsed;self.ledger['full_wall_s']+=elapsed
            save(folder/'receipt.json',row);journal(HERE/'logical-inputs.jsonl',row);self.persist()
        value.update(reused=False,new_full_wall_s=elapsed,canonical_public_path=row.get('public_path'))
        print(json.dumps(dict(event='FULL',group=group,slot=slot,condition=condition_id(task),verdict=value['public_check']['verdict'],status=row['status'])),flush=True)
        return public_copy(value,task)
