# 唤醒节点与 Agent 预实验：统一索引

整理日期：2026-11-12。这里保留两分支已有代码、报告和原始数据。最新新增[36条原题观测剥离实验](observability/REPORT.md)及[超时原因](observability/REPORT.md#七五条超时具体耗在哪里)；完整记录见[发布入口](observability/README.md)。下面第3—8节保留11月11日整理时的历史分析，不能将其中待执行描述视为今天仍未执行。此次提交没有新增模型调用或物理仿真。

## 1. 从哪里开始看

1. 先看本文第 3 节，理解一路排除了什么解释、留下了什么问题。
2. 看完整瞬态的[第二阶段报告](phase2/REPORT.md)，了解偏差、过程诊断、搜索范围与错误无解判断。
3. 看最新[幅相 / 事件窗口拆分](phase2_ablation/README.md)，了解诊断里究竟哪部分改变了行动。
4. 看另一分支的[13 族预实验](pilots/README.md)和[三项深入比较](pilots/DECISIVE.md)，了解明示定律、隐藏规律、无解判断与上界工具。
5. 最后看[下一轮三组试验](NEXT_EXPERIMENTS.md)。它是待实施方案，不是已有结果。

## 2. 两条证据链，分别回答不同的问题

| 环境 | 代码 | 实际算了什么 | 可以支撑什么 |
|---|---|---|---|
| 完整唤醒节点 | [sim.py](sim.py)、[design.json](design.json) | 梁与电路双向耦合、整流、储能、唤醒、实际采样与分类、保存、发送、截止时间 | 在声明模型中的完整服务设计结果 |
| 快速谐波筛选 | [agent_limits.py](agent_limits.py) | 谐波响应及能量、捕获、应力等约束 | 筛选器里的可行性；只有另存的瞬态回灌才算完整节点结果 |
| 闭式合成世界 | [world.py](world.py)、[pilots.py](pilots.py) | 参数化谐振、电学匹配、模块和分支；可生成可行 / 无解成对实例 | 定律可见性、搜索与停止行为；不等于完整瞬态或实物结果 |

`pilots` 的 H 原语拼装 8/8、A 明示 / 隐藏规律比较和 Python 7/8 对 6/8，属于第三行。不能拿它们直接替代 `sim.py` 的采样、误报或交付结果。所有结果均为仿真，没有实板测量。

## 3. 思路如何走到现在

### 第一步：先做出一个完整工作的节点

[节点设计说明](README.md)、[结果](result.json)、[波形](waveforms.svg)和[开发失败记录](development.jsonl)给出了最小工程起点：空电容充电，机械与模拟部分监听，数字部分按需启动，实际分类后发送。最终固定设计在 30 秒任务内交付 4/4、误报 0。它证明工程链条可执行，不证明某个 Agent 方法有优势。

### 第二步：发现“随机很难”不等于“Agent 很难”

[首轮 limits](limits/README.md)跑了 60 条对话。困难题上 All-Open 与 Cert-Guided 都是 10/10，Free-Expand 9/10，Fixed-P0 0/10。限制局部变量确实会卡死，但随机体积很小没有阻止模型利用公式和采样窗捷径直接过关。

随后 [boundary](boundary/README.md)锁定现有采样窗，按模块必要性选工作点，再区分白盒、灰盒、黑盒信息。这时开始出现真实困难，但也暴露 7 次输出长度截断。它们单列，不能算模型判断错误。

[D3 工具比较](boundary_d3/README.md)增加数值扫描：灰盒无工具 1/6，有工具 4/6；黑盒无工具 0/6，有工具只有 1 条完整完成，其余停止。成功设计中三个不同设计回到完整节点均为 2/2，移除 A 的固定设计反事实为 0/2。这说明连续信息和数值工具有用，尚不足以建立稳定方法优势。

### 第三步：把困难拆开，排除“不会跨域”这个过宽解释

[六维拆解](deep/README.md)和[33 条原因剥离](isolation/README.md)检查组件连接、未知偏差、软件预检、复位、数值精度与筛选失配。保留了数值误差、接入故障和原始 UNKNOWN，没有把所有失败都解释成 Agent 不懂物理。

另一分支的 [13 族扫描](pilots/README.md)及后续确认进一步发现：在闭式世界里，写出隐含需求和拼出唤醒原语往往不难；给出反事实定律也能推演。更稳定的困难是从混合反馈辨识隐藏电学关系，以及从有限试点错误地跳到“整个设计空间无解”。

具体地，反事实定律明示为 15/16，隐藏为 2/16，增加负载匹配度 / 源内阻观测为 14/16。它们不是同一对话中先后发生的能力变化，而是不同隔离会话的对照。明示和隐藏的差异不能只解释成“模型完全不懂物理”，也不能由此断言信息论上不可解。

### 第四步：在完整瞬态里检查信息究竟改变了什么

[Phase 2](phase2/REPORT.md)有 192 条会话。A1 完整诊断 D 为 15/16；基本反馈 P 为 8 次通过、7 次正常未过、1 次输出截断；也有名义参数完全正确却漏掉 30 mm 共振峰、根据 24 / 35 / 42 mm 就宣布全域无解的实例。

这里 **P 已经提供基本电压、峰值、阶段计数与裕量**，不是只给二元 PASS/FAIL。D 新增实际幅相、能量分项、最低运行电压和逐事件对应信息。后者有收益，但不能把全部收益归于某一个字段。

搜索范围摘要并未稳定消除错误排除：J 上 P 2/4、PS 3/4、D 4/4、DS 3/4。这是小样本结果，不是摘要普遍有害的证明。A3 的提示本来就要求最大化开路稳态代理；优化代理后漏首包，证明代理目标与完整服务不等价，不证明 Python 或数值优化普遍无效。

### 第五步：把 D 拆成幅相和事件窗口

[最新实验 B](phase2_ablation/README.md)只选历史 D 通过而 P 正常未过的 7 个配对，新增 14 条会话：P＋幅相 5/7，P＋事件窗口 4/7，共同通过 3 对。样本对应 5 个任务 ID，包含名义条件与重复，不能写成 7 道独立制造偏差题。

轨迹里有明确行动变化：相位帮助夹住共振区间；逐事件信息帮助区分“供能已好，但目标窗口没有唤醒”。也有相同信息被忽视、有限测点被错误推广为全域上界的失败。**信息变清楚有实际价值，可靠消费信息与正确停止仍未解决。**本轮没有运行 PA＋EW 联合组。

### 第六步：无解判断工具有价值，但必须拆开信息和强制规则

[Closure A](pilots/DECISIVE.md)中，可解题 base 9/16、hint 16/16、anon 13/16、bound 15/16；真无解识别分别 13/16、2/16、16/16、16/16。

三个必须保留的细节：

- hint 在可解题里实际只触发 2 次，两次救回；另外 14 次在触发前已通过。不能把全部组间差异归于提醒。
- anon / bound 的宿主会拒绝非负上界下的 INFEASIBLE。实际两组拒绝次数都是 0，模型分别在 31/32、32/32 条会话主动读取上界；这支持信息被使用，但“零错判”仍不能单独当成模型自身校准的证据。
- 正上界只表示还不能排除，不能证明存在解；负的、覆盖声明域的可靠上界才支持无解。可行性由实际通过设计作见证。

## 4. 实验与数据目录

| 包 | 已保存规模 | 主要报告 | 原始数据 / 固定对象 |
|---|---:|---|---|
| limits | 60 条终态对话 | [说明](limits/README.md) | [agents.jsonl](limits/agents.jsonl)、[初始输入](limits/agent_input.json)、[标定](limits/calibration.json)、[汇总](limits/summary.json) |
| boundary | 54 条；其中 7 次输出截断 | [说明](boundary/README.md) | [agents.jsonl](boundary/agents.jsonl)、[protocol](boundary/protocol.json)、[汇总](boundary/summary.json)、[瞬态回灌](boundary/transient.json) |
| boundary_d3 | 24 个 job；19 条完整、5 条预算 / 依赖停止 | [说明](boundary_d3/README.md) | [agents.jsonl](boundary_d3/agents.jsonl)、[汇总](boundary_d3/summary.json)、[回灌](boundary_d3/transient.json) |
| deep | 36 条终态对话；保留 6 笔缺用量请求 | [说明](deep/README.md) | [agents.jsonl](deep/agents.jsonl)、[protocol](deep/protocol.json)、[汇总](deep/summary.json)、同目录资格与故障记录 |
| isolation | 33 条；含 3 次输出截断 | [说明](isolation/README.md) | [agents.jsonl](isolation/agents.jsonl)、[protocol](isolation/protocol.json)、[汇总](isolation/summary.json) |
| pilots 初筛 / 确认 | 316 条有效对话 | [说明](pilots/README.md) | [runs.jsonl](pilots/runs.jsonl)、[tasks](pilots/tasks.json)、[confirm](pilots/confirm.json)、[汇总](pilots/summary.json) |
| pilots 深入 1 | 新增 77 条有效对话 | [深入报告](pilots/DECISIVE.md) | [decisive.jsonl](pilots/decisive.jsonl)、[固定题目](pilots/decisive.json)、[protocol](pilots/decisive_protocol.json) |
| pilots 深入 2 | 新增 48 条有效对话 | 同上 | [decisive2_exp2.jsonl](pilots/decisive2_exp2.jsonl) |
| pilots 深入 3 | 新增 19 条有效对话 | 同上 | [decisive2_exp3.jsonl](pilots/decisive2_exp3.jsonl) |
| pilots Closure A | 新增 128 条有效对话 | 同上 | [decisive3_closureA.jsonl](pilots/decisive3_closureA.jsonl)、[closureA](pilots/closureA.json)、[深入汇总](pilots/decisive_summary.json) |
| phase2 | 192 条终态会话；615 次有用量响应 | [完整报告](phase2/REPORT.md)、[汇总说明](phase2/README.md) | [results.jsonl](phase2/results.jsonl)、[jobs](phase2/jobs.json)、[physics](phase2/physics.json)、[scope](phase2/scope.json)、[汇总](phase2/summary.json) |
| phase2_ablation | 14 条正常终态；55 次有用量响应 | [最新报告](phase2_ablation/README.md) | [results.jsonl](phase2_ablation/results.jsonl)、[jobs](phase2_ablation/jobs.json)、[physics](phase2_ablation/physics.json)、[汇总](phase2_ablation/summary.json) |

pilot 五份 journal 合计 588 条有效对话，另有 93 条基础设施终态、7 条预算停止。它们原样保留，但不当作新增有效实例。加上本地六包的 389 条终态和 D3 的 24 个 job，可定位 1001 条所选终态记录；**这个总数不是 1001 个完整科学样本**。会话重复、成对世界、同一物理输入复用和工具中断的分母不同，比较以各包表格为准。

## 5. 源码版本如何合并

统一分支：`codex/agent-boundary-unified-20261111`。

- 用户 GitHub 分支：`codex/agent-boundary-pilots-20261110`，HEAD `f1c745c572d842042aeaf73caec6ebc637f89026`。
- 原唤醒分支：`codex/minimal-wakeup-node-20261110`，HEAD `a8badd8aba86cfabbffd2a91038c756d2aa738a1`。
- 本地新增完整瞬态与消融源码 / 数据首先保存为提交 `3060250`，再完成联合整理；它保留了合并前 367 行的 `agent_limits.py`。

最终工作版本采用：

| 文件 | 采用版本及原因 |
|---|---|
| `agent_limits.py` | 使用 `f1c745c` 的扩展版，保留 `ask`、流式读取和 D3；否则 `pilots.py` 导入会失败。双方共有物理常量与 14 个物理 / 反馈函数一致，没有更换科学方程。 |
| `world.py`、`pilots.py`、`pilots/`、`boundary_d3/` | 保留 GitHub 分支原文件。 |
| `sim.py` | 使用本地最新完整消费者，保留后续积分与阶段处理修正。 |
| `deep*`、`isolate*`、`phase2*` | 纳入本地现有源码、报告、输入、缓存和原始记录。 |
| 历史 journal / 费用 / 错误 | 不改写、不抹去、不以统一版本重跑。 |

原 `limits` 的 60 条来自提交 `5f06f8a`：当时 `sample_ms` 仍可调。当前代码已固定 62.5 ms，不能用当前程序重新跑旧任务后宣称复现原实验。原始执行身份由旧提交与原报告保留；统一分支提供当前可运行源码，并非所有历史条件的同一个源码快照。

## 6. 费用与运行量怎么读

各包保存请求、usage、估算和缺失情况。`estimated` 是按费率估算，不是供应商账单；缓存价、保守价、历史预留不能混加成“实付总额”。

本地六包的缓存费率估算分别约为：limits 0.714623304、boundary 0.8134371、deep 1.35022041、isolation 1.403779692、phase2 3.617026644、最新消融 0.314397528 美元。它们的估算口径与历史实时账本未必相同，详细值以各 summary 原字段为准。

`deep` 的 6 笔 UNKNOWN 与 USD 0.3957294 预留继续保留。pilot 也保存无 usage 的历史基础设施请求与原保守估算；不能因为从科学分母排除故障，就把可能费用删除。Phase 2 和最新消融均为 0 新 UNKNOWN。此次整理和推送为 0 新模型调用、0 新仿真。

“正式评价一次”不等于“只算一个点”：例如 D3 的 `explore` 可包含多个扫描点，Phase 2 数学优化也有内部点数。分析效率时同时读请求、所有数值点、新完整输入、精确缓存复用、token、费用与墙钟时间；不能只报首次正式提交数。

## 7. 最小复查方式

依赖仍只有现有 Python 科学计算包：`numpy scipy matplotlib`。查看 Markdown、JSON、JSONL 不需要模型密钥。原始数据无需重跑即可复核。

```bash
# 完整瞬态结果汇总；只读取已保存记录，不调用模型或执行仿真
PYTHONDONTWRITEBYTECODE=1 python3 -B wakeup/phase2_report.py

# 闭式世界初筛 / 确认汇总；只读原始记录
PYTHONDONTWRITEBYTECODE=1 python3 -B wakeup/pilots.py --report

# 闭式世界深入比较汇总
PYTHONDONTWRITEBYTECODE=1 python3 -B wakeup/pilots.py --decisive-report
```

以上命令会重写对应派生汇总，原始 journal 不变；阅读现有报告不必执行。带 `--run`、`--confirm`、`--decisive`、`--d3` 的执行入口可能调用模型，本次整理没有启动。没有新增框架、数据库或实验调度层。

## 8. 现在真正值得继续验证的问题

1. 换更强模型、增加实际思考量和独立评价预算，能否消除隐藏量反演与错误全域排除？若能，边界应收缩到模型与预算条件。
2. 同一个物理实例，在隔离会话里明示规律能解、隐藏规律不能解，究竟差在辨识、行动还是停止？不能通过同一会话泄漏答案来制造对比。
3. 数值工具、同事实摘要、中性提醒各自解决了什么，又遗漏什么？能否同时保留可解题通过率与有依据的无解判断？

这三个问题的具体任务数、对照、预算维度、复现与反证条件见[下一轮方案](NEXT_EXPERIMENTS.md)。现有数据支持研究它们，不预先保证“轻量模型加诊断必胜旗舰”或“所有通用补丁都无效”。
