# P01 预览与版本绑定修复

已发布到 BF Agent 当前页面，保持原有版式。默认查看 **已提交候选 D-c7890e74 · 同版工程**。

| 环节 | 现在可查看的内容 |
|---|---|
| 原理图 | 原生矢量图，可放大；对应 P1.esch2 |
| PCB | 双层走线、正面、背面；对应原 PCB 与 Gerber |
| CAD | STEP 三维预览、俯视／正视／侧视尺寸图 |
| 仿真 | 原 RAW 波形和当前网表 |
| 固件 | 实际 S132 工程源码及 ELF／HEX 等构建文件 |
| BOM | 39 行器件、封装与引脚表，已修复 UTF-16 读取 |
| 文档 | 首版报告直接阅读，并可单独导出 |

三个改动已落地：

1. **补齐预览。** 新增 7 个与源文件摘要绑定的图形预览，保留原始工程下载。
2. **共用系统能力。** 候选读取、预览发布和交付选择放在公共模块；P02／P03 接入时使用各自候选与原作业。
3. **统一版本绑定。** 工程工作区、产品页、交付页读取同一候选清单；已采用版、已提交版和历史记录分别标明。输入摘要变化时拒绝读取旧预览。

检查结果：366 项 Python 回归检查、6 组前端检查、7 个页面预览通过；108 件文件下载摘要和实际导出 ZIP 全部一致。

原工程、原 Pi 会话、费用／UNKNOWN、3 个选定作业、101 件源文件和原首版 ZIP 保留。新增模型调用、固件构建、CAD 构建和仿真均为 0。

含预览工程包：`/Users/depengsu/Downloads/P01_同版工程与预览_20261014.zip`。

复核记录：`live-verification.json`、`ui-verification.json`、`preview-package.json`、`release-tests-reportfix/tests.json`、`node-tests.json`。实际复核命令：`python3 verify-live.py`；回归命令：在 battery-world 运行 `PYTHONPATH=.:tests/agentlab:packages/python/bfworld/src python3 docs/agentlab/p01-mainline-20261013/preview-binding-20261014/run-tests.py`。
