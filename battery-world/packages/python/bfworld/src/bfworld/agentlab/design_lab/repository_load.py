"""Read declared load representations without executing participant generators.

Expanded points, a compact immutable netlist reference, and explicit activity
windows are distinct witnesses. Missing points are not a numerical mismatch.
"""
import copy
from decimal import Decimal
import hashlib
import math


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('TIMELINE_FINITE_NUMBER_REQUIRED')
    return Decimal(str(value))


def _window_points(model):
    windows = model['windows_ms']; amplitudes = model['declared_amplitudes_1v8']
    stop = _number(model['timeline']['t_stop_s'])
    quantum = _number(model['emission']['edge_quantum_s'])
    factor = _number(model['referral']['factor_k'])
    quiet = _number(amplitudes['quiescent_a'])
    if not 0 < quantum < stop or factor <= 0 or quiet < 0:
        raise ValueError('TIMELINE_DOMAIN_INVALID')
    events = []

    def add(start_ms, end_ms, amplitude):
        start, end = _number(start_ms)/1000, _number(end_ms)/1000
        current = _number(amplitude)
        if not 0 <= start < end <= stop or current < 0:
            raise ValueError('TIMELINE_WINDOW_INVALID')
        events.append((start, end, current))

    for name in ('boot', 'advertising', 'notify', 'cdc_convert'):
        entry = windows[name]
        spans = entry if isinstance(entry, list) else entry['windows']
        if len(spans) > 10000:
            raise ValueError('TIMELINE_WINDOW_LIMIT')
        if isinstance(entry, dict) and entry.get('count', len(spans)) != len(spans):
            raise ValueError('TIMELINE_WINDOW_COUNT_CONFLICT')
        for start, end in spans:
            add(start, end, amplitudes[name+'_a'])
    train = windows['connection_event']
    count = train['count']
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10000:
        raise ValueError('TIMELINE_CONNECTION_COUNT_INVALID')
    first, period, pulse = (_number(train[k]) for k in ('first_ms', 'period_ms', 'pulse_ms'))
    if period <= 0 or not 0 < pulse <= period:
        raise ValueError('TIMELINE_CONNECTION_PERIOD_INVALID')
    if first+(count-1)*period != _number(train['last_ms']):
        raise ValueError('TIMELINE_CONNECTION_LAST_CONFLICT')
    for index in range(count):
        start = first+index*period
        # Decimal arithmetic keeps the declared millisecond event grid exact.
        add(float(start), float(start+pulse), amplitudes['connection_a'])

    deltas = {}
    for start, end, amplitude in events:
        deltas[start] = deltas.get(start, Decimal(0))+amplitude
        deltas[end] = deltas.get(end, Decimal(0))-amplitude
    edges = sorted(t for t in deltas if 0 < t < stop)
    if any(b-a <= quantum for a, b in zip([Decimal(0), *edges], [*edges, stop])):
        raise ValueError('TIMELINE_EDGE_QUANTUM_CONFLICT')
    def referred(value):
        result = float(value*factor)
        if not math.isfinite(result):
            raise ValueError('TIMELINE_CURRENT_OVERFLOW')
        return result
    active = quiet+deltas.get(Decimal(0), Decimal(0))
    points = [[0., referred(active)]]
    for edge in edges:
        points.append([float(edge-quantum), referred(active)])
        active += deltas[edge]
        points.append([float(edge), referred(active)])
    points.append([float(stop), referred(active+deltas.get(stop, Decimal(0)))])
    return points


def normalize_timeline(value):
    """Interpret known layouts; original artifact bytes and SHA remain unchanged."""
    model = copy.deepcopy(value)
    if 'windows_ms' in model and 'declared_amplitudes_1v8' in model:
        radio = model['radio_domain_facts']
        canonical = {'advertising_period_ms': radio['advertising_interval_ms'],
                     'connection_period_range_ms': [radio['connection_min_ms'], radio['connection_max_ms']],
                     'connection_period_ms_used': model['windows_ms']['connection_event']['period_ms'],
                     'sample_period_ms': radio['sample_ms'],
                     'policy_advertising_ms': radio['policy_advertising_ms']}
        if 'actual_radio_timing' in model and any(model['actual_radio_timing'].get(k) != v for k, v in canonical.items()):
            raise ValueError('TIMELINE_RADIO_ALIASES_DISAGREE')
        model.setdefault('actual_radio_timing', canonical)
        model['window_charge_storage_rail_c'] = model['window_charge']['referred_load_only_c']
        model['pwl_time_value_referred_to_storage_rail_a'] = _window_points(model)
        model['load_witness_method'] = 'independent declared-window staircase'
        spans = model['windows_ms']['advertising']['windows']
        train = model['windows_ms']['connection_event']
        model['segments'] = [{'name': 'advertising', 't0_s': float(_number(a)/1000)} for a, _ in spans]
        model['segments'] += [{'name': 'connection', 't0_s': float((_number(train['first_ms'])+i*_number(train['period_ms']))/1000)} for i in range(train['count'])]
        model['events_covered'] = {'sample_and_notify_2byte_s': [float(_number(t)/1000) for t in model['windows_ms']['sample_request']['instants_ms']]}
    else:
        covered = model.get('events_covered', {})
        if 'sample_and_notify_s' in covered:
            covered.setdefault('sample_and_notify_2byte_s', covered['sample_and_notify_s'])
    return model


def load_binding(model, circuit, actual_pairs):
    points = model.get('pwl_time_value_referred_to_storage_rail_a')
    if points is not None:
        equal = isinstance(points, list) and len(points) == len(actual_pairs) and all(
            isinstance(a, (list, tuple)) and len(a) == 2 and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                and abs(x-y) <= max(1e-11, abs(y)*1e-8) for x, y in zip(a, b))
            for a, b in zip(points, actual_pairs))
        return {'status': 'PASS' if equal else 'FAIL', 'pwl_equal': equal,
                'method': model.get('load_witness_method', 'expanded declared points'),
                'expected_points': len(points) if isinstance(points, list) else None,
                'actual_points': len(actual_pairs)}
    compact = model.get('emitted_expansion', {})
    expected = compact.get('pwl_file_sha256')
    if expected and compact.get('pwl_source_name') == 'Iload':
        actual = hashlib.sha256(circuit.encode()).hexdigest()
        equal = expected == actual and compact.get('pwl_points') == len(actual_pairs)
        return {'status': 'PASS' if equal else 'FAIL', 'pwl_equal': None,
                'method': 'compact immutable netlist binding', 'expected_sha256': expected,
                'actual_sha256': actual, 'actual_points': len(actual_pairs),
                'waveform_scope': 'expanded declared points unavailable'}
    return {'status': 'UNEVALUABLE', 'pwl_equal': None, 'method': 'missing load witness',
            'error': 'DECLARED_POINTS_OR_COMPACT_NETLIST_BINDING_REQUIRED'}
