#!/usr/bin/env python3
"""Native capability probe: retained beam/program + vendor switching PMIC.

Runs in a new directory under the shared native lease. The abstract reference
and its acceptance rules are unchanged. Capacitors are a declared probe point
within Pi's proposed range, not a hardware-optimized design.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from run import ROOT, APP, save
from bf_v2_environment import environment
from v2_common import RUNTIME
os.environ.update(environment(RUNTIME)[1])
from bfworld.agentlab.design_lab.native_slot import native_slot
from bfworld.agentlab.simulation_chain.solver import read_raw


def main():
    import numpy as np
    p, _ = environment(RUNTIME)
    root = ROOT/'default/vendor-probe'
    if (root/'result.json').exists():
        print((root/'result.json').read_text()); return
    if (root/'dispatch.json').exists(): raise ValueError('NATIVE_PROBE_RECONCILE_REQUIRED')
    ltroot = Path('/Users/depengsu/.local/share/bf-agent-runtime/workbench/toolchains/ltspice-26/Package.pkg/Payload/Applications/LTspice.app/Contents/SharedSupport/ltspice')
    vendor = ltroot/'support/ltspice/drive_c/users/crossover/AppData/Local/LTspice/lib/sub/LTC3588-1.sub'
    executable = ltroot/'bin/wine'
    prior = json.loads((ROOT/'default/execution.json').read_text())
    blobs = RUNTIME/'workbench/design-lab/repository/blobs'
    def old(name):
        ref = prior['artifacts'][name]; raw = (blobs/ref['sha256']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref['sha256']: raise ValueError('SOURCE_IDENTITY')
        return raw
    source = old('source.cir').decode().split('.control')[0]
    source = '\n'.join(line for line in source.splitlines() if not line.startswith('Rl '))
    load = json.loads(old('load.json')); events = json.loads(old('events.json'))
    pwl = ' '.join(f'{t:.12g} {i:.12g}' for t,i in load)
    # Vendor symbol pin order inherited from the already exercised adapter:
    # PZ1 PZ2 CAP VIN SW VOUT VIN2 D1 D0 PGOOD GND.
    content = source + f'''
XU1 piezo 0 cap vin sw out vin2 0 vin2 pgood 0 LTC3588-1
Cstorage vin 0 150u IC=0
Ccap vin cap 1u
Cvin2 vin2 0 4.7u
L1 sw out 10u Rser=0.4
Cout out 0 68u IC=0 Rser=0.02
Vschedule schedule 0 PWL({pwl})
Bload out 0 I=V(schedule)*limit(V(out)/1.8,0,1)
.lib LTC3588-1.sub
.tran 0 20 0 100u uic
.options plotwinsize=0 reltol=0.001 abstol=1e-12 vntol=1e-8
.save V(piezo) V(vin) V(out) V(pgood) I(Bload)
.meas TRAN output_peak MAX V(out)
.meas TRAN storage_peak MAX V(vin)
.meas TRAN startup WHEN V(out)=2.3 RISE=1
.end
'''
    save(root/'protocol.json', {'version':'default-piezo-vendor-probe-v1',
        'source_execution':prior['execution_id'], 'source_netlist_sha256':prior['artifacts']['source.cir']['sha256'],
        'load_sha256':prior['artifacts']['load.json']['sha256'],
        'model_sha256':hashlib.sha256(vendor.read_bytes()).hexdigest(),
        'netlist_sha256':hashlib.sha256(content.encode()).hexdigest(),
        'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'cin_uF':150,'cout_uF':68,'inductor_uH':10,'initial_vin':0,'initial_vout':0,
        'selection':'Pi selected LTC3588-1 and estimated 100/150 uF input; Codex capability probe uses 150 uF and 68 uF output.',
        'changed_physics':'reciprocal beam loaded by vendor bridge/buck with separate VIN/VOUT; no constant-efficiency stage',
        'service_check':'sample and TX windows both >=2.2V, unique matching sequence/value/checksum',
        'load':'existing compiled event schedule; low-voltage current taper from existing native adapter',
        'native_lock':p['paths']['NATIVE_LOCK']})
    (root/'system.cir').write_text(content); shutil.copyfile(vendor,root/'LTC3588-1.sub')
    (root/'events.json').write_bytes(old('events.json'))
    with native_slot(p['paths']['NATIVE_LOCK'],blocking=False):
        save(root/'dispatch.json',{'started_epoch':time.time()})
        cmd=[str(executable),'--enable-alt-loader=macdrv','--bottle','default','--no-gui',
             '--workdir','C:/Program Files/ADI/LTspice','LTspice.exe','-b',str(root/'system.cir')]
        try:
            with (root/'launcher.log').open('w') as log:
                proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=600)
            if proc.returncode: raise ValueError('SOLVER_EXIT:'+str(proc.returncode))
            log=(root/'system.log').read_text(errors='replace')
            if 'Total elapsed time:' not in log or 'Fatal' in log: raise ValueError('INCOMPLETE_SOLVER')
            t,v=read_raw(root/'system.raw',20)
            for key,channel in [('output_peak','v(out)'),('storage_peak','v(vin)')]:
                match=re.search(r'^'+key+r':.*?=\s*([-+\d.eE]+)',log,re.M)
                if not match or not np.isclose(float(match[1]),max(v[channel]),rtol=5e-4): raise ValueError('MEAS_RAW_MISMATCH')
            windows=[]
            for event in events:
                a,b=event['t_s'],event['t_s']+event['duration_s']
                values=np.r_[np.interp([a,b],t,v['v(out)']),v['v(out)'][(t>=a)&(t<=b)]]
                windows.append({**event,'minimum_vout':float(min(values)),'powered':bool(min(values)>=2.2)})
            received=[]
            for e in windows:
                samples=[s for s in windows if s['state']=='sample' and s['seq']==e['seq'] and s['t_s']+s['duration_s']<=e['t_s']]
                if e['state']=='tx' and e['powered'] and samples and samples[-1]['powered'] and e['value']==samples[-1]['value'] and e['crc']==((e['seq']^e['value']^0xA5)&255): received.append(e['seq'])
            start=np.flatnonzero(v['v(out)']>=2.3)
            # Portable, reduced trace for the report; full native RAW is retained locally.
            grid=np.unique(np.r_[np.linspace(0,20,4001),*[np.linspace(e['t_s']-.001,e['t_s']+e['duration_s']+.001,120) for e in events]])
            np.savetxt(root/'waveform.csv',np.column_stack([grid,*[np.interp(grid,t,v[k]) for k in ['v(vin)','v(out)','v(pgood)']]]),delimiter=',',header='time_s,VIN_V,VOUT_V,PGOOD_V',comments='')
            result={'status':'SUCCEEDED','points':len(t),'startup_2p3v_s':float(t[start[0]]) if len(start) else None,
                'vin_peak_v':float(max(v['v(vin)'])),'vout_peak_v':float(max(v['v(out)'])),
                'windows':windows,'valid_sequences':received,'service_passed':len(set(received))>=3,
                'raw_sha256':hashlib.sha256((root/'system.raw').read_bytes()).hexdigest(),
                'physical':'NOT_TESTED','scope':'vendor macro-model / declared load envelopes'}
        except Exception as exc:
            save(root/'failure.json',{'error':str(exc)});raise
        save(root/'result.json',result);print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': main()
