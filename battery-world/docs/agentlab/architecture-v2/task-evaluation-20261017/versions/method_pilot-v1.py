#!/usr/bin/env python3
"""Small generated-method pilot, with development feedback and sealed selection.

This tests learning a contract/replay configuration. It does not alter a device
or the evaluator, and does not claim that the improver itself has evolved.
"""
import json
from pathlib import Path

from run import ROOT, model_call, parse_json, save
from mechanisms import COSTS, observations, static_interface, metrics, predict, run


def evaluate(config, rows, replays):
    contract=metrics(rows,[predict(r['case'],config['features']) for r in rows])
    work=0; disagreements=0; errors=[]
    for r in replays:
        c=r['case'];old=r['old_trace'];child=r['policies']['child'];truth=r['result']
        if config['replay']=='frozen':
            count=truth['child_frozen'];error=None;units=len(old)
        elif config['replay']=='full' or config['replay']=='causal' and c['coupling']:
            count=truth['child_full'];error=0.;units=truth['full_work']
        else:
            # Cached old source response is invalid if a changed load affects it.
            output=run({**c,'coupling':0.},child,source_trace=[x['source'] for x in old])
            count=output['valid_packets'];units=output['work_units']
            error=abs(output['final_energy']-(r['full_trace'][-1]['energy']+
                (r['full_trace'][-1]['source']-r['full_trace'][-1]['load'])*c['dt']))
        disagreements+=int((count>truth['parent_packets'])!=(truth['child_full']>truth['parent_packets']))
        errors.append(error);work+=units
    return {'contract':contract,'feature_cost':1+sum(COSTS[f] for f in config['features']),
        'replay_rank_errors':disagreements,'replay_n':len(replays),'work_units':work,
        'response_max_energy_error_uJ':max([e for e in errors if e is not None],default=None)}


def main():
    folder=ROOT/'method-pilot'
    inputs=json.loads((ROOT/'mechanisms/inputs.json').read_text())
    rows=[{'case':c,'truth':json.loads((ROOT/'mechanisms/runs'/f"{c['id']}.json").read_text())['success']} for c in inputs]
    replays=[json.loads(p.read_text()) for p in sorted((ROOT/'mechanisms/replay').glob('*.json'))]
    split=lambda name:[r for r in rows if r['case']['split']==name]
    replay_split=lambda name:[r for r in replays if r['case']['split']==name]
    save(folder/'protocol.json',{'version':'generated-contract-replay-config-v1','rounds':2,'independent_chains':3,
        'allowed_changes':['interface feature set','replay boundary rule'],'fixed':['case inputs','truth evaluator','feature implementations'],
        'selection':'validation errors, then response error, then feature and operation cost; final test evaluated after selection',
        'test_exposure':'proposal model never receives test or validation outcomes; operator has seen controlled pilot aggregates',
        'scope':'three known mechanism families with new parameter seeds; not new-task or recursive-improver evidence'})
    training={'cases':[{'inputs':static_interface(r['case']),'available_observations':observations(r['case']),
        'service_passed':r['truth'],'mechanism':r['case']['family']} for r in split('development')[:24]],
        'replay_examples':[{'feedback':r['result']['feedback'],'parent_packets':r['result']['parent_packets'],
            'changed_policy_full':r['result']['child_full'],'changed_policy_old_supply':r['result']['child_frozen']} for r in replay_split('development')[:4]]}
    system=('Propose a reusable assessment-method configuration, not a device change. Return one JSON object '
        '{"features":[...],"replay":"...","reason":"..."}. '
        'Features: prefix (event energy margin; cost 2), information (sample-window margin; cost 1), '
        'feedback (source energy lost due to active load; cost 3). Static budget has base cost 1. '
        'Replay choices: frozen (old supply trajectory), power_only (recompute energy/load using old source response), '
        'causal (include source whenever it responds to the changed load), full (always recompute source and energy). '
        'Minimize wrong accept/reject and wrong ranking of a proposed program change; preserve response accuracy then reduce cost. '
        'No prose outside JSON. You may select any subset; give a short reason.')
    candidates=[]
    for chain in range(3):
        feedback=None
        for generation in range(2):
            raw=model_call(f'method-chain{chain}-g{generation}',system,json.dumps({'chain':chain,'training':training,'prior_feedback':feedback},ensure_ascii=False),2200)
            try:
                config=parse_json(raw)
                if set(config)!= {'features','replay','reason'} or not isinstance(config['features'],list) or len(set(config['features']))!=len(config['features']) or any(f not in COSTS for f in config['features']) or config['replay'] not in ('frozen','power_only','causal','full'):
                    raise ValueError('CONFIG_SCHEMA')
                scored=evaluate(config,split('development'),replay_split('development'))
                feedback={'configuration':config,'development_result':scored}
                row={'chain':chain,'generation':generation,'configuration':config,'development':scored}
                row['validation']=evaluate(config,split('validation'),replay_split('validation'))
            except (ValueError,TypeError) as error:
                row={'chain':chain,'generation':generation,'error':str(error)};feedback={'error':str(error)}
            save(folder/f'candidate-{chain}-{generation}.json',row);candidates.append(row)
    def score(r):
        v=r['validation']; c=v['contract']
        return (c['false_accept']+c['false_reject']+c['unknown']+v['replay_rank_errors'],
                v['response_max_energy_error_uJ'] if v['response_max_energy_error_uJ'] is not None else 1e30,
                v['feature_cost']+v['work_units']/1000)
    eligible=[r for r in candidates if 'configuration' in r]
    if not eligible:raise ValueError('NO_VALID_METHOD_CANDIDATE')
    selected=min(eligible,key=score)
    save(folder/'selection.json',{'chain':selected['chain'],'generation':selected['generation'],
        'configuration':selected['configuration'],'validation':selected['validation']})
    baselines={'fixed-static-frozen':{'features':[],'replay':'frozen'},
        'fixed-rich-full':{'features':list(COSTS),'replay':'full'},
        'fixed-rich-causal':{'features':list(COSTS),'replay':'causal'},'selected':selected['configuration']}
    results={k:evaluate(v,split('test'),replay_split('test')) for k,v in baselines.items()}
    save(folder/'result.json',{'candidates':candidates,'test':results,'selection':selected['configuration'],
        'recursive_improver_tested':False,'source_simulations_reused':True})
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':main()
