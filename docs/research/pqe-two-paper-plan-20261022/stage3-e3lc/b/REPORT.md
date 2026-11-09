# E3LC B 最终公开证据报告

工单 `BF-PQE-S3-E3LC-20261023-001`，feature `BFA-084-pqe-e3-scope-lc`。B 的实现、公开读回、逐格分析与两稿增量已完成，交 S0 总账与根状态封口。B 没有启动测试、Agent、provider、科学/native/hardware 执行，也没有提交或推送。

## 结果与解释

一个暴露的 DOOR 机制开发任务、两个独立模型上下文，共八次求解。B0、B3、B0-SM 各 2/2 完整服务 PASS，B3-NR 各保持初始 FAIL 后局部停止，合计 0/2。普通 B0 两次都实际扩大并使用了范围，所以“离开初始 cap/ESR 范围有用”与“特定 B3 方法独有/稳定更优”必须分开。

所有费用为固定费率下的实际已知用量估计，非账单金额。首次可行列包含到第一次正常完成、模型域有效、完整 public PASS 为止的所有模型请求/纠错费用；总费用另含自主收尾。未达到首次可行用“未达到”，不把 0 次评价写成零成本可行。

|上下文/条件|最后完整服务|评价/新科学/缓存|首次可行请求 / USD|总请求 / USD|
|---|---|---:|---:|---:|
|r1 B0|PASS 6|4 / 4 / 0|9 / 0.1411242|10 / 0.1594149|
|r1 B3|PASS 6|1 / 1 / 0|2 / 0.0305979|3 / 0.0391695|
|r1 B3-NR|初始 FAIL 0，局部停止|0 / 0 / 0|未达到|1 / 0.0136341|
|r1 B0-SM|PASS 6|2 / 2 / 0|5 / 0.0712437|7 / 0.0930561|
|r2 B0|PASS 6|2 / 1 / 1|4 / 0.0327297|5 / 0.0428103|
|r2 B3|PASS 6|3 / 3 / 0|6 / 0.0893883|7 / 0.1056663|
|r2 B3-NR|初始 FAIL 0，局部停止|0 / 0 / 0|未达到|1 / 0.0131289|
|r2 B0-SM|PASS 6|4 / 4 / 0|8 / 0.1171689|9 / 0.1335783|

DOOR 合计 43 次请求，全部 KNOWN，估计 USD **0.6004584**，无本批缺失用量或未结预留；17 次工具动作中 16 次评价、1 次无新评价的 report，含 15 个新科学输入及 1 次 exact cache。首次可行的评价数在 r1 是 B3 1 对 B0 4，在 r2 是 B3 3 对 B0 2；请求数相应为 2 对 9、6 对 4。汇总 B3 较低费用不能消除第二上下文的反向结果。

## 实际范围与动作

Task、初始 Design、科学语义、服务、权限、暴露路由和单次上限共同冻结。初始 Problem 则有明确干预：B0/B3/NR 仅 cap/ESR active，其他值暂时 fixed；SM 初始全部九个顶层 Task 设计字段 active 且 fixed_choices 为空，不注入参考数值。不能写成所有初始 P 相同，也不能把 SM 的全范围称为与每条 B3 实现后的 P 完全相同。

|条件/上下文|实际消费与使用的范围|
|---|---|
|B0 r1|首次输入扩展电源与机构范围并移除相应 fixed choices；后续几何修改继续使用已开放范围。两次域无效、一次域有效服务 FAIL、最后 PASS。|
|B0 r2|首次输入开放全部 Task 字段；实际变化的是 C、ESR、startup、tx_gate 与机构行程，其他补丁中重述的未变字段不算实际修改。首次域无效 exact reuse；第二次几何修改后 PASS。|
|B3 r1|只新增 mechanism active 并放开其 fixed choice；同一输入把 stroke 6→7.5mm、ESR 5→0.1Ω。C 保持100µF，startup/tx_gate 均保持2.9V。完整 PASS。|
|B3 r2|新增 mechanism、startup_v、tx_gate_v active 并放开对应 fixed choices；实际 C100→390µF、startup2.9→1.9V、tx_gate2.9→2.1V、ESR5→0.1Ω、stroke6→8.5mm。该输入域无效；第二次 C470µF 与几何修改仍域无效；第三次 stroke7.5mm/cam7mm 后完整 PASS。|
|B3-NR r1/r2|0 动作；保留 cap/ESR 初始范围，均明确只作局部 FAIL 停止，没有 Task 全域无解结论，没有策略偏离。工具权限未被宿主收窄。|
|B0-SM r1/r2|初始已给全 Task 范围；实际改动电源与机构字段，r2 另改 retry。无需运行时范围扩展；分别经过2、4次评价后 PASS。|

B3 r1 GEN 提供3个候选、消费选中的1个；r2各轮提供4/3/4个候选、各消费1个。没有额外实际 observe。此前 `FIRST-CONTEXT.md` 的“没有额外观察或多候选竞争执行”应精确解释为“没有额外观察，也未逐个执行全部候选”，不能解释成没有生成/排序多个候选。本最终报告与 `DOOR-SUMMARY.json` 是完整分析的准据，早期四格便笺及其原哈希保留。

两次有效的 B3 UPDATE 都为局部 CONSISTENT、unique_cause=false。r1 选中预测仅 received_count≥1；r2 前两次域无效均为 DOMAIN_UNKNOWN，最终选中预测仅 model_valid=true。它们不构成完整服务的事前联合预测或唯一因果识别，完整 PASS 依实际公共检查另行成立。

## 失败、采用与排除分类

16 个 DOOR 已评候选中，8 个模型域无效（assembly envelope 5、cam pressure angle 3），虽均收到6条模拟消息仍保留 UNKNOWN；2 个域有效但服务 FAIL、接收0；6 个域有效且完整 PASS、接收6。不能把前8个写成服务成功，也不能把模型域不足混同为工具执行失败。

两次公开输出契约纠错分别是 r1 B0 的 EDIT_OUTSIDE_ACTIVE_VARIABLES 和 r1 SM 的 READ_ACTION_HAS_EDIT；原响应/费用保留，均未执行科学输入。r1 SM 的最后 report 为 NO_EXECUTION/无新评价，不会把之前完整 PASS 改成实际服务 UNKNOWN。逐格对照模型结论、最后已完成有效公共服务与明确 scope：错误采用0，未支持的 Task 全域排除0，NR 消费后的策略偏离0；无据此剔除、替换或追加求解。

## 冻结传统参照

OPT 实现 SHA `371a98fcb647feccb2b2ed7d1eb3fb75db2a05888419fcb986d7ecd19c1ffe36`，协议 SHA `05a23866ac9532fb35cdb5a4e5293a44501ca6788f1deb6112385e46e85d87f9`。S0 使用原始公共初始 Design 和合法盒中点两起点、每点6评价；公开完整范围预先给定，9个连续坐标受支持，布尔 queue 与非设计字段固定，无私有或参与者参考数值，执行后未调步长/顺序/评分。

|起点|评价/新科学/缓存|最优公共 score|停止|完整 PASS|
|---|---:|---|---|---:|
|public initial|6 / 5 / 1|[1,1,0,0]|EVALUATION_CAP|0|
|legal-box midpoint|6 / 6 / 0|[1,1,0,0]|EVALUATION_CAP|0|

12个评价全部正常完成、模型域有效、服务 FAIL（接收0），11个新科学输入及1缓存，0模型请求，公开执行 wall_s 20.4920。逐一比对 `opt-result.json` 与12个公开 compact 的 Design/Problem/输入和结果引用/有效性/服务；冻结脚本和协议当前字节哈希匹配。只支持“该确定性有限参照未在12次内求解”；未遍历所有坐标/连续域，不是全域排除或一般算法失败。

## 唯一新 LC H0

只读取 S0 明确交付的 `lcpv-h0/episode-result.json`、`method-transcript.json`、`actions/01/public-compact.json` 三件。实际参与者 Task 来自 transcript.initial_state.task。24h服务保持：最多60s采样、23400..66600的12h黑暗、66600恢复后120s内即66720前交付旧历史、网关可用时新采样按真实采集时间10s内接收；内部指定空气点温度误差≤0.5°C、时间误差≤60s，未知时间和缺采样不能凭标签通过。固定构造世界使用1s积分。

初始正常/域有效，接收1162，完整服务 FAIL 的四项为 CONTINUOUS_SAMPLING、DARK_SAMPLING、ALL_PRE_RECOVERY_UNACKED_HISTORY_BY_DEADLINE、FRESH_RECEIVE_FROM_ACTUAL_ACQUISITION_TIME。默认 H0（strong_generic）生成并选中一次 edit：

|字段|初始→执行后|类别|
|---|---|---|
|area_cm2|25→50|供能设计|
|capacitance_f|0.012→0.04|储能设计|
|esr_ohm|8→0.1|储能设计|
|startup_v|2.5→2.3|电源设计|
|nvm_capacity_records|2048→4096|存储设计|
|sample_period_s|60→59|程序参数|
|ack_spacing_s|0.25→0.001|程序参数|
|brownout_v / persistent_records / retry_s|2.2 / true /45，均未变|未变值|

执行后正常、域有效、完整 public PASS，received_count=1441，无 failures/unknown。公开精确计数为 sample/save_commit/ack_commit 各1441、clock_sync两次、无 brownout 项，pending_count=0；聚合 boot 耗能10µJ。Task hash、科学 sources、program_version、engineering_model_sha256、Problem 在初始/动作结果保持一致；transcript动作结果与独立 compact 的 Design/域/完整服务一致。只改了真实设计及程序参数，固定程序语义、服务/evaluator未改，没有生成代码加载；多个参数一起改，不能识别单一参数原因。

首次可行2请求、USD0.0287169；含模型自主停止共3KNOWN请求、USD**0.0351039**，1工具动作/1评价/1新科学输入，无契约纠错/缓存/native/hardware。其局部 PASS 结论与实际公共服务一致。此次 LC 的初始科学输入另计1，不混进 Agent 动作数。

该任务是新暴露开发实例，allowed_for_learning=false；不是此前4个无Agent资格输入，不是未见F2，也不是把五组方法复制过来的迁移评价。构造的光谱/PV/PMIC、付费活动、断电时钟、SAVE/ACK与空气点热惯性链的有限服务成功可成立；没有实测器件、硬件或统计丢失率结果。1s构造世界的有效结果无需被另加资格门槛抹除。

## 交付、成本和边界

本批9个 Agent episode 合计46个 KNOWN 请求，USD **0.6355623**、无本批 UNKNOWN/未结预留；DOOR/OPT/LC动作新科学分别15/11/1，另有本批 LC 初始1。私有资格/DOOR初始与全批科学总账由S0独立封口，B未读或自行补算。历史 UNKNOWN 不因本批已知用量而消失。

两稿：`paper1-stage3-e3lc-increment.md` 写实际范围干预与有限 OPT；`paper2-stage3-e3lc-increment.md` 写固定方法行为与首次 LC Agent 因果材料。原 F1 未采用结论保留；本批没有 H/G formation/adoption/learning、未见任务稳定迁移、RSI收益、native或硬件验收声明。

B 只做 JSON/哈希/静态 AST 和已授权公共读回分析；首四格从已绑定缓存复用，更新索引只新增r2四格，未重读首四原件。没有读取 private/lcpv-private、raw、assessment、A报告、参考设计/资格证明、LC host/protocol/input。当前来源别名在所有46个回调一致：`deepseek/deepseek-flash;profile=engineering-reasoning-active-context-v4;thinking=enabled/high;upstream-weights=unreported`，不声称上游权重已报告。

S0执行的薄入口检查以及唯一失败夹具修复详见已有 `TEST-FIXTURE-AMENDMENT.json`；B没有重跑。冻结 conditions保留修复前测试SHA，修复后的测试SHA由amendment绑定，不回写冻结条件。此交付不代表B独立运行了root init或完整仓库健康检查。S0负责根 feature/progress/handoff、完整账本、生成物/存储复核及最终封口；不自动进入新一轮实验。
