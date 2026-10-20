#!/usr/bin/env python3
"""Render small saved-data tables and one vector figure. No model or apparatus imports."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import os

HERE = Path(__file__).resolve().parent
ARMS = ['H0', 'H0-history', 'ordinary', 'proposed']
LABELS = [r'Fixed $H_0$', r'$H_0$ + history', 'Ordinary reflection', 'Proposed method']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-sources', action='store_true', help='Read canonical source hashes; never executes their contents.')
    args = parser.parse_args()
    e = json.loads((HERE / 'evidence.json').read_text())
    checked = []
    if args.verify_sources:
        for src in e['source_files']:
            p = Path(src['path'])
            assert p.stat().st_size == src['bytes'], str(p)
            assert hashlib.sha256(p.read_bytes()).hexdigest() == src['sha256'], str(p)
            checked.append(src['path'])
        for row in e['C_rows']:
            p = Path(row['result_path'])
            assert hashlib.sha256(p.read_bytes()).hexdigest() == row['result_sha256'], str(p)
            raw = json.loads(p.read_text())
            assert raw['episode'] == row['episode_id']
            assert raw['status'] == row['status']
            assert raw['native_dispatches'] == 0
            assert raw['accounting']['requests'] == row['requests']
            checked.append(str(p))
    formal = [r for r in e['C_rows'] if r['stage'] == 'formal']
    assert len(formal) == 24 and len({r['episode_id'] for r in formal}) == 24
    for arm in ARMS:
        rows = [r for r in formal if r['arm'] == arm]
        a = e['C_arms'][arm]
        assert len(rows) == a['planned'] == a['finished'] == 6
        assert all(r['independent_status'] == 'PASS' and r['actual_artifact_submitted'] for r in rows)
        for gate in ['event_matching', 'timely_receive', 'timestamp_accuracy']:
            assert sum(r[gate] == 'PASS' for r in rows) == a[gate + '_pass'] == 6
        assert sum(r['requests'] for r in rows) == a['requests']
        assert math.isclose(sum(r['charge_upper_usd'] for r in rows), a['charge_upper_usd'], abs_tol=1e-10)
        assert sum(r.get('failed_frozen_relation_on_passed_design') is True for r in rows) == a['failed_frozen_relation_on_passed_design']
        assert not any(r['unknown_usage'] for r in rows)
        if arm in ['ordinary', 'proposed']:
            assert all(r['consumed_method_sha256'] == e['C_frozen_methods'][arm]['semantic_sha256'] for r in rows)
    gen = HERE / 'generated'
    gen.mkdir(exist_ok=True)
    lines = [r'\begin{table}[htbp]', r'\centering\small',
             r'\begin{tabular}{@{}lrrrr@{}}', r'\toprule',
             r'Arm & Service PASS & Requests & USD upper & $H$ false on PASS \\', r'\midrule']
    for arm, label in zip(ARMS, LABELS):
        a = e['C_arms'][arm]
        false = '---' if arm in ARMS[:2] else f"{a['failed_frozen_relation_on_passed_design']}/6"
        lines.append(f"{label} & 6/6 & {a['requests']} & {a['charge_upper_usd']:.7f} & {false} " + r'\\')
    lines += [r'\bottomrule', r'\end{tabular}',
              r'\caption{C24 formal transfer: three task conditions times two fresh contexts per arm. Every design passes event matching, timely reception and timestamp accuracy. The last column counts successful designs with at least one frozen relation returning false; it is not an error rate or a proof of unsoundness. The fixed controls submit no learned relation set. Costs here exclude the separately listed formation, validation and first-use stages.}\label{tab:cformal}', r'\end{table}']
    (gen / 'c-formal.tex').write_text('\n'.join(lines) + '\n')
    stages = [r for r in e['C_rows'] if r['stage'] != 'formal']
    order = ['C-formation-ordinary', 'C-formation-proposed', 'C-validation-ordinary', 'C-validation-proposed', 'C-first-proposed']
    names = ['Ordinary formation', 'Proposed formation', 'Ordinary validation', 'Proposed validation', 'Proposed first use']
    lines = [r'\begin{table}[htbp]', r'\centering\small', r'\begin{tabular}{@{}lrrl@{}}',
             r'\toprule', r'Stage & Requests & USD upper & Independent result \\', r'\midrule']
    for key, name in zip(order, names):
        r = next(r for r in stages if r['episode_id'] == key)
        status = 'Structural admission' if r['stage'] == 'formation' else 'Design PASS'
        lines.append(f"{name} & {r['requests']} & {r['charge_upper_usd']:.7f} & {status} " + r'\\')
    total_q = sum(r['requests'] for r in e['C_rows'])
    total_usd = sum(r['charge_upper_usd'] for r in e['C_rows'])
    assert total_q == 153 and math.isclose(total_usd, 3.4548018, abs_tol=1e-9)
    lines += [r'\midrule', r'Formal transfer only & 126 & 2.7393975 & 24/24 design PASS \\',
              f'All 29 C episodes & {total_q} & {total_usd:.7f} & No missing usage ' + r'\\',
              r'\bottomrule', r'\end{tabular}',
              r'\caption{C learning and execution costs, charged once per actual episode. Both methods are carried unchanged into final use; validation is not an outcome-based selection gate. The first-use episode belongs only to the proposed arm and is excluded from C24. USD values use frozen token rates and are not invoices.}\label{tab:cstages}', r'\end{table}']
    (gen / 'c-stages.tex').write_text('\n'.join(lines) + '\n')
    with (gen / 'c-formal.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['episode_id', 'task_id', 'arm', 'service', 'event_matching', 'timely_receive', 'timestamp_accuracy', 'requests', 'upper_usd', 'frozen_relation_false_on_pass', 'candidate_json', 'false_relations_json'])
        for r in formal:
            false = [v for v in r.get('frozen_method_relations', []) if v['result'] is False]
            writer.writerow([r['episode_id'], r['task_id'], r['arm'], r['independent_status'], r['event_matching'], r['timely_receive'], r['timestamp_accuracy'], r['requests'], f"{r['charge_upper_usd']:.7f}", r.get('failed_frozen_relation_on_passed_design'), json.dumps(r['submitted_candidate'], sort_keys=True), json.dumps(false, sort_keys=True)])

    # Keep Matplotlib's small, rebuildable font cache within the admitted scratch.
    os.environ.setdefault('MPLCONFIGDIR', str(HERE / '.build/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8.5,
                         'pdf.fonttype': 42, 'ps.fonttype': 42, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.labelsize': 8.5,
                         'xtick.labelsize': 8, 'ytick.labelsize': 8,
                         'axes.linewidth': .6, 'xtick.major.width': .6, 'ytick.major.width': .6})
    colors = ['#777777', '#4075A6', '#BD7346', '#43836D']
    fig, axes = plt.subplots(2, 2, figsize=(6.55, 4.9), constrained_layout=True)
    y = list(range(4))
    labels = ['Fixed H₀', 'H₀ + history', 'Ordinary', 'Proposed']
    for ax in axes.flat:
        ax.set_yticks(y, labels)
        ax.invert_yaxis()
        ax.tick_params(length=3)
    values = [[6]*4,
              [e['C_arms'][a]['requests'] for a in ARMS],
              [e['C_arms'][a]['charge_upper_usd'] for a in ARMS]]
    titles = ['a  Complete time-component service', 'b  Formal model requests', 'c  Formal fixed-rate charge estimate']
    xlabels = ['Successful designs (of 6)', 'Requests', 'USD upper estimate']
    for ax, v, title, xlabel in zip(list(axes.flat)[:3], values, titles, xlabels):
        ax.barh(y, v, color=colors, height=.53)
        ax.set_title(title, loc='left', fontsize=9, pad=10)
        ax.set_xlabel(xlabel)
        ax.set_xlim(0, max(v)*1.25)
        ax.set_axisbelow(True)
        ax.grid(axis='x', color='#E5E5E5', linewidth=.4)
        for yy, val in zip(y, v):
            txt = f'{val:.3f}' if xlabel.startswith('USD') else ('6/6' if xlabel.startswith('Successful') else str(val))
            ax.text(val + max(v)*.025, yy, txt, va='center', fontsize=8)
    ax = axes[1, 1]
    ax.set_title('d  Frozen relation return on final D', loc='left', fontsize=9, pad=10)
    tasks = ['C-phase', 'C-confirm', 'C-definition']
    cells = [(task, rep) for task in tasks for rep in [1, 2]]
    for yy, arm in enumerate(ARMS):
        for xx, (task, rep) in enumerate(cells):
            row = next(r for r in formal if r['episode_id'] == f'{task}-{arm}-r{rep}')
            false = row.get('failed_frozen_relation_on_passed_design')
            color = '#FFFFFF' if false is None else ('#BD7346' if false else '#DCE9E3')
            ax.add_patch(Rectangle((xx-.43, yy-.34), .86, .68, facecolor=color, edgecolor='#AFAFAF', linewidth=.5, hatch='///' if false is None else None))
            if false is not None: ax.text(xx, yy, 'F' if false else 'T', ha='center', va='center', color='white' if false else '#244638', fontsize=8)
    ax.set_xlim(-.6, 5.6); ax.set_ylim(3.7, -.7)
    ax.set_xticks(range(6), ['r1', 'r2']*3)
    ax.set_xlabel('Phase        Confirm.        Definition', labelpad=5)
    for x in [1.5, 3.5]: ax.axvline(x, color='#BFBFBF', linewidth=.5)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.legend(handles=[Patch(facecolor='#DCE9E3', edgecolor='#AFAFAF', label='T: all true'),
                       Patch(facecolor='#BD7346', label='F: ≥1 false'),
                       Patch(facecolor='white', edgecolor='#AFAFAF', hatch='///', label='No H checks')],
              loc='upper left', bbox_to_anchor=(-.02, -.33), frameon=False, fontsize=6.5, ncol=3,
              handlelength=1.0, columnspacing=.7)
    fig.savefig(HERE / 'figures/c24-evidence.pdf', metadata={'Title': 'C24: device success, formal cost and frozen relations', 'Author': 'Saved-data rendering', 'CreationDate': None, 'ModDate': None})
    plt.close(fig)
    report = {'schema': 'bf-abc-C-paper-asset-check-v1', 'formal_rows': 24, 'all_C_episodes': 29,
              'all_C_requests': total_q, 'all_C_upper_usd': round(total_usd, 7),
              'source_hashes_verified': checked,
              'figure_contract': {'conclusion': 'All designs pass; proposed has no advantage over equal-history H0; relation truth is separate.',
                                  'archetype': '2x2 small multiples: service, requests, cost, relation matrix',
                                  'statistics': 'Exact finite counts; no error bars, p-values or independent-formation claim.',
                                  'semantic_boundary': 'False relation is not automatic evidence of H unsoundness.',
                                  'export': 'Single PDF vector; Matplotlib pdf.fonttype=42; no raster plot layers.'},
              'models': 0, 'scientific_executions': 0, 'native_dispatches': 0}
    (gen / 'asset-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['formal_rows', 'all_C_episodes', 'all_C_requests', 'all_C_upper_usd']}))


if __name__ == '__main__':
    main()
