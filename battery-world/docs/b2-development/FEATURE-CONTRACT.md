# B2-003：先形成可修复反例，再检验迁移

## 固定中心 claim

在跨域耦合的 BF AIoT 设计中，局部经验可能错误裁剪可行设计空间。我们研究通用 Coding Agent 能否借助独立实验识别这种失效，修订具有明确适用域的可执行判断，并使未来 Agent 在等预算的新任务中减少试错而不增加错误准入。

本 feature 不负责增加场景或证明 RSI。它首先减少两个不确定性：失败是否只是程序不能运行，以及局部规则究竟删除了哪些原本可解的设计。

| 合同项 | 当前约定 |
| --- | --- |
| 输入 | 已封存 pilot；公开机械测试 context；候选 code/scope；显式任务物理规格 |
| 输出 | 编译回执、修复尝试与成本、G2 残差、单因素实验、分开的 model/workflow 回执、启动阻塞清单 |
| 信任边界 | 候选只能提出程序/策略；不能改编译政策、参考世界、资格门、split、费用或证据身份 |
| 验收测试 | 语法/AST/plan/schema/domain；最大 3 候选；重复与未知 callback 停止；缓存恢复；物理换名重复；盲测反馈拒绝；回执错绑拒绝；UI 样本绑定 |
| 科学门 | 机械通过之后仍须新资格、可解性保留、真实激活、blind transfer、removal、transplant；目前均不声称通过 |
| 负对照 | G0/G1/G2 拒绝；all-abstain 程序只机械通过；无解任务；域外输入；无效 workflow；同物理新 ID；未结算回调 |
| 成本 | 本轮零 provider 调用；记录当前本地 wall/parent+child CPU；旧账本不重置，旧 CPU 不补猜 |
| 展示 | 现有 Campaign 页上的 Counterexample Workbench；不增加新的 3D 部署场景 |

## A — 机械门（已实现，非科学学习）

`compiler.py` 在 OS 隔离子进程前做 AST/语法、危险调用、单一 `plan(ctx)` 与明确 scope 检查；运行公开最小输入、域外、缺失、null、错误类型输入。新输出采用 `feasible / infeasible / abstain`。无效程序不会进入 `qualify_world()` 的科学 evaluator。

`repair.py` 最多接收两次替代候选（总计三次），使用候选/输入/编译器/序号的稳定身份。重复候选停止，完成结果缓存重放。先记录 callback 意图，进程中断但结果未知时拒绝重复 dispatch。已有 provider 调用机制尚未接入新协议，因此这里不生成真实 G3/G4。付费 callback 将来必须返回实际费用回执。

报告中的机械修复 control 是手写测试：语法错误 → all-abstain 程序。它只测试恢复路径，绝不是 Agent 学到物理知识的结果。原 G2 的旧布尔输出通过显式 envelope 迁移接受机械检查，未被偷偷改写成新程序。

## B — G2 科学反例（开发诊断已实现）

24 条旧检查逐一重新执行并匹配原 run hash；10 条 false reject、0 条 false admit。qualification-6/7 丢失可解性；qualification-8 从 3 次到 1 次只是局部收益。它们现在属于公开开发材料，不能计作新的盲测。

结构化残差字段包括 `false_reject_region`、`false_admit_region`、`lost_solvable_task`、`probe_reduction`、`scope_violation`、`missing_state_variable`。

发现的确定代码语义错配：G2 用 `tx_power * release_s / efficiency` 算负载能量，任务释放时刻 250 ms 不是 TX 时长 40 ms。ESR 和 TX 功率其实已被读取，不应宣称它们完全缺失。完整动作时长、相位和 typed deadline 是接口缺口。修正该表达式是否足以改进任务，尚未由新候选资格证明。

canonical episode 预先固定四个单因素干预，保留失败：

- ESR 18 → 4 Ω：仍掉电；最低输入约 1.794 V。
- C 330 → 2200 µF：计算任务通过；最低输入约 2.006 V。
- TX 36 → 9 mW：计算任务通过；最低输入约 2.620 V。
- source phase 0 → π/2：仍掉电；最低输入约 1.732 V。

这些是控制器执行的合成计算实验，不是实测，也不是 Agent 自主区分原因的正向故事。四种解释仍保留，单因素差异不能唯一识别全部机制。

## C — 模型 / Harness 分离（接口与负对照已实现）

`qualify_world` 和 `qualify_workflow` 有不同的 kind、candidate hash 和判据。world 拒绝不会清除一个通过路由安全检查的 workflow。workflow 目前是声明式有限候选路由，只能排序、请求 transient、在证据匹配后提交或无解时 abstain；不支持任意改代码。路由安全通过不等于省成本或迁移有效。

## D — 显式 split（检查器已实现，正式任务尚未生成）

新接口不接收 modulo task index。每个任务显式声明 source、初始状态、负载、C/ESR 候选、receiver、model card、label、deadline 和 reference version。物理指纹忽略任务/候选命名、排序、session 和单纯版本改名；重复物理不能变成 transfer。回归允许重复，但必须显式绑定来源。旧最终数据被标记 exposed，禁止重新准入 blind。

这是精确身份检查，不是所有近似任务都独立的证明；近重复阈值与任务族设计仍需正式协议。检查器不生成、不查看、不运行新的盲测集。

## E/F — 未完成，不预先记分

尚无合格 G3/G4、激活后的五条件公平比较、blind transfer 增益、removal 或 transplant。C1/C2 仍阻塞。现有 false admission 为零不替代未来新条件上的检验。

### 2026-09-07 继续实现：显式负载和测量回放

详见 `SEMANTIC-REPAIR-AND-MEASURED-REPLAY.md`。新增独立版本的 typed phase-load
reference 与七个公开任务的 36 条封存运行。三个工程诊断程序均能执行，但修复
release/TX 错配后错误可行预测显著增加，且 qualification-8 原有探测优势丢失；
没有晋升。已测试的移除／新进程移植仅为确定性工程控制，不算上述 E/F 研究结果。

同时只读封存了历史真实电流、接收日志及来源元数据。两者不属同一实验，
实测电压／能量和硬件闭环仍不可声称。网页新增诊断负结果与实测回放，未加场景。

## 复现

```sh
.venv/bin/python scripts/build_b2_development.py
PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m unittest discover -s tests/campaign -p 'test_b2*.py' -v
corepack pnpm run build:studio
node apps/world-studio/development-test.mjs
./init.sh
```

产物：`docs/b2-development/report.json`（最新投影）；对应 immutable report、29 个原始运行和机械 control 保存在 `.bfworld/b2-development/<input-hash>/`。浏览器核验写入 `browser-validation.json`。旧 `docs/campaign/report.json` 的哈希保持不变。

## 下一次付费前必须由负责人明确的决策

`studies/b2-003/protocol-draft.json` 暂不填写 owner approval、task manifest、资格阈值、统计单位、候选排序规则或新的执行窗口。它明确继承每 trial ¥2、累计严格低于 ¥20 与原账本，但不自动重置/扩展旧工程 token/call/wall 上限。旧预算已用 ¥1.463445、463,487 tokens；不能因现金剩余多就忽略其他上限。

完成这些决策并绑定 exact protocol hash 后，才考虑新模型生成与科学资格；如果新知识失败，应保留失败，不调门槛或替换模型追求表面通过。
