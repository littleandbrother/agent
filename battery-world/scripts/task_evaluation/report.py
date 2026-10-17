#!/usr/bin/env python3
"""Render the completed pilot from saved evidence. No model or solver dispatch."""
import json
from pathlib import Path
import re
from xml.sax.saxutils import escape

APP = Path(__file__).resolve().parents[2]
DOC = APP / 'docs/agentlab/architecture-v2/task-evaluation-20261017'
DATA = DOC / 'data'
ROOT = Path('/Users/depengsu/.local/share/bf-agent-architecture-v2/task-evaluation')
LABEL = {
    'audit':'审查诊断', 'reproduce':'复现', 'reconstruct':'重建', 'complete':'补全',
    'optimize':'优化', 'new_design':'新设计', 'single_module':'单模块',
    'coupled':'联合设计', 'end_to_end':'端到端', 'unspecified':'范围待定',
    'mechanical':'机械', 'power':'电源', 'pcb':'PCB', 'firmware':'固件',
    'sensing':'感知', 'radio':'无线', 'receiver':'接收端', 'assembly':'装配',
    'unknown':'待确认', 'conflict':'约束冲突', 'plausible':'初步可行',
}
NOTES = {
    'Q01':'诊断计划覆盖失谐、粘贴与负载；领域标签额外加入感知，需区分测量手段与被设计对象。',
    'Q02':'原请求没有指定样机制造；应先确认交付深度，再决定是否采购和加工。',
    'Q03':'复现模型、曲线、参数与偏差分析齐全；先取得论文和图表。',
    'Q06':'传感器负载和整流输出应从已有文件提取；不必一开始要求用户重新测量所有数据。',
    'Q08':'单电源设计可以读取传感器负载而不设计传感器。预设标签要求联合领域过强，保留原评分并标注歧义。',
    'Q12':'Gerber 可恢复几何，网络与元件身份需要额外证据；计划已标注不确定封装与网络。',
    'Q13':'标签遗漏电源，但计划已经检查发送压降；最后一步直接改程序超出“查原因”，应先提交诊断。',
    'Q15':'保留采样频率的要求被识别；改频率不应成为后续节能手段。',
    'Q19':'离线回放适合比较滤波；实际执行仍需验证延迟和响应，不能只比较噪声方差。',
    'Q22':'计划确实在接收日志上做缺帧和重复统计，标签却未含接收端。领域应由消费对象校正。',
    'Q23':'“单模块/联合”边界有歧义；若只改无线配置属于局部优化，联改供电与程序才是联合修改。',
    'Q24':'无线链路复现本来包含发射与接收；单模块标签与预设联合标签存在粒度差异。',
    'Q26':'计划包含板壳同坐标系、净空与插拔检查，内容合理；标签粒度需要统一。',
    'Q27':'机械标签足以描述支架强度；预设额外要求装配标签未必必要。载荷假设不能直接冻结成用户约束。',
    'Q29':'明确识别了耦合，却只标电源；源端特性和机电反馈应进入联合读取范围。',
    'Q31':'关键错误：“固定这块电源板”被理解成安装固定，计划加入修复电源板。此处应保持板卡设计不变，只调整采样发送策略。',
    'Q32':'电容与发送周期都允许变化，属于联合优化；模型计划正确包含组合扫描，但 scope 标成单模块。',
    'Q33':'接线与引脚映射跨硬件和固件；是否需要 PCB 标签取决于接线资料来自板卡还是外部线束。',
    'Q35':'覆盖初始化、时间同步和反馈环，方案方向合理；下一步必须绑定实际模型接口和执行器。',
    'Q38':'第二轮未知论文时领域留空合理，但后续预设了主控、固件和无线。边界复测已改成先读论文、范围待定。',
    'Q40':'整机审查应从原任务读取必需专业和接收要求；当前 power/firmware 标签过窄。',
    'Q41':'“更小更省电更便宜”被扩到量产定型。应以同服务条件下的候选比较结束本轮。',
    'Q42':'原始论文和照片未提供，预设全电子领域也缺依据；应先识别真实工程对象再选重建格式。',
    'Q43':'第二轮输出被截断。复测识别出能量矛盾，但意图仍被改成 audit；应保留新设计意图，另标可行性冲突。',
    'Q44':'分析而不设计的意图正确。缺方案时允许范围和领域待定；最新接口已支持。',
    'Q45':'含两个连续任务：先复现、后优化。应建立阶段关系，复现结论有效后再开启优化。',
    'Q46':'第二轮输出被截断。复测得到机械记录方案，没有强加 MCU 与无线。',
    'Q47':'“看看是否划算”应先评估。第二轮误标优化并安排节点原型；复测已改为审查和方案比较。',
    'Q48':'正确保持外部任务与输入不变；已有有效基线应直接复用，再执行受影响的组合。',
}


def load(name):
    return json.loads((DATA / name).read_text())


def label(value):
    return LABEL.get(value, value or '无完整输出')


def save(name, text):
    (DOC/name).write_text(text.rstrip()+'\n')


def figures():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    target=DOC/'figures'; target.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False,
                         'savefig.dpi':180, 'axes.titlesize':12})
    m=load('mechanisms/result.json')
    fig,axes=plt.subplots(1,2,figsize=(10,3.5),layout='constrained')
    names=['Static','Rich event','Refined','Abstain']
    keys=['static-budget','fixed-event-contract','counterexample-refinement','abstain-on-ambiguity']
    for ax,metric,title in zip(axes,['false_accept','coverage'],['False accepts / 72 test cases','Decision coverage']):
        vals=[m['tables']['test'][k][metric] for k in keys]
        ax.bar(names,vals,color=['#c76b47','#3478b5','#2d927b','#8b98a9'])
        for i,v in enumerate(vals):ax.text(i,v+.015 if metric=='coverage' else v+.8,f'{v:g}',ha='center')
        ax.set_title(title);ax.set_ylim(0,1.15 if metric=='coverage' else 42)
    fig.savefig(target/'contract-results.png');fig.savefig(target/'contract-results.pdf');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,3.5),layout='constrained')
    for side,color,name in [(0,'#2d927b','early energy / pass'),(1,'#c76b47','late energy / fail')]:
        r=json.loads((ROOT/f'mechanisms/runs/energy_timing-00-{side}.json').read_text())
        axes[0].plot([v['t'] for v in r['trace']],[v['energy'] for v in r['trace']],color=color,label=name)
    c=load('mechanisms/inputs.json')[0]
    axes[0].axhline(c['emin'],color='#888888',ls='--',label='task floor')
    axes[0].axvspan(.8,.88,color='#c9d5ea',alpha=.5);axes[0].set(xlabel='Time (s)',ylabel='Stored energy (uJ)',title='Same totals, different timing');axes[0].legend(fontsize=8)
    r=m['replay'][0];v=[r[k] for k in ['parent_packets','child_frozen','child_full','child_scoped']]
    axes[1].bar(['Parent','Frozen\nchild','Full\nchild','Scoped\nchild'],v,color=['#8b98a9','#c76b47','#3478b5','#2d927b'])
    for i,val in enumerate(v):axes[1].text(i,val+.12,str(val),ha='center')
    axes[1].set(ylabel='Valid frames',ylim=(0,10.5),title='Old supply trace reverses the ranking')
    fig.savefig(target/'counterexamples.png');fig.savefig(target/'counterexamples.pdf');plt.close(fig)
    a=np.genfromtxt(DATA/'default/vendor-probe/waveform.csv',delimiter=',',names=True)
    fig,ax=plt.subplots(figsize=(10,3.5),layout='constrained')
    ax.plot(a['time_s'],a['VIN_V'],label='VIN: input reservoir',lw=1.5,color='#346bb4')
    ax.plot(a['time_s'],a['VOUT_V'],label='VOUT: regulated output',lw=1.5,color='#239879')
    ax.axhline(2.2,color='#b96a43',ls='--',label='service floor on VOUT')
    for t in [2,6,10,14]:ax.axvline(t,color='#c76b47',alpha=.55,lw=.8);ax.text(t,.15,'TX',rotation=90,ha='right',fontsize=8)
    start=load('default/vendor-probe/result.json')['startup_2p3v_s']
    ax.annotate(f'VOUT >= 2.3 V at {start:.2f} s',xy=(start,2.3),xytext=(10,3.7),arrowprops={'arrowstyle':'->','color':'#42556a'})
    ax.set(xlabel='Time (s)',ylabel='Voltage (V)',title='Vendor PMIC, zero initial storage, original fixed schedule')
    ax.legend(loc='upper left',fontsize=8);fig.savefig(target/'default-startup.png');fig.savefig(target/'default-startup.pdf');plt.close(fig)
    rows=load('p08/readback.json')['rows']
    fig,ax=plt.subplots(figsize=(10,3),layout='constrained')
    ax.plot([r['initial_v'] for r in rows],[r['paper_us'] for r in rows],'o-',label='Paper Note S13')
    ax.plot([r['initial_v'] for r in rows],[r['native_us'] for r in rows],'x--',label='Existing native waveform')
    ax.set(xscale='log',xlabel='Initial output voltage (V)',ylabel='Decay duration (us)',title='P08 transfer: six existing waveform results');ax.legend()
    fig.savefig(target/'p08-transfer.png');fig.savefig(target/'p08-transfer.pdf');plt.close(fig)


def markdown():
    a=load('intake-results-v2.json');u=load('usage.json');p08=load('p08/readback.json')
    notes={'authorship':'Codex qualitative plan audit after model execution; original scores retained', 'notes':NOTES,
           'label_caveat':'Prewritten labels are reviewer labels, not a unique ontology. Do not infer plan correctness from label agreement.'}
    (DATA/'qualitative-review.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2)+'\n')
    brief=f'''# BF 任务范式与研究先导实验

日期：2026-10-17。代码环境：独立 Architecture V2。报告由 Codex 汇总，任务评估和案例判断来自真实 Pi/DeepSeek 调用。

## 本轮结果

| 工作 | 实际结果 | 当前结论 |
| --- | --- | --- |
| 48 道用户问题 | 两轮共 96 次评估；结构有效 10/48 → 44/48；新增边界复测 13/13 有效 | 接口格式已统一，语义范围仍需校正 |
| 压电默认案例 | 名义参考收到 4 帧；LTC3588-1 零储能探测 18.21 s 才启动，原计划收到 0 帧 | 参考链可执行；器件级冷启动方案待修订 |
| 原十例迁移 | 选择 P08，复用 6 条衰减结果，最大偏差 0.5265%；Pi 完成检查、判断、PDF 和同版包 | 曲线复核任务全流程完成 |
| 契约与重放 | 90 对静态信息相同、结果相反；30 个固定旧轨迹错误排序 | 两个最小反例成立；精化方法与固定丰富契约打平 |
| 方法改进 | 3 条链、每链 2 代真实模型提案 | 选中配置与固定因果范围基线相同；RSI 收益尚未出现 |

## 最值得修的四件事

1. **分类与计划分开检查。** Q31 把“固定电源板”误解成安装固定；Q13 诊断计划擅自加入改程序。
2. **用户目标和可行性分开。** 零能量即时发包应保留“新设计”意图，同时报告约束冲突。
3. **默认案例补电压驱动的固件执行。** 当前固定 2/6/10/14 s 调度早于器件启动；下一候选由 Pi 选择启动门控或其他设计修订。
4. **研究优先挑战强基线。** 已知三个关键特征全部加入，固定规则也能获得相同结果。下一实验应检验未知遗漏变量、保守性和真实计算成本。

## 代码与验证

新增统一任务评估接口和示例；允许范围待定；记录用户原话；严格检查输出结构。评估发生在创建项目之前。Pi 工具入口已经接通。

56 项相关回归、Pi 类型及运行图检查、V2 发布检查通过。原 Demo 和十个原 Pi 的工程、会话、费用核对一致。P08 和原默认名义结果直接复用。

本轮新增 {u['total_new_model_requests']} 次模型请求，全部结算；账本费用上界 **${u['total_new_upper_bound_usd']:.6f}**。有一次新建数值校准任务误重复了相同电气输入；已按输入哈希补上缓存，并验证换验收窗口时零派发复用。

## 阅读顺序

- `02_TASKS.md` / `output/pdf/02_TASKS.pdf`：48 道简短问题、任务定义、方案与逐题复核。
- `03_EXPERIMENTS.md`：两个最小反例、实验方法、完整结果与论文判断。
- `04_DEFAULT_AND_P08.md`：默认方案、真实启动波形、P08 六点及版本身份。
- `05_REPRODUCE.md`：数据、脚本、重算与保护记录。
- `deliveries/`：两个 Pi 生成的同版工程审查包和 PDF。
'''
    save('01_REPORT.md',brief)
    lines=['# 48 道用户问题、任务定义与方案复核','',
           '问题保持日常语言。下表来自第二轮原始输出；分数按运行前标签计算。边界复测另列，原失败记录保留。', '',
           '| 编号 | 用户问题 | Pi 任务类型 | 范围 | 结构 |','| --- | --- | --- | --- | --- |']
    for r in a['results']:
        v=r.get('assessment',{});lines.append(f"| {r['id']} | {r['request']} | {label(v.get('intent'))} | {label(v.get('scope'))} | {'有效' if r['schema_valid'] else '失败'} |")
    lines+=['','## 统计与复核原则','',
            '意图标签一致 45/48；范围一致 39/48；覆盖预设领域 34/48；是否缺输入一致 46/48。标签由 Codex 预先编写。Q08/Q23/Q24/Q26/Q27/Q42 等存在粒度或资料不足歧义，原始评分未回改。',
            '所有任务均输出草案，未自动冻结需求、建工程或派发仿真。具体模型最终回答见 data/public-model-answers.json。',
            '共同问题：多数计划直接安排现场测量、制造或样机验证。平台应先匹配现有资料与执行能力，再决定本轮交付深度。', '']
    for r in a['results']:
        v=r.get('assessment',{});lines += [f"## {r['id']} · {r['request']}",'',
        f"类型：{label(v.get('intent'))}；范围：{label(v.get('scope'))}；领域：{'、'.join(label(t) for t in v.get('domains',[])) or '待定'}。",'',
        f"复核：{NOTES.get(r['id'],'先读取已有工程和有效结果，再补必要资料；将本轮交付深度与可用工具对应。')}",'']
        if not v:lines+=['本次输出截断。边界复测得到完整定义，见本文末尾。',''];continue
        for title,key in [('任务目标','goal'),('允许变化','design_variables'),('验收条件','acceptance'),('交付内容','deliverables')]:
            val=v.get(key,[]);lines += [f'**{title}**','']
            lines += [str(val)] if isinstance(val,str) else ['- '+str(t) for t in val];lines += ['']
        lines+=['**需要补充的输入**','']+['- '+t['question']+('（影响执行）' if t['blocks_execution'] else '') for t in v['missing_inputs']]+['']
        lines+=['**方案与检查**','', '| 步骤 | 动作 | 用途 | 产出 | 检查 |','| --- | --- | --- | --- | --- |']
        for i,s in enumerate(v['plan'],1):lines.append('| '+' | '.join([str(i),*[s[k].replace('|','/') for k in ['action','purpose','output','check']]])+' |')
        lines+=['']
    lines+=['## 13 道边界复测','', '5 道已知问题 + 8 道新表述；13/13 结构有效。新表述仍由本轮设计者编写，属于工程回归。','',
            '| 编号 | 用户问题 | 结果 |','| --- | --- | --- |']
    for r in load('edge-checks/result.json')['results']:
        v=r.get('assessment',{});lines.append(f"| {r['id']} | {r['request']} | {label(v.get('intent'))} / {label(v.get('scope'))} / {label(v.get('feasibility'))} |")
    lines+=['','复测仍发现：Q43/N05 能量冲突被识别，但原设计意图被改成审查；N04 采样频率与电容联合调整未列固件领域。所有完整定义与计划保存在 data/edge-checks/result.json。']
    save('02_TASKS.md','\n'.join(lines))
    research='''# 契约充分性与因果范围重放：先导实验

## 实验回答了什么

两个最小反例均已运行：相同静态接口可以对应相反服务结果；固定旧供电轨迹可以把更差的程序策略判成更好。加入事件、信息窗口和反馈后，本实验消除了这些错误。

最重要的负结果：反例驱动精化选择了全部三个预定义特征，结果与固定丰富事件契约完全相同。真实模型提案也收敛到同一固定配置。本轮没有得到超越强基线的算法收益，也没有得到改进器自身变强的证据。

## 冻结的对象与实验单位

| 项目 | 设置 |
| --- | --- |
| 环境 | 分段恒功率能量缓冲模型，供能-负载-信息窗口-接收判断 |
| 独立变量 | 接口暴露特征、重放范围、模型提出的方法配置 |
| 固定内容 | 每个实例的任务、初态、源条件、程序活动、评价规则 |
| 三种机制 | 能量到达时序；事件信息有效窗口；活动负载影响源响应 |
| 主要样本 | 30 个参数种子 × 3 种机制 × 2 个相反结果实例 = 180 个场景，90 对 |
| 分割 | 开发 72、验证 36、测试 72；成对实例不跨分割 |
| 重放样本 | 30 个场景；开发 12、验证 6、测试 12 |
| 模型 | 既有 V2 provider 的 deepseek-flash；身份及费用进入原账本 |
| 方法提案 | 3 条链，每条 2 代；temperature=0，非独立随机种子实验 |
| 输入特征成本 | prefix=1、information=2、feedback=3；基础成本 1，均为设定权重 |

参数种子改变幅值，机制族保持相同。一次运行或一对缩放实例不能算成一个全新的工程任务。

契约与重放表由确定性判断器计算；真实模型参与任务评估和方法配置提案。研究者已查看机制先导结果，模型没有读取测试标签；本轮属于开发先导，正式论文仍需冻结新机制测试集。

## 最小反例一：总量相同，先后不同

选取 energy_timing-00：初始储能 98.598 µJ、任务下限 89.634 µJ、输入功率 717.076 µW，供能持续 0.6 s。采样发生于 0.80 s，发送发生于 0.84 s。

- 情况 A：在 0.10-0.70 s 收集能量，随后执行任务，结果成功。
- 情况 B：在 2.00-2.60 s 才收集能量，任务发生得过早，结果失败。

两者的总能量、初态、名义电压、峰值电流、帧长度和任务能量完全相同。静态接口对两者给出相同判断。

相同接口信息对应相反二元结论时，仅消费该接口的确定性判断者至少判错一个；等概率二元对的最小错误率为 1/2。允许补充读取或实验时，需要把新信息纳入接口。本轮把这一经典不可区分性事实作为问题定义。

另外两个反例分别交换事件有效窗口，以及加入负载作用于源端的反馈。90/90 对实例均出现静态别名与相反结果。

![最小反例](figures/counterexamples.png)

## 论文一：结果与算法增量

精化器在开发对上按“区分未覆盖反例数 / 特征成本”贪心选择。候选特征由开发者预先实现：任务前缀能量余量、采样相对信息窗口的余量、活动期反馈损失。

| 方法，测试集 72 | 正确放行 | 正确拒绝 | 错误放行 | 错误拒绝 | 未判定 | 覆盖率 | 特征权重 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 静态总预算 | 36 | 0 | 36 | 0 | 0 | 100% | 1 |
| 丰富静态量 | 36 | 0 | 36 | 0 | 0 | 100% | 1 |
| 固定丰富事件契约 | 36 | 36 | 0 | 0 | 0 | 100% | 7 |
| 反例驱动精化 | 36 | 36 | 0 | 0 | 0 | 100% | 7 |
| 全部回答未知 | 0 | 0 | 0 | 0 | 72 | 0% | 1 |

“丰富静态量”使用相同静态字段与总量判据，是字段增广控制；“固定丰富事件契约”才是本轮的有效强基线。精化器最终选择全部特征，没有节约特征成本。

![接口实验结果](figures/contract-results.png)

200 个后续压力场景改变源幅值、起止时刻、初态、容量、活动时间与反馈系数。静态方法错误放行 98 个；事件方法正确放行 84、正确拒绝 116。该压力集在先导结果后生成，用于检查代码与适用范围，单独记录。

保守性结果目前很弱：测试没有产生错误拒绝，所选机制又刻意突出静态误放行。下一阶段要加入“固定预算拒绝，但动态可调度”的可行方案，测量有效设计被排除的比例。

## 最小反例二：旧供电轨迹奖励更差的策略

父程序每 2 s 尝试一次服务；子程序每 0.4 s 尝试一次。源和初态不变，能量由实际活动持续消耗。

| 评价方式 | 父程序有效帧 | 子程序有效帧 | 对子程序的判断 |
| --- | --- | --- | --- |
| 完整响应环境 | 2 | 1 | 变差 |
| 把父供电轨迹固定给子程序 | 2 | 9 | 被误判为改善 |
| 重新执行受影响的反馈范围 | 2 | 1 | 与完整环境一致 |

30/30 个构造场景发生错误排序。无源反馈时复用独立源输入并重算电源、程序、接收；有源反馈时把源端也纳入执行范围。30 个范围重放均与完整计算一致。半数场景的工作计数由 4000 降到 2000，另半数保持 4000，合计减少 25%。这里统计的是模型运算单元，不是实际求解器时间。

## 论文二：真实方法提案结果

模型只能选择三个特征以及 frozen/power_only/causal/full 四种重放方式。它读取开发结果；验证集用于选择配置；选择后固定测试集评分。没有提供测试反馈来生成后代。

初次 2200 输出 token 限额下，6 次中 5 次把额度消耗在推理，最终答案为空。保存这些失败后，把上限改为 8192，其余条件不变，6/6 得到合法配置。

| 配置，固定测试集 | 契约判断正确 | 重放错误排序 | 工作计数 |
| --- | --- | --- | --- |
| 固定静态 + 旧轨迹 | 36/72 | 12/12 | 24000 |
| 固定丰富 + 全量执行 | 72/72 | 0/12 | 48000 |
| 固定丰富 + 因果范围 | 72/72 | 0/12 | 36000 |
| 模型选择的配置 | 72/72 | 0/12 | 36000 |

两条链两代选择不变；第三条链从 full 改为 causal。按验证排序选中的是第一条链的第一代配置。三个特征和合法重放边界已经由开发者写好，因此这里只验证方法配置选择。改进器代码、提示和特征生成能力没有发生递归演化。

本轮没有实施普通反思优化、GEPA、DGM 或 Pacti 的可比较实测；也没有实现未知边界的误差估计器。论文不能把本轮固定配置选择包装成对这些方法的超越。

## 校准、反例和重复执行

零能量控制失败、充足能量控制成功、错误信息窗口失败；相同策略重放相符；时间步从 2 ms 减到 1 ms 后判断不变。

六个代表场景另用 ngspice 积分相同能量状态方程，6/6 判断一致，最大终态偏差 0.829 µJ。它核对数值实现；器件级物理核对来自另外的 LTC3588-1 探测。

信息窗口对的电气输入相同，第一次校准执行时误重复了一次。现已按电气网表摘要缓存；更换信息判据直接复用同一波形，新增检查验证零派发。原 P01/P08 的已通过原生作业没有重跑。

## 当前科学结论与下一次最小实验

| 命题 | 本轮结果 | 下一步最有区分力的实验 |
| --- | --- | --- |
| 静态接口会隐藏服务成败差异 | 已有成对反例和原生数值校准 | 新器件/新反馈机制中的信息遗漏 |
| 反例精化优于固定丰富契约 | 本轮打平 | 高成本特征池，测最小观察成本与错误拒绝 |
| 固定旧轨迹会错误评价新策略 | 30 个构造场景均出现 | 在实际 PMIC + 电压驱动程序上复现 |
| 范围重放能节省完整计算 | 本模型减少 25% 工作计数 | 真实求解器耗时，范围扩展与边界误差检查 |
| 方法经历能产生可迁移改进 | 尚无跨新机制收益 | 固定反馈/验证/最终测试三集，未知机制迁移 |
| 改进器本身能递归提高 | 本轮未测试 | 固定起始求解器，让父/子改进器各自产生后代 |

当前研究入口应保留这两个反例，继续追问：怎样发现尚未实现的关键特征，以及怎样识别局部重放已经越过适用边界。下一阶段用真实设备模型回答这两个问题，比继续堆叠 Agent 数量更有价值。

## 相关工作定位

- Pacti：契约组合与不相容分析，https://www.pacti.org/ 。后续仅在兼容表达域内比较。
- GEPA：https://arxiv.org/abs/2507.19457 。后续加入普通反思优化和等预算比较。
- DGM：https://arxiv.org/abs/2505.22954 。区分配置选择、求解器改进和改进器改进。
- HarnessDev：https://arxiv.org/abs/2609.01437 。后续固定执行模型并检查迁移稳定性。

代码和完整数据：scripts/task_evaluation/、data/mechanisms/、data/mechanisms-controls/、data/method-pilot-v2/。可下载包包含逐场景轨迹。
'''
    save('03_EXPERIMENTS.md',research)
    default=load('default/final-summary.json');p=load('p08/final-summary.json')
    case='''# 默认压电案例与 P08 迁移

## 默认参考设计

机械：压电悬臂梁长 50 mm、宽 10 mm，基底与压电层各 0.2 mm，端部质量 2 g。名义输入 30 Hz、加速度峰值 4.905 m/s²。模型一阶频率 31.087 Hz。

电源：Pi 选择 LTC3588-1。压电接器件内置桥的 PZ1/PZ2；输入储能在 VIN；10 µH 外部电感连接 SW 与 VOUT；D0 接 VIN2、D1 接地选 2.5 V 输出。VIN 启动典型阈值 4.04 V，范围 3.77-4.30 V；VIN 停止稳压范围 2.66-3.08 V。输入阈值与输出供电门限分别检查。

来源：ADI《Energy Harvester Produces Power from Local Environment》，https://www.analog.com/en/resources/technical-articles/energy-harvester-produces-power-from-local-environment.html ；LTC3588-1 Rev C，https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf 。

程序：主机 C 编译产生 4 组采样/发送事件，采样 10 ms、发送 4 ms。电流包络暂用 1 mA / 8 mA / 8 µA；数字接收器核对序号、值和校验。该负载还需由实际 MCU、传感器和无线器件进一步落实。

| 项目 | 既有名义参考 | 本轮器件级探测 |
| --- | --- | --- |
| 源 | 压电机电模态，100 kΩ 负载 | 同一模态，厂商桥与 buck 直接加载 |
| 电源模型 | 固定 0.5 变换效率，单储能状态 | LTC3588-1 厂商模型，VIN/VOUT 双节点 |
| 储能初态 | 抽象节点 2.5 V | VIN=0、VOUT=0 |
| 储能电容 | 抽象 68 µF | 输入 150 µF、输出 68 µF |
| 活动计划 | 2/6/10/14 s 采样，11 ms 后发送 | 复用同一编译事件表 |
| 20 s 接收结果 | 4 个有效帧 | 0 个有效帧 |
| 决定 | 保留已有名义参考 | Pi 保留审查候选，修订冷启动调度 |

名义源功率 ngspice 305.514 µW，解析 304.295 µW，偏差 0.4003%。固定效率后平均可用 152.757 µW，负载平均 40.944 µW。这些平均值没有预测器件探测中的启动等待。

器件探测得到 293282 个原生采样点。VIN 峰值 4.0575 V；VOUT 峰值 2.5534 V；VOUT 到 2.3 V 的时间为 18.2096 s。四次任务都在启动之前，故全部失败。该对照同时改变了初态与模型，后续应逐项比较以归因。

![器件启动波形](figures/default-startup.png)

Pi 的下一工程问题：零初态、20 s 条件下，按 PGOOD/电压启动任务能否完成至少 3 帧？当前执行器缺电压驱动的固件反馈入口。该入口接通后，再由 Pi 选择调度与电容方案。本次交付为名义参考及器件失败审查包；冷启动产品方案仍在进行。

Codex 介入记录：提供 ADI 原文参数，纠正外部电感、最坏返回门限和电压域混用；实现并运行器件探测。Pi 负责选型、说明修订、结果判断与 release。探测点的 150 µF 输入 / 68 µF 输出由 Codex 在已提议范围内选择，已记录，未计作 Pi 自主优化。

Pi 报告还保留一个需要语义校验的问题：历史 G2 段把 VIN 阈值与输出任务下限排列比较。实际独立判据分别检查节点，主报告不采用这项跨电压域差值。原始输出保留以供任务标准化测试。

## 从原十例选 P08

P08 选取一级降压模型六个初始输出电压的电流衰减复核。它和压电节点使用不同任务类型，适合检验系统能否按任务缩小工程范围。

原始来源 owner 为 pi-chat-e0028698d50802cb，作业 eng-19eb09030ae354a8。复用 55305 点原生波形；按 |电感电流| 最后超过 1 mA 的时刻提取，与论文补充 Note S13 第 27-28 页比较。

| 初始输出 V | 论文 µs | 原波形 µs | 偏差 % |
| --- | --- | --- | --- |
'''
    for r in p08['rows']:case+=f"| {r['initial_v']:g} | {r['paper_us']:g} | {r['native_us']:.4f} | {r['relative_percent']:+.4f} |\n"
    case+='''
最大绝对偏差 0.5265%，低于本轮 1% 的复核条件。Pi 完成读取来源、表格检查、决定、报告和同版 release。新增原生仿真为 0。

此流程证明曲线复核任务的迁移；P08 原论文中的其他电路、通信和整机功能仍按原记录保存。复核使用独立 V2 owner，原 owner 保持原样。

![六点复核](figures/p08-transfer.png)

## 交付身份

'''
    for title,s in [('默认案例',default),('P08 复核',p)]:
        case+=f"### {title}\n\n- 当前候选：`{s['current_system']}`\n- 已采用：`{s['adopted']}`\n- Release：`{s['releases'][-1]['id']}`\n\n"
    case+='原始 RAW、提取数据、代码、任务定义和封存包均有 SHA-256。完整身份见 data/deliveries.json；原工程及费用保护结果见 data/preservation.json。\n'
    save('04_DEFAULT_AND_P08.md',case)


def pdfs():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
    font='BFStudyChinese';pdfmetrics.registerFont(TTFont(font,'/System/Library/Fonts/STHeiti Light.ttc',subfontIndex=0))
    out=DOC/'output/pdf';out.mkdir(parents=True,exist_ok=True)
    styles={
        'body':ParagraphStyle('body',fontName=font,fontSize=9.5,leading=15,spaceAfter=6,wordWrap='CJK',textColor=colors.HexColor('#25384b')),
        'small':ParagraphStyle('small',fontName=font,fontSize=8,leading=11.5,spaceAfter=4,wordWrap='CJK'),
        'title':ParagraphStyle('title',fontName=font,fontSize=21,leading=28,spaceAfter=16,textColor=colors.HexColor('#153f68'),wordWrap='CJK'),
        'h2':ParagraphStyle('h2',fontName=font,fontSize=13.5,leading=20,spaceBefore=13,spaceAfter=8,textColor=colors.HexColor('#17689a'),keepWithNext=True,wordWrap='CJK'),
        'h3':ParagraphStyle('h3',fontName=font,fontSize=11,leading=16,spaceBefore=8,spaceAfter=5,keepWithNext=True,wordWrap='CJK'),
    }
    def par(text,style='body'):
        s=escape(str(text)).replace('**','').replace('`','')
        # Printable local labels instead of long Markdown paths.
        s=re.sub(r'\[([^\]]+)\]\([^\)]+\)',r'\1',s)
        return Paragraph(s,styles[style])
    def footer(c,d):
        c.setStrokeColor(colors.HexColor('#d7e1eb'));c.line(40,38,A4[0]-40,38)
        c.setFont(font,8);c.setFillColor(colors.HexColor('#6b7d8e'))
        c.drawString(40,26,'BF DESIGN · V2 · 2026-10-17');c.drawRightString(A4[0]-40,26,str(d.page))
    def build(path,story):
        d=SimpleDocTemplate(str(path),pagesize=A4,leftMargin=40,rightMargin=40,topMargin=40,bottomMargin=48,
                            title=path.stem,author='BF Design / Codex')
        d.build(story,onFirstPage=footer,onLaterPages=footer)
    def md_story(text):
        story=[];lines=text.splitlines();i=0
        while i<len(lines):
            line=lines[i].strip();i+=1
            if not line:continue
            if line.startswith('!['):
                rel=line.split('](',1)[1].rstrip(')');p=DOC/rel
                from PIL import Image as PILImage
                w,h=PILImage.open(p).size;story.extend([Spacer(1,8),Image(str(p),width=515,height=515*h/w),Spacer(1,8)]);continue
            if line.startswith('|'):
                rows=[line]
                while i<len(lines) and lines[i].strip().startswith('|'):rows.append(lines[i].strip());i+=1
                vals=[[par(c.strip(),'small') for c in r.strip('|').split('|')] for r in rows if not re.fullmatch(r'[|\s:\-]+',r)]
                cols=len(vals[0]);widths=[515/cols]*cols
                if cols==3:widths=[105,213,197]
                if cols==2:widths=[110,405]
                t=Table(vals,colWidths=widths,repeatRows=1,hAlign='LEFT')
                t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6f0f8')),
                    ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#b5cddd')),
                    ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f8fa')]),
                    ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                    ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
                story.extend([t,Spacer(1,8)]);continue
            if line.startswith('# '):story.append(par(line[2:],'title'))
            elif line.startswith('## '):story.append(par(line[3:],'h2'))
            elif line.startswith('### '):story.append(par(line[4:],'h3'))
            else:story.append(par(line))
        return story
    for stem in ['01_REPORT','03_EXPERIMENTS','04_DEFAULT_AND_P08']:
        text=(DOC/(stem+'.md')).read_text()
        if stem=='01_REPORT':text=text.split('## 阅读顺序')[0]
        build(out/(stem+'.pdf'),md_story(text))
    story=[par('48 个用户任务 · 评估与方案','title'),par('问题用日常语言描述，涵盖单模块、联合设计、整链和联合优化。每页一题，完整原文、判断与检查条件见同名 Markdown 及 JSON。'),
        par('第二轮：44/48 结构有效；意图与预设标签一致 45/48。结构和标签分数分别统计。计划是否越界由逐题复核指出。'),
        par('阅读方式','h2'),par('先读用户原话，再看 Pi 如何界定任务、要什么输入、选择什么工作和交付什么。复核建议指出分类与计划之间的偏差。'),
        par('原始工程记录保留。48 道题只做任务评估，未据此自动建立 48 个工程或派发仿真。'),PageBreak()]
    edge={r['id']:r for r in load('edge-checks/result.json')['results']}
    for index,r in enumerate(load('intake-results-v2.json')['results']):
        v=r.get('assessment',{});origin='第二轮原始回答'
        if not v and r['id'] in edge:v=edge[r['id']]['assessment'];origin='边界复测回答；第二轮截断'
        story += [par(r['id']+' · '+r['request'],'h2'),par(origin,'small'),
                  par('类型：'+label(v.get('intent'))+' / '+label(v.get('scope'))+'    专业：'+('、'.join(label(t) for t in v.get('domains',[])) or '待定'),'small'),
                  par(v.get('goal','无完整定义')),
                  par('复核意见','h3'),par(NOTES.get(r['id'],'先读取已有工程与有效结果，再补必要资料；对齐本轮交付深度与可用工具。')),
                  par('先补什么','h3')]
        for x in v.get('missing_inputs',[])[:3]:story.append(par('• '+x['question'],'small'))
        story.append(par('方案步骤','h3'))
        for j,s in enumerate(v.get('plan',[]),1):
            story.append(par(f"{j}. {s['action']}",'small'))
            story.append(par('产出：'+s['output'],'small'))
        story += [par('结束条件与交付','h3'),par('；'.join(v.get('acceptance',[])[:2]),'small'),par('；'.join(v.get('deliverables',[])[:3]),'small')]
        if index<47:story.append(PageBreak())
    build(out/'02_TASKS.pdf',story)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['all','data','pdf'],default='all')
    phase=parser.parse_args().phase
    if phase in ('all','data'):figures();markdown()
    if phase in ('all','pdf'):pdfs()
    print(json.dumps({'reports':str(DOC),'pdfs':[p.name for p in (DOC/'output/pdf').glob('*.pdf')]}))
