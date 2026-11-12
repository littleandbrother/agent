"""E3: footprint-constrained architecture and loaded-transient proxy calibration."""
import copy
import json
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from scipy.optimize import minimize_scalar
from common import baseline, run, response, TASK, OUT


DOMAIN={'harvester.length_mm':[24.,42.],'harvester.tip_mass_g':[2.,7.],
    'trigger_beam.length_mm':[11.,24.],'trigger_beam.tip_mass_g':[.04,.6],
    'circuit.storage_uF':[80.,1000.],'circuit.start_V':[1.9,3.2],
    'circuit.converter_input_R_ohm':[1000.,1000000.],'circuit.bridge_series_ohm':[1000.,1000000.],
    'circuit.wake_high_V':[.100001,3.2],'circuit.wake_low_V':[.1,3.199999],
    'firmware.poll_s':[.05,30.],'circuit.shunt_ohm':[1000.,1000000.],
    'circuit.shunt_threshold_V':[.3,20.]}
BRANCHES={'supply':['direct','regulated'],'mcu_gate':['poll','envelope'],
    'detector_without_A':['none','harvester'],'modules':list('ABCD'),
    'readout_charge_ohm':[100000.,100000000.]}

SEARCH_BOUNDS=[(0,3),(24,42),(2,7),(3,6),(1.90309,3),(1.9,3.2),
               (-1.30103,1.477121),(.100001,3.2),(.01,.999999),(0,1),(3,6),(.3,20),(0,1),(0,1)]


def single_trial(x,row,label):
    """One original-consumer counterexample trial, including all four branches."""
    d=copy.deepcopy(row['witness'] if 'witness' in row else row['design'])
    t=row['task']
    arm=row.get('search_arms',[0,1,2,3])[int(round(x[0]))];envelope=arm%2==1;direct=arm>=2
    d['modules'].update(A=False,D=bool(round(x[9])),B=bool(round(x[12])),C=bool(round(x[13])))
    d['connections']={'detector_source':'harvester' if envelope else 'none','mcu_gate':'envelope' if envelope else 'poll'}
    d['harvester'].update(length_mm=float(x[1]),tip_mass_g=float(x[2]))
    c=d['circuit'];c.update(storage_uF=10**float(x[4]),start_V=float(x[5]),envelope_charge_ohm=row.get('search_readout_charge_ohm',100e6),
        wake_high_V=float(x[7]),wake_low_V=max(.1,float(x[7])*float(x[8])),shunt_ohm=10**float(x[10]),shunt_threshold_V=float(x[11]))
    if direct:c.pop('converter_input_R_ohm',None);c['bridge_series_ohm']=10**float(x[3])
    else:c['converter_input_R_ohm']=10**float(x[3])
    d['firmware']['poll_s']=10**float(x[6])
    prefix=copy.deepcopy(t);prefix['duration_s']=t['fault_starts_s'][0]+t['delivery_deadline_s']
    for key in ('fault_starts_s','nuisance_starts_s'):prefix[key]=[v for v in prefix[key] if v<prefix['duration_s']]
    r=evaluate_design(d,dict(row,task=prefix),rtol=1e-5,max_step=.001)
    passed_first=r['metrics']['delivered_on_time']>=1 and all(r['checks'].values())
    if passed_first:r=evaluate_design(d,row,rtol=1e-5,max_step=.001)
    m=r['metrics']
    wakes=sorted({e['time_s'] for w in r['measurements']['windows'] for e in w['events'] if e['event']=='WAKE'} |
        ({m['first_wake_s']} if m['first_wake_s'] is not None else set()))
    distances=[min([abs(w-s-.02) for w in wakes]+[1.]) for s in t['fault_starts_s']]
    score=4-m['delivered_on_time']+.05*m['brownouts']+.5*m['false_reports']+.25*sum(min(x,1) for x in distances)
    score+=max(m['peak_stress_MPa']/40-1,0)+max(m['peak_tip_mm']/1.5-1,0)
    receipt=dict(label=label,x=list(map(float,x)),arm=arm,readout_charge_ohm=c['envelope_charge_ohm'],score=score,design=d,task=t,result=r,wakes=wakes,partial_screen=not passed_first,full_calls=int(passed_first))
    with (OUT/'e3_single_search.jsonl').open('a') as f:f.write(json.dumps(receipt)+'\n')
    return score


def counterexample_search(row,seed=738,workers=4,generations=2,population=40):
    from scipy.optimize import differential_evolution
    from functools import partial
    import multiprocessing
    rng=np.random.default_rng(seed);initial=[]
    log=OUT/'e3_single_search.jsonl'
    offset=log.stat().st_size if log.exists() else 0
    arms=row.get('search_arms',[0,1,2,3]);bounds=list(SEARCH_BOUNDS);bounds[0]=(0,len(arms)-1)
    seeds=[]
    for x in row.get('counterexample_seeds',[]):
        if int(round(x[0])) in arms:
            x=list(x);x[0]=arms.index(int(round(x[0])));seeds.append(x)
    for i in range(population):
        index=i%len(arms);arm=arms[index]
        if i<len(seeds):
            x=list(seeds[i]);x[4]+=np.log10((row['task']['background_peak_g']/.1)**2)
            initial.append(x);continue
        L=float(rng.uniform(24,42))
        m=float(np.clip(5.8*(24/L)**3+rng.uniform(-.15,.15),2,7))
        R=float(rng.uniform(4.3,5.65)) if arm<2 else float(rng.uniform(3,4.3))
        start=float(rng.uniform(2.6,3.2))
        C=float(rng.uniform(2.0,2.5))
        high=float(rng.uniform(.15,1.0))
        if i%3==0:
            L=24.;m=5.8 if arm<2 else 5.5;R=np.log10(250000 if arm<2 else 1000)
            C=np.log10((174.5 if arm<2 else 180.5)*(2.8/start)**2)
            high=float(rng.uniform(.309,.314))
        if row.get('search_readout_charge_ohm')==100000.:
            R=float(rng.uniform(4.1,5.3)) if arm<2 else float(rng.uniform(3,5))
            high=float(rng.uniform(1.5,3.2));L=float(rng.uniform(24,34)) if i%2 else L
            m=float(np.clip(5.8*(24/L)**3+rng.uniform(-.3,.3),2,7))
        initial.append([index,L,m,R,C,start,np.log10(rng.choice([1.45,4.5,5.75,6])),
            high,rng.uniform(.96,.9999),int(i%5==0),rng.uniform(4,5.5),rng.uniform(.5,10),int(i%4==0),int(i%4==1)])
    f=partial(single_trial,row=row,label=f"{row.get('id','prototype')}/seed{seed}")
    with ProcessPoolExecutor(workers,mp_context=multiprocessing.get_context('fork')) as pool:
        r=differential_evolution(f,bounds,workers=pool.map,updating='deferred',init=np.array(initial),
            integrality=[True]+[False]*8+[True,False,False,True,True],maxiter=generations,
            polish=False,seed=seed,tol=0,atol=0)
    with log.open('rb') as stream:
        stream.seek(offset)
        trials=[json.loads(line) for line in stream]
    best=min(trials,key=lambda x:x['score'])
    return dict(seed=seed,bounds=bounds,arms=arms,readout_charge_ohm=row.get('search_readout_charge_ohm',100e6),nfev=r.nfev,best_score=float(r.fun),best_x=r.x.tolist(),
        prefix_calls=len(trials),full_calls=sum(x['full_calls'] for x in trials),
        pass_hits=sum(x['result']['verdict']=='PASS' for x in trials),
        best_design=best['design'],best_result=best['result'],
        claim='Mixed-domain numerical counterexample search, not a symbolic impossibility proof.')

def area_mm2(design):
    aux=design.get('connections',{}).get('aux_resonator',design.get('modules',{}).get('A',True))
    return design['harvester']['length_mm']*design['harvester']['width_mm'] + (design['trigger_beam']['length_mm']*design['trigger_beam']['width_mm'] if aux else 0.)


def evaluate_design(design,row,**resolution):
    """One common physical consumer plus this task's public footprint constraint."""
    area=area_mm2(design);limit=row.get('mechanical_area_limit_mm2',float('inf'))
    if area>limit:
        return dict(verdict='FAIL',checks={'mechanical_area_within_limit':False},
            mechanical_area_mm2=area,failure_codes=['AREA_FAIL'],full_calls=0)
    result=run(design,row['task'],**resolution)
    result['checks']['mechanical_area_within_limit']=True
    result['mechanical_area_mm2']=area
    result['verdict']='PASS' if all(result['checks'].values()) else 'FAIL'
    return result


def tasks(seed=3103):
    rng = np.random.default_rng(seed)
    rows = []
    # A fixed frequency sweep with independently drawn manufacturing damping.
    for i, fr in enumerate(np.linspace(43., 49., 16)):
        d, t = baseline(), copy.deepcopy(TASK)
        d['harvester']['damping_ratio'] = float(rng.uniform(.0145, .0155))
        t['background_Hz'] = float(fr)
        def voltage(L):
            b = dict(d['harvester'], length_mm=L)
            return abs(response(b, fr, 1.)[1])
        # Bracket every sampled peak rather than assuming unimodality globally.
        xs = np.linspace(24., 42., 361)
        ys = np.array([voltage(x) for x in xs])
        j = int(np.argmax(ys))
        L = float(minimize_scalar(lambda x:-voltage(x), bounds=(xs[max(0,j-1)],xs[min(len(xs)-1,j+1)]), method='bounded').x)
        steady, loaded = copy.deepcopy(d), copy.deepcopy(d)
        steady['harvester']['length_mm'] = L
        loaded['harvester']['length_mm'] = L*.9868
        rows.append(dict(id=f'E3-P{i+1:02}', kind='proxy_mismatch', task=t,
                         initial=steady, witness=loaded,
                         domain={'harvester.length_mm':[24.,42.]},
                         proxy='steady open-circuit voltage at background frequency',
                         proxy_optimum_mm=L, proxy_voltage_V=voltage(L)))
    return rows


def evaluate(row):
    a, b = evaluate_design(row['initial'],row), evaluate_design(row['witness'],row)
    row.update(initial_result=a,witness_result=b,
               qualified=a['verdict']=='FAIL' and b['verdict']=='PASS')
    return row


def control_tasks(seed=451):
    """Eight independently drawn local repairs on the same single-beam stock."""
    rng=np.random.default_rng(seed)
    base=json.loads((OUT.parent/'case2.json').read_text())
    base['design']['modules']['D']=False
    base['design']['harvester'].update(length_mm=29.,tip_mass_g=4.25)
    base['design']['circuit'].update(converter_input_R_ohm=46415.888,storage_uF=100,start_V=2.8,envelope_charge_ohm=100e6,wake_high_V=.7,wake_low_V=.4)
    base['task'].update(background_Hz=47.,fault_Hz=47.)
    ids=rng.permutation(np.arange(1,17))[:8]
    rows=[]
    for i in range(8):
        d,t=copy.deepcopy(base['design']),copy.deepcopy(base['task'])
        t.update(background_peak_g=float(rng.uniform(.20,.21)),fault_peak_g=float(rng.uniform(.64,.66)))
        initial=copy.deepcopy(d);initial['circuit'].update(wake_high_V=3.2,wake_low_V=1.)
        rows.append(dict(id=f'E3-T{ids[i]:02}',kind='local_single_beam',task=t,initial=initial,witness=d,
            domain=DOMAIN,branches=BRANCHES,mechanical_area_limit_mm2=300.,
            fixed_stock={'main_width_mm':10.,'aux_width_mm':6.,'main_substrate_mm':.15,'main_piezo_layer_mm':.12,'aux_substrate_mm':.1,'aux_piezo_layer_mm':.08},
            area_formula='Lmain*10 + (Laux*6 if A enabled else 0), mm2; PCB area is separate',
            ratio_definition='unshunted reference-witness peak stress / fixed 40 MPa safety limit; not a global impossibility certificate'))
    return rows


def control_evaluate(row):
    row=evaluate(row)
    row['reference_stress_ratio']=row['witness_result']['metrics']['peak_stress_MPa']/row['task']['stress_limit_MPa']
    row['mechanical_area_mm2']=area_mm2(row['witness'])
    dual=copy.deepcopy(row['witness']);dual['modules']['A']=True
    dual['harvester']['length_mm']=24.;dual['trigger_beam']['length_mm']=11.
    row['minimum_any_dual_area_mm2']=area_mm2(dual)
    row['smallest_dual_result']=evaluate_design(dual,row)
    row['qualified'] &= .6<=row['reference_stress_ratio']<=.9 and row['mechanical_area_mm2']<=300 and row['smallest_dual_result']['failure_codes']==['AREA_FAIL']
    return row


def calibrate_controls(workers=2):
    with ProcessPoolExecutor(workers) as pool:rows=list(pool.map(control_evaluate,control_tasks()))
    result=dict(requested=8,qualified=sum(r['qualified'] for r in rows),tasks=rows,
        claim='Local full-service single-beam controls. Reference stress ratio is not proof that another architecture is necessary.')
    (OUT/'e3_local_controls.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def required_tasks(seed=5931):
    """Independent small manufacturing/operating deviations around the dual prototype."""
    prototype=json.loads((OUT/'e3_dual_final_prototype.json').read_text())
    seed_file=OUT/'e3_required_search_seeds.json'
    seeds=json.loads(seed_file.read_text())
    rng=np.random.default_rng(seed)
    used={r['id'] for r in control_tasks()}
    ids=[f'E3-T{i:02}' for i in range(1,17) if f'E3-T{i:02}' not in used]
    rng.shuffle(ids);rows=[]
    for i in range(8):
        d,t=copy.deepcopy(prototype['design']),copy.deepcopy(prototype['task'])
        t.update(background_Hz=float(rng.uniform(44.9,45.1)),background_peak_g=float(rng.uniform(.099,.101)),
            fault_Hz=float(rng.uniform(209.5,210.5)),fault_peak_g=float(rng.uniform(.495,.505)),
            nuisance_peak_g=float(rng.uniform(1.29,1.31)))
        shift=float(rng.uniform(-.01,.01))
        for key in ('fault_starts_s','nuisance_starts_s'):t[key]=[v+shift for v in t[key]]
        initial=copy.deepcopy(d);initial['modules']['A']=False
        initial['connections']={'detector_source':'harvester','mcu_gate':'envelope'}
        initial['circuit']['envelope_charge_ohm']=100e6
        rows.append(dict(id=ids[i],kind='dual_beam_candidate',task=t,initial=initial,witness=d,
            domain=DOMAIN,branches=BRANCHES,
            mechanical_area_limit_mm2=300.,
            fixed_stock={'main_width_mm':6.,'main_substrate_mm':.15,'main_piezo_layer_mm':.12,
                'aux_width_mm':6.,'aux_substrate_mm':.1,'aux_piezo_layer_mm':.08,
                'envelope_capacitance_nF':2.,'envelope_discharge_ohm':20e6,
                'readout_charge_choices_ohm':[100000.,100000000.]},
            area_formula='Lmain*6 + (Laux*6 if module A enabled else 0), mm2; PCB area is separate',
            numeric_search_domain=SEARCH_BOUNDS,counterexample_seeds=seeds))
    return rows


def required_evaluate(row):
    row=evaluate(row)
    row['mechanical_area_mm2']=area_mm2(row['witness'])
    row['witness_qualified']=row.pop('qualified')
    return row


def assemble(proxy,controls,required):
    structure=dict(requested=16,qualified=controls['qualified']+required['qualified'],
        local_controls=controls,architecture_required=required,
        area_note='Original reference area408mm2 is retained. New public fixed-width stocks use actual L*b and the same 300mm2 limit in every branch.',
        chi_note='Reference stress/40MPa and energy duty burden are reported separately; they are not one interchangeable chi.')
    result=dict(experiment='E3',proxy_tasks=proxy,proxy_qualified=sum(r['qualified'] for r in proxy),structure=structure,
        claim='Original full transient factory calibration only; no Agent performance measured. Numerical branch exclusion is not a symbolic global impossibility proof.')
    public=[]
    for r in proxy+controls['tasks']+required['tasks']:
        public.append({k:r[k] for k in ('id','task','initial','domain','proxy','mechanical_area_limit_mm2','fixed_stock','branches','area_formula') if k in r})
    public.sort(key=lambda r:r['id'])
    (OUT/'e3_public_tasks.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    (OUT/'e3_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def calibrate(workers=4):
    with ProcessPoolExecutor(workers) as pool:
        proxy=list(pool.map(evaluate,tasks()))
    controls=calibrate_controls(workers)
    with ProcessPoolExecutor(workers) as pool:
        rows=list(pool.map(required_evaluate,required_tasks()))
    for i,row in enumerate(rows):
        row['counterexample_search']=counterexample_search(row,seed=8000+i,workers=workers,generations=2,population=16)
        row['independent_search']=counterexample_search(row,seed=9000+i,workers=workers,generations=1,population=16)
        low=dict(row,search_arms=[1,3],search_readout_charge_ohm=100000.,
            counterexample_seeds=json.loads((OUT/'e3_low_R_search_seeds.json').read_text()))
        row['alternative_readout_search']=counterexample_search(low,seed=10000+i,workers=workers,generations=1,population=16)
        searches=[row[k] for k in ('counterexample_search','independent_search','alternative_readout_search')]
        row['numeric_architecture_qualified']=row['witness_qualified'] and all(s['pass_hits']==0 for s in searches)
        row['best_without_A']=min(searches,key=lambda s:s['best_score'])['best_design']
    from functools import partial
    designs=[d for row in rows for d in (row['witness'],row['best_without_A'])]
    repeat_rows=[row for row in rows for _ in range(2)]
    with ProcessPoolExecutor(workers) as pool:
        repeated=list(pool.map(partial(evaluate_design,rtol=1e-6,max_step=.000125),designs,repeat_rows))
    for i,row in enumerate(rows):
        row['resolution_repeat']={'witness':repeated[2*i],'best_without_A':repeated[2*i+1]}
        row['numeric_architecture_qualified'] &= repeated[2*i]['verdict']=='PASS' and repeated[2*i+1]['verdict']=='FAIL'
    required=dict(requested=8,qualified=sum(r['numeric_architecture_qualified'] for r in rows),tasks=rows,
        qualification='Full-service witness, same-domain multi-start numerical counterexample search, and independent finer-integration repeat; not a symbolic global impossibility theorem.')
    (OUT/'e3_required_calibration.json').write_text(json.dumps(required,ensure_ascii=False,indent=2)+'\n')
    return assemble(proxy,controls,required)


if __name__=='__main__':
    result=calibrate()
    print(json.dumps({'proxy_qualified':result['proxy_qualified'],'structure_qualified':result['structure']['qualified']}))
