# 三篇论文的统一拨动采能案例：工程与仿真验收记录

更新：2026-09-28。用户选择先进行仿真，不连接或烧录硬件。

当前交付的是可运行、可审查的参考工程。**完整论文校准尚未通过，不能宣称已完成可工作的实物产品，也不能启动正式 Agent/Harness 收益比较。** 最新数值以案例目录的 `receipt.json` 为准，失败求解、旧版本和原始输出均保留。

## 1. 同一产品任务

产品目标是单次门窗动作供能的无线事件节点：门窗运动带动磁体，拨动压电梁；采集的电能经过提取与储能、电源管理，支撑 MCU 冷启动、BLE 初始化和广播；接收端记录“发生过动作”。

第一版必须从零电压开始计算，并在 2 秒的本地计算窗口内完成一次广播。2 秒是本案例的工程验收选择，不是论文给出的通用保证。方向分类保留 `unknown`：原论文利用安装非对称性造成的包数差异，我们还没有可验证的正反方向分布，不能凭单条仿真轨迹编造分类阈值。本案例不需要神经网络，不能用一个无关 TinyML 模型充当产品功能。

```text
公开论文与元件资料 → 有出处的参数 / 公开假设
                            ↓
门窗轨迹 → 磁力和梁动力学 ↔ 压电机电耦合 ↔ 整流 / SP-SECE
                                                    ↓
                      输入电容 → PMIC → 输出电容 → MCU / BLE
                                                          ↓
                               完整发包 → 模拟接收 → 事件判定

每一段保留：输入、版本、求解日志、数值输出、来源、失效状态
```

## 2. 三篇论文的资料和配置分开保存

三篇全文已从作者公开网站下载并计算 SHA-256。第三篇是作者公开的 accepted manuscript，不能将它当作排版后的最终出版版本。下载器会拒绝 HTML 和哈希变化，不使用机构登录或绕过访问限制。

| 资料 | 本地文件 | 本案例用途 | 不可混同的配置 |
|---|---|---|---|
| [ViPSN-Pluck](https://metal.shanghaitech.edu.cn/publication/J40.pdf)，DOI 10.1109/JIOT.2021.3098238 | `sources/vipsn-pluck.pdf` | 产品行为、结构尺寸、nRF52832 分阶段负载、原始工程 | Parallel SP-SSHI，10 µF；铜梁和粘贴 PZT |
| [Unified framework](https://sms-lab.github.io/publications/J99_Tang%20et%20al_2025_10.10881361-665xadd8d4.pdf)，DOI 10.1088/1361-665X/add8d4 | `sources/unified.pdf` | 已识别动力学参数、磁力公式、SP-SECE、储能对照点 | 470 µH；无线负载论文周期 1 s；MFC 试样 |
| [Cross-domain simulation](https://sms-lab.github.io/publications/J125_Tang%20et%20al_2026_10.11151.4071279.pdf)，DOI 10.1115/1.4071279 | `sources/cross-domain.pdf` | 势能、跨域过程与扩展工况的核查 | 1 mH；无线负载周期 0.1 s；磁体标号与前文有差异 |

目前整机仿真是明确标记的组合衍生设计：2025 年动力学和 SP-SECE + ViPSN 的阶段能量替代负载 + 新编译的 BLE 协议参考。不是把三篇互不相同的硬件声明为同一个复刻板。尚未完成 2026 年所有图线与工况的独立复现。

作者 ViPSN Git 仓库固定在 `5a6b13f85c9ee8dfa40e231bae94218f9b562ac4`；原始 Parallel SP-SSHI、EMU 原理图和 PCB 文件作为可编辑参考保存。下载不等于本地 ERC/DRC 或新 SP-SECE PCB 已通过。Nordic SDK 与 SoftDevice 的授权保留在上游，不能把它们重新声明为本项目的 Apache 代码。

## 3. 已实现的计算与工程

### 参数与电路

`configs/reference_cases/pluck-v1/case.json` 保存数值、单位、来源定位、模型替代、验收容差和后续实验边界。2025 年识别参数为 M=20.12 g、K=605.92 N/m、D=0.14 N·s/m、Cp=40.22 nF、θ=0.0006664。原表 θ 单位与方程不一致，本实现按方程量纲采用 N/V，并记录此解释。

ngspice 同时积分磁驱动、梁位移/速度和压电电压，电路包含二极管桥、包络电容、PNP/NPN 自供电开关、电感和储能电容。没有先计算一个固定“可用能量”再直接宣布负载成功。

SP-SECE 使用论文拓扑，但二极管、线圈 ESR 和若干寄生量仍是假设；晶体管使用公开厂商模型的 Gummel-Poon 兼容参数子集，非作者原始 LTspice 模型。原文给出的磁力表达式与排斥极性描述存在解释差异：当前使用有符号磁矩乘积表示同极相对，同时保留字面正号支路用于审计。选择依据是势能梯度和局部排斥方向，不能为不同电路各选一个更吻合的磁力符号。

### 电源和负载

LTC3588-1 采用**行为模型**，输入电容和输出电容分别建模。输入 UVLO 暂停变换器，并不直接抹掉输出电容；MCU 在自己的欠压边界下复位。3.3 V 输出的典型输入阈值采用数据手册的 5.05/3.67 V；不能混用 1.8 V 输出对应的阈值。80% 效率、输出 47 µF、MCU 3.2/2.7 V 阈值等是显式工程假设，开关纹波及真实芯片效率曲线未复现。

MCU 初始化、无线初始化、一次广播能量依次采用 ViPSN Table II 的 72.70、68.47、60.37 µJ。它们是论文负载替代，**不是本次固件实测**。只有时序上完成初始化与整段广播后，仿真接收器才允许生成事件；无输入、弱耦合、全丢包用于负对照。

### 真实编译的固件与接收端

已针对 nRF52832 / S132 3.0.0 编译 BLE 广播程序，生成源码、Makefile、链接脚本、ELF、HEX、BIN 和构建回执。编译器为 ARM GCC 13.3.1。程序包含 SoftDevice 初始化、广播数据、100 ms 广播间隔及休眠等待；不是空的 `main` 或只有 GPIO 的占位程序。

广播契约为原型 manufacturer ID `0xffff`，载荷 `BFP1` + 8 字节 FICR 设备 ID。设备 ID 不是动作 ID；静默间隔分组可能合并近邻动作或拆分一个动作。接收程序支持 JSONL 回放和未来可选的 BLE 扫描，本轮没有启用物理扫描或烧录。

LF 晶振、天线、实际电流和欠压恢复仍需目标板验证。没有模拟 Nordic 无线模拟前端或逐指令执行 SoftDevice；固件编译与负载行为仿真是分开的证据链。

### CAD、Blender、COMSOL

已建立 ViPSN 尺寸参考：100×10×0.53 mm 铜梁、50×8 mm PZT、10 mm/20 mm 磁体，输出 STEP/BREP/STL、三视图、GLB、原生 `.blend` 和渲染。PZT 厚度、夹具及摆放位置属于显式假设。6 个原生实体读回有效，未发现不允许的几何交叠；GLB 全新导入后再次检查零件身份和尺寸。

这套几何对应 ViPSN，不套用为 2025/2026 的 MFC 试样。夹具参考尚无紧固、公差与完整装配设计，不能直接标为可制造产品。

COMSOL 完成铜基梁固定端、端部 0.01 N 的静力校验：细网格位移约 0.24159 mm，Euler–Bernoulli 解析值约 0.24425 mm，误差约 1.1%；两档网格变化约 0.11%。铜材料 E=110 GPa 是工程假设。此 FEM 不包含粘贴 PZT、磁力、压电耦合或瞬态，不能据此宣布整机有限元校准成功。

## 4. 验收方法与当前主要问题

协议先于运行写入不可变目录，包含完整配置、引擎与运行器快照/哈希、0 模型费用和 1500 秒本地批次时间上限。每次 SPICE 子进程上限 180 秒。当前检查包括：

1. 三篇 PDF 身份和哈希；原始求解输入/输出可追踪。
2. 磁力等于势能的负梯度；自由衰减与独立解析解一致。
3. 压电、电路储能、负载和输出电容的能量核算。
4. 20 µs 与 10 µs 两档最大步长；储能末值、峰值、首次发包时间和包数比较。
5. 47/330 µF 的 SEH 与 SP-SECE 对照论文 Table 3；预先声明电压误差容差 20%。这是工程初步复现门槛，不是统计置信区间。
6. 无输入、弱耦合、全丢包；模型不得产生虚假的成功事件。
7. 固件真实编译、原生几何和 GLB 独立读回。

已定位并修复 ngspice 默认 ASCII 精度使极小相邻时间步被舍入为重复时间戳的问题，改为 17 位输出，旧失败保留在 `simulation-v1`。完整采样保存为 gzip CSV，页面曲线采用抽样预览，不用降采样曲线替代积分数据。

目前核心未通过项是 SP-SECE 的论文量值复现：初步 47 µF 结果约 14.15 V，而论文实验为 5.30 V；SEH 约 4.095 V，对照 4.32 V。不能把前者解释为“我们的设计更好”，也不能单靠调整效率或改容差将其判为通过。磁极约定、开关波形、元件参数、原模型文件缺失必须逐层核对。以最终运行回执的实际数值和每项判定为准。 当前 SP-SECE 计算压电峰值约 314 V，整机约 402 V，明显高于论文图示波形，也高于所选 [NSR02100 的 100 V 反向额定值](https://www.onsemi.com/download/data-sheet/pdf/nsr02100ht1-d.pdf)所允许直接外推的范围；需检查每只二极管反向波形及器件模型的击穿适用域，不能仅凭积分守恒承认电路有效。

## 5. 页面与可复现入口

在现有工作台进入 **控制台 → 验证 → 参考案例**；产品模式标题旁有“参考案例”入口。页面展示验收门槛、实际运行、来源、失败原因、三维结构、曲线和哈希绑定下载。无需新建第五种模式。

接口只向本机操作者开放，普通参与者不能读取案例答案。产物必须在清单中且哈希一致；目录越界和篡改都会被拒绝。参考包未自动注入其他任务的 Memory，未覆盖旧产品、正式任务或研究门控。

工程仓库：`/Users/depengsu/Documents/battery-world`。
案例目录：`/Users/depengsu/Documents/bf-agent-workbench/reference-cases/pluck-v1`。

```bash
cd /Users/depengsu/Documents/battery-world
export PYTHONPATH=packages/python/bfworld/src
python3 scripts/fetch_pluck_sources.py --home /path/to/new-case
git clone https://github.com/METAL-ShanghaiTech/ViPSN.git /path/to/new-case/upstream
git -C /path/to/new-case/upstream checkout 5a6b13f85c9ee8dfa40e231bae94218f9b562ac4
python3 scripts/build_pluck_firmware.py --home /path/to/new-case
python3 scripts/build_pluck_geometry.py --output /path/to/new-case/cad --render
python3 scripts/build_pluck_comsol.py --output /path/to/new-case/comsol
python3 scripts/pluck_reference_case.py --home /path/to/new-case --run-id simulation-001 --seal
# 使用安装 matplotlib 的 Python；发布只追加视图与文件，不改变验收结论：
/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 scripts/publish_pluck_case.py --home /path/to/new-case --run-id simulation-001
```

本地工具链路径见各脚本；COMSOL 需要现有安装和许可。本轮已实际运行，并非仅生成调用命令。每次复现使用新目录，不能覆盖旧求解记录。`ltc3588-1.pdf` 是电源资料的单独来源，下载器一并保存到 `sources` 中。

## 6. 下一步与 Agent 实验边界

先完成尚未通过的物理模型校准：从同一机械轨迹比较 SEH/SECE，核对峰值触发、二极管/晶体管导通、提取结束和储能电流；优先获得或核对作者原始 LTspice 元件模型与磁极约定。单项元件资料不能证明完整模型一致。补上全部六组电容与独立工作点、参数不确定性和模拟欠压的专项检查，再封存可作为比较基准的版本。

随后完善同一衍生产品的 MFC 制造尺寸、独立 SP-SECE 原理图/PCB，以及与目标固件一致的负载参数。在纯仿真阶段，结论限定为模拟事件服务；方向识别需要可解释的安装非对称模型和正反分布，缺少这些时持续保留 unknown。

`study-contract.json` 已定义四种用途：参考辅助工程、自主检索、长程修订、Harness 迁移。当前均不自动派发。参考辅助阶段的源码/答案不能作为自主检索任务的初始 Memory；同一任务上的修复不能冒充跨任务迁移。后续要固定世界、评估器、模型与预算，保存人工干预账本，在未见任务上比较 Harness。当前付费模型调用为 0，既有科学基准与预算未改变。
