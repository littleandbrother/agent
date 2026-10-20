#!/usr/bin/env python3
"""Frozen hybrid energy-buffer apparatus for contract/replay counterexamples.

Energy is in microjoules, power in microwatts, time in seconds. This is a
separate controlled mechanism study, not a modification of the scientific world.
"""
import hashlib
import json
import math
from pathlib import Path
import random
import time

from run import ROOT, DATA, save

VERSION = 'energy-information-feedback-pilot-v1'
COSTS = {'prefix':2, 'information':1, 'feedback':3}


def cases():
    result=[]
    for seed in range(30):
        split='development' if seed<12 else 'validation' if seed<18 else 'test'
        rng=random.Random(20261017+seed)
        scale=rng.uniform(.7,1.4)
        for family in ('energy_timing','information_window','load_feedback'):
            base={'seed':seed,'split':split,'family':family,'duration':4.,'dt':.002,
                  'emin':100*scale,'emax':1500*scale,'idle':2*scale,
                  'sample_power':100*scale,'sample_duration':.02,'tx_power':6000*scale,'tx_duration':.04,
                  'source_power':400*scale,'source_start':0.,'source_end':4.,
                  'sample_at':.8,'tx_at':.84,'event_start':0.,'event_end':4.,'coupling':0.,'initial':400*scale}
            for side in (0,1):
                c={**base,'id':f'{family}-{seed:02d}-{side}','pair_id':f'{family}-{seed:02d}'}
                if family=='energy_timing':
                    c.update(initial=110*scale,source_start=.1 if side==0 else 2.,source_end=.7 if side==0 else 2.6,
                             source_power=800*scale)
                elif family=='information_window':
                    c.update(event_start=.5 if side==0 else 1.5,event_end=1.2 if side==0 else 2.2)
                else:
                    # Both have a small positive ideal prefix margin; feedback
                    # removes source power while the load is active.
                    c.update(sample_at=.2,tx_at=.24,source_power=400*scale,coupling=0. if side==0 else .95)
                    consumed=(c['tx_power']*c['tx_duration']+c['sample_power']*c['sample_duration']+
                              c['idle']*(c['tx_at']+c['tx_duration']-c['sample_duration']-c['tx_duration']))
                    supplied=c['source_power']*(c['tx_at']+c['tx_duration'])
                    c['initial']=c['emin']+consumed-supplied+8*scale
                result.append(c)
    return result


def planned(c):
    return [(c['sample_at'],c['sample_at']+c['sample_duration'],'sample'),
            (c['tx_at'],c['tx_at']+c['tx_duration'],'tx')]


def run(c, policy=None, frozen=None, source_trace=None, dt=None):
    dt=dt or c['dt']; steps=round(c['duration']/dt)
    events=planned(c) if policy is None else []
    e=c['initial']; minimum=e; trace=[]; active=None; packets=[]; sample=None
    due=(policy or {}).get('start',.6); seq=0; busy_until=-1.; scope_work=0
    for i in range(steps):
        t=round(i*dt,10)
        perceived=frozen[min(round(t/c['dt']),len(frozen)-1)]['energy'] if frozen is not None else e
        if policy and t+1e-9>=due and t>=busy_until-1e-9:
            due=round(due+policy['interval'],10)
            if perceived>=(policy.get('threshold') or 0):
                seq+=1;st=t;tx=st+c['sample_duration']+.02;end=tx+c['tx_duration']
                if end<=c['duration']:
                    events.extend([(st,st+c['sample_duration'],'sample'),(tx,end,'tx')]);busy_until=end
        now=next(((start,end,state) for start,end,state in events if start-1e-9<=t<end-1e-9),None)
        if now!=active:
            if active and active[2]=='tx': packets[-1]['end_energy']=perceived
            active=now
            if active and active[2]=='sample': sample={'at':t,'valid':c['event_start']<=t<=c['event_end'],'powered':True}
            if active and active[2]=='tx': packets.append({'at':t,'powered':True,'sample_valid':bool(sample and sample['valid'] and sample['powered'])})
        load=c['idle'] if active is None else c[active[2]+'_power']
        if source_trace is None:
            incoming=c['source_power'] if c['source_start']-1e-9<=t<c['source_end']-1e-9 else 0.
            scope_work+=1
        else: incoming=source_trace[i]
        incoming*=1-c['coupling'] if active else 1
        next_e=max(0.,min(c['emax'],e+(incoming-load)*dt))
        actual_min=min(e,next_e) if frozen is None else min(perceived,frozen[min(round((t+dt)/c['dt']),len(frozen)-1)]['energy'])
        if active and actual_min<c['emin']-1e-6:
            if active[2]=='sample': sample['powered']=False
            if active[2]=='tx': packets[-1]['powered']=False
        trace.append({'t':t,'energy':e,'load':load,'source':incoming})
        e=next_e;minimum=min(minimum,e);scope_work+=1
    valid=sum(p['powered'] and p['sample_valid'] for p in packets)
    return {'success':bool(valid>=1),'valid_packets':valid,'attempted_packets':len(packets),'minimum_energy':minimum,
            'final_energy':e,'packets':packets,'trace':trace,'work_units':scope_work}


def static_interface(c):
    return {'nominal_input_uJ':round(c['source_power']*(c['source_end']-c['source_start']),8),
        'initial_uJ':c['initial'],'minimum_uJ':c['emin'],'rail_v':2.5,
        'peak_current_a':c['tx_power']*1e-6/2.5,'payload_bytes':8,
        'task_uJ':c['sample_duration']*c['sample_power']+c['tx_duration']*c['tx_power'],
        'idle_uJ':c['idle']*(c['duration']-c['sample_duration']-c['tx_duration'])}


def observations(c):
    # Closed-form prefix accounting of the declared piecewise constant inputs.
    # No evaluator result, label or simulated trace is read.
    edges=sorted({0.,c['duration'],c['source_start'],c['source_end'],*[x for a,b,_ in planned(c) for x in (a,b)]})
    e=c['initial'];min_active=math.inf;loss=0.
    for a,b in zip(edges,edges[1:]):
        t=(a+b)/2;state=next((s for lo,hi,s in planned(c) if lo<=t<hi),None)
        source=c['source_power'] if c['source_start']<=t<c['source_end'] else 0.
        load=c[state+'_power'] if state else c['idle']
        before=e;e=min(c['emax'],max(0,e+(source-load)*(b-a)))
        if state:
            min_active=min(min_active,before,e)
            loss+=source*c['coupling']*(b-a)
    return {'prefix':min_active-c['emin'],'information':min(c['sample_at']-c['event_start'],c['event_end']-c['sample_at']),
            'feedback':loss}


def predict(c, features, abstain=False):
    s=static_interface(c);margin=s['initial_uJ']+s['nominal_input_uJ']-s['task_uJ']-s['idle_uJ']-s['minimum_uJ']
    o=observations(c)
    if abstain and not features:return None
    if 'prefix' in features: margin=o['prefix']
    if 'feedback' in features: margin-=o['feedback']
    return margin>=-1e-6 and ('information' not in features or o['information']>=0)


def refine(training):
    pairs={}
    for row in training:pairs.setdefault(row['case']['pair_id'],[]).append(row)
    counterexamples=[rows for rows in pairs.values() if len(rows)==2 and rows[0]['truth']!=rows[1]['truth'] and static_interface(rows[0]['case'])==static_interface(rows[1]['case'])]
    uncovered=list(range(len(counterexamples)));selected=[];history=[]
    while uncovered:
        scores={f:[i for i in uncovered if abs(observations(counterexamples[i][0]['case'])[f]-observations(counterexamples[i][1]['case'])[f])>1e-7]
                for f in COSTS if f not in selected}
        chosen=max(scores,key=lambda f:(len(scores[f])/COSTS[f],f));cover=scores[chosen]
        if not cover:break
        selected.append(chosen);uncovered=[i for i in uncovered if i not in cover]
        history.append({'feature':chosen,'cost':COSTS[chosen],'pairs_separated':len(cover),'remaining':len(uncovered)})
    return selected,history,len(counterexamples)


def metrics(rows, predictions):
    tp=tn=fp=fn=unknown=0
    for r,p in zip(rows,predictions):
        y=r['truth']
        if p is None:unknown+=1
        elif p and y:tp+=1
        elif p:fp+=1
        elif y:fn+=1
        else:tn+=1
    return {'n':len(rows),'true_accept':tp,'true_reject':tn,'false_accept':fp,'false_reject':fn,'unknown':unknown,
            'coverage':(len(rows)-unknown)/len(rows),'accuracy_all':(tp+tn)/len(rows)}


def main():
    folder=ROOT/'mechanisms';inputs=cases()
    freeze={'version':VERSION,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'cases_sha256':hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest(),'costs':COSTS,
        'partitions':{'development':72,'validation':36,'test':72},'study_unit':'parameterized scenario; sides are paired counterexamples',
        'methods':['static-budget','static-rich','fixed-event-contract','counterexample-refinement','abstain-on-ambiguity'],
        'controls':['zero energy','ample energy','zero feedback','same policy replay','fine step invariance'],
        'interpretation':'Controlled constructed counterexamples; test scenarios use independent seeds, same three mechanism families.'}
    save(folder/'freeze.json',freeze);save(folder/'inputs.json',inputs)
    rows=[]
    for c in inputs:
        path=folder/'runs'/f"{c['id']}.json"
        if path.exists():out=json.loads(path.read_text())
        else:
            started=time.perf_counter();out=run(c);out['elapsed_s']=time.perf_counter()-started;save(path,out)
        rows.append({'case':c,'truth':out['success'],'observations':observations(c)})
    training=[r for r in rows if r['case']['split']=='development']
    features,history,count=refine(training)
    save(folder/'refinement.json',{'selected':features,'history':history,'contradictory_pairs':count,'training_ids':[r['case']['id'] for r in training]})
    tables={}
    for split in ('development','validation','test'):
        subset=[r for r in rows if r['case']['split']==split]
        methods={'static-budget':[],'static-rich':[],'fixed-event-contract':list(COSTS),'counterexample-refinement':features}
        tables[split]={name:{**metrics(subset,[predict(r['case'],fs) for r in subset]),'feature_cost':1+sum(COSTS[f] for f in fs)} for name,fs in methods.items()}
        tables[split]['abstain-on-ambiguity']={**metrics(subset,[None]*len(subset)),'feature_cost':1}
    # Replay experiment: a changed policy must consume a responding power state.
    replays=[]
    for seed in range(30):
        rng=random.Random(7000+seed);scale=rng.uniform(.8,1.2)
        c={**inputs[seed*6], 'id':f'replay-{seed}', 'initial':400*scale,'emin':100*scale,'emax':1500*scale,
           'source_start':0.,'source_end':4.,'source_power':160*scale,'sample_power':100*scale,'tx_power':6000*scale,'idle':2*scale,
           'event_start':0.,'event_end':4.,'coupling':.2 if seed%2 else 0.}
        parent={'start':.6,'interval':2.,'threshold':0.}
        child={'start':.6,'interval':.4,'threshold':0.}
        safe={'start':.6,'interval':.4,'threshold':c['emin']+c['tx_power']*c['tx_duration']+10*scale}
        old=run(c,parent);full=run(c,child);naive=run(c,child,frozen=old['trace'])
        source=[c['source_power']]*len(old['trace'])
        # A feedback edge forces the source into the affected component closure.
        scoped=run(c,child,source_trace=source if c['coupling']==0 else None)
        cautious=run(c,safe)
        same=run(c,parent,frozen=old['trace'])
        fine=run(c,child,dt=.001)
        record={'id':c['id'],'seed':seed,'split':c['split'],'feedback':bool(c['coupling']),
            'parent_packets':old['valid_packets'],'child_full':full['valid_packets'],'child_frozen':naive['valid_packets'],
            'child_scoped':scoped['valid_packets'],'safe_child':cautious['valid_packets'],
            'scope':['power','firmware','receiver']+(['source'] if c['coupling'] else []),
            'full_work':full['work_units'],'scoped_work':scoped['work_units'],
            'same_policy_equal':same['valid_packets']==old['valid_packets'],
            'fine_step_equal':fine['valid_packets']==full['valid_packets'],
            'scoped_energy_error':abs(scoped['final_energy']-full['final_energy'])}
        replays.append(record)
        save(folder/'replay'/f"{c['id']}.json",{'case':c,'policies':{'parent':parent,'child':child,'energy_gated':safe},'result':record,
            'full_trace':full['trace'],'old_trace':old['trace']})
    controls={'same_policy':all(r['same_policy_equal'] for r in replays),'time_step':all(r['fine_step_equal'] for r in replays),
              'scoped_equals_full':all(r['child_scoped']==r['child_full'] and r['scoped_energy_error']<1e-8 for r in replays)}
    if not all(controls.values()): raise ValueError('MECHANISM_CONTROL_FAILED:'+str(controls))
    save(folder/'result.json',{'freeze':freeze,'tables':tables,'refinement':history,'replay':replays,'controls':controls,
        'aliasing_pairs':sum(rows[i]['truth']!=rows[i+1]['truth'] and static_interface(rows[i]['case'])==static_interface(rows[i+1]['case']) for i in range(0,len(rows),2)),
        'native_simulations':0,'apparatus':'deterministic energy-buffer simulation','physical_measurements':0})
    print(json.dumps({'tables':tables,'controls':controls,'replay_disagreement':sum(r['child_frozen']!=r['child_full'] for r in replays)},ensure_ascii=False))


if __name__=='__main__':main()
