# Architecture V2：A、B 完成报告

| 项目 | 结果 |
|---|---|
| A · 源码基线 | 本地标签 `bf-p01-demo-20261014` → `3dc8a72056e85b71998c4160da309474c2cbee1c` |
| A · 工程与运行基线 | 6,388 文件，5.70 GB；包含两份 SQLite 一致性备份、十个原会话、原费用、P01 工程/作业/预览/检查及环境配置；逐件 SHA-256 读回通过 |
| B · 开发源码 | 分支 `codex/bf-architecture-v2`，独立工作树 `/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-architecture-v2` |
| B · 开发运行 | 独立 BF_HOME、SQLite、Pi 状态目录、测试会话；服务 http://127.0.0.1:8870/ |
| B · 工程输入 | 86 个冻结输入、6 个原生工程副本文件；原生副本留待 C 阶段注册独立工程身份 |
| 验证 | 24 项隔离测试、19 项实际接口检查通过；Pi SDK/Agent/Harness 构建成功，实际 SDK 会话保存与恢复通过 |
| 保留 | 原 Demo 8768 与 PID33871、十个原 owner、全部原数据库记录、UNKNOWN、费用与工程摘要一致；7 个原未提交报告单独封存并原样保留 |
| 本轮执行 | 0 模型请求，0 仿真作业，0 目标固件构建；V2 当前关闭模型、Agent 派发及原生写入 |

隔离配置会拒绝生产目录、原 owner、原 EDA UUID 和缺失的运行路径。新旧环境共用主机原生资源锁，已通过跨进程互斥和释放检查。原 UI 六个资源摘要与服务进程回执保持。

Baseline 清单：[manifest.json](/Users/depengsu/.local/share/bf-agent-baselines/bf-p01-demo-20261014/manifest.json)。验证：[result.json](/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-architecture-v2/battery-world/docs/agentlab/architecture-v2/verification-004/result.json)。

源码标签与 V2 分支已在本地建立；V2 新实现保留为未提交修改。

下一步 C：将 P01 已提交候选 `D-c7890e74…` 接入首个 System Commit，保留原采用候选 `D-8a1f760b…` 的独立身份；新增真实专业修改时才产生 Domain Commit。继而推进 D 契约依赖/结果复用、E 专业 Pi 协作、F 回归与集成。
