"""Fix one E3 Task and two reasoned private inputs before any solve."""
from copy import deepcopy
from datetime import datetime,timezone
import json
import math
import shutil
from common import HERE,ROOT,CAN,STUDY,SRC,PACKAGE,save,digest,identity


def main():
    private=STUDY/'private'
    assert not (private/'freeze.json').exists(),'E3_TASK_ALREADY_FIXED_NO_REPLACEMENT'
    free=shutil.disk_usage(ROOT).free
    assert free>=11_000_000_000
    catalog_path=CAN/'studies/pqe20261022/shared/door-tasks.json'
    base=json.loads(catalog_path.read_text())['DOOR-DEV-D04-v1']
    task=deepcopy(base)
    task.update(task_id='DOOR-E3LC-SCOPE-20261023-v1',family_id='E3-SCOPE-DEVELOPMENT',
                exposure='prospectively fixed development mechanism task; exposed existing DOOR apparatus, not an unseen family or transfer test',
                description='The current door device is not reporting reliably. Explore the current capacitor/ESR adjustment scope, and if evidence warrants, revise that temporary scope within the full authorized device and mechanism domain. The external events, deadlines and installation requirements remain fixed.',
                allowed_for_learning=False)
    motion=[]
    for start in (22.0,34120.0,74040.0):
        at=start
        for a,b,speed in ((0,25,40),(25,65,54),(65,90,50)):
            end=at+(b-a)/speed
            motion.append({'start_s':at,'end_s':end,'start_deg':a,'end_deg':b});at=end
        at+=1.1
        for a,b,speed in ((90,60,50),(60,20,54),(20,0,40)):
            end=at+(a-b)/speed
            motion.append({'start_s':at,'end_s':end,'start_deg':a,'end_deg':b});at=end
    task['motion']=motion
    design=task['initial_design']
    design.update(capacitance_f=.0001,esr_ohm=5.0,startup_v=2.9,brownout_v=1.8,tx_gate_v=2.9,
                  debounce_s=.07,persistent_queue=True,retry_s=.1,
                  mechanism={'stroke_m':.006,'cam_base_radius_m':.008})
    task['initial_problem']={'active_variables':['capacitance_f','esr_ohm'],
        'groups':[['capacitance_f','esr_ohm']],
        'fixed_choices':{k:deepcopy(v) for k,v in design.items() if k not in ('capacitance_f','esr_ohm')},
        'assumptions':['The initial capacitor/ESR-only scope is temporary, not a user constraint.',
                       'Every method may remove provisional fixed choices and activate any variable in the complete Task design_domain.',
                       'Source, service and event truth are fixed; an individual candidate failure is not a whole-domain conclusion.'],
        'local_objective':'Meet every frozen service constraint with legal authorized edits.'}
    task['qualification_claim']='Constructed E3 development task. Private eligibility checks do not establish Agent capability or hardware validity.'
    task['material_sources']['e3_lineage']={'template_task_id':base['task_id'],'template_task_sha256':identity(base),
        'construction':'Three cold-start cycles with a 40/54/50-degree-per-second piecewise opening and 50/54/40 closing, fixed before results; initial legal mechanism and power settings differ jointly from prior D04/D10/M3.',
        'not_relabelled':'Existing exposed apparatus and equations reused; not the old halfspeed trajectory or gateway translation; no held-out-family claim.',
        'permissions':'Initial fixed choices reversible within complete public design_domain, equally for all policies.'}
    expanded=deepcopy(design)
    expanded.update(startup_v=2.2,tx_gate_v=2.2,mechanism={'stroke_m':.0085,'cam_base_radius_m':.007})
    expanded_problem=deepcopy(task['initial_problem'])
    expanded_problem.update(active_variables=list(task['design_domain']),
        groups=[['mechanism'],['capacitance_f','esr_ohm','startup_v','brownout_v','tx_gate_v'],['debounce_s','persistent_queue','retry_s']],fixed_choices={})
    inputs={'initial':{'Task':task,'Design':design,'Problem':task['initial_problem'],'reason':'The single common initial input; no local capacitor sweep.'},
            'expanded-reference':{'Task':task,'Design':expanded,'Problem':expanded_problem,
                'reason':'A priori legal longer stroke and lower startup/transmit gates jointly address the all-time local voltage barrier; exactly one existence witness, not a parameter optimum.'}}
    sources={n:digest(SRC/n) for n in ('door_model.py','door_program.py','engineering.py','executor.py','evaluator.py')}
    # Private necessary exclusion for the entire local C/ESR domain, both allowed dt.
    peak_speed=max(abs((r['end_deg']-r['start_deg'])/(r['end_s']-r['start_s'])) for r in motion)
    voltage_barrier=500*design['mechanism']['stroke_m']*math.radians(peak_speed)-.3
    cmin=task['design_domain']['capacitance_f']['min']
    hmax=max(task['integration']['allowed_dt_s']);hmin=min(task['integration']['allowed_dt_s'])
    monotone_ratio=hmax*(1/1500+1/task['components']['leakage_ohm'])/(2*cmin)
    intervals=[]
    for row in motion:
        a,b=max(0,row['start_s']-.05),min(task['duration_s'],row['end_s']+task['service']['receive_deadline_s']+.2)
        if intervals and a<=intervals[-1][1]:
            intervals[-1][1]=max(b,intervals[-1][1])
        else:
            intervals.append([a,b])
    steps=sum(math.ceil((b-a)/hmin)+2 for a,b in intervals)
    numeric_roundoff_bound=steps*task['components']['max_v']/2**28
    bound={'schema':'pqe-e3-private-local-necessary-bound-v1','Task_sha256':identity(task),
        'local_active_variables':task['initial_problem']['active_variables'],
        'local_domain':{k:task['design_domain'][k] for k in task['initial_problem']['active_variables']},
        'frozen_other_choices':task['initial_problem']['fixed_choices'],'initial_bus_v':task['initial']['capacitor_v'],
        'maximum_motion_speed_deg_s':peak_speed,'rectified_open_circuit_upper_v':voltage_barrier,
        'discrete_midpoint_monotonicity_ratio':monotone_ratio,'maximum_OFF_step_count_both_dt':steps,
        'conservative_accumulated_bisection_width_v':numeric_roundoff_bound,
        'whole_horizon_voltage_upper_v':voltage_barrier+numeric_roundoff_bound,
        'startup_v':design['startup_v'],'strict_margin_v':design['startup_v']-voltage_barrier-numeric_roundoff_bound,
        'derivation':['For the frozen local mechanism, |emf|<=K*stroke*|omega|max since |sin(2theta)|<=1; blocking bridge current is max((emf-V-.3)/1500,0).',
            'Starting at zero, capacitor bus cannot exceed U=max(emf)-.3: at/above U there is no positive source current; leakage is nonnegative. Before startup the program is OFF and its load is zero, so ESR cannot change this bound.',
            'The implicit midpoint OFF update is monotone for h*(1/Rcoil+1/Rleak)/(2*Cmin)<1. It preserves the barrier for every legal capacitance and both registered dt; no-motion idle is a decay.',
            'Executor integrates only the merged event windows when OFF. Accumulating one full 28-bisection interval width per worst-case step, without using contraction, still leaves the bus strictly below startup.',
            'Induction therefore keeps the program OFF for the entire horizon, so no wire frame can exist. Any external stable event then makes complete service impossible within this local scope. No crossing-time startup assumption is used.'],
        'scope':'Only this frozen Task and local C/ESR scope with other choices fixed. Not an exclusion of the full legal Task domain or all door topologies.',
        'private':'A/S0 only; never deliver proof, bound, witness numbers or witness outcome to B/participants/HG.'}
    assert monotone_ratio<1 and bound['strict_margin_v']>.1
    save(private/'task.json',task)
    save(private/'inputs.json',inputs)
    save(private/'local-necessary-bound.json',bound)
    freeze={'schema':'pqe-e3-a-prospective-freeze-v1','package':PACKAGE,'at_utc':datetime.now(timezone.utc).isoformat(),
        'task_path':str(private/'task.json'),'task_file_sha256':digest(private/'task.json'),'task_sha256':identity(task),
        'input_path':str(private/'inputs.json'),'input_file_sha256':digest(private/'inputs.json'),
        'input_hashes':{n:identity(v) for n,v in inputs.items()},'scientific_sources':sources,
        'source_catalog_path':str(catalog_path),'source_catalog_sha256':digest(catalog_path),
        'bound_path':str(private/'local-necessary-bound.json'),'bound_file_sha256':digest(private/'local-necessary-bound.json'),
        'available_before_bytes':free,'estimated_peak_bytes':1000000000,'retained_cap_A_bytes':80000000,
        'limits':{'private_new_inputs_authorized_max':12,'prospective_attempts':2,'paid_requests':0,'native':0,'wall_cap_s':120},
        'stop':'Run the two frozen inputs once. If no valid local exclusion and expanded PASS, close eligibility without changing Task, tuning or paid E3. No unused private budget transferred.'}
    save(private/'freeze.json',freeze)
    save(STUDY/'shared/task-public.json',{'schema':'pqe-e3-public-task-v1','package':PACKAGE,'Task':task,
        'Design':design,'Problem':task['initial_problem'],'allowed_for_learning':False,
        'exposure':'Development mechanism task fixed before participant results; public initial design/scope are identical except the declared scope-matched intervention.'})
    save(STUDY/'shared/task-materials.json',{'schema':'pqe-e3-public-materials-v1','package':PACKAGE,
        'permissions':'All groups share the complete original Task design_domain, observations, tools and scientific/evaluator modules. Any group may remove provisional fixed choices and enlarge active variables except where its declared method policy chooses not to.',
        'model_facts':'x=L*(1-cos(2theta))/2; emf=K*L*sin(2theta)*omega; blocking bridge I=max((abs(emf)-V-.3)/1500,0). Capacitor/ESR, powered level-contact program, paid atomic SAVE/ACK and CRC receiver. Full coefficients/service/motion/domain are in Task and common source materials.',
        'program_facts':'No unpowered clock or edge history. Startup observes capacitor voltage, TX requires its gate and completed power. Persistent records survive resets only when selected.',
        'scope_intervention':'Initial Problem is capacitor/ESR only. The scope-matched comparator opens the complete legal variable set without supplying any reference value, diagnostic proof or expected outcome.',
        'private_boundary':'No reference design, qualification verdict, exclusion derivation or hidden evaluation is supplied. All methods receive the same public initial execution projection.',
        'claim_boundary':'Constructed development mechanism task; no unseen-family, optimal-design, global topology or hardware claim.'})
    print(json.dumps({'status':'ONE_TASK_AND_TWO_REASONED_INPUTS_FROZEN','task_sha256':identity(task),
        'private_freeze':str(private/'freeze.json'),'private_bound_margin_v':bound['strict_margin_v'],'free_before_bytes':free}))


if __name__=='__main__':
    main()
