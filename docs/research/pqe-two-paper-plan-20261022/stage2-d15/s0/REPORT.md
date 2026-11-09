# D15：公共边界修复与状态身份修复

本包 BF-PQE-S2-D15-20261022-001 / BFA-079，于北京时间2026-10-23完成实际两组执行。公共投影已先通过8项离线检查和B独立放行；两组随后从相同的公开失败初态自主选择状态保持，并得到4/4服务通过。完整阶段二未完成。

## 公共边界与来源

同一project_result用于adapter新出口、methods的last_result及history/evidence内嵌Result、pilot压缩/detail、共同初态、缓存和实际callback序列化。完整facts.receiver_identity及其诊断说明只留在私有assessment；合法public_check四字段、receiver_records、设备轨迹/活动/记录/包/能量保留。投影版本pqe-public-projection-v1独立记录来源对象hash和原result_sha256，幂等处理既存v1/v2，不改写旧执行身份。

原工程包的raw、assessment、受阻public文件及当时“暴露0”的BLOCKED记录都未修改。D15初态只是重新投影，新no-Agent数值0。五项科学消费者/评价器源码未改；methods仅公共边界函数变化，driver仅相应冻结文件hash更新，策略和driver逻辑AST摘要前后一致。只用1次薄实现修订和1轮8项检查，没有重跑旧8组件、3整链或全仓init。

实际6次provider wire的user JSON均精确等于保存的公共请求，未出现私有身份块/事件真值id/旧诊断说明。SDK只在system指令后附加专用participant工作目录，没有附加源码、私有评估或开发聊天。新出口和实际输入的放行边界都已记录，参见PUBLIC-RELEASE.json与execution-review.json。

## 两组实际行为

共同初态是开发者提供的原D15易失状态设计，服务2/4；完整合法域和九个Design变量全部开放，P没有人为收窄。两组获得相同Task、程序语义/成本资料、预算和合法工具；没有提供私有失败诊断或旧成功设计。

| 条件 | 自主选择 | 实际工具/数值 | 服务与停止 |
|---|---|---|---|
| strong_generic | 仅persistent_queue false→true | 1工具，1次新动态耦合 | 4/4 PASS后模型STOPPED |
| full_h | 同一持久性修改 | 1工具，精确复用前组同Task/Design/dt/五源结果；新数值0 | 同一已验证结果4/4 PASS后模型STOPPED |

每组仅生成一个候选，无未选候选、额外detail观察或合同错误纠正。第一组实际执行当前DoorProgram及动态供电；第二组复用标记和原始来源保留，不能说成第二次独立数值重复。没有跨Task复用D04名义结果，也没有为了纯投影变化重算旧初态。两次模型决策独立读取各自相同初态，full_h没有收到前组候选或解释；它选择同输入后，broker才给出精确缓存结果。

两组都从公开重启、SAVE、包序号与接收信息指出复位后身份重复，并选择已声明的NVM语义。generic结构化预测为UNKNOWN，文字给出4条接收的条件预期；full_h事前登记public_check.received_count≥4的局部预测，Update记录CONSISTENT、unique_cause=false。两者最终PASS均为模型自评，服务结论以独立评估和A读回为准。学习字段仍UNASSESSED/allowed_for_learning=false，没有H形成或G调用。

## 独立服务和状态证据

A只读取本次唯一新raw一次，独立核对CRC、事件真值、接收去重/顺序/截止、RAM/NVM/SAVE/ACK及能量代数，4/4通过。最大事件到接收延迟0.05666666667 s，TX最低2.2561323 V，峰值力0.00601691 N（约束0.5 N），能量闭合通过。

原始保存序号1,2,1,2变为1,2,3,4。两个reset仍在空队列IDLE，NVM分别保留seq=2/4，下一次BOOT读回seq=2；不同记录复用序号消失，同记录重传仍为0。该一次干预支持序号连续性修复；last_direction虽同时保留，其独立因果贡献未隔离，也没有在本轨迹中测试待发队列跨掉电或中断SAVE/ACK恢复。与先前已审初态回执比较，供电/能量/发送时序/掉电时点/力相同，反映的是预先声明的两模式相同保守成本模型，不是实测NVM无开销。

full_h复用键38a87a9ce35a769436702a8c5a5f3fd42f7162951dc6b266e07b930e4b968a4f对应完整冻结Task、Design、dt=0.001与五科学源。共同原始result_sha256为a400e701b2d38ce003c4356ee0f6c87703c199fde41da5747ff8c27866538d0d。模型结论引用的f0fa8135…与27b9bddb…是实际请求的公共registry对象索引，不是另一次动态结果。

## 费用与运行边界

总计6个模型请求、2个工具调用、1条新动态输入、1次精确缓存复用；原初态新计算0，native求解器/硬件0。输入75,670、输出9,603 tokens；现有缓存感知费率估算USD0.0342246（非发票），6笔均SETTLED，新UNKNOWN和未结预留0。开发会话成本非零，不在该研究账本内。

两个有限owner的token已撤销、grant/study过期，会话IDLE；临时per-owner预算设置恢复。原R11单请求UNKNOWN/null usage/USD0.2661324完整行保持不变，精确历史例外没有扩大，未重试旧请求。未花完的本包额度关闭，不补组、救援或转移余量。

## 阶段二剩余依赖

1. Design局部修复已分别在去抖、启动延迟和本次状态保持上发生；本包不再沿这些局部轴追加重复次数。
2. P合法编译/约束消费者可用，与Agent真正选择并执行P调整是两件事。本次两组P均不变，仅改persistent_queue是D编辑；仍缺在确有必要的任务中，P调整实际改变可执行行动及后果的证据。不能以未选P提案或分组改名代替。
3. 这是一题、每方法一次，且成功科学结果复用；不支持方法优势、统计比较、自动学习或迁移。H/G和正式对照不在本包授权内。
4. 上包几何/连通自定义网表可读并被消费者使用的范围保留；不是SPICE/厂商EDA、制造或物理资格，干涉/有限销接触与页面视觉仍未验收。本包没有再次尝试绕过浏览器限制。

后续由原审查根据这些实际缺口选择机制任务；不强制P正例，不自动开更多局部先导或正式矩阵。

## 交付与存储

统一结果见RESULTS.json；8项检查及实际序列化证据见boundary-check.json/boundary-evidence.json；两个episode目录保留模型原输出、wire、原始动态结果或明确复用来源、费用及停止记录。A/B最终独立复核和两篇短因果增量由对应回执绑定。

批前可用38,402,592,768 bytes，保留上限50MB、额外峰值估计300MB，原环境/工作区复用。没有新增备份、环境、commit/push或自动化恢复；本批清理释放0。最终实际文件占用和磁盘可用字节见postflight.json，不把后台全盘波动归为本任务新增产物或清理收益。

## 最终交付绑定

A回执 /Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/pqe-two-paper-plan-20261022/stage2-d15/a/A-RECEIPT.json，SHA-256 7738499065988d1f94eae2fcb0a277378452681224db13222039ff657de23bae；B回执 /Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/pqe-two-paper-plan-20261022/stage2-d15/b/RESULTS-HANDOFF.json，SHA-256 c7b66099acdd9de051909f414dc5690f74b98ab7c5ede16d73c42eff3bde87fc。两篇短增量已完成并由B回执逐项绑定，S0已读回正文、核对文件哈希和范围。有限包全部完成，完整阶段二保持开放；完成回报后不自动增加研究请求。
