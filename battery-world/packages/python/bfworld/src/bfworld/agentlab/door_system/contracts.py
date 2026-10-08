"""Actual design freedom is separated from task, model and numeric assumptions."""
import copy
import hashlib
import json
import math
from pathlib import Path

SCOPE = ('D4 fixed copper/PZT-5A beam and LTC3588 family; adjustable driver bracket '
         'pose/polarity, storage and application policy. Prescribed full door cycle, '
         'zero initial electric energy; nominal simulation, no physical qualification.')
DEFAULT = {'schema_version': 'bf-door-system-design-v2', 'revision': 'D4',
    'mechanical': {'gap_mm': 48., 'closed_dz_mm': -30.265, 'polarity': -1},
    'circuit': {'cin_uF': 47., 'cout_uF': 100.},
    'firmware': {'interval_ms': 100.}}
FROZEN = {
    'task': {'closing_s': 2., 'holding_s': .5, 'opening_s': 2., 'settling_s': 2.,
             'angle_deg': 65., 'initial_vin_V': 0., 'diagnostic_input_A': 0.,
             'event': 'one completed motion notification during close-hold-open cycle',
             'deadline_s': 6.5, 'link_loss_probability': 0., 'scan_duty': 1., 'seed': 17},
    'model': {'remanence_T': 1.25, 'damping_ratio': .02, 'recoil_permeability': 1.,
              'tip_magnet_mm': [10., 10., 10.], 'driver_magnet_mm': [20., 20., 20.],
              'beam_limit_m': .008, 'boot_ms': 53.8, 'init_ms': 13., 'tx_ms': 5.,
              'boot_mA': .410, 'init_mA': 1.596, 'tx_mA': 3.659,
              'sleep_uA': 2., 'reset_uA': .3},
    'numerics': {'max_step_s': 5e-5, 'firmware_step_s': 1e-4, 'reltol': 1e-4,
                 'max_coupling_iterations': 8, 'energy_residual_target': .01,
                 'mesh_target': .05, 'interpolation_target': .02},
}
LIMITS = {'mechanical': {'gap_mm': (28., 70.), 'closed_dz_mm': (-35., 5.),
                         'polarity': (-1, 1)},
          'circuit': {'cin_uF': (10., 4700.), 'cout_uF': (10., 470.)},
          'firmware': {'interval_ms': (100., 500.)}}

def normalize(candidate=None):
    candidate = {} if candidate is None else candidate
    if not isinstance(candidate, dict): raise ValueError('DOOR_DESIGN_OBJECT_REQUIRED')
    if set(candidate) - set(LIMITS): raise ValueError('DOOR_FROZEN_CONDITION_OR_UNKNOWN_FIELD')
    value = copy.deepcopy(DEFAULT)
    for section, changes in candidate.items():
        if not isinstance(changes, dict) or set(changes) - set(LIMITS[section]):
            raise ValueError('DOOR_FROZEN_CONDITION_OR_UNKNOWN_FIELD')
        for key, number in changes.items():
            lo, hi = LIMITS[section][key]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                raise ValueError('DOOR_FINITE_NUMBER_REQUIRED')
            if not lo <= number <= hi or (key == 'polarity' and number not in (-1, 1)):
                raise ValueError('DOOR_DESIGN_OUT_OF_RANGE:' + key)
            value[section][key] = number
    value['frozen'] = copy.deepcopy(FROZEN)
    value['design_id'] = digest({k: v for k, v in value.items() if k != 'design_id'})
    return value

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def template_hash():
    h = hashlib.sha256()
    for p in sorted(Path(__file__).parent.glob('*')):
        if p.is_file() and p.suffix in ('.py', '.c', '.java'):
            h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()

def verify_design(value):
    expected = normalize({k: value[k] for k in LIMITS})
    if value != expected: raise ValueError('DOOR_DESIGN_IDENTITY_OR_FROZEN_DRIFT')
    return expected

