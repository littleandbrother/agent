# R/Q 对比的声明可比性预检

现有协议给出四种R/Q配置和三候选配额；轨迹模块核对单条记录。此模块只补两个独立运行的**配置声明一致性**，不接收实验结果，不重复任务协议、轨迹审计或campaign驱动。当前真实pilot为strong_generic，不作为R/Q比较；本目录没有参与者运行或收益结论。

RULES.json为本次前瞻检查规则，引用原协议哈希。规则在任何真实比较结果输入前固定；这里不声称已有运行采用了这份预注册。后续改规则应产生新规则哈希，不回填旧运行。formal_method_comparison及execution_authorized仍为false。

```bash
python3 -B -m unittest discover -s research/bf-design-integration/analysis/comparison -p 'test_*.py' -v
```

模块仅公开纯函数 `check_configuration.check(pair)`，不启动进程、工具、网络或输出文件。pair恰含两个 `{source_id, sha256, record}`；sha256是脱敏record的规范JSON哈希，规范与轨迹模块一致。返回固定问题类别，不回显非法输入。

record精确字段为run_id、owner、profile、protocol_hash、rules_sha256、method_policy_sha256、max_candidates、identities、budgets。运行ID和owner必须不同；三个候选上限沿用原协议。method_policy_sha256核对现有method_prompt的policy列表，不把两个方法的策略文字要求为相同，也不另造方法。该哈希不是实际提示词交付证明；后者仍需轨迹交付记录。

identities必须按RULES的字段提供可信描述对象的SHA-256；缺少或null保持UNKNOWN：

- task_hash与initial_candidate_hash绑定现有任务及相同基线，当前检查不支持另换初始候选。
- initial_information_sha256：初始公共资料、可见观察及附件身份的完整有序清单；不能只哈希文件名。
- common_instructions_sha256：除受控R/Q策略外的共同指令；observation_policy_sha256：后续信息访问权限和提供方式。分支后不同候选产生不同反馈是正常的，不要求反馈内容相同。
- tool_permissions_sha256：动作、参数权限和观察范围；model_configuration_sha256：供应商/模型版本、采样参数、种子安排及上下文限制。
- runtime_source_sha256与harness_source_sha256：运行来源、依赖/工具身份和H实现。相同运行环境声明不等于相同机器路径。
- cache_policy_sha256：相同初态/隔离策略，不是共享缓存路径；termination_policy_sha256：停止/失败/重试规则；allocation_policy_sha256：运行安排和种子分配规则，不提供随机化实现。

budgets精确字段为model_tokens、model_requests、model_cost_microusd、native_wall_s、total_wall_s，值为非负整数；三候选配额另核对。费用用整数微美元避免浮点混淆。缺预算不补零；测试的全零预算仅为合成无执行声明，没有授权含义。双方预算上限必须相同，但不要求实际花费相同；本模块不检查实际执行账单或授权。

输出状态：MATCHED_DECLARATIONS_ONLY仅表示所提供声明完整且相等；UNKNOWN表示缺证；INCOMPARABLE表示已知差异或双方都为同一profile；BLOCKED表示哈希/任务/方法/配额/结构无效。00与11同时改变R和Q，不能据此分别归因。即使声明一致，也没有认证作者、实际交付、执行预算、封存时点、人工干预或真实轨迹完整性。科学收益、因果、架构和可执行H1均不由此模块判定。

本地BFA-035仍需从真实运行配置导出上述描述哈希与上限，保留来源证明，再提供现有轨迹契约记录。生产桥接尚未完成时，配置预检不能替代桥接验收。只读模块不改任何现有协议或生产文件。
