import datetime, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
plan={'schema_version':'bf-causal-diagnostic-plan-v2','model_version':'bf-event-apparatus-v2-fixed-reset-ports',
'evaluator_version':'bf-causal-evaluator-v2-postactivation','scope':'Generic apparatus software diagnostic, not LTC3588, vendor model, authoritative door-world, or hardware qualification',
'feedback_modes':['reciprocal','no-feedback'],'idle_current_a':{'baseline':1e-6,'treatment':.01},
'max_steps_s':[1e-5,5e-6,2.5e-6],'duration_s':.25,'maximum_scientific_solves':12,'retries':0,'per_run_timeout_s':40,
'solver':{'engine':'ngspice','version':'44.2','path':'/workspace/shared/current-cache-integration-20261001/toolchains/ngspice/usr/bin/ngspice','reltol':1e-5,'abstol':1e-11,'vntol':1e-8,'method':'gear','export_significant_digits':17,'initialization':'uic, all physical storage initially zero'},
'fixed_control':{'timer_reset_tau_s':1e-6,'start_v':.8,'stop_v':.5,'output_v':.4,'semantics':'mathematical fixture assumptions, not datasheet parameters or measured firmware'},
'observation_window_s':[.1,.25],'observation_points':501,'primary_observable':'max absolute treatment-minus-baseline displacement on fixed equally spaced grid, piecewise-linear interpolation; same finest step',
'criteria':{'activation':'Each case has finite strictly positive load before observation starts, and positive post-stage idle samples in the observation window',
'max_finest_relative_trajectory_change':.01,'displacement_floor_m':1e-8,'causal_separation_multiplier':10,'negative_control_refinement_multiplier':5,
'energy_absolute_floor_j':1e-8,'energy_relative_tolerance':.03},
'criteria_rationale':{'convergence':'1% is a prospective numerical adequacy screen for generic fixture trajectories, not hardware tolerance or a convergence-order proof',
'causal_separation':'Effect must be one order of magnitude above sum of both finest refinement changes, observed no-feedback difference and the solver-coordinate floor',
'displacement_floor':'10 nm maps the fixed vntol=1e-8 onto q, represented as a circuit voltage; it is a conservative floor, not a rigorous global bound',
'negative_control':'Five times summed finest refinement variation plus floor accommodates adaptive-grid variation; not exact-bit equality',
'energy':'Inherited 3%/10 nJ screen is retained, with separate mechanical, piezo and storage ports; no reduced old threshold'},
'energy_sign_contract':{'reaction':'positive theta*Vp is mechanical sink; mechanical power theta*Vp*u',
'generator':'positive theta*u is electrical source 0 to p; generated power theta*u*Vp',
'bridge_input':'positive i(Vpiezo_port), p to bridge_p; power Vp*i(Vpiezo_port)',
'storage_input':'positive i(Vsense), rect to cap; power (Vcap-Vneg)*i(Vsense)',
'no_feedback':'reaction disabled, generator retained; generated work is artificial external electrical work, not passive energy generation',
'bridge':'input minus output is net absorbed work including device energy change, not uniquely diode loss',
'integration':'Use first-to-last exported sample and measured energy differences, do not invent zero-time exported sample'},
'stop_conditions':['Solver error, timeout, incomplete or nonfinite output stops remaining solves','After exactly 12 completed cells, retain all failed/inconclusive criteria, no adaptive tuning','No integrated door-world comparison or startup transient while contract/model evidence missing'],
'production_change':False,'old_gate_disposition':'Retained failed original assertion and sealed outputs; independent replacement candidate only'}
path=ROOT/'contracts/prospective-plan-v2.json'
if path.exists(): raise SystemExit('Already frozen: do not overwrite')
path.write_text(json.dumps(plan,indent=2)+'\n')
files=[path,ROOT/'contracts/base-fixture-v2.json',ROOT/'src/event_apparatus_v2.py',ROOT/'src/causal_evaluator_v2.py']
seal={'schema_version':'bf-prospective-plan-seal-v1','sealed_before_scientific_runs':True,'scientific_runs_started':0,
'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
(ROOT/'PLAN-SEAL.json').write_text(json.dumps(seal,indent=2)+'\n')
print(json.dumps(seal,indent=2))
