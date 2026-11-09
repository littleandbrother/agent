"""Exact prior tasks/initials/cache, plus identical exposed development history."""
from common import *
from apparatus import door,lc_adapter,bridge
from bfworld.agentlab.pqe20261022 import pilot


def inputs():
    manifest=load(OLD/'a/stage3-host/MANIFEST.json')
    families={'DOOR':[],'LC':[]};contexts={}
    for entry in manifest['entries']:
        for key in ('task','initial_design','initial_problem','lc_public','lc_host_task'):
            if key in entry:
                assert ref(entry[key]['path'])==entry[key]
        task=load(entry['task']['path']);families[entry['family']].append(task)
        if entry['family']=='LC':contexts[task['task_id']]=dict(public=load(entry['lc_public']['path']),host_task=load(entry['lc_host_task']['path']))
    initials={name:load(OLD/'s0/initial'/f'{name}.json.gz') for name in families}
    for name,tasks in families.items():
        assert len(tasks)==3 and initials[name]['design']==tasks[0]['initial_design']
        assert initials[name]['model_valid'] and len(initials[name]['results'])==3
    return families,contexts,initials


def contract(name,tasks,initial):
    public_tasks=[pilot.public_task(t) if name=='DOOR' else bridge.public_copy(t) for t in tasks]
    return dict(family_id=name,world_kind='LC-PV' if name=='LC' else 'DOOR',
        tasks=public_tasks,design_domain=tasks[0]['design_domain'],initial_design=tasks[0]['initial_design'],
        initial_problem=tasks[0]['initial_problem'],active_variables=tasks[0]['initial_problem']['active_variables'],
        component_contract=initial['results'][0].get('component_contract'))


def admit_prior(app,families,contexts):
    known={t['task_id']:t for tasks in families.values() for t in tasks}
    admitted=0
    for row in load(OLD/'s0/science-resource-ledger.json')['rows']:
        if row['status']!='COMPLETE' or row['task_id'] not in known:continue
        saved=load(Path(row['path'])/'input.json');task=known[row['task_id']]
        assert saved['task']==task
        app.admit(task,saved['design'],row['public_path'],origin='CLOSED_BFA100_EXACT_INPUT',context=contexts.get(task['task_id']))
        admitted+=1
    return admitted


def history():
    old=load(OLD/'s0/stage3-result.json')
    rows=[]
    for trajectory in old['trajectories']:
        for h in trajectory['history']:
            rows.append(dict(source_trajectory=trajectory['ident'],family=trajectory['family'],slot=h['slot'],
                design=h['design'],model_valid=h['model_valid'],statuses=h['statuses'],
                public_check=h['public_check'],result=h['result']))
    return dict(scope='All 38 previously exposed BFA100 development proposals; identical for every new condition/repetition. No new-group future result.',
        rows=rows,prefixes=[ref(OLD/'shared/prefixes'/f'{name}.json.gz') for name in ('identity-progress','saved-undelivered')],
        source=ref(OLD/'s0/stage3-result.json'),upstream_weight_identity='unreported')


class Facts:
    """Memoize exact pure public fact/calculation inputs, not cross-group outcomes."""
    def __init__(self,app):
        self.app=app
        self.a=module(OUT/'a/shared_facts.py','joint_common_public_facts')
        self.cache={}
        self.cost=dict(fact_requests=0,calculation_requests=0,memo_hits=0,actual_api_calls=0,wall_s=0.)

    def call(self,kind,contract,design,public_result=None,operation='all',meter=None):
        start=time.monotonic()
        # Each group supplies only its own observed result. The function cache
        # key contains those complete sanitized input bytes and source identity.
        observed=bridge.public_copy(public_result) if public_result else None
        def sanitize(v):
            if isinstance(v,dict):return {k:sanitize(x) for k,x in v.items() if k not in {'reused','new_full_wall_s','canonical_public_path','cache_origin','provenance'}}
            if isinstance(v,list):return [sanitize(x) for x in v]
            return deepcopy(v)
        observed=sanitize(observed)
        key=digest(dict(kind=kind,contract=contract,design=design,observed=observed,operation=operation,source=ref(OUT/'a/shared_facts.py')))
        self.cost['fact_requests' if kind=='facts' else 'calculation_requests']+=1
        if key in self.cache:
            self.cost['memo_hits']+=1;self.app.meter('memo_hit',key)
            value=deepcopy(self.cache[key])
        else:
            fn=self.a.candidate_facts if kind=='facts' else self.a.calculate
            kwargs=dict(public_result=observed,meter=self.app.fact_meter)
            if kind!='facts':kwargs['operation']=operation
            value=fn(contract,deepcopy(design),**kwargs)
            assert value.get('design_sha256',value.get('binding',{}).get('design_sha256'))==digest(design)
            self.cache[key]=deepcopy(value);self.cost['actual_api_calls']+=1
            save(HERE/'public-calculations'/f'{key}.json.gz',dict(input_binding=dict(kind=kind,contract_sha256=digest(contract),design_sha256=digest(design),observation_sha256=digest(observed),operation=operation),result=value))
        self.cost['wall_s']+=time.monotonic()-start
        return value

    def facts(self,contract,design,public_result=None,*,meter=None):
        return self.call('facts',contract,design,public_result,meter=meter)

    def calculate(self,contract,design,operation='all',*,public_result=None,meter=None):
        return self.call('calculate',contract,design,public_result,operation,meter=meter)
