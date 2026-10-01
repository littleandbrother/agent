"""Authorized evidence-completion replay, not new independent samples/states."""
from pathlib import Path
import hashlib,json,math,sys,datetime
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;sys.path.insert(0,str(ROOT))
from magnetic_interface import StaticMagneticInterface,jsonable

def hashfile(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 seal=json.loads((HERE/'REPLAY-SEAL.json').read_text())
 if hashfile(__file__)!=seal['recording_code_sha256']:raise RuntimeError('recording-code hash mismatch')
 if hashfile(ROOT/'outputs'/'STATIC-RESULTS.json')!=seal['original_result_sha256']:raise RuntimeError('original result changed')
 if hashfile(ROOT/'magnetic_interface.py')!=seal['provider_sha256']:raise RuntimeError('provider changed')
 m=StaticMagneticInterface();original=json.loads((ROOT/'outputs'/'STATIC-RESULTS.json').read_text());rows=[];comparisons=[]
 tolerance=seal['reproduction_tolerances']
 def compare(label,new,old,unit):
  new=np.asarray(new);old=np.asarray(old);error=float(np.max(np.abs(new-old)))
  threshold=tolerance['absolute_by_unit'][unit]+tolerance['relative']*float(np.max(np.abs(old)))
  comparisons.append({'label':label,'max_absolute_difference':error,'unit':unit,'tolerance':threshold,'passed':error<=threshold})
 for row in original['states']:
  s=row['state'];a=math.radians(s['angle_deg']);q=s['q_m'];orders=[]
  for prior in row['orders']:
   n=prior['quadrature_order'];nom=m.evaluate(a,q,n)
   for key,unit in [('mutual_potential_J','J'),('force_beam_N','N'),('tip_torque_about_COM_beam_N_m','N_m'),('generalized_force_N','N')]:
    compare(f"{s['id']}/n{n}/{key}",nom[key],prior[key],unit)
   pairs=[]
   for oldfd in prior['q_energy_finite_differences']:
    h=oldfd['h_m'];plus=m.evaluate(a,q+h,n);minus=m.evaluate(a,q-h,n)
    fd=-(plus['mutual_potential_J']-minus['mutual_potential_J'])/(2*h)
    compare(f"{s['id']}/n{n}/h{h}/finite_difference",fd,oldfd['minus_dU_dq_N'],'N')
    def retained(result,qvalue):
     return {'q_m':qvalue,'mutual_potential_J':result['mutual_potential_J'],'contact':result['contact'],
             'minimum_quadrature_pair_distance_m':result['minimum_quadrature_pair_distance_m'],
             'tip_center_beam_m':result['tip_center_beam_m'],'driver_center_beam_m':result['driver_center_beam_m'],
             'tip_rotation':result['tip_rotation'],'driver_rotation':result['driver_rotation']}
    pairs.append({'h_m':h,'plus':retained(plus,q+h),'minus':retained(minus,q-h),
                  'minus_dU_dq_N':fd,'analytic_projection_N':nom['generalized_force_N'],
                  'difference_from_projection_N':fd-nom['generalized_force_N'],
                  'predeclared_virtual_work_tolerance_N':oldfd['predeclared_tolerance_N'],
                  'virtual_work_passed':abs(fd-nom['generalized_force_N'])<=oldfd['predeclared_tolerance_N']})
   orders.append({'quadrature_order':n,'nominal':nom,'raw_perturbation_pairs':pairs})
  rows.append({'state':s,'orders':orders})
 all_pass=all(c['passed'] for c in comparisons)
 result={'schema':'bf-static-magnetic-evidence-completion-replay-v1','purpose':seal['purpose'],
   'seal_sha256':hashfile(HERE/'REPLAY-SEAL.json'),'started_and_completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
   'independent_samples':False,'new_physical_states':0,'nominal_repeated_evaluations':15,'perturbed_repeated_evaluations':90,
   'all_original_numeric_reproduction_checks_passed':all_pass,'comparison_checks':comparisons,'states':rows,
   'minimum_perturbed_obb_separation_lower_bound_m':min(v[sign]['contact']['surface_distance_lower_bound_m'] for row in rows for o in row['orders'] for v in o['raw_perturbation_pairs'] for sign in ['plus','minus'])}
 out=HERE/'RAW-REPLAY-RESULTS.json'
 if out.exists():raise RuntimeError('Refuse to overwrite replay evidence')
 out.write_text(json.dumps(jsonable(result),indent=2,allow_nan=False)+'\n')
 print(json.dumps({'reproduction_checks':len(comparisons),'passed':all_pass,'maximum_reproduction_absolute_difference':max(c['max_absolute_difference'] for c in comparisons),'minimum_perturbed_obb_separation_lower_bound_m':result['minimum_perturbed_obb_separation_lower_bound_m'],'replay_sha256':hashfile(out)},indent=2))
 if not all_pass:raise RuntimeError('Replay discrepancy retained; original result unchanged')
if __name__=='__main__':main()
