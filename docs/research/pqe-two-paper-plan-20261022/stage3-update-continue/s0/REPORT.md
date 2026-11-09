# 同一外部发送欠压失败后的两组原方法续行

包：`BF-PQE-S3-UPDATE-CONTINUE-20261023-001`；特征：`BFA-087-pqe-update-continuation`。

原两组各执行一次，均从相同决策前公开状态实际消费同一外部失败，再自主选择新行动。两组最终均在原 Task、服务和动态消费者下取得域有效 PASS，收到 6 条有序记录。固定 H 本次用了一个候选，通用组用了两个；每组只有一个已暴露开发状态的 episode，不能建立稳定方法优势。

| 实际轨迹 | 已评价候选 | 新模型请求 | 新动态输入 | 最终最小 TX 端电压 | 最终独立结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| strong_generic | 2 | 5 | 2 | 2.230695 V | PASS，6 条接收记录 |
| H-decision-conditional-v1 | 1 | 1 | 1 | 2.185206 V | PASS，6 条接收记录 |

共同外部行动原先造成 64 次 TX 欠压、0 接收；其执行和费用已在 BFA-086 记过，本包不重复计数。两组 external-update 的决策前状态摘要均为 `c119babb419d94a41e6a18aa8b5eb10565c8b8ee49abca39adea7973607fa5d2`，消费的同一公共结果摘要均为 `e845203adefa344a242dbf9d23885eead26266fa043e39bd831b31b69fe7aacc`。两组 Update 都是既有实际消费者调用；初始 Update 没有新增模型请求。

通用组先联合改变储能与机构：270 µF、ESR 0.1 Ω、启动 1.9 V、TX 门限 1.85 V、8 mm 行程/8 mm 基圆。虽接收 6 条，但直径 36 mm 超出 35 mm 装配包络，独立结果为 MODEL_DOMAIN UNKNOWN。该 UNKNOWN 是科学适用域结果，与供应商 usage UNKNOWN 不同。随后保持电容与电压门限，将行程改为 7.5 mm，域有效并 PASS6。首次 Select 已在说明中识别包络越界，却仍执行唯一候选，说明仅解释约束尚不能保障行动守约。现有合同允许 non-OK 停止，但不会把“只拒绝当前候选”送回 Generate；合法范围内的几何耦合越界也不属于自动字段纠错。因此还存在单候选、执行/停止出口的接口限制，不能解释成通用组拥有无代价重新生成权而故意不用。

固定 H 下一 Generate 通过模型提出 300 µF、ESR 0.1 Ω、启动 1.9 V、TX 门限 1.85 V、7.5 mm 行程/6.5 mm 基圆的联合重构；独立执行首次 PASS6。其初始 Update 真实触发、写入点范围的 complete_service 反驳，但当时活动变量仍未变化，后续 Generate 才提出机构重构。实际 Generate/Select 没有筛除候选，确定性几何修复及精确失败记忆拦截均未在这条续行中触发。模型所述 r+L 的几何关系对应直径/宽度包络，不能把它改称装配深度的物理因果。每个原始模型候选池均只有一个候选、预测为 UNKNOWN，没有竞争候选或定量后果预测。因此，本次轨迹证明失败反馈进入了后续工程行动；不能把少一个候选因果归于 Update，不能把该模型候选描述成确定性几何修复器的输出。四次模型请求之差包含两次排序、一次停止确认和一次域无效后的重新生成；没有消融隔离 typed memory、固定提示词和采样。

最终两个候选均保存 6 条记录、形成 6 个完整报文且队列为空。TX 期间欠压已修复；剩余的 3 次掉电发生于交付后的 IDLE。原服务、事件保持、期限、装配/力/压力角和独立评价语义不变。一次联合修改也不足以辨认电容或机构的唯一根因。

6 个新模型请求全部 SETTLED，输入 184,614 token、输出 62,362 token；按既有固定费率估算总额 USD 0.1302186，其中通用组 0.0845871、固定 H 0.0456315。这是记账费率估算，非供应商发票。新数值 3，无缓存评价、额外初态/参考/native/硬件/H/G 形成。每组授权 USD5，原冻结 driver 更保守的 USD4 上限保持不变；没有为本包修改方法或预算实现。

原 16 项源码绑定未变。两临时 owner 的凭据和有效 grant 已关闭，study 过期，budget scope 恢复原缺省，0 在途请求。总请求 1914→1920；原 R11 UNKNOWN/null usage/完整预留原行 SHA-256 `256f6c58570f3138a6138291df7137667d2f61c5f8377f7123016fb8bfaee7e1` 未变，无新 usage 缺失。历史精确例外不扩展到其他请求。

直接证据：`final-readback.json`、`runtime-closeout.json`、`batch-result.json`、两组 `external-update.json`/`method-transcript.json` 与实际 actions 的 raw/assessment/public-result。A/B 独立回读与两稿短增量随后绑定到本特征 verification；未重跑科学资格、全仓检查或 `init.sh`，不声称整仓健康。

复现原调用入口：

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B docs/research/pqe-two-paper-plan-20261022/stage3-update-continue/s0/run_continue.py run
```

这是已完成且防重的原始命令；原 run-claim 和原产物保留，重调会拒绝，不能将复现理解为获准重做付费两组。可通过 `final-readback.json` 指定的原文件及摘要离线验证。

新产物约 11.27 MB，在 60 MB 上限内；封账采样可用 43,634,581,504 B。无新环境、工作树、备份、commit/push；本研究包清理释放空间 0 B。此前清理批次的回收量不再累加。

下一步按已授权 M1 执行零付费的动态约束修复工程，保留本包原方法与结果。优先让必要条件真正控制是否执行，并把阶段供电关系用于联合候选构造；不追加同题付费矩阵。工程开发所得解与 Agent 自主结果、自动 H 形成、未见迁移和硬件验收分别陈述。
