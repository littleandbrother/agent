import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parent
pdf=Path('/workspace/shared/primary-source-research-20261001/35881fc.pdf')
contract={'schema_version':'ltc3588-rail-state-contract-v2-static-only','claim_class':'datasheet-ideal-static-and-event-semantics','transient_startup_prediction_admitted':False,
'source':{'url':'https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf','revision':'C','sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'printed_pages':[3,7,8,9,13],'pdf_redistributed':False},
'rail_topology':{'cap_capacitor':{'positive_node':'VIN','negative_node':'CAP','recommended_f':1e-6},'vin2_capacitor':{'positive_node':'VIN2','negative_node':'GND','recommended_f':4.7e-6},'external_system_rail_use':'not intended'},
'ideal_settled_relations':{'VIN2':'min(VIN,4.8 V)','CAP':'max(VIN-4.8 V,0)','VIN_minus_CAP':'min(VIN,4.8 V)','applicability':'nonnegative VIN in datasheet operating scope, ideal diagram only','dynamic_time_constant_s':None,'dynamic_current_law':None},
'energy':{'cap_j':'0.5*Ccap*(VIN-CAP)^2','vin2_j':'0.5*Cvin2*VIN2^2','zero_initial_state_requires':['VIN=0','VIN2=0','VIN-CAP=0','VOUT=0','inductor current=0'],
'ideal_bypass_energy_at_4p8V_j':65.664e-6,'additional_post_uvlo_gate':False,'interpretation':'Stored state energy, not an independent lumped startup tax. Sub-4.8 V ideal tracking changes input loading; coupled mechanical work must be recomputed after any dynamic model change.'},
'nominal_3p3v_state_policy':{'D1':'VIN2','D0':'GND','output_target_v':3.3,'uvlo_rising_v':{'min':4.73,'typ':5.05,'max':5.37},'uvlo_falling_v':{'min':3.42,'typ':3.67,'max':3.91},
'sleep_threshold_v':{'min':None,'typ':3.312,'max':3.399},'wake_threshold_v':{'min':3.201,'typ':3.288,'max':None},
'pgood_falling_fraction':{'min':.83,'typ':.92,'max':None},'pgood_initial_assertion':'Independent converter sleep event at the programmed regulation level; cannot use 92% as initial assertion threshold',
'pgood_retention':'After assertion, UVLO falling alone does not clear PGOOD; output must cross its falling threshold',
'limits':'Nominal event logic helper only. Missing table extrema remain null. No assumed distribution, fixed delay, converter current or transient rail behavior.'},
'low_input_topology':{'status':'hypothesis_only_not_admitted','condition':'VIN must stay strictly below6V','wiring':{'CAP':'GND','VIN2':'VIN'},'reference':'p13/Fig6, shown at1.8V output','three_point_three_v_qualification':'separate requirement; not silently inferred from Fig6','requires':['Bound real clamp/protection BOM and tolerance','Leakage/capacitance/dynamic overshoot model','Complete source/rail/PMIC energy ledger','Qualified 3.3 V native evidence']},
'executable_scope':{'module':'src/ltc3588_rail_contract_v2.py','implements':['Ideal settled rail potentials, charge and energy arithmetic','UVLO nominal hysteresis conditional on VIN','PGOOD state transitions driven by independently supplied converter sleep event','Explicit exception for transient startup prediction'],'does_not_implement':['Rail charging/discharge dynamics','Full buck converter or PMIC','Vendor macro-model substitute','Native door-world mission prediction']},
'blocked_evidence':['Exact licensed model .SUBCKT declaration/order matched to XU1, without distributing model body','Versioned save extension and native rail voltage/current traces','Explicit zero or measured initial capacitor/inductor states','Source-open versus source-driven-down diagnostic with bounded source current/work','Qualified rail dynamics and losses, with numerical refinement','Firmware/program/receiver timing and load bindings from authoritative world'],
'old_model_disposition':{'one_milliamp_post_uvlo_aux_charge':'unqualified assumption retained historically, not reused','point_one_second_off_decay':'unqualified assumption retained historically, not reused','old_results':'preserved unchanged, cannot carry trajectories into changed rail model'},
'new_scientific_solves_for_rails':0}
(root/'contracts/ltc3588-rail-state-v2.json').write_text(json.dumps(contract,indent=2)+'\n')
