> 最新状态：本轮付费先导已完成四个真实提交、12个候选。下文包含早期停止与恢复历史；当前结论和证据以 [完成报告](PAID-PILOT-CLOSURE-20261002.md) 为准。无自供能正例，P3/P4仍按条件推进。

# BFA-035：共同基线、原生观察与真实 Pi 先导

2026-10-02。本轮是开发集成和受限名义模型先导。尚未完成四条 Pi 轨迹，不构成器件架构综合、方法优越性、硬件确认或 Harness RSI 的证据。

## 当前交付状态

| 工作包 | 已完成 | 保留的门槛 |
|---|---|---|
| P0 任务条件与来源冻结 | 主线执行器、任务/evaluator、可修改范围、缓存 v2、方法/运行身份、费用与窗口绑定 | 原协议及首条运行 seal 不覆盖更新后的传输修复 |
| P1 真实 Pi | baseline-r1 实际调用模型，独立执行三个候选，无人工代填后续参数 | 最后请求已发送，缺少供应商用量；未完成提交，其余三条未启动 |
| P2 模型与工作域 | 初始名义/越界复算、30 项装置对照、六项原生电源轨观察及真正减半步长复算 | 无合法自供能正例；磁网格及完整旋转 FEM 尚未合格，缺失的历史材料不冒充恢复 |
| P3 一个真实结构自由度 | 根据能量账本整理候选结构问题及接入判据 | 冻结协议要求先导完成后再开放；本轮未执行结构综合 |
| P4 等条件方法比较 | R/Q 四个策略及真实产物绑定元数据可用；导出与独立检查基础已接入 | 无完整反馈提交轨迹，未运行主比较或 RSI |

## 共同版本与不可变记录

- 应用/原生基线：main `87e7d75b4c5cd13c96560b8aaa4168a292ddc3c9`。
- 历史 Dot 检查点：`4be17f5ff3d8fb073029be6a7cef165284f07bd9`，639 个归档文件逐字节核对，无原文件改写。
- 工作分支：`codex/integrate-dot-20261002`，位于 `/Users/depengsu/.local/share/bf-agent-integration-20261002`。本轮未提交或推送。
- 保留 BFA-034 液态玻璃页面；本轮只增真实研究投影、状态与证据入口，没有新一轮视觉重构。
- Dot PR2 新补充分别归档于 review/dot-supplement-20261002 和 review/dot-supplement-20261002-v2；后者绑定 `256403f7c3e15f290cc305237ebbdf8475901fe7`。补充不自动成为首条轨迹的参与者方法。
- 新研究：`door-integration-pilot-20261002`。旧 door-design-pilot-v1 保持封存，失败、原生原文件和 UNKNOWN 费用未清理。

本次用户批准新增总额 $2、12 小时、每条最多 $0.50、单次请求低于 $0.20；实施请求上限 $0.19，每条最多三个新候选。原生观察使用另行声明的串行时间边界，不把工具 fixture 计为模型/硬件运行。

## 装置对照：明确差异，而非宣称模型等价

新目录 `/Users/depengsu/.local/share/bf-agent-runtime/apparatus-alignment-20261002-v3` 完成 30/30 检查。
名义 48 mm 几何关系吻合；非名义间距下主线和 Dot 的磁体运动关系不同。同一供电轨迹下两份 C 的默认发送时序、载荷及 PGOOD/重启/接收语义也有差异。

实际求解采用主线装置。对照通过包含“预期差异被检测到”，并不证明两个联合模型可以互换。独立回放没有调用厂商原生求解器或付费模型。macOS BLAS 适配只识别 `.dylibs` 并核对实际二进制哈希，物理方程和数值门槛未改变。原锁和前两次执行失败完整保留。

## 六项原生电源观察与纠错

LTspice 实际运行，使用已安装原厂宏模型的端口顺序；加密模型正文未发布。CAP、VIN2、输出和相关电流从实际 RAW 重新读取、按声明单位计算。

| 条件 | 输出峰值 V | 末端 VIN V | 解释 |
|---|---:|---:|---|
| 名义基线 | 1.06381e-6 | 0.145483 | 未冷启动 |
| 原 baseline-fine | 同上 | 同上 | 最大步长实际仍是 50 μs，拒绝当作细化证据 |
| 0→4 V 外部诊断 | 2.80029e-5 | 3.999991 | 外部刺激，不是自供能设计 |
| 充至 6 V 后断开 | 3.339638 | 5.994504 | 源断开与强制放电分别观察 |
| 电压源保持连接并拉低 | 3.339638 | 4.33283e-7 | 不能与“源断开”混为一谈 |
| 真正细化的充电/断开 | 3.339770 | 5.994504 | 20→10 μs |

四项原后处理曾因 NumPy 移除 trapz 失败，其回执没有覆盖。独立 readback 使用 SciPy trapezoid，新的复核回执指出原 baseline-fine 没有减半步长。

另起 `rails-baseline-refinement-20261002` 真正执行 50→25 μs：VIN/OUT/VIN2/CAP 的最大归一化差异约为 0.01582% / 0.01484% / 0.01582% / 0.12568%。这只证明已声明步长下的数值一致性。声明窗口的 settled 判据不等于渐近稳定、硬件稳定或完整 PMIC 内部能量去向已确认。

最新 readback：`/Users/depengsu/.local/share/bf-agent-runtime/observations/rails-integration-20261002-v3/reviewed-readback-v2/receipt.json`。真正基线细化：`/Users/depengsu/.local/share/bf-agent-runtime/observations/rails-baseline-refinement-20261002/reviewed-refinement/receipt.json`。

## 第一条真实 Pi 的结果

会话 `pi-chat-a2c98af95fc3bd7f`；19 次 bf_engineering 工具调用，17 次真实模型请求。三个候选都由 Pi 提出并执行。

| 顺序 | 实际修改 | 原生执行结论 | 任务结论 |
|---|---|---|---|
| 1 | gap 34 mm，Cin/Cout 220 μF，间隔 50 ms | 初始预载超出 ±8 mm ROM | not_evaluable，不能当作器件失败 |
| 2 | gap 40 mm，保留上述电容/程序配置 | 同样越界 | not_evaluable |
| 3 | gap 48 mm，保留上述电容/程序配置 | completed，联合数值检查完成 | unsatisfied，无完整 TX 或虚拟 RX |

第三候选：压电峰值 0.525222 V、输入储能峰值 0.0350487 V、供电峰值 1.15948e-7 V；C 仅到 RESET。初始机电能约 0.758637 mJ，机械边界净功约 −0.662924 mJ，PMIC 端口净输入约 0.00365171 mJ。这个名义账本提示机械能返回边界的组织方式值得后续研究，不能由此宣称导向/凸轮结构已经更优。

最后请求在原本地 90 秒流式总上限处中断，错误 PROVIDER_STREAM_LIMIT。已记录 16 项本地 SETTLED 和一项 UNKNOWN；费用上界合计 **$0.126963**，含 UNKNOWN 预留 **$0.0393837**。本地 SETTLED 是保守账本计算，不是独立供应商账单。

UNKNOWN 请求 `llm-d8ff18648ea8de1de867` 已发送；供应商响应 ID `e0b4fc29-f5cb-4ae0-9933-b9af4b7cfab9`，北京时间 10 月 2 日 03:28:22 开始。没有计费用量，不能标成 NOT_SENT，也不能从 SDK 的零 token 或余额变化推断用量。冻结协议要求暂停新增付费调用。首条未完成 submit；另三条 NOT_STARTED 不计为结果。

## 传输修复与恢复条件

后续代码将流式总窗口改为 300 秒，连接/socket 超时仍是 90 秒，字节上限 2 MB。费用、请求、候选和总窗口边界没有提高。
新增实际请求 ID、传输耗时、字节与终态 usage 事件。缺失 DONE 但存在有效终态用量时可以记录费用，输出仍失败；缺少或无效用量继续保留 UNKNOWN。没有自动付费重试。

这不能修复历史 UNKNOWN。恢复前需：

1. 取得该请求可核对的供应商输入/输出 token 及来源，保存追加式结算证据。
2. 保留首条 seal 和失败，用新的受控修订绑定传输修复后的 runtime 身份；不覆盖原运行 seal。
3. 核对原授权剩余费用/窗口及各轨迹预算；不重复新增 $2，不清零历史消耗。
4. 明确首条后续动作的协议身份，再推进未启动轨迹。结构开放/方法比较仍遵守原触发条件。

## Studio/Lab 与证据交付

产品页、Lab 和 CSV 读取同一个 SQLite 投影。明确区分作业执行成功、名义任务成功、物理排名资格和最终提交；失败/费用待核实不再显示“仍在迭代”。

Lab 提供同次候选的统一时间轴、已观察设计空间和实际 Pi 修订轨迹，以及逐运行结果。候选参数、真实产物哈希、时间和缓存命中是权威依据；不从解释文字推定架构已执行。

- 小型证据 ZIP：`/Users/depengsu/Documents/bf-agent-workbench/verification/dot-integration-20261002/pilot-evidence-v2.zip`。
- 35 个文件逐项 SHA-256 与 ZIP CRC 验证；603,601 字节。
- ZIP SHA-256：`b7dfb4cb52d18d35a813a9bde282f8da9058dc96a70124689119553b33659103`。
- 包含三图、CSV、结果、候选、迭代/能量/接收回执、原始大文件哈希；展示抽样与完整定量结果分开。
- 不包含凭据、原始会话正文、厂商模型正文或大型 RAW。
- 下载只接受注册的协议/文件、限定 verification 根路径并复查文件哈希，拒绝任意 record_file 路径。

实际服务还发现旧研究文件读取阻塞。历史读取现使用独立进程、8 秒上限，失败不改写历史记录；新的 Pi 面板独立显示和导出。真实 HTTP 已检查数据、四项资产哈希与越权路径拒绝。旧研究当前仍返回限时读取失败，需要本机存储恢复；没有用空数组冒充“没有历史实验”。浏览器可视化检查未完成。

## 验证、Dot 补充和未完成事项

最终应用 ./init.sh：463 项 Python 测试通过、SDK/Studio 类型与构建通过、2803 原始样本复现。此前 460 项完整验证日志保留；新增投影/资产与隔离读取检查已纳入最终复验。30 项研究回归及 JS 投影/语法检查另行通过，不重复累加测试数。
Dot 最新适配器 38 项离线检查通过。轨迹审计器在实际 Python 3.11 上 22 项通过；默认 Python 3.14 的符号链接环处理出现三个失败，保留失败日志，不能声称任意 Python 版本可移植。它只检查结构证据，缺失方法指令/反馈交付仍是未知，尚未作为真实先导的生产审计器。

Dot 原验证执行项目均通过，但全验证仍有 beam 材料 HTML、磁场原始两个 JSON 缺失的阻塞项；“已执行通过”不等于“所有门槛通过”。没有下载新文件冒充原始材料。
协调仓库 ./init.sh 在读取既有 fixture 时阻塞，采样及路径已保存，停止了本次自有验证进程；未宣称该仓库完整验证通过。88 项科学 feature 数组保持不变。

P3 后续候选可以比较直接旋转加载与导向退离/释放，但必须新增实际 CAD 运动约束、磁力轨迹、接触/驱动力和能量边界，并以新模型身份接受独立验证。当前只是由真实失败形成的待评估问题，未开放任意参数、更改评价条件或制造自供能正例。P4/RSI 等待合法任务空间和完整真实反馈轨迹。


## 2026-10-02 continued paid pilot (in progress)

The user explicitly authorized continuing despite missing provider usage. The existing USD2 / 12h study, USD0.50 owner and USD0.19 request ceilings remain; UNKNOWN rows keep their full reservations. The exception is scoped to this study and does not silently settle historical usage. Original failed receipts and the first runtime seal remain unchanged.

Live diagnosis found two transport issues: the upstream service returned only keepalive comments for more than 300 seconds, and the proxy discarded those comments, causing the Pi client to time out while its upstream request continued. The study-specific wait is now at most 1200 seconds inside its authorized window; SSE comments reach the client. Two bounded diagnostic requests later returned normally; they are recorded separately from Pi design trials.

A real recovery also exposed an observation failure: a >24KB engineering inspect response was reduced to an inaccessible file pointer. An owner-scoped compact job index now preserves all candidate IDs/statuses without the large native payload. A real Pi process with a fixture provider and 60KB native detail verifies that index delivery and independent submission work (9 task tests passed). This is an execution repair, not a new scientific method. The general >24KB full-response bridge remains unpromoted.

Baseline-r1 received one factual restoration containing all three of its own original job IDs, no operator-selected parameters. The intervention and original source hashes are saved under its trial directory. Subsequent fresh trials use the compact index and separately recorded runtime identities. These intervention variants must not be pooled as an untouched formal method comparison.

The original 464-test application verification passed; an additional 13 provider/keepalive checks and the 9 task tests passed after follow-up repairs. The first bare chat-test invocation lacked BF_PI_ROOT and failed to load Pi; the correctly configured full verification passed. No Git commit or push has been made.
