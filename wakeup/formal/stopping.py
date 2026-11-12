"""E4: measured narrow windows, passive voltage bounds and finite-time energy bounds."""
import copy
import json
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
import numpy as np
from scipy.optimize import minimize_scalar
from common import baseline, run, response, TASK, OUT
from sim import beam, G


def energy_bound(design, task, horizon, lengths=(42.,24.)):
    # d(E)/dt = -a*mf*v-c*v*v-loss <= a*a*mf*mf/(4*c).
    # With all other geometry fixed, mf^2/c is increasing with L.
    coefficient=0.
    for name,L in zip(('harvester','trigger_beam'),lengths):
        b=beam(dict(design[name],length_mm=L))
        coefficient+=b['forcing_mass']**2/(4*b['c'])
    # Triangle inequality in L2 and an analytic sin^2 integral upper bound.
    # Burst taper <= 1, so dropping it can only enlarge this bound.
    norms=[task['background_peak_g']*G*np.sqrt(horizon/2+1/(8*np.pi*task['background_Hz']))]
    for kind in ('fault','nuisance'):
        for start in task[kind+'_starts_s']:
            duration=max(0.,min(task[kind+'_duration_s'],horizon-start))
            if duration:
                norms.append(task[kind+'_peak_g']*G*np.sqrt(duration/2+1/(8*np.pi*task[kind+'_Hz'])))
    return float(coefficient*sum(norms)**2)


def tasks(seed=4104):
    rng=np.random.default_rng(seed); rows=[]
    for i in range(16):
        d,t=baseline(),copy.deepcopy(TASK)
        t['background_Hz']=float(rng.uniform(44.,46.))
        def voltage(L):
            return abs(response(dict(d['harvester'],length_mm=L),t['background_Hz'],1.)[1])
        L=float(minimize_scalar(lambda x:-voltage(x),bounds=(27.,34.),method='bounded').x)*.9868
        d['harvester']['length_mm']=L
        rows.append(dict(id=f'E4-S1-{i+1:02}',state='S1',task=t,witness=d,
                         domain={'harvester.length_mm':[24.,42.],'branch':['direct_aux']},
                         certificate=None, narrow_window_qualified=False))
    return rows



def voltage_bound(design, task):
    """A safe direct rectifier cannot exceed this passive port voltage.

    Between its last zero and t, Cp|v| <= theta|q(t)-q(t0)| <= 2theta qsafe.
    Every external port current is dissipative. theta/(Cp*stress_per_m) is
    independent of beam length, width, tip mass and damping in this beam model.
    """
    b=beam(design['harvester'])
    upper=2*abs(b['theta'])/b['cp']*task['stress_limit_MPa']*1e6/b['stress_per_m']
    start=1.9; drop=2*design['circuit']['bridge_diode_V']
    return dict(kind='safe passive piezo port voltage',port_voltage_upper_V=upper,
        direct_storage_upper_V=upper-drop,minimum_start_V=start,
        excludes_current_branch=upper-drop<start,
        proof='Integrate Cp*v_dot=-theta*q_dot-sign(v)*Iout from the latest v=0; Iout>=0. Safety requires |q|<=stress_limit/stress_per_m. At fixed substrate and piezo thickness theta/(Cp*stress_per_m) is independent of L, width, mass, damping. Direct storage cannot cross max|v|-2Vdiode from zero.')


def switch_tasks(seed=4105):
    rng=np.random.default_rng(seed); rows=[]
    for i in range(16):
        d,t=baseline(),copy.deepcopy(TASK)
        d['harvester'].update(width_mm=50.,piezo_layer_mm=.0035,tip_mass_g=9.3)
        d['circuit'].update(storage_uF=100.,bridge_diode_V=.05,converter_input_R_ohm=420.)
        t.update(background_Hz=float(rng.uniform(29.17,29.19)),
                 background_peak_g=float(rng.uniform(.1545,.1575)),
                 fault_peak_g=float(rng.uniform(.48,.52)),
                 fault_starts_s=[float(rng.uniform(9.9,10.1)),16.,22.,28.])
        domain={'harvester.length_mm':[24.,42.],'harvester.tip_mass_g':[1.,12.],
            'trigger_beam.length_mm':[11.,24.],'circuit.storage_uF':[80.,1000.],
            'circuit.start_V':[1.9,3.2],'circuit.wake_high_V':[.15,2.],
            'circuit.wake_low_V':[.05,1.5],'circuit.converter_input_R_ohm':[100.,1e6],
            'circuit.bridge_series_ohm':[100.,5e5],
            'circuit.envelope_charge_ohm':[1e5,1e8],'circuit.envelope_discharge_ohm':[1e6,1e8],
            'circuit.shunt_ohm':[1e4,1e6],'circuit.shunt_threshold_V':[.5,5.],
            'branch':['direct','boost_65pct'],'modules':{k:[False,True] for k in 'ABCD'},
            'fixed_platform':'3.5um piezo film, 0.15mm substrate, width50mm, bridge diode0.05V; other manufactured material and firmware service parameters fixed.',
            'coupling':'wake_low_V<wake_high_V. No free energy: boost has 65% efficiency; A/B/C/D static loads are 0.5/180/2/0.5uW in the original consumer.',
            'area':'Main L*50 plus auxiliary L*6 projected beam area; report separately. No 300mm2 restriction is claimed for this new thin-film platform.'}
        rows.append(dict(id=f'E4-S2-{i+1:02}',state='S2',task=t,witness=d,domain=domain,
                         certificate=voltage_bound(d,t)))
    return rows



def energy_tasks(seed=4106):
    rng=np.random.default_rng(seed);rows=[];scale=.075
    for i in range(16):
        d,t=baseline(),copy.deepcopy(TASK)
        for k in ['harvester','trigger_beam']:
            d[k]['width_mm']*=scale;d[k]['tip_mass_g']*=scale
        d['harvester']['length_mm']=29.85
        d['circuit'].update(storage_uF=150.,start_V=2.6,bridge_series_ohm=5e3/scale,
            envelope_charge_ohm=1e5/scale,envelope_nF=2*scale,
            envelope_discharge_ohm=2e7/scale,trigger_input_ohm=1e8/scale,
            converter_input_R_ohm=3e5*.09/scale)
        t.update(background_peak_g=float(rng.uniform(.363,.365)),
            fault_peak_g=float(rng.uniform(.497,.5)),
            fault_starts_s=[float(rng.uniform(0.,.002)),16.,22.,28.])
        horizon=t['fault_starts_s'][0]+t['delivery_deadline_s']
        upper=energy_bound(d,t,horizon);needed=.5*80e-6*1.9**2
        rows.append(dict(id=f'E4-S3-{i+1:02}',state='S3',task=t,witness=d,
            domain={'harvester.length_mm':[24.,42.],'trigger_beam.length_mm':[11.,24.],
                'circuit.storage_uF':[80.,1000.],'circuit.start_V':[1.9,3.2],
                'circuit.wake_high_V':[.15,2.],'circuit.wake_low_V':[.05,1.5],
                'circuit.converter_input_R_ohm':[100.,1e6],
                'branch':['direct','boost_65pct'],'modules':{k:[False,True] for k in 'ABCD'},
                'fixed_platform':'Main width0.75mm/tipmass0.34875g; aux width0.45mm/tipmass0.0105g. Other manufactured material/damping and firmware service parameters fixed; zero initial energy.',
                'coupling':'wake_low_V<wake_high_V; all original module power costs apply.'},
            certificate=dict(kind='first-deadline startup energy',horizon_s=horizon,
                mechanical_input_upper_J=upper,minimum_startup_storage_J=needed,
                excludes_all_branches=upper<needed,
                energy_domain='mechanical + piezoelectric + storage; envelope/shunt/firmware are nonnegative outward flows',
                proof='Complete square -c*u^2-a*mf*u <= a^2*mf^2/(4*c), integrate both beams, maximize mf^2/c at declared maximum lengths. Apply L2 triangle inequality to all excitations; losses are nonnegative.')))
    return rows

def window(row):
    center=row['witness']['harvester']['length_mm']; points=[]; brackets=[]
    for sign in [-1,1]:
        good=center; bad=center+sign*.5
        for _ in range(4):
            d=copy.deepcopy(row['witness']);d['harvester']['length_mm']=bad
            r=run(d,row['task']);points.append(dict(length_mm=bad,result=r))
            if r['verdict']=='FAIL':break
            good=bad;bad+=sign*.5
        else:
            row.update(qualified=False,narrow_window_qualified=False,window=dict(samples=points,reason='No failed outer endpoint in the declared local search.'))
            return row
        for _ in range(3):
            mid=(good+bad)/2;d=copy.deepcopy(row['witness']);d['harvester']['length_mm']=mid
            r=run(d,row['task']);points.append(dict(length_mm=mid,result=r))
            if r['verdict']=='PASS':good=mid
            else:bad=mid
        brackets.append(dict(pass_mm=good,fail_mm=bad))
    lo,hi=brackets
    width=hi['fail_mm']-lo['fail_mm']
    row['window']=dict(left=lo,right=hi,outer_width_mm=width,
        width_fraction_of_declared_length_domain=width/18,
        interpretation='Local connected PASS window bracketed by real FAIL/PASS transitions, not a proof of global uniqueness or that every interior point passes.',samples=points)
    row['narrow_window_qualified']=width<1.8 and all(x['result']['verdict']=='FAIL' for x in points if x['length_mm'] in [lo['fail_mm'],hi['fail_mm']])
    row['qualified']=row['witness_result']['verdict']=='PASS' and row['narrow_window_qualified']
    return row


def switch_counterfactual(row):
    direct=copy.deepcopy(row['witness']);direct['circuit'].pop('converter_input_R_ohm')
    allopen=copy.deepcopy(row['witness']);allopen['modules']={k:True for k in 'ABCD'}
    allopen['circuit'].update(shunt_ohm=47000.,shunt_threshold_V=1.)
    row['direct_result']=run(direct,row['task'])
    row['all_open_result']=run(allopen,row['task'])
    row['qualified']=(row['witness_result']['verdict']=='PASS' and
        row['certificate']['excludes_current_branch'] and row['direct_result']['verdict']=='FAIL'
        and row['all_open_result']['verdict']=='FAIL')
    return row



def write_public_views(result):
    """Only the selected information condition is shown to a future Agent."""
    rng=np.random.default_rng(4144); public=[]; views={}
    for j,index in enumerate(rng.permutation(len(result['tasks']))):
        r=result['tasks'][int(index)];name=f'E4-T{j+1:02}'
        r['public_id']=name;initial=copy.deepcopy(r['witness'])
        if r['state']=='S1':
            initial['harvester']['length_mm']=r['window']['left']['fail_mm']
            actual=next(p['result'] for p in r['window']['samples'] if p['length_mm']==initial['harvester']['length_mm'])
        elif r['state']=='S2':
            initial['circuit'].pop('converter_input_R_ohm');actual=r['direct_result']
        else:actual=r['witness_result']
        r['domain']['branch']=['direct','boost_65pct']
        r['domain']['modules']={k:[False,True] for k in 'ABCD'}
        mincap=r['domain'].get('circuit.storage_uF',[r['witness']['circuit']['storage_uF']])[0]
        minstart=r['domain'].get('circuit.start_V',[r['witness']['circuit']['start_V']])[0]
        horizon=r['task']['fault_starts_s'][0]+r['task']['delivery_deadline_s']
        bound_design=copy.deepcopy(r['witness'])
        if 'harvester.tip_mass_g' in r['domain']:
            bound_design['harvester']['tip_mass_g']=r['domain']['harvester.tip_mass_g'][1]
        upper=energy_bound(bound_design,r['task'],horizon)
        eb=dict(kind='startup energy',horizon_s=horizon,energy_upper_J=upper,
                required_lower_J=.5*mincap*1e-6*minstart**2,
                excludes=upper<.5*mincap*1e-6*minstart**2)
        vb=voltage_bound(r['witness'],r['task'])
        direct=dict(branch='direct',bounds=[eb,dict(kind=vb['kind'],storage_upper_V=vb['direct_storage_upper_V'],
            required_start_V=minstart,excludes=vb['direct_storage_upper_V']<minstart,
            premise='stress safety and passive external piezo port currents',proof=vb['proof'])])
        boost=dict(branch='boost_65pct',bounds=[eb],conversion_efficiency=.65)
        history=[dict(design=initial,result=dict(pass_=actual['verdict']=='PASS',
            delivered_on_time=actual['metrics']['delivered_on_time'],expected=4,
            false_alarms=actual['metrics']['false_reports'],
            safety={k:actual['checks'][k] for k in ['stress_within_limit','travel_within_limit']}))]
        current='boost_65pct' if 'converter_input_R_ohm' in initial['circuit'] else 'direct'
        public.append(dict(id=name,task=r['task'],initial=initial,domain=r['domain'],current_branch=current))
        views[name]={'L0':dict(history=history),'L1':dict(history=history,bounds=[boost if current=='boost_65pct' else direct]),
                     'L2':dict(history=history,bounds=[direct,boost])}
    (OUT/'e4_public_tasks.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    (OUT/'e4_feedback_views.json').write_text(json.dumps(views,ensure_ascii=False,indent=2)+'\n')
    (OUT/'e4_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


def qualify(row):
    row['witness_result']=run(row['witness'],row['task'])
    if row['state']=='S2':return switch_counterfactual(row)
    r=row['witness_result']
    row['qualified']=(row['certificate']['excludes_all_branches'] and
        r['metrics']['delivered_on_time']==3 and
        all(v for k,v in r['checks'].items() if k!='all_faults_delivered_on_time'))
    return row


def calibrate(workers=4):
    # Reuse the already measured S1 boundaries; new manufactured platforms run fully.
    s1=[r for r in json.loads((OUT/'e4_summary.json').read_text())['tasks'] if r['state']=='S1']
    frozen=switch_tasks()+energy_tasks()
    (OUT/'e4_frozen_new_platforms.json').write_text(json.dumps(frozen,indent=2)+'\n')
    rows=s1[:]
    with ProcessPoolExecutor(workers,mp_context=get_context('fork')) as pool:
        with (OUT/'e4_progress.jsonl').open('w') as f:
            for r in pool.map(qualify,frozen):
                rows.append(r);f.write(json.dumps(r)+'\n');f.flush()
                print(r['id'],r['qualified'],r['witness_result']['metrics']['delivered_on_time'],flush=True)
    result=dict(experiment='E4',tasks=rows,
        qualified_by_state={s:sum(r['qualified'] for r in rows if r['state']==s) for s in ['S1','S2','S3']},
        claim='Local narrow-window repair; safe direct-branch voltage exclusion over start1.9–3.2V/C80–1000uF with true boost PASS witnesses; all-declared-branch startup-energy exclusion over the same C/start ranges with true 3/4 histories. No Agent stopping accuracy measured.')
    write_public_views(result)
    (OUT/'e4_progress.jsonl').unlink()
    (OUT/'e4_frozen_new_platforms.json').unlink()
    return result


if __name__=='__main__':print(json.dumps(calibrate()['qualified_by_state']))
