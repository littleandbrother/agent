# BF/PQE 当前结果归档 · 2026-11-09

本分支保存当前研究结果及其代码，沿用既有 `littleandbrother/agent` 仓库；不改变原实验结果和科学判据。

## 先看结论

最新一轮运行了 12 条真实模型轨迹，各自第一个设计均通过原三个工况。但旧解析器拒绝了模型提出的六次计算调用，而内部策略可以使用计算器，因此**本轮没有完成同等工具能力下的有效比较**。不能以这些平局证明配套递推没有价值，也不能以调用更少或单个紧凑设计证明其有效。

实际配套链曾将读取源从 `contact_only` 改为 `holding_then_contact`，但修改前后完整服务仍在三个工况全部失败。它证明程序路径发生了改变，还没有证明端到端收益。任务和成功历史均已暴露，首设计通过也不能用作未见任务迁移证据。

## 阅读入口

| 内容 | 入口 |
| --- | --- |
| 最新联合修改/配套递推包：结论、失败和更正 | [最终索引](../research/pqe-two-paper-plan-20261022/joint-closure-20261102/FINAL-INDEX.md) · [完整报告](../research/pqe-two-paper-plan-20261022/joint-closure-20261102/REPORT.md) |
| 公共计算器实际不可达的证据 | [比较有效性记录](../research/pqe-two-paper-plan-20261022/joint-closure-20261102/s0/comparison-validity.json) |
| 逐轨迹设计、服务和费用 | [结果数据](../research/pqe-two-paper-plan-20261022/joint-closure-20261102/trajectory-table.json) · [汇总图](../research/pqe-two-paper-plan-20261022/joint-closure-20261102/figures/comparison-summary.pdf) |
| 前一轮反事实、关系合成和 G/D/R 对比 | [报告](../research/pqe-two-paper-plan-20261022/relation-synthesis-20261102/s0/REPORT.md) |
| 最新研究审查状态与阶段方案 | [状态](../research/pqe-two-paper-plan-20261022/review-state.json) · [总方案](../research/pqe-two-paper-plan-20261022/BF_PQE双论文与Agent演进_分阶段执行方案_待确认.md) |
| 上传文件和冻结源的逐文件摘要 | [归档清单](publication-manifest.json) |

最新包计费记录为 21 次 SETTLED 请求，375,381 输入 / 73,299 输出 tokens（合计 448,680，推理 tokens 已包含在输出中），本地费率估计上界 USD 0.2005731，不是供应商发票。54 个逻辑单工况评价中，18 个新完整执行、36 个精确复用；新执行耗时约 56.3 秒。历史 UNKNOWN、预留费用、原始拒绝与错误记录均保留。

## 代码、完整性与使用边界

本次上传最新联合包的完整结果文件、前一关系合成包的可读结果、当前方案与审查记录、较早批次的简要报告和复用代码，以及冻结依赖中实际使用的消费者/适配器代码。消费者位于 `battery-world/packages/python/bfworld/src/bfworld/agentlab/`。本机工作区 `workbench/bf-campaign-s0-20261019/` 在归档中映射到既有仓库根；映射逐项记录在清单。较早包有少量本机云端占位文件或限时读取不可用项，未上传也未删除，逐项列于清单 `unavailable_files`，不将其冒充完整上传。

原始证据中的绝对路径、时间、哈希和接口错误按原样保留。清单中的 `path` 是 GitHub 中的实际路径，`local_path` 是原记录路径。原脚本绑定本机依赖环境与运行账本；本归档提供结果/源码审查入口，不承诺下载后直接重启历史实验。旧大体积原始载荷、供应商凭据、运行数据库和已安装环境未上传；第三方 SDK 只保留原锁定身份，不重新打包。

最新包的 74 项冻结依赖均按原字节核对。较早包的 `historical_usage.py` 随新包增加了已登记的账务例外作用域；其前后摘要与直接授权保留在 [source-amendment.json](../research/pqe-two-paper-plan-20261022/joint-closure-20261102/s0/source-amendment.json)，清单明确标记该历史差异，没有把当前版本冒充较早的冻结版本。

可在此分支检出后做**纯文件完整性**核验：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B docs/github-publication-20261109/verify_archive.py
```

该命令不调用模型、不执行科学仿真、不连接供应商账本，也不修复原解析器。发布动作没有启动新实验或恢复暂停任务。
