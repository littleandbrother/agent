# BF-Design 本地验证与进度对齐

本分支是待本地验证的 Draft PR，不合并 main、不启用自动合并。原始检查点在 `review/bf-design-checkpoint/`，636 个选中文件保持原始字节；历史结果不是本次运行结果。

## 一个入口

在仓库根目录，选择一个**不存在**的输出目录：

```bash
python3 -B release/validate_bf_design.py --output ../bf-design-local-001
```

本次使用 Python 3.12.14、Node 24.19.0 和现有 NumPy/SciPy 环境。此窄检查入口不同于声明 Python 3.11 的完整 Battery World 安装；没有安装或更新依赖。Node 必须支持 `node:module.stripTypeScriptTypes`。缺少 Python 包或 Node 时，先按日志解决本地依赖，再换一个新输出目录重跑；不要覆盖之前的结果。原始依赖声明位于检查点的 `controlled-integration/dependency-locks/`。

退出码：`0` 表示执行的检查没有失败或材料阻塞，仍须阅读 `unrun`；`1` 表示检查失败；`2` 表示缺少前置材料。本次预期返回 **2**，不是全绿验收。入口不安装软件，不运行模型、供应商模拟器或动态物理试验。

输出：

- `VALIDATION.json`：每项 passed / failed / blocked / unrun 与日志位置。
- `INTEGRATION.json`：检查点摘要、根源码修订摘要、逐文件服务哈希与路径迁移映射。
- `service/`：第二层服务叠加九文件方法补丁后的源码，供继续构建审核；还不是已验收可启动服务。
- `sources/`：独立工作副本；`logs/`：本轮离线检查日志。

缓存 v2 已实际应用到 `battery-world` 的缓存实现、验收路径解析器与回归测试。新命名空间保留旧缓存，缓存返回值必须与已校验的独立产物一致。原 `release/source-manifest.json` 不改写；新增 `bf-design-source-revision.json` 绑定三个有意修订的文件。旧 `verify_source.py` 会如实报告这三个文件与发布基线不同；新入口同时校验未改基线和修订摘要。

整合器先校验所有检查点字节，再验证 layer-02 补丁前哈希、应用最终方法源码、迁移服务 Python 中的已知输入路径。权威 world / evaluator / protocol 指向同一工作副本。历史 JSON 锁、绝对路径与封存收据保持原样，不伪造新锁或既往通过证明。完整 Pi 构建、服务导入和进程测试仍需专门生成新锁并解决传递路径。

旧 `build_overlay.py` 会覆写最终方法源码，故新副本的两个层级与合并服务入口均明确拒绝运行。重新准备只能使用本入口与新目录；原生成器保留在不可变检查点中。独立测试实际读取合并服务源码的副本，整合回归测试验证阻止覆盖且检查点不变。这个保护不是完整 Pi 编译器替代品。

## 本轮进度矩阵

| 部分 | 本轮状态 | 范围与下一步 |
| --- | --- | --- |
| 2877 基线文件、3 个修订、636 检查点文件 | 通过 | 摘要校验；不是功能验收 |
| 缓存/契约 | 17 测试通过 | 包括值篡改、旧命名空间保留、缓存到 deck 一致性；无供应商执行 |
| 方法 Node / Python | 48 + 13 测试通过 | 四种 R/Q 策略、能力门禁、纯函数与新进程监督器；无 Pi SDK 会话 |
| 方法 TypeScript | 4 文件语法转换通过 | 不是项目类型检查或完整 Pi 构建 |
| 因果评估契约 | 14 测试通过 | 合成输入、控制矩阵、能量口径 |
| Native observation kit | 45 测试通过 | deck 静态检查、合成 RAW 解析；不代表 native 运行 |
| 防覆盖整合回归 | 1 测试通过 | 九文件顺序、旧生成器拒绝、新目录与封存字节 |
| 静态 beam ROM | blocked | 缺 `sources/piezo-material-20261001.html` 第三方来源原文；不能删掉来源检查来通过 |
| 磁接口完整回放 | blocked | 缺 `outputs/STATIC-RESULTS.json`、`evidence-completion-replay/RAW-REPLAY-RESULTS.json` 等原结果 |
| Passive、权威 world 完整回放 | unrun | 需要原始材料、传递路径及新执行收据；保留模块独立边界 |
| 完整 Pi / 服务 / 仓库 init | unrun | 仍需新输入锁、编译及受控运行时校验 |
| 原生实验、Agent 对比、H-loop、实物 | unrun | 本任务未授权执行；任务资格、运行隔离、模型/预算与独立验收未完成 |

第一轮曾实际遇到静态 ROM/磁结果缺失，日志保留在 `bf-design-validation-20261001/initial-blockers/`；最终入口在测试前明确列出这些前置缺口。完整原始回放还需要原档案中被有意排除的材料，不能用空文件或合成结果替换。不要把四个 R/Q 条件解释为全部 E1 方法已经实现或比较成功。

## 两部分统一记录

本地完成后，用同一 Git commit 与 `INTEGRATION.json` 哈希关联两条记录：工程/物理部分记录输入、工具版本、原始产物、失败门槛；方法/Agent 部分记录策略哈希、任务资格、观察与修订、总成本和独立验收。当前只具备上述离线软件记录。

反馈时提供 `VALIDATION.json`、失败项日志、Python/Node 版本和对应 commit。原生原始材料继续留在本地，勿提交凭据、运行数据库、供应商模型/安装包、大型原始轨迹或依赖目录。任何新实验另存新目录；不改历史失败、不提升资格、不把操作者修改称为 participant H1。
