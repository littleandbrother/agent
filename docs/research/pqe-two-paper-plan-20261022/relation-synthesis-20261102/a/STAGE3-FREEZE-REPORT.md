# 第三步事前任务冻结（仅 A/S0）

DOOR 与既有合格 LC-PV 消费者各冻结三个新工况，六份初态均未执行。S0 是唯一初态执行者；每工况最多一次、共最多六次。任何初态 PASS 均保留为正确停止控制，不换题。

| 族 | 工况 | 机制角色 | 初态 |
|---|---|---|---|
| DOOR | local-repair-control | local-repair/complexity-control | NOT_EXECUTED |
| DOOR | cold-contact-challenge | natural cold/source/contact challenge | NOT_EXECUTED |
| DOOR | link-recovery-challenge | natural transport challenge | NOT_EXECUTED |
| LC | local-repair-control | local-repair/complexity-control | NOT_EXECUTED |
| LC | light-before-link-challenge | natural recovery/queue challenge | NOT_EXECUTED |
| LC | link-before-light-challenge | natural retained-energy challenge | NOT_EXECUTED |

DOOR 使用既有 CODEBT 共同固件/保持组件接口及原连续机械源、力/空间/能量门与完整服务评价器；没有新源模型或策略分支。三工况使用原 task 模块默认设计，原零能量初态和合法域不变。这里只改预定运动、断联时序与任务标识；没有通过阈值搜索制造需求。

LC 绑定已有合格的单储能光谱二极管/PMIC 消费者、原 stdlib 独立评价器与严格 24h/12h 暗期服务。Profile、平面默认 Design、程序优先级、时间/温度目标、初始能量与动作域保持原样；只按自然旅程改变光照/遮挡、暗期/断联和相应恢复时刻。热真值只留 host，参与者任务仍由原 participant_task 生成。没有引入新 RTC、split store 或调度器。

两族各有局部修复/复杂度控制以及挑战条件，选择依据是服务机制，未运行或查看本轮 G/D/R 输赢。规则在任何第三步数值执行前固定；B 第二步算法冻结前不得读取本文件、manifest 或任务。

公平执行接口：同一整套设计同时通过三个原服务门合取才算成功；不拼接不同设计结果。共同初态之外，每方法每种子6个候选/18个工况评价槽，精确复用仍耗候选和评价槽；初态 PASS 条件不能被无偿更换。2族×G/D/R×2种子各自协议由 S0 绑定，是否执行取决于第二步语义激活门。

复杂度分别报告实际修改字段、组件、源面积/储能及测得能耗，不合成虚构加权分。遇到 LC 原接口无法表达，只记录具体 NOT_RUN_INTERFACE_GAP，不替换为 DOOR 或改科学语义。

检查：新增2项必要静态软件检查（DOOR 原接口/运动/服务，LC 原 host-public-Profile 绑定及全部引用读回），新增1次静态几何真实 miss，0 full、0模型。累计A=6full/6.740417581982911s、2cheap、4software、0模型；见 RESOURCE-TOTAL.json。初态和动态 model-valid/service 均 UNKNOWN_NOT_EXECUTED。

Manifest: stage3-host/MANIFEST.json；规则: stage3-host/RULES.json；检查: stage3-host/CHECKS.json。阶段1 counter 保留原逐字节收据，总资源独立放 RESOURCE-TOTAL.json，绑定修正说明见 RESOURCE-BINDING-AMENDMENT.json。

复现/审计入口：freeze_stage3.py 只构造和静态绑定，拒绝覆盖既有冻结目录；本包不可直接重跑。原消费者源哈希在 manifest 内，S0 运行前应绑定同源共同执行入口，不调用旧活跃 host/owner/deadline。
