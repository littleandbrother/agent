"""Source-bound D5 plots: actual native waveforms, program and checks only."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

from bfworld.agentlab.simulation_chain.contracts import file_hash, write_json

COLORS = ['#245A81', '#C57833', '#3B7C66', '#82658F', '#A34848']
STATES = ['RESET', 'BOOT', 'WAIT', 'INIT', 'TX', 'SLEEP']
PANEL_STORIES = {
    '1a': ('固定门动作', '本次成功对应怎样的运动输入？', '直接读取保存的门角度轨迹：关闭、停留、打开及静置；不代表任意一次开门。'),
    '1b': ('梁的适用范围', '梁响应是否仍在声明的降阶模型范围内？', '原生位移轨迹与正负8 mm模型边界同图比较；处于范围内不等于完成材料与疲劳验证。'),
    '1c': ('工程身份与尺寸', '这次计算究竟对应哪一个机械设计？', '安装间距、磁体尺寸、零初始电能与实体文件共同绑定本次设计；旧PCB包络未适配新增电路。'),
    '2a': ('门运动做功与磁能释放', '输入机械功在关闭与打开过程中如何变化？', '同一力模型的有符号驱动功和磁势能；返回规定运动端的机械功不是已经回收的电能。'),
    '2b': ('压电端响应', '机械释放之后压电端实际出现什么电压？', '原生机电互馈与非理想提取电路共同求解的压电电压，保留正负极性与瞬态峰值。'),
    '2c': ('能量传递的实际量级', '压电输出、线圈损耗与应用耗能分别有多大？', '比较原生波形积分所得能量；三项不是完整的损失分解，也不自动构成硬件效率。'),
    '3a': ('实际供电链路', '从压电端到MCU经过哪些环节？', '显示实际网表的功能组织，详细连接以system.cir为准；本图不是可制造的EDA原理图。'),
    '3b': ('冷启动与储备门控', '储能何时达到有效门控条件？', '输入储能、输出电压和有供电条件的控制信号共同判断启动，避免只用未上电控制器看到的VIN峰值。'),
    '3c': ('电路器件与参数', '哪些真实器件和模型参与了本次求解？', '列出提取器件、电感、电容、PMIC和有耗电监控器；行为模型与安装版模型的来源边界保留。'),
    '3d': ('逐支路二极管电流', '并联后每一个物理支路是否通过保守电流筛选？', '每个功率位置显示实际原生支路的最大峰值，与250 mA保守筛选线比较；并非将总电流事后平均。'),
    '3e': ('集电极与电感分别验收', '两个不同电流是否被错误地混用？', '分别读取集电极与电感端口，分别对照600 mA器件筛选和典型电感饱和门槛；未获得热脉冲SOA资格。'),
    '3f': ('三支路均流结构', '声明的并联修改有没有进入实际网表？', '每个功率位置为三只二极管及每支0.22 Ω电阻；共六组，另有两只检测二极管。真实PCB和器件公差尚未验收。'),
    '4a': ('联合时轴：机械', '机械释放与最终通知发生在什么时间？', '梁位移和首个完整发送及虚拟接收时刻对齐。'),
    '4b': ('联合时轴：压电', '压电瞬态与机械释放是否对应？', '保留同一次原生联合计算的压电端电压，不拼接不同候选波形。'),
    '4c': ('联合时轴：电源', '采集的电能何时真正到达应用？', '输入储能、稳压轨和门控后的MCU轨同时显示；欠压门槛属于当前应用行为模型。'),
    '4d': ('联合时轴：程序', '供电轨迹实际驱动了哪些程序状态？', '使用编译C程序的状态输出，包含复位、启动、初始化、发送和休眠。'),
    '4e': ('联合时轴：负载', '应用执行反过来怎样加载电源？', '冻结阶段电流形成负载，再进入原生电源求解；这是声明硬件抽象下的软件在环负载。'),
    '5a': ('应用执行期间的供电', '完整工作负载期间电压是否维持在欠压线以上？', '放大启动至发送窗口，与1.8 V行为模型欠压门槛比较；不代表任意MCU二进制的实测功耗。'),
    '5b': ('完整应用顺序', '通知是否经过完整BOOT、INIT和TX？', '显示实际编译C状态轨迹；状态名的出现不能单独替代完整TX事件检查。'),
    '5c': ('发送与虚拟接收', '真正完成的报文是否产生了应用接收事件？', '分别显示完整发送与虚拟接收；接收环境固定，本结果不是实物RF或跨重启恰好一次语义。'),
    '6a': ('负载波形收敛', '电路与程序迭代后的负载是否一致？', '保留每次迭代的整段负载最大差异，不能用最后一个时刻或TX计数替代。'),
    '6b': ('供电波形收敛', '负载相同后电源轨迹是否也已经稳定？', '整段供电最大差异同时满足1 mV门槛才结束；仅负载差异为零并不足以宣布收敛。'),
    '6c': ('可观察能量账本', '能量用在哪里，还有哪些损失没有分解？', '区分应用、监控、分压、电感直流损耗、最终储能与未分解部分；未分解量不能伪装成某个器件的实测损耗。'),
    '6d': ('独立验收与边界', '哪些检查通过，哪些资格仍未获得？', '显示本次模型、数值与器件筛选，并单列独立冷复算；硬件、制造和RF资格保持未获得。'),
}


def render(run, output, audit=None, switch_fixture=None):
    run, output = Path(run).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('FIGURE_OUTPUT_ALREADY_EXISTS')
    result = json.loads((run / 'result.json').read_text())
    if result['run_status'] != 'completed':
        raise ValueError('FIGURES_REQUIRE_COMPLETED_NATIVE_RESULT')
    output.mkdir(parents=True)
    design = json.loads((run / 'design-spec.json').read_text())
    wave = np.genfromtxt(run / 'waveform.csv', delimiter=',', names=True)
    prog = np.genfromtxt(run / 'program.csv', delimiter=',', names=True)
    drive = np.genfromtxt(run / 'drive-ledger.csv', delimiter=',', names=True)
    ledger = json.loads((run / 'energy.json').read_text())
    receiver = json.loads((run / 'receiver.json').read_text())
    metrics = result['metrics']
    t = wave['time_s']
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
                         'font.size': 9, 'axes.labelsize': 10, 'axes.titlesize': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none', 'pdf.fonttype': 42,
                         'savefig.facecolor': 'white', 'figure.facecolor': 'white'})
    artifacts = []
    panels = []
    external_sources = {}
    fixture = None
    if switch_fixture:
        fixture_path=Path(switch_fixture).resolve()
        fixture=json.loads((fixture_path/'result.json').read_text())
        if (fixture.get('passed') is not True or fixture.get('test_only') is not True
                or fixture.get('self_powered_product') is not False
                or fixture['revised']['part']!=design.get('gate_switch','BSS84')
                or fixture['model_sha256']!=design['parts']['load_switch_model']['sha256']):
            raise ValueError('FIGURE_SWITCH_FIXTURE_MISMATCH')
        target=output/'inputs'/'powered-switch-fixture'
        shutil.copytree(fixture_path,target)
        for p in target.rglob('*'):
            if p.is_file():external_sources['figures/'+str(p.relative_to(output))]=p
    atlas=PdfPages(output/'D5-figure-atlas.pdf')

    def save(fig, stem, dependencies):
        order=int(stem.split('-')[1])
        fig.tight_layout(pad=1.6)
        fig.canvas.draw()
        source_records=[{'id':f'source-{i+1}','path':str(external_sources.get(f,run/f)),
                         'sha256':file_hash(external_sources.get(f,run/f)),'published_path':f}
                        for i,f in enumerate(dependencies)]
        declared=[{k:v for k,v in s.items() if k!='published_path'} for s in source_records]
        source_identity=hashlib.sha256(json.dumps(declared,sort_keys=True).encode()).hexdigest()
        for ext in ('png', 'pdf', 'svg'):
            path = output / (stem + '.' + ext)
            fig.savefig(path, dpi=300, bbox_inches='tight')
            artifacts.append({'path': path.name, 'sha256': file_hash(path), 'bytes': path.stat().st_size})
        atlas.savefig(fig,bbox_inches='tight')
        # Each readable panel remains a vector view of the very same axes and
        # data, with explicit source binding. This is not a raster screenshot.
        for i,ax in enumerate(fig.axes):
            letter=chr(ord('a')+i);pid=str(order)+letter
            bounds=ax.get_tightbbox(fig.canvas.get_renderer()).transformed(fig.dpi_scale_trans.inverted()).expanded(1.035,1.07)
            title=ax.get_title(loc='left') or (pid+' Engineering identity')
            if title.startswith(letter+'  '):title=title[3:]
            story = PANEL_STORIES.get(pid)
            # The optional powered control uses different lower-row panels.
            if fixture and pid in ('3d', '3e', '3f'):
                story = (title, '这个有外部供电的控制实验能确认什么？',
                         '独立器件控制实验，不能计作本候选的自供能成功；模型来源和完整任务验收分别保存。')
                if pid == '3e':
                    story = (title, '器件放回零初始电能整机后表现如何？',
                             '本子图是整机联合求解期间的实际供电；与相邻的外供电器件控制实验分开判读。')
            title, question, caption = story or (title, '这个来源明确的子图能确认什么？', title)
            row={'id':pid,'label':letter,'title':title,'question':question,
                 'caption':caption,
                 'status':'available','reason':None,'evidence_kind':'native-simulation-or-explicit-engineering-description',
                 'source_identity':source_identity,'dependencies':dependencies,'source_records':source_records}
            for ext,key in (('png','figure'),('pdf','pdf'),('svg','svg')):
                path=output/(f'panel-{pid}.'+ext)
                fig.savefig(path,dpi=300,bbox_inches=bounds,pad_inches=.03)
                row[key]='figures/'+path.name
                artifacts.append({'path':path.name,'sha256':file_hash(path),'bytes':path.stat().st_size})
            path=output/f'panel-{pid}.provenance.json'
            row['provenance']='figures/'+path.name
            write_json(path,row)
            artifacts.append({'path':path.name,'sha256':file_hash(path),'bytes':path.stat().st_size})
            panels.append(row)
        plt.close(fig)
        write_json(output / (stem + '.provenance.json'), {
            'design_id': design['design_id'], 'run_result_sha256': file_hash(run / 'result.json'),
            'sources': declared,
            'claim_boundary': result['qualification']['reason'], 'renderer_sha256': file_hash(Path(__file__))})

    def label(ax, letter, title):
        ax.set_title(letter + '  ' + title, loc='left', weight='bold', pad=10)
        ax.grid(axis='y', alpha=.15)

    fig, axs = plt.subplots(1, 3, figsize=(11.5, 3.3))
    # Use the saved native drive; reconstructing a linear angle from timing
    # fields would silently replace the smooth motion used by the solver.
    angle = np.rad2deg(drive['angle_rad'])
    axs[0].plot(drive['time_s'], angle, color=COLORS[0]); axs[0].set(xlabel='Time (s)', ylabel='Door angle (degree)')
    label(axs[0], 'a', 'Fixed full door cycle')
    axs[1].plot(t, wave['tip_m'] * 1e3, color=COLORS[0])
    axs[1].axhline(8, color=COLORS[4], ls='--', lw=1); axs[1].axhline(-8, color=COLORS[4], ls='--', lw=1)
    axs[1].set(xlabel='Time (s)', ylabel='Tip deflection (mm)'); label(axs[1], 'b', 'Declared ROM domain')
    axs[2].axis('off')
    base = design['base_design']
    text = (f"Physical gap: {base['mechanical']['gap_mm']:g} mm\n"
            f"Driver offset: {base['mechanical']['closed_dz_mm']:g} mm\n"
            'Tip / driver magnets: 10 / 20 mm cubes\n'
            'Beam: fixed COMSOL-derived ROM\n'
            'Electrical initial energy: 0 J\n'
            'Mechanical STEP + force table\n'
            'Existing D4 PCB: stale for D5')
    axs[2].text(0, .98, 'c  Engineering identity', weight='bold', va='top')
    axs[2].text(0, .82, text, va='top', linespacing=1.8)
    save(fig, 'figure-1-design', ['design-spec.json', 'system-manifest.json', 'waveform.csv', 'drive-ledger.csv'])

    fig, axs = plt.subplots(1, 3, figsize=(11.5, 3.3))
    axs[0].plot(drive['time_s'], drive['actuator_work_J'] * 1e3,
                color=COLORS[0], label='Signed actuator work')
    axs[0].plot(drive['time_s'], drive['magnetic_potential_J'] * 1e3,
                color=COLORS[1], ls='--', label='Magnetic potential')
    axs[0].axhline(0, color='#777777', lw=.6)
    axs[0].set(xlabel='Time (s)', ylabel='Energy (mJ)')
    axs[0].legend(frameon=False, fontsize=7)
    label(axs[0], 'a', 'Door work and magnetic release')
    axs[1].plot(t, wave['piezo_V'], color=COLORS[1]); axs[1].set(xlabel='Time (s)', ylabel='Piezoelectric voltage (V)')
    label(axs[1], 'b', 'Nonlinear extraction response')
    numeric = {k: ledger[k] * 1e6 for k in ('piezo_port_J', 'extractor_coil_loss_J', 'application_J')}
    axs[2].bar(range(3), list(numeric.values()), color=[COLORS[0], COLORS[1], COLORS[2]], width=.65)
    axs[2].set_xticks(range(3), ['Piezo port', 'Coil DCR', 'Application']); axs[2].set(ylabel='Energy (µJ)')
    for i, value in enumerate(numeric.values()): axs[2].text(i, value, f'{value:.1f}', ha='center', va='bottom')
    label(axs[2], 'c', 'Observed energy quantities')
    save(fig, 'figure-2-mechanical', ['waveform.csv', 'energy.json', 'drive-ledger.json', 'drive-ledger.csv', 'rom.json'])

    bank=design['parts'].get('diode_bank')
    fig, axs = plt.subplots(2 if fixture or bank else 1, 3, figsize=(12.5, 7.8 if fixture or bank else 3.5))
    axs=np.asarray(axs).reshape(-1)
    axs[0].axis('off'); axs[0].set_title('a  Native power-path organization', loc='left', weight='bold')
    nodes = ['Piezoelectric port', 'Self-powered peak detector', 'Extraction switch + 470 µH',
             'Input storage', 'LTC3588-1 native model', 'Reserve gate → MCU']
    for i, name in enumerate(nodes):
        y = .91 - i * .16
        axs[0].text(.5, y, name, ha='center', va='center', bbox={'boxstyle': 'round,pad=.35', 'fc': 'white', 'ec': COLORS[0]})
        if i < 5: axs[0].annotate('', (.5, y - .115), (.5, y - .035), arrowprops={'arrowstyle': '->', 'color': COLORS[0]})
    axs[1].plot(t, wave['storage_V'], color=COLORS[0], label='VIN')
    axs[1].plot(t, wave['regulated_V'], color=COLORS[2], label='VOUT')
    if 'gate_control_V' in wave.dtype.names:
        axs[1].plot(t,wave['gate_control_V'],color=COLORS[3],ls='--',lw=.8,label='Powered control')
        threshold=design['parts'].get('gate_thresholds_V',{}).get('high_V')
        if threshold:axs[1].axhline(threshold,color='#666666',ls=':',lw=.8,label='Enable threshold')
    axs[1].set(xlabel='Time (s)', ylabel='Voltage (V)'); axs[1].legend(frameon=False)
    label(axs[1], 'b', 'Native cold-start trajectory')
    axs[2].axis('off'); label(axs[2], 'c', 'Actual declared parts / settings')
    gate = design['gate']
    info = (f"Topology: {design['extraction']['topology']}\nCe: {design['extraction']['envelope_pF']:g} pF\n"
            f"Diodes: {design['extraction']['diodes']}\nCIN / COUT: {base['circuit']['cin_uF']:g} / {base['circuit']['cout_uF']:g} µF\n"
            'Coil: 7447471471, DCR 1.2 Ω\nQdet: MMBT5551; Qswitch: 2N5401\n'
            f"Monitor: {design['parts']['monitor'].split()[0]} behavioral, 1.5 µA\nGate: {gate}\nPMOS: {design.get('gate_switch','BSS84')} native model")
    axs[2].text(0, .92, info, va='top', linespacing=1.65)
    circuit_sources=['system.cir','design-spec.json','waveform.csv','rating-check.json']
    if (run/'gate-observation.json').exists():circuit_sources.append('gate-observation.json')
    if fixture:
        for row,color,style in ((fixture['legacy'],COLORS[4],'--'),(fixture['revised'],COLORS[0],'-')):
            samples=sorted(row['samples'],key=lambda x:x['source_V'])
            axs[3].plot([x['source_V'] for x in samples],[x['mcu_V'] for x in samples],
                        'o'+style,color=color,label=row['part'],markersize=4)
        axs[3].axhline(1.8,color='#666666',ls=':',lw=1)
        axs[3].set(xlabel='External source voltage (V)',ylabel='MCU terminal voltage (V)',ylim=(0,3.6))
        axs[3].legend(frameon=False);label(axs[3],'d','Independent powered switch control')
        start=prog['time_s'][prog['state']==1][0] if np.any(prog['state']==1) else 0.
        mask=(t>=start-.005)&(t<=start+.09)
        axs[4].plot(t[mask],wave['regulated_V'][mask],color=COLORS[1],label='Upstream VOUT')
        axs[4].plot(t[mask],wave['mcu_V'][mask],color=COLORS[0],ls='--',label='MCU')
        axs[4].axhline(1.8,color=COLORS[4],ls=':',lw=1)
        axs[4].set(xlabel='Time (s)',ylabel='Native rail voltage (V)');axs[4].legend(frameon=False)
        label(axs[4],'e','Coupled circuit during the full workload')
        axs[5].axis('off');label(axs[5],'f','Device evidence and boundary')
        resistance=fixture['manufacturer_test_point']['samples'][0]['effective_on_resistance_ohm']
        axs[5].text(0,.92,f"Original Si2333CDS vendor subcircuit\nVGS = −1.8 V, ID = 2 A test point\nModel RDS(on): {resistance*1000:.2f} mΩ\nDatasheet maximum: 59 mΩ\n\nPanel d uses external test power.\nIt is not a self-powered product result.\nPanel e is the zero-charge coupled run.\nTemperature / physical SOA: unqualified.",
                    va='top',linespacing=1.65)
        circuit_sources+=list(external_sources)
    elif bank:
        rating=json.loads((run/'rating-check.json').read_text())
        positions=bank['power_positions']
        peak=[max(v['forward_peak_A'] for k,v in rating['diodes'].items() if k.startswith(pos.lower()+'_')) for pos in positions]
        axs[3].bar(range(len(positions)),peak,color=COLORS[0],width=.6)
        axs[3].axhline(.25,color=COLORS[4],ls='--',lw=1,label='Conservative 250 mA screen')
        axs[3].set_xticks(range(len(positions)),positions,rotation=30,ha='right')
        axs[3].set(ylabel='Largest per-die peak (A)',ylim=(0,max(.3,max(peak)*1.2)))
        axs[3].legend(frameon=False,fontsize=7);label(axs[3],'d','Every physical branch is checked')
        limits=[rating['collector_limit_A'],rating['coil_peak_limit_A_typ']]
        peaks=[rating['collector_peak_A'],rating['coil_peak_A']]
        axs[4].bar([0,1],peaks,color=[COLORS[0],COLORS[1]],width=.5)
        for x,(limit,value) in enumerate(zip(limits,peaks)):
            axs[4].plot([x-.35,x+.35],[limit,limit],color=COLORS[4],ls='--')
            axs[4].text(x,value,f'{value:.3f} A',va='bottom',ha='center')
        axs[4].set_xticks([0,1],['QP collector','Coil peak'])
        axs[4].set(ylabel='Native current (A)',ylim=(0,max(limits+peaks)*1.25))
        label(axs[4],'e','Different quantities, different limits')
        axs[5].axis('off');label(axs[5],'f','Actual three-branch implementation')
        for y in (.75,.5,.25):
            axs[5].plot([.05,.97],[y,y],color=COLORS[0],zorder=1)
            axs[5].text(.36,y,'0.22 Ω',ha='center',va='center',bbox={'fc':'white','ec':COLORS[0],'boxstyle':'square,pad=.3'})
            axs[5].text(.75,y,'BAT46WJ',ha='center',va='center',bbox={'fc':'white','ec':COLORS[0],'boxstyle':'square,pad=.3'})
        axs[5].plot([.05,.05],[.25,.75],color=COLORS[0]);axs[5].plot([.97,.97],[.25,.75],color=COLORS[0])
        axs[5].text(.5,.02,'One bank shown; 6 power banks + 2 detector diodes.\nNominal matching only; physical PCB / thermal limits unqualified.',ha='center',va='top',fontsize=7)
        axs[5].set(xlim=(-.03,1.03),ylim=(-.18,1.))
    save(fig, 'figure-3-circuit', circuit_sources)

    fig, axs = plt.subplots(5, 1, figsize=(10.5, 8), sharex=True)
    axs[0].plot(t, wave['tip_m'] * 1e3, color=COLORS[0]); axs[0].set_ylabel('Tip (mm)')
    axs[1].plot(t, wave['piezo_V'], color=COLORS[1]); axs[1].set_ylabel('Piezo (V)')
    for n, name in enumerate(('storage_V', 'regulated_V', 'mcu_V')): axs[2].plot(t, wave[name], color=COLORS[n], label=name.removesuffix('_V'))
    axs[2].axhline(1.8, color=COLORS[4], lw=.8, ls='--'); axs[2].set_ylabel('Supply (V)'); axs[2].legend(frameon=False, ncol=3, loc='upper right')
    axs[3].step(prog['time_s'], prog['state'], where='post', color=COLORS[0]); axs[3].set_yticks(range(6), STATES); axs[3].set_ylabel('C program')
    axs[4].plot(prog['time_s'], prog['current_A'] * 1e3, color=COLORS[3], label='Application current')
    axs[4].set(xlabel='Time (s)', ylabel='Load (mA)')
    for ax, letter, title in zip(axs, 'abcde', ('Mechanical release', 'Piezoelectric terminal',
                                               'Storage, regulated rail and switched MCU rail',
                                               'Compiled application states', 'Actual application load')):
        label(ax, letter, title)
        for e in receiver['delivered']: ax.axvline(e['time_s'], color=COLORS[2], ls=':', lw=1)
    if receiver['delivered']:
        event_s=receiver['delivered'][0]['time_s']
        axs[0].annotate(f'First complete TX / virtual RX: {event_s:.4f} s',
                        xy=(event_s,0),xycoords=('data','axes fraction'),
                        xytext=(10,8),textcoords='offset points',color=COLORS[2],fontsize=8)
    fig.suptitle('Aligned native mechanics → power → compiled C → virtual receive', y=1.005, weight='bold')
    save(fig, 'figure-4-joint-timeline', ['waveform.csv', 'program.csv', 'receiver.json', 'result.json'])

    fig, axs = plt.subplots(1, 3, figsize=(11.5, 3.4))
    active = prog['time_s'][prog['state'] > 0]
    lo, hi = (max(0, active[0] - .01), min(6.5, active[0] + .12)) if len(active) else (2.5, 3.2)
    mask = (t >= lo) & (t <= hi)
    axs[0].plot(t[mask], wave['mcu_V'][mask], color=COLORS[0])
    axs[0].axhline(1.8, color=COLORS[4], ls='--', label='Modeled brownout: 1.8 V')
    axs[0].legend(frameon=False, fontsize=7, loc='lower right')
    axs[0].set(xlabel='Time (s)', ylabel='MCU supply (V)'); label(axs[0], 'a', 'Supply during application execution')
    mask = (prog['time_s'] >= lo) & (prog['time_s'] <= hi)
    axs[1].step(prog['time_s'][mask], prog['state'][mask], where='post', color=COLORS[0])
    axs[1].set_yticks(range(6), STATES); axs[1].set(xlabel='Time (s)', ylabel='Application state'); label(axs[1], 'b', 'Full application sequence')
    for e in receiver['transmitted']: axs[2].vlines(e['time_s'], .55, 1.0, color=COLORS[3], lw=2)
    for e in receiver['delivered']: axs[2].vlines(e['time_s'], 0, .45, color=COLORS[2], lw=2)
    axs[2].set(xlim=(0, 6.5), xlabel='Time (s)', ylim=(-.1, 1.1)); axs[2].set_yticks([.2, .8], ['Received', 'Complete TX'])
    label(axs[2], 'c', 'Virtual packet delivery')
    save(fig, 'figure-5-program', ['waveform.csv', 'program.csv', 'receiver.json', 'firmware/program.c', 'firmware/policy.h'])

    fig, axs = plt.subplots(2, 2, figsize=(11.5, 7.5))
    axs = axs.reshape(-1)
    iterations = json.loads((run / 'coupling-iterations.json').read_text())
    axs[0].plot([x['iteration'] for x in iterations], [x['max_current_difference_A'] * 1e3 for x in iterations], 'o-', color=COLORS[0])
    axs[0].set(xlabel='Coupling iteration', ylabel='Maximum load difference (mA)'); label(axs[0], 'a', 'Whole-waveform load convergence')
    axs[1].plot([x['iteration'] for x in iterations],
                [x['max_supply_difference_V'] if x['max_supply_difference_V'] is not None else np.nan
                 for x in iterations], 's--', color=COLORS[1])
    axs[1].axhline(.001, color=COLORS[4], ls=':', lw=1, label='1 mV stopping threshold')
    axs[1].set(xlabel='Coupling iteration', ylabel='Maximum supply difference (V)')
    axs[1].legend(frameon=False, fontsize=8)
    label(axs[1], 'b', 'Whole-waveform supply convergence')
    names = ['Application', 'Monitor IQ', 'Divider', 'Coil DCR', 'Final storage', 'Unresolved']
    values = [ledger[k] * 1e6 for k in ('application_J', 'monitor_IQ_J', 'divider_J', 'extractor_coil_loss_J', 'final_observable_storage_J', 'unresolved_electronics_J')]
    axs[2].barh(names, values, color=[COLORS[2], COLORS[3], COLORS[3], COLORS[1], COLORS[0], '#999999'])
    axs[2].invert_yaxis(); axs[2].set(xlabel='Energy (µJ)'); label(axs[2], 'c', 'Explicit lower-bound ledger')
    axs[3].axis('off'); label(axs[3], 'd', 'Acceptance boundary')
    check_labels = {'rom_domain': 'ROM domain', 'force_interpolation': 'Force interpolation',
                    'energy_balance': 'Mechanical / piezo energy balance',
                    'drive_balance': 'Actuator work balance',
                    'electrical_energy_lower_bound': 'Electrical energy lower bound',
                    'component_ratings': 'Component screens',
                    'program_power_fixed_point': 'Power / program fixed point',
                    'time_step': 'Half-step confirmation'}
    status = '\n'.join(f"{check_labels.get(k, k)}: {'PASS' if v is True else 'NOT PASSED'}" for k, v in result['checks'].items())
    audit_value=json.loads(Path(audit).read_text()) if audit else None
    if audit_value and not any(Path(r['path']).resolve()==run and r['result_sha256']==file_hash(run/'result.json')
                             for r in audit_value['runs']):
        raise ValueError('FIGURE_AUDIT_SOURCE_MISMATCH')
    repeat_text = 'Cold repeat: pending' if not audit_value else 'Cold repeat: ' + ('PASS' if audit_value['passed'] else 'NOT PASSED')
    axs[3].text(0, .96, status + '\n' + repeat_text + '\nHardware / PCB / RF: unqualified', va='top', linespacing=1.5, fontsize=8)
    acceptance_sources = ['coupling-iterations.json', 'energy.json', 'time-step-check.json', 'result.json']
    if audit:
        audit_copy = output / 'inputs' / 'independent-audit.json'
        audit_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(audit, audit_copy)
        audit_key = 'figures/inputs/independent-audit.json'
        external_sources[audit_key] = audit_copy
        acceptance_sources.append(audit_key)
    save(fig, 'figure-6-acceptance', acceptance_sources)
    if audit:
        write_json(output/'independent-audit.provenance.json',{'path':str(Path(audit).resolve()),'sha256':file_hash(Path(audit))})
    atlas.close()
    atlas_path=output/'D5-figure-atlas.pdf'
    # Include source receipts and copied controls, not only rendered images.
    # The publication check binds every exported byte to the figure index.
    artifacts = [{'path': str(p.relative_to(output)), 'sha256': file_hash(p), 'bytes': p.stat().st_size}
                 for p in sorted(output.rglob('*')) if p.is_file()]
    write_json(output / 'figure-index.json', {'design_id': design['design_id'], 'groups': 6,
        'subpanels': len(panels), 'panels':panels,'artifacts': artifacts, 'source_run': str(run), 'academic_format': 'White background, source-bound axes/units, vector SVG/PDF, PNG300dpi, editable SVG text; nominal native results.'})
    return {'groups': 6, 'subpanels': len(panels), 'output': str(output)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--audit', type=Path)
    p.add_argument('--switch-fixture',type=Path)
    a = p.parse_args(); print(json.dumps(render(a.run, a.output, a.audit,a.switch_fixture)))
