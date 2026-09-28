# B2-003 · 显式负载、修订负结果与实测回放

2026-09-07。本记录属于公开开发证据，不是新盲测或真实 Agent 学习试验。

## 当前交付

冻结的 `coupled/engine.py`、A-001、B0 与原付费 pilot 保持不变。新增
`coupled/profiled.py` 使用独立版本 `coupled-profiled-reference-v2`，将
boot、sense、infer、TX 时长与功率、接收延迟和冷启动时间变成可执行输入。
采能相位、释放时刻、deadline 也各自有明确字段。源端口、储能、负载、
PMIC 和 MCU 状态继续相互反馈，不使用两个互相独立的平均功率与 schedule。

默认负载重现旧参考的电压与任务结果。仅将 TX 从 40 ms 改为 200 ms，
默认设计会在 0.467 s brownout；释放时刻仍为 250 ms。错误诊断、接收丢失、
迟到与过压分别有负对照。每条新运行封存 world IR、manifest、JSONL events、
Parquet channels、evidence、views、run JSON 与独立 HTML，并测试精确重放。

这不是全新独立物理实现：v2 共享 v1 的元件方程与整数分类器，仍是合成
128-sample 信息任务和简化电气参考。实测导入不能自动给它加上“已校准”标签。

边界负对照还暴露并修复了 v2 的恒功率供给问题：高 ESR 时，即使端口电压
没有低于 off 阈值，也可能已经不能提供请求功率。新执行器以
`constant_power_collapse` 单独记录并终止动作，不能拿最大功率支路的较小
实际功率冒充一次完成的推理/TX。旧引擎未修改，默认域重放一致性继续检查。

## 显式任务与受控修订

运行前写入任务与候选 manifest。三个已公开的旧资格条件，加上长 TX、长采样、
紧 deadline 和改变源相位四个固定公开条件，共 7 条任务、36 个参考设计运行。
旧 `%6` 接口只用于迁移已观测的历史定义；新执行入口接收完整物理 record，
不接收整数任务别名。所有任务保留为 development，没有伪造新的 qualification
或 blind-transfer 集合。

程序输入不包含参考观测、ground-truth label 或接收结果。三种程序得到完全相同
的公开输入，采用原 pilot 的稳定电容升序。仅接口适配的版本会逐项检查其历史
预测和 baseline / learned 探测次数是否与原 pilot 一致。

| 工程诊断程序 | 错误剪枝 / 36 | 错误可行预测 / 36 | 确定性控制器成功 / 7 |
| --- | ---: | ---: | ---: |
| G2，仅接口适配 | 12 | 1 | 4 |
| 只修复 release → TX duration | 0 | 18 | 6 |
| 修复时长并计入 boot/sense/infer | 0 | 17 | 6 |

**没有任何一个诊断程序被晋升。** 这些是工程师编写的消融补丁，不是 DeepSeek
产生的 G3/G4。修复了确定语义错误，并不意味着修复了平均能量判据的全部问题。
重新检查的完整条件还包含信息、时限和交付要求，电气近似也不能独自证明它们。

历史任务的可解性和成本结果：

| 已观测任务 | Raw 探测 | 原 G2 | 两个诊断补丁 |
| --- | ---: | --- | --- |
| qualification-6 | 4 | 过滤全部，失去可解性 | 4，恢复可解性 |
| qualification-7 | 5 | 过滤全部，失去可解性 | 5，恢复可解性 |
| qualification-8 | 3 | 1 次成功 | 3 次成功，局部省探测收益丢失 |

任何“可行”预测都不能直接提交成功，控制器仍须获得匹配的 reference 证据。
因此错误可行预测与错误准入是两个不同量。本次控制器没有错误准入，不代表
候选模型科学合格，也不替代未来盲测检查。

早期开发记录曾用输入 JSON 顺序作控制；现已改为严格恢复原 pilot 的排序，
并新增一致性断言。此前内容寻址目录保留，不把不同排序下的数字混用。

## 移除与移植的当前含义

当前已测试移除代码后回到同一 Raw 顺序，以及只携带候选程序和当前公开任务
在新隔离进程里得到相同输出。程序不依赖原 session 的聊天或历史文件。

这只是可移植性和控制器 plumbing 检验。没有运行新的 Agent 来证明它使用知识
后变强，没有激活新的 raw/text/unqualified/qualified/oracle 模型比较。正式 E/F
仍然未完成，不能将四张控制卡计作研究迁移结果。

## 真实历史测量：可以说什么

只读导入以下明确资产，原目录未修改，未启动设备或操作采集器：

- H13 A128 rep_0003 的 **119,998 个实测电流样本**，原始单位秒、安培，
  约 20 kHz。保留每个原始样本，界面按固定桶保留首／最小／最大／末样本。
- 完整历史 phase ledger、MCU event 文件和原分析程序，含缺失 BLE phase 值；
  缺失值保留 null，不填成零。分析程序仅作为来源封存，不在导入时执行。
- 另一场实验的 **808 行 TX–RX 对齐日志，其中 777 行为 payload 与 host-window
  匹配**。这不是全链路 PDR，不能将 callback offset 称作空口时延。
- 原 wiring / collector / receiver metadata，以及一个明确标记不同步的 PPK
  缓存 manifest。没有导入该缓存的原始二进制用于推导动作能量。

电流和接收日志来自不同实验，不拼接为一个硬件 episode。原 phase-energy
分析使用给定电压和波形唤醒特征对齐，不是同步电压/电流测量。当前导入只计算
电流及电荷统计；**实测电压、实测能量与硬件任务准入均不可用或为 false**。
供电隔离、整板能量、真实输入标签和同步接收链仍需独立确认。

`measured-replay.zip` 保存固定白名单文件，含原始日志与 manifest，支持脱离
硬件目录恢复和审计。网页只展示聚合接收状态，不展示 receiver 地址。原始包
仍含实验主机/session 元数据，不应未经单独脱敏直接作为公开数据集发布。

## 可视化与复现

现有 Campaign 页面增加两个区块，没有新增 3D 部署场景：

1. **A fix is not yet knowledge**：三个补丁、完整参数、源绑定波形、失败游标、
   code diff、每条决策与 Raw / code / removed / detached 对照。
2. **Real traces. Explicit limits.**：真实电流及极值跳转、接收聚合、缺失值、
   来源哈希和明确的测量边界。

```sh
.venv/bin/python scripts/build_b2_profiled.py
./init.sh
node apps/world-studio/development-test.mjs
node apps/world-studio/campaign-test.mjs
```

正常 Studio 构建会恢复本地封存测量包，不扫描外部硬件目录；profiled 运行和
机械程序控制支持按输入及实现身份缓存。构建报告记录该次生成的 wall / parent
及 child CPU，**不涵盖历史研究、人工开发以及后续重复审计的全部成本**。
本次新增付费模型调用 0，原账本未扩展或重置。

主要证据：`profiled-report.json`、`measured-import.json`、`measured-replay.zip`、
`browser-validation.json` 与相应 immutable artifact 目录。

下一项研究工作是：基于这些结构化反例，由真实 Agent 提出机械有效的新模型，
在已批准的新协议下分别检验预测有效性和设计有效性。不能把更换模型、降低门槛、
重复使用已经公开的任务或放宽预算当作修复手段。
