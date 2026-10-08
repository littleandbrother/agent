"""Contain only the exact native job after its declared timeout.

Wine may detach LTspice from the launcher subprocess. A timed-out launcher is
not proof that native writes have stopped. Never terminate a shared Wine host
or another candidate; recheck the exact command before signalling a PID.
"""
import os
import signal
import subprocess
import time
import re
from pathlib import Path
from ..simulation_chain.contracts import write_json


def job_pids(process_table, circuit, windows_file_check=None):
    prefix = 'LTspice.exe -b '
    expected = Path(circuit).resolve()
    found = []
    for row in process_table.splitlines():
        fields = row.strip().split(None, 1)
        if len(fields) != 2 or not fields[0].isdigit() or not fields[1].startswith(prefix):continue
        arg = fields[1][len(prefix):].strip()
        same = Path(arg).resolve() == expected
        # Wine may rewrite the exact argument to a drive-relative Windows path.
        # Do not guess its drive mapping: verify the actual open RAW instead.
        if not same and re.match(r'^[A-Za-z]:[\\/]', arg) and windows_file_check:
            same = windows_file_check(int(fields[0]), expected.with_suffix('.raw'))
        if same:found.append(int(fields[0]))
    return found


def contain_timeout(directory):
    directory = Path(directory).resolve()
    circuit = directory / 'system.cir'
    table = subprocess.check_output(['ps', '-axo', 'pid=,command='], text=True)
    actions = []
    def open_waveform(pid, raw):
        observed = subprocess.run(['lsof', '-a', '-p', str(pid), '-Fn', str(raw)],
                                  text=True, capture_output=True, timeout=10)
        return 'n'+str(raw) in observed.stdout.splitlines()
    for pid in job_pids(table, circuit, open_waveform):
        try:
            current = subprocess.check_output(['ps', '-p', str(pid), '-o', 'pid=,command='], text=True)
            if job_pids(current, circuit, open_waveform) != [pid]:
                actions.append({'pid': pid, 'action': 'identity-changed-not-signalled'})
                continue
            os.kill(pid, signal.SIGTERM)
            for _ in range(25):
                time.sleep(.1)
                current = subprocess.run(['ps', '-p', str(pid), '-o', 'pid=,command='], text=True, capture_output=True)
                if job_pids(current.stdout, circuit, open_waveform) != [pid]:break
            else:
                # Still the exact stalled native child, after a graceful stop.
                os.kill(pid, signal.SIGKILL)
                actions.append({'pid': pid, 'action': 'SIGKILL-exact-job-after-SIGTERM'})
                continue
            actions.append({'pid': pid, 'action': 'SIGTERM-exact-job-exit-observed'})
        except (ProcessLookupError, subprocess.CalledProcessError):
            actions.append({'pid': pid, 'action': 'already-exited'})
    write_json(directory / 'timeout-containment.json', {
        'schema_version': 'bf-native-timeout-containment-v1',
        'circuit': str(circuit), 'trigger': 'declared-native-timeout', 'actions': actions,
        'scope': 'Exact job only; no process-group, Wine-host or global termination.'})
