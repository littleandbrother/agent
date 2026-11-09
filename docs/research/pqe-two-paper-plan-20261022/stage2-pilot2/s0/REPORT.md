# PQE 第二阶段第二包：D04 共同响应预算修正后配对

总派发 `BF-PQE-20261022-001`；本包 `BF-PQE-S2-PILOT2-20261022-001`；特性 `BFA-076-pqe-door-response-budget`。两格已各执行一次并关闭，A/B独立回执已完成。full_h 从公共 Task 选定一次合法局部设计修改，真实消费者公开检查 PASS，随后模型给出限定范围的最终自判；strong_generic 的完整 JSON 因只读动作夹带设计修改被拒绝，未执行。**完整第二阶段仍未完成**，本包不与上一协议四格拼接统计。

## 实际结果

| 条件 | 请求 / 工具 / 新数值 | 输出 token | 费率上界估算 USD | 实际路径 |
| --- | ---: | ---: | ---: | --- |
| strong_generic | 1 / 0 / 0 | 25,419 | 0.0312342 | 完整 JSON → 唯一候选被拒 → INSUFFICIENT_EVIDENCE；NOT_ASSESSED，无自判 |
| full_h | 3 / 1 / 1 | 7,191 | 0.0130440 | 两候选 → Rank 选 edit → debounce_s=0.06 → 公开 PASS → Update → STOPPED/PASS 自判 |

合计 **4 个真实 provider 请求、1 个工具调用、1 次新数值、USD 0.0442782 费率上界估算**；17,154 输入 / 32,610 输出 token，episode 墙钟合计153.101秒；唯一工具数值执行约1.311秒。四笔全部 SETTLED，新增 UNKNOWN 和未结预留均为0。费用沿用原账本锁定费率，不是供应商账单。Codex/宿主预算实现、组织和独立审查成本非零，未货币定价；没有人工改写参与者答案、补跑、续写或额外付费探针。

四个实际 provider wire 和 SDK 都使用 `max_tokens=32768`，原 high/thinking/temperature0.2 保持。响应均正常 `stop`，有公开 JSON；没有 length、传输失败或解析错误。真实 completion_tokens 分别25419、6107、420、664，均未到各请求上限或每格累计131072。共同输出容量在本包实际请求上可用，不等价于对所有远端请求的能力保证。

## Generic 的具体停止原因

唯一候选 `obs-c500-start22-tx21-deb01` 声明 operation=observe，同时 design_patch 提议改变电容、发送阈值、去抖及机制字段。固定公共合同明示 observe/verify/report/select 不得修改 Design，因此原 H-GEN 候选检查返回 `READ_ACTION_HAS_EDIT`，候选集合为空后使用原状态名 `INSUFFICIENT_EVIDENCE` 停止。这里具体原因是**动作合同违反**，不是已经证实物理服务失败，也不是响应长度或科学资料缺失的结论。

未运行 Rank、工具、Update 或最终自判；初始 Design/Problem 保持不变。保留模型原始公开候选和费用，不将 observe 改写成 edit，也不代它补写结论。其他潜在输入问题没有执行验证，不能将未检查的后续约束算成真实失败。

## Full H 的实际闭环和边界

首次 Generate 提供两个候选：观察当前设计与设置去抖0.06秒的 edit；两者事前预测都是 UNKNOWN。Rank 选择 `c1_debounce_repair`，依据公共 Task 中 stable_s=0.06、接触抖动延续到0.048秒以及当前debounce_s=0。未选候选为 `c0_baseline_observe`。只有去抖从0改到0.06，其他Design字段和Problem均未改。

此选择发生在**本格首次工具反馈之前**。它证明模型依据公共任务事实选择并消费了局部修改，不能描述为先观察本格失败、再由反馈触发修复。没有把上一包诊断、私有参考0.07秒答案或开发聊天加入参与者输入。

一次真实执行产生4条持久记录、4帧与4条接收，公开检查 PASS；结果进入固定 H.Update，下一次 Generate 明确 STOPPED/PASS。模型解释引用了完整公开服务状态、四次开闭捕获/接收、发送电压、反力以及队列为空时的IDLE掉电，并把结论限于当前86400秒构造任务。最终自判来源是模型公开 JSON；不是宿主代写。没有单独的 report/select 工具提交，最终状态由 STOPPED conclusion 关闭。

实际 Rank 比较了两个候选；Update 确实消费新结果。两候选预测均为 UNKNOWN，不能据此声称完成定量预测反驳或明确因果假设更新；P活跃变量、固定选择与分组均未变化，H/G形成均0。一次局部正例和另一次合同失败不建立方法优势、统计收益、重构必要性或未见迁移。另一个未选观察候选把“超过两个事件ID”列为异常，但当前Task包含四次开闭转换；该分支没有执行，其错误阈值仍保留，不能从最终PASS推断所有候选语义都正确。

A独立读回唯一新raw确认 **PASS / 4个真事件全部匹配**：无漏报、伪报或重复，独立真事件到接收最大延迟57.67ms（截止2s）；TX受载最低2.256112V，较1.8V欠压阈值有0.456112V裕量；把手附加力峰值0.006017N，小于0.5N。机械与储能闭合残差均在原容差内，未重跑求解器。模型自判与本次构造结果一致。解释需区分：tx_gate_v=2.2V是TX启动时电容门限，持续受载供电按brownout_v=1.8V判断；捕获到接收的短延迟不替代真事件到接收的截止检查，后者已由A独立核对。两次空队列IDLE掉电不证明待发数据跨复位恢复。B公开行为/预算审查完成，26个源码/公开证据绑定核对无不一致；原始JSON、候选、Rank、实际消费者输入、Result、Update及最终自判保持对应。真实四请求均未触发紧余量裁剪或越界拒绝，这些边界由本包离线检查覆盖。

## 资源入口、隔离与关闭

本包仅前瞻参数化公共资源入口。旧默认4096/49152及旧冻结协议保留；新协议32768/131072依次贯通 EpisodeDriver 的Generate/Rank、实际request.max_output_tokens、SDK模型cap、网关、provider wire/预留及实际usage。每次按 min(32768, 累计剩余) 发出，零余量不派发；同一次next的Generate与Rank不重复授权余额，超本次或累计授权保留原usage并硬停。相同模型、科学源、Task、固定H策略、工具schema、公共投影和分页保持不变，全服务默认预算未改。

一次集中离线边界检查8项通过，包含真实Pi SDK对模拟provider的32768请求、余额裁剪、越界拒绝、旧协议读回和driver硬停。0付费格式探针，未重跑旧55项/装置资格/全仓init。原初态精确缓存已登记，但两格均未选择该观察，**实际缓存复用0**；唯一修改输入为新数值。

4次provider权威wire与本次公开消息逐条一致，实际cap、high、temperature一致。每个Pi callback是干净会话，工具列表/初始历史为空；模型无法调用shell或宿主文件，固定可信H仅消费JSON。参与者输入未混入私有参考、最终评估器或开发聊天；审查不读取或引用私有reasoning。

2个新owner均有限USD4 grant，共同study USD8；结束后grant关闭、token撤销、study过期，临时per-owner预算模式恢复原缺省。四笔预留均按实际wire字节/输出额度复核相符。旧R11 `llm-1de4d60d9bc93d257392` UNKNOWN、null usage和USD0.2661324预留整行身份不变；新缺usage仍阻断。新源码冻结绑定未变，旧协议未覆写，自动化维持暂停，无commit/push。

## 下一依赖与存储

首要响应截断阻断在本包4次真实请求中未出现。后续由原审查选择真正不同机制/实质问题重构的有限任务，另行考虑是否需要反馈驱动的第二次设计改变证据；不自动翻倍cap、换模型、修正generic后补跑、扩大矩阵或进入F1/G。D04为已见开发题，本结果不外推到未见任务或硬件。

复用既有源码、服务、Pi SDK和依赖；无新环境、工作区或备份，原失败与完整必要费用保留。新产物/字节和可用空间以 `postflight.json` 为准。本包释放空间0，此前34.17GB退役收益不重复计入。

证据入口：`RESULTS.json`；`episodes/<cell>/method-transcript.json`、`episode-result.json`、`callbacks/*/{input-public,wire-public,callback-result}.json`；唯一新raw在 `episodes/d04-full-h/actions/01/`；独立回执在 `../a/A-RECEIPT.json` 和 `../b/RESULTS-HANDOFF.json`。新协议为canonical APP的 `studies/pqe20261022/shared/pilot2-protocol.json`。两格已执行，**不要再次运行本包run命令**。
