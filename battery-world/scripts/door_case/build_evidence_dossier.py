"""Build a source-bound six-figure door case dossier. Never runs a solver.

Input snapshots remain immutable. Regenerate from the portable inputs directory;
missing/corrupt inputs fail closed instead of producing substitute measurements.
"""
import argparse
import csv
import hashlib
import html
import json
import os
import shutil
import subprocess
from pathlib import Path

SCHEMA = 'bf-product-evidence-v1'
VERSION = 'E1'
TITLES = ['这是什么产品', '一次动作怎样产生能量', '为什么保留与修改这套设计', '能量到哪里去了', '电路和程序如何共同工作', '当前可以交付什么']

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def capture(case, review, dest):
    """Explicit source roots, no databases, secrets, sessions or vendor installs."""
    if (dest / 'source-index.json').exists():
        verify_inputs(dest)
        return
    paths = []
    for sub in ['mechanical-D2', 'animation-D2', 'electronics-D3', 'firmware-D2-final']:
        for f in sorted((case / sub).rglob('*')):
            if not f.is_file() or f.is_symlink() or 'frames' in f.parts or f.name.startswith('.') or f.suffix == '.zip' or f.name == 'publication.json': continue
            if sub=='firmware-D2-final' and str(f.relative_to(case/sub)) not in {'main.c','Makefile','ble_app_beacon_gcc_nrf52.ld','receipt.json','resources.json','reproducibility.json','size.txt','FLASH.md','_build/nrf52832_xxaa.hex','_build/nrf52832_xxaa.bin','config/sdk_config.h'}: continue
            paths.append(('engineering', case, f))
    for sub in ['frozen-baseline', 'orientation-v3']:
        for f in sorted((review / sub).rglob('*')):
            if f.is_file() and not f.is_symlink() and f.suffix in {'.json', '.csv', '.c', '.h', '.py', '.cir', '.pwl', '.sub', '.log', '.step'}:
                paths.append(('review', review, f))
    for sub in ['simulation/beam-v4', 'simulation/magnetic-D2-final']:
        for f in sorted((case / sub).glob('*')):
            if f.is_file() and f.suffix in {'.png', '.glb', '.json', '.java', '.txt', '.mph'}: paths.append(('engineering', case, f))
    records = []
    for category, base, src in paths:
        rel = Path(category) / src.relative_to(base); target = dest / rel
        print('Capture '+str(rel),flush=True)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, target)
        records.append(dict(path=rel.as_posix(), bytes=target.stat().st_size, sha256=sha(target)))
    write(dest / 'source-index.json', {'schema_version': 'bf-evidence-sources-v1', 'files': records,
          'boundary': 'Snapshot of existing engineering, not new solver execution. Large native RAW archives remain identified by original result receipts; no claim of full native rerun portability.'})

def verify_inputs(root):
    index = json.loads((root / 'source-index.json').read_text())
    for f in index['files']:
        rel = Path(f['path']); p = root / rel
        if rel.is_absolute() or '..' in rel.parts or p.is_symlink() or not p.resolve().is_relative_to(root.resolve()): raise ValueError('SOURCE_PATH_DENIED')
        if not p.is_file() or sha(p) != f['sha256']: raise ValueError('SOURCE_CHANGED: ' + f['path'])
    return index

def source_identity(records):
    return hashlib.sha256(json.dumps(sorted(records, key=lambda f: f['path']), sort_keys=True).encode()).hexdigest()

def dependencies_for(group, records):
    prefixes = {
        1: ['engineering/mechanical-D2/', 'engineering/animation-D2/'],
        2: ['review/orientation-v3/candidate.json', 'review/orientation-v3/joint/waveform.csv', 'review/frozen-baseline/design-spec.json'],
        3: ['review/frozen-baseline/design-spec.json', 'review/frozen-baseline/result.json', 'review/orientation-v3/native-result.json', 'review/orientation-v3/candidate.json'],
        4: ['review/frozen-baseline/energy.json', 'review/orientation-v3/joint/energy.json'],
        5: ['review/orientation-v3/joint/', 'review/orientation-v3/firmware/', 'engineering/electronics-D3/pcb/schematic', 'engineering/electronics-D3/pcb/pcb-combined', 'engineering/firmware-D2-final/receipt.json'],
        6: ['engineering/', 'review/']}
    return [r for r in records if any(r['path'].startswith(prefix) for prefix in prefixes[group])]

def generate(root, inputs):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font = Path(os.environ.get('BF_EVIDENCE_FONT','/System/Library/Fonts/Hiragino Sans GB.ttc'))
    if not font.exists(): raise RuntimeError('CJK_FONT_REQUIRED: configure a readable CJK font before rendering')
    font_manager.fontManager.addfont(str(font)); plt.rcParams['font.family'] = [font_manager.FontProperties(fname=str(font)).get_name(), 'DejaVu Sans']
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.titlelocation': 'left', 'axes.titleweight': 'bold', 'axes.labelcolor': '#343b42', 'text.color': '#20252a', 'axes.edgecolor': '#ced4da', 'axes.unicode_minus': False, 'svg.hashsalt': 'door-evidence-v1'})
    index = verify_inputs(inputs); records = index['files']
    load = lambda path: json.loads((inputs / path).read_text())
    design = load('engineering/mechanical-D2/design.json')
    b = load('review/frozen-baseline/result.json'); v = load('review/orientation-v3/native-result.json')
    be = load('review/frozen-baseline/energy.json'); ve = load('review/orientation-v3/joint/energy.json')
    spec = load('review/frozen-baseline/design-spec.json')
    w = np.genfromtxt(inputs / 'review/orientation-v3/joint/waveform.csv', names=True, delimiter=',')
    prog = np.genfromtxt(inputs / 'review/orientation-v3/joint/program.csv', names=True, delimiter=',')
    receiver = load('review/orientation-v3/joint/receiver.json')
    if len(receiver['transmitted']) != v['metrics']['tx_completed'] or len(receiver['events']) != v['metrics']['received_events']: raise ValueError('EVENT_COUNT_MISMATCH')
    if w['time_s'][0] != prog['time_s'][0] or abs(w['time_s'][-1]-prog['time_s'][-1]) > 1e-8: raise ValueError('TIMELINE_MISMATCH')
    if set(prog['state'].astype(int)) != set(v['metrics']['program_states_reached']): raise ValueError('PROGRAM_STATE_MISMATCH')
    figure_dir = root / 'report/figures'; figure_dir.mkdir(parents=True, exist_ok=True)
    def finish(fig, n, caption):
        fig.text(.05,.026,caption,fontsize=10,color='#535c65')
        fig.savefig(figure_dir / f'figure-{n}.png',dpi=170,facecolor='white')
        fig.savefig(figure_dir / f'figure-{n}.svg',facecolor='white',metadata={'Date': None})
        plt.close(fig)
    def photo(ax, path, title):
        ax.imshow(plt.imread(inputs / path)); ax.axis('off'); ax.set_title(title,pad=12)
    blue,orange='#38697e','#a46b36'
    # 1. The assembled object leads, then its dimensioned engineering context.
    fig=plt.figure(figsize=(13.2,9));gs=fig.add_gridspec(3,2,height_ratios=[2.4,1,.72],left=.055,right=.96,top=.93,bottom=.1,hspace=.35)
    photo(fig.add_subplot(gs[0,0]),'engineering/animation-D2/installation.png','a  安装位置 / 固定在门楣，驱动磁体随门运动')
    photo(fig.add_subplot(gs[0,1]),'engineering/animation-D2/mechanism.png','b  内部布置 / 铜梁 + 压电片 + 梁端磁体')
    ax=fig.add_subplot(gs[1,:]);ax.axis('off')
    dims=lambda values:' × '.join(f'{x:g}' for x in values)+' mm'
    d,beam,pzt,mag=design['door'],design['beam'],design['pzt'],design['magnets']
    ax.text(0,.7,f"门：{dims([d['width'],d['height'],d['thickness']])}      壳体：{dims(design['enclosure']['outer_mm'])}      PCB：{dims(design['board']['size_mm'])}",fontsize=14)
    ax.text(0,.3,f"梁：{dims([beam['length'],beam['width'],beam['thickness']])}（自由长 {beam['free_length']:g} mm）     PZT：{dims([pzt['length'],pzt['width'],pzt['thickness']])}",fontsize=13)
    ax.text(0,-.1,f"梁端磁体：{dims(mag['tip_mm'])}     驱动磁体：{dims(mag['driver_mm'])}     名义中心间距：{mag['nominal_center_separation_x_mm']:g} mm",fontsize=12)
    ax=fig.add_subplot(gs[2,:]);ax.axis('off')
    for i,t in enumerate(['门动作','磁力与梁响应','压电端口','储能与稳压','程序 → 无线事件']):
        x=i*.203;ax.text(x,.5,t,bbox=dict(boxstyle='round,pad=.6',fc='#f4f6f7',ec='#dbe0e4'),fontsize=12)
        if i<4:ax.text(x+.158,.5,'→',fontsize=18)
    finish(fig,1,'D2 原生 CAD / Blender 既有工程。尺寸是设计假设；电路 D3.3 尚未回装验证。流程末端是目标，不是已实现结果。')
    # 2. Real returned trajectory and prescribed angle, not fabricated FEM frames.
    fig=plt.figure(figsize=(13.2,9)); gs=fig.add_gridspec(4,4,height_ratios=[1.15,1,1,1],left=.09,right=.95,top=.93,bottom=.11,hspace=.52)
    for i,t in enumerate([0,.25,2,4]):
        ax=fig.add_subplot(gs[0,i]);a=np.deg2rad(min(t/spec['mechanical']['opening_s'],1)*spec['mechanical']['angle_deg'])
        ax.plot([-1.1,1.1],[0,0],color='#75808a',lw=3);ax.plot([0,np.cos(a)],[0,np.sin(a)],color=blue,lw=6);ax.scatter([np.cos(a)],[np.sin(a)],s=90,marker='s',color=orange)
        ax.set_xlim(-.2,1.2);ax.set_ylim(-.25,1.1);ax.set_aspect('equal');ax.axis('off');ax.set_title(f'{chr(97+i)}  t = {t:g} s',fontsize=12)
        q=np.interp(t,w['time_s'],w['tip_m'])*1000
        ax.text(0,-.25,f'门角 {np.rad2deg(a):.1f}° / 梁端 {q:.2f} mm',fontsize=10)
    for row,(key,factor,label) in enumerate([('tip_m',1e3,'梁端位移 (mm)'),('piezo_V',1,'压电端电压 (V)'),('storage_V',1,'储能电压 (V)')],1):
        ax=fig.add_subplot(gs[row,:]);ax.plot(w['time_s'],w[key]*factor,color=blue,lw=1.4);ax.set_ylabel(label);ax.grid(alpha=.16);ax.set_xlim(0,4)
        if row==3:ax.set_xlabel('共同时间轴 (s)')
    finish(fig,2,'180° 驱动磁体探索运行 orientation-v3。上排是规定转角的运动示意（非等比例 FEM）；下排是同一次原生联合求解。')
    # 3. Comparable metrics with unchanged task and explicit intervention authority.
    fig,axs=plt.subplots(1,3,figsize=(13.2,7.5));fig.subplots_adjust(left=.07,right=.97,top=.8,bottom=.28,wspace=.38)
    for ax,(k,label) in zip(axs,[('peak_tip_mm','梁端峰值 (mm)'),('peak_storage_V','储能峰值 (V)'),('tx_completed','完整发送包数')]):
        values=[b['metrics'][k],v['metrics'][k]];ax.bar(['基线','驱动磁体 180°'],values,color=[blue,orange],width=.52);ax.set_title(label);ax.grid(axis='y',alpha=.17);ax.set_axisbelow(True)
        for i,value in enumerate(values):ax.annotate(f'{value:.4g}',(i,value),xytext=(0,7),textcoords='offset points',ha='center',fontsize=15)
        ax.set_ylim(0,max(values)*1.3 if max(values)>0 else 1)
    fig.text(.06,.9,'同一门动作与电源配置，比较磁化方向修改',fontsize=21,weight='bold')
    fig.text(.06,.17,f"固定条件：{spec['mechanical']['gap_mm']:g} mm / 0–{spec['mechanical']['angle_deg']:g}°，{spec['mechanical']['opening_s']:g} s 开门 / {w['time_s'][-1]:g} s 观察 / 输入 {spec['circuit']['cin_uF']:g} μF、输出 {spec['circuit']['cout_uF']:g} μF / 零初始电储能",fontsize=12)
    fig.text(.06,.12,'修改由操作者提出并运行；保留为机制探索。两者均未启动，不能作为 Agent 优化成功或合格设计。',fontsize=12)
    finish(fig,3,'来源：两次原生运行的 result / native-result 与 candidate。小位移 ROM、磁场全轨迹确认仍有限制。')
    # 4. Signed accounts, not a misleading positive Sankey.
    fig,axs=plt.subplots(1,2,figsize=(13.2,8));fig.subplots_adjust(left=.24,right=.97,top=.84,bottom=.23,wspace=.62)
    ks=['initial_mechanical_piezo_J','external_force_work_J','mechanical_loss_J','pmic_port_energy_J','final_mechanical_piezo_J']
    labels=['初始机械/压电储能','磁力净功（带符号）','机械阻尼耗散','进入 PMIC 端口','末态机械/压电储能']
    for ax,energy,title in zip(axs,[be,ve],['基线','驱动磁体 180°']):
        values=[energy[k]*1e6 for k in ks];ax.barh(labels,values,color=[blue,orange,'#909ba2',blue,'#c1c9cd']);ax.axvline(0,color='#7f8990',lw=.7);ax.invert_yaxis();ax.set_xlabel('能量 / 功 (μJ)');ax.set_title(title,fontsize=17)
        ax.set_xlim(-850,1100)
        for i,value in enumerate(values):
            ax.text(value/2 if value<0 else value+20,i,f'{value:.2f}',va='center',ha='center' if value<0 else 'left',color='white' if value<0 else '#20252a',fontsize=11)
    fig.text(.06,.95,'初始储能 + 磁力净功 = 阻尼耗散 + PMIC 端口能量 + 末态能量 + 残差',fontsize=15)
    balance=lambda e:f"{e['initial_mechanical_piezo_J']*1e6:.2f} {e['external_force_work_J']*1e6:+.2f} ≈ {e['mechanical_loss_J']*1e6:.2f} + {e['pmic_port_energy_J']*1e6:.2f} μJ"
    fig.text(.06,.14,balance(be)+'       |       '+balance(ve),fontsize=14)
    fig.text(.06,.085,'负磁力净功表示能量从梁—压电子系统流出；它不是 PMIC 损耗。完整门加载功尚未闭合。',fontsize=12)
    finish(fig,4,'机械/压电能量账本。PMIC 内部损耗未独立观测；禁止由此推算整机效率或把预加载储能当作本次门输入。')
    # 5. One run only, all six channels share time, including genuine zero events.
    fig,axs=plt.subplots(6,1,figsize=(13.2,10),sharex=True);fig.subplots_adjust(left=.15,right=.96,top=.93,bottom=.1,hspace=.28)
    for ax,key,scale,label in zip(axs[:3],['storage_V','supply_V','pgood_V'],[1,1e6,1e6],['储能 (V)','MCU 供电 (μV)','PGOOD (μV)']):
        ax.plot(w['time_s'],w[key]*scale,color=blue,lw=1.3);ax.set_ylabel(label);ax.grid(alpha=.18)
    axs[3].step(prog['time_s'],prog['state'],where='post',color=blue);axs[3].set_yticks(range(6),['RESET','BOOT','WAIT','INIT','TX','SLEEP'],fontsize=9);axs[3].set_ylabel('程序状态');axs[3].set_ylim(-.5,5.5)
    for ax,events,label in [(axs[4],receiver['transmitted'],'完整 TX'),(axs[5],receiver['events'],'接收事件')]:
        ax.set_ylim(-.1,1.2);ax.set_yticks([0,1]);ax.set_ylabel(label);ax.text(.08,.55,f'{len(events)} 个事件 / 未发生',fontsize=12);ax.axhline(0,color=blue,lw=1.2)
    axs[0].set_title('供电没有建立，程序持续 RESET；没有发射，也没有接收',fontsize=19,pad=14)
    axs[-1].set_xlim(0,4);axs[-1].set_xlabel('共同时间轴 (s)')
    finish(fig,5,'orientation-v3：共享 C 软件在环 + 虚拟接收；不是 nRF52832 / SoftDevice 周期仿真。实际 HEX 属于独立 D2 目标工程。')
    # 6. Engineering overview and honest release gates.
    fig=plt.figure(figsize=(13.2,9));gs=fig.add_gridspec(2,2,height_ratios=[1.3,1],left=.05,right=.96,top=.94,bottom=.11,hspace=.2)
    photo(fig.add_subplot(gs[0,0]),'engineering/electronics-D3/pcb/schematic.png','a  原理图 / D3.3 电路采购修订')
    photo(fig.add_subplot(gs[0,1]),'engineering/electronics-D3/pcb/pcb-combined.png','b  双面 PCB / 实际布线，非制造放行')
    ax=fig.add_subplot(gs[1,:]);ax.axis('off')
    rows=[['机械','D2 CAD / Blender / 图纸','可读取','电路修订回装待验'],['电路 / PCB','D3.3 EDA / 铜线 / Gerber','独立二维检查通过','原生 ERC / DRC 待验'],['固件','D2 C / HEX / BIN / 编译收据','已编译','未烧录，能耗未实测'],['联合仿真','基线 / 180° / CSV / C 状态','真实运行已保留','未冷启动 / 0 TX / 0 RX'],['BOM','14 装配件 / 11 嘉立创料号','2026-10-03 库存快照','当前库存与贴片资格待核实']]
    tab=ax.table(cellText=rows,colLabels=['部分','交付内容','已知事实','仍缺少'],loc='center',cellLoc='left',colWidths=[.12,.36,.22,.30]);tab.auto_set_font_size(False);tab.set_fontsize(11);tab.scale(1,2.05)
    for (i,j),cell in tab.get_celld().items():cell.set_edgecolor('#dde2e5');cell.set_facecolor('#eff2f3' if i==0 else '#ffffff')
    finish(fig,6,'可打开、可检查与可制造是不同条件。此档案交付已有证据，不宣称整机成功、实物测试或 80% 自主复现。')
    summaries=[
      ('D2 安装与尺寸定义已存在；磁驱动随门转动，梁与电子组件固定在门楣。','确认使用场景、安装关系与器件尺寸。',['原生几何/既有渲染','尺寸属于设计假设，未实测','D3.3 电子修订与 D2 壳体的集成配合待验']),
      ('给定门角运动改变磁力，梁—压电响应产生端口输出；这还不是经验证的完整加载/释放机构。','把规定运动与实际计算响应放在同一条时间轴。',['上排运动示意，不是 FEM 云图','下排为 orientation-v3 原生联合计算','完整闭门加载功与旋转磁场覆盖待确认']),
      ('翻转驱动磁体后端口能量上升，但依然没有冷启动。当前保留为探索候选。','比较真正执行的修改，并保留失败结果。',['相同门动作、电容与观察时间','初始机械平衡随磁化方向改变','操作者实验，不是 Pi 自主架构成功']),
      ('基线的大量初始机械能以负磁力净功流出；翻转后阻尼耗散主导。不能只以最高电压优化。','解释能量变化，并明确哪些账目尚未观测。',['所有值读取已有 energy.json','能量残差仅对应机械/压电端口','PMIC 内部损耗与完整门输入功未知']),
      ('供电轨迹、PGOOD、C 状态与接收记录属于同一次运行：程序始终 RESET，TX/RX 均为零。','让电路、程序和应用结果在共同时间轴上对应。',['共享 C 逻辑及假设负载','不代表实际 nRF52 二进制能耗','D3.3 原理图是相关电子修订，不是此运行的新电路']),
      ('工程文件已经存在；整机启动、原生 EDA 检查、装配配合及实物验收仍未完成。','给出可带走的内容、各自版本和下一步验收。',['D2 机械与目标固件 / D3.3 电路 / 联合运行独立标识','库存是已保存快照，不是实时供应保证','未制造放行，无实物或自主复现成功声明'])]
    groups=[]
    for n,(conclusion,question,limits) in enumerate(summaries,1):
        deps=dependencies_for(n,records)
        group=dict(order=n,title=TITLES[n-1],question=question,conclusion=conclusion,limitations=limits,figure=f'report/figures/figure-{n}.png',vector=f'report/figures/figure-{n}.svg',source_identity=source_identity(deps),dependencies=[r['path'] for r in deps])
        write(root/f'report/figure-{n}-provenance.json',group);groups.append(group)
    baseline=dict(schema_version=SCHEMA,id='door-evidence',version=VERSION,title='门动作磁耦合压电节点',
        conclusion='尚未实现单次开门自供能启动；证据已整理，完整产品仍待验证。',
        product_accepted=False,hardware_verified=False,autonomous_agent_verified=False,
        source_identity=source_identity(records),components=[
          dict(id='mechanical',revision='D2',role='安装与原生几何'),dict(id='electronics',revision='D3.3-electronics',role='采购与布线草案；尚未与 D2 机械和 SIL 重新集成'),
          dict(id='joint-baseline',revision=b['physics_hash'],role='既有联合基线'),dict(id='orientation',revision='orientation-v3',role='驱动磁体 180° 探索'),dict(id='firmware',revision='D2-final',role='已编译目标代码，尚未烧录')],
        metrics=dict(baseline=b['metrics'],orientation=v['metrics']),groups=groups,
        next_actions=['核算完整闭门加载与开门释放功；补旋转磁场锚点和模型有效域。','依据能量去向设计可制造的结构修改，重跑同一任务；保留失败候选。','确认电子修订封装、原生 ERC/DRC、机械贴合与固件接口，再形成统一集成版本。'])
    write(root/'report/baseline.json',baseline);write(root/'report/source-index.json',index)
    write(root/'report/run-comparison.json',dict(baseline=b,orientation=v,energy={'baseline':be,'orientation':ve}))
    # Portable numeric data behind the figures, not merely screenshots.
    for src in ['review/orientation-v3/joint/waveform.csv','review/orientation-v3/joint/program.csv','review/orientation-v3/joint/receiver.json','review/frozen-baseline/waveform.csv']:
        dst=root/'report/data'/Path(src).relative_to('review');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(inputs/src,dst)
    esc=html.escape
    pages=[]
    for g in groups:
        pages.append(f'<section id="figure-{g["order"]}"><small>图组 {g["order"]} / 6</small><h2>{esc(g["title"])}</h2><p>{esc(g["question"])}</p><img src="figures/figure-{g["order"]}.png" alt="{esc(g["question"])}"><h3>{esc(g["conclusion"])}</h3><ul>'+''.join(f'<li>{esc(x)}</li>' for x in g['limitations'])+f'</ul><details><summary>数据与生成依据</summary><p>源身份 {g["source_identity"]}</p><a href="figure-{g["order"]}-provenance.json">查看来源与依赖</a></details></section>')
    (root/'report/door-evidence-report.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>门磁产品证据档案 E1</title><style>body{font:17px/1.7 -apple-system,BlinkMacSystemFont,sans-serif;color:#20252a;max-width:1100px;margin:auto;padding:40px 24px;background:#fff}h1{font-size:38px}h2{font-size:28px}small{color:#56616a}img{width:100%;height:auto}section{padding:45px 0;border-top:1px solid #ddd}nav{display:flex;gap:18px;flex-wrap:wrap;margin:30px 0}a{color:#38697e}code{overflow-wrap:anywhere}@media print{section{break-before:page}nav{display:none}}</style><h1>门动作磁耦合压电节点</h1><p>产品证据档案 E1 / 2026-10-05</p><h2>'+esc(baseline['conclusion'])+'</h2><p>机械、电子和联合求解各自保留来源版本。本档案用于工程评审，不是已集成产品的合格证书。</p><nav>'+''.join(f'<a href="#figure-{i}">图组 {i}</a>' for i in range(1,7))+'</nav>'+''.join(pages)+'<h2>下一步</h2><ol>'+''.join('<li>'+esc(t)+'</li>' for t in baseline['next_actions'])+'</ol><p>源身份：<code>'+baseline['source_identity']+'</code></p><a href="baseline.json">完整结构化档案</a></html>')
    return baseline

def publish(root, state, owner, baseline):
    from types import SimpleNamespace
    from bfworld.agentlab.store import Store
    from bfworld.agentlab.product_results import ProductResults
    def file(p):return dict(path=str(p.relative_to(root)),name=str(p.relative_to(root)).replace('/','--'),sha256=sha(p))
    groups=[]
    for g in baseline['groups']:
        links=[root/g['figure'],root/g['vector'],root/f'report/figure-{g["order"]}-provenance.json']
        groups.append(dict(id=f'figure-{g["order"]}',title=f'图组 {g["order"]} · '+g['title'],kind='evidence-figure',domain='system',scope=g['conclusion'],files=[file(p) for p in links],evidence_story={**g,'baseline_id':baseline['id'],'baseline_version':baseline['version'],'baseline_source_identity':baseline['source_identity'],'baseline_conclusion':baseline['conclusion'],'component_summary':'机械 D2、电子 D3.3 和联合运行分别绑定；尚未证明它们已经重新集成为合格整机。'},design_status='insufficient_evidence'))
    for domain,folders in [('mechanical',['engineering/mechanical-D2','engineering/animation-D2','engineering/simulation']),('circuit',['engineering/electronics-D3']),('firmware',['engineering/firmware-D2-final']),('system',['review'])]:
        files=[file(p) for folder in folders for p in sorted((root/'inputs'/folder).rglob('*')) if p.is_file()]
        groups.append(dict(id=domain+'-sources',kind='engineering-source',domain=domain,title={'mechanical':'D2 机械、图纸与展示','circuit':'D3.3 原理图、PCB 与采购','firmware':'D2 目标固件','system':'基线与 180° 联合运行原始记录'}[domain],scope='独立来源快照；工程可读不等于重新集成或制造放行。',files=files))
    # Report assets remain within one directory for the existing dependency closure.
    used={f['path'] for g in groups for f in g['files']}
    report_files=[file(p) for p in sorted((root/'report').rglob('*')) if p.is_file() and str(p.relative_to(root)) not in used]
    report_files += [file(p) for p in sorted((root/'reproduce').glob('*')) if p.is_file()]
    report_files += [file(root/'inputs/source-index.json'),file(root/'seal.json')]
    groups.append(dict(id='report',kind='engineering-report',domain='system',title='E1 完整图组报告与再生成程序',scope=baseline['conclusion'],files=report_files,design_status='insufficient_evidence'))
    m=dict(schema_version='bf-engineering-case-v1',id=baseline['id'],version=baseline['version'],title='门磁产品证据档案',authority='operator-assisted',hardware_verified=False,autonomous_agent_verified=False,design_sha256=baseline['source_identity'],groups=groups)
    write(root/'publication-manifest.json',m)
    catalog=ProductResults(SimpleNamespace(store=Store(state)));catalog.cases.publish(owner,root,m)
    _,files,_=catalog.cases.collect(owner);own=[f for f in files if f['case_id']==baseline['id'] and f['case_version']==baseline['version']]
    if not all(f['integrity'] for f in own):raise ValueError('PUBLISH_READBACK_FAILED')
    return dict(owner=owner,files=len(own),groups=6,integrity=True,source_identity=baseline['source_identity'])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--case-root',type=Path);parser.add_argument('--review-root',type=Path);parser.add_argument('--inputs',type=Path)
    parser.add_argument('--report-python',type=Path,required=True);parser.add_argument('--state',type=Path);parser.add_argument('--owner');a=parser.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);inputs=a.inputs or a.output/'inputs'
    if a.inputs is None: capture(a.case_root,a.review_root,inputs)
    if inputs.resolve() != (a.output/'inputs').resolve():shutil.copytree(inputs,a.output/'inputs',dirs_exist_ok=True);inputs=a.output/'inputs'
    baseline=generate(a.output,inputs)
    rep=a.output/'reproduce';rep.mkdir(exist_ok=True)
    for n in ['build_evidence_dossier.py','evidence_report.py','verify_evidence_dossier.py']:shutil.copyfile(Path(__file__).with_name(n),rep/n)
    (rep/'README.md').write_text('使用 Python + numpy + matplotlib 再生成图组；PDF 使用 reportlab。需要可读的中文字体；macOS 默认 Hiragino Sans GB 和 Arial Unicode。其他系统请设置 BF_EVIDENCE_FONT 与 BF_EVIDENCE_PDF_FONT 到有许可的本机字体（PDF 需 TrueType），更换字体会改变图像哈希。\n\npython reproduce/build_evidence_dossier.py --inputs inputs --output /tmp/door-evidence-rebuild --report-python /path/to/python-with-reportlab\n\npython reproduce/verify_evidence_dossier.py /tmp/door-evidence-rebuild\n\n只重建已有证据的展示，不启动 COMSOL/LTspice，不宣称原生求解已重算。源文件变化会停止生成，需建立新输入快照与版本。\n')
    subprocess.run([str(a.report_python),str(Path(__file__).with_name('evidence_report.py')),str(a.output)],check=True)
    files=[dict(path=str(p.relative_to(a.output)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(a.output.rglob('*')) if p.is_file() and p.name not in {'seal.json','publication-manifest.json','publication-receipt.json'}]
    write(a.output/'seal.json',dict(schema_version=SCHEMA,source_identity=baseline['source_identity'],files=files))
    receipt=publish(a.output,a.state,a.owner,baseline) if a.state and a.owner else dict(source_identity=baseline['source_identity'],figure_groups=6)
    write(a.output/'publication-receipt.json',receipt);print(json.dumps(receipt))

if __name__=='__main__':main()
