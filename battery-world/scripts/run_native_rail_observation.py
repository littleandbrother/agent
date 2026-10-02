#!/usr/bin/env python3
"""New, prospectively bounded LTspice rail fixtures; never amend old RAW."""
import argparse
import json
import re
import shutil
import time
from pathlib import Path
import numpy as np
from bfworld.agentlab.simulation_chain import solver, native
from bfworld.agentlab.simulation_chain.contracts import write_json, file_hash

SIGNALS = ['V(vin2)', 'V(cap)', 'V(vin,cap)', 'I(Ccap)', 'I(Cvin2)',
           'I(Cstorage)', 'I(Cout)', 'I(L1)', 'I(Idiagnostic)']


def interface(source):
    declarations = [x for x in native.PMIC.read_text(errors='replace').splitlines()
                    if re.match(r'^\s*\.subckt\s+LTC3588-1\s', x, re.I)]
    exact = len(declarations) == 1 and not declarations[0].rstrip().endswith('+')
    symbol = native.PMIC.parents[1]/'sym/PowerProducts/LTC3588-1.asy'
    symbol_text = symbol.read_text()
    pairs = re.findall(r'PINATTR PinName (\S+)\s+PINATTR SpiceOrder (\d+)', symbol_text)
    ports = declarations[0].split()[2:] if exact else [name for name, order in sorted(pairs, key=lambda x:int(x[1]))]
    instance = next(x for x in source.splitlines() if x.startswith('XU1 ')).split()
    if len(instance[1:-1]) != len(ports) or len(ports) != 11:
        raise ValueError('MACRO_INSTANCE_PORT_COUNT')
    return {'schema_version': 'native-model-interface-v2',
        'declaration': declarations[0] if exact else None, 'exact_subcircuit_declaration_available': exact,
        'ordered_ports': ports, 'model_sha256': file_hash(native.PMIC),
        'symbol_sha256': file_hash(symbol), 'ordering_source': 'vendor symbol PINATTR SpiceOrder; not package pin numbers',
        'instance_port_map': dict(zip(ports, instance[1:-1])),
        'provenance': 'Authorized installed vendor symbol; encrypted model declaration remains inaccessible. No model body exported.'}



def diagnostics(source, kind, fine=False):
    # Preserve the original passive components, load envelope and vendor model.
    lines = source.splitlines()
    start = next(i for i, x in enumerate(lines) if x.startswith('XU1 '))
    end = next(i for i, x in enumerate(lines) if x.startswith('.tran '))
    body = lines[start:end]
    body[0] = body[0].replace('XU1 port pz2 cap vin sw out vin2',
                             'XU1 port pz2 cap pmicvin sw pmicout vin2')
    body = [x for x in body if not x.startswith('Idiagnostic ')]
    controls = ('PWL(0 1 1.5 1 1.500001 0 4 0)' if kind == 'charge-disconnect' else '1')
    drive = 'PWL(0 0 1 6 1.5 6 1.500001 0 4 0)' if kind == 'driven-down' else (
        'PWL(0 0 1 4 4 4)' if kind == 'sub-uvlo-ramp' else 'PWL(0 0 1 6 4 6)')
    step = 1e-5 if fine else 2e-5
    return '\n'.join(['* Separate externally powered diagnostic; no mechanical source.',
        'Rport port 0 1G', 'Rpz2 pz2 0 1G', *body,
        'VpmicVin vin pmicvin 0', 'VpmicOut pmicout out 0',
        'Vdrive drive 0 '+drive, 'Rsource drive branch 100',
        'Ssource branch vin control 0 sourceSwitch', 'Vcontrol control 0 '+controls,
        '.model sourceSwitch SW(Ron=0.01 Roff=1e12 Vt=0.5 Vh=0)',
        f'.tran 0 4 0 {step} uic',
        '.options plotwinsize=0 reltol=1e-5 abstol=1e-12 vntol=1e-9',
        '.save V(vin) V(out) V(pgood) V(vin2) V(cap) V(vin,cap) I(Ccap) I(Cvin2) I(Cstorage) I(Cout) I(L1) I(Vdrive) V(drive) V(control) I(VpmicVin) I(VpmicOut)',
        '.meas TRAN storage_peak MAX V(vin)', '.meas TRAN output_peak MAX V(out)', '.end', ''])


def run(input_path, output, only=None):
    if output.exists():
        raise ValueError('NEW_OBSERVATION_DIRECTORY_REQUIRED')
    output.mkdir(parents=True)
    source = input_path.read_text()
    iface = interface(source)
    write_json(output/'native-model-interface.json', iface)
    plan = {'schema_version': 'native-observation-request-v1', 'source_deck_sha256': file_hash(input_path),
        'model_sha256': file_hash(native.PMIC), 'wine_sha256': file_hash(native.WINE),
        'duration_s': 4, 'budget_wall_s': 3600, 'diagnostic_Rsource_ohm': 100,
        'disconnect_s': 1.5, 'switch_off_ohm': 1e12,
        'fixtures': ['baseline-observation', 'baseline-fine', 'sub-uvlo-ramp', 'charge-disconnect', 'driven-down', 'charge-disconnect-fine'],
        'settling': {'window_s': .5, 'voltage_peak_to_peak_tol_V': .001,
            'slope_voltage_change_tol_V': .001, 'energy_drift_tol_J': 1e-8,
            'charge_consistency_tol_C': 1e-8, 'max_sample_interval_s': .001,
            'cap_F': 1e-6, 'vin2_F': 4.7e-6, 'phase': 'source_off'},
        'scope': 'Rail observability and diagnostic mechanism only; not self-powered success.'}
    if only:
        if set(only)-set(plan['fixtures']):raise ValueError('UNKNOWN_FIXTURE')
        plan['fixtures']=[x for x in plan['fixtures'] if x in only]
    write_json(output/'request.json', plan)
    (output/'original.cir').write_text(source)
    started = time.time(); results = []
    for name in plan['fixtures']:
        if time.time()-started > plan['budget_wall_s']:
            raise ValueError('OBSERVATION_WALL_CAP')
        if shutil.disk_usage(output).free < 5*1024**3:
            raise ValueError('OBSERVATION_DISK_RESERVE')
        directory = output/name; directory.mkdir()
        shutil.copyfile(native.PMIC, directory/'LTC3588-1.sub')
        shutil.copyfile(input_path.parent/'load.pwl', directory/'load.pwl')
        if name.startswith('baseline'):
            deck = source.replace('.end', '.save '+' '.join(SIGNALS)+'\n.end')
            if name.endswith('fine'):
                deck = re.sub(r'(?m)^(\.tran\s+0\s+\S+\s+0\s+)(\S+)',
                              lambda m: m[1]+str(float(m[2])/2), deck)
        else:
            deck = diagnostics(source, name.removesuffix('-fine'), name.endswith('-fine'))
        (directory/'system.cir').write_text(deck)
        print('OBSERVATION', name, flush=True)
        attempt = {'id': name, 'started': time.time(), 'deck_sha256': file_hash(directory/'system.cir')}
        try:
            t, v = solver.native_solve(directory, 4)
            cap = v['v(vin)']-v['v(cap)']; vin2 = v['v(vin2)']
            columns = {'time_s': t, 'vin_V': v['v(vin)'], 'cap_V': cap,
                'vin2_V': vin2, 'out_V': v['v(out)'], 'pgood_V': v['v(pgood)'],
                'icap_A': v['i(ccap)'], 'ivin2_A': v['i(cvin2)'],
                'storage_current_A': v['i(cstorage)'], 'output_current_A': v['i(cout)']}
            for channel in ('v(drive)', 'i(vdrive)', 'v(control)', 'i(vpmicvin)', 'i(vpmicout)'):
                if channel in v: columns[channel] = v[channel]
            np.savetxt(directory/'rails.csv', np.column_stack(list(columns.values())), delimiter=',', header=','.join(columns), comments='', fmt='%.12g')
            source_work = float(np.trapezoid(-v['v(drive)']*v['i(vdrive)'], t)) if 'v(drive)' in v else None
            attempt.update(status='completed', raw_sha256=file_hash(directory/'system.raw'),
                csv_sha256=file_hash(directory/'rails.csv'), samples=len(t),
                peak_vin_V=float(max(v['v(vin)'])), peak_out_V=float(max(v['v(out)'])),
                final_cap_energy_J=float(.5e-6*cap[-1]**2), final_vin2_energy_J=float(.5*4.7e-6*vin2[-1]**2),
                source_work_J=source_work, self_powered_success=False,
                all_required_saved=all(x in v for x in ('v(vin2)', 'v(cap)', 'i(ccap)', 'i(cvin2)')))
        except Exception as exc:
            attempt.update(status='failed', error=str(exc))
        attempt['ended'] = time.time(); attempt['end_to_end_s'] = attempt['ended']-attempt['started']
        write_json(directory/'receipt.json', attempt); results.append(attempt)
        write_json(output/'receipt.json', {'request_sha256': file_hash(output/'request.json'),
            'fixtures': results, 'elapsed_s': time.time()-started, 'historical_raw_unchanged': True,
            'model_body_portable': False, 'scientific_qualified': False})
        print('OBSERVATION_END', name, attempt['status'], flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', nargs='+')
    args = parser.parse_args(); run(args.input, args.output, args.only)
