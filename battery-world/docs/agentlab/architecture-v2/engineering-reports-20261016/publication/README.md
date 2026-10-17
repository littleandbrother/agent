# GitHub 发布内容

本次更新包含已完成的 Lab A–D 改版与 P01 工程报告生成能力。沿用 `codex/bf-architecture-v2`，比较基准仍为 `3dc8a72`；原 Baseline 分支保留。

- `../delivery/` 保存最终简版8页、详版29页及其连接电路SVG、时序JSON、CAD/PCB图、图表数据、作者正文、来源索引、模板Skill和质量检查。文件与原 Pi 发布的封存报告逐件一致。
- `../IMPLEMENTATION.md` 记录实现、实际 Pi 消费、测试与工程结论。
- `SUMMARY.json` 汇总实际验证与费用；运行数据库、原账本、完整轨迹、RAW及原生工程保留在本机。
- 共享实现：`battery-world/.../design_lab/repository_reports.py`、`report_assets.py`、`report_render.py`；共享技能：`pi-bf-aiot/packages/bf-harness/resources/skills/bf-engineering-report/`。
- 当前P01供能和PCB待修复、四项工程门待核实；报告如实记录。原工程、十原会话和费用历史保持。

本目录 `source-manifest.json` 记录本次发布的实际Git检出字节。可从仓库根目录运行：

```sh
python3 release/verify_source.py --manifest battery-world/docs/agentlab/architecture-v2/engineering-reports-20261016/publication/source-manifest.json
```
