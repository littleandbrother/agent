"""Independent solver check of the passive electrical subnetwork, not full PMIC."""
from __future__ import annotations
import math
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from bisect import bisect_right
from bfworld.kernel.canonical import canonical_hash
from .engine import Design,Reference,execute

def circuit_check()->dict:
    solver=shutil.which('ngspice')
    if not solver:return {'status':'unavailable','scope':'passive source/storage subnetwork','full_system_verified':False}
    design=replace(Design(),clamp_v=None,start_v=50)
    ref=replace(Reference(),duration_s=.2,dt_s=.0002,rpm=0,source_phase_rad=math.pi/2)
    with tempfile.TemporaryDirectory(prefix='bfworld-circuit-') as tmp:
        path=Path(tmp)
        netlist=f'''Independent passive reference
Iharv 0 store DC {ref.source_peak_a}
Rsource store 0 {ref.source_r_ohm}
Rleak store 0 {ref.leakage_r_ohm}
Cstore store 0 {design.capacitance_f} IC={ref.initial_v}
.tran {ref.dt_s} {ref.duration_s} UIC
.control
set wr_singlescale
set wr_vecnames
run
wrdata voltage.txt v(store)
quit
.endc
.end
'''
        (path/'reference.cir').write_text(netlist)
        result=subprocess.run([solver,'-b','reference.cir'],cwd=path,capture_output=True,text=True,timeout=60,check=True)
        observed=[list(map(float,line.split())) for line in (path/'voltage.txt').read_text().splitlines()[1:] if line.strip()]
        run=execute(design,ref)
        times=[r['time_s'] for r in run['rows']][1:]
        ours=[r['storage_voltage_v'] for r in run['rows']][1:]
        ot=[r[0] for r in observed]
        def interpolate(t):
            idx=max(1,min(len(ot)-1,bisect_right(ot,t)))
            a,b=observed[idx-1],observed[idx]
            return a[1]+(b[1]-a[1])*(t-a[0])/(b[0]-a[0])
        values=[interpolate(t) for t in times]
        error=max(abs(a-b) for a,b in zip(ours,values))
        version=subprocess.run([solver,'--version'],capture_output=True,text=True,timeout=10).stdout.strip()
        return {'status':'pass' if error<1e-4 else 'fail','solver_version':version,'netlist':netlist,
          'netlist_hash':canonical_hash(netlist),'reference_run_hash':run['content_hash'],
          'maximum_absolute_error_v':error,'tolerance_v':1e-4,'samples':len(times),
          'scope':'constant-source passive Norton resistance, leakage and storage only',
          'full_system_verified':False,'measured':False,
          'observations':[{'time_s':float(t),'engine_voltage_v':float(a),'ngspice_voltage_v':float(b)} for t,a,b in zip(times[::50],ours[::50],values[::50])],
          'solver_completed':result.returncode==0}
