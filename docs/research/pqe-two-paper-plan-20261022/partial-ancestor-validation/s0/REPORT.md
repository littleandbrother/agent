# 配套关系与失败祖先价值：有限验证出口

包 `BF-PQE-PARTIAL-ANCESTOR-VALIDATION-20261026-001` / BFA-099，2026-10-26。

**本轮没有建立“关系引导保留有用失败祖先能稳定降低搜索成本”的结论。** R 在 M2r 三个 seed 均找到完整方案，A 两个、D 一个；但 D 首个联合候选直接通过，A 在另一个 seed 更早通过，R/A 没有任何节点被标记为 `useful_failed=true`，且 G 的新机制比较运行不完整。R 的三个成功方案均关闭保持器，已经给出“本工况全局必须加保持器”的明确反例。有限包完成不代表完整四组科学比较完成，也不代表整个项目完成。

## 资格事实与它实际支持的命题

原 45 输入的 `a/mechanism-qualification.json` 保持 `NOT_ESTABLISHED`：M0/M1 30 次有效，12 PASS、18 FAIL；原 M2 的 15 次因 `speed_out_of_domain` 为 UNKNOWN。原输入、失败和 public v1 投影均保留。原转速边界在绝对时间相减后成为 120.000000000018，不能把它改写成模型有效的科学失败。

按工单第 9 节单独冻结 M2r 表达修订，将每个事件的持续时间统一延长至不超过原转速上界的 0.99 倍；保持事件间隔、转角、负载、供电、网关相对窗口和服务规则。未修改消费者物理/服务语义，15 次新增评价全部计数，原 M2 UNKNOWN 不覆盖。

| M2r 固定参考设计 | capture-recover | reuse-train | radio-gap |
|---|---|---|---|
| 原父 | FAIL | FAIL | FAIL |
| 原父仅开 persistent_queue | FAIL | FAIL | FAIL |
| 保持器部分方案 | FAIL | FAIL | FAIL |
| 固定完整配套参考 | PASS | PASS | PASS |
| 完整参考 clear=never 邻居 | FAIL | FAIL | FAIL |

这只建立该固定局部参考集的交互，不建立保持器在整个合法设计域的必要性。`persistent_queue` 实际持久化 seq、last_direction 和 queue；它不是纯序号身份干预。M0/M1 的恢复也涉及 last_direction 使闭合后捕获成为可能，不能简化成纯身份因果。

资格设计/删除邻居的精确输入和隐藏事件真值未进入方法或模型历史；主比较只开放共同初态及相同有类型公开记录关系。M2r 是见到原表达问题后的探索性修订，不追称原 M2 的事前成功。

## 实际比较与预算口径

G 为同后端真实模型与工具，可自由提交整个合法联合设计；D 为普通多样性联合搜索；R 为关系/祖先选择；A 仅关闭低分非初态祖先的展开。每 family 三个固定 seed，最多 6 槽（含共同初态），三工况全 PASS 即按共同规则停止。语义重复/精确缓存仍占槽；未执行的节点不继承父 PASS。

以下“合法完整评价数”来自实际 controller 节点，排除共同初态和静态域拒绝，包含精确复用；“新增完成”来自整个科学账本，按真实执行归属计数。它们不是同一个量。所有原始行及第一次退出见 `comparison-first-exit.json`，最终终态行见 `comparison-result.json`；原文件中 `FINITE_MATRIX_COMPLETE` 仅指 24 行都有终态。

| family | 组 | seed | 终态 | 槽位含初态 | 合法完整评价数 | 本包新增完成 | 中断 |
|---|---|---:|---|---:|---:|---:|---:|
| known-local | D | 161803 | MODEL_DOMAIN → UNKNOWN 停止 | 3 | 3 | 3 | 0 |
| known-local | G | 161803 | 三原工况 PASS | 2 | 3 | 0 | 0 |
| known-local | R | 161803 | 三原工况 PASS | 2 | 3 | 0 | 0 |
| known-local | A | 161803 | 三原工况 PASS | 2 | 3 | 0 | 0 |
| known-local | D | 271828 | MODEL_DOMAIN → UNKNOWN 停止 | 3 | 3 | 3 | 0 |
| known-local | G | 271828 | 三原工况 PASS | 2 | 3 | 3 | 0 |
| known-local | R | 271828 | 三原工况 PASS | 3 | 6 | 6 | 1 |
| known-local | A | 271828 | 三原工况 PASS | 3 | 6 | 0 | 0 |
| known-local | D | 314159 | MODEL_DOMAIN → UNKNOWN 停止 | 3 | 3 | 3 | 0 |
| known-local | G | 314159 | 运行/接口未完成 | 1 | 0 | 0 | 0 |
| known-local | R | 314159 | 三原工况 PASS | 2 | 3 | 3 | 0 |
| known-local | A | 314159 | 三原工况 PASS | 2 | 3 | 0 | 0 |
| mechanism | D | 161803 | MODEL_DOMAIN → UNKNOWN 停止 | 3 | 3 | 3 | 0 |
| mechanism | G | 161803 | 运行/接口未完成 | 1 | 0 | 0 | 0 |
| mechanism | R | 161803 | 三原工况 PASS | 2 | 3 | 0 | 0 |
| mechanism | A | 161803 | 三原工况 PASS | 2 | 3 | 3 | 0 |
| mechanism | D | 271828 | MODEL_DOMAIN → UNKNOWN 停止 | 2 | 0 | 0 | 0 |
| mechanism | G | 271828 | 运行/接口未完成 | 1 | 0 | 0 | 0 |
| mechanism | R | 271828 | 三原工况 PASS | 5 | 12 | 6 | 0 |
| mechanism | A | 271828 | 三原工况 PASS | 3 | 6 | 3 | 0 |
| mechanism | D | 314159 | 三原工况 PASS | 2 | 3 | 3 | 0 |
| mechanism | G | 314159 | 运行/接口未完成 | 1 | 0 | 0 | 0 |
| mechanism | R | 314159 | 三原工况 PASS | 4 | 9 | 6 | 0 |
| mechanism | A | 314159 | 6 槽耗尽，未成功 | 6 | 15 | 9 | 0 |

known-local 两条 G 成功是模型实际提出“仅开启 persistent_queue”的方案，三个原工况均通过。host 曾因 JSON 的 1/1.0、5/5.0 哈希差异拒收；只按已授权的数值等价绑定接回已有结果，未增加仿真、模型请求或槽位。原 `MEMBER_DESIGN_BINDING` 错误保留，接回见 `binding-recovery/`。

known-local-R-271828 的断点续跑行仅列 5 次新增，不能拿来当整条轨迹成本。完整账本含 science/028 的已完成前缀、science/029 的人工中断和后续：**6 次完成 + 1 次中断，35.476994667 秒**。公平设计成本是两候选 × 三工况 = 6 次合法逻辑评价。中断仍保留 STARTED 原行，按运行中断解释，不补写科学 FAIL，不抹掉成本。

D 的五条未成功轨迹均因共同预筛返回域 UNKNOWN 后按冻结规则停止：4 次 `ADAPTIVE_REQUIRES_PERSISTENT_QUEUE_AND_BACKOFF_ORDER`，1 次 `cam_pressure_angle_exceeded`。它们不是跨不过“死亡谷”的科学负例。D 在 M2r seed314159 第一个联合修改（槽 2）已三工况 PASS。

G 的两个 seed314159 在本地闲置租约拒绝/对象占位符路径错误后到达原 900 秒截止，0 上游请求，未重开 owner 或延长窗口。M2r-G271828/161803 主要消耗公共分页工具，未形成合格完整设计；原 host 每次新 Pi 调用没有对话历史，payload 只保留最后页，分页过程的 remaining 显示亦曾滞后。因此不能将其当作强 G 的科学败绩。271828 在原 owner/原截止内恢复其已读 12 页与真实剩余 2 请求/1 工具后仍耗尽工具，12 请求/24 工具，0 新完整输入、无 final；161803 已满 24 工具，不续。兼容恢复原始记录见 `context-recall/`；它发生在其他组 holdout 之后，未输入任何 holdout 结果，且没有产生新的 holdout 设计。

## 失败祖先是否真的发挥了所提机制

- seed314159：R 的成功链为 root → 槽2 的 persistent 失败父 → 槽4 的 startup_v=1.9 成功子。A 同样看过前两个候选，之后门禁阻止展开该低分父，6 槽未过。这证明一条配对轨迹中“展开失败父”改变了路径；该父的 targets 为空、useful_failed=false，实际父选择为 COMMON_DIVERSE_ELITE_PARENT，不能称“有用中间能力被关系指导保留”已获证实。
- seed271828：R 多次展开失败父，却由 root 重启候选在槽5成功；A 槽3已成功。额外展开在该条轨迹没有节省评价。
- seed161803：R/A 第一个候选相同，槽2均成功，未经过失败祖先扩展。

R/A 所有实际节点的 useful_failed 标记均为 false，没有按该标记优先展开。关系可以在存在公开 false 事实时影响父/补丁排序；共同 factory 只把关系放入哈希，不依据它改变候选生成。R 与 D 还存在小补丁与 novelty/joint 的次序差异，不能把 R/D 差异全归因于关系信息。R/A 是更直接的低分父门消融，但三个 seed 呈有利、不利、持平三种路径，不能从 3/3 对 2/3 宣称稳定收益或显著性。

公开 capability 按 seq/direction 去重，不是真实事件唯一身份或独立捕获召回；missing、重复读取、ACK 时序及已消费记录不自动等同丢失。人工 depends_on 是声明契约，不能冒称学习出的因果规律。

## 隔离扰动的确切完成范围

原 12 条机制轨迹的最终状态在首次 holdout 前统一冻结。这里是 6 项合格最终提交、5 种不同设计。**6 个合格最终方案的两扰动均 PASS（12 个逻辑成员结果，其中 10 次新完整执行、2 次精确缓存）；另 6 条轨迹未复验。** 合格项为 D314159、R314159、R271828、A271828、A161803、R161803，后两项同设计的复验精确复用。

其余 6 项为 A314159 和 D271828/D161803 保留父但 `eligible_for_holdout=false`，以及三个 G 无合格最终设计。工单“保留父也复验”的表述与冻结实现只允许合格设计的 eligible 规则存在缺口，本包不改规则补跑，也不把原父算复验成功。两扰动只是在同一构造机制上的固定设计复验，不是大规模未见任务泛化。

R 三个成功方案（以及两个成功 A）均 holder off，通过持久化及合法电压/储能/发送参数调整取得完整服务。保持器的全局必要性已被这些真实完整结果反驳；固定配套参考的局部交互仍成立，两者不矛盾。

## 实际资源与记录保全

本包 125 次新增完整尝试、434.827546834 秒消费者实耗：资格 60；主比较 54 完成 + 1 中断；隔离复验 10 完成。完成的 124 条包含原 15 个域 UNKNOWN，不能写为 124 次模型有效成功。另有 54 次精确完整缓存操作（含初态/恢复上下文的重读），不可当 54 个新候选。廉价数值 23，静态缓存命中 360。

软件上限 12 项已用完：A3、B5、S04。B 原 4 PASS/1 FAIL 的上限断言回执保留，单行断言修正后未重跑；S0 公共链最后一步曾错将未分页全对象送入 240KB guard 而 FAIL，只续完正确 project→callback 的未完成子步骤 PASS，不额外增加软件项或重跑套件。这些是软件接入事实，不是方法科学收益。

真实 provider 29 次均 SETTLED，455,988 input / 92,108 output tokens，cache-hit tokens=0；按已固定费率的账本上界/缓存感知估算均 USD 0.247326，未核发票。G 六个注册 episode 中四个实际发生上游请求，计数为 known 两项各4、mechanism 两项12与9，其余两项0。新 UNKNOWN/缺 usage/在途预留为0。原 1,966 条计费整行哈希、原例外授权哈希不变；原两 UNKNOWN、null usage 和合计 USD0.3686529 全预留原样保留。临时 principal 已撤销、grants/study 过期、六 conversation IDLE，model_budget_scope 恢复原缺省不存在状态。

继续复用原环境和源树，未新增备份、环境、工作树、native/hardware 调用、commit/push 或全仓 init。旧清理、旧研究和定时任务保持暂停，本轮主动释放 **0 B**。输出上限200MB、入场磁盘36,796,846,080B；最终输出分配与磁盘可用量以 `postflight.json` 为准，文件系统背景变化不冒称本包回收/占用。

## 独立读回与复验入口

A 独立服务/能量、任务设计与 raw 绑定范围见 `../a/METHOD-INDEPENDENT-READBACK.json` / `.md`；B 独立轨迹/实际费用/祖先链范围见 `../b/METHOD-INDEPENDENT-EXIT.json` / `.md`。原资格和 B 初次不兼容出口不覆盖。S0 只读集中核验的实际出口为 `final-readback.json`，完整当前产物哈希清单为 `integrity-manifest.json`，科学资源原表为 `science-resource-ledger.json`，24 行解释投影为 `method-summary.json`。原 `comparison-result.json` 内嵌账本哈希早于后续同 episode 恢复的账本保存，已过时；原摘要不覆盖，当前账本/摘要的显式绑定见 `evidence-index.json`，65 行计数与耗时不变，不将此索引问题当成新科学结果。

在项目根目录执行以下命令只核验现有事实和只读费用表，不产生模型请求或重新仿真：

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B docs/research/pqe-two-paper-plan-20261022/partial-ancestor-validation/s0/verify_final.py
```

本包出口是有限构造实验及运行缺口的完整记录；没有建立强 G 比较优势、有用失败祖先的因果收益、全域必需部件、合格不可行证书、学习/递归或硬件验收。所有执行门关闭，后续不自动补组或启动修复包。
