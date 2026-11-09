# 联合/递推有限包：执行完成，公平比较被接口缺口阻断

包 `BF-PQE-JOINT-CLOSURE-20261102-001`。12/12 条真实模型执行结束，均在首设计通过原三工况；计费/冻结科学源审计 PASS。**相同能力的比较未完成：公共计算器接口被本地解析器阻断。**

本包精确保留 DOOR/LC 原任务、各三工况和六个共同初态。三组均由同一 API 模型 `deepseek/deepseek-flash`、high 推理配置实际决策；底层权重未披露。314159/271828 是重复标识与控制器种子，不能称模型可控随机种子。
协议要求所有组获得相同原始事实、条件计算器和合法整套编辑权限，以及同一已暴露历史。实际事实与合法设计权限在场，但模型计算调用被旧解析器拒绝；J/C 内部策略能用计算器，所以共同工具的实际可达性没有实现。以下服务结果保留为执行事实，不能作有效同能力消融。

## B 最终复核发现的实质缺口

S0 复用的 `codebt-zeroapi/s0/model_format.py` 在 JSON 与 DSML 两条路径都只允许 `public_object`。新增宿主虽声明了 `candidate_facts/calculate`，合法模型调用仍在解析阶段被挡住。4次已结算回包合计6次 calculate 和同批1次 public_object 未执行；所有原始文本、FORMAT_ERROR 和费用保留在 `s0/comparison-validity.json` 的绑定记录。

这是 S0 的接入与端到端检查遗漏。不能把本地拒绝算成模型/方法科学失败。最初“同底座比较完成、未见递推增益”的表述在此撤回；现有结果只能说明12个实际模型最终各找到一个原任务成功方案。A 的服务读回支持这些原消费者结果，B 的方法读回指出公平比较缺口，二者范围不同。

当前12个episode身份和24个直接软件case已用完，不修冻源后补跑、不救组、不转配额。下一步具体是严格接通三种公共工具的 JSON/DSML 参数校验，用本批已存真实回包做零API端到端复验，随后才可在另行授权的新范围做有效比较。此次未进行这些新检查或新增实验。

## 三层观察（不作有效增量归因）

- G：4/4 通过；逻辑设计数 [1, 1, 1, 1]；真实请求 8；选中递推候选 0。
- G+J：4/4 通过；逻辑设计数 [1, 1, 1, 1]；真实请求 8；选中递推候选 0。
- G+J+C：4/4 通过；逻辑设计数 [1, 1, 1, 1]；真实请求 5；选中递推候选 0。

算参数与联合修改：两个旧失败前缀的联合候选均通过原三工况，C 的相同候选精确复用。这证明新增联合路径在这些已见前缀上可用，并不证明模型自主学会联合策略。 这是开发者/内部工具路径的支持，不能替代真实模型共有计算器的接通验证。
配套递推：实际生成过 holder 职责变化→CONSUMPTION 义务→读取配套修改→候选重检。开发者选择该既有候选执行时，修改前后仍均为三工况 FAIL。不能以静态链或日志变化宣称完整服务收益。
正式轨迹没有选中 J/C 自动候选，未获得真实模型动态机制样本。加上计算器接口阻断，本包不能有效判别递推独立价值，也不能用这些平局证明递推无价值。
这是已见任务、已暴露历史上的开发机制诊断。不能作未见迁移、统计优势、不可行证书、最优性、硬件或 RSI 证据。共同历史包含旧合法大电容成功，所有组三方都可复用；首通过指标受这种暴露影响。

DOOR G+J+C 的一次自由数值设计使用约257µF，其余DOOR为1000µF；该点未选中J/C自动候选且无配套链，不能归因为递推带来的紧凑性。LC最终均为50mF/50cm²。正式三组均首设计通过，当前已暴露历史使效率指标饱和。

## 逐轨迹结果

| 族 | 条件 | 重复标识 | 首通过设计 | 已评设计 | 请求 | 新 full / 复用 | 递推选中 | 终态 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| DOOR | G | 314159 | 1 | 1 | 1 | 0 / 3 | 0 | COMPLETE |
| DOOR | G+J | 314159 | 1 | 1 | 2 | 0 / 3 | 0 | COMPLETE |
| DOOR | G+J+C | 314159 | 1 | 1 | 2 | 3 / 0 | 0 | COMPLETE |
| DOOR | G | 271828 | 1 | 1 | 4 | 0 / 3 | 0 | COMPLETE |
| DOOR | G+J | 271828 | 1 | 1 | 2 | 0 / 3 | 0 | COMPLETE |
| DOOR | G+J+C | 271828 | 1 | 1 | 1 | 0 / 3 | 0 | COMPLETE |
| LC | G | 314159 | 1 | 1 | 1 | 0 / 3 | 0 | COMPLETE |
| LC | G+J | 314159 | 1 | 1 | 3 | 0 / 3 | 0 | COMPLETE |
| LC | G+J+C | 314159 | 1 | 1 | 1 | 3 / 0 | 0 | COMPLETE |
| LC | G | 271828 | 1 | 1 | 2 | 0 / 3 | 0 | COMPLETE |
| LC | G+J | 271828 | 1 | 1 | 1 | 0 / 3 | 0 | COMPLETE |
| LC | G+J+C | 271828 | 1 | 1 | 1 | 0 / 3 | 0 | COMPLETE |

## 真实设计与部件负担

完整候选、设计 diff、父状态、生成来源和完整后果保留在 `s0/trajectories/*/history.json`，汇总为 `trajectory-table.json`。以下是最终选定/最后已评方案的实际参数，不作人为总复杂度评分。

| 轨迹 | C (F) | PV (cm²) | 改字段数 | 新部件 | 生成来源 |
|---|---:|---:|---:|---|---|
| DOOR-G-314159 | 0.001 | — | 4 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| DOOR-G+J-314159 | 0.001 | — | 4 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| DOOR-G+J+C-314159 | 0.00025702811244979917 | — | 4 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| DOOR-G-271828 | 0.001 | — | 4 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| DOOR-G+J-271828 | 0.001 | — | 4 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| DOOR-G+J+C-271828 | 0.001 | — | 4 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| LC-G-314159 | 0.05 | 50 | 7 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| LC-G+J-314159 | 0.05 | 50 | 7 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| LC-G+J+C-314159 | 0.05 | 50 | 7 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| LC-G-271828 | 0.05 | 50 | 7 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| LC-G+J-271828 | 0.05 | 50 | 7 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |
| LC-G+J+C-271828 | 0.05 | 50 | 7 | 无 | FREE_OR_MODIFIED_MODEL_PROPOSAL |

## 费用、资源与失败

新完整执行 18 个单工况，实际 56.300647s；逻辑评价 54（开发 18，正式 36）；精确复用 36。共同初态直接引用，不重跑、不占新设计槽。
便宜数值输入 44/120：A/B/S0={'A': 6, 'B': 13, 'S0': 25}，真实几何 miss 包含在内；精确 memo 和结构检查单列在各 owner 计量事件。24 个登记软件 case：A 2/6、B 8/8、S0 8/10；另 B 有一次进入 case 前的 parse 启动错误。
120 为包总额，启动登记分配 A24/B24/S072；冻结宿主实际以 S0=72 为更严停止门，未热改或转移额度。
A 旧四项失败来自过小光照分段 guard，修订后由 S0 实际 LC 路径覆盖；S0 两项失败来自错误拼接父 ID 和越域测试值。失败原记录不覆盖，修订原因/独立核证在 integration-review.json。未增加第25项软件检查。
真实模型请求 21，全部状态 {'SETTLED': 21}。prompt/completion/total/reasoning tokens = 375381/73299/448680/69907；本地结算估计/上界 USD 0.2005731，不冒供应商发票金额。
启动前的 2026 条完整请求行和原 authorizations 哈希不变。两条旧 UNKNOWN 的原始行、null usage 与 USD 0.3686529 全额预留不变；新请求没有缺失 usage。
新 owner 凭证关闭：True；原预算 scope 恢复；本包自启服务停止。新包保留分配占用上界 42.43MB，当前可用 19.17GB。未新增环境、worktree 或备份。此次是研究执行包，清理释放 0B；前后磁盘可用量差不能冒充本包回收。

末端只读报告首次启动将授权快照标签误当作表名，未执行实验或模型；已使用原historical_usage_exceptions表核得完全相同哈希，原错误保留在s0/report-launch-failure-001.json。

## 证据和复核入口

- 协议：`shared/protocol.json`；登记预算：`shared/registration.json`。
- 实际前后链：`s0/actual-companion-consequences.json`；联合四单元：`s0/development-results.json`。
- 正式结果：`s0/comparison-result.json`；逐轨迹设计/来源/费用：`trajectory-table.json`。
- 完整费用、原行哈希、资源和关闭证据：`s0/postflight-audit.json`。
- 只读核证（零模型/零消费者）：

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B "/Users/depengsu/Documents/Long-Horizon AI Agent/docs/research/pqe-two-paper-plan-20261022/joint-closure-20261102/s0/verify_readonly.py"
```

本包到此停止；不自动恢复旧学习、第二篇论文、清理、自动化或硬件任务。独立 A 服务读回与 B 方法/费用读回，以及此处接口阻断后的结论更正，见最终索引。
