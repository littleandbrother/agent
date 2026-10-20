# 方法重执行首批

协议见 `configs/studies/parallel-20261019/methods/protocol.json`，全新 BF runtime 为 `/Users/depengsu/.local/share/bf-campaign-20261019-s0`。新工作区的 profile 绑定该空数据库，保护原 V2、生产运行根与 Baseline；原 owner 没有复用。

先运行确定性控制：

```sh
PYTHONPATH=packages/python/bfworld/src python3 scripts/campaign_methods.py qualify
python3 papers/method-reexecution-20261019/render_results.py
```

四次付费尝试采用固定顺序 H0-r1、H1-r1、H1-r2、H0-r2。已登记任务和提示摘要，并冻结每次相同的 16 项原生缓存起点。派发模式要求 S0 先核实会话空位，避免与两个执行会话合计超出三个活跃模型会话。不要把重看回执当作新设计尝试，也不要为复现报告重跑相同成功输入。

`paid/<attempt>/result.json` 只含实际已结束尝试。完整 owner、项目、模型请求、usage 及原生执行回执保留在独立 runtime 的 `trials/` 与 `workbench/`。无结果不补零。账本 charge 是保守费用上界；缓存命中量可用时另列按固化费率估计，均不称为发票金额。供应商提示缓存不可清空，故成本差仅作描述；物理缓存起点则可以且已经冻结。

F1a 小型反馈控制有 6 个输入：固定旧轨迹在 5 项上与完整响应不同，三种保守正确方法在全部输入上相同。边界方法与依赖方法在反馈条件下均退化为完整响应，本批没有测得其独立加速。物理装置仍采用已经资格化的压电/厂商 PMIC/主机 C/数字接收端；新提示 H1 从任务入口运行后才能评价，不用旧设备成绩代替。

H1 是研究者从早期真实失败中提出的全局提示修改。当前未运行 G0/G1 谱系比较，也无未见任务、硬件、递归自改进结论。所有任务是公开开发资产，两篇论文共享机制暴露记录。


## 本批实际结束状态

四个登记 owner 均已实际启动；三次同版交付，H0-r2 在执行完成、验证/发布尚未完成时触发原定 5 GB 余量门槛。停止后不补跑、不更改门槛。全部 68 笔 BF 请求已 SETTLED，费用保守上界 1.142922 USD；缓存命中费率估计 0.350730768 USD 不是发票。没有未结算预留或缺失 provider usage。两次失败工具调用及停止成本都保留在原 owner 轨迹与账本。

H1 两次确认通过，但 H0 配对不完整，决策为 `NO_PROMOTION_RESOURCE_CENSORED`；默认方法不变。旧缓存建设账单 UNKNOWN、研究者提出 H1 的劳动未定价、Codex 主管/执行会话/写作费用不在 BF 账本，不能称为端到端改进总成本。未运行 G，未检验迁移或硬件。

只读复现：

```sh
python3 docs/research/parallel-20261019/methods/audit_paid.py
python3 docs/research/parallel-20261019/methods/verify_artifacts.py --check
python3 papers/method-reexecution-20261019/render_results.py
```

这些命令只读回既有事实并重建报告，不派发模型或求解。`collect` 对停止尝试采用原停止时刻，延迟整理时间不计入 Agent 决策时间。源码和账本原封保留，结束后只对已终止尝试的重复文件作 APFS 克隆并逐件 SHA 回读；第四轮释放共享空间后也没有恢复实验。
