#!/usr/bin/env python3
"""Read-only, small evidence package. Never dispatches, settles usage or rewrites a study."""
import argparse
import csv
import json
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace
import zipfile

import numpy as np
from bfworld.agentlab.design_pilot_view import export_projection
from bfworld.agentlab.simulation_chain.contracts import file_hash, write_json

SMALL_ARTIFACTS = {'design-spec.json', 'task-evaluation.json', 'result.json', 'energy.json',
                   'receiver.json', 'convergence.json', 'coupling-iterations.json', 'magnetic-confirmation.json'}


def verified_copy(source, target, manifest):
    name = source.name
    if name not in SMALL_ARTIFACTS or source.is_symlink() or file_hash(source) != manifest['sha256']:
        raise ValueError('EXPORT_ARTIFACT_IDENTITY:' + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def load_wave(source):
    return np.genfromtxt(source, delimiter=',', names=True)


def plots(directory, output):
    output.mkdir(parents=True,exist_ok=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    w = load_wave(directory/'waveform.csv')
    p = load_wave(directory/'program.csv')
    receiver = json.loads((directory/'receiver.json').read_text())
    fig, axes = plt.subplots(6, 1, figsize=(10, 10), sharex=True)
    stride = max(1, len(w)//4000)
    t = w['time_s'][::stride]
    for ax, name, label, factor in zip(axes[:4], ['tip_m', 'piezo_V', 'storage_V', 'supply_V'],
            ['Beam tip [mm]', 'Piezo [V]', 'Input storage [V]', 'MCU supply [V]'], [1000, 1, 1, 1]):
        ax.plot(t, w[name][::stride]*factor, color='#236fa5', lw=1)
        ax.set_ylabel(label)
        ax.grid(alpha=.15)
    axes[4].step(p['time_s'][::max(1, len(p)//4000)], p['state'][::max(1, len(p)//4000)], where='post')
    axes[4].set_ylabel('C state')
    axes[4].set_yticks(range(6), ['RESET', 'BOOT', 'WAIT', 'INIT', 'TX', 'SLEEP'])
    axes[5].set_ylabel('TX / RX events')
    axes[5].set_ylim(-.5, 1.5)
    axes[5].set_yticks([0, 1], ['TX', 'RX'])
    if not receiver['transmitted'] and not receiver['delivered']:
        axes[5].text(.5, .5, 'No complete TX; no virtual RX', transform=axes[5].transAxes, ha='center')
    else:
        for level,key in enumerate(('transmitted','delivered')):
            for packet in receiver[key]:axes[5].scatter(packet['time_s'],level,marker='|',s=60)
    axes[-1].set_xlabel('Native candidate time [s]')
    spec=json.loads((directory/'design-spec.json').read_text())
    evaluation=json.loads((directory/'task-evaluation.json').read_text())
    fig.suptitle(f"{directory.name}: gap {spec['mechanical']['gap_mm']} mm, Cin {spec['circuit']['cin_uF']} uF; {evaluation['nominal_task_status']}")
    fig.tight_layout()
    for ext in ('svg', 'png'):
        fig.savefig(output/('candidate-time-axis.'+ext), dpi=160)
    plt.close(fig)
    # Display-only sampled rows retain original units; quantitative metrics use full-source results.
    for source, data in [('waveform', w), ('program', p)]:
        indices = np.unique(np.r_[np.arange(0, len(data), max(1, len(data)//4000)), len(data)-1])
        np.savetxt(output/(source+'-display.csv'), np.column_stack([data[n][indices] for n in data.dtype.names]),
                   delimiter=',', header=','.join(data.dtype.names), comments='', fmt='%.12g')


def export(home, study, output):
    if output.exists():
        raise ValueError('EXPORT_EXISTS: preserve original export')
    if study.parent.resolve() != (home/'studies').resolve():
        raise ValueError('EXPORT_STUDY_SCOPE')
    output.mkdir(parents=True)
    db_path = home/'state/workbench.sqlite'
    def connect():
        db = sqlite3.connect(db_path.as_uri()+'?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        return db
    view = export_projection(SimpleNamespace(connect=connect))
    protocol = json.loads((study/'protocol.json').read_text())['id']
    view['projection']['studies'] = [s for s in view['projection']['studies'] if s['protocol']==protocol]
    view['projection']['trials'] = [t for t in view['projection']['trials'] if t['protocol']==protocol]
    owners = {t['owner'] for t in view['projection']['trials'] if t['owner']}
    view['projection']['billing_blockers'] = [b for b in view['projection']['billing_blockers'] if b['owner'] in owners]
    # CSV is filtered by protocol too; other historical studies are not part of this package.
    rows = list(csv.DictReader(view['trials_csv'].splitlines()))
    with (output/'runs.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(r for r in rows if r['protocol']==protocol)
    view.pop('trials_csv')
    write_json(output/'projection.json', view)
    sources = {}
    for name in ('seal.json', 'agent-runtime-seal.json', 'protocol.json', 'task.json', 'continuation-authorization.json', 'agent-runtime-continuation-seal.json', 'active-runtime-amendment.json', 'completion-allocation-amendment.json', 'tool-delivery-amendment.json', 'tool-capacity-amendment.json'):
        p = study/name
        if not p.exists():continue
        sources[str(p)] = file_hash(p)
        shutil.copyfile(p, output/name)
    if (study/'runtime-amendments').exists():shutil.copytree(study/'runtime-amendments',output/'runtime-amendments')
    actual = []
    for trial in view['projection']['trials']:
        if trial.get('planned_only'):
            continue
        root = study/'trials'/trial['trial']
        attempts=sorted(root.glob('continuation-*/receipt.json'),key=lambda p:int(p.parent.name.split('-')[-1]))
        continuation=attempts[-1].parent if attempts else root/'continuation-1'
        if (continuation/'receipt.json').exists():
            shutil.copytree(root,output/'preserved-attempts'/trial['trial'],ignore=shutil.ignore_patterns('events.json','input.json'))
            root=continuation
        # Final reconciliation is an additional snapshot, never a replacement
        # for a failed attempt or a late provider settlement.
        final=study/'trials'/trial['trial']/'final-reconciliation'
        if (final/'receipt.json').exists():root=final
        for name in ('receipt.json', 'usage.json', 'events.json'):
            sources[str(root/name)] = file_hash(root/name)
        receipt = json.loads((root/'receipt.json').read_text())
        write_json(output/(trial['trial']+'-receipt.json'), receipt)
        usage = json.loads((root/'usage.json').read_text())
        write_json(output/(trial['trial']+'-usage.json'), usage)
        events = json.loads((root/'events.json').read_text())
        actions = []
        for event in events:
            data = json.loads(event['data']) if isinstance(event['data'], str) else event['data']
            if data.get('type')=='tool_execution_start':
                actions.append({'seq': event['seq'], 'time': event['created'], 'tool_call_id': data['toolCallId'],
                                'tool': data['toolName'], 'args': data['args']})
        write_json(output/(trial['trial']+'-actions.json'), actions)
        for job in trial['jobs']:
            directory = home/'engineering'/job['id']
            with connect() as db:
                result = json.loads(db.execute('SELECT result FROM engineering_jobs WHERE id=? AND owner=?',
                                               (job['id'], trial['owner'])).fetchone()[0])
            artifacts = {a['name']: a for a in result['artifacts']}
            target = output/'candidates'/job['id']
            for name in sorted(SMALL_ARTIFACTS & artifacts.keys()):
                verified_copy(directory/name, target/name, artifacts[name])
                sources[str(directory/name)] = artifacts[name]['sha256']
            for name in ('waveform.csv', 'program.csv', 'engineering-evidence.zip'):
                if name in artifacts:
                    if file_hash(directory/name)!=artifacts[name]['sha256']:
                        raise ValueError('EXPORT_SOURCE_HASH:'+name)
                    sources[str(directory/name)] = artifacts[name]['sha256']
            actual.append({**job, 'trial': trial['trial']})
            if 'waveform.csv' in artifacts:
                plots(directory, target)
                # Overview uses the most recently evaluated waveform; every candidate keeps its own plot.
                for ext in ('png','svg'):shutil.copyfile(target/('candidate-time-axis.'+ext),output/('candidate-time-axis.'+ext))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    mapping = view['projection']['studies'][0]['initial_runs']
    points = [{'id': r['id'], 'candidate': json.loads((study/'runs'/r['id']/'design-spec.json').read_text()),
               'run_status': r['evaluation']['run_status'], 'evaluation': r['evaluation']} for r in mapping]
    points += actual
    fig, ax = plt.subplots(figsize=(9, 5))
    groups={}
    for item in points:
        spec=item['candidate'];evaluation=item.get('evaluation') or {}
        category=('satisfied' if evaluation.get('nominal_task_status')=='satisfied' else 'unsatisfied') if item['run_status']=='completed' else item['run_status']
        key=(spec.get('mechanical',{}).get('gap_mm',48),spec.get('circuit',{}).get('cin_uF',47),category)
        groups.setdefault(key,[]).append(item['id'])
    colors={'satisfied':'#27845b','unsatisfied':'#c25b3b','out_of_domain':'#777777','numerical_fail':'#7954ac','tool_fail':'#a83535'}
    marked=set()
    for (gap,cap,category),ids in groups.items():
        ax.scatter(gap,cap,marker='o' if category in ('satisfied','unsatisfied') else 'x',c=colors.get(category,'#999999'),s=80,label=category if category not in marked else None)
        marked.add(category)
        ax.annotate(ids[0][-6:] if len(ids)==1 else str(len(ids))+' runs',(gap,cap),xytext=(5,7),textcoords='offset points',fontsize=8)
    ax.legend(fontsize=8)
    ax.set(xlabel='Magnet gap [mm]', ylabel='Input storage [uF]',
           title='Observed candidates only; execution failures and task outcomes separated')
    ax.grid(alpha=.15)
    fig.tight_layout()
    fig.savefig(output/'candidate-map.png', dpi=160)
    fig.savefig(output/'candidate-map.svg')
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, max(4,len(actual)*.45)))
    first = actual[0]['created']
    for index, job in enumerate(actual):
        spec = job['candidate']
        ax.plot([job['created']-first, job['ended']-first], [index, index], linewidth=8,
                color='#777777' if job['run_status']=='out_of_domain' else '#c25b3b')
        ax.text(job['ended']-first+2, index, job['run_status'], fontsize=9, va='center')
    ax.set_yticks(range(len(actual)), [j['trial']+' / gap '+str(j['candidate'].get('mechanical',{}).get('gap_mm',48))+' mm' for j in actual])
    ax.set(xlabel='Wall time from first actual candidate [s]', title=f"Real Pi revisions: {len(actual)} executed jobs; {sum(bool(t['submission']) for t in view['projection']['trials'])} submissions")
    ax.grid(axis='x', alpha=.15)
    fig.tight_layout()
    fig.savefig(output/'pi-revision-trajectory.png', dpi=160)
    fig.savefig(output/'pi-revision-trajectory.svg')
    plt.close(fig)
    write_json(output/'stop-receipt.json', {'schema_version': 'integration-pilot-stop-v1',
        'paid_dispatch_paused': bool(view['projection']['billing_blockers']) and not view['projection']['studies'][0]['conservative_continuation'],
        'blockers': view['projection']['billing_blockers'],
        'planned_unstarted': sum(bool(t.get('planned_only')) for t in view['projection']['trials']),
        'physical_success': False, 'architecture_opened': False, 'method_comparison_started': False,
        'reason': 'Explicit user continuation amendment retains unknown reservations and original failed attempts; same task and candidate limits.'})
    (output/'README.md').write_text('''# BFA-035 先导证据包

本包包含实际候选结果、费用上界、原生时间轴、设计空间观察和真实 Pi 修改轨迹。
逐条执行与提交状态见 projection.json 和 runs.csv。首次失败及恢复续跑分别保存。
未知用量保留预留费用，不计为已结算。图形中的抽样 CSV 仅用于展示；完整来源哈希、任务身份与结果指标另行保存。
工程任务 SUCCEEDED 表示执行完成，不表示产品成功。缓存复用与原生计算耗时、端到端耗时分别记录。
不包含凭据、原始会话正文、加密厂商模型或大型 RAW。原生大文件仍留在本机。
没有可行正例，磁场/全旋转 FEM 门槛未满足，不能用于物理设计排序、方法优越性或 RSI 结论。
''')
    write_json(output/'sources.json', {'files': sources, 'exporter_sha256': file_hash(Path(__file__)),
        'scope': 'Verified original artifacts and immutable study receipts; display-derived rows are explicitly labelled.'})
    shutil.copyfile(__file__, output/'exporter.py')
    write_json(output/'manifest.json', {'schema_version': 'pilot-small-package-v1', 'files': {
        str(p.relative_to(output)): {'sha256': file_hash(p), 'bytes': p.stat().st_size}
        for p in sorted(output.rglob('*')) if p.is_file()}})
    archive = output.with_suffix('.zip')
    if archive.exists():
        raise ValueError('EXPORT_ARCHIVE_EXISTS')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file():
                z.write(p, str(p.relative_to(output)))
    index = study/'evidence-index.json'
    if index.exists():
        prior=study/('evidence-index-'+file_hash(index)[:12]+'.json')
        if not prior.exists():shutil.copyfile(index,prior)
    write_json(index, {'schema_version': 'pilot-evidence-index-v1', 'assets': {
        p.name: {'path': str(p.relative_to(home)), 'sha256': file_hash(p)}
        for p in [archive, output/'candidate-time-axis.png', output/'candidate-map.png', output/'pi-revision-trajectory.png']}})
    print(json.dumps({'path': str(archive), 'bytes': archive.stat().st_size, 'sha256': file_hash(archive),
                      'actual_candidates': len(actual), 'paid_dispatch': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.home, args.study, args.output)
