"""One versioned contract for feedback inputs, program ABI and validation.

Task requirements are operator-owned. Candidate code controls activities;
the apparatus owns current amplitudes, power/reset semantics and the receiver.
"""
from copy import deepcopy
import math

VERSION = 'piezo-feedback-v1'
ABI = 'bf-feedback-program-abi-v1'
GATES = ['source_model', 'load_binding', 'power_service', 'receiver_service',
         'coupling_numerics', 'delivery_version']
STATES = {'off': 0, 'idle': 1, 'sample': 2, 'tx': 3}
FIELDS = {
    'length_m': ('m', .02, .1), 'width_m': ('m', .002, .03),
    'substrate_m': ('m', .00005, .001), 'piezo_m': ('m', .00005, .001),
    'tip_mass_kg': ('kg', 0, .02), 'storage_f': ('F', .000001, .02),
    'output_f': ('F', .000001, .02), 'inductance_h': ('H', .000001, .001)}
UNITS = {'frequency_hz': 'Hz', 'acceleration_peak_m_s2': 'm/s2', 'damping_ratio': '1',
    'material': 'SI', 'duration_s': 's', 'initial_storage_v': 'V', 'initial_output_v': 'V',
    'start_v': 'V', 'brownout_v': 'V', 'pgood_min_v': 'V', 'current_model': 'A',
    'minimum_supply_v': 'V', 'minimum_sample_s': 's', 'minimum_tx_s': 's',
    'sample_validity_s': 's', 'sensor_value': '1'}
CHECK_ONLY = {'minimum_supply_v', 'minimum_sample_s', 'minimum_tx_s', 'sample_validity_s', 'sensor_value'}
NUMERICS = {'program_step_s': .001, 'refinement': 2, 'max_iterations': 12,
    'current_tolerance_a': 1e-12, 'voltage_tolerance_v': .001,
    'native_max_step_s': .0001, 'native_timeout_s': 600,
    'relative_mechanical_residual': .02, 'energy_absolute_tolerance_j': 2e-6,
    'load_current_tolerance_a': 1e-7, 'refinement_energy_relative': .03,
    'refinement_event_steps': 2, 'linear_displacement_ratio': .05,
    'initial_condition_tolerance_v': .003}

HEADER = '''#ifndef BF_FEEDBACK_H
#define BF_FEEDBACK_H
/* One call chooses activity on [t_s,t_s+dt_s). Time/voltage/PGOOD are observations.
 * The supervisor invokes bf_reset at power loss; all program state is volatile.
 * Current amplitudes and brownout admission belong to the device model.
 * BF_OFF belongs to the supervisor. Powered code returns IDLE/SAMPLE/TX.
 * SAMPLE/TX are complete only after a normal transition while powered. */
enum { BF_OFF=0, BF_IDLE=1, BF_SAMPLE=2, BF_TX=3 };
void bf_reset(void);
int bf_step(double t_s, double dt_s, double supply_v, int pgood);
unsigned bf_sequence(void);
unsigned bf_value(void);
unsigned bf_checksum(void);
#endif
'''


def spec():
    return {'adapter': VERSION, 'abi': ABI, 'header': HEADER, 'states': STATES,
        'observations': ['elapsed time', 'previous-interval minimum MCU VDD', 'PGOOD'],
        'reset': 'volatile program reset on loss of power; start admission requires VDD and PGOOD',
        'current': 'frozen task current_model, tapered below 1.8 V by the declared device model',
        'numerics': deepcopy(NUMERICS), 'power_model': 'LTC3588-1 vendor macro-model; D1=0,D0=VIN2',
        'writable_files': ['design.json', 'firmware/main.c', 'notes/'],
        'physical_scope': 'linear reciprocal piezo mode, vendor PMIC, declared state currents, host C, digital RX'}


def validate(raw):
    s = raw['scenario']
    if set(s) - set(UNITS) - {'boundary', 'parameter_basis'} or set(UNITS) - set(s):
        raise ValueError('FEEDBACK_SCENARIO_FIELDS')
    for key in set(UNITS) - {'material', 'current_model', 'sensor_value'}:
        v = s[key]
        if type(v) not in (float, int) or not math.isfinite(v) or v < 0:
            raise ValueError('FEEDBACK_SCENARIO_VALUE:' + key)
    if not (1 <= s['frequency_hz'] <= 1000 and .001 <= s['damping_ratio'] <= .2 and
            .01 <= s['duration_s'] <= 120 and 0 <= s['initial_storage_v'] <= 18 and
            0 <= s['initial_output_v'] <= 2.6 and 1.8 <= s['brownout_v'] < s['start_v'] <= 2.5 and
            0 < s['pgood_min_v'] <= 2.5 and 0 < s['minimum_supply_v'] <= 2.5 and
            0 < s['minimum_sample_s'] <= 1 and 0 < s['minimum_tx_s'] <= 1 and s['sample_validity_s'] > 0):
        raise ValueError('FEEDBACK_SCENARIO_DOMAIN')
    if type(s['sensor_value']) is not int or not 0 <= s['sensor_value'] <= 65535:
        raise ValueError('FEEDBACK_SENSOR_VALUE')
    m = s['material']
    if not isinstance(m, dict) or set(m) != {'substrate_E_pa', 'piezo_E_pa', 'substrate_density',
            'piezo_density', 'relative_permittivity', 'd31_m_v'}:
        raise ValueError('FEEDBACK_MATERIAL_FIELDS')
    for k, v in m.items():
        if type(v) not in (float, int) or not math.isfinite(v) or (k != 'd31_m_v' and v <= 0):
            raise ValueError('FEEDBACK_MATERIAL_VALUE')
    c = s['current_model']
    if not isinstance(c, dict) or set(c) != {'id', 'values_a', 'source'} or not isinstance(c['id'], str) or not c['id']:
        raise ValueError('FEEDBACK_CURRENT_MODEL')
    if set(c['values_a']) != set(STATES) or any(type(v) not in (float, int) or not math.isfinite(v) or
            not 0 <= v <= .1 for v in c['values_a'].values()):
        raise ValueError('FEEDBACK_CURRENT_VALUES')
    if not isinstance(c['source'], dict) or c['source'].get('kind') not in ('declared', 'datasheet', 'measurement') or not c['source'].get('locator'):
        raise ValueError('FEEDBACK_CURRENT_PROVENANCE')
    n = raw['acceptance']['receiver_service'].get('minimum_packets')
    if type(n) is not int or n < 1: raise ValueError('FEEDBACK_MINIMUM_PACKETS')


def interfaces():
    return [{'id': 'piezo-pmic', 'producer': 'linear-piezo-mode', 'consumer': 'LTC3588-1',
        'executor': VERSION, 'checker': 'bf-feedback-validation-v1', 'input_paths': ['design.json'],
        'affected_gates': ['source_model', 'power_service', 'coupling_numerics'], 'units': 'SI',
        'initial_state': 'task scenario VIN/VOUT; other reactive states zero', 'model_scope': 'reciprocal modal source and vendor bridge/buck'},
        {'id': 'power-program', 'producer': 'MCU VDD + PGOOD', 'consumer': ABI,
        'executor': VERSION, 'checker': 'bf-feedback-validation-v1', 'input_paths': ['design.json', 'firmware/main.c'],
        'affected_gates': GATES[:-1], 'units': 's,V,A', 'initial_state': 'fresh volatile program each feedback iteration',
        'model_scope': 'voltage-driven compiled host program and fixed state current model'},
        {'id': 'program-power', 'producer': 'compiled program states', 'consumer': 'LTC3588-1 Bload',
        'executor': VERSION, 'checker': 'bf-feedback-validation-v1', 'input_paths': ['firmware/main.c'],
        'affected_gates': ['load_binding', 'power_service', 'receiver_service', 'coupling_numerics'],
        'units': 's,A', 'initial_state': 'off leakage', 'model_scope': 'converged load waveform and independent digital receiver'}]
