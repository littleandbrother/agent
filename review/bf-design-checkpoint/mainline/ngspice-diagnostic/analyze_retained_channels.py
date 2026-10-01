#!/usr/bin/env python3
"""Read-only postprocessing of the four already-completed solver outputs."""
import bisect
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
names = ['time_s','drive','displacement_m','velocity_m_s','piezo_v','storage_v','enabled','stage_time_s','force_n','rectifier_a','load_a','diode_loss_w','quiescent_a']

def read(name):
    path = ROOT / 'runs' / name / 'out.tsv'
    with path.open() as f:
        next(f)
        return [dict(zip(names, map(float, line.split()))) for line in f if line.strip()]

def interpolate(rows, times, t, field):
    i = bisect.bisect_left(times, t)
    if i < len(times) and times[i] == t:
        return rows[i][field]
    if i == 0 or i == len(times):
        raise ValueError('No extrapolation permitted')
    left, right = rows[i-1], rows[i]
    alpha = (t-left['time_s']) / (right['time_s']-left['time_s'])
    return left[field] + alpha * (right[field]-left[field])

result = {'scope': 'postprocessing only; no extra solves; exported channels, not hidden solver state', 'pairs': {}}
for label in ('10us','5us'):
    a,b = read('baseline-'+label),read('feedback-'+label)
    ta,tb = [r['time_s'] for r in a],[r['time_s'] for r in b]
    prefix = 0
    for ra,rb in zip(a,b):
        if ra != rb: break
        prefix += 1
    pa,pb = max(a,key=lambda r:abs(r['displacement_m'])),max(b,key=lambda r:abs(r['displacement_m']))
    starts = {k:next(r['time_s'] for r in rows if r['enabled']>.5) for k,rows in [('baseline',a),('feedback',b)]}
    loads = {k:next(r['time_s'] for r in rows if r['load_a']>0) for k,rows in [('baseline',a),('feedback',b)]}
    assert a[-1]['time_s'] == b[-1]['time_s'] == .25
    common = sorted(set(t for t in ta+tb if max(ta[0],tb[0]) <= t <= min(ta[-1],tb[-1])))
    deltas = [(interpolate(b,tb,t,'displacement_m')-interpolate(a,ta,t,'displacement_m'),t) for t in common]
    delta,t = max(deltas,key=lambda x:abs(x[0]))
    result['pairs'][label] = {
        'initial_identical_full_rows': prefix,
        'identical_prefix_end_time_s': a[prefix-1]['time_s'],
        'first_activation_s': starts,
        'first_nonzero_load_s': loads,
        'baseline_peak': pa, 'feedback_peak': pb,
        'both_peaks_precede_any_load': max(pa['time_s'],pb['time_s']) < min(loads.values()),
        'all_premeasured_peak_load_values_zero': all(r['load_a']==0 for rows in [a,b] for r in rows if r['time_s'] <= max(pa['time_s'],pb['time_s'])),
        'terminal_time_s': .25,
        'baseline_terminal': a[-1], 'feedback_terminal': b[-1],
        'terminal_feedback_minus_baseline_displacement_m': b[-1]['displacement_m']-a[-1]['displacement_m'],
        'interpolated_max_abs_displacement_difference_m':abs(delta),
        'interpolated_max_difference_signed_m':delta,
        'interpolated_max_difference_time_s':t,
        'interpolation_method':'Piecewise linear on union of both exported time grids, within common support; diagnostic only, no certified error bound',
    }
result['raw_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'runs').glob('*/out.tsv'))}
(ROOT / 'CHANNEL-ANALYSIS.json').write_text(json.dumps(result,indent=2)+'\n')
for label,p in result['pairs'].items():
    print(label,json.dumps({k:p[k] for k in ['identical_prefix_end_time_s','first_activation_s','both_peaks_precede_any_load','terminal_feedback_minus_baseline_displacement_m','interpolated_max_abs_displacement_difference_m','interpolated_max_difference_time_s']}))
