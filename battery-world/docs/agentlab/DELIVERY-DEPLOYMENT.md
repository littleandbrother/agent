# 产品交付、MCU 固件与 TinyML 部署验收

日期：2026-09-23。Feature：BFA-017-delivery-deployment。

本轮完成的是软件交付流程和可编译部署产物：原失败 Pi 会话完成当前版本文件发布；任务、控制台、全景能追溯进展；参考桌面陪伴产品新增 MCU 固件包和有界 NAS/模型测试包。未检测到 ST-Link，未烧录实物，也没有 MCU 实测功耗、延迟或真实用户识别准确率。一次有反馈恢复不能证明系统已达到统计意义的长期稳定性。

## 1. 原 Pi 任务恢复

会话 `pi-chat-cf37636f82c771a4`，页面名称仍保留为“独立 Pi · 历史失败样本”。产品为其自行生成的 SunBuddy v4，17 个部件。本轮没有替它重新建模、读取另一产品或改动 CAD/能源检查器。

发现并修复两个完成判定问题：

1. `publish_file` 缺少 `revision` 时原来返回不明确的错误；Pi 曾把方案 revision 1 当作装配 revision 4，导致文件存在但不属于当前交付。现在报错明确要求装配版本，观察结果带当前发布契约，Pi 已显式发布到 v4。
2. 已有交付通过后，新要求“修订并发布另一个说明文件”没有进入旧完成条件。真实复核中 Pi 连续两次只回复准备执行。现在 operator goal 可添加 `required_paths`，指定文件不存在、未发布、版本过期或哈希损坏都不能通过。原角色、零件、原生检查和能源条件不变。

增加 `delivery/PRODUCT.reviewed.md` 条件后，Pi 实际生成并发布了说明。旧文档保留，修订副本明确标注协调者事实复核。当前 `delivery.passed=true`、`missing=[]`，会话为 `IDLE`，无当前错误。源码 JSON 与当前装配 payload 逐字段相等。

复核纠正了“每日接受 20–28 次”的表述：20 次/天是需求输入，28 次是两天轨迹的累计接受数；同期有 6 次不可用和 6 次脉冲中止。文档还删除未被计算支持的短闪序列，区分日收支初筛与简化 ESR 时域假设。已有数字交付门槛只要求存在成功服务事件，不能推导所有请求均成功。

最后收尾曾触发历史会话默认 USD 1 的预留限制。按用户此前允许超出旧 USD 1 完成验收的授权，仅该 owner 上限改为 USD 1.10。全局 USD 10、单次 USD .19、token 限额保持；本轮实际新增 17 笔已结算调用，上界 USD 0.0899604，低于本 Feature USD .15 的诊断支出边界。原 1550 笔账本不改。

## 2. 三种界面的职责

| 界面 | 新增内容 |
|---|---|
| 任务 | 右侧“部署”入口；当前版本的产物、目标编译结果、网络结构与待实测指标 |
| 控制台 → 验证 → 交付与部署 | 产品定义、CAD、能源、说明/源码发布、指定文件、固件、NAS、板上验证的逐项状态；工具错误及 Trace 入口；部署文件下载；本机构建/搜索入口 |
| 全景 | MCU 固件与烧录、神经网络与 NAS 两个模块；关联真实源文件；当前任务进展；跳转交付与问题定位 |

状态来自版本化产物及检查结果，不用模型的一句“完成”覆盖事实。历史源码快照不叠加当前任务进展；没有配置自动交付条件的参考会话明确标注，避免显示成未知缺项。原始 Trace 和工程日志继续保留，架构连线仍是声明关系，不冒充自动提取的全部动态调用图。

## 3. 桌面陪伴产品的固件

绑定参考会话 `pi-chat-bc78abe0ca313091`、装配 v5。该参考与上面的独立 Pi 产品是两条分开记账的证据链，不能混成 Pi 独立完成电路和固件的结论。

工程 job：`eng-9d69de5a692b7085`，目标 STM32L031K6T6，实际 ARM GCC 13.3.1 编译。

- C 源码实现 PA0 按键消抖、PB0/PB1 双 LED、100 ms 回应、等待释放和睡眠。脉冲时长由该装配的能源参数绑定。
- 低能量停服依赖原设计的 BQ25570 VBAT_OK → VOUT_EN 硬件门控；不能单凭固件声明电路已验证。
- 导出 C/H、启动文件、链接脚本、CMSIS 与许可、构建脚本、ELF/BIN/MAP、构建日志和清单。
- 实际 Flash 1268 B，静态 RAM 12 B，另预留栈 1024 B；目标容量为 Flash 32768 B / RAM 8192 B。
- `flash_mcu.py` 默认仅输出计划，`--list` 只枚举探针；写板需明确探针序列号和 Device ID，先检查包内文件哈希和目标身份，再执行写入、校验、复位并保存 receipt。

烧录包：[mcu-firmware.zip](/Users/depengsu/Documents/bf-agent-workbench/participants/pi-chat-bc78abe0ca313091/delivery/bfa017/mcu-firmware.zip)。构建命令为解包目录中的 `python3 build.py`；工具链可通过 `ARM_GCC` 配置。重新构建可能改变编译产物/日志哈希，应重新生成版本化清单，不能绕过原包完整性校验。该包当前默认工具链路径适用于本机。

芯片约束依据 [ST STM32L031K6](https://www.st.com/en/microcontrollers-microprocessors/stm32l031k6.html)，写入工具依据 [STM32CubeProgrammer 用户手册](https://www.st.com/resource/en/user_manual/dm00403500-stm32cubeprogrammer-stmicroelectronics.pdf)。本机枚举结果为 `No ST-Link detected!`；尚无任何写板或上电验收。

## 4. 神经网络、NAS 与资源

用户尚未指定识别对象或提供真实数据，因此按可修改假设实现“单击/双击/长按”流程演示。它是参考产品的可选部署实验，不改变原产品不需要神经网络的功能承诺。简单按键节奏在实际产品中可能用规则更合适，本演示不主张网络优于规则。

工程 job：`eng-39fc4549a06a68f5`。固定 seed 7，200 epochs，实际训练 5 个 MLP 候选；按采集组划分训练、验证、测试，仅按验证集选型，随后报告选中网络的测试结果。跨划分重复样本、非法路径和越界搜索配置会拒绝。

| 架构 | Parameters | MAC / inference | 验证集 INT8 | Pareto |
|---|---:|---:|---:|---|
| 4 → 4 → 3 | 35 | 28 | 93.1% | 是 |
| **4 → 8 → 3（选中）** | **67** | **56** | **100.0%** | **是** |
| 4 → 16 → 3 | 131 | 112 | 100.0% | 否 |
| 4 → 8 → 4 → 3 | 91 | 76 | 94.4% | 否 |
| 4 → 16 → 8 → 3 | 243 | 216 | 99.3% | 否 |

以上分数来自 648 条 synthetic-fixture 数据，是通路检查，不是真实用户识别效果。四个输入为首按时长、间隔、第二按时长、总时长；隐藏层 ReLU，输出三个类别。权重 INT8，偏置/激活 INT32，累加 INT64；不把它称作全部算子均为 INT8。

选中网络导出 `model.json`、`model.c/h`、架构、候选记录、数据、划分、测试向量与指标。64 组 Python/C 整数 logits 逐值一致。MCU 测试向量固件真实编译：Flash 1940 B，静态 RAM 524 B，另预留栈 1024 B。NAS 候选的权重/工作区是分析估算，最终程序大小以链接结果为准；未对每个候选做板上时延搜索。

部署包：[tinyml-nas.zip](/Users/depengsu/Documents/bf-agent-workbench/participants/pi-chat-bc78abe0ca313091/delivery/bfa017/tinyml-nas.zip)。包含独立测试向量计时程序 `profile.c`，通过 SysTick 记录周期、时钟和输出。它尚未把实际按键特征采集接入产品灯光状态机，不能作为已集成的智能产品固件。

`latency_ms_mcu`、`power_mw_mcu`、`energy_uj_per_inference` 均为 null；页面显示“待实测”。主机 CPU 时间单独标注，不能代替 MCU。测量约定要求固件/模型哈希、板号、实测时钟、电压/电流与推理标记同步原始记录、仪器校准、重复次数和积分边界；当前仅交付约定和计时固件，尚未实现通用仪器采集和测量文件导入服务。

## 5. 验证与下一步

- 最终 `battery-world ./init.sh`：322 项 Python 测试、SDK/Studio 类型检查、构建与复现全部通过；Python 测试耗时 224.045 秒。
- 定向验证覆盖缺失发布参数、精确文件交付、旧版本/损坏文件、数据路径与 NAS 预算、实际 C parity、ARM 构建、源文件损坏时禁止烧录。
- Pi TypeScript 构建通过；最终 UI JS 语法检查通过。实际 Codex 浏览器检查任务部署、控制台 NAS 比较、滚动、全景定位与返回，修复了部署标签白名单遗漏。
- 两个 ZIP 的清单哈希、ZIP CRC 和实际 HTTP 下载哈希通过；原两条已验收产品 Trace 与旧五项交付 ZIP 保留。
- 根协调仓库 88 项研究 feature 哈希不变；本轮未运行其科学 init，不主张其健康或新的科学/RSI结论。无提交。

下一步应绑定一块实际 STM32L031K6 板和 PCB 引脚，再完成烧录、按键/灯光/掉电恢复验收。采集真实按键或选定传感器的数据，使用按用户/场次隔离的测试集训练，比较规则基线；将选中模型与实际输入、能量门控接入同一产品固件。随后用同步电流/电压/推理标记测延迟分布、待机功耗和单次能量，将实测参数反馈到同一产品的能源模型，再评估服务成功率与冷启动。本轮没有把这些未完成项标为已通过。

机器收据：[DELIVERY-DEPLOYMENT.json](./DELIVERY-DEPLOYMENT.json)。原始证据：[delivery-deployment-20260923](/Users/depengsu/Documents/bf-agent-workbench/verification/delivery-deployment-20260923/)。可重放只读审计：`rtk proxy python3 /Users/depengsu/Documents/bf-agent-workbench/verification/delivery-deployment-20260923/audit.py`。
