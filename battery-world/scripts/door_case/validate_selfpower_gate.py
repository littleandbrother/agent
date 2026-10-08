"""Powered native gate calibration fixture, never a self-powered product run."""
import argparse
from pathlib import Path
import numpy as np
from bfworld.agentlab.door_selfpower import extraction, contracts
from bfworld.agentlab.door_system import solver as d4
from bfworld.agentlab.simulation_chain.native import command
from bfworld.agentlab.simulation_chain.contracts import write_json, file_hash


def validate(output,gate_name='reserve-e96-6v3'):
    p=Path(output).resolve();p.mkdir(exist_ok=False,parents=True)
    gate=contracts.GATES[gate_name]
    if gate is None:raise ValueError('GATE_FIXTURE_REQUIRES_RESERVE_GATE')
    text='''* EXTERNALLY POWERED calibration fixture only; not product success.
Vtest_out out 0 3.3
Vtest_storage vin 0 PWL(0 0 .02 8 .04 0)
Rtest mcu 0 100k
'''+extraction.energy_gate(**gate)+'''.tran 0 .04 0 1u uic
.options plotwinsize=0 reltol=1e-4 abstol=1e-12 vntol=1e-9 threads=2
.save V(vin) V(out) V(gate) V(mcu) I(Vtest_out) I(Smonitor) I(Smonitor_high)
.end
'''
    (p/'system.cir').write_text(text)
    command([d4.WINE,'--enable-alt-loader=macdrv','--bottle','default','--no-gui','--workdir',
             'C:/Program Files/ADI/LTspice','LTspice.exe','-b',p/'system.cir'],p,'launcher',60)
    t,v=d4.read_raw(p/'system.raw',.04)
    on=np.flatnonzero((t>.001)&(v['v(gate)']<.3))
    if not len(on):raise ValueError('GATE_NEVER_ENABLED')
    start=on[0];stop=on[-1]
    high=float(v['v(vin)'][start]);low=float(v['v(vin)'][stop])
    checks={'low_voltage_off':bool(max(v['v(mcu)'][(t>.001)&(t<.014)])<.1),
            'high_voltage_on':bool(min(v['v(mcu)'][(t>.017)&(t<.03)])>3.),
            'divider_high_matches':abs(high-gate['high_V'])<.05,
            'divider_low_matches':abs(low-gate['low_V'])<.05}
    result={'schema_version':'bf-door-powered-gate-fixture-v1','test_only':True,'gate':gate_name,
            'self_powered_product':False,'executor_sha256':contracts.template_hash(),
            'high_measured_V':high,'low_measured_V':low,'checks':checks,
            'passed':all(checks.values()),'deck_sha256':file_hash(p/'system.cir')}
    write_json(p/'result.json',result)
    np.savetxt(p/'gate-waveform.csv',np.column_stack([t,v['v(vin)'],v['v(mcu)'],v['v(gate)']]),
               delimiter=',',header='time_s,storage_V,mcu_V,gate_V',comments='')
    return result


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--gate',default='reserve-e96-6v3',choices=[k for k,v in contracts.GATES.items() if v])
    a=parser.parse_args();r=validate(a.output,a.gate);print(json.dumps(r,indent=2))
    raise SystemExit(0 if r['passed'] else 1)
