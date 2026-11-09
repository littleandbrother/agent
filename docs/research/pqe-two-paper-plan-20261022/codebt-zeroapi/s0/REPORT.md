# 零 API 定点验证包出口 — BFA-098

派发 `BF-PQE-CODEBT-ZEROAPI-CHECK-20261024-001`。有限检查完成；方法科学比较仍未准入，项目尚未完成。

只改持久身份已使三个原工况全部通过完整服务。原 Debt 所选联合候选保持原样时全部有效失败，各只接收1条。当前三题不支持“必须新增保持器”的主张。没有可信的机制II单条件被事前冻结，未扫参数、未凑联合方案胜出。

身份分支已修正并经过保存事实的实际 GSU 读回。缺捕获分支仍有实质缺口：软件负例下一动作是 holder 关闭时修改 `holding_capacity=1`，不能称有效捕获修复。原关闭的真实 host 尚未加载新公开桥和 DSML normalizer；12项软件检查通过不构成重开付费比较的条件。

## 原工况实测

各格为原完整服务判定 / 有效接收条数；新运行另列子进程实耗。六个新结果均 model-valid，原父三结果精确复用。

| 工况 | 原父（复用） | P1 仅持久身份 | P2 原 Debt 联合候选 |
|---|---|---|---|
| short-cold | FAIL / 2 | PASS / 6 / 1.446s | FAIL / 1 / 0.782s |
| reset-link | FAIL / 4 | PASS / 6 / 1.526s | FAIL / 1 / 0.943s |
| simple-control | PASS / 6 | PASS / 6 / 1.406s | FAIL / 1 / 0.814s |

P1只改 `persistent_queue=true`，holder保持off，三工况捕获/SAVE/发出/ACK均6；序号复用和接收去重均0。掉电仍为3/2/1次，修复的是跨掉电身份。原OFF分支未新增步数计数，P1 steps=null按实际保留。

P2保留原候选的lp_fifo、持久身份、holding_then_contact及 `clear_after=never`。三个原完整服务均FAIL/MISSED_OR_LATE_EVENT，无模型域UNKNOWN；MCU捕获/SAVE为4/3/2，发送成功/ACK/有效接收均1。holder捕获提交6/4/2、读取50/25/2、清除0/0/0、过期6/4/2、溢出0/2/4；掉电88/49/1次。never让已ACK队首仍不移除，后项受阻直至60s过期，超过原2s交付期限。另有欠压和溢出，不能归为单一“纯能量债”。

原始能量及各holder操作负载见 [A完整计数](../a/counter.json)，MCU启动/掉电时刻见各P2目录的event-timings.json。保留轨迹中的电压极值属于采样范围，不冒连续电压资格证据。原任务、设计及原科学核均经出口哈希回读。

## 数值、静态域及算法修订

实测卡点为 t=139.633881905s、v=1.800011000968516V、h≈4.366507e-8s。固定28次二分在该sub-dt空闲段把电压量化到同一数值，20万步保护触发TOOL_ERROR。第一次诊断另遇到非有限值序列化错误，原stderr保留；第二次保存完整紧凑卡点。两次均计新增完整尝试，不是有效能量FAIL。

修补对所有正长度无源恒载空闲段复用解析RC积分，并明确消费原有下降门限事件；没有新增迟滞、驻留时间或改门限、负载、服务。卡点处一次60位Decimal对照通过。P1使用原OFF路径consumer `9bd116f7…`，P2使用修补后 `3b15295b…`，每次来源单独保存。后续task缓存补丁是明确的之后版本，未回填P2源码身份。六次原科学核、固件及evaluator字节一致。

静态装配前筛复用原 `door_model.source_step(0,0,0,mechanism)`，只提前筛装配包络和压力角两项静态错误；独立动态检查保留。三控制器使用同一validator，原mixed在动态前共同拒绝同一assembly错误，父/P1/P2合法。进程内精确输入/源码身份缓存使B的574次helper调用仅产生2次新代数求值、572命中，未将重复计算重分类规避配额。

原首次Debt候选实际来自 `DOMAIN_COUNTERFACTUAL` 确定性祖先链，没有成功MODEL_JOINT_PROPOSAL；模型当时输出DSML公开读页也被旧JSON解析拒绝。此前“模型提出该候选”的表述有误，以 [原节点归因](../b/causal-attribution.json) 为准，旧原始记录不改。旧排序奖励新开义务及自造义务的闭合；新排序先看完整服务事实，公开已观察失败可触发有界诊断，静态自开/自闭不算进展。

新公开桥只取同权限activity中capture→SAVE配对、records及共同公开计数要求，不读host-only接收身份诊断。原身份丢失轨迹使真实step仅选持久身份；实际Update消费A已保存的P1三public后完整PASS停止。新子设计不继承父的实测结论。缺字段/域外/工具未完成、陈旧绑定保持UNKNOWN；重传不算新捕获。

捕获SATISFIED仅支持公开计数，不能扩称与每个隐藏真值事件逐一对应；never的静态交接SAT也不意味着期限、容量、能量或服务通过。7例为节省新几何计算共同排除mechanism编辑，这是软件检查范围，不能称整个合法域的比较。

缺捕获负例确实走完Update→Generate→Select，但选中holder关闭时的容量修改。控制路由测试通过，物理干预有效性仍未证实；宽泛依赖元数据仍允许不活动字段的试验。本次是开发者修订，不是自动学习。证书未改，物理必要性/方法优势仍未建立。

## 接入的实际范围

[有界DSML normalizer](model_format.py) 对保存的Generic嵌套arguments形式、Debt直接字段形式转换通过；合法JSON语义兼容，非法工具负例返回结构化FORMAT_ERROR。白名单仅public_object及object_id/section/offset，未执行模型文本或工具。见 [三项保存载荷回执](model-format-readback.json)。两控制器对旧格式错误现在共同MODEL_FORMAT_ERROR停止，不再让Debt在同类错误后确定性兜底而Generic停止。

公开桥已在B保存结果的实际控制器路径执行。原关闭的FamilyBroker、真实planner transport未改、未加载这两个新helper，未作新真实模型接入验证。原JSON_SYNTAX_ERROR和费用不回填。静态域已接共同task validator，不能把DSML和运行公开桥混称已在未来付费host生效。

## 计数、保存及出口

新增完整输入8=6完成+2保护诊断TOOL_ERROR，累计子进程43.106849s；原父复用3，机制II新执行0。cheap数值7/8（A5+B2），软件12/12（A2+B7+S03，各一次）。没有额外suite/init、provider请求/model episode/API费用/native/硬件运行。

[集中保存事实回读](final-readback.json) 核对24个结果文件完整JSON/gzip及SHA、任务/设计/科学核/计数和六张费用授权表。原1966请求、两个历史例外及owners/studies/principals/grants行数与完整行哈希均未变，UNKNOWN/null usage/全预留没有清零或重试。[接入与限制复核](final-integration-review.json) 另核B源码/产物全部哈希及P1条件绑定，不重跑行为或数值。

原环境和源树复用，0新增备份/环境/工作树/清理/commit/push。主动释放0B；观察可用空间变化属于全机活动，不计作本包清理收益。产物不足40MB限额，精确末采样见postflight.json。旧清理、旧试验保持暂停，P1/P2短里程碑各已送一次，不重发。

保存结果复核命令（不运行控制器、科学核或provider，只刷新本包派生回执）：

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B docs/research/pqe-two-paper-plan-20261022/codebt-zeroapi/s0/verify_final.py
```

下一前置依赖是审查方限定后续有限修订：处理不活动字段的因果选择并核实共同host接线，继续允许机制II不成立。本包不自动启动63输入、付费三组或重开旧预算；此处停止新增执行。
