# Pi 会话无限制费用与 token 策略

核对时间：2026-10-09T13:50:23.545603+08:00。

用户直接要求取消累计费用与 token 上限。十个原论文 Pi 会话已应用新授权，BF 新建及现有普通交互 Pi 会话也默认采用该策略。未重新创建论文会话。原单轮128次/原任务24次的模型请求次数限制、单请求金额限制与累计金额/token限制，对这些授权会话均取消，实际有效值为 `null`。未采用极大数字模拟“无限”。

## 当前执行

原 Pi 文件夹：**2025–2026 论文复现 · 10个 Pi 任务**（folder-e76b14742e431ed5）。原生执行器按原 owner 串行调度。P06已产生新的实际模型请求并继续工程复核；P04/P05保留此前 `CHAT_TURN_REQUEST_CAP` 失败回执，已通过原会话消息接口重新排队。P03已有172份文件的同版本清单；文件验收不等于完整工程或物理通过。

每15分钟的线程跟进已启用（`bf-agent`），检查恢复、修复、原生检查与封存交付；仅有实质变化时通知。原运行时间授权保留到 **2026-10-09 17:48:15 北京时间**。本次只取消费用、累计token和请求次数上限。模型固有上下文/单次输出容量、传输超时及原生求解器约束继续作为实际能力边界。

## 权限与账本

- `model_unbounded_policy` 是有直接用户授权、明确scope和 `null` 上限的独立setting。当前study仅绑定十个原owner；旧的冻结实验不自动改变预算条件。普通BF交互默认策略排除已登记的research owners。
- 原 `$30` 授权、配置行和旧回执保留作为历史，新的有效预算由新增授权决定；不重写旧数值或伪造结果。
- 激活前后8,016条原费用记录逐行保持一致；UNKNOWN及完整预留保留。新调用追加记账。暂缓usage对账沿用此前直接用户授权。
- 无相关工程输入变更时复用原成功计算。旧门磁 owner 未恢复，`eng-28deaae4839d843d`、`eng-2a02583017cf031c` 未重跑。

## 验证

174个不调用外部模型的独立测试用例通过：原173例中PaperSessions的15例被最终16例运行替换。覆盖超过旧金额/token/请求次数仍可派发、未授权研究owner仍受原约束、UNKNOWN记录保留、过期运行窗口拒绝、模型上下文限制保留、窗口过期不会恢复取消的金额上限。

8项封存原生校准SHA保持一致，未重跑求解。原生评价器、文件清单检查、原生路由约束及参与者专业指令与维护前一致。发布前所有原生turn、模型请求、工程job均已停止，再切换代码并重新资格化。

隔离目录中的一次全套测试因runtime配置从错误的相对根查找依赖而失败（3 failures、5 errors），记录保留；正式源码根的最终回归通过。未运行完整 `init.sh`，不宣称全仓健康。本次操作不证明任何新的整机功能、Agent自改进收益或物理性能。

## 可复查证据

- [资格与冻结代码摘要](/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/campaign/native-qualification.json)
- [新增无限制授权](/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/campaign/parallel-20261009/unbounded-budget-authorization.json)
- [代码/原生语义/账本发布核对](/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/deployment/unbounded-budget-20261009/release-integrity.json)
- [数据库策略与账本保留回执](/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/deployment/unbounded-budget-20261009/policy-activation.json)
- [发布与实际Pi续跑回执](/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/deployment/unbounded-budget-20261009/release.json)
- [原Pi会话实时索引](/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/campaign/parallel-20261009/pi-session-index.json)
- [十篇最新工程检查报告](/Users/depengsu/.local/share/bf-agent-integration-20261002/battery-world/docs/agentlab/LITERATURE-RSI-TEN-PAPERS-20261009.md)

完整产品验收0，物理NOT_TESTED；Pi设计、Codex运行维护与独立检查分别记录。源码备份、原READY、原资格和旧报告均在本次deployment目录中保留。若未来改变预算策略，应另存授权，不清零账本。
