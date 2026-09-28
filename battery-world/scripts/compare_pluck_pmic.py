#!/usr/bin/env python3
"""Cross-check the current average buck assumptions against vendor SPICE results.

This block test uses prescribed ideal current, not mechanical plucking.
It records model discrepancy without changing the frozen reference case.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    power = json.loads(args.case.read_text())['power']
    vendor = json.loads((args.vendor/'report.json').read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    results = {}
    for label, factor in [('continuous', '1'), ('one-second-burst', '(time<1)'), ('zero', '0')]:
        out = args.output/label
        out.mkdir()
        deck = f'''Average-buck block check - prescribed ideal rectified current
Binput 0 vin I=200u*abs(sin(2*pi*100*time))*{factor}
Cstorage vin 0 47u ic=0
Vlogic logic 0 1
Sgate logic gate vin 0 ENABLE
Rgate gate 0 1
.model ENABLE sw(ron=1e-6 roff=1e12 vt={(power['start_v']+power['stop_v'])/2} vh={(power['start_v']-power['stop_v'])/2})
Bbuck 0 buckout I=(v(gate)>0.5?min(0.1,max({power['output_v']}-v(out),0)*0.1):0)
Vbuck buckout out 0
Cout out 0 {power['output_capacitance_f']} ic=0
Rload out 0 25k
Routleak out 0 100meg
Bload vin 0 I=v(out)*i(Vbuck)/{power['efficiency']}/max(v(vin),0.01)
Bquiet vin 0 I={power['quiescent_a']}*v(vin)/(abs(v(vin))+0.01)
Bshunt vin 0 I=max(v(vin)-20,0)/10
.options reltol=1e-4 abstol=1e-10 vntol=1e-8 method=trap itl4=200 gmin=1e-10
.control
set noaskquit
set wr_singlescale
set wr_vecnames
set numdgt=17
tran 20u 5 0 20u uic
wrdata channels.txt v(vin) v(out)
quit
.endc
.end
'''
        (out/'model.cir').write_text(deck)
        run = subprocess.run(['/opt/homebrew/bin/ngspice','-b','model.cir'], cwd=out, capture_output=True, text=True, timeout=180)
        (out/'solver.log').write_text(run.stdout+run.stderr)
        if run.returncode:
            raise RuntimeError('NGSPICE_FAILED')
        values = np.loadtxt(out/'channels.txt', skiprows=1)
        if not np.isfinite(values).all() or abs(values[-1,0]-5)>1e-8:
            raise ValueError('Incomplete/nonfinite output')
        crossings = np.flatnonzero(values[:,2]>=3.2)
        startup = float(values[crossings[0],0]) if len(crossings) else None
        peak = float(values[:,2].max())
        energy = float(np.trapz(values[:,2]**2/25000,values[:,0]))
        ref = vendor['cases'][label]
        results[label] = {'average_model': {'output_peak':peak,'storage_peak':float(values[:,1].max()),'startup_s':startup,'load_energy_j':energy},
            'vendor_model':ref,'startup_delta_s':startup-ref['startup'] if startup is not None and ref['startup'] is not None else None,
            'load_energy_relative_delta':energy/ref['load_energy']-1 if ref['load_energy']>1e-10 else None,
            'netlist_sha256':hashlib.sha256((out/'model.cir').read_bytes()).hexdigest()}
        sample = np.linspace(0,5,5001)
        np.savetxt(out/'preview.csv',np.column_stack([sample,np.interp(sample,values[:,0],values[:,1]),np.interp(sample,values[:,0],values[:,2])]),delimiter=',',header='time_s,storage_v,output_v',comments='')
    report = {'scope':'PMIC-only prescribed-current comparison. Existing averaged assumptions unchanged; not hardware or coupled-case calibration.',
        'source_case_sha256':hashlib.sha256(args.case.read_bytes()).hexdigest(),'power_parameters':power,'cases':results,
        'hardware_verified':False,'calibrated':False}
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:{'startup_delta_s':v['startup_delta_s'],'load_energy_relative_delta':v['load_energy_relative_delta']} for k,v in results.items()}))


if __name__ == '__main__':
    main()
