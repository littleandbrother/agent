# BF Agent 本地立创桌面接入

目标宿主为嘉立创 EDA 专业桌面版。本机已确认 ARM 4.1.71、半离线模式。BF 使用 typed easyeda-agent CLI、单一 localhost daemon 和固定原生 CLI 提供程序；BF 不自动回退 Web。旧论文工程、会话、费用与冻结资源保留。

## 当前配置

- 运行文件：`~/.local/share/bf-agent-runtime/runtime.json`，`eda.host=desktop`，`eda.modes=[half-offline,offline]`，`eda.transport=native-cli-v1`，启动观察最长 30 秒。
- 本地 CLI/连接器兼容修订：`1.9.0-bf-desktop.1`。源码在 `/Users/depengsu/Documents/easyeda-agent`；本次为本机兼容补丁，没有发布 vendor 版本。
- 后台 LaunchAgent：`com.bf-agent.easyeda`，监听 loopback 60832；登录本机后自动启动，异常退出自动拉起，关闭自动覆盖本地 Skill。
- 原生适配后台：`com.bf-agent.easyeda-native`，运行哈希冻结的 `native_connector.mjs`，通过同一个 60832 daemon 注册。提供程序版本 `1.9.0-bf-native.1`；当前冻结目录 `~/.local/share/bf-agent-runtime/deployment/easyeda-native/build/1791746940641439000/`。
- 厂商内置 CLI：`/Applications/嘉立创EDA(专业版).app/Contents/MacOS/LCEDA-Pro`，现场版本 `4.1.71.7a7261be`，实际 Mach-O arm64。无需另装同名 `easyeda` 命令。
- GUI 仅用于客户端模式/扩展安装、启用连接与正常退出启动；原生工程操作由 typed 工具执行。

## 核对与恢复

```sh
easyeda health
python3 scripts/eda/manage_local.py status
# 只有后台故障且工程操作已排空时：
python3 scripts/eda/manage_local.py restart
```

健康 daemon 不代表工程可读。查看 `windows[].context.environment` 的真实 SDK `host/mode/version`，须为 desktop 与 half-offline/offline。原生路径须同时具备 `native-cli.v1` capability，窗口 ID 为 `native-cli-<厂商 sessionId>`。关闭的 session 不参与路由；相同工程的两个实际存活 session 仍拒绝含混选择。旧 Connect 的多个 WebSocket 注册不能替代实际原生窗口。

```sh
"/Applications/嘉立创EDA(专业版).app/Contents/MacOS/LCEDA-Pro" doctor
"/Applications/嘉立创EDA(专业版).app/Contents/MacOS/LCEDA-Pro" session list
# 仅操作员在确认不存在重复窗口后，恢复同一个既有本地工程文件：
"/Applications/嘉立创EDA(专业版).app/Contents/MacOS/LCEDA-Pro" open --path /absolute/path/existing.eprj2
```

客户端尚未打开绑定工程时停止设计调用并报告 `EDA_BOUND_PROJECT_NOT_OPEN`；不要重建工程、换 UUID 或让模型不断重试。Connect 和 Run API Gateway 扩展可以保留；BF 本次不依赖它们的 WebSocket 来选窗口。

BF 的 `bf_eda inspect` 返回绑定 UUID、当前兼容窗口与就绪原因；每次原生操作还会用 `project info` 新鲜回读，再在连接器 FIFO 内复核项目身份。窗口重连后 ID 可变化，原工程 UUID 不变；不把旧窗口或同名工程当替代。批处理只接受 typed 数据，保存后重载并新鲜读取，保留 partial/UNKNOWN 操作回执再决定是否补做。

参与者仍只提交 typed argv 和参数文件。适配器使用固定编译的 action handler，经内置 CLI 的 stdin 执行；不给 Pi 任意 JS、shell 或原始 Gateway 执行能力。每个原生 session 的请求与上下文探针共享 FIFO；超时后的写入状态保留在按工程 UUID 索引的 `unknown-mutations.json` 中，后续写入被冻结，重启不清除。每个检查点显式保存；本次不把没有工程身份的后台 autosave 当作持久化证据。

## Skill 与版本

全局 Skill 与 source Skill 已消除 Web-only 限制；BF 只读取本次冻结的项目 Skill/catalog。新本地参考 `vendor/easyeda-typed/references/local-host.md` 按需加载。不会改写历史运行的 Skill 正文或 manifest。旧源码、CLI 与配置均保留回滚备份。

## 登录与能力边界

本地工程应保存到本地工程库，读写与重开流程不依赖反复云登录。云端项目、在线器件库、团队协作、云备份及厂商要求的授权仍遵守其服务条件；本次不保存新密码、不关闭认证、不替用户退出账户。不能承诺厂商云端会话永久有效。

## 验收

桌面兼容补丁的既有离线检查：连接器 680 项、Go 全测试、BF AgentLab 746 项通过。原生 CLI 改动及最终帮助/诊断修正另有 BF 路由/权限/EDA 37 项、固定 JSON 适配 3 项、TS 原生提供程序及宿主事实 6 项、TypeScript typecheck 通过；不把这些局部测试称为新代码的完整回归。

真实 Pi 验证 owner：`pi-chat-d0e795fe9050ec43`。绑定独立本地工程 UUID `6ff3fc5592512d537fcc7a0c7759bc686cdaea5896a84677604c7d2b8718253e`，PCB UUID `6ad2ee48c9cbd6e7`。Pi 已将同一 PCB 的原生板框由 20×12 mm 改为 24×12 mm，两版保存、文档重载及新鲜读回一致；`.epro2` 原生导出、哈希及 ZIP CRC 独立核对通过。后台重启，以及整个客户端实际退出、重启、打开原本地文件后，独立 typed 回读仍为同一工程/PCB、24×12 mm。本次没有重新登录。只授予该独立板框任务的连接/读写/持久化资格。

Run API Gateway 的早期只读探针出现 8 秒和 12 秒超时及一个旧连接错误；完整客户端重启后，精确选择测试项目窗口的只读调用恢复，项目读取约 4 ms。随后使用**同一个冻结 typed 提供程序、同一个 action、同一输入**串行比较一次板框读取：内置 CLI 约 0.546 s，Gateway 约 0.133 s，均通过真实项目/文档/几何核对。Gateway 本次只读，不授予写入、保存、UNKNOWN 处理或同版交付资格，BF 当前仍选择经过 Pi 完整测试的原生 CLI。

已有本地文件的 CLI 打开约 1.3–1.5 秒，但文档重载分别约 28.5 和 32.3 秒。不是完整性能基准，不外推所有工程启动或所有 API 的性能；ARM 与 x86 的观察也不是受控对照，不能据此声称客户端卡顿全部解决。

阶段结果与回执在 `local-desktop-eda-20261012/`，未执行步骤保持 PENDING。该测试只证明本地连接与原生读写，不能作为 PCB DRC、制造、十篇整机或物理验证通过。

详见 [本轮验收报告](local-desktop-eda-20261012/ARM-NATIVE-ACCEPTANCE.md)。原十篇会话、107 项原工程作业、所有既有模型/EDA 行及费用保留；新增模型调用均单独归入测试 owner，不重跑既有仿真，不推广任何论文结果或 RSI 结论。
