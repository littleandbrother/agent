"""Bounded static-only preparation. This file never time-integrates."""
from pathlib import Path
import hashlib, json, sys, time
import numpy as np
from scipy.optimize import brentq
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'sources/magnetic'))
from magnetic_interface import StaticMagneticInterface, jsonable

PLAN={"version":"passive-static-equilibrium-preflight-v1","quadrature_order":10,
 "scan_points":65,"q_interval_m":[-.008,.008],"brent_xtol_m":1e-14,
 "selection":"stable interior root of minimum absolute q; negative q breaks an exact tie",
 "stability_steps_m":[1e-6,5e-7],"minimum_boundary_margin_m":1e-5,
 "minimum_stiffness_N_m":1e-3,"maximum_equilibrium_residual_N":1e-9,
 "maximum_evaluations":500,"wall_budget_s":60,"dynamic_solves":0}

def main():
    planpath=ROOT/'STATIC-PREFLIGHT-PLAN.json'
    if planpath.exists(): assert json.loads(planpath.read_text())==PLAN
    else: planpath.write_text(json.dumps(PLAN,indent=2)+'\n')
    out=ROOT/'outputs/EQUILIBRIUM-PREFLIGHT.json'
    if out.exists(): raise RuntimeError('immutable result already exists')
    p=StaticMagneticInterface(ROOT/'sources/magnetic'); k=p.rom['k_N_m']
    start=time.monotonic(); records=[]
    def ev(q,n=10):
        if len(records)>=PLAN['maximum_evaluations'] or time.monotonic()-start>PLAN['wall_budget_s']:raise RuntimeError('static budget')
        r=p.evaluate(0,float(q),n)
        records.append({'q_m':q,'n':n,'U_J':r['mutual_potential_J'],'Fq_N':r['generalized_force_N'],'contact':r['contact']})
        return r
    try:
        qs=np.linspace(*PLAN['q_interval_m'],PLAN['scan_points'])
        fs=[k*q-ev(q)['generalized_force_N'] for q in qs]
        roots=[]
        for i in range(len(qs)-1):
            if fs[i]*fs[i+1]<0:
                q=brentq(lambda q:k*q-ev(q)['generalized_force_N'],qs[i],qs[i+1],xtol=1e-14)
                slopes=[k-(ev(q+h)['generalized_force_N']-ev(q-h)['generalized_force_N'])/(2*h) for h in PLAN['stability_steps_m']]
                r=ev(q); residual=k*q-r['generalized_force_N']
                roots.append({'q_m':q,'effective_stiffness_N_m':slopes,'residual_N':residual,'stable':min(slopes)>PLAN['minimum_stiffness_N_m'],'raw':jsonable(r)})
        suitable=[r for r in roots if r['stable'] and abs(r['q_m'])<.008-PLAN['minimum_boundary_margin_m'] and abs(r['residual_N'])<=1e-9]
        if not suitable:raise RuntimeError('no suitable stable closed-door root')
        chosen=sorted(suitable,key=lambda r:(abs(r['q_m']),r['q_m']))[0];q0=chosen['q_m']
        coarse=ev(q0,6)
        result={'status':'STATIC_PREFLIGHT_PASS','plan':PLAN,'selected_root':chosen,'all_bracketed_roots':roots,
         'q0_m':q0,'qdot0_m_s':0.,'Vpiezo0_V':0.,'Vstorage0_V':0.,'Q0_C':p.rom['theta_C_m']*q0,
         'initial_elastic_J':.5*k*q0*q0,'initial_mutual_magnetic_J':chosen['raw']['mutual_potential_J'],
         'initial_piezo_J':0.,'initial_storage_J':0.,'initial_kinetic_J':0.,
         'n6_equilibrium_residual_N':k*q0-coarse['generalized_force_N'],
         'scan_is_exhaustive_root_proof':False,'preparation_reset_work_qualified':False}
    except Exception as e:
        result={'status':'STATIC_PREFLIGHT_FAILED','exception':repr(e),'plan':PLAN}
    result.update({'raw_evaluations':records,'evaluations':len(records),'wall_s':time.monotonic()-start,'dynamic_trajectories':0})
    out.write_text(json.dumps(jsonable(result),indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('raw_evaluations','all_bracketed_roots','selected_root')},indent=2))

if __name__=='__main__':main()
