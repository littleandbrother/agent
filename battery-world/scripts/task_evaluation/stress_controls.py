#!/usr/bin/env python3
"""Independent native integration anchors and broader input stress controls."""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess

from run import ROOT, save
from mechanisms import cases, run, predict, metrics
from bf_v2_environment import environment
from v2_common import RUNTIME
profile, env = environment(RUNTIME)
os.environ.update(env)
from bfworld.agentlab.design_lab.native_slot import native_slot


def native(c, folder):
    if (folder/'result.json').exists():return json.loads((folder/'result.json').read_text())
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'dispatch.json').exists():raise ValueError('CONTROL_RECONCILE_REQUIRED')
    # Independent SPICE state integrator: one volt denotes one microjoule.
    # A 1 uF capacitor with 1 uA input per microW gives dE/dt = Pin-Pload.
    intervals=[(c['sample_at'],c['sample_at']+c['sample_duration'],c['sample_power']),
               (c['tx_at'],c['tx_at']+c['tx_duration'],c['tx_power'])]
    def signal(t):
        active=next((power for a,b,power in intervals if a<=t<b),None)
        load=c['idle'] if active is None else active
        source=c['source_power'] if c['source_start']<=t<c['source_end'] else 0
        if active is not None:source*=1-c['coupling']
        return (source-load)*1e-6
    edges=sorted({0.,c['duration'],c['source_start'],c['source_end'],*[x for a,b,_ in intervals for x in (a,b)]})
    points=[]
    for t in edges:
        if t>0:points.append((t-1e-8,signal(t-1e-8)))
        points.append((t,signal(t+1e-9)))
    pwl=' '.join(f'{t:.12g} {v:.12g}' for t,v in points)
    deck=f'''Independent energy-state integration calibration
Cstate energy 0 1u IC={c['initial']:.12g}
Isource 0 energy PWL({pwl})
Bfloor 0 energy I=max(-v(energy),0)*.1
Bceiling energy 0 I=max(v(energy)-{c['emax']:.12g},0)*.1
.control
set wr_singlescale
tran .0005 {c['duration']} 0 .0005 uic
wrdata energy.dat v(energy)
quit
.endc
.end
'''
    (folder/'energy.cir').write_text(deck)
    key = hashlib.sha256(deck.encode()).hexdigest()
    for previous in sorted(folder.parent.glob('*/dispatch.json')):
        if previous.parent == folder: continue
        marker = json.loads(previous.read_text()); result_file = previous.parent/'result.json'
        if marker.get('input_sha256') != key or not result_file.exists(): continue
        result = json.loads(result_file.read_text()); raw = previous.parent/'energy.dat'
        if not raw.is_file() or hashlib.sha256(raw.read_bytes()).hexdigest() != result['raw_sha256']:
            raise ValueError('CONTROL_CACHE_INTEGRITY')
        for name in ('energy.dat', 'solver.log'): shutil.copyfile(previous.parent/name, folder/name)
        result = {**result, 'reused_from': str(previous.parent)}
        save(folder/'reuse.json', {'input_sha256': key, 'source': str(previous.parent)})
        # Only the waveform is cached. Information-window validity belongs to
        # the new task and is evaluated again below.
        result['success'] = min(result['window_minima_uJ']) >= c['emin']-1e-5 and c['event_start'] <= c['sample_at'] <= c['event_end']
        save(folder/'result.json', result)
        return result
    save(folder/'dispatch.json',{'input_sha256':key})
    with native_slot(profile['paths']['NATIVE_LOCK'],blocking=False):
        p=subprocess.run(['/opt/homebrew/bin/ngspice','-b','energy.cir'],cwd=folder,capture_output=True,text=True,timeout=60)
    (folder/'solver.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise ValueError('CONTROL_NATIVE_FAILED')
    rows=[[float(x) for x in line.split()] for line in (folder/'energy.dat').read_text().splitlines()]
    minima=[min(v for t,v in rows if a<=t<=b) for a,b,_ in intervals]
    valid=c['event_start']<=c['sample_at']<=c['event_end']
    result={'success':min(minima)>=c['emin']-1e-5 and valid,'window_minima_uJ':minima,
        'final_energy_uJ':rows[-1][1],'raw_sha256':hashlib.sha256((folder/'energy.dat').read_bytes()).hexdigest()}
    save(folder/'result.json',result);return result


def main():
    folder=ROOT/'mechanisms-controls'
    if (folder/'result.json').exists():print((folder/'result.json').read_text());return
    base=cases()[0]
    negative={'zero':{**base,'initial':0.,'source_power':0.},
              'ample':{**base,'initial':1400.,'source_power':1000.,'source_start':0.,'source_end':4.},
              'invalid_information':{**base,'initial':1400.,'source_power':1000.,'source_start':0.,'source_end':4.,'event_start':2.,'event_end':3.}}
    expected={'zero':False,'ample':True,'invalid_information':False}
    outcomes={k:run(v)['success'] for k,v in negative.items()}
    if outcomes!=expected:raise ValueError('NEGATIVE_CONTROL_FAILED')
    anchors=[]
    for c in cases()[:6]:
        n=native(c,folder/'native'/c['id'])
        old=json.loads((ROOT/'mechanisms/runs'/f"{c['id']}.json").read_text())
        anchors.append({'id':c['id'],'native':n,'existing_discrete':old['success'],
            'same_judgment':n['success']==old['success'],'final_energy_difference_uJ':abs(n['final_energy_uJ']-old['final_energy'])})
    stress=[];rng=random.Random(20261018)
    for i in range(200):
        sample=round(rng.uniform(.1,3.4)/.002)*.002
        a=round(rng.uniform(0,2)/.002)*.002;b=round(rng.uniform(a+.1,4)/.002)*.002
        c={**base,'id':f'stress-{i:03d}','initial':rng.uniform(0,800),'emax':rng.uniform(800,1800),
            'source_power':rng.uniform(0,1200),'source_start':a,'source_end':b,'sample_at':sample,'tx_at':sample+.04,
            'coupling':rng.choice([0.,.2,.7,.95]),'event_start':rng.uniform(0,1),'event_end':rng.uniform(1,4)}
        stress.append(c)
    save(folder/'stress-freeze.json',{'cases':stress,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'stage':'post-pilot out-of-envelope stress; predictions fixed from the original study'})
    rows=[]
    for c in stress:
        out=run(c);save(folder/'stress'/f"{c['id']}.json",{'case':c,'outcome':out})
        rows.append({'case':c,'truth':out['success']})
    scores={name:metrics(rows,[predict(r['case'],f) for r in rows]) for name,f in
        [('static',[]),('event-refined',['prefix','information','feedback'])]}
    result={'controls':outcomes,'native_anchors':anchors,'stress':scores,
        'scope':'native integration checks the mathematical energy-state model; not physical device calibration'}
    save(folder/'result.json',result);print(json.dumps(result))


if __name__=='__main__':main()
