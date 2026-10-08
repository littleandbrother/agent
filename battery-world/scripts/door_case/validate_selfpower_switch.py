"""Native externally powered switch control; never a self-power result."""
import argparse
import json
from pathlib import Path
import numpy as np
from bfworld.agentlab.door_selfpower import contracts, extraction
from bfworld.agentlab.door_system import solver as d4
from bfworld.agentlab.simulation_chain.native import command
from bfworld.agentlab.simulation_chain.contracts import write_json, file_hash


def solve(path, part, *, characterization=False):
    path.mkdir(parents=True,exist_ok=False)
    supply=('1.8' if characterization else
            'PWL(0 3.3 .002 3.3 .0021 2.5 .004 2.5 .0041 2.24 .006 2.24 '
            '.0061 2.0 .008 2.0 .0081 1.8 .01 1.8)')
    current=2. if characterization else .003659
    duration=.002 if characterization else .01
    text=f'''* EXTERNAL TEST SUPPLY. Diagnostic component fixture, not self-power.
Vtest_out out 0 {supply}
Vtest_storage vin 0 7.2
Btest_load mcu 0 I={current}*limit(V(mcu)/.5,0,1)
'''+extraction.energy_gate(**contracts.GATES['reserve-e96-6v3-2v96'],load_switch=part)+f'''
.tran 0 {duration} 0 1u uic
.options plotwinsize=0 reltol=1e-4 abstol=1e-12 vntol=1e-9 threads=2
.save V(out) V(mcu) V(gate) I(Vtest_out)
.end
'''
    (path/'system.cir').write_text(text)
    command([d4.WINE,'--enable-alt-loader=macdrv','--bottle','default','--no-gui',
             '--workdir','C:/Program Files/ADI/LTspice','LTspice.exe','-b',path/'system.cir'],path,'launcher',60)
    log=(path/'system.log').read_text()
    if 'Total elapsed time:' not in log or 'Fatal' in log:raise ValueError('NATIVE_FIXTURE_INCOMPLETE')
    t,v=d4.read_raw(path/'system.raw',duration)
    samples=[]
    for at in ([.0015] if characterization else [.0015,.0035,.0055,.0075,.0095]):
        out,mcu,gate=[float(np.interp(at,t,v[k])) for k in ('v(out)','v(mcu)','v(gate)')]
        samples.append({'time_s':at,'source_V':out,'mcu_V':mcu,'Vgs_V':gate-out,
                        'drop_V':out-mcu,'effective_on_resistance_ohm':(out-mcu)/current})
    np.savetxt(path/'waveform.csv',np.column_stack([t,v['v(out)'],v['v(mcu)'],v['v(gate)']]),
               delimiter=',',header='time_s,source_V,mcu_V,gate_V',comments='')
    return {'part':part,'current_A':current,'samples':samples,'deck_sha256':file_hash(path/'system.cir'),
            'native_log_sha256':file_hash(path/'system.log')}


def validate(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    start=contracts.template_hash()
    legacy=solve(output/'bss84','BSS84')
    revised=solve(output/'si2333','Si2333CDS')
    characterized=solve(output/'si2333-1v8-2A','Si2333CDS',characterization=True)
    checks={'bss84_dropout_reproduced':legacy['samples'][2]['mcu_V']<1.8,
            'si2333_reaches_low_voltage_load':all(x['drop_V']<.005 for x in revised['samples']),
            'si2333_model_within_datasheet_on_resistance':0<characterized['samples'][0]['effective_on_resistance_ohm']<=.059,
            'source_stable':contracts.template_hash()==start}
    value={'schema_version':'bf-powered-load-switch-fixture-v1','test_only':True,
           'self_powered_product':False,'executor_sha256':start,'checks':checks,'passed':all(checks.values()),
           'legacy':legacy,'revised':revised,'manufacturer_test_point':characterized,
           'source_url':'https://www.vishay.com/docs/68516/si2333cd.txt',
           'model_sha256':contracts.SI2333_MODEL_HASH,'datasheet_sha256':contracts.SI2333_DATASHEET_HASH,
           'claim_boundary':'Native nominal component-control test. Original vendor model is typical; no worst-case thermal, fabrication or hardware validation.'}
    write_json(output/'result.json',value)
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    r=validate(a.output);print(json.dumps(r,indent=2));raise SystemExit(0 if r['passed'] else 1)
