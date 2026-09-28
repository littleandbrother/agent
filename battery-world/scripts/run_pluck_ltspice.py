#!/usr/bin/env python3
"""Exercise the vendor LTC3588-1 macro-model; never claim physical calibration."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--app', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = a.app.resolve()/'Contents/SharedSupport/ltspice'
    bundled = root/'support/ltspice/drive_c/users/crossover/AppData/Local/LTspice'
    model = bundled/'lib/sub/LTC3588-1.sub'
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, out/Path(__file__).name)
    protocol = {'schema_version': 'ltc3588-vendor-check-v1', 'engine': 'LTspice 26.0.2 for MacOS',
        'source': 'https://ltspice.analog.com/software/LTspice_26.pkg',
        'model_sha256': hashlib.sha256(model.read_bytes()).hexdigest(),
        'topology': 'Vendor example adapted: 3.3 V (D1=VIN2,D0=GND), 47 uF storage, 47 uF output, 10 uH, 25 kohm load',
        'source_scope': 'Prescribed 100 Hz, 200 uA ideal current source; NOT coupled piezo mechanics or calibrated door motion',
        'hardware_verified': False, 'paper_calibrated': False}
    (out/'protocol.json').write_text(json.dumps(protocol, indent=2))
    results = {}
    for label, source in [('continuous', 'SINE(0 200u 100)'), ('one-second-burst', 'SINE(0 200u 100 0 0 0 100)'), ('zero', '0')]:
        case = out/label
        case.mkdir()
        deck = case/'power.cir'
        deck.write_text('* LTC3588-1 vendor macro-model, prescribed source test\n'
            'XU1 pz1 pz2 cap vin sw out vin2 vin2 0 pgood 0 LTC3588-1\n'
            'Cstorage vin 0 47u\nCcap vin cap 1u\nCvin2 vin2 0 1u\n'
            'L1 sw out 10u\nCout out 0 47u\nRload out 0 25k\n'
            f'Ipiezo pz2 pz1 {source}\n'
            '.lib LTC3588-1.sub\n.tran 0 5 0 100u\n'
            '.save V(vin) V(out) V(pgood) I(Rload)\n'
            '.meas TRAN output_peak MAX V(out)\n.meas TRAN storage_peak MAX V(vin)\n'
            '.meas TRAN startup WHEN V(out)=3.2 RISE=1\n'
            '.meas TRAN output_final FIND V(out) AT=5\n'
            '.meas TRAN load_energy INTEG (V(out)*I(Rload)) FROM=0 TO=5\n.end\n')
        cmd = [str(root/'bin/wine'), '--enable-alt-loader=macdrv', '--bottle', 'default', '--no-gui',
            '--workdir', 'C:/Program Files/ADI/LTspice', 'LTspice.exe', '-b', str(deck)]
        with (case/'launcher.log').open('w') as log:
            run = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        if run.returncode:
            raise RuntimeError(f'{label}: LTspice exit {run.returncode}')
        log = (case/'power.log').read_text(errors='replace')
        if 'Total elapsed time:' not in log or 'Files loaded:' not in log:
            raise RuntimeError('Incomplete solver log')
        values = {}
        for key in ['output_peak', 'storage_peak', 'startup', 'output_final', 'load_energy']:
            pattern = r'^startup:.*?\bAT\s+([-+\d.eE]+)' if key == 'startup' else r'^'+key+r':.*?=\s*([-+\d.eE]+)'
            match = re.search(pattern, log, re.M)
            values[key] = float(match[1]) if match else None
        if any(values[k] is None for k in ['output_peak', 'storage_peak', 'output_final', 'load_energy']):
            raise RuntimeError('Missing required native measurement')
        values['startup_observed'] = values['startup'] is not None
        values['raw_sha256'] = hashlib.sha256((case/'power.raw').read_bytes()).hexdigest()
        values['netlist_sha256'] = hashlib.sha256(deck.read_bytes()).hexdigest()
        values['scope'] = protocol['source_scope']
        results[label] = values
        print(label, json.dumps(values), flush=True)
    (out/'report.json').write_text(json.dumps({'protocol': protocol, 'cases': results}, indent=2))


if __name__ == '__main__':
    main()
