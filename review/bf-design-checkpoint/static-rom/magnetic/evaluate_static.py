"""Execute only the frozen five-state plan, with its numerical perturbations."""
from pathlib import Path
import datetime,hashlib,json,math
import numpy as np
from magnetic_interface import StaticMagneticInterface,VERSION,LEGACY_VERSION,jsonable
ROOT=Path(__file__).resolve().parent

def write(name,obj):
    p=ROOT/'outputs'/name
    if p.exists():raise RuntimeError('Refuse to replace retained output: '+str(p))
    p.write_text(json.dumps(jsonable(obj),indent=2,allow_nan=False)+'\n')

def main():
    m=StaticMagneticInterface()
    identity={'provider_version':VERSION,'legacy_identity':LEGACY_VERSION,'plan_sha256':hashlib.sha256((ROOT/'STATIC-PLAN.json').read_bytes()).hexdigest(),
      'implementation_sha256':hashlib.sha256((ROOT/'magnetic_interface.py').read_bytes()).hexdigest(),
      'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'static_voltage_V':0,'q_only_kinematics':True,'physical_qualified':False,'native_equivalent':False,
      'extra_magnetic_states':0,'table_sweeps':0,'time_integrations':0,'equilibrium_solves':0}
    write('EVALUATION-IDENTITY.json',identity)
    frames=[]
    # Finish frame/sign/polarity verification before any magnetic evaluation.
    for s in m.plan['states']:
        a=math.radians(s['angle_deg']);q=s['q_m']
        tip,driver,p=m.pose(a,q)
        xd=m.nominal_tip_world[0]-m.plan['gap_m'];yd=m.world['geometry']['nominal_driver_world_m'][1]
        expected_relative=np.array([m.nominal_tip_world[0]-xd*math.cos(a)+yd*math.sin(a)-m.rom['magnet_axial_shape']*q,
                                   0,xd*math.sin(a)+yd*math.cos(a)-m.nominal_tip_world[1]-q])
        relative_error=float(np.max(np.abs(driver.center-tip.center-expected_relative)))
        if relative_error>2e-15:raise ValueError('relative displacement formula mismatch, no sign correction allowed')
        if s['id']=='closed_zero':
            if not np.allclose(driver.center-tip.center,[.048,0,-.030265],atol=2e-15,rtol=0):raise ValueError('rest CAD centers mismatch')
            if not np.array_equal(tip.rotation[:,0],[1,0,0]) or not np.array_equal(driver.rotation[:,0],[1,0,0]):raise ValueError('polarity mismatch')
        frames.append({'state_id':s['id'],'tip_center_beam_m':tip.center,'driver_center_beam_m':driver.center,
          'relative_formula_max_error_m':relative_error,'tip_rotation_det':np.linalg.det(tip.rotation),
          'driver_rotation_det':np.linalg.det(driver.rotation),'tip_magnetization_unit_beam':tip.rotation[:,0],
          'driver_magnetization_unit_beam':driver.rotation[:,0]})
    write('FRAME-VERIFICATION.json',{'verified_before_force_evaluation':True,'beam_origin_world_m':m.beam_origin_world,'beam_from_world':m.A,
          'transform_determinant':np.linalg.det(m.A),'canonical_rest_tip_world_m':m.beam_origin_world+m.A.T@m.tip_rest,'states':frames})
    rows=[]
    abs_tol,rel_tol=m.plan['predeclared_numeric_checks']['virtual_work_abs_plus_relative_N']
    quad_abs,quad_rel=m.plan['predeclared_numeric_checks']['quadrature_6_to_10_abs_plus_relative_Q_N']
    for state in m.plan['states']:
        a=math.radians(state['angle_deg']);q=state['q_m'];orders=[]
        for n in m.plan['quadrature_orders']:
            result=m.evaluate(a,q,n);fd=[]
            for h in m.plan['q_central_difference_steps_m']:
                up=m.evaluate(a,q+h,n)['mutual_potential_J']
                down=m.evaluate(a,q-h,n)['mutual_potential_J']
                value=-(up-down)/(2*h);error=value-result['generalized_force_N']
                tolerance=abs_tol+rel_tol*abs(result['generalized_force_N'])
                fd.append({'h_m':h,'minus_dU_dq_N':value,'difference_from_force_torque_N':error,
                           'absolute_error_N':abs(error),'predeclared_tolerance_N':tolerance,'passed':abs(error)<=tolerance})
            old=m.legacy_force(a,q,n)
            result.update({'q_energy_finite_differences':fd,'legacy_fixed_tip_force_beam_N':old,
                           'new_Q_minus_legacy_Fz_N':result['generalized_force_N']-old[2],
                           'legacy_warning':'fixed-tip transverse-only identity; not a valid substitute for the new generalized force'})
            orders.append(result)
        final=orders[-1];previous=orders[-2]
        change=final['generalized_force_N']-previous['generalized_force_N']
        tol=quad_abs+quad_rel*abs(final['generalized_force_N'])
        quadrature={
          'order4_to6_Q_change_N':orders[1]['generalized_force_N']-orders[0]['generalized_force_N'],
          'order6_to10_Q_change_N':change,
          'order6_to10_F_vector_change_N':np.linalg.norm(final['force_beam_N']-previous['force_beam_N']),
          'order6_to10_torque_vector_change_N_m':np.linalg.norm(final['tip_torque_about_COM_beam_N_m']-previous['tip_torque_about_COM_beam_N_m']),
          'order6_to10_U_change_J':final['mutual_potential_J']-previous['mutual_potential_J'],
          'predeclared_Q_tolerance_N':tol,'passed':abs(change)<=tol,
          'interpretation':'Observed convergence at these states only; neither a rigorous remainder bound nor whole-domain qualification'}
        rows.append({'state':state,'angle_rad':a,'orders':orders,'quadrature_check':quadrature})
    write('STATIC-RESULTS.json',{'identity':identity,'states':rows})
    summary={
      'state_count':len(rows),'nominal_new_evaluations':15,'q_perturbation_evaluations':90,'legacy_comparison_evaluations':15,
      'all_virtual_work_checks_passed':all(f['passed'] for row in rows for order in row['orders'] for f in order['q_energy_finite_differences']),
      'all_6_to10_quadrature_checks_passed':all(row['quadrature_check']['passed'] for row in rows),
      'all_sampled_and_perturbed_magnets_separated':True,
      'maximum_virtual_work_absolute_error_N':max(f['absolute_error_N'] for row in rows for order in row['orders'] for f in order['q_energy_finite_differences']),
      'maximum_6_to10_Q_change_N':max(abs(row['quadrature_check']['order6_to10_Q_change_N']) for row in rows),
      'states_order10':[{'id':r['state']['id'],'Q_N':r['orders'][-1]['generalized_force_N'],
                         'U_J':r['orders'][-1]['mutual_potential_J'],
                         'terms_N':r['orders'][-1]['projection_terms'],
                         'legacy_Fz_N':r['orders'][-1]['legacy_fixed_tip_force_beam_N'][2],
                         'clearance_lower_bound_m':r['orders'][-1]['contact']['surface_distance_lower_bound_m']} for r in rows],
      'status':'conditional_static_interface_only',
      'limitations':['V=0 retained q-only pose; no voltage-dependent axial shift',
        'Fx axial resultant and torque-driven discarded modes are not statically recondensed',
        'quadrature/chain-rule checks are not independent physical or FEM validation',
        'inherited angle/gap/q support is computational, not a proven accuracy/safety range',
        'collision coverage only these magnet OBB samples and perturbations, not full assembly or continuous path',
        'no native material recovery, dynamic coupling, force table, equilibrium, damping or mission result']}
    write('SUMMARY.json',summary)
    print(json.dumps(jsonable(summary),indent=2,allow_nan=False))
if __name__=='__main__':main()
