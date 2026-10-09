# BF Agent · 十篇论文的原 Pi 会话文件夹

在 http://127.0.0.1:8768/ 的 Studio 侧栏打开 **2025–2026 论文复现 · 10个 Pi 任务**。文件夹 ID：`folder-e76b14742e431ed5`。十个条目都对应原有 Pi 会话，保留其消息、工程、轨迹、累计费用和实际作业。

|论文|会话|本轮工作|
|---|---|---|
|P01 · TENG 无线微系统|pi-chat-b47a35e335bc68d4|核对 BOM/器件映射；独立原生原理图与 PCB；保存、读回、连通性和 DRC|
|P02 · 矿井 TESS 平台|pi-chat-103e79405f0e0c6d|修欠压首次发送/缓存重试、初始化和 ADC 参考错误；实际 L031 构建与同版交付|
|P03 · 混合采能智能耳标|pi-chat-23f915b7ee4e9fe6|将已核对的 172 份同版文件登记到原产品与交付页；保留 AFE/RF/PCB 缺口|
|P04 · 高速自供能感知|pi-chat-41ef51c671ce114a|用官方寄存器/SDK核对采样时序、中断、输入映射和超长帧；实际目标构建|
|P05 · 道路能量采集器|pi-chat-c5766cc7b28004ae|实际补建采集固件；双触发、噪声、回绕和错误路径检查|
|P06 · 擒纵机械采能|pi-chat-c5fec5f6fc802e72|修 CAD 轴承厚度和轴坐标差异，只重验受影响机械工程|
|P07 · 磁摆电荷分配|pi-chat-2d9cbbc98382d1da|修论文层数/覆盖结构差异，冻结本篇 Pi 工程和原生读回|
|P08 · 多级降压电源|pi-chat-e0028698d50802cb|核对初始储能、功率方向、能量分母和模型边界|
|P09 · 无芯片无线贴片|pi-chat-cb52d6cf20e67841|修适用条件、能量归属和数据对照；不重复未变的计算|
|P10 · 植入接收无线供电|pi-chat-5df297583b1cd187|核对发射/接收电源边界、器件来源和通信矛盾，保留作者固件缺口|

共享原生执行器依次领取这些独立会话的任务。串行调度保留原服务锁；每个论文的上下文、工程身份、费用和输出版本始终隔离。一个论文的 Pi 不会操作另一个论文或旧门磁的原生工程。早先误建的十个 Codex 会话已全部停止并归档，其公共审查产物保留并注明外部介入。

## 读取与续跑

Studio 中查看原消息与实际原生作业；发送修订要求或继续操作进入该原 owner 的队列。观察接口采用 SQLite 只读连接，不构造第二个 Workbench，不恢复或改写正在执行的 Pi 状态。页面事件来自原会话游标。

原会话与队列索引：

`/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/campaign/parallel-20261009/pi-session-index.json`

运行队列目录：

`/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/campaign/parallel-20261009/pi-queue/`

每个条目记录原 owner、论文、公开恢复阶段、操作身份、启动/终止和封存检查结果。重复操作身份不能带不同内容；停止操作取消待领取工作，并在下一模型调用前停止活动会话，保留已派发作业。

执行仍按各原 owner 累计 USD30；本轮有明确六小时续期。按用户指令暂缓 usage 对账，UNKNOWN 及全额预留保持原状。没有新建 owner 来获取新的 USD30，也没有重置账本。

## 交付与声明

每篇独立核对当前源码、原生作业输入、装配身份、实际文件 SHA、公开功能反例和工程包版本。原生工作只在相关输入修改后重验。运行完成、文件门通过、功能通过、产品验收和物理测量分别记录。

`CHECKS_COMPLETE` 只表示本次原生文件门完成；完整产品与物理状态仍由独立检查决定。当前池包含五个完整系统候选与五个专项/替代架构；十个任务不等于十件已验收整机。Pi 的实现、Codex 的公共工具/教师反馈/检查，以及未获得的物理验证分别记账。

## P01 会话恢复

P01 的上一轮 Pi 在交付清理时删除 `.pi/chat-sessions/*.jsonl`，后续追加产生缺头部文件。本轮启动在模型调用前失败，新增模型调用为零。Codex 从该 owner 原 Trace 恢复 1,046 条公开消息及 552 组完整工具调用，原生 `SessionManager` 加载检查通过，仍使用原 session ID 和原 owner。

损坏原文件、旧指针、封存 Trace 摘要、恢复文件与加载/切换回执位于：

`/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/deployment/pi-project-folder/p01-session-recovery/`

这是公开历史恢复，不能声称删除前原始会话文件逐字节恢复。没有重建私有推理。恢复期间工程源码、原费用和旧 Trace 不变。运行目录应保留，交付采用文件白名单排除运行状态。

## 验证与恢复记录

254 项定向检查通过，包含原科学工具回归、原 Pi owner/消息/费用保留、只读 SQLite 写入拒绝、操作幂等、授权范围、版本与原生结果投影。已在实际 8768 页面验证文件夹十条原 Pi 会话，以及 P02 的实际修复过程。没有声称完整 `./init.sh` 健康检查通过。

资格指针：`campaign/native-qualification.json`；激活回执及页面截图：`deployment/pi-project-folder/`。后续只在没有活动原生工作时修改已冻结的公共模块并重新取得资格；任务公开资料及恢复/交付记录单独保存。

刷新当前报告使用 `deployment/pi-project-folder/refresh_pi_state.py` 和 `deployment/refresh_reports.py`。旧报告版本保存于 `deployment/pi-project-folder/report-history/`。
