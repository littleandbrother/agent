# BF 第三阶段：受控比较结果

状态：BFA-057/058/059 有限工作包已完成；实际矩阵、保存核验、两稿本地编译及逐页检查通过。阶段出口待审查，下一批派发关闭。

结论：保留原 H。新 H、固定 H0、普通反思均为 12/12 服务成功；新 H 连同提案用了 127 次请求，固定 H0 为 64 次，普通反思为 117 次。没有任务级额外成功或请求成本优势。本批 H 是任务内实例，未形成跨任务复用的全局 H，也未改变 G 或证明 RSI。

正式部分为 4 个固定任务 × 3 次重复 × 8 个条件，共 96 个组、120 个 episode。另有 16 个 pilot 组、20 个 episode。两次 pilot 后因设计或结果不稳定，一次性冻结正式重复数为 3，此后完成全部预登记重复，失败没有补跑替换。complete-raw 是 A 的 fixed_H 与 B 的共同单元；rich-static 是 E4 JSON 共同单元，都没有重复计数。

| 正式条件 | PASS | FAIL | INCOMPLETE | 请求数 | 平均组请求 | 保守费用估计 USD |
|---|---:|---:|---:|---:|---:|---:|
| live-e5 | 7 | 0 | 5 | 80 | 6.667 | 0.782416 |
| proposed_method | 12 | 0 | 0 | 127 | 10.583 | 0.936791 |
| complete-raw | 12 | 0 | 0 | 64 | 5.333 | 0.423181 |
| average-energy | 8 | 4 | 0 | 75 | 6.250 | 0.344513 |
| rich-static | 12 | 0 | 0 | 65 | 5.417 | 0.426720 |
| e4-rich-static-table | 12 | 0 | 0 | 65 | 5.417 | 0.514568 |
| executable-response | 12 | 0 | 0 | 66 | 5.500 | 0.466075 |
| ordinary_reflection | 12 | 0 | 0 | 117 | 9.750 | 0.819012 |

平均能量在两个 reset 任务中各为 1/3 成功，在静态任务与 C-lite 中各为 3/3。完整提供记录、rich-static、可执行应答及 E4 表格均为 12/12。E5 为 7/12 完成真实 propose→qualify→consume→D→独立服务链路；其余 5 个组保留在分母中，其中 4 次来源/单位资格失败、1 次无类型化消费者匹配。成功项为 6 次 selection、1 次 construction，不能写成新物理测量或强静态信息之外的收益。

E4 的 12 个正式配对和 2 个 pilot 配对，解码后的初始信息包及工具哈希全部一致。正式 JSON 与表格均为 12/12、65 次请求，平均 5.417 次；费用和墙时差异仅作描述。后续 acquisition 两臂共同返回 JSON，因此只隔离了初始序列化。rich-static 与 complete-raw 包含全部提供的输入记录及完整模型定义；完整耦合物理 trace 留在 host 侧审计。executable-response 提供候选专属的公开 energy ledger、activity 与 packets。

事件顺序回读找到 4 次 fresh Agent 选择的跨复位待发事件送达：fixed_H 两次、proposed_H 一次、E4 表格一次。它们全部重用同一个历史数字响应：C=10µF，TX=45ms；捕获截至 7.9ms，brownout=12.1ms，RX=46.9ms，复位后没有重新捕获。应记为 4 次选择、1 个不同执行键；固定 passive-latch 机制没有被 Agent 发明或修改，物理记忆资格仍 UNKNOWN。其余正式成功的 83 组在送达前没有发生复位。证据见 ordered-selected-witnesses.json。

107 个已执行组进行了确定性来源绑定审计，其中 91 个 D 改变使旧 trajectory 失效，61 个旧服务标签与实际完整应答不同。这些是保存响应的审计控制，额外科学执行为 0；dependency/scope 保守扩展至同一完整应答，没有局部重算加速证据。28 个 H 配对的信息、初始缓存、工具、模型 alias、新会话与总预算核对均通过，全部拒绝晋升。reflection 正式组包含 2 次 no-update，相关成本未删除。

C-lite 是原案例目录的一项预登记 synthetic DC 单查询派生。查询捕获、固定单次 token、应答时限与新鲜度由新增门控检查；旧相对 deadline PASS 不足以成立查询服务 PASS。固定 seq/key/event=1 仅是虚拟单次查询映射，不证明多查询 nonce 安全、RF 或硬件资格。

全部 140 个 episode 共 771 次 provider 请求，已 SETTLED，保守费用估计 $5.4478605；episode 总墙时 8914.282s，含 pilot。正式请求 659 次，pilot 112 次。该费用使用既有固定费率和 provider usage，不是发票审计；Codex 协助及全端到端成本 UNKNOWN。新增科学执行 57 次（比较 56 + 派生基线 1），native=0，112 个隔离组内累计 122 个逻辑 D 核验，每组最多两个不同 D，初始只读缓存快照一致。

核验：保存回读通过 54 个绑定文件、208 个缓存响应文件、263 个第二阶段清单文件，原始失败和历史 24 条 UNKNOWN 保留，本批 UNKNOWN=0。26 项针对性检查已通过；登记的 S0 architecture-v2-ci 通过 343 项测试和 44 文件/11 控制的保存证据检查。首次集成调用因漏配显式开发 profile 出现导入错误，原日志保留；恢复已登记 profile 后通过。此处不声称 root 全仓、硬件或产品验收通过。

存储：前述集中清理实测 APFS 可用空间净增 12,261,535,744 字节（12.26 GB / 11.42 GiB），见 [集中清理报告](/Users/depengsu/Documents/Long-Horizon AI Agent/docs/storage-deep-clean-20261020/REPORT.md)。最终可用 23,052,652,544 字节（23.05 GB）；本阶段私有记录 58,202,626 字节，provider 运行目录逻辑增长 43,290,453 字节。三现有工作区中的本阶段源码/配置/文档/论文合计约 2.06 MB。本阶段无新环境、工作树或全树备份。两稿构建/栅格临时产物共删除 9,548,636 逻辑字节，该逻辑删除量没有另测 APFS 净释放，不与前述实测净增相加。详细边界、快照时间与后写小型收尾元数据排除范围见 storage-final.json；背景可用空间变化不计作额外清理收益。

论文：[A 稿，5 页](/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-s0-20261019/battery-world/papers/method-reexecution-20261019/phase3.pdf) 与 [B 稿，6 页](/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-s0-20261019/battery-world/papers/interface-sufficiency-20261019/phase3.pdf) 已完成两遍本地编译、全部页面视觉检查、字体嵌入检查、最终 PDF 全文回读及来源字节绑定。最终日志无溢出或未解析引用；草稿修复和首次失败日志保留。A/B 的 13/8 个原准备文件在原工作区与 S0 均保持一致，共享官方英文横版矢量校徽与样式在三个现有工作区一致。只导入 37 个新的纸稿与小型 QA 文件，共 897,083 字节；回执见 paper-readback.json、paper-import-a.json、paper-import-b.json。本批论文仅本地保存，未提交或推送 Overleaf；先前稿件未改。

原 A/R 决定保持 NO_GO、dark-service FAIL、strict FIFO FAIL、NOT_ACCEPTED；用户已确认保留失败基线，服务与 FIFO 要求没有更改。第四阶段选择为 KEEP_UNCHANGED_BASE_H；stage4-selection-freeze.json 中两项未暴露新输入仅用于模型内参数泛化，尚未执行，需独立注册下一批协议。历史 b-esr-fail/b-no-energy 已用过，不能计作 unseen。

核验命令（现有数据只读回读，不运行实验）：

```sh
rtk proxy python3 -B docs/research/phase-plan-20261019/phase3/verify_final.py
```

核心文件：protocol.json、formal-repeat-freeze.json、actual-comparison.json、main-tables.json、ordered-selected-witnesses.json、preservation-final.json、final-integration.json、stage4-selection-freeze.json、paper-readback.json、storage-final.json、result.json、source-manifest.json。
