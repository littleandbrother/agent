# P01 工程预览与版本绑定 · 2026-10-14

本次源码发布包含 P01 当前候选读取、预览发布、产品与交付的同版选择，以及这些功能依赖的任务恢复、本地 EDA 接口、上下文和按需技能实现。

- 原理图：原生矢量图；PCB：双层、正面、背面；CAD：三维模型及三张尺寸视图。
- 波形、S132 工程源码、39 行 BOM 和报告可直接阅读。
- 工程工作区、产品页、交付页对应候选 D-c7890e74，108 件文件摘要一致。
- 366 项 Python 回归、6 组前端检查、7 个实际页面预览通过；Pi 完整代码检查通过。
- 原工程、Pi 会话、作业、费用和 UNKNOWN 记录保持。此发布新增模型调用、构建和求解均为 0。

[修复报告](../battery-world/docs/agentlab/p01-mainline-20261013/preview-binding-20261014/REPORT.md) · [同版工程与预览 ZIP](evidence/p01-preview-20261014/P01-engineering-preview.zip) · [发布验证](evidence/p01-preview-20261014/verification.json)

原始工程与预览来源记录在包内索引及 source-index.json 中。当前工程仍有源模型、PCB DRC 和板级装配问题待修订；物理验证尚未开展。

复用入口：candidate_results.py、preview_publication.py、result_selection.py 和 scripts/design_lab/publish_candidate_previews.py。P02/P03 使用各自原 owner、冻结候选及选定作业发布预览。现场运行状态、凭据、SQLite、依赖目录和完整历史 Trace 保留在本机。

源码核对命令：`python3 release/verify_source.py --manifest release/source-manifest-20261014.json`。
