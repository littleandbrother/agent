"""Trace-based native rail fixture criterion, not a fabricated settling time.

All numeric tolerances/windows must be prospectively supplied by the fixture
owner. No defaults, adaptive loosening, hardware qualification or extrapolation.
Consumes a full-resolution export of mapped native RAW observables, not the
historical downsampled waveform.csv. Signed current direction follows Ccap
vin→cap and Cvin2 vin2→ground, after the vendor interface has been verified.
"""
import argparse,json,math,pathlib
import numpy as np
REQUIRED=('time_s','vin_V','cap_V','vin2_V','icap_A','ivin2_A','source_connected')
PARAMETERS={'window_s','voltage_peak_to_peak_tol_V','slope_voltage_change_tol_V','energy_drift_tol_J','charge_consistency_tol_C','max_sample_interval_s','cap_F','vin2_F','phase'}

def evaluate(rows,p):
    if set(p)!=PARAMETERS:raise ValueError('EXPLICIT_PROSPECTIVE_PARAMETERS_REQUIRED')
    if p['phase'] not in ('source_on','source_off'):raise ValueError('UNKNOWN_PHASE')
    for key in PARAMETERS-{'phase'}:
        if type(p[key]) not in (int,float) or not math.isfinite(p[key]) or p[key]<=0:raise ValueError('POSITIVE_FINITE_PARAMETER:'+key)
    if any(key not in rows for key in REQUIRED):raise ValueError('RAIL_TRACE_COLUMNS_MISSING')
    x={k:np.asarray(rows[k],float) for k in REQUIRED};n=len(x['time_s'])
    if n<3 or any(len(v)!=n or not np.isfinite(v).all() for v in x.values()):raise ValueError('INVALID_TRACE')
    t=x['time_s']
    if t[0]<0 or (np.diff(t)<=0).any():raise ValueError('NONMONOTONIC_TRACE')
    if not np.isin(x['source_connected'],[0,1]).all():raise ValueError('UNKNOWN_SOURCE_CONNECTION')
    wanted=1 if p['phase']=='source_on' else 0
    if x['source_connected'][-1]!=wanted:return {'settled':False,'reason':'WRONG_TERMINAL_SOURCE_PHASE'}
    changes=np.flatnonzero(np.diff(x['source_connected'])!=0)+1;start=changes[-1] if len(changes) else 0
    W=p['window_s']
    if t[-1]-t[start]<2*W:return {'settled':False,'reason':'INSUFFICIENT_POST_TRANSITION_TRACE','observed_post_transition_s':float(t[-1]-t[start]),'required_window_multiple':2}
    metrics=[]
    for factor in (1,2):
        # Include a point at/before lower boundary. Reject inadequately sampled windows.
        first=max(start,int(np.searchsorted(t,t[-1]-factor*W,side='right')-1));tt=t[first:]
        if len(tt)<8 or np.max(np.diff(tt))>p['max_sample_interval_s']:
            return {'settled':False,'reason':'INSUFFICIENT_SAMPLING','window_multiple':factor}
        elapsed=tt[-1]-tt[0];dt=tt-tt[0]
        for name,v,i,C in [('CAP_gap',x['vin_V']-x['cap_V'],x['icap_A'],p['cap_F']),('VIN2',x['vin2_V'],x['ivin2_A'],p['vin2_F'])]:
            vv=v[first:];ii=i[first:];energy=.5*C*vv*vv
            slope=float(np.polyfit(dt,vv,1)[0]);ptp=float(np.ptp(vv));dE=float(abs(energy[-1]-energy[0]));qerr=float(abs(C*(vv[-1]-vv[0])-np.trapezoid(ii,tt)))
            tests={'voltage_peak_to_peak':ptp<=p['voltage_peak_to_peak_tol_V'],'slope_over_observation_window':abs(slope)*elapsed<=p['slope_voltage_change_tol_V'],'energy_drift':dE<=p['energy_drift_tol_J'],'signed_charge_consistency':qerr<=p['charge_consistency_tol_C']}
            tests={key:bool(value) for key,value in tests.items()}
            metrics.append({'rail':name,'window_multiple':factor,'window_start_s':float(tt[0]),'window_end_s':float(tt[-1]),'voltage_peak_to_peak_V':ptp,'slope_V_s':slope,'energy_drift_J':dE,'signed_charge_consistency_error_C':qerr,'checks':tests,'passed':all(tests.values())})
    return {'settled':all(x['passed'] for x in metrics),'phase':p['phase'],'observed_until_s':float(t[-1]),'criteria':p,'metrics':metrics,'claim':'Only declared trace-window criterion under this fixture; no asymptotic/hardware settling or energy-destination claim'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trace',type=pathlib.Path,required=True);p.add_argument('--parameters',type=pathlib.Path,required=True);args=p.parse_args()
    data=np.genfromtxt(args.trace,delimiter=',',names=True)
    result=evaluate({k:data[k] for k in (data.dtype.names or ())},json.loads(args.parameters.read_text()))
    print(json.dumps(result,indent=2,allow_nan=False))
