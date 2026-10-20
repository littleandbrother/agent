# BF 系统存储清理 · 2026-10-19

**实际净释放 9.0 GB，当前可用 12.7 GB。**

| 清理项 | 结果 |
| --- | --- |
| 重复仿真波形、工程产物、交付及历史验证文件 | 894 份采用 APFS 写时复制，共享 16.1 GB 重复内容；保留文件路径、内容和独立 inode |
| uv / npm 下载缓存 | 已清理；已安装环境和工具链保留 |
| 实际可用空间 | 3.7 → 12.7 GB，按清理前后磁盘实测 |

所有替换文件 SHA-256 一致；Baseline 6,388 件文件和当前 P01 交付 115 件文件校验通过。原十个 Pi 会话、工程、费用及 UNKNOWN 记录保护核对通过；Demo 8768 和 V2 8870 均返回 HTTP 200。

本轮模型调用 0、仿真重跑 0、原始工程文件删除 0。

主要增长来自多目录重复保存波形和工程产物，以及积累的下载缓存。后续产物复制可继续使用写时复制，保留同版证据路径。

回执：[verification.json](verification.json)、[clone-journal.jsonl](clone-journal.jsonl)、[缓存清理](cache-receipt.json)、[Baseline 核对](baseline-verification.json)。复用清理脚本时使用新的 `--output` 目录保存独立回执。
