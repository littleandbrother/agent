"""Vendor transient adapter, exact native cache and shared machine resource lease."""
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import zlib

import numpy as np

from ..store import identity
from ..runtime_config import configured
from ..simulation_chain.solver import read_raw, conservative_sample
from ..simulation_chain.contracts import ChainError
from .contracts import sealed
from .repository import file_hash
from .repository_feedback_contract import NUMERICS
from .repository_reference_node import modal
from .native_slot import native_slot


def tools():
    base = configured('LTSPICE_RUNTIME', Path.home()/'.local/share/bf-agent-runtime/workbench/toolchains/ltspice-26/Package.pkg/Payload/Applications/LTspice.app/Contents/SharedSupport/ltspice')
    paths = {'clang': Path('/Library/Developer/CommandLineTools/usr/bin/clang'),
        'sandbox': Path('/usr/bin/sandbox-exec'), 'wine': base/'bin/wine',
        'ltspice': base/'support/ltspice/drive_c/Program Files/ADI/LTspice/LTspice.exe',
        'vendor_model': base/'support/ltspice/drive_c/users/crossover/AppData/Local/LTspice/lib/sub/LTC3588-1.sub'}
    if not all(p.is_file() for p in paths.values()): raise ValueError('FEEDBACK_NATIVE_TOOL_MISSING')
    return {k: {'path': str(p), 'sha256': file_hash(p)} for k,p in paths.items()}


def coefficients(design, scenario):
    # Reuse the same reciprocal modal coefficients. The analytic resistive-load
    # response is not used to judge a nonlinear bridge/buck transient.
    value = modal(design, {**scenario, 'electrical_load_ohm': 100000})
    return {k:value[k] for k in ('mass_kg','forcing_mass_kg','stiffness_n_m','damping_n_s_m',
        'theta_n_v','capacitance_f','force_n','frequency_hz')}


def load_pairs(grid, current):
    if len(current) != len(grid)-1: raise ValueError('FEEDBACK_LOAD_GRID')
    pairs = [(float(grid[0]),float(current[0]))]
    for i in range(1,len(current)):
        if current[i] != current[i-1]:
            # A decision at t cannot alter the past. The transition ramp is
            # entirely inside the newly selected interval.
            pairs += [(float(grid[i]),float(current[i-1])),
                      (float(grid[i]+min(1e-9,(grid[i+1]-grid[i])/100)),float(current[i]))]
    pairs.append((float(grid[-1]),float(current[-1])))
    return pairs


def deck(design, scenario, pairs, max_step):
    m = coefficients(design,scenario)
    pwl = '\n+ '.join(' '.join(f'{t:.17g} {i:.17g}' for t,i in pairs[n:n+6]) for n in range(0,len(pairs),6))
    return f'''Piezo-program feedback v1; reciprocal source and vendor switching PMIC
Vforce drive 0 SIN(0 {m['force_n']:.17g} {scenario['frequency_hz']:.17g})
Lmass drive damper {m['mass_kg']:.17g} Rser=0
Rdamper damper spring {m['damping_n_s_m']:.17g}
Cspring spring coupling {1/m['stiffness_n_m']:.17g}
Bcouple coupling sense V={m['theta_n_v']:.17g}*v(piezo)
Vsense sense 0 0
Bpiezo 0 piezo I={m['theta_n_v']:.17g}*i(Vsense)
Cp piezo 0 {m['capacitance_f']:.17g}
Vport piezo pzin 0
XU1 pzin 0 cap vin sw out vin2 0 vin2 pgood 0 LTC3588-1
Cstorage vin 0 {design['storage_f']:.17g} IC={scenario['initial_storage_v']:.17g}
Ccap vin cap 1u
Cvin2 vin2 0 4.7u
L1 sw out {design['inductance_h']:.17g} Rser=0.4 IC=0
Cout out 0 {design['output_f']:.17g} IC={scenario['initial_output_v']:.17g} Rser=0.02
Vschedule schedule 0 PWL({pwl})
Bload out 0 I=V(schedule)*limit(V(out)/1.8,0,1)
.lib LTC3588-1.sub
.tran 0 {scenario['duration_s']:.17g} 0 {max_step:.17g} uic
.options plotwinsize=0 reltol=0.001 abstol=1e-12 vntol=1e-8
.save V(piezo) V(vin) V(out) V(pgood) V(cap) V(vin2) I(L1) I(Bload) I(Vport) I(Vsense) V(spring,coupling) V(drive)
.end
'''


def native(root, cache, content, toolset, budget, duration):
    pinned = {k:v for k,v in toolset.items() if k in ('wine','ltspice','vendor_model')}
    key = identity({'netlist':content, 'tools':pinned, 'reader':inspect.getsource(read_raw)})
    location = cache/key; location.mkdir(parents=True,exist_ok=True)
    completed, marker = location/'completed.json', location/'dispatch.json'
    reused = True
    with native_slot():
        if completed.exists():
            receipt = json.loads(completed.read_text())
            if receipt['key'] != key: raise ValueError('FEEDBACK_NATIVE_CACHE_IDENTITY')
            if receipt['status'] != 'SUCCEEDED': raise ValueError('FEEDBACK_NATIVE_RETAINED_FAILURE:' + receipt['error'])
            for name,digest in receipt['outputs'].items():
                if file_hash(location/name) != digest: raise ValueError('FEEDBACK_NATIVE_CACHE_CHANGED')
        else:
            if marker.exists(): raise ValueError('FEEDBACK_NATIVE_UNKNOWN_RECONCILE_REQUIRED')
            budget()
            sealed(marker, {'key':key, 'tools':pinned})
            (location/'system.cir').write_text(content)
            shutil.copyfile(toolset['vendor_model']['path'],location/'LTC3588-1.sub')
            command = [toolset['wine']['path'],'--enable-alt-loader=macdrv','--bottle','default','--no-gui',
                '--workdir','C:/Program Files/ADI/LTspice','LTspice.exe','-b',str(location/'system.cir')]
            try:
                with (location/'launcher.log').open('w') as log:
                    proc = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=NUMERICS['native_timeout_s'])
                if proc.returncode: raise ValueError('FEEDBACK_NATIVE_EXIT:' + str(proc.returncode))
                log = (location/'system.log').read_text(errors='replace')
                if 'Total elapsed time:' not in log or 'Fatal' in log: raise ValueError('FEEDBACK_NATIVE_INCOMPLETE')
                raw = location/'system.raw'
                read_raw(raw,duration)
                (location/'system.raw.zlib').write_bytes(zlib.compress(raw.read_bytes(),6)); raw.unlink()
                outputs = {name:file_hash(location/name) for name in ('system.cir','system.log','launcher.log','system.raw.zlib')}
                sealed(completed, {'key':key, 'status':'SUCCEEDED', 'outputs':outputs})
                reused = False
            except (ValueError, ChainError) as error:
                sealed(completed, {'key':key,'status':'FAILED','error':str(error)})
                raise
    root.mkdir(parents=True,exist_ok=True)
    for name in ('system.cir','system.log','system.raw.zlib'):
        shutil.copyfile(location/name,root/name)
    return {'key':key,'reused':reused,'raw_sha256':file_hash(root/'system.raw.zlib')}


def waveform(root, duration):
    # The independent validator also reads the retained full native waveform.
    # Derived downsampled previews never decide service validity.
    raw = root/'readback.raw'
    raw.write_bytes(zlib.decompress((root/'system.raw.zlib').read_bytes()))
    try: return read_raw(raw,duration)
    finally: raw.unlink(missing_ok=True)


def observe(t, values, grid):
    return conservative_sample(t,values,grid)
