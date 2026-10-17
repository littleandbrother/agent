# 当前交接 · V2-P01 两轮完成 · 2026-10-15

- 本次 C–F 的 Power/Firmware 真实消费、连续修订、回归集成与审查交付已完成；三原 owner 均 IDLE，原生队列排空。
- 原 Lead `pi-chat-050766187db5de0d`；Power `pi-chat-0fe155a873295087`；Firmware `pi-chat-62d401bd5fa78a8d`。后续沿这些身份继续。
- 当前提交 `SC-e8f2f2e5b6b4709a69cfbe332fca9e76351764aa11e7a988382e31e2a066d4d9`，父 `SC-a1974dece1a65f85d410d4cd5438f1a72aa7db476da793ddc34e8feab7db56e8`；采用 `SC-4c0da605a4238a3c9d5b5fca8162b7a24e560c8a6a84ef43bcd40339ef771292` 保留。
- 最新第二版检查 `RV-454541ff3ab726d9cc3f69a7fe73d153cad7b6360fc0ed9da19eb65966eb62ef`；发布 `REL-02aae90a976c9447dbd1e936a66d00c4eb911df4a8995bed17ef484bd17d980f`；BF决定 `RETAIN_FOR_REVIEW`。2PASS/2FAIL/4UNEVALUABLE；产品 `REPAIR_REQUIRED`，物理 `NOT_TESTED`。
- 实际构建 `eng-42f734718d566c30` 和 SPICE `eng-2cf474f68315a9d8` 已完成且输入封存；相同输入继续复用。专业新任务要显式重基，不用 reopen 假装切换基线。
- 179 Repository /114上下文回归、Pi构建/类型检查、architecture-v2-lab ./init.sh 通过。旧检查器回执和工程失败全部保留，检查器修正追加新记录，未重跑原生作业。
- 当前代码 `9ec6c22fe9b7af9a5300dfbdaa602113aff9785f` 已加载到 V2 8870/PID92739；原 Demo8768/PID69997保持。最终文档发布可不重启运行服务。
- 原十论文会话、12,454费用行、原P01六件原生文件、Baseline/profile摘要核对一致。329新请求/$7.074384原登记；缓存估算$4.156926，不替换账本。
- Draft PR https://github.com/littleandbrother/agent/pull/3 对比 exact3dc8a72，保持Draft，不合并main或切换默认。后续小提交在同分支进行；发布须核对最新HEAD CI。
- 交付与完整身份见 `docs/agentlab/architecture-v2/v2-p01-20261015/V2-P01-REPORT.md`；audit、cost、preservation、delivery回执同目录。
- 下一轮优先PWL窗口664/672和人工接通模型，随后PCB/器件/装配。专业数值产物只读入口单独立工单。多Agent并行扩展、十篇迁移与方法比较未展开，RSI收益未测量。

---
以下为历史交接，版本和PID以本节为准。

# A/B 开发交接

- 完成时间：2026-10-14T11:05:51.912941+00:00；BFA-036 的 A/B PASS，C–F NOT_STARTED。
- 主机 Demo：8768/PID33871；不得切换它的源码、运行根或原生工程。
- V2：8870/PID50755；源码 `/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-architecture-v2`；运行 `/Users/depengsu/.local/share/bf-agent-architecture-v2`。
- 基线：`/Users/depengsu/.local/share/bf-agent-baselines/bf-p01-demo-20261014`，manifest SHA256 `75933849122ee4102943777ea810528cc72d327ae3715cfa8ff39869260e0cdb`。
- 原 P01 owner：`pi-chat-b47a35e335bc68d4`；十篇会话不迁移、不重开。
- 开发环境测试 owner：`pi-chat-c56ff9ff09147793`，仅环境探测；SDK 两条消息是明确标记的合成持久化输入，无模型调用。
- `profile.json`/`runtime.json` 与工作树 marker 相互绑定；启动统一使用 `scripts/bf_v2_environment.py launch --runtime /Users/depengsu/.local/share/bf-agent-architecture-v2 --background`。
- `BF_RUNTIME_ROOT`、`BF_RUNTIME_CONFIG`、`BF_HOME`、`BF_PI_ROOT`、`BF_DEVELOPMENT_PROFILE` 和 `PI_CODING_AGENT_DIR` 必須显式一致；脚本自动提供。
- A/B capabilities 均 false，原生 UUID 白名单为空；C 阶段按独立发布配置启用所需操作，原 UUID 仍受保护。
- 主机原生锁 `/Users/depengsu/.local/share/bf-agent-runtime/design-native.lock`；typed EDA 写入在 C 的真实副本测试中还需接入同一跨进程租约，禁止并发操作原工程。
- 原生副本目录 `native-projects/P01-B0-copy` 是字节归档，尚未在桌面打开；须通过本地导入获得新 UUID，不能直接登记原 UUID。
- 历史 SQLite 与十个会话备份仅在私有 baseline；开发服务使用全新数据库，参与者只能取得 `inputs/P01` 的86个公开输入。
- 共享已安装工具路径/可执行文件摘要见 `tool-pins.json`。SDK依赖按原 lockfile 离线安装并编译，无 MCU 编译或求解；当前 Node22.22.0，Pi0.85.1。
- 验证命令见 feature.yaml；现有PASS回执 `verification-004` 不覆盖。前三次失败保留：001错误测试任务id、002拦截顺序、003验证脚本误用CJS解析ESM导出；均无原工程/账本改动。
- 源码/状态新修改未提交，未推送；下一阶段沿当前 V2 工作树接续。

C 的第一项工作：在已有 DesignLab 增加系统提交/专业提交/接口契约/集成请求，导入冻结的已提交P01候选。首个 System Commit保留原验收状态（2 PASS、2 FAIL、4 UNEVALUABLE，物理 NOT_TESTED），不重建历史专业提交。采用版与提交版分开关联。接口与专业修订采用CAS和不可变操作记录；从独立测试任务执行。

D 依赖精确复用；E 单Agent串行通过后验证Lead与两个专业Pi；F固定环境回归、发布Identity/Integration和Experiment。不修改基线科学语义，不混入旧十篇 owner 或旧费用。
