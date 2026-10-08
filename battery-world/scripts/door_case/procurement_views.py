"""Make bounded, source-bound previews of a native electronics revision.

This reads actual LTspice binary records. Preview rows preserve each channel's
per-bin extrema and endpoints; native RAW remains the authoritative source.
Run PNG/PDF conversion separately in an environment containing CairoSVG.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def raw_records(path):
    data = path.read_bytes()
    marker = 'Binary:\n'.encode('utf-16le')
    start = data.index(marker) + len(marker)
    head = data[:start].decode('utf-16le')
    count = int(re.search(r'No. Points:\s*(\d+)', head)[1])
    columns = re.findall(r'^\s*\d+\s+(\S+)\s+(\S+)\s*$', head, re.M)
    variables = int(re.search(r'No. Variables:\s*(\d+)', head)[1])
    if len(columns) != variables or variables != 7 or 'complex' in head:
        raise ValueError('LTSPICE_VARIABLE_LAYOUT_CHANGED')
    dtype = np.dtype([('time', '<f8'), ('values', '<f4', (variables-1,))])
    if len(data)-start != count*dtype.itemsize:
        raise ValueError('LTSPICE_BINARY_SIZE_MISMATCH')
    records = np.frombuffer(data, dtype=dtype, offset=start, count=count)
    values = np.column_stack([np.abs(records['time']), records['values']])
    if not np.isfinite(values).all() or np.any(np.diff(values[:, 0]) < 0):
        raise ValueError('LTSPICE_RECORD_INVALID')
    return values, columns


def bounded_rows(values, bins=48):
    selected = {0, len(values)-1}
    for chunk in np.array_split(np.arange(len(values)), bins):
        for col in range(1, values.shape[1]):
            selected.add(int(chunk[np.argmin(values[chunk, col])]))
            selected.add(int(chunk[np.argmax(values[chunk, col])]))
    return values[sorted(selected)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('revision', type=Path)
    root = parser.parse_args().revision
    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    receipt = []
    for case in ['nominal', 'weak-slow', 'no-motion']:
        source = root/'power'/case/'power.raw'
        values, columns = raw_records(source)
        names = [n.lower() for n, _ in columns]
        indices = [names.index(n) for n in ['v(vin)', 'v(out)', 'v(pgood)', 'i(bload)']]
        # Reorder into human-readable channels; retain all channel extrema.
        preview = bounded_rows(values)
        csvpath = source.parent/'waveform.csv'
        np.savetxt(csvpath, preview[:, [0, *indices]], delimiter=',',
                   header='time_s,storage_voltage_V,supply_voltage_V,pgood_V,load_current_A', comments='')
        for ax, index in zip(axes, indices[:3]):
            ax.plot(values[:, 0], values[:, index], label=case, linewidth=1.1)
        entry = dict(source=str(source.relative_to(root)),
                     source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                     native_points=len(values), preview_points=len(preview),
                     preview=str(csvpath.relative_to(root)),
                     preview_sha256=hashlib.sha256(csvpath.read_bytes()).hexdigest(),
                     selection='48 time-order bins; extrema of every native channel plus endpoints',
                     original_channels=columns, extrema_preserved=True)
        (source.parent/'waveform-provenance.json').write_text(json.dumps(entry, indent=2))
        receipt.append(entry)
    for ax, title in zip(axes, ['Input storage VIN (V)', 'MCU supply VOUT (V)', 'Power-good PGOOD (V)']):
        ax.set_ylabel(title);ax.grid(alpha=.18)
    axes[0].legend();axes[-1].set_xlabel('Time (s)')
    fig.suptitle('D3 native LTspice: zero initial energy / 14 mA TX envelope\n'
                 'Cold-start failed in all three cases; one-way ROM input, not hardware-calibrated', fontsize=11)
    fig.tight_layout();fig.savefig(root/'power/power-waveforms.png', dpi=170);plt.close(fig)
    (root/'power/preview-provenance.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps({'native_cases':len(receipt),'preview_rows':[r['preview_points'] for r in receipt]}))


if __name__ == '__main__':
    main()
