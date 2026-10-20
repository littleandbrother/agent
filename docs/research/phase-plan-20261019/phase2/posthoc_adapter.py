"""External engineering replay of already-generated model output, zero new Pi.

Original failed episodes/protocols remain immutable. This posthoc diagnostic
cannot be relabeled as an accepted original tool submission or a benefit test.
"""
from pathlib import Path
from decimal import Decimal
import copy
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.campaign20261019.common import digest, file_hash, seal
from bfworld.agentlab.campaign20261019.phase2 import CaseStore, VARIABLES, consume
from bfworld.agentlab.campaign20261019.phase2_discovery import validate_proposal, evaluate_proposal

OUT=Path('/Users/depengsu/.local/share/bf-phase2-20261020')
HIST=Path('/Users/depengsu/.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-001')


def pointer(source,path):
    value=source
    for part in path.split('/')[1:]:
        key=part.replace('~1','/').replace('~0','~')
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value


def independent_ast(tree, source):
    if 'field' in tree:
        v=pointer(source,tree['field'])
        return Decimal(str(v)) if type(v) in (int,float) else v
    if 'constant' in tree:
        v=tree['constant']
        return Decimal(str(v)) if type(v) in (int,float) else v
    values=[independent_ast(x,source) for x in tree['args']]
    a,b=values
    if tree['op']=='mul': return a*b
    if tree['op']=='sub': return a-b
    if tree['op']=='add': return a+b
    if tree['op']=='div': return a/b
    if tree['op']=='gt': return a>b
    if tree['op']=='ge': return a>=b
    if tree['op']=='lt': return a<b
    if tree['op']=='le': return a<=b
    if tree['op']=='eq': return a==b
    raise ValueError('UNSUPPORTED_INDEPENDENT_POSTHOC_OPERATOR')


def prefix_pointer_fields(v):
    if isinstance(v,list): return [prefix_pointer_fields(x) for x in v]
    if isinstance(v,dict):
        return {k:('/'+x if k=='field' and isinstance(x,str) and not x.startswith('/') else prefix_pointer_fields(x)) for k,x in v.items()}
    return v


def main():
    episode=OUT/'p2-e5-001';dest=episode/'posthoc-adapter-001'
    if dest.exists(): raise FileExistsError('IMMUTABLE_POSTHOC_DIAGNOSTIC_EXISTS')
    rows=[json.loads(x) for x in (episode/'pi-public-trace.jsonl').read_text().splitlines()]
    calls=[v['arguments'] for x in rows if x.get('type')=='assistant_public' for v in x['content'] if v.get('type')=='toolCall']
    proposals=[x for x in calls if x['action']=='propose']
    first,corrected=proposals[0],proposals[1]
    assert prefix_pointer_fields(first['spec']['ast'])==corrected['spec']['ast']
    assert first['policy']==corrected['policy']
    spec=validate_proposal(corrected['spec'])
    store=CaseStore(APP,OUT/'cases',HIST)
    acquisition=json.loads((episode/'scientific/acquisitions'/(spec['source_id']+'.json')).read_text())
    source=store.source(spec['source_id'])
    if (source['source_sha256']!=acquisition['source_sha256'] or
            source['parent_sha256']!=acquisition['parent_sha256']):
        raise ValueError('ACTUAL_ACQUISITION_NOT_AUTHENTIC')
    observed=evaluate_proposal(spec,source['payload'],field_units=source['field_units'])
    if observed['status']!='OBSERVED' or observed['unit_status']!='CHECKED_AGAINST_SUPPLIED_MAPPING':
        raise ValueError('DOMAIN_OR_UNITS_REJECTED')
    independent=independent_ast(spec['ast'],source['payload'])
    if independent!=observed['value']:raise ValueError('INDEPENDENT_DECIMAL_VALUE_DISAGREED')
    # Probe expression/source dependence only. These are source evaluations,
    # not simulations, model decisions or modified true BF worlds.
    probes=[]
    for variable,ends in VARIABLES.items():
        if variable not in source['payload']:continue
        for end in ends:
            payload=copy.deepcopy(source['payload']);payload[variable]=end
            result=evaluate_proposal(spec,payload,field_units=source['field_units'])
            if result['status']=='OBSERVED':
                second=independent_ast(spec['ast'],payload)
                assert second==result['value']
                probes.append({'variable':variable,'value':end,'relation_value':result['value']})
    values={digest(x['relation_value']) for x in probes}
    if len(values)<2:raise ValueError('UNINFORMATIVE_SOURCE_RELATION')
    bad_domain=copy.deepcopy(source['payload']);bad_domain['capacitance_f']=1
    domain_negative=evaluate_proposal(spec,bad_domain,field_units=source['field_units'])
    if domain_negative['status']!='UNKNOWN':raise ValueError('OUT_OF_DOMAIN_NEGATIVE_FAILED')
    observation={'qualification':'EXTERNAL_PASS','value':observed['value'],'units':observed['units'],
        'source_sha256':source['source_sha256'],'spec_sha256':digest(spec),
        'qualification_kind':'POSTHOC_HOST_ADAPTER_REEVALUATION'}
    policy=corrected['policy'];task=store.task('b-volatile-reset')
    current={k:task['device'][k] for k in VARIABLES}
    before=consume(None,policy,current)
    after=consume(observation,policy,current,registry={digest(observation):observation})
    assert after['used_observation'] and after['design']!=before['design']
    assert consume(observation,policy,current)['judgment']=='UNKNOWN' # self-signature alone
    new_before=store.new_executions
    executed=store.execute('b-volatile-reset',after['design'])
    old=store.execute('b-volatile-reset',current)
    static=store.execute('b-volatile-reset',{'capacitance_f':1e-5,'tx_not_before_s':0})
    binding={'label':'POSTHOC_HOST_ADAPTER_REEVALUATION','original_episode_status':json.loads((episode/'episode-result.json').read_text())['status'],
        'actual_model_owner':json.loads((episode/'owner.json').read_text())['owner'],
        'actual_generated_corrected_call':corrected,'actual_call_sha256':digest(corrected),
        'original_model_trace_sha256':file_hash(episode/'pi-public-trace.jsonl'),
        'original_protocol_sha256':file_hash(episode/'protocol.json'),
        'qualification_code_sha256':file_hash(Path(__file__)),'source':source,
        'independent_implementation':'Decimal AST interpreter separate from bounded proposal evaluator',
        'unit_status':observed['unit_status'],'domain_status':observed['domain_status'],
        'relation_value':observed['value'],'source_dependence_probes':probes,
        'negative_controls':{'missing_observation':'UNKNOWN','self_signed_observation':'UNKNOWN',
            'out_of_domain':domain_negative['status'],'source_hash_binding':'PASS',
            'constant_relation':'REJECT_BY_DISTINCT_PROBE_VALUES'},
        'new_provider_requests':0,'new_model_proposals':0,'frozen_true_world_changed':False,
        'scope':'Engineering adapter replay of existing model-generated output; not original episode success or evidence of method superiority.'}
    decision={'before':before,'after':after,'observation':observation,'policy':policy,
              'consumer_input_edge_sha256':digest({'observation':observation,'policy':policy}),
              'actual_executed_input_sha256':executed['input_sha256']}
    seal(dest/'qualification.json',binding);seal(dest/'consumer.json',decision)
    seal(dest/'service.json',{'original':old,'selected':executed,'static_complete':static})
    result={'status':'POSTHOC_REAL_CONSUMER_AND_SERVICE_EXECUTED','label':binding['label'],
        'original_live_E5_success':False,'qualified_engineering_relation':True,
        'mode':spec['mode'],'before_design':current,'after_design':after['design'],
        'original_service':old['complete_service'],'selected_service':executed['complete_service'],
        'static_complete_service':static['complete_service'],
        'new_scientific_executions':store.new_executions-new_before,'total_new_scientific_executions':store.new_executions,
        'new_provider_requests':0,'physical_qualification':'UNKNOWN',
        'qualification_sha256':file_hash(dest/'qualification.json'),
        'consumer_sha256':file_hash(dest/'consumer.json'),'service_sha256':file_hash(dest/'service.json'),
        'superiority_claim':False,'original_failed_attempt_unchanged':True}
    seal(dest/'result.json',result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
