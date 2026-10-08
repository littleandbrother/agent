"""Independent, outcome-blind nominal task evaluation of D4 artifact facts."""
from .contracts import verify_design, digest

CHECKS = ('rom_domain','force_interpolation','energy_balance','drive_balance','program_power_fixed_point','time_step')

def check_candidate(binding, parameters):
    task=binding['task']
    if digest(task)!=binding['task_hash']:raise ValueError('SIMULATION_TASK_HASH_MISMATCH')
    if parameters.get('confirmation') is not True:raise ValueError('TASK_CONFIRMATION_REQUIRED')
    value=verify_design(parameters['candidate'])
    if value['frozen']!=task['frozen']:raise ValueError('DOOR_TASK_FROZEN_DRIFT')
    return value

def evaluate(binding, design, result, receiver):
    errors=[]
    try:check_candidate(binding,{'candidate':design,'confirmation':True})
    except (ValueError,KeyError) as exc:errors.append(str(exc))
    checks=result.get('checks',{});missing=[k for k in CHECKS if checks.get(k) is not True]
    eligible=not errors and not missing and result.get('run_status')=='completed'
    transmitted={(r.get('capture_id'),r.get('time_s'),r.get('payload_hex')) for r in receiver.get('transmitted',[])}
    valid=[];service=binding['task']['service']
    for r in receiver.get('delivered',[]):
        t=r.get('time_s')
        if type(t) in (float,int) and 0<=t<=service['deadline_s'] and r.get('payload_hex')==service['expected_payload_hex'] and (r.get('capture_id'),t,r.get('payload_hex')) in transmitted:valid.append(r)
    prediction=bool(valid) and result.get('metrics',{}).get('cold_start_reached') is True
    return {'schema_version':'simulation-task-evaluation-v2','task_id':binding['task']['id'],'task_hash':binding['task_hash'],
            'candidate_hash':digest(design),'input_violations':errors,'unpassed_numerical_checks':missing,
            'nominal_prediction_eligible':eligible,'nominal_task_status':('satisfied' if prediction else 'unsatisfied') if eligible else 'not_evaluable',
            'timely_correct_packets':len(valid),'first_correct_packet_s':min((r['time_s'] for r in valid),default=None),
            'design_ranking_eligible':eligible and checks.get('rotated_work_domain') is True,
            'full_rotated_FEM_coverage':False,'exactly_once_semantics_qualified':False,
            'product_verified':False,'hardware_calibrated':False,'scope':binding['task']['claim_boundary']}

