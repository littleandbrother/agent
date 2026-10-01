"""Pure prospective two-profile declaration check; accepts no outcomes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
RULE_PATH=Path(__file__).with_name('RULES.json')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def sha(value):
    return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None


def expected_method_hash(protocol,profile):
    # Reuse the exact existing policy renderer; this invokes no Adapter/tool.
    spec=importlib.util.spec_from_file_location('comparison_method',ROOT/'src/method_adapter.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    task=json.loads((ROOT/'contracts/MIGRATION.json').read_text())['normalized_main_task']
    return digest(module.method_prompt(protocol,profile,task,[])['policy'])


def check(pair):
    """Stable codes only. Equality is not proof of delivery, authorship or timing."""
    result={'schema':'bf-rq-comparison-preflight-v1','status':'BLOCKED','issues':[],
            'rules_sha256':None,
            'actual_delivery_verified':False,'actual_budget_enforcement_verified':False,
            'pre_run_seal_timing_verified':False,'method_benefit':'not assessed',
            'execution_authorized':False,'formal_method_comparison':False}
    try:
        rules_raw=RULE_PATH.read_bytes()
        result['rules_sha256']=hashlib.sha256(rules_raw).hexdigest()
        rules=json.loads(rules_raw)
        protocol=json.loads((ROOT/'contracts/PROTOCOL.json').read_text())
        if digest({k:v for k,v in protocol.items() if k!='protocol_hash'})!=rules['protocol_hash'] or protocol['protocol_hash']!=rules['protocol_hash']:
            raise ValueError('PROTOCOL_BINDING')
        if not isinstance(pair,list) or len(pair)!=2:raise ValueError('PAIR_REQUIRED')
        required={'run_id','owner','profile','protocol_hash','rules_sha256','method_policy_sha256','max_candidates','identities','budgets'}
        records=[];missing=[];unequal=[]
        profiles={v['id']:v for v in protocol['profiles']}
        for entry in pair:
            if set(entry)!={'source_id','sha256','record'}:raise ValueError('SOURCE_FIELDS')
            if not isinstance(entry['source_id'],str) or re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',entry['source_id']) is None:raise ValueError('SOURCE_ID')
            r=entry['record']
            if not sha(entry['sha256']) or digest(r)!=entry['sha256']:raise ValueError('SOURCE_HASH')
            if not isinstance(r,dict) or set(r)!=required:raise ValueError('RECORD_FIELDS')
            if any(not isinstance(r[k],str) or re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',r[k]) is None for k in ('run_id','owner')):raise ValueError('RUN_IDENTITY')
            if r['profile'] not in profiles:raise ValueError('PROFILE')
            if r['protocol_hash']!=rules['protocol_hash'] or r['rules_sha256']!=result['rules_sha256']:raise ValueError('DECLARATION_SEAL')
            if r['method_policy_sha256']!=expected_method_hash(protocol,r['profile']):raise ValueError('METHOD_POLICY')
            if type(r['max_candidates']) is not int or r['max_candidates']!=protocol['max_new_candidates_per_owner']:raise ValueError('QUOTA')
            for group,fields in [('identities',rules['equal_identity_fields']),('budgets',rules['equal_budget_fields'])]:
                if not isinstance(r[group],dict) or set(r[group])-set(fields):raise ValueError('CONFIGURATION_FIELDS')
                for field in fields:
                    value=r[group].get(field)
                    if value is None:missing.append(group+'.'+field)
                    elif group=='identities' and not sha(value):raise ValueError('IDENTITY_HASH')
                    elif group=='budgets' and (type(value) is not int or value<0):raise ValueError('BUDGET_VALUE')
            if r['identities'].get('task_hash') not in (None,protocol['normalized_task_hash']):raise ValueError('TASK_BINDING')
            baseline=digest(protocol['common_facts_and_freedoms']['baseline'])
            if r['identities'].get('initial_candidate_hash') not in (None,baseline):raise ValueError('INITIAL_CANDIDATE_BINDING')
            records.append(r)
        a,b=records
        if pair[0]['source_id']==pair[1]['source_id'] or a['owner']==b['owner'] or a['run_id']==b['run_id']:raise ValueError('RUN_ISOLATION')
        if a['profile']==b['profile']:unequal.append('distinct_RQ_profiles_required')
        for group,fields in [('identities',rules['equal_identity_fields']),('budgets',rules['equal_budget_fields'])]:
            for field in fields:
                av,bv=a[group].get(field),b[group].get(field)
                if av is not None and bv is not None and av!=bv:unequal.append(group+'.'+field)
        result.update(status='INCOMPARABLE' if unequal else 'UNKNOWN' if missing else 'MATCHED_DECLARATIONS_ONLY',
            issues=sorted(set(unequal)),unknown_fields=sorted(set(missing)),
            profiles=[a['profile'],b['profile']],changed_factors=[k for k in ('R','Q') if profiles[a['profile']][k]!=profiles[b['profile']][k]],
            source_hashes=[v['sha256'] for v in pair])
        if len(result['changed_factors'])==2:result['factor_attribution']='R and Q jointly differ; individual effects not identified'
    except Exception:
        # No exception repr or unchecked input is included in public output.
        result.update(status='BLOCKED',issues=['INVALID_OR_UNBOUND_DECLARATION'])
    return result
