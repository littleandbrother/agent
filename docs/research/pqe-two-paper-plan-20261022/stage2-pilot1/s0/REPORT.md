# PQE 第二阶段首包：四格真实 Pi 先导

总派发 `BF-PQE-20261022-001`，本包 `BF-PQE-S2-PILOT1-20261022-001`。四格已按冻结协议各运行一次，本有限包执行关闭；完整第二阶段尚未完成。结果是两条实际观察—选择—消费者—Update 链，以及四次请求输出截断；没有自主修改设计、修复、最终提交或问题重构，不建立方法优势。

## 四格结果

| 题目 / 方法 | 请求 | 实际工具 / 新数值 | 已发生的动作与完整服务 | 终止与自判 | 费率上界估算 USD |
| --- | ---: | ---: | --- | --- | ---: |
| D04 / strong_generic | 1 | 0 / 0 | 未动作，NOT_ASSESSED | 首次 Generate 返回 length，无公开 JSON、无最终自判 | 0.0056442 |
| D04 / full_h | 3 | 1 / 1 | 选择 observe 初始设计，完整服务 FAIL | Update 消费真实结果；下一 Generate 返回 length，无最终自判 | 0.0115743 |
| D07 / strong_generic | 3 | 1 / 1 | 选择 observe 初始设计，完整服务 FAIL | Update 消费真实结果；下一 Generate 返回 length，无最终自判 | 0.0114417 |
| D07 / full_h | 1 | 0 / 0 | 未动作，NOT_ASSESSED | 首次 Generate 返回 length，无公开 JSON、无最终自判 | 0.0056442 |

总计 **8 个真实 provider 请求、2 次真实数值输入、2 个工具调用、USD 0.0343044 费率上界估算**。34,664 输入 token、19,921 输出 token；全部 SETTLED，新增 UNKNOWN 与未结预留均为 0。该金额使用原账本锁定费率，不是供应商账单金额。原 R11 UNKNOWN、null usage 与 USD 0.2661324 原预留整行身份未变。

四次截断均由实际响应给出 `length`，公开 text 长度为 0，未形成可解析的公开 JSON。对应 completion_tokens 为 4096、4096、4096、4095；每请求上限为 4096。没有读取或引用私有 reasoning 内容，也不据此推断未观察到的内部推理过程。两次有效 Generate 和两次有效 Rank 均有完整 JSON，单次 token 成本和输出见 `RESULTS.json`。

这里耗尽的是单次响应长度；各格尚未耗尽 12 请求、24 工具、6 新数值、900 s 或 USD 4 总上限。冻结的 driver 在无有效输出时停止，不手写修复、不续写截断、不追加组、不补跑、不转移剩余额度。保留失败是本包结果，而不是工程装置无解结论。

## 两条实际消费链

D04/full_h 只生成一个 observe 候选并选择 `obs-current-1`，未选列表为空，事前预测为 UNKNOWN；真实消费者在初始设计上产生 7 条持久事件记录、1 条过早且不匹配的接收、47 次 TX 掉电。独立完整服务判为 `MISSED_OR_LATE_EVENT` 和 `SPURIOUS_OR_DUPLICATE_EVENT_ID`。`received_count=1` 是收到的记录数，不是正确匹配 1 个真事件。没有改变去抖、供电参数或程序。

D07/strong_generic 同样只生成一个 observe 候选并选择 `c1_baseline_observe`，未选列表为空，事前预测为 UNKNOWN；初始设计有 4 条持久记录、0 接收、753 次 TX 掉电，完整服务判为 `MISSED_OR_LATE_EVENT`。没有修改 ESR、容量或发送程序。两条结果都进入真实 H.Update；full_h 的 next_evidence 为 UNRESOLVED，strong_generic 为 ordinary feedback available，hypotheses/invalidated 均为空。因此实际调用过 Rank 和 Update，但没有多候选排序、假设支持/反驳或因果归因证据。最后均未产生 Agent 最终 PASS/FAIL/UNKNOWN 自判。其余两格没有新运行，不能沿用旧参考或另一组结果给它们算服务判决。

逐格证据在 `episodes/<cell>/`：`method-transcript.json` 保存生成、候选、选择、实际位点、预测、Update 与终止；`actions/01/` 保存真实输入、raw、独立 assessment 和公开反馈；`callbacks/` 保存实际 Pi 输入、公开输出、截断及费用对应。完整公开列表提供按 64 条分页的 observe 入口，两组采用相同采样/分页规则。本包没有提出分页动作，不能声称分页已被真实 Agent 使用。

## 身份、权限与记账

复用现有 Pi SDK **0.85.1**、8980 服务及同一个 provider 账本，使用 4 个新 owner。两组均为 `deepseek/deepseek-flash`，profile `engineering-reasoning-active-context-v4`，thinking enabled / high，temperature 0.2，单请求输出上限 4096。身份限定到实际请求/响应的供应商别名与配置；供应商没有提供可锁定的底层权重 revision。

每次固定 H 的模型 callback 创建新的干净 Pi SDK 会话，输入为该 episode 的公共 Task、Design、Problem、公开历史和结果。SDK 的实际工具列表始终为空，skills/extensions/context-file discovery 关闭；网关拒绝任意模型工具、tool 历史及其他端点。固定可信 H 校验 JSON 后调用合法 BF broker；模型未取得 shell、Python import 或宿主文件访问工具，也未加载模型生成代码。

S0 将 8 次网关的实际消息逐条与 provider 权威 wire 记录比较：system/user 两条消息相同，准确模型、token、thinking/temperature 配置一致，无工具；初始模型历史为空，无私有参考、qualification 答案、最终 evaluator 文件或开发聊天输入。固定的 H 位点实际调用与输入绑定记录在 transcript。这证明本次 JSON-only 参与者权限边界，不是新建通用 OS sandbox。

本包没有调用会授予无上限权限的旧 method_authorize。新 owner 有有限 USD 4 cap、900 s grant；共同 study 上限 USD 16。串行期间临时启用现有 per-owner 预算模式，结束后恢复原来的缺省设置；4 个 grant 已关闭、participant token 已撤销。旧账本和无上限策略未改写；旧 R11 不恢复，新缺失 usage 的阻断仍有效。

## 复用、工程范围和独立审查

第一阶段 55 项测试、已有资格/负例/半步长证据均复用。新增 3 项 S0 接口检查（含真实 Pi SDK 接模拟 provider 的一次无工具请求）和 B 的 10 项薄 driver 契约检查通过；另核对 callback 返回封装。这些检查没有付费或产生科学输入。四格之间没有改变冻结 source、Task、服务、候选权限或 driver。

两个旧初始 raw 属于旧校验器字节版本，未冒充当前 exact-input/source cache。本包两个首次 observe 计为 2 次新数值；没有重跑参考修复、半步长或全仓 init。后续精确缓存路径已实现，本包实际 reused 为 0。

工程阅读入口：canonical APP 下 `studies/pqe20261022/engineering/stage2/door-entry.html`。A 的独立事件/供电/服务回执在 `../a/A-RECEIPT.json`；B 的行为/稿件交接在 `../b/RESULTS-HANDOFF.json`。该视图和模型为构造仿真：门角轨迹是规定输入，负载仅通过附加反力约束评价；`esr_ohm` 是负载支路简化串联供电阻抗，未包含真实电容净充电电流的完整 ESR 效应；网关窗口为理想链路。没有实体干涉、制造、电路板或硬件验收。

A 对两份既有 raw 的独立事件、CRC/去重、队列、TX 电压和能量账核对与 S0 一致：D04/D07 的 TX 最低诊断分别为 1.69170865 V、1.30000040 V，均低于 1.8 V；附加力与两条能量闭合在原约束内。最低值按开始点/保留步末分别解释，不作为连续时间极值证明。宿主 HTML 的实际观察页包含独立真值和两条时间轴，未加入参与者输入；视图仅完成静态结构和脚本语法检查，未完成浏览器渲染验收。

## 第二阶段剩余缺口

本包完成了四格有限尝试和实际 callback/权限/账本接通。S2-08/09/10/11 的生成、选择、消费者和 Update 有两条真实观察链；S2-14 的四格执行和失败记录已交付。冻结模型的 S2-02—07 证据按原构造范围复用；A/B 交付 S2-15/16 的独立读回与短因果增量。

完整阶段二的核心出口仍缺：按证据自主修订 Design/Problem、产生改变后的动态后果与正确最终结论；至少一条实质问题重构轨迹，以及自主局部修复的对照。本包 `P` 没有任何实际变化，不能用其接口或分组标签宣称 S2-12 的科研轨迹已成立。S2-01/03 的可读几何/连接入口也不能替代完整 CAD 干涉或器件电路工程资格。

下一步应先由原审查会话判断输出协议在固定预算中的可用性及下一独立工单，再选择真正不同的机制任务；不自动重跑这四格、扩大矩阵、沿电容/相位扫参或进入 F1/G。原总授权继续有效，没有新增许可要求，本有限包的冻结边界和停止条件已经执行。

## 存储与交接

复用原环境、SDK、服务和源码树；无新环境、工作区、备份或 commit/push，自动化维持暂停。原模型失败、2 份新 raw、8 次请求账及公开行为记录保留；临时软件接口测试目录已自动清除。实际产物字节与可用空间见 `postflight.json`。本包开发释放空间记为 0，之前的 34.17 GB 退役释放不再次计入。

复现入口为 `scripts/pqe_pilot.py`；本包协议已冻结且四格已执行，**不要再次运行 `run`**。检查既有证据从 `RESULTS.json`、逐格回执和账本读回开始，不以自动重跑替代审查。
