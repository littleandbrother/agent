# B2：将工作流安全与使用价值分开

2026-09-07。新增 `campaign/workflow_use.py`，保留原 `harness-patch-v1` 安全检查语义。
新的 `scoped-workflow-v1` 将 source/context-version 适用范围与排序策略共同绑定，
调用方不能在资格通过后丢掉 scope 只提取内部 policy。

独立检查的输入只有 workflow、baseline、显式任务、冻结计划、原始 RunBundle 和
成本归属；没有 world-model receipt。因此世界模型拒绝不会阻止检查工作流。
但两个独立检查器也不等于完成了 world-only / workflow-only / joint 的受控实验。

## 已执行的公开诊断

重用 36 份已封存计算观测，不新增参考运行、模型调用或实测数据。

| 固定策略 | 7 条件策略探测总数 | 可解 use 条件探测减少中位数 | 丢失可解任务 | 正式晋升 |
| --- | ---: | ---: | ---: | --- |
| C 升序（无修改） | 22 | 0 | 0 | 否 |
| C 降序 | 9 | 1 | 0 | 否 |
| ESR 升序 | 9 | 1 | 0 | 否 |

q6/q7/q8 在后两项中各为 1 次探测。tight-deadline 无可解设计，仍耗用 3 次探测并
弃权；它不进入“成功任务探测减少”的中位数，但成本和失败保留在完整结果中。
无修改策略不能满足新增 use gate，也不能保持 q8 的一探测要求。

这些策略由工程程序明确提出，**不是 Agent 学习的 G3/G4**。22→9 是在同一组已有
观测上重放路由得到的数量，不是实际发生的 13 次成本节省。两项通过的是公开
工程 use controls；历史成本不完整，正式任务/阈值未批准，所有 `qualified` 均为 false。

这个结果还暴露了重要混淆：简单排序已经足以大幅改善旧基线。后续程序若仅复现
同一收益，不能宣称学到了更好的物理世界模型。需要冻结经典控制并观察机制覆盖。

## 可检查的性质与边界

- 只读取原始 bundle；完整 task/design/load/run hash 绑定，缺失、错绑和路径越界拒绝。
- 控制器保存全部观察，路由只得到当前完成和已验证的 ID；没有提前看完整真值排序。
- 同等目录和基线；可解性、探测收益、回归上限、域外弃权、错误准入各自输出。
- 乱序输入不改变排序结果；不可解任务必须穷尽后弃权，不能凭空提交。
- 工程结果不能自晋升。正式模式还要求负责人绑定候选、scope、baseline、阈值、
  任务、证据、实现、成本归属及窗口，且 use 必须属于未公开 qualification。
- 重放重新核对文件及派生计数，不重复数值求解或付费；已封存报告不得覆盖。
- 适用范围目前仅 source 和 context-version，尚不能声称覆盖连续参数域和复杂
  workflow 策略。当前语义提案协议仍输出旧 v1 策略；将其升级为带范围的新候选
  必须绑定新生成请求，不能事后替 Agent 发明 scope。
- 成本记录覆盖本次审计/策略重放。历史 acquisition 与后续维护仍不完整，不能
  据此给出总学习成本回收时间；没有新的硬件或独立物理实现证据。

## 复现与负责人审阅

```sh
.venv/bin/python scripts/build_b2_workflow_use.py
PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m unittest discover \
  -s tests/campaign -p test_b2_workflow_use.py -v
```

产物：`docs/b2-development/workflow-use-controls.json` 与其指向的内容寻址目录。
目录含固定 control-manifest、每个策略的 inputs/report，以及来源 RunBundle 路径。
Studio 只投影该回执，不在前端重算收益或资格。

下一次正式运行的具体提案见 `studies/b2-003/OWNER-REVIEW-PROPOSAL.md`。原账本仍是
63 calls / 463,487 tokens / ¥1.463445 上界，零未结算；本轮没有读取密钥或付费。
