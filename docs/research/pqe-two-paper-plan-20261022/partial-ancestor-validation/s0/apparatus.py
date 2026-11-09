"""Single real consumer, shared static prescreen, cache, and finite resources."""
from copy import deepcopy
import signal
import time
from common import *
from public_bridge import project
from bfworld.agentlab.pqe20261024debt import adapter, task as task_module


def action_for(task, design):
    return dict(actual_input=dict(operation='edit', design_patch={k:deepcopy(v) for k,v in
        design.items() if task['initial_design'].get(k)!=v}, problem_patch=dict(
        active_variables=list(task['design_domain'])),dt_s=task['integration']['dt_s']))


class Apparatus:
    def __init__(self):
        if (HERE/'science-resource-ledger.json').exists():
            raise RuntimeError('NO_AUTOMATIC_MATRIX_RERUN')
        self.cache={}
        self.ledger=dict(full_attempts=0,full_wall_s=0.,cheap_numeric=0,
                         static_hits=0,reused=0,rows=[],prechecks=[])
        self.original_static=task_module.static_geometry_facts
        task_module.static_geometry_facts=self.static_geometry

    def persist(self):
        save(HERE/'science-resource-ledger.json',self.ledger)

    def static_geometry(self, mechanism):
        from bfworld.agentlab.pqe20261022 import door_model
        f=door_model.source_step
        key=(f,getattr(f,'__code__',None),json.dumps(dict(mechanism=mechanism,
            defaults=door_model.DEFAULT_MECHANISM,domain=door_model.DOMAIN),sort_keys=True,
            separators=(',',':'),allow_nan=False))
        if key in task_module._STATIC_GEOMETRY_CACHE:self.ledger['static_hits']+=1
        else:
            if self.ledger['cheap_numeric']+16>=96:raise RuntimeError('GLOBAL_CHEAP_CAP')
            self.ledger['cheap_numeric']+=1
        value=self.original_static(mechanism)
        self.persist()
        return value

    @staticmethod
    def key(task,design):
        return digest(dict(task=task,design=design,sources=adapter.source_identity()))

    def admit(self,task,design,path,*,origin):
        public=load(path)
        if public.get('task_id')!=task['task_id'] or public.get('design')!=design:
            raise RuntimeError('REUSE_INPUT_BINDING:'+origin)
        decision=load(Path(path).parent/'decision.json')
        if decision['task_sha256']!=digest(task):raise RuntimeError('REUSE_TASK_HASH:'+origin)
        sources=adapter.source_identity()
        if decision['sources'] != sources:
            fixed=('door_model.py','door_program.py','engineering.py','executor.py',
                   'evaluator.py','bold/consumer.py','bold/firmware.py','codebt/adapter.py',
                   'codebt/holding.py','codebt/bounds.py')
            if design['holding_component']!='off' or any(decision['sources'][k]!=sources[k] for k in fixed):
                raise RuntimeError('REUSE_SOURCE_BINDING:'+origin)
            raw=load(Path(path).parent/'raw.json.gz')
            if raw.get('holding_route')!='OFF_EXACT_ORIGINAL_FUNCTION':
                raise RuntimeError('REUSE_OFF_ROUTE_BINDING:'+origin)
            self.ledger.setdefault('off_route_reuse_bindings',[]).append(dict(
                origin=origin,decision=ref(Path(path).parent/'decision.json'),raw=ref(Path(path).parent/'raw.json.gz'),
                identical_executed_sources={k:sources[k] for k in fixed},
                changed_nonexecuted_or_projection_sources={k:dict(old=v,current=sources[k]) for k,v in decision['sources'].items() if v!=sources[k]},
                scope='Exact task/design/dt, unchanged original OFF function; enabled path and public projection changes are not numerical re-executions.'))
        public['condition_id']=task['condition_id']
        self.cache[self.key(task,design)]=dict(public=public,path=str(path),origin=origin)

    def ready(self):
        require_capacity_and_time()
        require_sources(load(OUT/'shared/protocol.json'))
        if self.ledger['full_attempts']+60>=512:raise RuntimeError('GLOBAL_FULL_COUNT_CAP')
        if self.ledger['full_wall_s']+125.5230115413433>=3600:raise RuntimeError('GLOBAL_FULL_WALL_CAP')

    def member(self,task,design,*,group,slot,phase):
        self.ready()
        key=self.key(task,design)
        if key in self.cache:
            cached=self.cache[key];self.ledger['reused']+=1;self.persist()
            public=deepcopy(cached['public'])
            public.update(condition_id=task['condition_id'],reused=True,canonical_public_path=cached['path'],
                          cache_origin=cached['origin'],new_full_wall_s=0.)
            return project(public)
        index=self.ledger['full_attempts']+1
        folder=HERE/'science'/f'{index:03d}'
        folder.mkdir(parents=True,exist_ok=False)
        decision=action_for(task,design)
        save(folder/'input.json',dict(task=task,design=design,decision=decision,group=group,slot=slot,phase=phase))
        timeout=min(120.,3600-125.5230115413433-self.ledger['full_wall_s'],
                    load(HERE/'preflight.json')['absolute_deadline_epoch']-time.time())
        row=dict(index=index,group=group,slot=slot,phase=phase,task_id=task['task_id'],
                 condition_id=task['condition_id'],design_sha256=digest(design),path=str(folder),status='STARTED')
        self.ledger['full_attempts']+=1;self.ledger['rows'].append(row);self.persist()
        started=time.monotonic();old_signal=signal.getsignal(signal.SIGALRM)
        def expire(*_):raise TimeoutError('FULL_120S_OR_GLOBAL_REMAINING_WALL')
        signal.signal(signal.SIGALRM,expire);signal.setitimer(signal.ITIMER_REAL,max(.001,timeout))
        try:
            public=adapter.execute(task,task['initial_design'],task['initial_problem'],decision,
                folder/'result',task_resolver=lambda ident:task if ident==task['task_id'] else None)
            public['condition_id']=task['condition_id']
            path=folder/'result/public-result.json.gz';adapter._write_gzip(path,public)
            (folder/'result/public-result.json').unlink()
            row.update(status='COMPLETE',model_valid=public['model_valid'],verdict=public['public_check']['verdict'],public_path=str(path))
            self.cache[key]=dict(public=public,path=str(path),origin='NEW_FULL')
        except Exception as exc:
            row.update(status='TOOL_ERROR',error=type(exc).__name__+':'+str(exc))
            public=dict(task_id=task['task_id'],design=deepcopy(design),condition_id=task['condition_id'],
                execution_status='TOOL_ERROR',model_valid=False,public_check=dict(verdict='UNKNOWN'),error=row['error'])
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_signal)
            elapsed=time.monotonic()-started;row['full_wall_s']=elapsed
            self.ledger['full_wall_s']+=elapsed;save(folder/'receipt.json',row);self.persist()
        public.update(reused=False,new_full_wall_s=elapsed,canonical_public_path=row.get('public_path'))
        print(json.dumps(dict(event='FULL',group=group,slot=slot,condition=task['condition_id'],
            status=row['status'],verdict=public['public_check']['verdict'],wall_s=elapsed)),flush=True)
        return project(public)

    def evaluate(self,family,design,*,group,slot,phase='main',request_id=None):
        self.ready()
        pre=dict(group=group,slot=slot,design_sha256=digest(design))
        try:
            t=family[0]
            adapter.prepare(t,t['initial_design'],t['initial_problem'],action_for(t,design),
                            task_resolver=lambda ident:t if ident==t['task_id'] else None)
            pre['status']='PASS'
        except ValueError as exc:
            pre.update(status='MODEL_DOMAIN',reason=str(exc))
        self.ledger['prechecks'].append(pre);self.persist()
        if pre['status']!='PASS':
            rows=[dict(task_id=t['task_id'],condition_id=t['condition_id'],design=deepcopy(design),
                execution_status='MODEL_DOMAIN',model_valid=False,public_check=dict(verdict='UNKNOWN'),
                domain_error=pre['reason'],reused=False,new_full_wall_s=0.) for t in family]
        else:
            rows=[]
            for i,t in enumerate(family):
                row=self.member(t,design,group=group,slot=slot,phase=phase);rows.append(row)
                if row.get('execution_status')=='TOOL_ERROR':
                    rows.extend(dict(task_id=other['task_id'],condition_id=other['condition_id'],
                        design=deepcopy(design),execution_status='NOT_RUN_DEPENDENCY_TOOL_ERROR',
                        model_valid=False,public_check=dict(verdict='UNKNOWN'),
                        reused=False,new_full_wall_s=0.) for other in family[i+1:])
                    break
        valid=len(rows)==len(family) and all(r.get('model_valid') is True and r.get('execution_status')
            in {'OK','COMPLETE','COMPLETED','SUCCESS'} for r in rows)
        verdict='UNKNOWN' if not valid else 'PASS' if all(r['public_check']['verdict']=='PASS' for r in rows) else 'FAIL'
        return dict(design=deepcopy(design),request_id=request_id,results=rows,model_valid=valid,
            execution_status='COMPLETE' if len(rows)==len(family) else 'TOOL_ERROR',public_check=dict(verdict=verdict),
            score=sum(r.get('public_check',{}).get('verdict')=='PASS' for r in rows),
            usage=dict(full_inputs=sum(r.get('new_full_wall_s',0)>0 for r in rows) if pre['status']=='PASS' else 0,
                       full_wall_s=sum(r['new_full_wall_s'] for r in rows)))
