"""Bind actual model/physical/source receipts and independently reject promotion."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[4]
APP=ROOT/'workbench/bf-campaign-s0-20261019/battery-world'
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.campaign20261019.common import digest,file_hash,seal
from bfworld.agentlab.campaign20261019 import phase2_methods as methods

OUT=Path('/Users/depengsu/.local/share/bf-phase2-20261020')


def load(path):return json.loads(Path(path).read_text())


def record(episode, kind):
    root=OUT/episode;episode_result=load(root/'episode-result.json');costs=load(root/'provider-costs.json')
    trace=[json.loads(x) for x in (root/'pi-public-trace.jsonl').read_text().splitlines()]
    loaded=next(x for x in trace if x.get('type')=='bf_episode_loaded')
    rows=costs['rows']
    common={'evidence_kind':'ACTUAL_PROVIDER','externally_verified':True,
        'decision_trace_sha256':file_hash(root/'pi-public-trace.jsonl'),
        'usage_status':'SETTLED' if all(x['status']=='SETTLED' for x in rows) else 'UNKNOWN',
        'provider_request_ids':[x['id'] for x in rows],'costs_complete':not costs['unknown_or_missing_usage'],
        'owner':episode_result['owner'],'episode_id':episode,
        'context_id':Path((root/'participant/.pi/phase1-session-path').read_text().strip()).name,
        'source_scope':'public-development','actual_tool_inputs_bound':not episode_result['trace_audit']['unmatched_executed_inputs']}
    if kind=='method-proposal':
        method=load(root/'external/method.json')
        return {**common,'proposal_sha256':digest(method['proposal']),'semantic_artifact':'H',
            'method_author':'participant-model','qualification_kind':method['qualification_kind'],
            'original_live_submission_success':False}
    external=load(root/'external/result.json');execution=external['execution'];protocol=load(root/'protocol.json')
    acquired={p.stem:load(p)['source_sha256'] for p in (root/'scientific/acquisitions').glob('*.json')}
    raw_input=load(Path(execution['raw_path']).parent/'input.json')
    initial=load(OUT/'p2-h0-design-001/scientific/acquisitions/component_record.json')['payload']
    raw_input['device']=initial
    method=load(OUT/'p2-h-proposal-001/external/method.json')
    return {**common,'task_sha256':digest(raw_input),'sources_sha256':digest(acquired),
        'information_sha256':digest(acquired),'model_sha256':digest({'alias':'deepseek-flash','provider':protocol['provider_service'],'thinking':'high'}),
        'tools_sha256':protocol['tool']['sha256'],'evaluator_sha256':file_hash(APP/'scripts/campaign_reference.py'),
        'initial_cache_sha256':None, # Not frozen at entry; never manufacture parity.
        'initial_cache_boundary':'Physical shared exact-input cache evolved; initial snapshot parity not established',
        'start_stage':'task-entry','initial_decision_messages':loaded['resume_messages'],
        'execution_input_sha256':execution['input_sha256'],'evaluation_input_sha256':execution['input_sha256'],
        'independent_complete_service':True,'feedback_scope_verified':execution['origin']=='new-full-feedback-response',
        'service_status':execution['complete_service'],
        'method_sha256':method['proposal']['method_sha256'] if kind=='Hprime-design' else digest(loaded['core']),
        'design':execution['design'],'first_receive_s':execution['reference']['first_receive_s']}


def main():
    records={k:record(ep,k) for k,ep in [('method-proposal','p2-h-proposal-001'),
            ('H0-design','p2-h0-design-001'),('Hprime-design','p2-hprime-design-001')]}
    actual=load(OUT/'p2-h-proposal-001/external/method.json')
    identifiers={k:digest(v) for k,v in records.items()}
    def resolve(kind,identity):
        if identifiers[kind]!=identity:raise ValueError('UNREGISTERED_EXTERNAL_RECEIPT')
        return records[kind]
    gate=methods.confirmation_gate(actual['raw_proposal'],proposal_receipt_id=identifiers['method-proposal'],
        h0_receipt_id=identifiers['H0-design'],hprime_receipt_id=identifiers['Hprime-design'],resolve_receipt=resolve)
    accounts={p.name:load(p/'provider-costs.json') for p in OUT.glob('p2-*') if (p/'provider-costs.json').exists()}
    decision={'status':'REJECT_PROMOTION_KEEP_EXPERIMENTAL_ARTIFACT','retained':False,
        'automatic_H_text_source':'ACTUAL_MODEL_WITH_POSTHOC_HOST_ADAPTER_REEVALUATION',
        'actual_H0_service':records['H0-design']['service_status'],
        'actual_Hprime_service':records['Hprime-design']['service_status'],
        'actual_H0':records['H0-design']['design'],'actual_Hprime':records['Hprime-design']['design'],
        'gate':gate,'ordered_state_audit':str(OUT/'ordered-state-audit.json'),
        'reasons':['Original method proposal episode was blocked by host-action contract; posthoc use is not original live success.',
                   'H0 already met the frozen complete service; this single pair does not demonstrate more successful designs.',
                   'Improver plus Hprime costs exceed H0 design cost; no same-total-budget advantage established.',
                   'Initial physical cache parity was not frozen; descriptive case outcomes are not a causal method comparison.',
                   'Method language over-restricts first-pulse/capacitance requirements relative to actual passing H0.'],
        'h0_charge_upper_usd':accounts['p2-h0-design-001']['settled_charge_upper_bound_usd'],
        'improver_plus_hprime_charge_upper_usd':accounts['p2-h-proposal-001']['settled_charge_upper_bound_usd']+accounts['p2-hprime-design-001']['settled_charge_upper_bound_usd'],
        'default_H_changed':False,'new_provider_requests':0,'new_scientific_executions':0,
        'no_transfer_RSI_hardware_claim':True}
    seal(OUT/'method-external-registry.json',{'records':records,'identifiers':identifiers})
    seal(OUT/'method-retain-or-reject.json',decision)
    summary={'status':'FINITE_PHASE2_RESULTS_READY_WITH_ORIGINAL_FAILURES_AND_POSTHOC_BOUNDARIES',
        'actual_episodes':{p.name:load(p/'episode-result.json') for p in OUT.glob('p2-*') if (p/'episode-result.json').exists()},
        'e5_original_result':str(OUT/'p2-e5-001/external/result.json'),
        'e5_posthoc_real_consumer_result':str(OUT/'p2-e5-001/posthoc-adapter-001/result.json'),
        'method_retention':decision,'provider_requests':sum(a['requests'] for a in accounts.values()),
        'settled_charge_upper_bound_usd':sum(a['settled_charge_upper_bound_usd'] for a in accounts.values()),
        'cache_aware_rate_estimate_usd':sum(a['cache_aware_rate_estimate_usd'] for a in accounts.values()),
        'unresolved_usage':[x for a in accounts.values() for x in a['unknown_or_missing_usage']],
        'new_scientific_executions':sum(x['origin']=='new-full-feedback-response' for x in load(OUT/'cases/index.json').values()),
        'wall_seconds':sum(load(p/'episode-result.json')['wall_seconds_total'] for p in OUT.glob('p2-*') if (p/'episode-result.json').exists()),
        'native_calls':0,'old_failure_results_preserved':True,'product_AR':'UNCHANGED_NO_GO_FIFO_FAIL_NOT_ACCEPTED'}
    seal(OUT/'actual-results.json',summary)
    print(json.dumps({'status':summary['status'],'requests':summary['provider_requests'],'upper_usd':summary['settled_charge_upper_bound_usd'],
        'new_scientific_executions':summary['new_scientific_executions'],'method_decision':decision['status'],'gate':gate},ensure_ascii=False))


if __name__=='__main__':main()
