# BF Agent R0–R2 与 C 案例实施、验收和环境报告

更新日期：2026-10-12。以下结论来自真实源码、不可变回执、原 Pi 公开轨迹、实际编译执行与只读数据库核对。没有使用 harness-creator，没有恢复定时消息，也没有修改历史结果来获得通过。

## 1. 本轮结果和边界

R0 的旧工程保护、R1 的任务／设计／执行／验收身份与 R2 的单 Pi 控制路径已经实现。首个 C 案例在**固定 D5 供电包络与虚拟事件接口**范围内跑通：Pi 读取要求、建立计划、执行候选、观察失败、修改应用 C 源码、重新执行、自行采用并提交同版本交付。独立检查六个门全部通过。

这是一条有真实可执行应用代码的有限数字设计链。执行的是主机编译 C 程序，另产生 Cortex-M4 可重定位对象；不是 nRF52832／S132 的 ELF/HEX 在真实芯片或完整 SoC 模拟器中的执行。供电证据复用既有 D5 固定点，没有重新求解整机。CAD、网表等原参考按哈希引用，Pi 本轮没有重新设计机械、PMIC 或 PCB。

| 维度 | 当前结论 |
|---|---|
| 有限 C 数字工程 | `C-F0-opening-event-fixed-D5-envelope-v1`，6/6 PASS |
| 编译与执行 | 实际主机 C 执行、ARM 对象检查、源码与输出绑定 |
| 事件接口变体 | 两组实际编译接口回放通过；不等于两次实物关门试验 |
| 完整数字产品 | `full_product_passed=false`；SoC、板级接口、RF 与完整负载闭环尚未验收 |
| 实物／制造资格 | NOT_TESTED；PCB/BOM、引脚、烧录、实测功率、物理 RF 保持 NOT_CHECKED |
| Pi／Codex | 应用修订和采用由 Pi 完成；环境、公共起点和独立检查由 Codex 建设；Codex 工程设计动作 0 |
| 方法效果／RSI | NOT_EVALUATED；没有配对收益和后代递归证据 |

用户指出 UI 改动过大后，主页面已恢复原有界面。原来的对话／产品／交付、工程工作区／运行动画、自动收起导航和玻璃按钮均保留。新审查样式不再加载到主界面，仅在可选独立审查页生效。主 `index.html` 与之前版本逐字节一致，SHA-256 为 `5a1f77537c25f07c3eaa2e4fc477d2f47eb8ba2b8a2e0e4b42f4962e3f9a078e`。

## 2. 工作树和保护对象

实施工作树：`/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-refactor-r0-r2-20261011`。分支：`codex/bf-design-lab-r0-r2-20261011`。原实现仍在 `/Users/depengsu/.local/share/bf-agent-integration-20261002`，起点提交 `7e4aaff8294bf445d3ebd7d5e65028a43eff07ff`。未提交或推送本轮修改。

批准计划：`/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/review-packages/BF_Agent_Refactor_Implementation_Plan_20261011.md`，SHA-256 `9ccf08b29ae61bcc882ed77c73d958d35c5b7d73f787a44f760810264a389099`。所有实施归属于 `project/features/BFA-035-dot-integration-pilot/design-lab-r0-r2.json`，父 BFA-035 保持未完成。

R0 捕获了旧状态、原工程、D5 参考和费用记录；所有数据库核对均使用 `mode=ro`。生产启动只有一个明确的 Workbench，没有为查询创建第二个可恢复状态的实例。

最新保护核对：十个原论文 owner 的 **5957 条完整费用行**、跨库 **21 条历史 UNKNOWN 完整行及预留**、原目录 **123 个 Python 文件**、十会话索引、D5 **25 个冻结小文件**均与 R0 相同。两个大型 RAW 的完整 SHA 回读已在 R0 封存；后续没有为了整理流程再次读取全部 RAW 或重跑已通过仿真。十个原论文会话未被替换、合并或启动新 Codex 论文会话；旧门磁 owner `pi-chat-8ae12ef0354d33bb` 未恢复。

费用、累计 token、请求数与总运行时间均按用户明确授权取消上限。历史授权、UNKNOWN、失败和账本保留。单个编译／工具动作仍有资源 containment 和无进展停止条件；这与偷偷恢复累计上限不同。

## 3. R0–R2 的源码落点

下面路径相对实施工作树中的 `battery-world/`；Pi 路径相对同级 `pi-bf-aiot/`。

| 模块／函数 | 职责与实际约束 |
|---|---|
| `agentlab/design_lab/baseline.py`：`capture`、`environment`、`rows_receipt` | R0 来源、旧目录与账本基线；只读核对，不恢复旧任务 |
| `contracts.py`：`contract`、`snapshot`、`check_snapshot`、`acceptance` | Task/Design/Environment/Validation/Check 身份和范围；阶段、完整产品、物理、方法结论分别记录 |
| `case_c.py`：`build`、`verify_build`、`execute`、`evaluate` | 沙箱编译实际源码、执行程序输出事件帧、固定负载逐样本核对、独立解码与验收 |
| `service.py`：`run`、`verified_result`、`adopt`、`submit`、`delivery` | 幂等执行、原始回执校验、CAS 采用、同版本打包、下载前版本和哈希再核对 |
| `service.py`：`worker`、`execute` | 单串行 worker，共享工程锁与跨进程锁；关闭后的线程不重建已删除的测试数据库 |
| `controller.py`：`freeze`、`start`、`_run` | 冻结实际执行的 H、一次 Pi SDK 控制路径、WAIT／事件恢复、每次尝试的不可变 Trace |
| `resources.py`：`bundle`、`load` | 两项版本化设计方法；精确目录、名称、版本与内容哈希；错误名称明确拒绝 |
| Pi `packages/bf-agent/src/design-task.ts` | SDK session 指针、恢复消息、DefaultResourceLoader、实际请求投影与审计 |
| Pi `src/extensions/bf-design.ts` | `before_agent_start`／`context`／`tool_result` 挂钩及 `bf_design` 操作接口 |
| `server.py`／`chat.py` | 加性 C 后端与对应原 owner 路由；原论文路径保留；Studio 只投影事实 |

正式源码前缀为 `packages/python/bfworld/src/bfworld/agentlab/`。交付包同时包含当前源码与**实际付费运行时**的独立源码快照，避免将后来修复冒充当时执行的版本。

幂等性不是单纯复用一个请求名字。相同 Task/Design 的已成功、排队、运行或 UNKNOWN 操作即使换请求名字，也返回原操作；输入变更不能拿旧结果通过。

```python
cached = db.execute("SELECT * FROM design_operations WHERE owner=? AND request_hash=? "
                    "AND status IN ('SUCCEEDED','QUEUED','RUNNING','UNKNOWN') "
                    "ORDER BY created DESC LIMIT 1", (owner, digest)).fetchone()
if cached:
    return self.operation(owner, cached['id'])
```

独立接收器从实际发送字节提取事件身份，以事件发生时刻计算截止时间；不能用发包次数或模型口头总结代替正确接收。

```python
decoded = [(e, decode(e['payload_hex'])) for e in execution['transmitted']]
delivered = [] if link_loss else [(e, d) for e, d in decoded if d is not None and
    event['time_s'] <= e['time_s'] <= min(task['event']['deadline_s'], event['time_s'] + .5)]
unique = {(d['event_id'], d['kind']) for _, d in delivered}
```

采用候选不被强行等同于全部通过：Agent 可以采用一个待继续修订的工作版本；提交交付则必须有当前设计、独立检查、完整证据绑定。工具不能替 Agent 选择下一设计，检查器不能被参与者自己颁发 PASS。

## 4. C 案例实际运行

原 Pi owner：`pi-chat-3faf3eb798e76401`。Task：`task-C-5dc91031091cb217b13d`。

| 对象 | 精确身份 |
|---|---|
| 实际付费运行 H | `H-307cc21a4f22f17158eacf7d0b59b68d0b8ef3e28a4d5bdf713e5d7947892358` |
| 初始设计 | `D-3ff37001ad8a44e4e4c281d7947fffe4f764c31f55eba4f3ddbaa99dda19483f` |
| Pi 修订／采用设计 | `D-bb9b84f05fa3155828bb7ff007c917deb82a56de78d477d21f54f4d96a3c4b66` |
| 固定环境 | `E-9f334232e587481af84df127232ea03b790b5b5dc58ac12a59c24e4df9fdebfe` |
| 环境资格 | `Venv-07fe347b03202a36d1cbafe6b14220373f1cadc59e968e56497b70b99646518e` |
| 采用时独立检查 | `V-4da8e33cb24a898a641d5e4949bff0c56bfef92c5736095001ceb01aa7553218` |
| 提交 | `S-5fd2e7de6f21293cb287c7d7e42ebe8f736ca6ceea02da15caffba202cef26f1` |

模型保持 `deepseek-flash` 与 high thinking，实际运行约 **97.133 秒，17 个 SETTLED 请求**。Pi 初始代码产生错误的 BFD2 帧，三个事件门失败；Pi 根据真实反馈修改 C/H，使用 BFMC 协议、uint32 事件身份、锁存和去重，再冻结、执行、观察、采用并提交。没有教师提供下一组源码或逐步修复指令。

两个操作状态均为 SUCCEEDED，因为编译／执行成功；初始操作的功能检查仍为 FAIL。修订后六门为：源码构建绑定、固定供电负载、事件身份、接收时限、应用去重、参考完整性。随后只读独立回读再次得到六门 PASS。

开门事件发生在 **2.5 s**，虚拟接收在 **2.859 s**，响应延迟是 **0.359 s**。65001 个时间／电流／状态样本与冻结 D5 波形一致，因此复用原生固定点见证；新增原生模拟求解 **0**。接口变体覆盖另一个 ID 和 uint32 大 ID／事件类型，但只是建模接口一致性，不能外推为实际关门供能合格。

同版本交付 `refactor-r0-r2-20261011/trial/C-digital-design.zip`：4,561,507 字节，SHA-256 `f9833dd76cce8116e3bd098e4a0b7703357329431b250bb0e55560f8580e5ecb`。包含采用源码、冻结设计、实际构建／执行／检查、CSV 和原参考依赖。大型原生 RAW 仍以不可变本地依赖引用，不声称 ZIP 是完全脱离本机的硬件复现包。

## 5. 恢复、上下文与实际成本

本轮真实请求中有七次无效工具调用：猜错技能 ID、四次漏 `job_id`、缺 `parent` 和缺 `rationale`。这些不是隐藏失败。后续在 WorkingView 中提供精确技能目录、完善字段错误反馈、保护标准技能激活内容，并将旧 UNKNOWN 聊天传输中的原目标作为恢复上下文；**provider UNKNOWN 费用／请求不被自动重试**。

最新零模型恢复 H 为 `H-2336102e0d2205ae25dac2c2453595384ffb512e5e7dca8c5add1d304fb5808c`。真实 SDK 原会话恢复 **44 条消息**，采用设计、修订号 2、提交、费用行与两个操作均保持不变；新增模型和工程操作为 0。每次恢复另封存 `trace-sealed.jsonl`，不以可变顶层指针冒充历史付费 Trace。这个 H 的恢复测试不能被记成 H307 的付费求解效果。

上下文压力测试确认两项已激活技能存在于请求中，但在当前轮消息本身约 194 KB 的反例中，40 KB 投影目标仍 `fits=false`。因此已经证明的是技能保护和原目标恢复，不是所有输入均有硬上下文上限，也不是已证明费用下降。长当前轮如何归档并按需取回，需要另行限定并比较，不应无声删掉当前工具证据。

| 本轮成本观察 | 数值／口径 |
|---|---|
| 本地保守登记费用 | USD 0.1348554，原账本保持 |
| 缓存感知价目估算 | USD 0.06862308，非供应商实付账单 |
| Prompt／completion | 378310／17802 tokens |
| Cache hit／miss | 225280／153030 tokens |
| 冻结估算费率 | hit 0.006、miss 0.30、output 1.20 USD／百万 tokens |

一次小案例没有等模型／等工具／等输入对照，不能据此声称方法降低了花费、长期提高自主性或完成 RSI。Pi 中间公开说明也并非始终中文；这项风格约束仍需观察。

## 6. 设计、执行和验证环境

已完成九个无 Agent 正／负控制：正确参考通过；错误帧失败；新 ID 与接口类型通过；丢包失败；零供电和发送中掉电不交付并保持不可评价；旧构建拒绝；变更负载保持 UNEVALUABLE。没有付费调用或旧整机重算。环境资格不授予任意 C 电流模型、任意机械输入或真实 RF 的资格。

环境还暴露并修复了两项公共配置问题：旧 ST 工具链为 x86_64，在当前 Apple Silicon 上报 `Bad CPU type`；位于用户目录的编译器标准头文件又不在原沙箱只读范围内。已另行安装**官方 Arm 14.2.Rel1 的 darwin-arm64 工具链**，对照官方 SHA-256 后才解包。原工具链、旧失败日志与原固件作业均保留。

新归档 SHA-256：`c7c78ffab9bebfce91d99d3c24da6bf4b81c01e16cf551eb2ff9f25b9e0a3818`；gcc SHA-256：`07bfe9e74cfe028af639bf38703b2259c608aedee6ff991752084a10b82da614`。仅把编译器的 `lib`、`libexec`、`arm-none-eabi` 加入对应固件动作的只读依赖，不放开用户目录、网络或写权限。负控制确认同级私人目录仍不能被 include。

第二轮完整应用检查另外暴露了旧 Pi `chat-product.ts` 的文件路径错误：三个方法模块哈希点直接使用 URL 的 `.pathname`，将目录中的空格保留为 `%20`。已改用 `fileURLToPath(new URL("./research-method.js", import.meta.url))`，仍检查同一个真实模块 SHA，未绕过方法版本校验。失败运行和带 stderr 的诊断封存；原有十项公开夹具集成检查恢复通过。此修复属于 Codex 环境维护，不是 Pi 的设计失误或自改进。

官方来源：[Arm 安装说明](https://learn.arm.com/install-guides/gcc/arm-gnu/)；确切归档、校验地址与二进制版本记录在 `verification/native-arm-toolchain.json`。新工具链通过六组临时构建／SIL 控制，不自动替换已封存 S132／特定厂商工程的 GCC 版本资格。C 案例仍使用其原有冻结编译环境。

| 检查 | 结论和实际含义 |
|---|---|
| R0–R2 针对测试 | 114 项 Python 通过，bf-agent 类型检查与独立审查 JS 语法通过 |
| 无 Agent 环境控制 | 9/9 正确通过或正确拒绝；已封存 |
| C 原生执行独立复查 | 六门 PASS，接口 2/2；0 新模拟求解 |
| 原会话零模型恢复 | 44 消息；账本、采用设计与操作未改变 |
| 六组原应用构建／SIL 回归 | 全部通过；包含新编译器只读依赖与拒绝私人 include |
| 根科学仓库 `./init.sh` | 实际运行：1145 tests，6 FAIL、6 ERROR、4 skipped；冻结父证据／资格锁／旧快照问题未改写 |
| 首次应用完整 `./init.sh` | 912 tests，5 FAIL、8 ERROR；旧工具链／旧提示词断言等失败保留 |
| 更新环境的完整应用 `./init.sh` | **完整通过**：915 Python tests、应用 TypeScript SDK、World Studio 类型／构建、2803 原始样本与投影；总约 391.8 s，0 外部模型调用 |
| Pi SDK 全库类型 | 此前全库检查有 Request／Response 等基线错误；本轮针对 bf-agent 通过，未重新授予整个 Pi SDK 全库通过 |

根科学仓库原有锁定证据不属于本轮 C 装置修复范围。没有改变冻结语义、删掉失败或降低门槛来获得全仓绿色；目前不授予整个根仓库健康声明。

完整应用成功回执：`verification/native-environment-1791737026653149000/report.json`，日志保留所有原始输出。此前 `native-environment-1791736527164486000` 的 915 项中一个 URL 路径失败，以及更早 912 项旧工具链失败均保持。应用的 World Studio 构建检查是环境回归，未将该页面替换为 BF 主界面。

`environment-snapshot-1791737166918942000.json` 核对当前 Clang 二进制与 MacOSX26.4 SDKSettings 的实际 SHA、Node 二进制／版本、Pi lock 和三个 SDK 解析路径／版本／摘要。依赖仍使用当前固定的本地安装；没有声称离线干净重装可重现已经验证。

## 7. 可重复命令与证据入口

在实施工作树 `battery-world/` 内执行，使用既有 Python 3.11 虚拟环境；macOS 主机需允许沙箱 C 执行。以下均不派付费推理、不重跑旧 D5 原生求解。

```sh
rtk proxy .venv/bin/python scripts/design_lab/verify.py --native
rtk proxy .venv/bin/python scripts/design_lab/verify_environment.py
rtk proxy .venv/bin/python scripts/design_lab/preservation_check.py
rtk proxy .venv/bin/python scripts/design_lab/recovery_check.py
```

完整应用检查：`rtk proxy .venv/bin/python scripts/design_lab/verify_environment.py --full-init`。首次环境跟进时的一次 ARM 环境变量错误、一次标准头文件权限错误和旧断言失败均作为 Codex 环境问题保留，不记为 Pi 设计错误。

仅在原生产服务排空、owner／账本／哈希已核对后发布：`scripts/design_lab/deploy.py --apply --toolchain docs/agentlab/refactor-r0-r2-20261011/verification/native-arm-toolchain.json`。此命令是维护动作，不是只读检查。生产仍连接原 main state；十论文 owner 没有被转移或重复派发。

主要证据目录：`docs/agentlab/refactor-r0-r2-20261011/`。

- `baseline.json`：R0 保护对象。
- `trial/independent-review.json`：六门、身份、成本、归因与边界。
- `trial/executed-code/H-307…/`：真实付费运行代码快照。
- `trial/pi-public-trace.jsonl`、`design-events.json`：公开动作、失败、修订和采用。
- `trial/zero-model-recovery-1791736036726117000.json`：最新恢复与 Trace 校验。
- `preservation-final-1791736197850032000.json`：旧 owner、源码、UNKNOWN 和参考保留。
- `verification/`：所有成功与失败测试、原工具链失效、新工具链资格。
- `ui-restoration/receipt.json`、`restored-main.jpg`：之前主界面的恢复和现场回读。

审查 ZIP 只包含公开动作／工具事实和指定证据，不包含密钥、operator token、原始私有推理、整库会话、node_modules 或虚拟环境。

## 8. 下一阶段的测试出口

| 尚未完成的思路 | 进入下一阶段前所需资格 |
|---|---|
| 修改真实负载／功耗策略 | R3：新负载剖面、重新耦合供电、变化失效、零电能正／负控制；当前固定点只能用于完全相同负载 |
| 完整 MCU／BLE 程序 | 锁定 SDK、SoftDevice、官方引脚和中断定义，实际 ELF/HEX／目标执行、掉电和通信失败反例；ARM 对象不替代 |
| 机械／电路自由设计、A/B 案例 | 每个装置定义范围、原生执行、独立可观察核心门和变化传播；不能直接套 C 的六门 |
| 十论文继续收口 | 沿十个原 owner，从实际未关闭门恢复；当前 R0–R2 没有把十篇重新标为通过 |
| 所有上下文均受控且更便宜 | 对超长当前轮的明确策略，以及相同模型／工具／输入／公开历史的新阶段配对成本与质量结果 |
| 方法采用与 RSI | Pi 提出真实方法补丁，独立回归／新变体／新任务评价，采用后的版本参与下一代；本轮没有授予 |
| 实物产品 | 制造、装配、实测电源、烧录、实际事件和 RF 测量；数字 PASS 保持独立 |

因此，当前可以重复测试的是已声明的有限 C 设计链、恢复、负控制、版本绑定和交付。完整设计空间、物理系统与递归改进需要继续建设并通过各自资格，不能承诺“所有想法已经可测试”。主 UI 后续只作小范围必要接入，避免用界面重构代替工程和方法验收。
