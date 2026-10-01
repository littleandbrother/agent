# Main nominal R/Q 方法适配器

状态：`supplied-for-local-integration`。基线 `87e7d75`；新协议 `bf-design-main-nominal-rq-3-v1`，每 owner 最多三个新候选。全部新增内容限定本目录。PR1 和旧两候选记录不改、不重新解释。

```bash
python3 -B research/bf-design-integration/verify.py --output /tmp/bf-rq-check-001
```

输出目录必须不存在。适配器验证需要 Python 标准库、Git 与 Node；不安装依赖，不启动服务、模型或原生求解器。测试调用发布版 `check_candidate`、`evaluate` 和 `artifact_view`，传输使用显式合成 fixture。报告记录实际测试数、失败与跳过，以及源码哈希。

## 本地接入边界

`src/method_adapter.py` 接受一个本地协调者提供的 `tool(arguments)` 可调用对象。它返回现有 `bf_engineering` 的 JSON 对象或单个完整 JSON text 工具回复；适配器没有 HTTP、凭据、模型或原生入口。该调用对象的认证、操作授权、后端预算和原生派发由本地 BFA-035 协调者负责。不能把 `evidence_kind` 标签当授权。

```python
adapter = Adapter(owner, "bf_design", existing_engineering_tool, new_ledger_dir,
                  evidence_kind="local_coordinator_transport")
try:
    instructions = adapter.activate()  # 交给本地已有的提示词接入点
    adapter.read_skill()
    job = adapter.run_candidate("candidate-01", candidate,
        rationale="基于已读回观察的修订原因", falsifier="何种下一次反馈将否定预测")
    # 本地已有调度器按需调用 poll；这里不自动等待、重派发或选候选。
    job = adapter.poll("candidate-01")
    # 只有终态且有可核验评价产物，才能调用 submit。失败候选可合法提交。
finally:
    adapter.close()
```

示例只说明调用契约，不是执行许可。云端没有实际连接上述生产工具。首次构造会 inspect 并严格绑定 owner、task hash 和三候选配额；已有但未被同一账本记录的 job 拒绝接管。15 个发布源码哈希发生变化时拒绝加载；本地 runtime 的九项差异须由协调者建立新的兼容性/协议身份，不能删校验或全量同步。

四个 profile 共用同一任务、观察、动作与数值自由度，分别开启 R（关系表示）和 Q（冲突归因/有反证条件的修订）。`activate()` 记录真实 Python 方法函数调用与输出哈希，**不宣称已经交付到 Pi SDK 提示词**；实际接入点由本地拥有。`run_candidate` 保留观察摘要、候选哈希、修订原因和 falsifier；每个工具调用在调用前后写入关联意图与响应证据。它不代替后端预算或验收。

## 账本与产物

新操作在调用前保守占用一个候选机会，最多三次；后端仍是实际计数权威。等待中的 job 仅轮询；超时或未知副作用只能重试相同 operation_id/候选，不能靠改 ID 获取新额度。恢复时从同一哈希链重建状态。每个 ledger 只允许一个写者；异常终止遗留 `writer.lock` 时，由本地协调者确认旧进程已停止再处理，代码不自动抢锁。

终态 job 的 owner、operation、候选、任务与状态均校验；通过发布版 `artifact_view` 的字节 offset 分页读回，验证全文件大小和 SHA-256。提交核对 result/design/evaluation 与后端提交收据；提交意图即冻结选择与理由，响应丢失后只允许同一选择重试。该验证保证本地一致性，不认证能任意重写账本和哈希的攻击者，也不产生独立物理验收。

```bash
python3 -B research/bf-design-integration/src/analyze_ledger.py /path/to/ledger/events.jsonl
```

摘要只读，保留失败和未决动作，费用为未知而非伪造零成本。fixture 始终标为合成证据。

## 所有权和仍未完成部分

本地 BFA-035 拥有生产缓存应用、服务/工具接入、UI、任务/预算权威、原生 adapter、原生通道 sidecar、部署和四轨迹执行。云端不重跑 pilot，不重复创建 vin2/cap 等原生通道工作，也不修改 formatting-only 的 product.ts 差异。`contracts/OWNERSHIP.json` 为归属记录。

`patches/cache-v2-minimal-review.patch` 只供本地审查，测试仅在临时目录应用。保留 fresh/hit JSON 归一化，在现有 owner cache root 下加 v2 子目录；不替换生产 `simulation_chain/__init__.py`，不搬运旧分支的服务实现。

当前只支持 gap、cin、cout、发送间隔四个数值变量；`architecture=false`、`artifact_source_changes=false`。不是 DEV-FEASIBLE/DEV-COUPLING，不具有真实器件选型、物理设计排名、架构合成或 RSI 资格。缺失 piezo 来源原文继续缺失；本地拥有的 native-model-interface sidecar 尚待提供。独立科学比较、实际方法提示词交付和生产调用验证均未完成。

## 传输修复与验证范围

生产 Pi `reply()` 使用 JavaScript JSON.stringify，会将 48.0 变成 48。任务身份仍核对服务器 task_hash，并逐字段核对已哈希绑定的可信任务模板；只接受值相等的有限数值，不把布尔值当数值，不允许多余/缺失字段或数值漂移。内部恢复服务器规范表示，未改服务器协议哈希。Node 回归测试直接提取发布版 reply 函数（仅去除 TypeScript 类型标记），以合成输入覆盖 inspect/run/job/artifact_view/submit。返回提示词、任务、job 和提交证明使用快照，调用方修改不改变账本状态。

**超过 24000 字节的 Pi 回复仍未接通。** 发布版将其保存为 record_file 摘要；适配器记录摘要并抛出 TOOL_SUMMARY_ENVELOPE_REQUIRES_LOCAL_TRANSPORT_BRIDGE，绝不读取该路径。已占用候选保持未决，不能绕过额度。完整生产兼容性仍需本地协调者提供经过授权的完整响应桥接并独立验证；这里没有修改生产包装器，也没有实际 Pi/Agent 轨迹。

## 已保留 passive 数据分析

[分析说明](analysis/passive/README.zh.md) 与 DELIVERY-MANIFEST.json 保留交付原始字节。RESULTS.json、SELF-TEST.json 为独立分析交付方的既有结果；当前环境没有三份原始归档，未重放该结果。该旧 conditional-passive cohort 不是当前 PMIC/native 主线验收或 Agent 收益证据。

可选的便携性冒烟检查需要已安装 NumPy（不会安装依赖）：

```bash
python3 -B -m unittest discover -s research/bf-design-integration/analysis/checks -v
```

该检查仅验证交付哈希、合成数值、缺失/损坏输入拒绝和输出保护。拥有三份未改动原始归档的本地协调者可另行执行：

```bash
python3 -B research/bf-design-integration/analysis/passive/analyze_passive.py --archive-dir /path/to/original-archives --out /path/outside-archives/new-analysis.json
```

归档文件名和固定哈希见分析说明；输出必须为归档目录外不存在的新路径。原版 1 条中断、3 个未运行槽位与修订版 4 条完成保持各自身份。已有的 30 项测试报告保留；后续报告按新目录追加，不把此前有限覆盖解释为生产通过。
