"""Finish the remaining original registrations serially; no new samples."""
import json
from pathlib import Path
import subprocess
import sys
import time

FOLDER=Path(__file__).resolve().parent
APP=FOLDER.parents[3]
sys.path.insert(0,str(APP/'scripts'))
from run_organization_pilot import ROOT, read_trial_final, run


def main():
    # The first recovered trial is already running under its original owner.
    first=ROOT/'trials/T2-short-validity--single'
    while not (first/'recovery-final.json').exists():time.sleep(5)
    if not read_trial_final(first)['metrics']['model_calls']:
        raise ValueError('FIRST_RECOVERY_DID_NOT_REACH_MODEL')
    second=ROOT/'trials/T2-short-validity--temporary'
    if not (second/'recovery-final.json').exists():
        subprocess.run([sys.executable,str(FOLDER/'recover_zero_call.py'),
                        'T2-short-validity--temporary'],check=True,cwd=APP)
    if not read_trial_final(second)['metrics']['model_calls']:
        raise ValueError('SECOND_RECOVERY_DID_NOT_REACH_MODEL')
    print(json.dumps(run('organizations')),flush=True)
    print('FINITE_REGISTERED_LIST_FINISHED',flush=True)


if __name__=='__main__':main()
