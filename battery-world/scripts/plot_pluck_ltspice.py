#!/usr/bin/env python3
"""Read LTspice real, non-FastAccess raw output and cross-check native measures."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read_raw(path):
    data = path.read_bytes()
    marker = 'Binary:\n'.encode('utf-16-le')
    offset = data.index(marker)+len(marker)
    header = data[:offset].decode('utf-16-le')
    flags = re.search(r'Flags: ([^\n]+)', header)[1]
    if 'real' not in flags or 'FastAccess' in flags or 'double' in flags:
        raise ValueError('Unsupported raw format: '+flags)
    n = int(re.search(r'No. Variables: (\d+)', header)[1])
    count = int(re.search(r'No. Points:\s+(\d+)', header)[1])
    names = [row.split()[1] for row in header.split('Variables:\n')[1].split('Binary:')[0].splitlines() if row.strip()]
    dtype = np.dtype([('t', '<f8'), ('v', '<f4', (n-1,))])
    values = np.frombuffer(data, offset=offset, dtype=dtype)
    if len(values) != count or len(names) != n or not np.isfinite(values['v']).all():
        raise ValueError('Raw record count or finite-value check failed')
    time = np.abs(values['t'])  # LTspice compression marks can negate timestamps.
    if (np.diff(time) < 0).any() or abs(time[-1]-5) > 1e-8:
        raise ValueError('Incomplete/nonmonotonic transient')
    return time, {name.lower(): values['v'][:, i] for i, name in enumerate(names[1:])}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, required=True)
    a = p.parse_args()
    report = json.loads((a.input/'report.json').read_text())
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(3, 2, figsize=(11, 8), constrained_layout=True)
    validation = {}
    for row, (label, expected) in enumerate(report['cases'].items()):
        path = a.input/label/'power.raw'
        t, v = read_raw(path)
        measured = {'output_peak': float(v['v(out)'].max()), 'storage_peak': float(v['v(vin)'].max()), 'output_final': float(v['v(out)'][-1])}
        for key, value in measured.items():
            if not np.isclose(value, expected[key], rtol=5e-4, atol=1e-5):
                raise ValueError(f'{label}: native measure/raw disagreement {key}')
        validation[label] = {'native_measure_cross_check': True, 'samples': len(t), 'raw_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        step = max(1, len(t)//12000)
        for ax, name, title in zip(axes[row], ['v(vin)', 'v(out)'], ['Storage VIN', 'Regulated output']):
            ax.plot(t[::step], v[name][::step], lw=.9)
            ax.set(xlabel='Time (s)', ylabel='Voltage (V)', title=label+' / '+title)
            ax.grid(alpha=.2)
            if name=='v(out)':
                ax.axhline(3.2, ls='--', color='#aa6633', lw=.8, label='Assumed MCU startup 3.2 V')
                ax.legend(fontsize=8)
        # Small time-uniform inspection export; full adaptive raw remains authoritative.
        sample = np.linspace(0, 5, 5001)
        np.savetxt(a.input/label/'preview.csv', np.column_stack([sample]+[np.interp(sample,t,v[n]) for n in ['v(vin)','v(out)','v(pgood)']]), delimiter=',', header='time_s,storage_v,output_v,pgood_v', comments='')
    fig.suptitle('Official LTC3588-1 macro-model / LTspice 26.0.2\n3.3 V selection, 47 uF storage + output, 25 kohm load; prescribed current source, not a hardware measurement', fontsize=11)
    for ext in ['png','pdf']:
        fig.savefig(a.input/('ltspice-startup.'+ext), dpi=180)
    (a.input/'raw-validation.json').write_text(json.dumps(validation,indent=2))


if __name__ == '__main__':
    main()
