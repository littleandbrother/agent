"""Recover bookkeeping only after the first pre-owner entry recovery.

The SDK and provider have already finished. This never opens an endpoint or
invokes the participant. The original zero-request receipt is retained.
"""
import importlib.util
import json
from pathlib import Path
import sys

from bfworld.agentlab.campaign20261019 import abc_methods
from bfworld.agentlab.campaign20261019.phase1 import file_hash, ledger, seal

ROOT = Path('/Users/depengsu/Documents/Long-Horizon AI Agent')
APP = ROOT/'workbench/bf-campaign-s0-20261019/battery-world'
OUT = Path.home()/'.local/share/bf-abc-20261020'
episode = OUT/'episodes/C-formation-proposed'
assert not (OUT/'active-owner.lock').exists()
assert not (episode/'episode-result.json').exists()
events = [json.loads(s) for s in (episode/'gateway/gateway-events.jsonl').read_text().splitlines()]
trace = [json.loads(s) for s in (episode/'pi-public-trace.jsonl').read_text().splitlines()]
assert events[-1]['kind']=='gateway_closed'
assert not any(v['kind'] in ('episode_dispatch_stopped','model_forward_failed') for v in events)
assert trace[-1]['type']=='bf_episode_complete'
assert not (episode/'pi-stderr.log').read_text()
spec = json.loads((episode/'attempt.json').read_text())['spec']
owner = json.loads((episode/'owner.json').read_text())['owner']
database = Path.home()/'.local/share/bf-campaign-20261019-s0/workbench/state/workbench.sqlite'
account = ledger(database,owner)
assert account['requests']==6 and not account['unknown_or_missing_usage']
method = json.loads((episode/'methods/method-submission.json').read_text())
calls = [c['arguments'] for e in trace if e.get('type')=='assistant_public' for c in e['content']
         if c.get('type')=='toolCall' and c.get('name')=='bf_abc_methods']
assert any(v.get('action')=='submit_method' and v.get('proposal')==method for v in calls)
loader = importlib.util.spec_from_file_location('abc_frozen_participant_audit',APP/'scripts/campaign_phase1.py')
runner = importlib.util.module_from_spec(loader)
sys.modules[loader.name] = runner
loader.loader.exec_module(runner)
audit = runner.audit_participant(episode,'bf_abc_methods')
assert not audit['unmatched_executed_inputs']
starts = [v for v in trace if v.get('type')=='bf_episode_loaded']
assert len(starts)==1 and starts[0]['resume_messages']==0
old_cost = episode/'provider-costs.json'
assert json.loads(old_cost.read_text())['requests']==0
old_hash = file_hash(old_cost)
old_cost.rename(episode/'entry-failure-001-costs.json')
seal(episode/'provider-costs.json',account)
judgment = abc_methods.independent_check(episode,spec)
assert judgment['status']=='STRUCTURALLY_ADMITTED'
wall = events[-1]['time']-events[0]['time']
result = dict(episode='C-formation-proposed',package='methods',spec=spec,status='ACTUAL_SUBMITTED',
    wall_seconds_total=wall,accounting={k:v for k,v in account.items() if k!='rows'},
    independent_result=judgment,trace_audit=audit,fresh_context=True,reported_models=['deepseek-flash'],
    sdk_complete_trace=True,sdk_exit_code='NOT_RECORDED_BECAUSE_POST_RUN_LEDGER_RECEIPT_CONFLICT',
    native_dispatches=0,automatic_retry=False,method_raw_sha256=file_hash(episode/'methods/method-submission.json'),
    bookkeeping_recovery=dict(original_zero_cost_sha256=old_hash,old_record_retained='entry-failure-001-costs.json',
        exception='IMMUTABLE_RECEIPT_EXISTS on old pre-owner zero-request provider-costs.json',
        new_model_requests=0,new_scientific_executions=0,submission_and_usage_independently_read_back=True))
seal(episode/'episode-result.json',result)
print(json.dumps(dict(status=result['status'],requests=account['requests'],charge_upper_usd=account['settled_charge_upper_bound_usd'],
                     method_sha256=result['method_raw_sha256'],independent=judgment['status'],wall_s=wall)))
