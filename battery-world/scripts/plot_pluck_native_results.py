#!/usr/bin/env python3
"""Plot native COMSOL CSVs without converting assumptions into calibration claims."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--coupled', type=Path, required=True)
    parser.add_argument('--transient', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = []

    def read(root, name):
        path = root / (name + '.csv')
        sources.append({'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        return np.loadtxt(path, delimiter=',', ndmin=2)

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axs = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for i, label in enumerate(['100 kohm', '1 Mohm']):
        r = read(args.coupled, f'frf{i}')
        m = read(args.coupled, f'frf{i}mechanical')
        for ax, values in zip(axs.flat, [r[:, 1], r[:, 2]*1e6, m[:, 0]*1e6, m[:, 1]/1e6]):
            ax.plot(r[:, 0], values, '.-', label=label)
            ax.set_xlabel('Frequency (Hz)')
            ax.grid(alpha=.2)
    for ax, label in zip(axs.flat, ['Terminal amplitude (V)', 'Mean resistor power (uW)', 'Maximum displacement (um)', 'Maximum von Mises stress (MPa)']):
        ax.set_ylabel(label)
    axs[0, 0].legend()
    fig.suptitle('COMSOL 3D piezoelectric + circuit: 1 mN harmonic load\nAssumed PZT-5A candidate; sampled sweep, not a resolved resonance peak', fontsize=12)
    for ext in ['png', 'pdf']:
        fig.savefig(args.output / ('comsol-frequency.' + ext), dpi=180)
    plt.close(fig)
    if args.transient:
        r = read(args.transient, 'signal')
        m = read(args.transient, 'field')
        if len(m) != len(r):
            raise ValueError('Transient field and signal sampling differ')
        energy = np.concatenate(([0], np.cumsum(np.diff(r[:, 0])*(r[1:, 2]+r[:-1, 2])/2)))
        fig, axs = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
        for ax, y, label in zip(axs.flat, [r[:, 1], r[:, 3]*1e6, r[:, 2]*1e6, energy*1e9], ['Terminal voltage (V)', 'Mean loaded-face displacement (um)', 'Resistor power (uW)', 'Resistor energy (nJ)']):
            ax.plot(r[:, 0], y, color='#1d6d91')
            ax.set(xlabel='Time (s)', ylabel=label)
            ax.grid(alpha=.2)
        fig.suptitle('COMSOL coupled transient: 10 mN Gaussian pulse, 100 kohm\nNative FEM result; prescribed test pulse, not calibrated magnetic plucking', fontsize=12)
        for ext in ['png', 'pdf']:
            fig.savefig(args.output / ('comsol-transient.' + ext), dpi=180)
        plt.close(fig)
    (args.output/'sources.json').write_text(json.dumps({'sources': sources, 'hardware_verified': False, 'paper_calibrated': False}, indent=2))


if __name__ == '__main__':
    main()
