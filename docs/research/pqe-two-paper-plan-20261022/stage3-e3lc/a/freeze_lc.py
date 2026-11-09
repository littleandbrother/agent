"""One new LC development scenario; no old qualification execution/results."""
from copy import deepcopy
from datetime import datetime,timezone
import json
import shutil
from common import HERE,ROOT,CAN,STUDY,SRC,PACKAGE,save,digest,identity


def main():
    private=STUDY/'lcpv-private'
    assert not (private/'freeze.json').exists(),'LC_INSTANCE_ALREADY_FIXED_NO_REPLACEMENT'
    free=shutil.disk_usage(ROOT).free
    assert free>=11_000_000_000
    original_path=CAN/'studies/pqe20261022/engineering/lc_pv_task.draft.json'
    original=json.loads(original_path.read_text())
    task=deepcopy(original)
    instance='LC-PV-E3LC-DEV-20261023-v1'
    # The consumer's fixed task_id is its contract identity. The complete new
    # scenario has a separate instance_id and different complete input hash.
    task.update(instance_id=instance,allowed_for_learning=False,
        status='EXECUTABLE_CONSTRUCTED_WORLD_DEVELOPMENT_INSTANCE',
        description='Preserve the specified interior air-point temperature history through the declared dark/disconnected journey, then deliver both old history and new samples within the unchanged service deadlines.')
    task['service'].update(dark_interval_s=[23400,66600],recovery_at_s=66600,
        recovery_old_history_deadline_s=66720)
    task['gateway_windows_s']=[[0,16200],[66600,86400]]
    optical=task['optical_environment']
    optical['irradiance_schedule_w_m2']=[[0,23400,.45],[23400,66600,0.0],[66600,86400,.45]]
    optical['uniform_shading_transmission']=[[0,6300,.75],[6300,9900,.4],[9900,66600,.9],
                                           [66600,72000,.6],[72000,86400,.85]]
    thermal=task['thermal_reference']
    thermal.update(nominal_tau_s=24.0,nominal_bias_c=.05,
        air_truth_piecewise_linear_knots_s_c=[[0,5],[10200,5],[10800,8.5],[11700,8.5],[12300,5.5],
            [46800,5.5],[47700,9],[48900,9],[49800,5],[86400,5]])
    task['clock_reference']['nominal_rate_error_ppm']=-15.0
    # Extract the reusable model coefficients only. No old Design, Program,
    # purpose, reference outcome or old raw is copied into this new task.
    model_profile_path=CAN/'studies/pqe20261022/e2main/lcpv-private/inputs.json'
    model_profile=deepcopy(json.loads(model_profile_path.read_text())['reference']['Profile'])
    task['pv_consumer_contract']['coefficient_status']='BOUND_TO_EXPLICIT_CONSTRUCTED_PROFILE; NOT_VENDOR_OR_MEASURED'
    task['qualification_gaps']=['Measured/calibrated profile, switching, physical RF/MCU/NVM and continuous-grid convergence remain outside this discrete-world claim.']
    task['next_owner']='S0 runs one default-H0 development episode; no H formation, qualification rerun or transfer claim.'
    task['generation_receipt']={'rule_source_sha256':digest(original_path),
        'rule':'Explicit new joint light/shadow/darkness/connectivity/thermal/clock block, selected before one initial observation and all H0 results.',
        'dark_start_s':23400,'dark_duration_s':43200,'irradiance_lit_w_m2':.45,
        'uniform_shadow_domain':[.2,1.0],'probe_tau_s':24,'probe_bias_c':.05,'clock_rate_ppm':-15,
        'exposure':'New development realization, not a held-out F2 test; allowed_for_learning=false.'}
    flat={'area_cm2':25.0,'capacitance_f':.012,'esr_ohm':8.0,'startup_v':2.5,'brownout_v':2.2,
          'persistent_records':True,'nvm_capacity_records':2048,
          'sample_period_s':60.0,'ack_spacing_s':.25,'retry_s':45.0}
    domain={
        'area_cm2':{'kind':'number','min':10.0,'max':50.0},
        'capacitance_f':{'kind':'number','min':.001,'max':1.0},
        'esr_ohm':{'kind':'number','min':.1,'max':100.0},
        'startup_v':{'kind':'number','min':2.3,'max':3.6},
        'brownout_v':{'kind':'number','min':2.2,'max':3.2},
        'persistent_records':{'kind':'boolean'},
        'nvm_capacity_records':{'kind':'integer','min':1,'max':4096},
        'sample_period_s':{'kind':'number','min':30.0,'max':60.0},
        'ack_spacing_s':{'kind':'number','min':0.0,'max':2.0},
        'retry_s':{'kind':'number','min':10.0,'max':3600.0}}
    program_fixed={'ack_drop_first_n':1,'rank':{'op':'-','args':[{'const':0},{'field':'seq'}]},
        'receiver_dedup':True,'clock_continuation':'Only while powered; reset loses synchronization; no unpowered clock.',
        'gateway_beacon':'Current available beacon while powered; charged sync phase on initial/new availability. No future schedule access.',
        'storage':'Atomic SAVE/ACK after paid completion; interrupted pending write discarded; persistent image survives reset only when enabled.'}
    problem={'active_variables':list(domain),'groups':[['area_cm2','capacitance_f','esr_ohm','startup_v','brownout_v'],
        ['persistent_records','nvm_capacity_records'],['sample_period_s','ack_spacing_s','retry_s']],
        'fixed_choices':{},'assumptions':['Original 24h service and spatial/optical hard bounds remain fixed.',
            'The declared finite development action box changes real supply/activity/record/receive behavior.',
            'A sampling gap or unknown-time record is not valid continuous history.'],
        'local_objective':'Meet every applicable frozen LC-PV service; report scope of any remaining failure.'}
    public_task={'task_id':instance,'consumer_contract_task_id':task['task_id'],'instance_id':instance,
        'description':task['description'],'allowed_for_learning':False,
        'exposure':'Development-only joint scenario fixed before initial and H0; never retroactively F2 or formation/selection.',
        'duration_s':task['duration_s'],'target':task['target'],'service':task['service'],'initial':task['initial'],
        'gateway_windows_s':task['gateway_windows_s'],'optical_environment':optical,
        'thermal_contract':{k:v for k,v in thermal.items() if k!='air_truth_piecewise_linear_knots_s_c'},
        'clock_contract':task['clock_reference'],'design_domain':domain,
        'fixed_program_semantics':program_fixed,
        'observations':'Only powered quantized samples, device record/time intervals, actual wire/receiver, activity and supply/energy facts; no ideal air truth or hypothetical missing samples.',
        'domain_scope':'Finite development action box within the existing constructed consumer. Sampling30..60s and retries10..3600s bound retained event output; the original60s service maximum remains unchanged. No claim to every configuration the low-level consumer can encode.'}
    public={'schema':'pqe-e3lc-public-lc-task-v1','package':PACKAGE,'Task':public_task,
        'Design':flat,'Problem':problem,'Profile':model_profile,
        'design_fields':['area_cm2','capacitance_f','esr_ohm','startup_v','brownout_v','persistent_records','nvm_capacity_records'],
        'program_fields':['sample_period_s','ack_spacing_s','retry_s'],
        'allowed_for_learning':False,
        'model_id':'pqe-lcpv-constructed-hybrid-20261023-v1',
        'world_profile_scope':'The same constructed world coefficients/1s semantics as qualified previously; only this new task and its initial design are public. No old four qualification designs/results or reference choices are supplied.',
        'host_boundary':'Selected air-point truth realization and complete final assessment remain host-only. Public check returns only service labels and observable facts.'}
    assert task['duration_s']==86400 and task['service']['continuous_new_sampling']['maximum_spacing_s']==60
    assert task['service']['recovery_delay_s']==120 and task['service']['new_sample_receive_max_delay_s']==10
    assert task['service']['cold_start_first_valid_receive_deadline_s']==1800
    assert task['service']['dark_interval_s'][1]-task['service']['dark_interval_s'][0]==43200
    assert original['target']==task['target'] and task['optical_environment']['legal_area_cm2']==[10,50]
    save(private/'host-task.json',task)
    save(STUDY/'shared/lcpv-task-public.json',public)
    freeze={'schema':'pqe-e3lc-lc-initial-freeze-v1','package':PACKAGE,'at_utc':datetime.now(timezone.utc).isoformat(),
        'task_id':instance,'consumer_contract_task_id':task['task_id'],'allowed_for_learning':False,
        'host_task_path':str(private/'host-task.json'),'host_task_file_sha256':digest(private/'host-task.json'),
        'host_task_sha256':identity(task),'public_path':str(STUDY/'shared/lcpv-task-public.json'),
        'public_file_sha256':digest(STUDY/'shared/lcpv-task-public.json'),'profile_sha256':identity(model_profile),
        'initial_design_sha256':identity(flat),'source_model_sha256':digest(SRC/'lcpv20261023.py'),
        'old_four_qualification_inputs_reexecuted':0,
        'limits':{'new_initial_scientific_inputs':1,'paid_requests':0,'native':0,'initial_wall_cap_s':120,
                  'A_retained_cap_bytes':80000000,'estimated_package_peak_bytes':1000000000},
        'available_before_bytes':free,'stop':'Run exactly one frozen initial. Preserve PASS/FAIL/UNKNOWN without changing instance/initial. Hand current public task and host consumer binding to S0; no A Agent/candidate run.'}
    save(private/'freeze.json',freeze)
    print(json.dumps({'status':'ONE_NEW_LC_DEVELOPMENT_TASK_FROZEN','task_id':instance,
                     'freeze_path':str(private/'freeze.json'),'freeze_sha256':digest(private/'freeze.json'),
                     'public_file_sha256':digest(STUDY/'shared/lcpv-task-public.json')}))


if __name__=='__main__':
    main()
