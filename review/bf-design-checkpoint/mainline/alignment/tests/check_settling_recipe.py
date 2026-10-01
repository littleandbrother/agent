"""Four synthetic checks of the prospective trace validator, no native evidence."""
import json,pathlib,sys
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from settling_validator import evaluate
from adapters import write,sha
p={'window_s':1.,'voltage_peak_to_peak_tol_V':1e-4,'slope_voltage_change_tol_V':1e-4,'energy_drift_tol_J':1e-9,'charge_consistency_tol_C':1e-12,'max_sample_interval_s':.011,'cap_F':1e-6,'vin2_F':4.7e-6,'phase':'source_off'}
t=np.linspace(0,10,1001);rows={'time_s':t,'vin_V':t*0+4.,'cap_V':t*0+3.5,'vin2_V':t*0+2.5,'icap_A':t*0,'ivin2_A':t*0,'source_connected':(t<5).astype(float)}
constant=evaluate(rows,p);assert constant['settled']
ramp={**rows,'vin2_V':2.5+t*.001,'ivin2_A':t*0+4.7e-9};drifting=evaluate(ramp,p);assert not drifting['settled']
short={k:v[t<=6] for k,v in rows.items()};insufficient=evaluate(short,p);assert insufficient['reason']=='INSUFFICIENT_POST_TRANSITION_TRACE'
try:evaluate(rows,{k:v for k,v in p.items() if k!='window_s'});raise AssertionError('missing required window accepted')
except ValueError as e:assert str(e)=='EXPLICIT_PROSPECTIVE_PARAMETERS_REQUIRED'
write(ROOT/'SETTLING-VALIDATOR-SYNTHETIC-RECEIPT.json',{'schema_version':'settling-recipe-validator-tests-v1','tests':4,'passed':4,'validator_sha256':sha(ROOT/'src/settling_validator.py'),'fixture_parameters':p,'constant_fixture':constant,'drifting_fixture':drifting,'short_fixture':insufficient,'no_default_tolerances':True,'scope':'Synthetic validator test only. These test tolerances and1s windows are NOT adopted as native experiment criteria. No native rail waveform has been observed.'})
print('4/4 synthetic settling-validator checks passed')
