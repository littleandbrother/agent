# B2：语义候选与等条件试验执行

2026-09-07。推进对象仍为 B2-003，没有扩展场景、换模型、追加旧协议付费试验。

## 现在补上的执行语义

`campaign/proposal.py` 将语义生成与机械修复分开。公开历史经过任务、设计、负载与
原始运行绑定检查后，构成独立的 G3/G4 请求。模型可以提出世界模型、文字经验、
工作流，或者选择不更新。引用必须来自输入实验。世界模型的机械检查与工作流
安全检查彼此独立；任何一项通过都不等于科学准入。

语义生成接口复用原 Provider/Ledger 和结算恢复逻辑。新的协议须绑定请求、全部
实现哈希、模型 fingerprint、原账本与明确时间窗。默认草稿不能 dispatch。
目前验证使用隔离 fake transport，未读取真实密钥，未生成真实 G3/G4。

`campaign/trials.py` 实现以下五条件的公共执行核心：

| 条件 | 除共同历史和工具外的输入 | 当前验证范围 |
| --- | --- | --- |
| Raw history | 无预装知识 | 同样允许编写和执行 Python |
| Text lesson | 非空、有历史绑定的文字经验 | 空字符串不能充当记忆条件 |
| Unqualified executable | 经过机械检查但未科学准入的代码与实际调用输出 | 记录输入、代码、输出哈希及调用次数 |
| Qualified executable | 同一代码，另有准入状态 | 当前只验证明确标注的工程激活替身；不伪造正式资格 |
| Exhaustive reference | 固定顺序枚举，同样的实验预算 | 无 LLM；不是第五个“同模型 Agent” |

四个参与者条件共享模型接口形状、原始历史、任务参数、排序、工具、回合与实验
预算；每个试验从一个新消息列表开始。传给参与者的是公开 context，不含标签、
接收端最终结果、确认任务或参考源代码。代码预装执行的额外成本属于处理成本，
不能在后续正式比较中省略。

每次提交必须引用该试验、该任务、该设计实际产生且通过的实验回执。设计在最终
确认中物理通过，但没有匹配实验，也不会被计为证据准入。失败设计的自称成功
保留为 false claim。重复确定性实验单独记录，不能当作独立噪声重复。

全部条件完成、原始消息与动作封存之后才执行最终确认。确认结果不会返回给
候选生成器或尚在执行的参与者。完整重放不再次调用决策函数或参考执行器；中断
且效应未知时停止，保留成本缺口，而不是重新跑完后宣称恢复成功。

## 可以亲自逐项检查的一次执行

```sh
.venv/bin/python scripts/build_b2_trial_control.py
```

输出定位文件：`docs/b2-development/matched-trial-control.json`。
其中 `artifact_root` 指向持久化的控制目录，各层文件依次为：

```text
inputs.json                         公开任务、历史、候选和预声明确认条件
mechanical.json                     程序机械检查
raw-history/request-0.json          系统提示、公开 context、工具与预算
raw-history/action-0.json           决策输出与请求哈希
raw-history/experiment-1.json       预测、观测、回执与原始运行绑定
raw-history/runs/<hash>/            世界、事件、波形、证据与离线 replay
raw-history/trial.json              完整试验、提交与证据匹配状态
其他四条件/                         同一执行接口下的独立试验
learning-frozen.json                所有试验封存屏障
confirmation/<hash>/                屏障之后产生的确认运行
report.json                         分条件计算控制结果和本次本地成本
```

此例使用已经公开的 long-TX 历史、long-sense 任务和 shifted-source 确认，全部是
开发控制，不是新盲集。决策由脚本扫描产生，预装程序故意全 abstain。它展示真实
执行与错误预测的追踪，也展示“调用知识不等于获得知识收益”。不能将此例图表
用作 LLM 改善或迁移成功的实验证据。

## 验证与边界

```sh
.venv/bin/python scripts/validate_b2_execution.py
./init.sh
node apps/world-studio/development-test.mjs
```

新增控制覆盖历史/工具一致、Raw Python、非空文字、代码真实调用、停用处理拒绝、
错误和无证据提交、最终确认屏障、完整重放、中断停止、篡改拒绝，以及语义提案的
预算门、请求绑定、不更新和组件独立性。测试通过证明的是这些执行语义，不是研究
假设成立。

尚未完成：正式五条件的付费决策适配与逐调用对账、独立任务/阈值/统计协议、真实
有效 G3/G4、科学资格、真实 Agent removal/transplant，以及完整成本下的长期收益。
语义生成已有受限 provider 接口，但试验矩阵明确只允许无付费控制回调，不能偷偷
切换到真实模型。工作流的路由安全仍不同于科学使用收益。B2 保持进行中。
