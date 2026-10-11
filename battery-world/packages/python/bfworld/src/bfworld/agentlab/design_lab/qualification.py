"""No-Agent environment controls. Never connected as a Pi answer tool."""
from pathlib import Path
from . import case_c
from .contracts import contract, snapshot, sha, sealed
from ..store import identity


def sources(environment, correct=False):
    root=Path(environment['root'])
    application=(root/'program.c').read_text()
    if not correct:
        application+='\nvoid bf_event(uint32_t id,uint8_t kind){(void)id;(void)kind;}\n'
    else:
        begin=application.index('void bf_payload(')
        application=application[:begin]+'''
static uint32_t latest_id=0;
static uint8_t latest_kind=0;
void bf_event(uint32_t id,uint8_t kind){latest_id=id;latest_kind=kind;}
void bf_payload(uint8_t *out){
    out[0]='B';out[1]='F';out[2]='M';out[3]='C';out[4]=1;out[5]=latest_kind;
    for(int i=0;i<4;i++)out[6+i]=(uint8_t)(latest_id>>(8*i));
    out[10]=0;out[11]=0;for(int i=0;i<11;i++)out[11]^=out[i];
}
'''
    return {'program.c':application,'policy.h':(root/'policy.h').read_text()}


def validation_id():
    return 'Venv-'+identity({'version':case_c.VALIDATOR_VERSION,'code':sha(case_c.__file__),
                            'contract':sha(Path(__file__).with_name('contracts.py')),
                            'qualifier':sha(__file__)})


def qualify(environment,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    task=contract(environment['environment_id'],validation_id())
    controls=[]
    designs={}
    for label,correct in [('reference',True),('wrong-event-frame',False)]:
        design=snapshot(task,sources(environment,correct));designs[label]=design
        root=directory/label
        build=case_c.build(design,root)
        execute=case_c.execute(task,design,build,root,environment)
        check=case_c.evaluate(task,design,build,execute,environment)
        for name,value in [('snapshot.json',design),('build.json',build),('execution.json',execute),('check.json',check)]:sealed(root/name,value)
        expected='PASS' if correct else 'FAIL'
        observed='PASS' if all(v=='PASS' for v in check['gates'].values()) else 'FAIL'
        controls.append({'name':label,'expected':expected,'observed':observed,'matched':expected==observed,
                         'execution_id':execute['execution_id'],'check_id':check['check_id']})
    design=designs['reference'];root=directory/'reference'
    import json
    build=json.loads((root/'build.json').read_text());execution=json.loads((root/'execution.json').read_text())
    for label,event in [('new-id',{'time_s':2.5,'event_id':4294967239,'kind':1}),
                        ('close-port-conformance',{'time_s':2.5,'event_id':17,'kind':2})]:
        out=directory/label;new_build=case_c.build(design,out)
        x=case_c.execute(task,design,new_build,out,environment,event=event)
        c=case_c.evaluate(task,design,new_build,x,environment,event_truth=event)
        controls.append({'name':label,'expected':'PASS','observed':c['gates'],'matched':all(v=='PASS' for v in c['gates'].values()),
                         'claim':'Virtual event-port conformance, not an independently powered closing motion.'})
        sealed(out/'execution.json',x);sealed(out/'check.json',c)
    loss=case_c.evaluate(task,design,build,execution,environment,link_loss=True)
    controls.append({'name':'RF-not-received','expected':'FAIL','observed':loss['gates']['deadline_receive'],
                     'matched':loss['gates']['deadline_receive']=='FAIL','claim':'Injected virtual link loss only.'})
    for label,fault in [('zero-supply',lambda t:True),('brownout-during-TX',lambda t:2.856<=t<=2.9)]:
        out=directory/label;new_build=case_c.build(design,out)
        x=case_c.execute(task,design,new_build,out,environment,supply_override=fault)
        c=case_c.evaluate(task,design,new_build,x,environment)
        controls.append({'name':label,'expected':'NO_DELIVERY_AND_RECHECK','observed':c['gates'],
                         'matched':x['brownout_reset_valid'] and not x['transmitted'] and c['gates']['power_fixed_point']=='UNEVALUABLE',
                         'claim':'Fault-injected F0 execution; no new native analog solve.'})
        sealed(out/'execution.json',x);sealed(out/'check.json',c)
    changed=dict(execution);changed['design_id']='D-wrong-version'
    try:case_c.evaluate(task,design,build,changed,environment);rejected=False
    except ValueError:rejected=True
    controls.append({'name':'stale-build','expected':'REJECT','observed':'REJECT' if rejected else 'ACCEPT','matched':rejected})
    # A deliberate workload change must invalidate native evidence reuse.
    changed_sources=sources(environment,True)
    changed_sources['policy.h']=changed_sources['policy.h'].replace('#define TX_MS 5.0','#define TX_MS 6.0')
    if changed_sources==sources(environment,True):
        import re
        changed_sources['policy.h']=re.sub(r'(#define TX_MS)\s+[^\n]+',r'\1 6.0',changed_sources['policy.h'])
    changed_design=snapshot(task,changed_sources)
    out=directory/'changed-load';b=case_c.build(changed_design,out);x=case_c.execute(task,changed_design,b,out,environment)
    c=case_c.evaluate(task,changed_design,b,x,environment)
    controls.append({'name':'changed-load','expected':'UNEVALUABLE','observed':c['gates']['power_fixed_point'],
                     'matched':c['gates']['power_fixed_point']=='UNEVALUABLE' and x['native_solve']=='RECHECK_REQUIRED'})
    sealed(out/'execution.json',x);sealed(out/'check.json',c)
    report={'schema_version':'bf-design-environment-qualification-v1','environment_id':environment['environment_id'],
            'validation_id':task['validation_id'],'scope':task['scope'],'controls':controls,
            'passed':all(c['matched'] for c in controls),'model_calls':0,'new_native_solver_calls':0,
            'qualifier_sha256':sha(__file__),'physical':'NOT_TESTED','full_product_passed':False}
    sealed(directory/'qualification.json',report)
    return report

