#!/usr/bin/env python3
"""Read sealed pilot runs, independently re-evaluate and export a lightweight audit."""
import argparse
import csv
import json
import hashlib
from pathlib import Path
import shutil
import zipfile
import textwrap

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from bfworld.agentlab.simulation_chain.contracts import file_hash, write_json
from bfworld.agentlab.simulation_tasks import evaluate
from run_design_pilot import DEFAULT_ROOT, prepare, verify_run


def evidence_notes(root, out, rows, cold):
    """Human-readable observations derived only from preserved native receipts."""
    recoveries = {r['repeat_of']: r for r in rows if r['repeat_of']}
    unique = [recoveries.get(r['id'], r) for r in rows if not r['cold_control'] and not r['repeat_of']]
    completed = [r for r in unique if r['run_status'] == 'completed']
    energy_rows = []
    for r in completed:
        result = json.loads((root/'runs'/r['id']/'result.json').read_text())
        e = result.get('energy_ledger', {})
        energy_rows.append({'id': r['id'], **{k: e.get(k) for k in (
            'initial_mechanical_piezo_J', 'external_force_work_J', 'mechanical_loss_J',
            'pmic_port_energy_J', 'relative_residual')},
            'peak_tip_mm': result.get('metrics', {}).get('peak_tip_mm'),
            'states_reached': result.get('metrics', {}).get('program_states_reached')})
    write_json(out/'energy-comparison.json', energy_rows)
    def number(v): return '—' if v is None else f'{v:.6g}'
    lines = ['# 门磁受限设计先导：实际运行记录', '',
        '本报告区分工具正常执行、名义任务达标和物理验证。所有候选由预声明脚本安排，不能当作 Agent 自主设计成果。', '',
        f'已保存 {len(rows)} 次原生尝试，覆盖 {len(unique)} 个预声明设计与 {len(cold["comparisons"])} 次独立空缓存复算。',
        f'同设计环境恢复另有 {len(recoveries)} 次；原始失败记录保留在 runs.csv 中。下表在存在恢复时展示恢复后的结果，未删除失败。', '',
        '| 候选 | 间距 mm | 输入/输出电容 μF | 间隔 ms | 执行状态 | 名义任务 | VIN 峰值 V | 完整 TX |',
        '|---|---:|---:|---:|---|---|---:|---:|']
    for r in unique:
        lines.append(f'| {r["id"]} | {r["gap_mm"]} | {r["cin_uF"]}/{r["cout_uF"]} | {r["interval_ms"]} | {r["run_status"]} | {r["nominal_task"]} | {number(r["peak_storage_V"])} | {number(r["complete_tx"])} |')
    lines += ['', '## 能量沿途到了哪里', '',
        '电容初始电压为零；梁仍包含模型计算的初始磁预加载能量，不能把它描述成所有初始能量都为零。下表为有符号净能量，外力负功表示从梁/压电系统向外交换的净能量。', '',
        '| 候选 | 初始机电能 μJ | 外力净功 μJ | 机械损耗 μJ | PMIC 端口净能量 μJ | 梁峰值 mm |',
        '|---|---:|---:|---:|---:|---:|']
    for e in energy_rows:
        cells = [f'{e[k]*1e6:.3f}' for k in ['initial_mechanical_piezo_J','external_force_work_J','mechanical_loss_J','pmic_port_energy_J']]
        lines.append('| '+e['id']+' | '+' | '.join(cells)+f' | {e["peak_tip_mm"]:.3f} |')
    lines += ['', '机械/压电端口的能量守恒检查不等价于 PMIC 加密模型内部损耗被独立确认。当前能量结果提示应检查加载与释放过程，尚不能保证更改某一结构就会成功。']
    lines += ['', '## 当前可支持的结论', '',
        '- 修改确实经过了声明的 CAD、力表、电源和程序配置路径。缓存复用与原生重算次数见逐运行表。',
        '- out_of_domain 表示当前模型不能评价该候选；tool_fail 表示执行环境失败。两者都不能解释为产品物理不可行。',
        f'- 已完成联合求解的独立设计有 {len(completed)} 个，其中名义任务满足 {sum(r["nominal_task"] == "satisfied" for r in unique)} 个。有限取样不能证明整个空间不可行。',
        '- 磁场网格及完整旋转 FEM 覆盖的缺口仍保留；没有物理合格设计排序，没有实物校准或可制造产品验收。',
        '- 降低电容后的更高电压只是诊断量，不能替代完整发送与正确接收的任务目标。', '',
        '## 数值重复与环境干预', '',
        'cold-repeat.json 给出空缓存复算的波形偏差，以及 C 程序/接收记录是否一致。它与热缓存读取一致分开统计。',
        'environment/ 保留云占位故障、本地运行环境迁移和同设计恢复的说明；这些是操作者环境修复，不是 Agent 行为。', '',
        '## 下一阶段', '',
        'Pi 的付费运行状态以 summary.json 和真实轨迹收据为准。未运行时不生成虚假的 Agent 修订图。',
        '先导只用于检查 Agent 能否正确利用失败和越界反馈；在没有合理自供能正例前，不开展大规模方法胜率比较。',
        '结构自由度由能量传递、初始平衡和释放过程的证据决定。先检查现有机械加载/释放模型是否适合该问题，再决定增加真实结构或扩大非线性模型范围。', '',
        '## 如何复核', '',
        '解压轻量包后运行 `python3 check_evidence.py`，核对所有文件、模型源码快照及每条收据。',
        '这项检查不重新启动 COMSOL/LTspice；原生档案的位置与哈希在 large-native-artifacts.json。完整复算仍需要记录的软件和依赖。', '']
    (out/'REPORT.md').write_text('\n'.join(lines))
    checker = '''
        import hashlib, json
        from pathlib import Path
        root = Path(__file__).resolve().parent
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        manifest = json.loads((root/'manifest.json').read_text())
        for name, expected in manifest.items():
            p = (root/name).resolve()
            assert p.is_relative_to(root) and p.is_file(), name
            assert sha(p) == expected, 'manifest: '+name
        seal = json.loads((root/'seal.json').read_text())
        for name, expected in seal['sources'].items():
            assert sha(root/'source-snapshot'/name) == expected, 'source: '+name
        checked = 0
        for p in (root/'records').glob('*/receipt.json'):
            receipt = json.loads(p.read_text())
            if receipt.get('result_sha256'):
                result_path = p.parent/'result.json'
                assert sha(result_path) == receipt['result_sha256'], 'result: '+str(p.parent)
                result = json.loads(result_path.read_text())
                for artifact in result.get('artifacts', []):
                    small = p.parent/artifact['name']
                    if small.exists(): assert sha(small) == artifact['sha256'], str(small)
            checked += 1
        print(json.dumps({'status':'passed','manifest_files':len(manifest),'native_attempts':checked,
                          'scope':'byte integrity and preserved receipts; does not rerun native solvers'}))
        '''
    (out/'check_evidence.py').write_text(textwrap.dedent(checker).lstrip())


def timeline(run, target):
    a = np.genfromtxt(run/'waveform.csv', delimiter=',', names=True)
    p = np.genfromtxt(run/'program.csv', delimiter=',', names=True)
    receiver = json.loads((run/'receiver.json').read_text())
    fig, axes = plt.subplots(5, 1, figsize=(11, 10), sharex=True, layout='constrained')
    axes[0].plot(a['time_s'], a['tip_m']*1000); axes[0].set_ylabel('Beam tip / mm')
    axes[1].plot(a['time_s'], a['piezo_V'], label='Piezo port')
    axes[1].plot(a['time_s'], a['storage_V'], label='Input storage'); axes[1].set_ylabel('Voltage / V')
    axes[1].legend()
    axes[2].plot(a['time_s'], a['supply_V'], label='MCU supply')
    axes[2].plot(a['time_s'], a['pgood_V'], label='PGOOD'); axes[2].set_ylabel('Voltage / V'); axes[2].legend()
    axes[3].step(p['time_s'], p['state'], where='post')
    axes[3].set_yticks(range(6), ['RESET', 'BOOT', 'WAIT', 'INIT', 'TX', 'SLEEP'])
    axes[3].set_ylim(-.3, 5.3)
    for level, name in enumerate(['transmitted', 'delivered']):
        times = [e['time_s'] for e in receiver.get(name, [])]
        axes[4].scatter(times, [level]*len(times), marker='|', s=100)
        if not times: axes[4].text(.03, .25+level*.5, name+': 0', transform=axes[4].transAxes)
    axes[4].set_yticks([0, 1], ['Complete TX', 'Virtual received']); axes[4].set_ylim(-.5, 1.5)
    axes[4].set_xlabel('Aligned simulation time / s')
    for ax in axes: ax.grid(alpha=.15)
    fig.suptitle(run.name+' — same candidate, coupled model / shared C SIL\nNominal prediction; no hardware or full-trajectory magnetic qualification', fontsize=12)
    fig.savefig(target, dpi=160); plt.close(fig)


def trajectory_check(run, receipt):
    """Additional observation only; does not update model or acceptance gates."""
    from scipy.interpolate import RegularGridInterpolator
    from bfworld.agentlab.simulation_chain.native import coordinates, force
    result = json.loads((run/'result.json').read_text())
    spec = json.loads((run/'design-spec.json').read_text())
    table = np.load(Path(receipt['cache'])/'force'/result['stages']['force']['key']/'force-table.npz')
    interp = RegularGridInterpolator((table['angles'], table['qs']), table['values'], bounds_error=True)
    a = np.genfromtxt(run/'waveform.csv', delimiter=',', names=True)
    angles = np.minimum(a['time_s']/spec['mechanical']['opening_s'], 1)*np.deg2rad(spec['mechanical']['angle_deg'])
    tab = interp(np.column_stack([angles, a['tip_m']]))
    indices = np.unique(np.r_[np.arange(0, len(a), 80), len(a)-1])
    points = []
    for i in indices:
        dx, dz = coordinates(angles[i], spec['mechanical']['gap_mm'])
        f6, f10, f14 = [force(dx, dz-a['tip_m'][i], angles[i], spec['mechanical']['remanence_T'], n)[2] for n in (6, 10, 14)]
        points.append({'time_s': float(a['time_s'][i]), 'angle_deg': float(np.rad2deg(angles[i])),
                       'tip_m': float(a['tip_m'][i]), 'table_N': float(tab[i]),
                       'quadrature6_N': float(f6), 'quadrature10_N': float(f10), 'quadrature14_N': float(f14)})
    scale = max(max(abs(p['quadrature14_N']) for p in points), 1e-12)
    power = abs(tab*a['velocity_m_s']); dt = np.diff(a['time_s'])
    work = .5*(power[:-1]+power[1:])*dt
    early = angles[1:] <= np.deg2rad(15)
    return {'scope': 'sampled full-trajectory quadrature/interpolation diagnostic; same analytical force assumptions, not independent FEM',
            'points': points, 'sampled_max_table_error_over_peak': max(abs(p['table_N']-p['quadrature14_N']) for p in points)/scale,
            'sampled_max_quadrature10_14_delta_over_peak': max(abs(p['quadrature10_N']-p['quadrature14_N']) for p in points)/scale,
            'absolute_magnetic_work_from_resampled_waveform_J': float(work.sum()),
            'fraction_absolute_magnetic_work_at_0_to_15_deg': float(work[early].sum()/work.sum()) if work.sum() else None,
            'initial_elastic_energy_is_separate': True, 'changes_acceptance_gates': False}


def report(root):
    manifest = prepare(root)
    out = root/'report'; out.mkdir(exist_ok=True)
    lightweight = out/'records'; lightweight.mkdir(exist_ok=True)
    rows = []; outcomes = []; large = []
    for receipt_path in sorted((root/'runs').glob('*/receipt.json')):
        run = receipt_path.parent; receipt = json.loads(receipt_path.read_text())
        result = verify_run(run) if (run/'result.json').exists() else {}
        spec = json.loads((run/'design-spec.json').read_text()) if (run/'design-spec.json').exists() else manifest['task']['task']['baseline']
        receiver = json.loads((run/'receiver.json').read_text()) if (run/'receiver.json').exists() else {}
        evaluation = evaluate(manifest['task'], spec, result or {'run_status':receipt['run_status']}, receiver)
        if result and evaluation != result.get('task_evaluation'): raise ValueError('INDEPENDENT_EVALUATION_DIFF:'+run.name)
        metrics = result.get('metrics', {})
        row = {'id':run.name, 'gap_mm':spec['mechanical']['gap_mm'], 'cin_uF':spec['circuit']['cin_uF'],
               'cout_uF':spec['circuit']['cout_uF'], 'interval_ms':spec['firmware']['interval_ms'],
               'run_status':receipt['run_status'], 'nominal_task':evaluation['nominal_task_status'],
               'physical_ranking':evaluation['design_ranking_eligible'], 'peak_storage_V':metrics.get('peak_storage_V'),
               'peak_supply_V':metrics.get('peak_supply_V'), 'complete_tx':metrics.get('tx_completed'),
               'timely_correct_packets':evaluation['timely_correct_packets'],
               'end_to_end_s':receipt['end_to_end_s'], 'solver_reported_s':receipt['solver_reported_s'],
               'executed_stages':receipt['executed_stages'], 'logical_stages':receipt['logical_stages'],
               'cold_control':receipt['cold_control'], 'model_calls':0, 'human_next_candidate':True}
        row['repeat_of'] = run.name.split('-runtime-recovery')[0] if '-runtime-recovery' in run.name else None
        rows.append(row); outcomes.append({'receipt':receipt, 'evaluation':evaluation})
        target = lightweight/run.name; target.mkdir(exist_ok=True)
        for name in ['candidate.json','design-spec.json','result.json','receipt.json','trace.jsonl','task-evaluation.json',
                     'coupling-iterations.json','energy.json','convergence.json','magnetic-confirmation.json','receiver.json',
                     'waveform.csv','program.csv','program.c','policy.h','system.cir','runner.log']:
            if (run/name).exists(): shutil.copy2(run/name, target/name)
        for artifact in result.get('artifacts', []):
            if artifact['name'] in ('engineering-evidence.zip','assembly.step'):
                large.append({'run':run.name, **artifact, 'local_path':str(run/artifact['name'])})
        if result.get('run_status') == 'completed' and not receipt['cold_control']:
            diag = out/(run.name+'-trajectory-check.json')
            if not diag.exists(): write_json(diag, trajectory_check(run, receipt))
    if rows:
        with (out/'runs.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        main=[r for r in rows if not r['cold_control']]
        fig, ax=plt.subplots(figsize=(11,5.8),layout='constrained')
        colors={'completed':'#3974c2','out_of_domain':'#9062ac','numerical_fail':'#d5743c','tool_fail':'#7a8088'}
        for i,r in enumerate(main):
            x=r['peak_storage_V'] if r['peak_storage_V'] is not None else 0
            ax.barh(i,x,color=colors.get(r['run_status'],'#bbb'))
            if r['peak_storage_V'] is None:
                ax.plot(0,i,'o',color=colors.get(r['run_status'],'#bbb'),clip_on=False)
            ax.text(x+.008,i,r['nominal_task']+' / '+r['run_status'],va='center',fontsize=8)
        ax.set_yticks(range(len(main)),[r['id'] for r in main]);ax.invert_yaxis()
        ax.set_xlabel('Peak input-storage voltage / V (diagnostic measure, not the objective)')
        ax.set_xlim(0,max([r['peak_storage_V'] or 0 for r in main]+[.1])*1.7)
        ax.set_title('Declared candidate space: each label is one actual run\nFailure to evaluate is distinct from nominal task failure; all physical ranking flags remain explicit')
        fig.savefig(out/'candidate-space.png',dpi=160);plt.close(fig)
        if (root/'runs/nominal/waveform.csv').exists(): timeline(root/'runs/nominal',out/'aligned-timeline.png')
    repeats=[r for r in rows if r['cold_control']]
    nominal=next((r for r in rows if r['id']=='nominal'),None)
    cold={'completed_controls':len(repeats),'independent_empty_caches':True,'comparisons':[]}
    for r in repeats:
        cold['comparisons'].append({'id':r['id'],'status':r['run_status'],
            'max_scalar_relative_difference':max(abs((r[k] or 0)-(nominal[k] or 0))/max(abs(nominal[k] or 0),1e-12)
               for k in ['peak_storage_V','peak_supply_V','complete_tx']) if nominal and r['run_status']=='completed' else None})
        if nominal and r['run_status']=='completed':
            a=np.genfromtxt(root/'runs/nominal/waveform.csv',delimiter=',',names=True)
            b=np.genfromtxt(root/'runs'/r['id']/'waveform.csv',delimiter=',',names=True)
            if not np.array_equal(a['time_s'],b['time_s']):raise ValueError('COLD_REPEAT_TIME_GRID_CHANGED')
            cold['comparisons'][-1]['waveform_relative_max']={k:float(np.max(abs(a[k]-b[k]))/max(np.max(abs(a[k])),1e-12)) for k in a.dtype.names if k!='time_s'}
            cold['comparisons'][-1]['program_csv_identical']=file_hash(root/'runs/nominal/program.csv')==file_hash(root/'runs'/r['id']/'program.csv')
            pa=np.genfromtxt(root/'runs/nominal/program.csv',delimiter=',',names=True)
            pb=np.genfromtxt(root/'runs'/r['id']/'program.csv',delimiter=',',names=True)
            cold['comparisons'][-1]['program_time_state_current_identical']=all(np.array_equal(pa[k],pb[k]) for k in ['time_s','state','current_A'])
            cold['comparisons'][-1]['receiver_json_identical']=file_hash(root/'runs/nominal/receiver.json')==file_hash(root/'runs'/r['id']/'receiver.json')
    write_json(out/'cold-repeat.json',cold)
    write_json(out/'large-native-artifacts.json',large)
    write_json(out/'independent-evaluations.json',outcomes)
    recovery = {r['repeat_of']: r for r in rows if r['repeat_of']}
    effective = [recovery.get(r['id'], r) for r in rows if not r['repeat_of'] and not r['cold_control']]
    write_json(out/'summary.json',{'runs':len(rows),'mapping':sum(not r['cold_control'] and not r['repeat_of'] for r in rows),
        'runtime_recoveries':sum(bool(r['repeat_of']) for r in rows),
        'cold_controls':len(repeats),'statuses':{s:sum(r['run_status']==s for r in rows) for s in sorted({r['run_status'] for r in rows})},
        'unique_designs_after_explicit_runtime_recovery':{s:sum(r['run_status']==s for r in effective) for s in sorted({r['run_status'] for r in effective})},
        'self_powered_nominal_successes':sum(r['nominal_task']=='satisfied' for r in rows),
        'physically_rankable':sum(r['physical_ranking'] for r in rows),'native_end_to_end_s':sum(r['end_to_end_s'] for r in rows),
        'pi_status':'not run' if not list((root/'trials').glob('*/receipt.json')) else 'see trial receipts',
        'claim':'fixed nominal model development pilot; finite unsatisfied samples do not prove an infeasible design space'})
    for name in ['seal.json','protocol.json','task.json']: shutil.copy2(root/name,out/name)
    shutil.copytree(root/'source-snapshot',out/'source-snapshot',dirs_exist_ok=True)
    environment=out/'environment';environment.mkdir(exist_ok=True)
    for p in [root/name for name in ['local-storage-migration.json','environment-intervention.json',
              'runtime-overlay.json','cmsis-runtime-receipt.json','validation-targeted.json',
              'validation-full.json','application-init-final.log','paid-status.json',
              'agent-runtime-seal.json']]+list(root.glob('*-runtime-recovery1.json')):
        if p.exists():shutil.copy2(p,environment/p.name)
    evidence_notes(root,out,rows,cold)
    files={str(p.relative_to(out)):file_hash(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'}
    write_json(out/'manifest.json',files)
    archive=root/'lightweight-evidence.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file(): z.write(p,str(p.relative_to(out)))
    with zipfile.ZipFile(archive) as z:
        if z.testzip(): raise ValueError('EXPORT_ZIP_INTEGRITY')
        if set(z.namelist())!=set(files)|{'manifest.json'}:raise ValueError('EXPORT_FILE_SET_MISMATCH')
        for name,sha in files.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=sha:raise ValueError('EXPORT_HASH_MISMATCH:'+name)
    print(json.dumps({'summary':json.loads((out/'summary.json').read_text()),'package':str(archive),'bytes':archive.stat().st_size},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=DEFAULT_ROOT);a=p.parse_args();report(a.root)
