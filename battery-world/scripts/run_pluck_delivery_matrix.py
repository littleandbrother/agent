#!/usr/bin/env python3
"""Predeclared SEH design-domain exploration, not calibrated product acceptance."""
import argparse
import copy
import csv
import json
from pathlib import Path
import shutil
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/python/bfworld/src'))
from bfworld.agentlab.pluck_case import run, digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    base=json.loads((ROOT/'configs/reference_cases/pluck-v1/case.json').read_text())
    scenarios=[
        {'id':'cold','gap':.024},
        {'id':'reverse','gap':.024,'b0':.1,'speed':-.4},
        {'id':'slow','gap':.024,'b0':-.04,'speed':.04},
        {'id':'fast','gap':.024,'speed':.8},
        {'id':'partial','gap':.024,'b0':-.1,'speed':.02},
        {'id':'gap-plus-2mm','gap':.026},
        {'id':'gap-minus-2mm','gap':.022},
        {'id':'cap-minus20','gap':.024,'cap':37.6e-6},
        {'id':'cap-plus20','gap':.024,'cap':56.4e-6},
        {'id':'leakage-10x','gap':.024,'leak':9.5e-6},
        {'id':'no-motion-drive','gap':.024,'scale':0},
        {'id':'heavy-init','gap':.024,'init_multiplier':20},
        {'id':'heavy-tx','gap':.024,'tx_multiplier':20},
    ]
    protocol={'schema_version':'bf-pluck-domain-matrix-v1','scenarios':scenarios,'interface':'seh','step_s':20e-6,'wall_cap_s':900,'model_calls':0,
        'scope':'Reduced-model design exploration. Firmware energy from ViPSN paper; semiconductor/PMIC assumptions. Not the new CAD calibrated geometry.',
        'not_covered':['angular/clamping tolerance','multiaction transient in one persistent state','long idle transient','native switching-PMIC dynamics'],
        'thresholds':{'event_deadline_s':base['acceptance']['event_deadline_s'],'max_deflection_m':base['acceptance']['max_deflection_m'],'diode_voltage_rating_v':100}}
    (a.output/'protocol.json').write_text(json.dumps(protocol,indent=2));shutil.copy2(__file__,a.output/'runner.py')
    shutil.copy2(ROOT/'packages/python/bfworld/src/bfworld/agentlab/pluck_case.py',a.output/'model-source.py')
    results=[];start=time.monotonic()
    for spec in scenarios:
        c=copy.deepcopy(base);c['motion']['initial_b_m']=spec.get('b0',c['motion']['initial_b_m']);c['motion']['velocity_m_s']=spec.get('speed',c['motion']['velocity_m_s']);c['power']['quiescent_a']=spec.get('leak',c['power']['quiescent_a'])
        for stage in c['workload']['stages'][:2]:stage['energy_j']*=spec.get('init_multiplier',1)
        c['workload']['stages'][2]['energy_j']*=spec.get('tx_multiplier',1)
        row={'id':spec['id']}
        try:
            if time.monotonic()-start>protocol['wall_cap_s']:raise TimeoutError('MATRIX_WALL_LIMIT')
            r=run(c,a.output/spec['id'],interface='seh',loaded=True,capacitance_f=spec.get('cap',47e-6),gap=spec['gap'],motion_scale=spec.get('scale',1))
            domain=r['peak_piezo_v']<=100 and r['checks']['deflection_limit']
            row.update(status='computed',tx=len(r['tx_complete_times_s']),first_tx_s=next(iter(r['tx_complete_times_s']),None),startup_count=len(r['startup_times_s']),brownouts=len(r['brownouts_s']),storage_v=r['peak_storage_v'],piezo_v=r['peak_piezo_v'],deflection_mm=1000*r['peak_deflection_m'],service=r['checks']['service'],domain=domain,result_sha256=digest(a.output/spec['id']/'result.json'))
            row['failure_class']='model-domain' if not domain else 'none' if r['checks']['service'] else 'design-service'
        except (ValueError,RuntimeError,TimeoutError) as e:row.update(status='failed',failure_class='solver',error=str(e))
        results.append(row);print(json.dumps(row),flush=True)
    fields=list(dict.fromkeys(k for r in results for k in r))
    with (a.output/'results.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(results)
    (a.output/'report.json').write_text(json.dumps({'protocol_sha256':digest(a.output/'protocol.json'),'results':results,'hardware_verified':False,'reference_qualified':False,'scope':protocol['scope'],'not_covered':protocol['not_covered']},indent=2))

if __name__=='__main__':main()
