# BF Agent R3–R5 实施、实验与验收记录

日期：2026-10-12，北京时间。十论文只读审查截止 01:49；最新完整应用验证完成于 02:00。本报告记录实际执行结果，不把阶段、方法世代、数字产品和物理验证合成一个完成度。

## 1. 当前结论

**R3 的有限 A/B 环境与 Pi 实际修订已通过；R4 的一次真实方法候选及追加配对评价已完成，追加评价拒绝扩大采用；R3 完整工程范围与 R5 尚未完成。**

| 对象 | 实际结果 | 尚不能授予的结论 |
|---|---|---|
| R0–R2 的 C | Pi 已自行修订、执行、采用、提交；6 个独立门通过；本轮复用 | 改变负载后仍可沿用 D5 供电、完整 MCU/RF/物理产品通过 |
| R3 A/B 公共环境 | v4 精确代码哈希下 20 个正负/分辨率/版本控制匹配，含 16 次新数值账本回放 | 标定采能器、开关变换器、原生 PCB 或完整目标 MCU 已建成 |
| R3 A 实际 Pi | 同一 owner 恢复后，四个请求的采样、类别、期限、虚拟接收通过 | 长期连续工业诊断、实测信号识别或真实无线通信 |
| R3 B 实际 Pi | 单事件启动、真实请求身份、期限、虚拟接收通过 | 无初始表面电荷、真实 TENG/SECE 电路或实物自供能 |
| R4 方法候选 | Pi 生成条件化 Skill 补丁；5 对首轮、3 对追加实际运行；真实加载可核对 | 已提高正确率、稳定降低总成本、跨论文泛化、生产采用 |
| R5 后代 | 追加确认未通过冻结采用规则，后代派发被前置检查阻止 | H2 已产生、递归链已成立 |
| R5 实物 | 测量协议、原始数据模板、来源检查可用；硬件连接未确认 | 已刷写、校准、实测接收或物理功能失败/成功 |

没有调整规则来得到绿色结果。阶段文件包可以交付，未获得资格的能力仍明确保留。

## 2. 版本、范围和保护

实施工作树：

```text
/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-refactor-r0-r2-20261011
  battery-world/
  pi-bf-aiot/
```

Git 分支为 `codex/bf-design-lab-r0-r2-20261011`；基线 integration HEAD 为 `7e4aaff8294bf445d3ebd7d5e65028a43eff07ff`。当前改动为本地未提交实现，不把该 HEAD 当成包含本轮修改的发布版本。执行版本由具体协议及文件 SHA-256 确定。

执行计划：[BF_Agent_Refactor_Implementation_Plan_20261011.md](</Users/depengsu/Documents/Long-Horizon AI Agent/workbench/review-packages/BF_Agent_Refactor_Implementation_Plan_20261011.md>)。其 SHA-256 为 `9ccf08b29ae61bcc882ed77c73d958d35c5b7d73f787a44f760810264a389099`。R3–R5 所有权已预先登记于 `project/features/BFA-035-dot-integration-pilot/design-lab-r3-r5.json`，含假设、证伪条件、测试、负控、预算和停止条件。

继续保留：十个原论文 owner、已有工程、5957 条原设计 owner 模型费用记录、跨两个库的 21 条历史 UNKNOWN 完整行及全部预留、原论文索引、123 个原 Python 源文件和旧 D5 参考。对旧成功且输入不变的工程没有重新求解。主页面内容与原 UI 字节一致，主页面 SHA 为 `5a1f77537c25f07c3eaa2e4fc477d2f47eb8ba2b8a2e0e4b42f4962e3f9a078e`。

本轮没有使用 `harness-creator`、创建定时聊天消息、恢复旧门磁 owner、替换十篇 Pi 会话、代写 Pi 被评价的 C 或 Skill 补丁、提交 Git 或推送 GitHub。只读查询均使用 SQLite `mode=ro`，不为审查创建第二 Workbench。

## 3. R3：真实程序进入有限源—供电—服务循环

主要实现：[finite_cases.py](</Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-refactor-r0-r2-20261011/battery-world/packages/python/bfworld/src/bfworld/agentlab/design_lab/finite_cases.py>)，版本 `finite-source-program-power-service-v4`。

`manifest()` 冻结范围、源条件、初始能量、任务时限、编译器和求解器身份。`build()` 编译 Pi 的真实 `program.c`，生成可执行主机程序和 Cortex-M4 可重定位对象。`execute()` 每个时间步执行该程序，并反馈当时电压。`evaluate()` 独立检查请求身份、实际采样阶段、类别、接收期限和精确数值回执。

```text
源条件 / 初始储能
        ↓
实际编译的 C 核心 ← 当前电压及当时可见的传感样本
        ↓
阶段与时序 → 声明范围内的固定阶段电流 → 储能、电压与复位
        ↓
虚拟发送 / 接收 → 独立请求与诊断检查
```

程序改变采样窗口或发送持续时间，会改变任务成本、储能及接收结果。源不足会影响程序启动和完成。这解决了“只有源码变化、执行轨迹不变”的一类问题。

### 3.1 明确的抽象层

这仍是 **F0 共享逻辑执行**。电流使用可信执行器固定的四个阶段值：idle 0.3 μA、boot 0.41 mA、sample 1.596 mA、TX 3.659 mA。参与者不能把阶段电流改成零，但程序仍声明自己处于哪个阶段；没有指令级/SoC 功耗测量。

目标输出是 ARM `.o`，不是已链接目标 ELF/HEX；没有真实 ADC、时钟树、DMA、SoftDevice、射频栈或板级引脚执行。主机运行真实 C，并不自动代表 MCU 上的完整程序能运行。

源模型、理想 3.3 V 钳位和恒定储能电容属于声明域。禁止把有限模型的通过写成原论文器件或完整设备通过。

### 3.2 A：合成振动诊断服务

| 参数 | 冻结内容 |
|---|---|
| 供能 | 规定的整流 Norton 等效功率，`0.003 × abs(sin(2π × 30t)) W` |
| 储能 | 220 μF，初始外部储能 0 J，理想 3.3 V 上限 |
| 运行 | 12 s，2/5/8/11 s 四个外部请求，每个期限 0.75 s |
| 信息 | 合成 30/90 Hz 信号；256 Hz 采样，64 点窗口 |
| 独立性 | 真值标签不传给参与者；通过样本变体检验类别是否随实际信号改变 |

这验证四个有间隔诊断请求，不能称为无限期连续监测。没有机械梁、压电材料和整流/变换器的标定。

### 3.3 B：单次输入事件通知

采用固定表面电荷 Q–V–x 工作上界：Q=4 μC，接触电容 100 nF，分离电容 2 nF，抽象转移效率 0.65，事件能量约 2.548 mJ，在 0.1–0.2 s 转移。一个请求，期限 1 s，总仿真 1.5 s；4 点采样用于事件通知。

**初始外部储能为零，但源具有 4 μC 初始表面电荷和约 0.08 mJ 初始静电能。** 因而只能声明“外部储能从零启动”，不能声明系统完全无初始电荷或全部能量只来自当前一次机械输入。当前效率是抽象损失比例，没有执行 SECE/buck 开关拓扑。

### 3.4 数值复核的实际范围

`native_energy_check()` 将同一执行的净能量账本分块后交给原生 ngspice 积分，核对最终能量。它验证数值账本，不独立验证输入功率或负载模型是否符合真实硬件。

实际源码片段，`finite_cases.py:native_energy_check/evaluate`：

```python
v={'execution_id':execution['execution_id'],
   'trace_sha256':execution['observations'][execution['trace_name']],
   'solver':str(SPICE),'solver_sha256':sha(SPICE),
   'deck_sha256':sha(deck),
   'raw_text_sha256':sha(directory/'energy-native.txt'),
   'final_storage_J':native_final,
   'reference_final_J':execution['final_J'],'absolute_error_J':error,
   'passed':error<=2e-6,
   'scope':'Independent native integrator replay, not native source/rectifier/converter qualification'}
```

接受条件还要求 `execution_id` 与实际 trace 摘要对应。其他执行的 PASS 不能为本执行背书。分块数值检查不独立验证每个 MCU tick 的时序；另外的细时间步检查验证该模型内的接收与延迟稳定性。

### 3.5 资格及被撤回的早期结果

当前唯一权威 R3 有限资格为：

`docs/agentlab/refactor-r3-r5-20261012/environment-1791740435574814000/qualification.json`

20 项控制匹配，含正确参考、标签置换、细时间步、旧构建拒绝、零源、错误身份、接收丢失、错误诊断、混叠、长 TX、持续供能不足、慢启动、窗口不足和单次事件能量不足。阴性失败是预期结果，不作为环境失败计数。16 次新 ngspice 数值回放，0 模型调用，0 旧 D5 原生重算。

早期环境中的真值泄漏、自由阶段电流、主机专用 I/O 漏检以及数值回执缺乏精确绑定，均记录在 `validity-amendments.json`。对应旧 PASS 被撤回或标为已被替代，原文件未覆盖。Mach-O 对象误送 ELF 解析器、B 通知错误继承 A 窗口、审查器读取错误摘要字段，也单独记为公共环境/检查器错误，不归因于 Pi 设计。

主机 I/O 检查补了 `#ifdef __APPLE__` 路径：实际主机对象用 `nm -u` 检查，ARM 对象另检；汇编和构造器拒绝，文件和进程外部符号拒绝。当前仍不能声称已形式化证明对任意恶意 C 的隔离；纯逻辑参与者是本轮支持范围。

## 4. Pi 实际 A/B 设计与恢复

执行器：[run_finite_design.py](</Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-refactor-r0-r2-20261011/battery-world/scripts/design_lab/run_finite_design.py>)。Pi 使用真实 SDK、正式 DeepSeek 代理和原账本，`deepseek-flash`、high thinking、compact-v2。工具返回冻结事实，Pi 决定检查、源码修订与最终提交理由；最终检查独立执行。

| 实验 | 实际过程 | 结果及费用 |
|---|---|---|
| A 首次 | 11 请求；Pi 通过 `candidate` 发送源码，但旧工具处理器只接受 `source`，且静默忽略错误字段；检查仍失败；后处理另有字段名错误 | 失败保留，$0.0826878；未把进程完成算作验收 |
| A 恢复 | 同一 owner `pi-chat-777548cec6ae6f86`；真实 SDK 恢复 23 条历史消息；工具严格校验字段，Pi 改成实际零交叉分类 | 4 新请求，$0.043401；四个请求正确，延迟均约 0.285 s；细步长、信号置换通过 |
| B | owner `pi-chat-a1943f58b0dd3b11`；Pi 将硬编码 request=1 改为真实 pending 身份并保留去重 | 5 请求，$0.0155073；基准延迟约 0.19 s，细步长/0.8 倍输入变体约 0.1995 s，通过 |

A 的 owner 累计 15 请求、$0.1260888；A/B 共 20 个真实请求、$0.1415961。所有为 SETTLED 本地登记，不是供应商结算账单。恢复没有创建替代 owner、清除旧失败或重置费用。

实际采用 D：

```text
A D-f36e2d554fad1d91013e96ff185e4abefbb35fea1edde5aa4f86ec1df6f2c0d1
B D-2aeaf25321ea4eee7803b989fed9d5983fd2f7ba153a411db68960350015a030
```

Pi 源码与公开采用理由、编译对象、运行记录、数值账、最终独立检查、控制器冻结文件一起封装。每个 ZIP 完整 CRC 与全部成员摘要已读回：

- [A-F0-digital-design.zip](</Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-refactor-r0-r2-20261011/battery-world/docs/agentlab/refactor-r3-r5-20261012/deliveries/A-F0-digital-design.zip>)，SHA `b372f21ca69d91b17e1dd9c43dfc2d50e2efbcc94d5584a6bf2efa837e97087a`。
- [B-F0-digital-design.zip](</Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-refactor-r0-r2-20261011/battery-world/docs/agentlab/refactor-r3-r5-20261012/deliveries/B-F0-digital-design.zip>)，SHA `606227e44221d9845dd926c132f3b6897301383e118bd2346fdc90ac57a62627`。

Codex 参与者源码修改为 0；公共起点、模型、编译执行器、工具修复和独立评价由 Codex 提供。因此可称“BF 在固定有限工程空间自主修订”，不能称“无外部基础设施或无参考答案辅助”。

## 5. R4：经历、Pi 补丁与实际配对

核心实现：[method_study.py](</Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-refactor-r0-r2-20261011/battery-world/packages/python/bfworld/src/bfworld/agentlab/design_lab/method_study.py>)，函数 `expected/evaluate/candidate/decision`；Pi 接口为 `pi-bf-aiot/packages/bf-agent/src/method-task.ts`。

评价对象是实际编译的异步回调 C 逻辑：连接身份、operation 身份为 uint32，0 也是有效值；旧连接回调不破坏新连接；重复完成只交付一次；替换、超时和迟到完成按各自身份处理。Python 期望模型与实际 C 输出分别计算。先执行无 Agent 正确参考和失败参照，再连接 Pi。

Pi-Improver 读取真实 C 修订片段和公开经历，提交六字段候选：instruction、hypothesis、falsifier、applicability、negative_scope、evidence_episodes。它不能修改评价、账本或自己批准候选。

本轮候选：

```text
H-method-495f8cec8544379ace120d688d38f7554c94b3d1b1ffb5a11b1e9075ea05ea4c
SKILL.md SHA b3984edc332a777e84a5939bfe4c76f7e717b59d797e38a66ab50190f8dd1990
```

候选要求锁存完整连接/操作身份，独立表示 connected 与 pending，旧回调保持无动作，采样完成与实际交付分开，匹配的完成/超时只作用于自己的请求。Pi-Improver 4 请求、$0.0047247，Codex 未代写补丁。

这是实际 `SKILL.md` 文件和受保护 system 指令的加载实验；不是已发布到通用 21 项技能目录的产品升级。正式请求内容检查确认实际加载，检查的只是公开信息，不采集隐藏思维链。

### 5.1 预注册采用规则

所有子方法独立检查通过、没有正确性退化，并满足其一：

1. 至少一个新正确性收益，子方法加候选获取成本不超过父方法 1.5 倍；
2. 正确性均通过时，计入候选获取成本，总费用降低至少 15%。

不能事后删掉改进器成本、挑最便宜单项或把无增益双方 PASS 算作能力提高。

### 5.2 首轮与追加确认

| 比较 | 对数 | 正确性 | 父费用 | 子费用 | 获取费 | 冻结结论 |
|---|---:|---|---:|---:|---:|---|
| 首轮固定顺序，父→子 | 5 | 双方全部通过，收益 0 | $0.122184 | $0.0733143 | $0.0047247 | 合计约降 36.1%，限定变体采用 |
| 三个新序列，子→父 | 3 | 双方全部通过，收益 0 | $0.0368694 | $0.0288015 | $0.0047247 | 合计约降 9.1%，低于 15%，拒绝扩大采用 |

首轮同步对照中的父费用异常偏大，贡献大部分表观差额；顺序可能影响缓存，单样本也受随机性影响。追加反向顺序减轻一个混杂因素，但不是统计保证。只看追加求解费用约降 21.9%，若加入获取费则不达门槛，故按冻结规则拒绝。

同一获取费在两次资格计算中使用，**没有在账本二次扣费**。首轮五对和追加三对的全部真实模型费用合计 $0.2658939。没有将八对事后混合、降低阈值来覆盖追加失败。

两份不可变比较：

```text
method-study-77a587a1bb6ee37dd97726d8/comparison.json
method-study-followup-d98c5124f7b02b89f532eea5/comparison.json
```

原运行 Python 后续只增加了后代阻止条件；封存包保留根据原始 pre-run SHA 精确恢复的旧运行器及原评价源码，另提供当前源码。首个失败 A 包未在运行前复制完整 Python 包装器，保留其原记录哈希和这个可复现性缺口。

## 6. R5：未满足的前提与已准备的验证

后代检查回执 `R5-descendant-blocked.json` 为 `BLOCKED_NO_CONFIRMED_PARENT`，新模型派发 0。追加确认没有满足规则，因此不把未确认的方法作为“已改善父代”继续产生成功谱系。第一轮限定采用历史保留，生产推广仍为 false。

物理准备见 `physical-readiness-1791738323981611000/`：raw CSV 仅表头、测量模板 origin=UNCONFIRMED、测量计划和来源验证器。JLinkExe/nrfjprog 已安装，未观察到 USB 串口；这不能证明现场没有硬件，也不能证明调试器可用。没有刷写或发送仪器控制命令。

`physical.py:inspect_capture()` 要求外部批准的采集元数据、仪器身份、校准回执、设计版本、原始 SHA、单位和时间关系。测量计划另要求记录校准不确定性；代码不自动判断校准是否充分。模拟文件或自行宣称实测的文件不能通过来源门；来源门通过也不等于完整产品通过。

尚需真实板卡/采能器版本、BOM、接线与调试器确认、目标 ELF/HEX，以及电压/电流/事件/接收原始测量。已向用户询问一次，尚无设备答复；不能凭软件工具安装替代这些事实。

## 7. 恢复的具体修复与边界

C 主控已有持久任务、不可变设计、采用 CAS、同一 operation ID、WAIT 真实 pending 作业、事件 cursor 和精确提交绑定。A 的同 owner SDK 恢复本轮确实使用了 23 条历史消息并完成修订。

同时发现实验 SDK 与通用 chat 初始化之间的缝隙：21 个新实验会话已完成独立 SDK 执行，但通用 chat 的未派发初始消息仍标为 QUEUED。按完成记录保留旧 SDK 会话，并经唯一现有服务的 recall API 撤回这些未派发占位，避免后续误点重试派发到错误控制器。

回执 `deferred-placeholders-1791740844349903000.json` 核对 97 条新费用行不变；原十 owner 不在操作集合中；0 新推理或仿真。撤回的是未发送的通用占位，不是已完成实验。

当前 A/B/方法协议仍以实验 CLI 和封存文件组织，没有统一迁入 C 的持久主任务/Studio 交付流。这是实际集成缺口，不能因 CLI 通过就宣称所有任务都在产品 UI 内无缝恢复。

## 8. 检查与复现

最新完整应用检查：`refactor-r0-r2-20261011/verification/native-environment-1791741319469001000/report.json`。实际 `./init.sh` 通过：**932 个 Python tests**、应用/Pi SDK/World Studio 类型与构建、2803 样本投影；0 外部模型调用，0 旧封存原生重算。17 项新增针对测试另行通过，含信号真值置换、免费电流拒绝、主机专用 I/O、错数值回执及假物理来源。

根科学仓库此前实际 `./init.sh` 为 1145 tests，6 FAIL、6 ERROR、4 skipped；冻结父证据/锁/快照问题保留。不能用应用通过覆盖根仓库失败。88 个科学 feature 摘要仍为 `16e3c12f9412dcb6e986bf668e384410e556743e5f024b5414f27fc3aa1302a1`。

在上述 `battery-world` 目录，可运行：

```sh
# 新资格检查会新建输出并进行有限数值积分；不是旧产品重算。
rtk proxy .venv/bin/python scripts/design_lab/qualify_r3.py
rtk proxy env PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m unittest discover -s tests/agentlab -p test_design_lab_r3_r5.py -v
# 当前十论文只读复核；只生成新审查回执。
rtk proxy .venv/bin/python scripts/design_lab/audit_system.py
```

付费 `run_method_study.py --run`、`run_method_followup.py --run`、`run_finite_design.py --case A --run`（B 用 `--case B`）是正式实验派发命令，**不要为验证包内容重复运行**。应先读取已封存协议、attempt 和独立结果；改变 E/H/V 时须创建明确新实验，不覆盖旧记录。

## 9. 本轮费用及归因

R3 实际 A/B 加 R4 首轮及追加确认共 **97 个 SETTLED 新请求，本地登记 $0.40749**，含 A 首次失败。先前 R0–R2 C 的 17 请求 $0.1348554 独立保留，不混入本轮合计。资格控制、审查、包装和本轮完整 init 无外部推理费用。

本轮不把缓存感知价格估算改写为供应商实付，不修改原保守费用登记。也未完整计入 Codex、人工、原生计算和物理设备成本；所以它不是全项目成本。

| 工作 | 执行者 | 证据边界 |
|---|---|---|
| 模型、执行器、资格、独立检查、恢复接口修复 | Codex | 公共基础设施建设 |
| A/B C 源修订、检查选择、最终采用理由 | Pi | 声明 F0 范围内的自主工程修订 |
| 条件化 Skill 候选 | Pi-Improver | 方法候选生成，不自行采用 |
| 父/子程序和公开修订 | Pi-Solver | 全部实际请求及检查记录 |
| 冻结采用规则、追加确认与拒绝 | 独立程序；Codex维护 | 不等于证明方法无效于所有任务 |
| 实物校准与端到端验证 | 尚未执行 | NOT_TESTED |

## 10. 尚需完成的工作

1. 将有限源模型升级为有来源、可检查的机械/电路/负载接口；先资格确认再连接 BF。改变 C 负载必须重新耦合，保留旧固定 D5 证据。
2. 将 A/B 的持久操作、结果、提交接入同一主任务控制器，消除通用 chat 占位与独立实验执行的双重状态。保留原 UI。
3. 明确一个目标板级执行范围：真实链接构建、外设行为、任务功耗以及接收端；不能只增加输出格式。
4. 方法改进继续以新任务为准，针对成本/正确性提出可证伪的小候选；本候选不生产推广、不声称递归收益。
5. 取得实物身份和原始测量，校准模型；若测量否定模型则更新 E 并使受影响结论过期。

详细的使用者、研究者、工程及论文评价见 [SYSTEM-REVIEW-20261012.md](</Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-refactor-r0-r2-20261011/battery-world/docs/agentlab/SYSTEM-REVIEW-20261012.md>)。最新机器可读阶段结论为 `refactor-r3-r5-20261012/closeout.json`。
