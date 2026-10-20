# D/H 起步候选与真实执行状态

起步候选及历史/本批状态；12 项 D 和 6 项 H 不等于 18 项新实验。当前批次关闭，不自动扩大。

| 候选 | 改变 | 当前证据或反证 | 状态 |
|---|---|---|---|
| D01 | 增加 A/R 储能容量以覆盖暗区 | 12h 暗区仍漏采样；不能把保留旧记录当持续服务 | PROPOSED_NOT_RUN |
| D02 | 降低 A/R 暗区采样频率 | 能量与服务频率有取舍；必须先冻结新服务要求 | PROPOSED_NOT_RUN |
| D03 | 易失记录改为非易失记录 | 170 条耐久记录保留；易失路径丢 121 条，暗区新采样仍失败 | EXECUTED_PARTIAL_GAIN |
| D04 | 恢复上传时新鲜数据优先于旧 FIFO | 现行恢复排队使一条新样本等待 30s，违反 10s 新鲜度 | PROPOSED_NOT_RUN |
| D05 | 显式保存缺口及恢复状态 | 缺口必须被报告；记录保持不等于时间已知 | PROPOSED_NOT_RUN |
| D06 | 增加有独立依据的跨掉电时间基准 | 当前时钟连续性 UNKNOWN，不能靠软件字段宣称已知 | PROPOSED_REQUIRES_PHYSICAL_ANCHOR |
| D07 | 相同能量下改变储能 ESR | 150uJ 低 ESR 通过，高 ESR 失败；能量标量不足 | EXECUTED_PASS_FAIL_PAIR |
| D08 | 易失事件位改为声明的被动保持机构 | 掉电后的事件保持分化；未添加额外释放能源，机构尚未实测 | EXECUTED_PASS_FAIL_PAIR |
| D09 | 改变储能钳位拓扑 3V/5V | 当前 10uF 条件同结果，合法容量修改后分化 | EXECUTED_INTERVENTION_COUNTEREXAMPLE |
| D10 | 储能从 10uF 改为 4uF | 3V 结构只能供 16uJ，5V 可供 30uJ；是相同合法干预 | EXECUTED_INTERVENTION_COUNTEREXAMPLE |
| D11 | 在固定电源板上修订采样和发送排程 | 三份固件同版计算交付；第四份执行后资格检查未完成 | EXECUTED_THREE_DELIVERIES_ONE_RESOURCE_STOP |
| D12 | 为绕过不可行任务而放宽固定有效窗口 | 历史 8ms 与公开最低采样/发送时间冲突；修改检查器不是合法设备修订 | REJECT_OUT_OF_SCOPE |
| H01 | 先核对约束、时间起点与反馈依赖，再修订并比较 | 实际 H1，两次交付；对照末轮因资源中断，默认方法不变 | EXECUTED_TWO_CONFIRMATIONS_NO_PROMOTION |
| H02 | 固定丰富观察替代只有当前判决的摘要 | 固定丰富、全原始、可执行动态均 4/4；未运行模型表达收益实验 | QUALIFIED_INFORMATION_CONTROL_ONLY |
| H03 | 按精确输入与依赖有效性复用物理响应 | 6 项控制均与完整响应一致；反馈条件退化为完整重算，无独立加速 | QUALIFIED_SYNTHETIC_ONLY |
| H04 | 阶段恢复时绑定归档原文、版本与当前源码 | 来自 BFA-043 长会话恢复；本批四轮均零旧轨迹起步 | HISTORICAL_EXPERIENCE_NOT_NEW_COMPARISON |
| H05 | 由单主设计者改为有界专业委派 | 已有组织先导不足以给通用收益；本批只用 single，不启动新多 Agent 条件 | HISTORICAL_ONLY_NOT_DISPATCHED |
| H06 | 只有可证明状态适用时从局部边界继续 | 全局提示必须从任务入口重启；局部继续需另证，本批未作局部 H 实验 | QUALIFIED_TYPED_RULE_ONLY |
