# 第二阶段：实际方法链与独立保留判决

本批四个实际 Pi episode 已结束。H0 与 H′ 都从任务入口产生了通过完整服务检查的新设计；**H′ 不推广，默认 H 不变**。E5 原 episode 未完成有效提交，事后使用模型已经生成的修正表达式接通了真实消费者，得到设计改变及 FAIL→PASS；这是 **POSTHOC_HOST_ADAPTER_REEVALUATION**，不能改写为原流程成功。

派发：`phase-2-core-methods-bf-20261020-001`。基线：`P2-f7ac8bfc4d5f262ff2736e25298d0c4bddd43b2f2064ae0c48b3bdb42b612977`。原 S0/A/B 工作区、依赖和冻结科学判据继续使用。本批不改变 A/R 产品的 **NO_GO / FIFO FAIL / NOT_ACCEPTED**。用户已在审查会话确认“保留当前失败基线，先完成第二阶段方法研究”；原服务及 FIFO 要求有效，产品取舍已确认，无需等待或重复询问。

## BF 信息怎样改变设计

固定任务是在 100 ms 内收到一个有效、无重复的 8 字节应用帧。供能、初态、易失事件状态、接收器和评价器冻结；合法设计仅改变电容 4–22 µF 与发送下限 0–45 ms。结果属于未做物理校准的理想瞬态模型，硬件资格为 UNKNOWN。

E5 模型读取实际组件、激励和保留活动记录，自行构造了以下由已有事实推导的布尔关系：

`tx_current × tx_duration × output_voltage > 0.5 × C × (ready_voltage² − off_voltage²)`

在原组件记录上，左侧为 28.8 µJ，右侧为 23.0 µJ，结果为 true。新增的是可被类型化消费者使用的推导关系，未增加新的物理测量，也不是已证实的新物理发现。该关系只比较标称储能余量；完整闭环服务仍由独立动态执行判定。

| 条件 | 消费者选择 | 首个有效收帧 | 完整服务 |
| --- | --- | --- | --- |
| 原设计，观察缺失时返回 UNKNOWN | 10 µF，发送下限 45 ms | 无 | FAIL |
| 事后资格化的模型关系为 true | 15 µF，发送下限 45 ms | 46.9 ms | PASS |
| 保留的静态完整信息对照 | 10 µF，发送下限 0 ms | 5.6 ms | PASS |

事后验证绑定实际模型修正调用、已取得来源及哈希、独立单位映射、适用域、独立 Decimal 表达式求值和真实消费输入。模型原有 true 分支直接选择 15 µF，未由研究者改写其公式或策略；只新执行这一改变后的合法设计，原设计与静态对照复用精确输入结果。静态对照也通过，因此不声称 E5 比完整静态信息更优。观察缺失、越域、自签来源与常数关系的拒绝结果仍保留。

## H′ 从入口重新设计及保留判决

实际改进者提出了供能、储能、程序时序与事件状态的能量/延迟账本方法。全局 H 改变要求从任务入口重新设计；电容或发送下限变化要求重执行完整供能—储能—供电—程序—接收反馈，不能沿用旧轨迹。

| 实际 fresh-session 条件 | 最终电容 | 发送下限 | 有效收帧 | 截止前掉电 | 完整服务 |
| --- | --- | --- | --- | --- | --- |
| H0 | 22 µF | 45 ms | 46.9 ms | 无 | PASS |
| H′ | 9 µF | 3.7 ms | 5.6 ms | 12.1 ms，交付后 | PASS |

两者都在任何复位前完成交付。H0 通过增加储能避免交付前掉电；H′ 提前发送，在稍后掉电前交付。易失状态没有变成持久状态。冻结检查器的旧字段 `event_preserved_after_reset` 只检查成功与存在复位，不能证明待发送状态穿过复位；[时序审计](/Users/depengsu/.local/share/bf-phase2-20261020/ordered-state-audit.json)保留原标签并说明限制，没有改动旧判据。

独立判决为 **REJECT_PROMOTION_KEEP_EXPERIMENTAL_ARTIFACT**：

- H0 已通过，单组成功对不能证明 H′ 提升成功率。
- H′ 的文字把首脉冲发送及 7.4–14 µF 写得过强；实际通过的 H0 22 µF、晚发送提供反例。
- H0 设计的计费上界估计为 0.0393375 USD，改进者加 H′ 为 0.0729432 USD，未建立相同总预算收益。
- 初始物理缓存快照未冻结为一致，确认门拒绝 `PARITY_INITIAL_CACHE_SHA256`。本组是描述性实际结果，不能作因果方法比较。
- H 提案原 episode 受宿主接口错误阻断，后续使用其模型文本有事后复核边界。

无方法推广、迁移、RSI 或硬件收益主张。实际父子方法、设备版本、执行输入、反馈范围、费用及拒绝原因均保留。

## 两个原始失败与新版本修复

| 原 episode | 实际请求 | 原始结果与责任边界 |
| --- | --- | --- |
| `p2-e5-001` | 6 | 首个表达式路径缺少 JSON Pointer 的 `/`；无效提案被计入唯一候选额度，模型实际生成的修正调用随后被额度拒绝。无原流程消费者成功。 |
| `p2-h-proposal-001` | 9 | **S0 宿主接口错误**：H episode 对外暴露 D 的 `check`，不支持的操作又占用 H 额度，随后真实 H 提案与 no-update 被拒绝。 |

两个 `INCOMPLETE_OR_STOPPED`、完整实际轨迹、费用和错误不删除、不重跑，也不回写为成功。使用已经生成的输出做事后复核，没有新模型提案。

新版本 `dispatch_adapter_v2.py` 将路径语法、示例和后端统一；H 接口不提供 D check；先验证操作、类型及语法，再计有效提案额度；语法/类型错误单独限额，合法 no-update 在提案额度用尽后仍允许。每个原故障各一个定向回归已通过，零 provider、零科学执行。新版本未部署到原 episode，不冒充真实 SDK 流程已通过。

## 执行、费用与资源

四个实际 episode 共 **25 次请求**，全部 SETTLED，无新 UNKNOWN；episode 累计墙钟 **348.744 秒**。固定费率的结算上界估计 **0.1766922 USD**，缓存感知估计 0.10124004 USD。它们不是发票金额；Codex 开发与判读介入非零且未计价，端到端总费用 UNKNOWN。Provider 报告别名为 `deepseek-flash`，独立权重版本未固定。

新增完整科学执行 **7 次**：4 个预注册静态网格、H0、H′、事后 E5 选中设计。5 个原有正反例复用，输入改变时重执行完整反馈；无新原生仿真、环境、工作树或整树备份。实际结果及失败轨迹保留于 `/Users/depengsu/.local/share/bf-phase2-20261020`。本批的两个 SDK 资格化尝试是软件连接检查，首次环境变量缺失失败也保留，未发生 provider 或科学请求。

原75条 S0请求，以及原生产、V2和历史账本、原十个 Pi 会话、独有实验与原有 UNKNOWN 的保存状态见 `preservation-final.json`。原论文正文、两份阶段一 PDF、共享样式与校徽保持冻结；本批新增两份独立阶段二稿件，未提交或推送。

中央清理窗口已经实测释放 **12,261,535,744 字节（12.26 GB）**，详见[存储报告](</Users/depengsu/Documents/Long-Horizon AI Agent/docs/storage-deep-clean-20261020/REPORT.md>)。本批最终可用空间、新增实际输出大小和 scratch 清理另见 `storage-final.json`；APFS 后台变化不算成本批释放。

## 交付与复核

登记 S0 的 `architecture-v2-ci` 实际 `./init.sh` 通过：343 项检查及 44 文件/11 控制读回。阶段二 43 个不同定向用例通过；首次 42 通过、1 个因 S0 漏合入 A 的 CLI 失败，补入该文件后仅重跑该失败用例，再完成这一次登记集成检查。原失败日志保留。新版本另有两个原故障定向回归通过。上述均未增加模型或科学请求，不代表根仓库全量或 worker 拒绝原生配置的健康状态。

两份新稿各 4 页，实际两遍编译、全部页面视觉检查通过；S0 分别读回 35 / 17 项稿件与证据绑定，未重复编译或生成新栅格图。原阶段一稿件与指定 Overleaf 项目保持既有版本，阶段二新稿仅本地保存。

- 机器实际结果：[actual-results.json](/Users/depengsu/.local/share/bf-phase2-20261020/actual-results.json)。
- H 独立判决：[method-retain-or-reject.json](/Users/depengsu/.local/share/bf-phase2-20261020/method-retain-or-reject.json)。
- E5 事后链：[result.json](/Users/depengsu/.local/share/bf-phase2-20261020/p2-e5-001/posthoc-adapter-001/result.json)。
- 本地稿件：[方法论文阶段二稿](</Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-s0-20261019/battery-world/papers/method-reexecution-20261019/phase2.pdf>)；[接口论文阶段二稿](</Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-s0-20261019/battery-world/papers/interface-sufficiency-20261019/phase2.pdf>)。

本批最终存储读数为 **22,142,779,392 字节可用（22.14 GB）**。私有实验产物为 2,907,596 字节，provider 目录逻辑增长 1,053,623 字节；两 worker 清掉本批可重建排版/预览文件 4,726,740 逻辑字节。全阶段可用空间变化包括 APFS 后台活动，不另宣称为清理释放量。历史中央清理的实测净释放量仍单列为 12.26 GB。

本批有限工作包以实际负结果、事后连接验证及拒绝推广结束，阶段二出口待审查。若继续比较，应注册独立的新版本、冻结相同初始缓存、采用同总预算及强静态对照；不得自动重试原失败 episode，也不扩展服务目标。用户已选择保留 A/R 失败基线，因此后续方法比较不依赖修改产品要求。
