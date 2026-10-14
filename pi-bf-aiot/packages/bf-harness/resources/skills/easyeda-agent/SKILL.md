---
name: easyeda-agent
description: "使用本地立创桌面 typed CLI 操作原理图、器件与 PCB。"
---

通过 `bf_eda` 使用已绑定桌面工程。先查 inspect 的工程身份，当前命令见 [常用入口](references/common-paths.md)。完整上游手册在 `vendor/easyeda-typed/SKILL.md`，按操作加载对应 references。

command 的 argv 不含 easyeda。修改需稳定 operation_id、当前 candidate_id/revision 和 decision_use；重试沿原 ID 查询。UNKNOWN 先读回与对账。

器件查询固定站点/库身份；C 编号、device UUID、symbol UUID、footprint UUID 各用实际字段。核对封装、引脚和网络后修改。

写入后沿 save → reload → read/dump 核对持久化，原理图到 PCB 用已有 import-changes 流程，固定 --no-sync-attrs，再核对差异与 DRC。

结果直接读 native 对象。大结果用 bf_engineering response_view fields=[...]；本地回执用 bf_workspace json。帮助按 CLI/连接器版本缓存，同版本已有内容直接复用。
