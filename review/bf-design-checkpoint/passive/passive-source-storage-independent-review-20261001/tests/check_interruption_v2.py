"""Synthetic lifecycle fault injection only. No ODE or magnetics are evaluated.

Uses a temporary copy, a constant fake dense segment, a fake integrator and
retained initializer magnetics. Approval checks are mocked only in this fixture.
"""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch
import numpy as np

REVIEW = Path(__file__).resolve().parents[1]
SOURCE = REVIEW/'snapshots/candidate-v2'


class SyntheticDense:
    def __init__(self, y):
        self.t_old, self.t = 0., .001
        self.y_old = y.copy()
        self.Q = np.zeros((8, 3))

    def __call__(self, t):
        return self.y_old.copy()


class InterruptedFakeRadau:
    def __init__(self, fun, ta, y, tb, **kwargs):
        self.y = y.copy()
        self.status = 'running'
        self.t = ta
        self.calls = 0

    def step(self):
        self.calls += 1
        if self.calls > 1:
            raise KeyboardInterrupt('synthetic reviewer interruption')
        self.t = .001

    def dense_output(self):
        return SyntheticDense(self.y)


with tempfile.TemporaryDirectory(prefix='passive-lifecycle-review-') as tmp:
    root = Path(tmp)/'fixture'
    shutil.copytree(SOURCE, root)
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location('reviewed_runner_v2', root/'passive_runner.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    retained = json.loads((root/'outputs/EQUILIBRIUM-PREFLIGHT.json').read_text())['selected_root']['raw']
    # JSON vectors are normalized only for the original code's vector algebra.
    retained = copy.deepcopy(retained)
    for key in ('force_beam_N','tip_torque_about_COM_beam_N_m','driver_torque_about_COM_beam_N_m','driver_center_beam_m'):
        retained[key] = np.asarray(retained[key])
    def no_provider(*args, **kwargs):
        raise AssertionError('review must never evaluate a magnetic provider')
    caught = False
    with patch.object(module, 'check_frozen', return_value={}), patch.object(module, 'Radau', InterruptedFakeRadau), patch.object(module.Model, 'force', return_value=retained), patch.object(module.StaticMagneticInterface, 'evaluate', no_provider):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                module.run_one('cin47', 'coarse')
        except KeyboardInterrupt:
            caught = True
    out = root/'outputs/cin47-coarse'
    summary = json.loads((out/'SUMMARY.json').read_text())
    result = {
        'test_kind': 'synthetic lifecycle fault injection; not scientific evidence',
        'real_time_integrations': 0,
        'real_magnetic_evaluations': 0,
        'interruption_propagated': caught,
        'summary_status': summary['status'],
        'last_accepted_t_s': summary['last_accepted_t_s'],
        'expected_completion_t_s': 4.,
        'failure_run_seal_written': (out/'RUN-SEAL.json').exists(),
        'fix_verified': (not caught) and summary['status'] == 'INSUFFICIENT_NUMERICAL_EVIDENCE' and summary['last_accepted_t_s'] == .001 and summary['exception'] is not None,
    }
    assert result['fix_verified']
    (REVIEW/'reports/v2-interruption-check.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
