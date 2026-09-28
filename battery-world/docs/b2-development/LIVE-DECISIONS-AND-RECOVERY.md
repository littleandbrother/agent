# B2：逐回合模型决策与恢复

2026-09-07。实现边界从“脚本决策回调”推进到原 Provider/Ledger 支持的逐回合执行。
本轮只运行隔离测试传输；没有新真实模型调用，没有生成 G3/G4 或证明知识收益。

## 新执行路径

`campaign/live_trials.py` 是 v2；上一版已封存的脚本控制及其语义保持不变。

```text
协议、任务、历史、候选、独立资格回执、实现哈希
 → 共同工具与预算 / 分条件知识输入
 → 逐回合模型请求 → 原账本 reserve / settle
 → Python 或实验 → 持久化工具结果
 → 引用同试验、同任务、同设计证据的提交
 → 全部五条件封存
 → 最终确认 → 分条件计算结果与费用
```

每一回合有固定 session、turn、请求哈希、预算和原账本回执。模型能直接看到剩余
回合、实验预算与工具。后续消息必须接续上次实际模型响应及已经完成的工具结果，
不能在中途换历史或塞入最终确认。Raw 同样能执行 Python。Oracle 是确定性枚举，
不冒充第五个相同模型的 Agent。

正式 qualified 条件要求独立科学资格回执，并由协议精确绑定；工程资格替身不能
启用正式模式。两个代码条件使用同一候选。代码实际运行及 abstain 情况会被记录，
但程序被调用本身不是使用收益。正式模式只能使用实际 Provider；模拟传输只能
产生 `provider-controls` 结果，不能更名为真实 Agent 数据。

## 中断发生后怎样处理

| 中断位置 | 已验证的行为 |
| --- | --- |
| Provider 已结算，父级决策文件尚未写入 | 恢复相同回执，无第二次付费调用；父级本地耗时仍未知 |
| 远端结果未知，原账本保留 reservation | 停止，不自动重发；也阻止其他新调用绕过去 |
| 工具结果已完整封存 | 恢复该结果，不再次执行工具 |
| 本地工具是否完成不确定 | 保留起始记录并停止，不用重跑掩盖成本缺失 |
| 全部试验已封存、确认尚未执行 | 从封存屏障后继续；不重新询问模型 |
| 完整试验已完成 | 可在原窗口过期后只读对账，恢复相同结果 |

测试包括真实子进程 `os._exit(72)`，不是只抛出异常；外部响应仍是明确的 fake
transport。历史学习、资格获取和后续审计维护成本没有补造，
`total_campaign_cost_complete` 仍为 false。恢复缺失的 CPU/耗时保持 null，不记成零。

## 一个入口

```sh
# 默认只检查：协议、输入、原账本和窗口；不加载密钥、不创建新账本。
.venv/bin/python scripts/run_b2_trials.py \
  --inputs path/to/trial-inputs.json \
  --protocol path/to/owner-approved-protocol.json \
  --output .bfworld/b2-trial-matrix/exact-run

# 正式 dispatch 需要显式 --execute --key-file path/to/private-key-file。
# 绝不要把密钥正文写进命令、协议或报告。

# 已有执行恢复：同样输入增加 --reconcile-only。
# SQLite mode=ro，无 credential、reserve、settle 或新本地实验能力。
```

输入包含 `plan / tasks / history / capsule / qualification`。当前默认协议草稿仍然
不能通过；输入和路径示例不代表已经批准或执行了正式试验。真实费用仍使用原账本、
每试验 ¥2、总工程 ¥19、120 calls、600,000 tokens 的既有上限，不重新开始计费。

## 可亲自检查的执行样例

```sh
.venv/bin/python scripts/build_b2_provider_control.py
```

定位文件为 `docs/b2-development/provider-trial-control.json`。它指向独立的测试目录，
其中有：机械检查、每条件的 treatment / decision / effect / trial、原始运行、
`learning-frozen.json`、确认运行、总报告和隔离 SQLite 账本。

该示例通过实际 Provider.complete 的 reserve/settle 路径处理 16 次**模拟**响应。
四个参与者条件都经历 Python、失败实验、修订后的成功实验和证据提交；Oracle
使用相同实验接口。实际网络调用和实际费用为零。再次重放不增加账本行。

这里的候选与决策来自明确的测试程序。该样例证明执行和恢复链能够运行，不证明
通用 Agent 学到了知识，也不是后续论文的性能比较数据。测试协议文件带有
`FIXTURE-PROTOCOL-NOT-AUTHORIZATION` 标记，不能用来启动真实调用。

## 仍需完成的科学工作

独立任务划分、阈值、统计口径、正式窗口和实际候选资格仍待冻结；真实 G3/G4、
匹配模型试验、Agent removal/transplant、独立工作流使用收益及跨现实确认仍未完成。
新执行器为这些实验提供可运行接口，但不会替负责人批准协议或替结果通过检验。

验证命令：先 `scripts/validate_b2_execution.py` 刷新来源绑定回执，再 `./init.sh`，
最后运行现有 development / campaign 浏览器检查。B2 保持进行中。
