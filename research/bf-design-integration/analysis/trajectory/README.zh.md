# 方法行为证据审计

本目录只提供脱敏记录的只读审计，不是 campaign driver。真实轨迹尚未提供；SYNTHETIC-INPUT.json 和 SYNTHETIC-AUDIT.json 全部是合成测试，不能填入实际实验记录。

```bash
python3 -B research/bf-design-integration/analysis/trajectory/audit_trajectory.py --input /path/to/sanitized-records.json --out /tmp/new-trajectory-audit.json
python3 -B -m unittest discover -s research/bf-design-integration/analysis/trajectory -p 'test_*.py' -v
```

仅需 Python 标准库。输出必须为新路径；已有文件、链接或目录拒绝，最终独占创建。运行前后核对输入字节不变。记录不完整或哈希/引用冲突返回 BLOCKED；无对应事件的证据层显示 unknown。退出0仅表示结构审计完成，不表示轨迹完整或实验成功。不可加入原始聊天、凭据、隐藏评价或私有工具响应正文。

## 本地需导出的字段

沿用现有 PROTOCOL.json 的 protocol_hash、normalized_task_hash、四个 profile 和最多3个候选规则，不新建任务身份。INPUT-CONTRACT.json 列出每类记录的精确字段集合；未列字段拒绝。顶层必须含 schema、owner、protocol_hash、task_hash、evidence_kind、sources。真实脱敏导出用 sanitized_local_receipts，合成用 synthetic。

每个 sources 元素含 id、sha256、record。id 应保留源账本/收据的稳定标识（字符仅字母、数字、下划线、点、冒号、连字符）；record 含从0递增的 seq、owner、kind、data。sha256 是脱敏后 record 的 Python `json.dumps(sort_keys=True,separators=(',',':'),allow_nan=False)` UTF-8 哈希，不是假称原始文件哈希。JSON 数值须保留该规范表示；此输入契约不是 Pi 的原始 JSON 序列化契约。原始来源与脱敏 ID 的对应由本地保留，不上传敏感内容。哈希证明所交付记录的一致性，不认证记录作者、原始完整性或未导出的历史。

| kind | 本地协调者需要提供的 data |
|---|---|
| configuration | profile、instruction_sha256、loaded 布尔值；仅证明配置载入记录 |
| instruction_delivery | config_id、request_id、instruction_sha256、delivered 布尔值、receipt_id；必须来自实际提示词交付接入点，不可用 activate() 调用替代 |
| candidate_action | operation_id、request_id（未知可null）、完整规范化 candidate、candidate_hash、job_id（未知可null）、dispatch（acknowledged/unknown）、revision_id（无则null）；沿用 bf_engineering 操作/任务ID |
| terminal_result | action_id、job_id、result、result_sha256；result 仅含 job_id、operation_id、owner、task_hash、candidate_hash、status（SUCCEEDED/FAILED）、artifact_sha256；哈希绑定的是脱敏结果对象 |
| feedback_available | terminal_id、接收该反馈的 request_id、delivery_receipt_id、available 布尔值；必须记录反馈实际进入该请求上下文，不以文件存在代替 |
| revision | previous_action_id、feedback_id、request_id、next_operation_id、candidate_hash、kind=numeric；需在下一候选动作之前记录，下一动作引用其ID |
| h_change | authorship（developer/participant/unknown）、artifact_sha256、generation_request_id、execution_receipt_id；未知ID用null，不接收代码或执行 |
| cost | usd（有限非负数）、coverage（partial/complete_trace）；不自动求和，避免重复账单/重叠覆盖 |
| manual_intervention | status（present/none_reported/unknown）、coverage（partial/complete_trace）；未提供时未知，不视作无人干预 |

配置 → 对应请求实际交付 → 动作；旧动作 → 终态 → 反馈可用 → 修订声明 → 新动作，引用都必须指向之前的记录。同请求的指令交付和反馈交付均要在关联动作之前。只有完整链路且候选实际变化才列为 feedback_linked_numeric_revision；仍只证明记录关联，不能证明模型阅读、理解或因果。没有修订声明的候选变化仍报告相对基线差异，不补造反馈关联。

同 operation_id 重试必须保留候选和 job 绑定；不新增配额。未知副作用仍保守计一个不同操作。超过3个不同操作拒绝。只能改 gap_mm、cin_uF、cout_uF、interval_ms；保护字段、非法值和 architecture 标签拒绝，数值变化不叫架构变更。审计不会轮询、重试或启动任务。

## 解读边界

terminal_result_bound 仅核对所提供脱敏结果的哈希、owner/task/candidate/job 和终态一致；外部 artifact_sha256 只是声明，原始产物字节未提供，所以 external_artifact_hash_verified=false。它不是独立原生结果验收。终态失败保留 FAILED；即使终态 SUCCEEDED 也不等于任务满足。

H 记录分开标记开发者补丁和参与者生成声明。只有 generation/execution 的ID不足以证明参与者生成了可执行H1；本审计始终保持 executable_H1_verified=false，且不执行H实验。单条轨迹不建立方法收益、因果、架构能力、RSI 或科学资格。费用和人工干预记录即使存在也只是所声明范围，缺失仍未知。

已有 report_design_pilot.py 负责原有 pilot 报告；src/analyze_ledger.py 负责适配器本地调用账本。本模块只补上述交付/行为证据层，不重跑或替代前两者。生产接入、真实模型和本地四轨迹由 BFA-035 拥有。
