"""Fresh sandboxed C process per feedback iterate; no participant DLL in server."""
import csv
import io
from pathlib import Path
import shutil

import numpy as np

from .repository import file_hash
from .repository_feedback_contract import HEADER, STATES
from .repository_reference_node import sandbox_run

RUNNER = r'''#include <stdio.h>
#include "feedback.h"
int main(void) {
    double start, off, pgmin;
    if (scanf("%lf %lf %lf", &start, &off, &pgmin)!=3) return 2;
    double t, dt, v, pg; int powered=0, boot=0;
    bf_reset();
    puts("t_s,dt_s,supply_v,pgood_v,powered,boot,state,seq,value,crc");
    while (scanf("%lf %lf %lf %lf", &t,&dt,&v,&pg)==4) {
        if (powered && v<off) { powered=0; bf_reset(); }
        if (!powered && v>=start && pg>=pgmin) { powered=1; ++boot; }
        int state=powered ? bf_step(t,dt,v,pg>=pgmin) : BF_OFF;
        if (state<BF_OFF || state>BF_TX || (powered && state==BF_OFF)) return 3;
        unsigned seq=0,value=0,crc=0;
        if (powered) { seq=bf_sequence(); value=bf_value(); crc=bf_checksum(); }
        printf("%.17g,%.17g,%.17g,%.17g,%d,%d,%d,%u,%u,%u\n",
            t,dt,v,pg,powered,boot,state,seq,value,crc);
    }
    return 0;
}
'''


def compile_program(root, source, tools):
    root = root.resolve()
    folder = root/'program-build'; folder.mkdir()
    (folder/'main.c').write_text(source)
    (folder/'feedback.h').write_text(HEADER)
    (folder/'runner.c').write_text(RUNNER)
    result = sandbox_run([tools['clang']['path'], '-isysroot', '/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk',
        '-std=c11', '-Wall', '-Wextra', '-Werror', 'main.c', 'runner.c', '-o', 'firmware'], folder)
    (folder/'build.log').write_text(result.stdout+result.stderr)
    if result.returncode: raise ValueError('FEEDBACK_PROGRAM_BUILD:' + result.stderr[-1600:])
    return folder/'firmware'


def execute_program(root, binary, scenario, grid, supply, pgood):
    root, binary = root.resolve(), binary.resolve()
    root.mkdir()
    executable = root/'firmware'; shutil.copyfile(binary, executable); executable.chmod(0o500)
    witness = root/'observations.txt'
    with witness.open('w') as f:
        f.write(f"{scenario['start_v']:.17g} {scenario['brownout_v']:.17g} {scenario['pgood_min_v']:.17g}\n")
        for t, dt, v, pg in zip(grid[:-1], np.diff(grid), supply[:-1], pgood[:-1]):
            f.write(f'{t:.17g} {dt:.17g} {v:.17g} {pg:.17g}\n')
    observed_hash, binary_hash = file_hash(witness), file_hash(executable)
    # stdin redirection is a constant trusted wrapper; paths are relative to the
    # isolated application directory, which cannot access solver/model files.
    result = sandbox_run(['/bin/sh', '-c', './firmware < observations.txt'], root, 10)
    (root/'stderr.log').write_text(result.stderr)
    if file_hash(witness) != observed_hash or file_hash(executable) != binary_hash or file_hash(binary) != binary_hash:
        raise ValueError('FEEDBACK_PROGRAM_MODIFIED_INPUT')
    if result.returncode: raise ValueError('FEEDBACK_PROGRAM_EXIT:' + result.stderr[-1000:])
    expected = ['t_s','dt_s','supply_v','pgood_v','powered','boot','state','seq','value','crc']
    reader = csv.DictReader(io.StringIO(result.stdout))
    if reader.fieldnames != expected: raise ValueError('FEEDBACK_PROGRAM_TRACE_SCHEMA')
    rows = []
    for r in reader:
        if set(r) != set(expected) or any(v is None for v in r.values()): raise ValueError('FEEDBACK_PROGRAM_TRACE_SCHEMA')
        row = [float(r[k]) for k in expected]
        if not all(np.isfinite(row)) or any(row[k] != int(row[k]) for k in range(4,10)):
            raise ValueError('FEEDBACK_PROGRAM_TRACE_VALUE')
        rows.append(row)
    trace = np.asarray(rows)
    if trace.shape != (len(grid)-1, 10) or not np.allclose(trace[:,:4],
            np.column_stack([grid[:-1], np.diff(grid), supply[:-1], pgood[:-1]]), rtol=0, atol=1e-12):
        raise ValueError('FEEDBACK_PROGRAM_OBSERVATION_MISMATCH')
    powered, boot = False, 0
    for row in trace:
        if powered and row[2] < scenario['brownout_v']: powered = False
        if not powered and row[2] >= scenario['start_v'] and row[3] >= scenario['pgood_min_v']:
            powered, boot = True, boot+1
        if ((row[4],row[5]) != (int(powered),boot) or row[6] not in STATES.values() or
                (not powered and row[6] != 0) or (powered and row[6] == 0)):
            raise ValueError('FEEDBACK_PROGRAM_SUPERVISOR_MISMATCH')
    (root/'program.csv').write_text(result.stdout)
    currents = scenario['current_model']['values_a']
    amplitude = np.array([currents[list(STATES)[int(state)]] for state in trace[:,6]])
    events = events_from_trace(trace)
    return trace, amplitude, events


def events_from_trace(rows):
    events = []; start = None
    for i, row in enumerate(rows):
        if start is None: start = i
        last = rows[start]
        changed = tuple(row[4:10]) != tuple(last[4:10])
        if changed:
            if int(last[6]) in (2,3):
                events.append({'t_s':float(last[0]), 'duration_s':float(row[0]-last[0]),
                    'state':list(STATES)[int(last[6])], 'boot':int(last[5]), 'seq':int(last[7]),
                    'value':int(last[8]), 'crc':int(last[9]),
                    'completed':bool(row[4] and row[5]==last[5])})
            start = i
    if start is not None and int(rows[start][6]) in (2,3):
        row = rows[start]; end = rows[-1][0]+rows[-1][1]
        events.append({'t_s':float(row[0]), 'duration_s':float(end-row[0]),
            'state':list(STATES)[int(row[6])], 'boot':int(row[5]), 'seq':int(row[7]),
            'value':int(row[8]), 'crc':int(row[9]), 'completed':False})
    return events
