# B2-003：真实修复接口与科学检验执行链

2026-09-07。本轮接通执行代码与控制实验，未发送真实模型请求，也未批准新的实验协议。

## 两条执行链

```text
候选 + 公开 context → 编译失败 → 稳定 repair request
    → 已批准协议 / 固定模型 / 原账本 / 时间窗口检查
    → reserve → provider → settle → 候选解析 → 再编译

机械有效候选 + 完整成本状态 + 显式 task manifest + 冻结 qualification plan
    → explanation → use → regression → out-of-scope
    → 分项事实与拒绝 / 资格回执
```

候选的可行预测不是 reference 的任务成功；机械通过不是科学资格；正式资格也不是
未来 Agent 迁移增益。上述层次仍有独立的状态，不合并成一个绿色“成功”。

## 付费前检查与恢复

`campaign/repair_bridge.py` 复用现有 `Provider.complete` 与 SQLite 原账本，
不修改其代码或预算。固定每试验 ¥2、总工程上限 ¥19、120 calls、600,000 tokens，
包含已经计入的历史支出。模型、fingerprint、编译器、provider、ledger、adapter、
初始候选与 contexts 均需要由协议精确绑定。新执行窗口必须明确；代码不补签批准。

| 中断状态 | 恢复行为 |
| --- | --- |
| request 已写，adapter 尚未进入 | 在协议仍有效时可开始；没有前序付费效应 |
| adapter intent 已写，账本没有 reservation | 串行锁与固定 reserve-before-dispatch 实现证明未 dispatch，允许开始一次 |
| 账本 reserved，provider 结果未知 | 保留费用预留并停止，绝不自动重发 |
| 账本 settled，候选文件缺失 | 从相同 request key 的原 receipt 恢复，不发送第二次请求 |
| 模型或 fingerprint 改变 | 保留实际付费记录，但拒绝候选，不换模型重试 |
| 输出不是完整 JSON / 被截断 | 作为无效候选进入剩余机械修复次数，不占科学 reference 预算 |
| 父级候选/费用文件被修改后重新计算哈希 | 与实际 settlement 再对账，拒绝不一致结果 |

通过一个实际子进程 `os._exit(71)` 测试了“已结算、未写完候选”的窗口。
外部传输使用明确标识的 fake response，SQLite reserve/settle 与进程退出是真的。
隔离测试账本不会接触项目原付费数据库；因此这不是一次真实 DeepSeek G3 试验。

若进程退出导致本地 CPU/耗时区间不可测，回执记录 `incomplete-after-crash`，
数值只是已知区间的下界，不能解释成实际零成本。完整成本状态默认为未确认；
科学执行器在控制器明确确认之前不会开始 reference 检验。

另有完整对接测试：响应替身经真实账本、机械修复与科学执行器，再转换为
已有组件激活 API 的 world-model 回执。工程样例不会获准激活为已合格知识；
独立通过路由安全检查的 workflow 不会随世界模型一同清空。这仍不是 workflow
收益资格或正式 world/workflow 因果比较。

## 一个入口，三种模式

脚本为 `scripts/run_b2_repair.py`，输入是实际 JSON 文件，而不是对话中的推测身份。

```sh
# 默认只检查；不加载密钥、不创建费用预留、不生成候选。
.venv/bin/python scripts/run_b2_repair.py \
  --protocol path/to/owner-approved-protocol.json \
  --initial path/to/candidate.json --contexts path/to/public-contexts.json \
  --trial-id exact-trial-id --output .bfworld/b2-repair/exact-trial-id

# 只有已批准协议且全部绑定一致时，显式增加 --execute 和 --key-file 才会 dispatch。
# 不要把密钥本身写进命令、协议、报告或代码。

# 已结算请求的恢复，不需要密钥或新时间窗口。
# 相同参数增加 --reconcile-only；账本以 SQLite mode=ro 打开，没有 dispatch 能力。
```

文件名与 trial ID 在上例中是占位符，不是已批准或已执行的运行。
当前默认 `studies/b2-003/protocol-draft.json` 必然返回 `not-authorized`，
而且该检查发生在任何凭据读取之前。已经测试不存在密钥路径也不会被触及。

## 科学检验不是只接收一个 pass 布尔值

`campaign/scientific.py` 要求完整 plan，不能隐式使用上一次阈值：

- task manifest 哈希、reference 版本及实现身份；
- 分开的 explanation / use / regression 任务 ID；
- agreement、prediction coverage、false-feasible 上限；
- median probe reduction 下限，以及保留所有原本可解任务；
- 每项 regression 的预先指定探测次数上限；
- 域外输入与最大 reference/predictor 调用预算；
- 所有条件采用相同的稳定电容升序；不静默替换排序策略。

Formal plan 必须绑定 owner-approved protocol、完全一致的阈值、任务与排序。
正式 explanation/use 不能使用 prior-exposure 已观察任务；blind-transfer 不能
进入资格选择。解释、使用与回归任务集合不得重叠。精确环境 hash 检查不能替代
近重复分析或真实器件独立性，任务族是否科学独立仍须协议与独立观测支持。

每条 reference observation 指向封存 v2 run。错误可行、错误剪枝、覆盖率、
使用探测数、保留可解性、回归与 abstention 分开计算。回传给候选生成器的反馈
不包含 regression / OOS / blind 事实。reference 仍是简化的计算环境；这里没有
把它升级为实测或者独立 full-system 物理验证。

资格期间若进程中断，独占锁释放后仍保留执行起始记录和原始运行。当前会停止，
明确报告本地成本不完整，不自动重跑并丢掉上一段计算成本。这是保守停止边界，
不是已经完成任意资格过程的精确恢复。

## 工程控制与科学证据

`scripts/validate_b2_execution.py` 运行隔离控制，记录源文件哈希、每项测试和本地成本。
覆盖正常恢复、未知 reservation、真实进程退出、费用篡改、模型漂移、输出截断、
只读 CLI、机械失败、成本未确认、错误可行、全 abstain、回归退步、盲测泄漏和
缺少阈值/预算等情况。`engineering-controls` 即使所有分项通过，`qualified`
仍为 false。不会用这些手写 fixture 宣称新知识产生。

```sh
.venv/bin/python scripts/validate_b2_execution.py
./init.sh
node apps/world-studio/development-test.mjs
```

最新投影：`execution-controls.json` 与 `execution-controls.log`；内容寻址存档位于
`.bfworld/execution-controls/<report-hash>/`。现有 Campaign 的恢复/资格详情区显示
同一来源，没有新增页面或部署场景。

## 仍未完成的研究要求

还没有真正由固定 DeepSeek 生成的有效 G3/G4；没有在新的独立 qualification
任务上晋升候选；没有激活新的五条件等预算模型比较；没有 blind Agent transfer、
removal/transplant 正向结果。原有语义补丁的负结果保留，B2 没有标记完成。

下一阶段需要完整正式协议与真实 Agent 设计试验执行链。现有协议草稿仍缺任务
划分、资格阈值、统计口径、排序确认、新运行窗口和精确执行绑定。工程实现不能
替负责人批准这些选择，也不能重置原账本来绕过剩余 token / call 预算。
