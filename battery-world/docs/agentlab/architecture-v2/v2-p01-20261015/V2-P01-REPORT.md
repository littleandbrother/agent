# V2-P01：两轮跨专业设计与同版审查交付

完成日期：2026-10-15。运行位置：独立 Architecture V2，8870；Lab 从现有 8768/lab 读取。

## 结果

**两轮连续设计已跑通。** 原 BF Lead 组织原 Power / Firmware Pi，完成实际修订、目标构建或求解、系统集成、八项独立验收、设计决定及同版交付。

连续主线：`SC-f9a05943… → SC-a1974dec… → SC-e8f2f2e5…`。

BF 将第二版保留供审查，当前资格为 `REPAIR_REQUIRED`。采用版仍为 `SC-4c0da605…`（原 `D-8a1f760b…`）；冻结提交版 `D-c7890e74…` 的来源和状态单独保留。

## 四项修复

| 问题 | 已落地的行为 | 验证 |
|---|---|---|
| 声明格式冲突 | `repository_contracts.declaration_spec()` 统一 `interface/sources/assumptions/issues`；提示、工具与示例使用同一定义 | 模型可见示例由实际检查器接受；错误字段及 SHA 被拒绝 |
| 部分提交丢父文件 | 专业提交继承完整父树，执行按完整 manifest 生成输入 | 连续“源码提交→声明提交”，源文件、编译/求解输入、worker 源码 ZIP、系统清单、交付 ZIP 全部对应 |
| 表述一致代替设备判断 | 接口时序、目标构建、联合供电和八项工程门分别记录 | BF 实际改变固件和负载输入；独立检查读本版 RAW，并得到供电失败结论 |
| 失效后无新资格出口 | `repository_validate(scope=system)` 追加不可变八门记录；`qualification()` 计算当前资格 | 新证据返回同一 SC；未改输入的固件及原生 EDA/CAD 证据精确复用，历史提交和回执保留 |

源码位置：`packages/python/bfworld/src/bfworld/agentlab/design_lab/repository_{contracts,actions,execution,validation,load}.py`；Pi 入口：`../pi-bf-aiot/packages/bf-agent/src/repository-task.ts`。

## BF 实际设计与执行

| 轮次 | BF 的修订 | 实际执行 | 系统与决定 |
|---|---|---|---|
| 第一轮 | Firmware Pi 实现每 5 秒开启一段 12 事件／2250 ms 广播；Power Pi 对应活动表 | `eng-68513e5516fb0bb8`：真实 nRF52832 / SDK 17.1 / S132 7.2 构建。模型输入未变，复用 `eng-9d45631d57148be4` | `SC-a1974dec…`；BF 根据供电和绑定结果选择 `REVISE` |
| 第二轮 | BF 选择 6 事件／1125 ms 小修订；Power Pi 修订真正进入求解的通知负载 | `eng-42f734718d566c30`：新 S132 目标构建；`eng-2cf474f68315a9d8`：新 SPICE 求解，165,130 点／13 变量 | `SC-e8f2f2e5…`，父为第一轮；BF 选择 `RETAIN_FOR_REVIEW` |

每轮先提交真实输入，再单独提交接口声明；声明提交仍包含此前源码。第二轮原专业 owner 显式重基到第一轮 SC，SDK 历史前缀保留。

第一轮构建失败两次，Pi 自行修复后构建成功。此后声明、重基和检查修正均复用已成功的精确输入作业。全程新增 3 次固件构建尝试（2 次失败、1 次成功）及第二轮 1 次新固件构建、1 次新 SPICE；CAD 和其他输入未变的成功仿真未重跑。

[完整源树与实际消费审计](actual-cycle-audit.json) 保存完整 SC/DC/IC/EX 身份、源摘要、构建输入、RAW、连续提交、重基、BF 决定及 ZIP 对应关系。

## 当前第二版八项验收

| 工程门 | 结果 | 实际卡点 |
|---|---|---|
| 固件事件逻辑 | PASS | 18 项既有公开事件／总线反例通过，本版目标构建成功 |
| 同版交付 | PASS | 89 文件与本版作业输入、产物、包内清单一致 |
| 供电—负载链 | FAIL | 最低供电 0.133508 V，要求 1.8 V；人工接通模型出现负电压；声明应有 664 点，实际 PWL 为 672 点 |
| PCB 连接／DRC | FAIL | 原生输入未变，精确复用 52 项间距错误、50 项连接错误 |
| 源与 SECE 适用域 | UNEVALUABLE | 器件参数、绕组及真实 SECE 行为尚缺依据 |
| 原理图／BOM／引脚 | UNEVALUABLE | 供应商、封装、厂商引脚全审计和 T1 参数待核对 |
| 板卡—固件接口 | UNEVALUABLE | 时序声明已通过；PCB 外设初始化及完整引脚审计未完成 |
| 机械装配 | UNEVALUABLE | 元件高度、PCB 到 CAD 变换、安装孔对应缺失 |

第二版实际 Iload 电荷为 `0.0009120850588268327 C`，窗口声明为 `0.0009117226890756307 C`。漏电单独计账。

## 检查器修正

旧检查器将紧凑 v3 表缺少展开数组判为数值不一致；v4/v5 又采用了明确窗口表。修正后：

- 紧凑表核对实际 netlist SHA 和点数；SC1 绑定通过。
- 窗口表由独立程序重建，不运行参与者生成器；SC2 的 664／672 点差异保留为真实失败。
- 固定名义输入、人工接通边界和八项工程门保持。
- 原 EDA/CAD 输入和原独立证据逐项核对后复用，原 PCB 失败进入当前资格。

检查器版本：`power-firmware-source-contract-v3`、`p01-system-independent-review-v2`；记录中同时保存主程序、负载解析器与固件反例 fixture 的 SHA。

新回执：SC1 `RV-26b7093638d6cae4eb73bcfbcd0cda05e1316e35dbddef78301f0c0a8fd13b8d`；SC2 `RV-454541ff3ab726d9cc3f69a7fe73d153cad7b6360fc0ed9da19eb65966eb62ef`。

旧回执和包保留，新回执及最新资格已进入两版新包。核对：[delivery-validation-readback.json](delivery-validation-readback.json)。检查器更正期间 SC 内容、源码、RAW 与构建产物未变化，原生作业新增为 0。

## 连续设计与恢复

- **A：连续部分提交**：实际构建／求解消费完整父树；声明提交精确复用相同成功输入。
- **B：新系统基线继续**：第二轮从 SC1 显式重基，旧工作区和 SDK 历史保留；两轮主线审计通过。
- **C：中断与未知状态**：确定性故障测试覆盖 UNKNOWN 不重派、脏工作区拒绝重基、成功作业复用；实际运行跨平台发布恢复原 owner。

平台恢复补齐了旧快照淘汰、当前源码保留、失败编译日志和 owner 绑定的归档读取入口。旧原始历史保留。早期旧基线审查分支 `SC-b3a0e625…` 和中间分支 `SC-d686794d…` 单独作为历史，连续两轮审计从 `SC-f9a05943…` 计数。

Lead 曾误建两个未执行的 V2 专业任务，均 0 请求／0 费用；实际设计使用原三个 owner，误建记录保留。专业任务读取复用作业的完整数值产物仍需完善入口；本轮系统检查器已直接消费对应 RAW。此项作为下一项工具工单登记。

## 费用和介入

| 会话 | 新请求 | 本地保守登记 USD | 缓存费率估算 USD |
|---|---:|---:|---:|
| BF Lead | 103 | 1.4925 | 0.8087 |
| Power Pi | 96 | 2.3044 | 1.4950 |
| Firmware Pi | 130 | 3.2774 | 1.8532 |

合计 329 请求，原本地登记 **$7.0744**，按供应商缓存费率估算 **$4.1569**。估算覆盖全部本轮请求；供应商账单另行对账。原账本未替换，历史 UNKNOWN 和全额预留保留。详细数据：[cost-final.json](cost-final.json)。

Codex 修改公共接口、恢复程序和检查器，执行独立审计及导出核对；本轮参与者工程源码由 Pi 修改，Codex 代写为 0。任务范围、检查器更正和交付补充由 Codex 投递并留痕，设备策略及采用决定由 BF 作出。方法对照与 RSI 收益尚未测量。

## 回归与发布

- Repository：179 项测试通过，含声明、父树、消费、资格、重基、UNKNOWN、归档和负载反例。
- 上下文：114 项测试通过；Pi 离线构建及完整类型检查通过。
- `./init.sh` 使用 `architecture-v2-lab`：7 项测试、7 项实际预览通过，0 模型调用、0 仿真重跑。回执：[live-regression-004/result.json](live-regression-004/result.json)。
- 原十篇会话及 12,454 条费用记录逐行摘要一致；原 P01 6 件原生文件、Baseline manifest 与独立 V2 profile 摘要一致。回执：[preservation-final.json](preservation-final.json)。
- Draft PR [#3](https://github.com/littleandbrother/agent/pull/3) 对比基准 `3dc8a72056e85b71998c4160da309474c2cbee1c`，最新 head 由 BF V2 regression 验证。分支 `codex/bf-architecture-v2`；原 stable/main 及默认执行路径保留。

## 交付

- 第1轮：`SC-a1974dece1a65f85d410d4cd5438f1a72aa7db476da793ddc34e8feab7db56e8`；`REL-478344a4da146de6f20d7f9effdf5e74554574386c45347bffd926d27a0ee515`。
  - 文件：[P01_V2_第1轮_同版审查包_20261015.zip](</Users/depengsu/Downloads/P01_V2_第1轮_同版审查包_20261015.zip>), 23.63 MB。
  - SHA-256：`4d6c395a9499da40477c26ff45f4cb65390b33b02342650b73aa01d18cc5b158`。
- 第2轮：`SC-e8f2f2e5b6b4709a69cfbe332fca9e76351764aa11e7a988382e31e2a066d4d9`；`REL-02aae90a976c9447dbd1e936a66d00c4eb911df4a8995bed17ef484bd17d980f`。
  - 文件：[P01_V2_第2轮_同版审查包_20261015.zip](</Users/depengsu/Downloads/P01_V2_第2轮_同版审查包_20261015.zip>), 13.19 MB。
  - SHA-256：`c410c568c6f782e0d2ef41ef7d1604e8b0e8615482ab1bb163ceb255806fb3b1`。

两版包含可编辑源码、原生工程、目标构建产物、求解 RAW、全部历史及当前检查记录和资格，物理验证状态为 `NOT_TESTED`。当前三个实际 owner 均 IDLE，原生队列排空；下一轮集中修正负载表达和人工接通模型，再处理 PCB、器件和装配。
