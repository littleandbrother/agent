# DOOR 工程与掉电恢复语义：有限包结论

总派发BF-PQE-20261022-001；本包BF-PQE-S2-ENGINEERING-20261022-001，BFA-078。原生工程、实际程序和有限验证已经交付；发现的新公共投影边界尚未修复，**当前v2结果不得送入新Agent实验**。本包没有付费研究请求或真实参与者暴露。

## 实际交付

同一100µF/负载支路5Ω/去抖60ms/持久候选，具有可编辑CadQuery源和STEP装配。7个具名实体经现有OCP一次导入均有效，包含固定安装件、门轴、凸轮、随动销和发电机包络。基圆7mm、行程8mm、凸轮外径34mm、安装包络60×35×20mm，规定角度0–90°。行程、基圆与实际换能源同输入；安装孔、壳体、有限销接触及内部发电机形状为展示布局。未完成实体干涉、强度、公差或制造资格。

连通电路包含5节点、9个typed元件：运动电势源、线圈阻抗、构造整流器、储能、漏电、限压、负载支路电阻、状态负载和供电观察。source-model.json与PQE-NETLIST 2无损往返，解析结果直接由同一consume_engineering_model消费。该网表是本装置原生模型交换格式，不是SPICE或厂商EDA工程；没有真实芯片标定。100→101µF只做一次参数传递读回，无新增求解或选型扫描。

第一项新代码回归直接读取A导出的source-model.json，原始结果嵌入对象与源对象相等，身份16355f20992dca0419a61a7c9f26e0b7dad47a1761055617e3ea4220580f61e9。工程文件确实参与数值输入。后续合法Design仍由同一网络生成并消费；未开放任意电路拓扑或固件代码生成。

原工程目录：workbench/bf-campaign-s0-20261019/battery-world/studies/pqe20261022/engineering/stage2/native/。原door-entry.html已接入v2默认候选、8组件、3整链和默认提交链，PILOT3八条事件链明确标v1，未新建页面。

## 实际程序语义

主求解器使用door_program.py的pqe-door-program-v2；新raw为pqe-door-result-v2。程序只接收当前触点、供电、上电后的相对elapsed和理想ACK可用性，不接收绝对仿真时钟、事件真值或离线边沿历史。

NVM布局为seq、last_direction和待确认queue。SAVE完成原2ms、3mA写入后原子提交序号、方向及队列；ACK再完成同样写入代价后才删除已确认队首。中断写入保留前一完整映像。pending、去抖状态、剩余操作、RAM与retry_due计时均随掉电清除；持久模式在新BOOT时装入NVM，易失模式从空状态启动。原2ms/1mA BOOT、6ms/15mA TX保留。两模式均付相同保守写入负载，没有凭持久选择产生节能收益。

原子提交是明确的构造模型假设，并非真实存储芯片耐断电证明。上电后重新读取仍存在的电平并付费捕获，不等于恢复半写事件；上电前已经消失的完整开关事件仍无法免费恢复。

## 有限结果

固定供电3.3V→0V→3.3V、1ms步长，61/62/69/70ms四断点事前冻结，对应SAVE半完成、SAVE完成TX前、TX完成ACK半写、ACK提交后。每断点持久/易失各一次，共8条，B预登记纯checker与A独立读回均通过。

| 断点 | 持久模式恢复 | 易失模式恢复 |
|---|---|---|
| SAVE前 | 未提交记录不存在，需重新捕获并完成写入 | 同样没有已提交记录 |
| SAVE后TX前 | 保留seq/方向/待发记录 | RAM清空；后续捕获是新记录 |
| TX后ACK未提交 | 原记录可重发，接收器不增加唯一服务数 | 重新捕获可复用原序号；与同记录重发分开 |
| ACK提交后 | 已确认项不复活，seq/方向保留 | RAM清空，重新捕获可能复用旧身份 |

每个中断SAVE或ACK仍支付1ms写负载；完整BOOT、SAVE、TX、ACK支付全时长。OFF阶段没有时钟前进或隐藏状态保留。外部接收器不随设备掉电清空。它们是人为注入的软件资格，不能当作自然门体供电故障结论。

四项H.Update直接检查通过：工具错误、模型域外、有效执行但服务失败、指定字段预测一致。固定H未修改，没有学习或方法优势。

| 新整链输入 | 独立服务 | 关键事实 |
|---|---|---|
| 原60ms名义候选，新程序 | PASS，4/4 | 最大接收延迟56.6667ms，TX最低2.256132V |
| 原70ms名义候选，新程序 | PASS，4/4 | 最大66.6667ms，TX最低2.255929V |
| D15一个易失身份初态 | FAIL，2/4 | 四次SAVE/TX/ACK均完成，但第二次自然上电产生的新记录复用seq1/2，被原接收器去重，遗漏事件3/4 |

D15两次掉电均在IDLE且队列为空；同记录重传0、不同记录同序号2、方向冲突0。因此它是跨启动的记录身份复用及有效服务丢失，没有证据把它归因为TX欠压、SAVE或ACK中断。没有为D15运行修复或扫参。

两个名义输入的Task/Design与旧raw相同。第一周期接收不变，第二周期提前1ms；相对上电时钟取代大绝对时间后在原1ms网格上消除了原先的一个步进延后。源/负载能量差约1e-10J，独立能量容差与反力约束仍通过。旧70ms raw的2.405909V字段只有步前采样；原Stage1 reassessment.json已纠正步后受载最低2.25590865556V，新2.25592898894V与该口径相近，不能解释成0.15V供电退化。旧raw不改写、旧程序不重跑。

## 收尾review发现的开放边界

新public-result.facts.receiver_identity包含4处host-only preceding_truth_event_id。固定H公共投影保留facts，因此未来若直接发送会把独立真值关联带入参与者上下文。S0/B已确认，记录PUBLIC-RELEASE-GATE.json：BLOCKED_FOR_NEW_PARTICIPANT_EXPOSURE。本包研究模型请求0，所以没有实际模型暴露；不声称当前公共投影已正确隔离。

本包两次有理由实现修订已用完。第一次提取程序和统一模型消费者；第二次修复有限runner的精确参考输入表示：计划整数5与旧参考浮点5.0物理值相同但内容哈希不同，在第二整链调用前停止。原中断与protocol保留，reference-literal-amendment.json恢复精确旧literal，resume仅继续未执行的第二名义和D15，未重复8组件、4测试或第一回归。科学源、服务阈值没有因该修订改变。

依有限工单，不暗做第三次实现或改写原结果。下一必要动作是薄公共投影修复：私有诊断保留完整真值关联，公共面删除独立真值派生字段，并用已有保存结果做直接边界检查；不需要重复8组件或3整链。

## 阶段二一页交接

| 项目 | 本次已具备 | 仍缺的实际交付/证据 |
|---|---|---|
| S2-01/02 | 参数源、STEP、安装/运动尺寸与同参数换能源；规定运动下反力和能量 | 实体干涉/有限销接触未验；并非制造或自由动力学资格 |
| S2-03 | 连通原生模型网表与主求解器实际读取同对象 | 厂商电路/PCB/实测器件不在本包 |
| S2-04 | 实际RAM/NVM程序、带代价SAVE/ACK、无免费时钟的恢复；8组件正反例 | 任意程序/事件保持器的生成与消费未演示 |
| S2-05/06/07 | 原独立真值、CRC/序号去重、截止/能量判定保留；2名义与1自然D15已区分 | 新公共投影仍泄漏真值关联，修复前禁止研究参与者读取 |
| S2-08至11/13 | 前三先导已有固定Generate/Select/Update调用轨迹；本包4条Update直接语义检查 | 真实合同纠错尚未触发，不能将软件检查变成新方法收益 |
| S2-12 | P字段可限制合法候选，D15初始P公开完整变量域 | 无实际Agent重构P后消费并改变后果的证据；只改persistent_queue仍是D编辑 |
| S2-14/15 | 历史有限先导保留；本包和PILOT3统一时间链数据接入原页 | 页面视觉/交互未验收；单例不构成统计优势或跨题迁移 |
| S2-16 | 两稿短增量登记程序/复位/服务因果与装置缺口 | 没有H/G形成，完整阶段二未关闭 |

当前先修公共投影，再由审查选择真正需要P解锁或程序消费的有限任务；不强制P改变、不自动开第四轮付费先导/F1/G。

## 资源与验证边界

最终共8组件轨迹、3新整链、4项Update测试；研究模型请求0、native求解器0、硬件0。CAD一次生成与STEP读回不是科学求解。Codex/操作员开发审查成本非零，未作为研究费用定价。A/B回执和两稿在同包相邻目录及canonical papers/pqe20261022/，收尾绑定见RESULTS.json。

入场40,720,539,648字节，保留上限100MB、额外峰值500MB，原环境复用。无新备份/环境/工作区、commit/push或自动化恢复；本包未修改旧费用/UNKNOWN，新增清理释放0。实际产物与最终可用空间见postflight.json。

工程页通过静态HTML链接/ID、Python AST、SVG XML、JS语法和限定diff检查。浏览器URL安全策略拒绝file://页面访问，本轮未绕过该限制；没有完成页面视觉或交互验收。STEP可导入与源码可打开也不等于实体装配或制造验收。未运行全仓init，不作全仓健康声明。

## 最终交付绑定

A独立工程/状态回执：/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/pqe-two-paper-plan-20261022/stage2-engineering/a/A-RECEIPT.json，SHA-256 3b7f752a1ca8af3a65c28daac10a8871106ebcd174c115ebdbbf551ec5e25c9e。B事前语义、结果复核与两稿回执：/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/pqe-two-paper-plan-20261022/stage2-engineering/b/RESULTS-HANDOFF.json，SHA-256 cb01c06883fa9ef334a7c27f6175b85bfa17ada24b104954aee204b387926774。S0已核对两份最终回执、事前语义、科学源绑定及论文/页面文件身份；本轮收尾没有重跑组件、数值输入或测试。

两篇增量分别为 /Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-s0-20261019/battery-world/papers/pqe20261022/paper1-stage2-engineering-increment.md 和 /Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-s0-20261019/battery-world/papers/pqe20261022/paper2-stage2-engineering-increment.md。源码修订与公共边界原样保留，有限包关闭不等于新参与者就绪；完整阶段二仍为未完成。
