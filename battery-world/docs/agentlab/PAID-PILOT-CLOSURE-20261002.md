# 真实 Pi 先导实验完成记录 · 2026-10-02

本轮四条真实 Pi 轨迹均已调用 `bf_engineering submit` 提交实际运行候选，共执行 12 个候选。五个完成联合计算但未满足自供能任务，七个超出模型适用域。没有取得自供能正例。

这次完成的是固定门磁压电器件家族内的反馈迭代先导。它不是完整开放式器件设计，也不是方法优越性、物理合格或 Harness RSI 结果。

## 1. 任务与结果

任务仍是同一次门动作、零初始储能、无外部诊断电流，4 秒内完成至少一个正确报文。环境、材料假设、程序阶段电流、接收条件与求解精度保持冻结。每条最多三个新候选；操作者没有代选下一步设计参数。

| 轨迹 | 起点 | 新候选数 | Pi 最终选择 | 结果 |
|---|---|---:|---|---|
| baseline-r1 | 名义基线失败 | 3 | `eng-552536886002eb42`：48 mm、Cin/Cout 220 μF、间隔 50 ms | completed / unsatisfied |
| baseline-r2 | 名义基线失败 | 3 | `eng-8607242c92ab33fd`：48 mm、Cin/Cout 10 μF、间隔 500 ms | completed / unsatisfied |
| domain-r1 | 28 mm 越界起点 | 3 | `eng-4a11434fc102901c`：42 mm、Cin 220 μF、Cout 470 μF、间隔 50 ms | completed / unsatisfied |
| domain-r2 | 28 mm 越界起点 | 3 | `eng-ecced7e19ea2ae8f`：48 mm、Cin 47 μF、Cout 100 μF、间隔 100 ms | completed / unsatisfied |

四条选择均由 Pi 的实际工具调用写入数据库，独立复核了所有权、任务哈希、结果文件哈希和重新计算的评价。首条提交后的自然语言总结请求又遇到上游错误，因此其对话终态仍是 FAILED；提交回执已经持久化，不能将这两种状态混为一谈。

新发现的 42 mm 候选位于当前 ROM 内：初始位移约 −7.018 mm，峰值约 7.612 mm；储能峰值约 0.067303 V，供电峰值约 1.036e−7 V，仍无完整 TX 或虚拟接收。48 mm、10 μF 的候选储能峰值提高到约 0.455428 V，供电峰值仍仅约 32.50 μV，同样没有启动。

这些结果表明修改确实进入计算，有限搜索中仍未找到符合任务的方案。不能因此证明全部设计不可行，也不能仅凭 VIN 排序宣布改进成功。磁场网格与全旋转 FEM 资格仍未满足，五个 completed 均不能用于物理合格设计排名。

## 2. 真正阻碍实验的执行问题及修复

1. **传输等待被错误截断。** 上游长时间只发 SSE 保活，代理此前丢弃保活，Pi 在收到首个响应头前超时。现在向客户端转发保活；本研究范围内的流式等待最长 1200 秒。上游 90 秒读空闲、客户端首响应 300 秒、后端总流窗口和上游显式 SSE error 分别记录，不互相混称。
2. **工程反馈过大，候选编号丢失。** 超过 24 KB 的 inspect 返回退化为当前受限工具无法读取的路径。现在绑定研究任务的 inspect 使用紧凑索引，保留本 owner 的全部 job ID、状态、参数和评价。60 KB 原生详情夹具下，真实 Pi 仍能读回并提交。通用的大响应分页桥尚未完成，不能说所有大反馈问题都已解决。
3. **串行求解器引发模型重试风暴。** 本轮实际记录了 156 次 `ENGINEERING_BUSY` 工具返回：domain-r1 40 次、baseline-r2 26 次、domain-r2 90 次。后续 Pi 的工具实现会在内部等待容量，使用同一 operation ID 和相同参数，不为忙等待调用模型。真实 Pi 零付费测试中，连续两次 BUSY 后只创建一个候选，总模型夹具调用数没有增加。
4. **已开始新回复却仍显示上一轮失败。** 后续 `assistant_start` 现在清除旧的当前状态错误，保留原错误事件。已完成针对性回归；部署时先确认无在途模型、原生作业和活动会话，再重启服务，没有中断活动计算。
5. **失败与费用未知导致全局阻塞。** 按本轮用户直接指令，仅该研究允许继续，UNKNOWN 原始行及全额费用预留不变。其他研究不自动继承该例外。

## 3. 费用、恢复与研究边界

- 共 244 个实际模型请求，其中 242 个属于四条 Pi 轨迹，2 个是明确区分的传输诊断。
- 本地保守费用上界为 **USD 1.5573279**：已知用量的保守计算 USD 1.3571244，未知用量预留 USD 0.2002035。不是供应商独立账单金额。
- 用户要求优先完成后，既有 USD2 研究额度在四条轨迹间合并使用；没有新增研究总额、清零费用或重置候选次数。原 USD0.50 分配保留在历史授权，重新分配另有追加回执。不可把这一轮当成等成本方法比较。
- 所有原始失败、恢复尝试、最初运行 seal 与后续运行身份均保留。最终 reconciliation 是追加快照，不覆盖失败或迟到结算。
- baseline-r1 有一次人工事实恢复：提供其已有三个 job ID 和状态，没有提供新的候选参数。其余恢复也是操作者发送的继续执行消息；这轮不能称为完全无人干预的端到端自治。
- 方法配置为 strong_generic；19 份关闭尝试与最终快照通过 Dot 轨迹契约的结构一致性审计。模型指令是否准确投递到特定请求、反馈是否被读取及因果利用仍保留 unknown，不用相邻时间或解释文字填补证据。
- 结束时无在途模型请求和原生作业。不自动启动下一轮付费试验。

## 4. 验证与交付

- 最终应用 `./init.sh`：**469 项 Python 测试通过**，SDK / Studio 类型与构建通过，2803 样本复现通过。
- 独立结果审计：4 个真实提交、12 个候选，任务约束、所有权与结果哈希检查全部通过；物理资格不被提升。
- 证据包 215 个文件逐项 SHA-256 和 ZIP CRC 通过；本机 HTTP 下载与文件字节哈希一致。API 实读为 4 条轨迹、4 个提交、12 个作业。未进行本轮浏览器视觉验收。
- 一次使用集成 Pi 路径的测试返回 `PI_PROCESS_FAILED`；改为实际服务使用的 runtime Pi 后 9 项任务回归通过。前一次失败的具体依赖原因未单独确认，失败日志未删除。
- 本轮未进行 Git 提交或推送。

交付位置：

- [证据 ZIP](/Users/depengsu/Documents/bf-agent-workbench/verification/dot-integration-20261002/pilot-evidence-v3.zip)
- [逐运行 CSV](/Users/depengsu/Documents/bf-agent-workbench/verification/dot-integration-20261002/pilot-evidence-v3/runs.csv)
- [候选空间图](/Users/depengsu/Documents/bf-agent-workbench/verification/dot-integration-20261002/pilot-evidence-v3/candidate-map.png)
- [实际修订轨迹图](/Users/depengsu/Documents/bf-agent-workbench/verification/dot-integration-20261002/pilot-evidence-v3/pi-revision-trajectory.png)
- [单次候选联合时间轴](/Users/depengsu/Documents/bf-agent-workbench/verification/dot-integration-20261002/pilot-evidence-v3/candidate-time-axis.png)
- [独立审计](/Users/depengsu/.local/share/bf-agent-runtime/integration-receipts-20261002/independent-final-pi-audit.json)
- [脱敏轨迹目录清单](/Users/depengsu/.local/share/bf-agent-runtime/integration-receipts-20261002/sanitized-terminal-attempts-v2/manifest.json)

ZIP SHA-256：`2ea1cbaf46186ade0201a2394da829e8e7f0533c178ddec123cdc89b9fe3c712`。

## 5. 下一步的工程问题

现在优先检查机械加载/释放时的能量通路，以及磁力 ROM 边界附近的确认充分性。42 mm 提供了新的可计算观察点，但它仍未解决启动问题。应以实际能量账本决定是否开放“加载与释放关系”这一结构自由度，再让 CAD、磁力轨迹、边界功与联合求解共同接受检验。

不要继续用更多电容扫描或更高 VIN 替代自供能事件任务。正式方法比较还需要任务空间内的合法正例、足够的模型确认，以及完整的大反馈获取与请求交付证据；这轮的恢复与调度修复应先固定成稳定执行版本。
