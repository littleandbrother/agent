"""Retained-data-only audit. Never imports/evaluates magnetic provider."""
import datetime,hashlib,json,math
from pathlib import Path
import numpy as np
R=Path('/workspace/shared/magnetic-generalized-force-20261001');O=Path('/workspace/shared/generalized-force-independent-review-20261001/reports/retained-force-readback.json')
read=lambda p:json.loads((R/p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
plan=read('STATIC-PLAN.json');identity=read('outputs/EVALUATION-IDENTITY.json');original=read('outputs/STATIC-RESULTS.json');summary=read('outputs/SUMMARY.json');replay=read('evidence-completion-replay/RAW-REPLAY-RESULTS.json');seal=read('evidence-completion-replay/REPLAY-SEAL.json')
assert sha(R/'STATIC-PLAN.json')==identity['plan_sha256']==read('PLAN-SEAL.json')['plan_sha256']
assert sha(R/'magnetic_interface.py')==identity['implementation_sha256']==seal['provider_sha256']
assert sha(R/'evaluate_static.py')==identity['runner_sha256'];assert sha(R/'outputs/STATIC-RESULTS.json')==seal['original_result_sha256']
assert sha(R/'evidence-completion-replay/REPLAY-SEAL.json')==replay['seal_sha256']
assert datetime.datetime.fromisoformat(plan['sealed_utc'])<datetime.datetime.fromisoformat(identity['started_utc'])
assert datetime.datetime.fromisoformat(seal['sealed_before_replay_utc'])<datetime.datetime.fromisoformat(replay['started_and_completed_utc'])
for pin in plan['source_bindings'].values():assert sha(R/pin['snapshot_path'])==pin['sha256']
rom=read('sources/beam-static-rom.json');world=read('sources/world-v1.json');slope=rom['magnet_pitch_slope_per_m'];psi=rom['magnet_axial_shape'];A=np.array([[-1,0,0],[0,0,1],[0,1,0.]],float);origin=np.array([1.,.070,2.140]);xg=.096;zg=.005265
assert math.isclose(rom['phi_magnet_center'],1,abs_tol=1e-14);assert np.linalg.det(A)==1
rot=lambda a:np.array([[math.cos(a),0,math.sin(a)],[0,1,0],[-math.sin(a),0,math.cos(a)]])
def sat(d):
 ct=np.array(d['tip_center_beam_m']);cd=np.array(d['driver_center_beam_m']);rt=np.array(d['tip_rotation']);rd=np.array(d['driver_rotation'])
 gaps=[]
 for ax in [*rt.T,*rd.T,*[np.cross(i,j) for i in rt.T for j in rd.T]]:
  if np.linalg.norm(ax)<1e-12:continue
  u=ax/np.linalg.norm(ax);gap=abs((cd-ct)@u)-np.sum(np.abs(rt.T@u)*.005)-np.sum(np.abs(rd.T@u)*.010);gaps.append(float(gap))
 value=max(gaps);assert value>1e-12;assert math.isclose(value,d['contact']['surface_distance_lower_bound_m'],rel_tol=1e-12,abs_tol=1e-14);return value
fd=[];quadratures=[];examples={};maxmoment=0.;contacts=[];repeat=0
assert len(original['states'])==len(replay['states'])==len(plan['states'])==5
for state,old,new in zip(plan['states'],original['states'],replay['states']):
 assert state==old['state']==new['state'];a=math.radians(state['angle_deg']);q=state['q_m']
 driver_world=np.array([.856*math.cos(a)-.045*math.sin(a),.856*math.sin(a)+.045*math.cos(a),2.14]);driver=A@(driver_world-origin)
 assert len(old['orders'])==len(new['orders'])==3
 for n,oo,no in zip(plan['quadrature_orders'],old['orders'],new['orders']):
  d=no['nominal'];assert oo['quadrature_order']==no['quadrature_order']==n
  for k in ['mutual_potential_J','force_beam_N','tip_torque_about_COM_beam_N_m','generalized_force_N']:assert d[k]==oo[k];repeat+=1
  t=np.array(d['tip_center_beam_m']);rt=np.array(d['tip_rotation']);rd=np.array(d['driver_rotation']);F=np.array(d['force_beam_N']);T=np.array(d['tip_torque_about_COM_beam_N_m']);Td=np.array(d['driver_torque_about_COM_beam_N_m'])
  assert np.allclose(t,[xg+psi*q,0,zg+q],rtol=0,atol=1e-14)
  assert np.allclose(d['driver_center_beam_m'],driver,rtol=0,atol=3e-15)
  assert np.allclose(rt,rot(-slope*q),rtol=0,atol=1e-14);assert np.allclose(rd,rot(a),rtol=0,atol=1e-14)
  for r in (rt,rd):assert np.allclose(r@r.T,np.eye(3),rtol=0,atol=1e-14);assert abs(np.linalg.det(r)-1)<1e-14
  Q=float(F[2]+psi*F[0]-slope*T[1]);assert abs(Q-d['generalized_force_N'])<1e-14
  terms={'transverse_Fz_N':float(F[2]),'axial_virtual_work_N':float(psi*F[0]),'rotational_virtual_work_N':float(-slope*T[1])}
  for k,v in terms.items():assert abs(v-d['projection_terms'][k])<1e-14
  balance=T+Td+np.cross(t-driver,F);maxmoment=max(maxmoment,float(np.linalg.norm(balance)));assert np.linalg.norm(balance)<1e-14
  contacts.append(sat(d))
  assert len(no['raw_perturbation_pairs'])==3
  for h,pair,older in zip(plan['q_central_difference_steps_m'],no['raw_perturbation_pairs'],oo['q_energy_finite_differences']):
   assert pair['h_m']==older['h_m']==h
   for sign,label in [(1,'plus'),(-1,'minus')]:
    z=pair[label];assert z['q_m']==q+sign*h;assert np.allclose(z['tip_center_beam_m'],[xg+psi*z['q_m'],0,zg+z['q_m']],rtol=0,atol=1e-14);contacts.append(sat(z))
   energy=-(pair['plus']['mutual_potential_J']-pair['minus']['mutual_potential_J'])/(2*h);err=energy-Q
   assert energy==pair['minus_dU_dq_N']==older['minus_dU_dq_N'];repeat+=1
   tol=plan['predeclared_numeric_checks']['virtual_work_abs_plus_relative_N'][0]+plan['predeclared_numeric_checks']['virtual_work_abs_plus_relative_N'][1]*abs(Q)
   assert abs(err)<=tol and pair['virtual_work_passed'] and older['passed']
   fd.append({'state':state['id'],'order':n,'h_m':h,'energy_gradient_N':energy,'projected_Q_N':Q,'absolute_difference_N':abs(err),'tolerance_N':tol})
  if n==10 and state['id'] in ('closed_zero','rotated_positive'):
   oldF=np.array(oo['legacy_fixed_tip_force_beam_N']);examples[state['id']]={'legacy_Fz_N':float(oldF[2]),'new_Fz_N':float(F[2]),'new_generalized_Q_N':Q,'old_new_force_vector_difference_norm_N':float(np.linalg.norm(F-oldF)),'Fz_change_from_pose_N':float(F[2]-oldF[2]),'added_axial_work_N':terms['axial_virtual_work_N'],'added_torque_work_N':terms['rotational_virtual_work_N'],'total_newQ_minus_oldFz_N':float(Q-oldF[2]),'same_pose':q==0,'same_q_vertical_normalization':True,'same_configuration_tangent':False}
 q6=old['orders'][1]['generalized_force_N'];q10=old['orders'][2]['generalized_force_N'];change=q10-q6;tol=plan['predeclared_numeric_checks']['quadrature_6_to_10_abs_plus_relative_Q_N'][0]+plan['predeclared_numeric_checks']['quadrature_6_to_10_abs_plus_relative_Q_N'][1]*abs(q10)
 assert abs(change)<=tol;assert change==old['quadrature_check']['order6_to10_Q_change_N'];quadratures.append({'state':state['id'],'order6_to10_change_N':change,'tolerance_N':tol})
assert len(fd)==45 and repeat==105
assert max(x['absolute_difference_N'] for x in fd)==summary['maximum_virtual_work_absolute_error_N']
result={'schema':'bf-independent-retained-magnetic-interface-review-v1','status':'PASS_RETAINED_STATIC_IDENTITY_AND_ARITHMETIC_ONLY','new_force_evaluations':0,'provider_imports':0,'dynamic_runs':0,'plan_sha256':sha(R/'STATIC-PLAN.json'),'source_implementation_sha256':identity['implementation_sha256'],'original_results_sha256':sha(R/'outputs/STATIC-RESULTS.json'),'raw_replay_sha256':sha(R/'evidence-completion-replay/RAW-REPLAY-RESULTS.json'),'states':5,'nominal_quadrature_rows':15,'raw_energy_derivatives_recomputed':45,'original_replay_equalities_checked':repeat,'replay_is_independent_evidence':False,'maximum_virtual_work_difference_N':max(x['absolute_difference_N'] for x in fd),'maximum_6_to10_Q_change_N':max(abs(x['order6_to10_change_N']) for x in quadratures),'maximum_moment_balance_residual_N_m':maxmoment,'all_105_nominal_and_perturbation_OBBs_separated':True,'minimum_including_nominal_separation_lower_bound_m':min(contacts),'same_work_coordinate_comparison':False,'comparison_interpretation':'Both q values normalize vertical magnet-COM displacement, but legacy is fixed-orientation pure translation and new mode has axial/rotational motion. Force differences show nontransferability, not a legacy numerical error. Identical q=0 poses still have different virtual tangents.','examples':examples,'derivative_checks':fd,'quadrature_checks':quadratures,'source_or_physical_magnet_model_independently_validated':False}
O.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['derivative_checks','quadrature_checks']},indent=2))
