"""Bounded source-derived arithmetic. Imports no solver or firmware library."""
import ast,json
from pathlib import Path
from admission import ROOT,file_hash
S=ROOT.parent
old=S/'bf-simulation-chain/battery-world/scripts/door_case/simchain/firmware_receiver.py'
new=S/'current-source-reconciliation-20261001/checkout/battery-world/configs/reference_cases/closed-simulation/d2-nominal.json'
def literal_assignment(path,name):
 tree=ast.parse(path.read_text())
 for node in tree.body:
  if isinstance(node,ast.Assign) and any(isinstance(x,ast.Name) and x.id==name for x in node.targets):return ast.literal_eval(node.value)
 raise ValueError(name)
o=literal_assignment(old,'DEFAULTS');n=json.loads(new.read_text())['firmware']
a=[{'state':s,'duration_ms':o['durations_s'][s]*1000,'current_mA':o['currents_a'][s]*1000} for s in ['reset','clock','boot','init','read','payload','tx']]
b=[{'state':s,'duration_ms':n[s+'_ms'],'current_mA':n[s+'_mA']} for s in ['boot','init','tx']]
for rows in [a,b]:
 for r in rows:r['charge_uC']=r['duration_ms']*r['current_mA'];r['energy_at_constant_3p3V_uJ']=3.3*r['charge_uC']
def sums(rows):
 return {'states':rows,'duration_ms':sum(r['duration_ms'] for r in rows),'charge_uC':sum(r['charge_uC'] for r in rows),'energy_at_constant_3p3V_uJ':sum(r['energy_at_constant_3p3V_uJ'] for r in rows)}
v={'schema':'bf-startup-model-sufficiency-v1','scientific_solves':0,
 'sources':{'old_firmware':{'path':str(old),'sha256':file_hash(old)},'new_firmware_parameters':{'path':str(new),'sha256':file_hash(new)},'ADI':{'url':'https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf','revision':'C','sha256':'f1e52b155e35b2b5fe70ee05f5cdf130a577488df648703054bf2f57395c7c1d','research_copy_only':'/workspace/shared/primary-source-research-20261001/35881fc.pdf','redistributed':False,'printed_pages':[7,8,13],'figures':[1,6]}},
 'frozen_firmware_assumptions':{'historical_behavioral':sums(a),'pinned_native':sums(b),'evidence_class':'Arithmetic from executable frozen parameter values, all timings/currents unmeasured assumptions.', 'exclusions':['WAIT and first RESET sampling tick in native C','off and sleep draw','PGOOD/brownout aborts and repeated boots','sample quantization','output capacitor charge','PMIC/bridge/converter/clamp losses'], 'not_claimed':['measured binary consumption','exact transient mission energy','proof of feasibility','one firmware better than the other']},
 'existing_topology_rail_analysis':{
  'datasheet_relationship':'Ideal quasi-static relation: VIN2=min(VIN,4.8 V), CAP=max(VIN-4.8 V,0); CAP capacitor is between VIN and CAP.',
  'capacitance_uF':{'VIN_to_CAP':1.0,'VIN2_to_GND':4.7},
  'ideal_bypass_stored_energy_uJ_at_Vin':{str(x):.5*5.7*min(x,4.8)**2 for x in [1.8,3.67,4.8,5.05]},
  'ideal_input_plus_bypass_stored_energy_at_UVLO_5p05V_uJ':{str(ci):.5*ci*5.05**2+.5*5.7*4.8**2 for ci in [.1,.22,.47,1,10,47]},
  'interpretation':'65.664 uJ is real ideal stored energy in the two recommended bypass capacitors at their 4.8 V differential voltages. It is not established as an independent all-at-once post-UVLO gate. Before 4.8 V the ideal tracking relationship loads the input like an additional 5.7 uF. Internal rail charging dynamics and dissipation require their own qualification; these static estimates are not a universal start/no-start criterion.',
  'sub_UVLO_invariant_counterexample':{'scope':'Exact old-model invariant plus datasheet ideal quasistatic comparison; not a timed native experiment.', 'initial_aux_J':0,'UVLO_rise_V':5.05,'old_off_equation':'dEaux/dt=-Eaux/0.1 with startup=0','old_result_for_arbitrarily_long_sub_UVLO_input':'Eaux(t)=0','test_points':[{'Vin_V':x,'old_aux_uJ':0,'datasheet_ideal_settled_bypass_uJ':.5*5.7*x*x} for x in [2.5,4.5]],'settling_time_s':None,'settling_explanation':'No documented rail charging time constant is available. Claim is the incompatible settled relationships, not a finite-time convergence claim.'},
  'old_model_difference':'Input can first reach5.05V while separate Eaux remains zero; then a1mA startup draw fills Eaux toward65.664uJ, blocking any output current until ready, and Eaux decays exponentially with0.1s tau whenever UVLO is off. Neither this staged timing nor the decay constant is qualified by source or measurements.',
  'consequence':'Changing the rail model changes input loading, UVLO timing and electrical back-action on mechanics. Existing trajectory values cannot be carried into the alternative model as fixed harvested-energy supply.',
  'evidence_blockers':['The pinned vendor deck omits CAP/VIN2 voltages and currents from .save, so old RAW alone cannot establish these missing rail dynamics. A separately versioned observable extension and bounded new diagnostic is needed.', 'The licensed macro-model .SUBCKT port declaration/order has not been independently verified; obtain declaration metadata and identity before assuming package pin numbering equals model order. No full licensed model needs to be distributed.'],
  'do_not':'Do not delete stored energy, substitute a zero threshold, or claim lower startup energy without a changed physical topology and complete energy accounting.'},
 'alternative_circuit_contract':{
  'id':'HYP-LOWVIN-3V3-v1','status':'proposed_blocked_component_and_model_qualification','claim':'Testable design hypothesis only, no successful reference.',
  'source_boundary':'ADI p13/Fig6 permits VIN2 tied to VIN and CAP to GND for input limited below6V; its figure is1.8V output. This hypothesis retains3.3V and must independently qualify that configuration.',
  'fixed_world':{'opening_s':2,'angle_deg':65,'observation_s':4,'electrical_initial_V':0,'external_electrical_work_J':0,'no_extra_operations':True},
  'wiring':{'CAP':'GND','VIN2':'VIN','D1':'VIN2','D0':'GND','VOUT_target_V':3.3,'separate_Ccap_uF':0,'separate_Cvin2_uF':0,'Cin_uF':47,'Cout_uF':100,'L_uH':10},
  'parts_rule':'Use the pinned native baseline values for common components; removing bypass capacitors is an explicit topology change. Select an actual protection BOM and bind models before any run.',
  'voltage_guards':{'datasheet_condition_Vin_strictly_below_V':6.0,'proposed_engineering_worst_case_Vin_ceiling_V':5.8,'includes':['clamp_tolerance','dynamic_overshoot','temperature','all_door_conditions','component_variation'],'maximum_allowed_raw_transient_above_guard':0,'output_target_must_not_be_silently_lowered':True},
  'clamp_and_leakage':{'clamp_part':None,'nominal_5p6V_label_not_sufficient':True,'reverse_leakage_I_of_V_T_required':True,'junction_capacitance_required':True,'dynamic_resistance_and_pulse_energy_required':True,'all_clamp_and_leakage_current_in_source_and_energy_ledger':True,'leakage_budget_A':None,'budget_rule':'Freeze after BOM/source review. No zero-leak ideal clamp permitted. Missing budget prevents run admission.'},
  'firmware':'Pinned native program and its declared assumptions unchanged for topology contrast. No current/duration reduction. Any later firmware optimization needs changed source, build hash and independent timing/current bounds.',
  'required_raw_observables':['q','qdot','magnetic_force','piezo_voltage','piezo_current','VIN','VIN2','VIN-CAP','VOUT','PGOOD','rail_currents','clamp_current','load_current','complete_TX','receiver_event'],
  'additional_checks':['pin_absolute_limits_across_waveform','output_and_PGOOD_policy_compatibility','zero_initial_rail_and_cap_energies','no_ideal_hidden_supply','full_port_energy_ledger','numerical_halfstep','actual_part_models_and_tolerances'],
  'run_admission':False},
 'bounded_matched_physics_proposal':{
  'status':'not_executed_needs_exact_inputs_and_parent_approval','maximum_new_joint_solves':4,'cells':['native_default_rails_coarse','native_default_rails_fine','native_low_input_topology_coarse','native_low_input_topology_fine'],'retries':0,
  'common_conditions':['same independently bound native ROM and force table','same gap48,2s65deg,zero-electrical-initial-state world','same initial equilibrium/reset boundary','same Cin47,Cout100,L10 and load firmware','same vendor model hash and complete receiver criteria'],
  'proposal_solver_parameters':{'coarse':{'max_step_s':5e-5,'firmware_step_s':1e-4,'reltol':1e-4},'fine':{'max_step_s':2.5e-5,'firmware_step_s':5e-5,'reltol':5e-5},'max_coupling_iterations':8},
  'not_yet_frozen':['protection_BOM_and_leakage_budget','verified_macro_model_port_order','versioned_rail_observable_extension','source/provider_ids','per_solve_wall_and_native_process_caps','imported_native_Raw_evidence','numerical_acceptance_provider_contract','independent_reviewer'],
  'stopping_condition':'Exactly four planned cells, or any applicability/voltage/qualification failure. Zero adaptive capacitance/geometry/threshold search. If unchanged baseline evidence exactly matches, reuse it rather than rerun.',
  'purpose':'Establish topology/startup model sufficiency on matched physics before searching for feasibility. Four successful solves do not themselves admit either task.',
  'separate_mechanical_patch_plan':'At most8 D,D+a,D+b,D+a+b coarse/fine solves only after a qualified passive-release patch and circuit patch are frozen; not an authorization or automatic next stage.'}}
(ROOT/'STARTUP-MODEL-ANALYSIS.json').write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
print(json.dumps({'old':sums(a),'new':sums(b)},indent=2))
