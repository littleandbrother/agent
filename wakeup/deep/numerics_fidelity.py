"""Two numerical-attribution and two actual multi-fidelity probes; no model client."""
import copy
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_limits import BASE, DEFAULT, DOMAIN, bounds, oracle, passed, public_spec, scalar
from sim import TASK, simulate

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'boundary'
CAL = json.loads((OLD / 'calibration.json').read_text())['workpoints']
CACHE = {}
for old in json.loads((OLD / 'transient.json').read_text()):
    a = old['transient']
    CACHE[json.dumps([a['design'], a['task']], sort_keys=True)] = a


def tasks():
    out = []
    domain = {k: [v[0], v[1]] for k, v in DOMAIN.items()} | {k: [False, True] for k in 'ABCD'}
    for case in ('wake', 'impact'):
        t = next(r['task'] for r in CAL if r['task']['id'] == case+'-D3')
        out.append(dict(id='P5-'+case+'-narrow', axis=5,
            description='Separate an unsuccessful numerical point from rejection of its module combination.',
            initial=DEFAULT.copy(), domain=domain.copy(), spec=public_spec() | dict(environment={k:v for k,v in t.items() if k not in ('id','difficulty')}),
            diagnostic='One failed parameter vector does not exclude its module combination. A bounded numerical search is not an infeasibility certificate.',
            _private=dict(task=t), fidelity='harmonic-only'))
    s = json.loads((OLD/'summary.json').read_text())['results']
    wake = next(r['final_design'] for r in s if r['task']=='wake-D2' and r['visibility']=='I0' and r['arm']=='All-Open')
    for case, initial, name in [('wake', dict(wake, envelope_discharge_Mohm=10000., wake_low_ratio=.33), 'envelope-reset'),
                               ('impact', dict(next(r for r in CAL if r['task']['id']=='impact-D2')['witnesses']['D'], envelope_discharge_Mohm=20., wake_low_ratio=.33), 'impact-transfer')]:
        t = next(r['task'] for r in CAL if r['task']['id'] == case+'-D2')
        spec = public_spec() | dict(environment={k:v for k,v in t.items() if k not in ('id','difficulty')},envelope_capacitance_nF=2.,
            extra_parameters={'envelope_discharge_Mohm':'actual envelope discharge resistance', 'wake_low_ratio':'rearm threshold / wake threshold'},
            full_requirements='Two events six seconds apart; real 128-point classification; ACK within 250ms; no false reports/brownouts; travel<=1.5mm and declared stress limit.',
            fidelity_difference='Fast: settled peak-triggered equivalent shunt. Full: voltage-dependent dissipative shunt, rectifier and envelope dynamics. These models are not identical.')
        out.append(dict(id='P6-'+name, axis=6,
            description='Use sparse full execution to challenge a settled-harmonic prediction; original exposed development designs, not unseen tasks.',
            initial=initial, domain=domain | dict(envelope_discharge_Mohm=[.1, 10000.], wake_low_ratio=[.05, .9]),
            spec=spec, diagnostic='Steady energy and stress do not certify envelope rearming, displacement, classification or delivery deadlines.',
            _private=dict(task=t), fidelity='fast/full'))
    return out


def _harmonic(task, design):
    a = scalar(oracle(task['_private']['task'], design))
    return dict(pass_=bool(passed(a)), slack=a.pop('slack'), metrics=a,
                cost=dict(full=0, numeric=1), fidelity='harmonic')


def _physical(task, x):
    t = task['_private']['task'];d = copy.deepcopy(BASE)
    d['harvester'] |= dict(substrate_mm=.15*x['h'], piezo_layer_mm=.12*x['h'], tip_mass_g=x['mass_g'])
    d['trigger_beam'] |= dict(length_mm=x['L2_mm'], tip_mass_g=x['m2_g'])
    d['modules'] = {k:x[k] for k in 'ABCD'}
    d['circuit'] |= dict(storage_uF=x['C_uF'], start_V=x['gate_V'], wake_high_V=x['trigger_V'],
        wake_low_V=x['trigger_V']*x.get('wake_low_ratio',.33), converter_input_R_ohm=x['R_kohm']*1000,
        shunt_ohm=x['shunt_kohm']*1000, shunt_threshold_V=x['shield_V'],
        envelope_discharge_ohm=x.get('envelope_discharge_Mohm',20.)*1e6)
    d['firmware']['poll_s']=x['poll_ms']/1000
    z=dict(TASK, background_peak_g=t['background_g'], fault_Hz=t['event_Hz'], fault_peak_g=t['event_g'],
        fault_duration_s=t['event_ms']/1000, stress_limit_MPa=t['stress_MPa'],
        fault_starts_s=[t['ready_s'],t['ready_s']+6], duration_s=t['ready_s']+7.5, nuisance_starts_s=[t['ready_s']+3])
    if t['case']=='impact':
        d['firmware'] |= dict(target_band_Hz=[35,55], minimum_target_rms_g=1., wake_from_harvester=True)
        d['circuit'] |= dict(wake_high_V=x['gate_V']+.3, wake_low_V=(x['gate_V']+.3)*x.get('wake_low_ratio',.33))
        z |= dict(nuisance_Hz=75., nuisance_peak_g=2.)
    return d,z


def evaluate(task, design, fidelity='full', observation=None):
    if task['axis']==5 or fidelity in ('fast','harmonic'):
        return _harmonic(task,design)
    qualified=HERE/'numerics_fidelity_qualification.json'
    if observation is None and qualified.exists():
        for q in json.loads(qualified.read_text())['records']:
            if q.get('task')==task['id'] and q.get('design')==design and q['result'].get('fidelity')=='full':
                r=copy.deepcopy(q['result']);r['cost']['full']=0;r['metrics']['reused']=True;return r
    d,z=_physical(task,design);key=json.dumps([d,z],sort_keys=True);reused=key in CACHE
    if not reused:
        a=simulate(d,z);a.pop('trace');CACHE[key]=a
    a=CACHE[key];m=a['metrics']
    area=20+.03*design['C_uF']+sum(design[k]*v for k,v in dict(A=15,B=18,C=40,D=12).items())
    slack=dict(delivery=m['delivered_on_time']/m['faults']-1, false_reports=-m['false_reports'],
        brownouts=-m['brownouts'], stress=1-m['peak_stress_MPa']/z['stress_limit_MPa'],
        travel=1-m['peak_tip_mm']/z['tip_travel_limit_mm'], area=1-area/task['_private']['task']['area_mm2'])
    metrics=dict(m, checks=a['checks'], runtime_s=a['runtime_s'], reused=reused)
    if observation in ('power','trigger','program'):
        metrics['events']=[{k:v for k,v in e.items() if k!='samples_g'} for e in a['events']]
        metrics['energy']=a['energy_J']
    return dict(pass_=a['verdict']=='PASS' and slack['area']>=0,slack=slack,metrics=metrics,
                cost=dict(full=0 if reused else 1,numeric=0),fidelity='full')


def optimize(task, design, variables, budget=50):
    """Bounded normalized SLSQP violation search; best FOUND point, not a maximum/proof."""
    keys=[k for k in variables if k in DOMAIN];best=copy.deepcopy(design);best_result=_harmonic(task,best);calls=1
    score=min(best_result['slack'].values())
    def encode(x):
        return [(np.log(x[k]/DOMAIN[k][0])/np.log(DOMAIN[k][1]/DOMAIN[k][0]) if DOMAIN[k][2]=='log' else (x[k]-DOMAIN[k][0])/(DOMAIN[k][1]-DOMAIN[k][0])) for k in keys]
    def decode(u):
        x=design.copy()
        for k,v in zip(keys,u):
            lo,hi,scale=DOMAIN[k];x[k]=float(lo*(hi/lo)**v if scale=='log' else lo+v*(hi-lo))
        return x
    def objective(u):
        nonlocal best,best_result,score,calls
        if calls>=budget:raise StopIteration
        x=decode(u);r=_harmonic(task,x);calls+=1;s=min(r['slack'].values())
        if s>score:best,best_result,score=x,r,s
        return sum(min(v,0)**2 for v in r['slack'].values())
    if keys and budget>1:
        try:minimize(objective,encode(design),method='SLSQP',bounds=[(0,1)]*len(keys),options=dict(maxiter=budget,ftol=1e-12))
        except StopIteration:pass
    best_result['cost']=dict(full=0,numeric=calls)
    return dict(design=best,result=best_result,evaluations=calls,proves_infeasibility=False,
                explanation='Best observed point in a bounded local search, not a theoretical limit or a certified empty subspace.')


if __name__=='__main__':
    selected=tasks();prior=HERE/'numerics_fidelity_qualification.json'
    records=[r for r in json.loads(prior.read_text())['records'] if r['kind']=='50-call-local-search'] if prior.exists() else []
    for t in selected:
        a=evaluate(t,t['initial'],fidelity='fast');records.append(dict(task=t['id'],kind='initial-fast',design=t['initial'],result=a))
    t=next(t for t in selected if t['id']=='P6-envelope-reset')
    for label,x in [('slow',t['initial']),('discharge-restored',dict(t['initial'],envelope_discharge_Mohm=20.))]:
        records.append(dict(task=t['id'],kind=label,design=x,result=evaluate(t,x)))
    t=next(t for t in selected if t['id']=='P6-impact-transfer')
    records.append(dict(task=t['id'],kind='exposed-physical-reference',design=t['initial'],result=evaluate(t,t['initial'])))
    for t in selected[:2]:
        x=dict(t['initial'],A=t['_private']['task']['case']=='wake',D=t['_private']['task']['case']=='impact')
        records.append(dict(task=t['id'],kind='50-call-SLSQP',result=optimize(t,x,['C_uF','R_kohm','h','mass_g','gate_V','shunt_kohm'],50)))
        case=t['_private']['task']['case']
        old=json.loads((OLD/'summary.json').read_text())['results']
        witness=next(z['final_design'] for z in old if z['task']=='wake-D3' and z['pass_']) if case=='wake' else next(r for r in CAL if r['task']['id']=='impact-D3')['post_run_private_reference']['design']
        records.append(dict(task=t['id'],kind='private-known-feasible-not-sent-to-model',design=witness,result=evaluate(t,witness,'fast')))
    (HERE/'numerics_fidelity_qualification.json').write_text(json.dumps(dict(records=records,boundary='Actual reduced-order harmonic/ODE calculations; no model calls, no optimizer optimality claim.'),indent=2))
    for r in records:
        z=r['result'];print(r['task'],r['kind'],z.get('pass_',z.get('result',{}).get('pass_')),z.get('metrics',{}))
