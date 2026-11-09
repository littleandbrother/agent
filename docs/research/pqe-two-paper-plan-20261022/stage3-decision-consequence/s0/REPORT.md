# 两项冻结行动的动态后果：一项有效FAIL，一项有效PASS

`BF-PQE-S3-DECISION-CONSEQUENCE-20261023-001` / `BFA-086-pqe-decision-consequences`。两项已产生的固定H行动按原JSON精确数值执行，约11.94s；0新模型请求、0episode、USD0，2新数值、0精确缓存命中。旧六组对照保持封存，没有重选、调参、救援或追加输入。

| 已改变行动 | 原结果（直接复用） | 新输入与必要条件 | 新动态后果 |
|---|---|---|---|
| common_initial_r2_pool | 原8.5mm行程/8mm基圆越35mm包络；域无效、服务UNKNOWN | 改选原池合法阈值候选：100µF、ESR0.1Ω、启动1.9V/TX门限1.85V，保持6mm行程/8mm基圆；域有效 | 服务FAIL、接收0。64次boot/tx_begin及64次TX中brownout，只有1次capture/save，0完整包。 |
| after_r2_first_failure | 原8mm行程/6mm基圆压力角超40°；域无效、服务UNKNOWN | 保留470µF、ESR0.1Ω、启动1.9V/TX门限2.1V和8mm行程；基圆取JSON精确0.006919567294017877m；域有效 | 服务PASS、接收6。3次boot，capture/save/TX/wire/ACK各6，随后3次idle brownout。 |

第一项表明：必要条件筛查能排除原包络无效行动，但留下的合法动作未完成服务。动态轨迹显示反复在TX中掉电，不能因“启动了”或满足阈值/几何范围就称设备修复；联合改动不提供某一参数的唯一因果归因。

第二项补齐了既有缺口：当时公开状态→原池压力角违规→冻结Generate按联合可行区间改变基圆→精确新设计在动态源—供电—程序—接收链完整PASS。它支持这一个已见设计点的条件几何修复后果。旧域无效运行中的接收诊断不能当作有效服务基线，也不能由此给出强通用Agent优势、总体成功率或自动发现结论。

两项均使用原Task完整运动日程与物理初态，恢复当时Design/Problem后提交已保存行动；没有沿用旧电源波形、结束电压或固件快照。原动作及结果仅读回，未重求解。模型、方法及科学源文件保持冻结；独立评价与public_result一致。

本包直接验证了两项新调用/结果路径：Task与决策前公开状态匹配，行动精确等于冻结behavior-delta，新结果Design/Task/hash、raw完整性及独立服务判定一致。未新增资格、旧测试、全仓init/哈希或健康声明。费用账本总行数不变，旧R11 UNKNOWN/null usage/完整reserve SHA不变。

先前六组的控制调用节省结论不变。本补链没有新增自主模型选择，也没有运行失败后Update→下一轮Generate/Select；失败记忆守卫在真实自主闭环中的效益仍未回答。必要约束筛查是有限工程机制，不能单凭这两点构成论文的全部新意，更不能称学习H/G、RSI、强基线优势、未见迁移、统计或硬件资格。

所有结果无论正负均保留，本包在两项后结束。沿原环境与源树，约2MB产物、30MB上限；磁盘采样和资源收口见postflight.json。没有新增备份/环境/工作树、清理工单、commit/push，定时任务继续暂停，整体项目未完成。

证据：[两项结果](batch-result.json)、[冻结完整输入](frozen-inputs.json)、[直接验证与零费用审计](verification.json)、各executions子目录下raw/public-result/assessment；A独立review与B因果补段由各自报告目录绑定。原研究记录不覆盖，当前两稿只追加短补链结论。

独立收口：[A关系—动态—完整服务核对](../a/A-REVIEW.md)、[A凭据](../a/A-RECEIPT.json)、[B因果结论](../b/REPORT.md)、[两稿追加绑定](../b/PAPER-APPEND-BINDINGS.json)。A确认原物理初态能量均0，第一项全部64次掉电发生于TX/LOAD_TERMINAL_UVLO、最低TX端电压1.730045V；第二项最低TX2.054248V，3次掉电在IDLE，不影响已经完成的6次接收。私有评价仅作独立判断，未喂回方法。
