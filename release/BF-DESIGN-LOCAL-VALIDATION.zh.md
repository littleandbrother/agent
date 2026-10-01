# BF-Design 本地验证与进度对齐

本分支是待本地验证的 Draft PR，不合并 main、不启用自动合并。原始检查点在 `review/bf-design-checkpoint/`，636 个选中文件保持原始字节；历史结果不是本次运行结果。

## 一个入口

在仓库根目录，选择一个**不存在**的输出目录：

```bash
python3 -B release/validate_bf_design.py --output ../bf-design-local-001
```

本次使用 Python 3.12.14、Node 24.19.0 和现有 NumPy/SciPy 环境。此入口不同于声明 Python 3.11 的完整 Battery World 安装；没有安装或更新依赖。Node 必须支持 `node:module.stripTypeScriptTypes`。受控服务使用 POSIX `fcntl`，本轮在 Linux 验证；Windows Python 路径的字符串转义有回归测试，不代表 Windows 服务运行已经支持。

入口会在现有锁定依赖可用时执行 Pi 离线构建、项目类型检查、合并 overlay 编译与真实零调用服务探针。缺少编译器时会报告 blocked；可先在 `pi-bf-aiot` 执行 `npm ci --ignore-scripts --no-audit --no-fund` 恢复锁定依赖，再回仓库根目录运行同一入口。缺少 Python 包或 Node 时，按日志解决本地依赖后换新输出目录重跑。原始依赖声明位于检查点的 `controlled-integration/dependency-locks/`。入口不会自动安装或升级依赖。

退出码：`0` 表示执行的检查没有失败或材料阻塞，仍须阅读 `unrun`；`1` 表示检查失败；`2` 表示缺少前置材料。本次预期返回 **2**，不是全绿验收。入口不安装软件，不运行模型、供应商模拟器或动态物理试验。

输出：

- `VALIDATION.json`：每项 passed / failed / blocked / unrun 与日志位置。
- `INTEGRATION.json`：检查点摘要、根源码修订摘要、逐文件服务哈希与路径迁移映射。
- `RUNTIME-INTEGRATION.json`：编译及运行时迁移后的新源码/构建摘要；与前一阶段记录分开。
- `service/LOCAL-INPUT-LOCK.json`：本轮真实源码、编译产物、权威输入与测试文件的新锁；不冒充历史封存收据。
- `service/`：第二层服务叠加九文件方法补丁后的源码；`reports/local-probe/RESULT.json` 记录受控服务探针，原生请求必须仍是 BLOCKED。
- `sources/`：独立工作副本；`logs/`：本轮离线检查日志。

缓存 v2 已实际应用到 `battery-world` 的缓存实现、验收路径解析器与回归测试。新命名空间保留旧缓存，缓存返回值必须与已校验的独立产物一致。原 `release/source-manifest.json` 不改写；新增 `bf-design-source-revision.json` 绑定三个有意修订的文件。旧 `verify_source.py` 会如实报告这三个文件与发布基线不同；新入口同时校验未改基线和修订摘要。

整合器先校验所有检查点字节，再验证 layer-02 补丁前哈希、应用最终方法源码、迁移服务 Python 中的已知输入路径。路径按 Python 字符串值重写并检查语法，支持目录名中的引号和反斜杠。权威 world / evaluator / protocol 指向同一工作副本；handoff 通过显式 `pipeline_root` 参数绑定当前仓库，不修改封存 core。历史 JSON 锁、绝对路径与封存收据保持原样。运行时使用另外生成的新本地锁，校验真实构建产物；npm 锁固定依赖版本，但不声称逐字节审计全部 node_modules。

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
| 防覆盖与便携入口回归 | 3 测试通过 | 九文件顺序、旧生成器拒绝、新目录、封存字节、特殊路径与 skipped 状态；同一入口实际执行 |
| Pi 原项目 | 离线构建、项目类型检查通过 | 使用现有锁定依赖；未执行在线模型目录生成 |
| 合并 bf-agent / bf-harness | 编译通过 | 编译最终方法源码，没有调用旧源码生成器 |
| 受控服务 | 24 测试与独立零调用探针通过 | 真实 Pi 进程、方法激活、上传/任务绑定、篡改拒绝与回放；原生请求 BLOCKED，无模型选择动作 |
| 静态 beam ROM | blocked | 缺 `sources/piezo-material-20261001.html` 第三方来源原文；不能删掉来源检查来通过 |
| 磁接口完整回放 | blocked | 缺 `outputs/STATIC-RESULTS.json`、`evidence-completion-replay/RAW-REPLAY-RESULTS.json` 等原结果 |
| Passive、权威 world 完整回放 | unrun | 需要原始材料、传递路径及新执行收据；保留模块独立边界 |
| 仓库 init、真实 participant 隔离 | unrun | 构建和受控探针不代表全部应用健康或不可信参与者运行资格 |
| 原生实验、Agent 对比、H-loop、实物 | unrun | 本任务未授权执行；任务资格、运行隔离、模型/预算与独立验收未完成 |

第一轮曾实际遇到静态 ROM/磁结果缺失，日志保留在 `bf-design-validation-20261001/initial-blockers/`；最终入口在测试前明确列出这些前置缺口。完整原始回放还需要原档案中被有意排除的材料，不能用空文件或合成结果替换。不要把四个 R/Q 条件解释为全部 E1 方法已经实现或比较成功。

后续完整服务检查的收据在 `bf-design-runtime-validation-20261001/`；首次服务测试的两个旧假设失败日志亦保留。最终套件共 164 项测试通过，没有跳过；如本地 unittest 跳过测试，`VALIDATION.json` 将记录 `skipped_count` 并把该项标记 blocked，退出码不会伪装为全覆盖通过。尤其缓存到 deck 一致性检查需要 NumPy/SciPy。

## 两部分统一记录

本地完成后，用同一 Git commit 与 `INTEGRATION.json` 哈希关联两条记录：工程/物理部分记录输入、工具版本、原始产物、失败门槛；方法/Agent 部分记录策略哈希、任务资格、观察与修订、总成本和独立验收。当前只具备上述离线软件记录。

反馈时提供 `VALIDATION.json`、失败项日志、Python/Node 版本和对应 commit。原生原始材料继续留在本地，勿提交凭据、运行数据库、供应商模型/安装包、大型原始轨迹或依赖目录。任何新实验另存新目录；不改历史失败、不提升资格、不把操作者修改称为 participant H1。
