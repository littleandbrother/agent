"""Versioned contract repair; original actual-run sources stay immutable.

Only two targeted regressions use the original failed inputs. No provider or
scientific execution is triggered. Future dispatch must bind this new version.
"""
from pathlib import Path
import copy
import importlib.util
import json
import sys

ROOT=Path(__file__).resolve().parents[4]
APP=ROOT/'workbench/bf-campaign-s0-20261019/battery-world'
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from jsonschema import Draft202012Validator
from bfworld.agentlab.campaign20261019 import phase2_discovery as discovery, phase2_methods as methods
from bfworld.agentlab.campaign20261019.common import seal,digest,file_hash

OUT=Path('/Users/depengsu/.local/share/bf-phase2-20261020')


def schema(kind):
    if kind=='E5':
        s=copy.deepcopy(discovery.tool_schema())
        def visit(v):
            if isinstance(v,dict):
                for k,child in v.items():
                    if k=='field' and isinstance(child,dict) and child.get('type')=='string':
                        child.update(pattern=r'^(?:/(?:[^~]|~[01])*)?$',
                            description="JSON Pointer, e.g. /field_name or /items/0/value. Use / prefix; encode tilde as ~0 and slash in a key as ~1. Bare field names are invalid.")
                    visit(child)
            elif isinstance(v,list):
                for x in v:visit(x)
        visit(s)
        return s
    if kind=='H':
        return {'type':'object','additionalProperties':False,'required':['action'],
                'properties':{'action':{'enum':['inspect','sources','acquire','propose','submit']},
                    'source_id':{'type':'string'},'proposal':methods.tool_schema(),
                    'reason':{'type':'string','maxLength':4000}},
                'allOf':[{'if':{'properties':{'action':{'enum':['propose','submit']}}},
                          'then':{'required':['proposal']}}]}
    raise ValueError('UNKNOWN_ADAPTER_KIND')


class ProposalCounter:
    """Action/type/syntax rejects <=2; valid unique H or E5 proposals <=1.

All calls and provider requests retain their costs and overall bounds. A wrong
H/D operation never occupies the other artifact's proposal slot. Explicit H
no-update remains legal at the proposal cap. Valid proposals count on first
propose/submit, independently of subsequent qualification or service outcome.
"""
    def __init__(self,kind):
        self.kind=kind;self.validator=Draft202012Validator(schema(kind))
        self.used=set();self.rejected_operations=0
    def prepare(self,body):
        try:
            self.validator.validate(body)
            if body['action'] not in ('propose','submit'):return body
            if self.kind=='H':
                value=methods.validate_method(body['proposal'])
                if value['decision']=='no-update':return body
                candidate=value
            else:
                candidate=discovery.validate_request(body,legal_domain={
                    'capacitance_f':[4e-6,22e-6],'tx_not_before_s':[0,.045]})
                candidate={k:v for k,v in candidate.items() if k!='action'}
        except (ValueError, __import__('jsonschema').exceptions.ValidationError) as error:
            self.rejected_operations+=1
            if self.rejected_operations>2:raise ValueError('V2_SYNTAX_REJECTION_CAP') from error
            raise ValueError('V2_ACTION_TYPE_OR_SYNTAX_REJECTED') from error
        key=digest(candidate)
        if key not in self.used and len(self.used)>=1:raise ValueError('V2_VALID_PROPOSAL_CAP')
        self.used.add(key)
        return body


def model_calls(episode):
    rows=[json.loads(x) for x in (OUT/episode/'pi-public-trace.jsonl').read_text().splitlines()]
    return [v['arguments'] for x in rows if x.get('type')=='assistant_public'
            for v in x['content'] if v.get('type')=='toolCall']


def main():
    e5=[x for x in model_calls('p2-e5-001') if x['action']=='propose']
    counter=ProposalCounter('E5')
    try:counter.prepare(e5[0]);raise AssertionError('Original pointer failure must reject')
    except ValueError as error:assert str(error)=='V2_ACTION_TYPE_OR_SYNTAX_REJECTED'
    assert len(counter.used)==0
    counter.prepare(e5[1]);assert len(counter.used)==1
    h=model_calls('p2-h-proposal-001')
    wrong=next(x for x in h if x['action']=='check')
    actual=next(x for x in h if x['action']=='submit' and x.get('proposal',{}).get('decision')=='propose')
    counter2=ProposalCounter('H')
    try:counter2.prepare(wrong);raise AssertionError('Wrong H/D action must reject')
    except ValueError as error:assert str(error)=='V2_ACTION_TYPE_OR_SYNTAX_REJECTED'
    assert not counter2.used
    counter2.prepare(actual);assert len(counter2.used)==1
    counter2.prepare({'action':'submit','proposal':{'decision':'no-update','reason':'finite rejection'}})
    dest=Path(__file__).parent/'adapter-v2'
    for kind in ('E5','H'):seal(dest/(kind.lower()+'-schema.json'),schema(kind))
    result={'status':'PASS','targeted_regressions':2,'source_sha256':file_hash(Path(__file__)),
        'E5_original_bad_pointer':'REJECTED_BEFORE_PROPOSAL_COUNTER',
        'E5_actual_corrected_model_call':'ONE_VALID_PROPOSAL',
        'H_original_wrong_D_check':'REJECTED_WITH_ZERO_H_PROPOSALS_USED',
        'H_actual_model_H':'ONE_VALID_H_PROPOSAL','H_no_update_at_cap':'ALLOWED',
        'syntax_rejection_cap':2,'valid_proposal_cap':1,
        'new_provider_requests':0,'new_scientific_executions':0,
        'old_protocols_and_original_failure_results_unchanged':True,
        'deployment':'New version qualification only; no in-flight or old episode modified'}
    seal(dest/'regression-result.json',result);print(json.dumps(result))


if __name__=='__main__':main()
