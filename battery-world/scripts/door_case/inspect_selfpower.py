"""Read-only facts for a finished or in-progress D5 candidate.

Provisional observations remain explicitly separate from accepted native
results. This command neither changes a candidate nor promotes a reference.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np

from bfworld.agentlab.simulation_chain.contracts import file_hash

STATES = ('RESET', 'BOOT', 'WAIT', 'INIT', 'TX', 'SLEEP')


def inspect(run):
    run = Path(run).resolve()
    final = run / 'result.json'
    result = json.loads(final.read_text()) if final.exists() else None
    accepted = bool(result and result['run_status'] == 'completed'
                    and result.get('checks', {}).get('program_power_fixed_point') is True)
    coarse_path = run / 'joint/solve.json'
    coarse = json.loads(coarse_path.read_text()) if coarse_path.exists() else {}
    coarse_converged = coarse.get('coupling_converged') is True
    program = (run / 'program.csv' if accepted else
               run / 'joint/program.csv' if coarse_converged else
               run / 'joint/provisional-program.csv')
    if not program.exists():
        program = run / 'provisional-program.csv'
    value = {'schema_version': 'bf-door-selfpower-observation-v1',
             'run': str(run), 'final_result_present': final.exists(),
             'converged_program_feedback': accepted or coarse_converged,
             'program_observation_scope': 'converged_coarse' if accepted or coarse_converged else 'provisional',
             'confirmation_complete': bool(result and result.get('checks', {}).get('time_step') is True),
             'not_task_acceptance': True,
             'nominal_prediction_eligible': bool(result and result['qualification']['nominal_prediction_eligible']),
             'run_status': result['run_status'] if result else 'in_progress_or_interrupted',
             'nominal_status': result['qualification']['nominal_status'] if result else 'pending',
             'sources': []}
    if result:
        value['sources'].append({'path': str(final), 'sha256': file_hash(final)})
    if coarse_converged:
        value['sources'].append({'path': str(coarse_path), 'sha256': file_hash(coarse_path)})
    if not program.exists():
        value['program_observation_available'] = False
        return value
    snapshot = program.read_bytes()
    data = np.genfromtxt(io.BytesIO(snapshot), delimiter=',', names=True)
    time, state = data['time_s'], data['state'].astype(int)
    design = json.loads((run / 'design-spec.json').read_text())
    deadline = design['base_design']['frozen']['task']['deadline_s']
    if not len(time) or time[0] != 0 or not np.isclose(time[-1], deadline):
        raise ValueError('PROGRAM_OBSERVATION_INCOMPLETE')
    starts = np.r_[0, np.flatnonzero(np.diff(state)) + 1]
    stops = np.r_[starts[1:], len(state)]
    step = float(np.median(np.diff(time)))
    segments = []
    for start, stop in zip(starts, stops):
        s = int(state[start])
        duration = (time[stop] if stop < len(state) else time[-1]) - time[start]
        reset_after = stop < len(state) and state[stop] == 0
        segments.append({'state': STATES[s], 'start_s': float(time[start]),
                         'observed_duration_ms': float(duration * 1000),
                         'minimum_supply_V': float(min(data['mcu_supply_V'][start:stop])),
                         'followed_by_reset': bool(reset_after),
                         'next_supply_V': float(data['mcu_supply_V'][stop]) if stop < len(state) else None})
    value.update(program_observation_available=True, program_segments=segments,
                 recorded_complete_TX=int(sum(state[x] == 5 and state[x-1] == 4 for x in starts[1:])),
                 incomplete_TX_resets=int(sum(x['state'] == 'TX' and x['followed_by_reset'] for x in segments)))
    value['sources'].append({'path': str(program), 'sha256': hashlib.sha256(snapshot).hexdigest()})
    return value


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(inspect(a.run), ensure_ascii=False, indent=2))
