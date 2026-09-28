# 立创专业版接入与原生电路验收

2026-09-18，BFA-012。接入已完成，验证范围是独立的小电路与软件链路；太阳能桌面陪伴产品仍需单独设计与验收。

## 现在可用

在工作台 `http://127.0.0.1:8768/` 选择会话 → 开发者 → Tools → 工程环境。
新增一张立创 EDA 卡片，连接检测、工程/板卡绑定与参数操作折叠在卡片内。
原有运行页面不增加 EDA 控制项。

- `bf_engineering` 支持 `engine: jlceda`，可放置原理图元件、连线、同步 PCB、建立矩形板框和布局、指定铜线、检查、导出。
- Tools 的 Skills 页读取安装的原始内容和 SHA-256；MCP 页展示实际能力和调用。
- Trace 时间线收录工程任务、MCP 初始化/调用、输入、结果、耗时、错误和 Skill 读取；MCP 详情可下载完整原始请求与响应。
- 工程操作携带稳定 operation_id、绑定的窗口/工程/板卡/图页、模板哈希和产物哈希。重试不重复执行；项目变化拒绝操作。超时/断线导致的未知执行阻止后续修改。
- 发起身份由服务端认证写入。开发者手动试运行不归入模型轮次，不可通过请求正文伪装成 Agent 调用。早期未采集身份的历史记录保留“未记录”。

## 安装来源

| 能力 | 来源 | 本次固定版本 |
|---|---|---|
| 官方 API / Gateway Skill | https://github.com/easyeda/easyeda-api-skill | ccfaf28a577b61a09ebc907f0a943d1e6c782def |
| 官方原理图扇出 Skill | https://github.com/easyeda/easyeda-enhanced-schematic-skill | 0c4b9a0ad94d532923dee5c828a6efa7444f4506 |
| 社区 MCP | https://github.com/Nambers/easyeda-pro-mcp | 5222fc162702b9446199c8403e973b8e776ae1ae |
| 本项目 PCB 布线 Skill | ~/.codex/skills/easyeda-pcb-routing/SKILL.md | 以每次读取时的内容哈希标识 |

前两项声明 MIT，社区 MCP 为 Apache-2.0，源码原样保留。技能目录中的 references/scripts 一并安装。
本项目布线 Skill 将电源/模拟关键走线、真实焊盘与网络、单位换算、规则检查、未知结果处理落实到类型受限的接口。
官方扇出 Skill 处理原理图引脚布局，不是 PCB 自动布线器。
官方 extension-dev-mcp-tools 主要用于扩展开发调试，本次不把它当作 PCB 布线 MCP。
另一个已审阅的 easyeda-mcp-pro 未启用。

实际路径是 Pi → BF 的 bf_engineering → stdio MCP → 官方 API Gateway → 本机立创。
没有把 Blender/COMSOL 的 CLI 调用标成 MCP。未修改全局 Codex MCP 配置；调用挂载在 BF 工作台自己的工程适配器中。
生产服务仅执行固定操作，没有向模型开放任意 eda JavaScript。

## 原生测试结果

本机应用：嘉立创 EDA 专业版 V3.2.148、半离线。独立工程 `BF-EDA-Smoke-20260918`。
测试仅用于连接和制板文件链路：两个 2P 排针和两个 10kΩ 电阻组成分压电路。
原用户的 SHM 工程没有作为测试目标。

| 项目 | 结果 |
|---|---|
| MCP 初始化、发现与执行 | 真实连接；发现 19 个工具 |
| 原理图 | 4 元件、8 个引脚赋网、VIN/VOUT/GND 共 3 网 |
| 元件来源 | 排针 C124375，电阻 C25804；实际符号/封装与引脚读回 |
| PCB | 30×20 mm；元件布局、板框与 0.30 mm 顶层铜线 |
| 铜线 | 原生读回 12 段（立创在连接点自动拆分线段） |
| SCH 与 PCB | 逐引脚网络表一致 |
| PCB DRC | 原生 strict=true 检查通过；保存、关闭、重新打开后复核通过；页面再次提交检查通过 |
| 原理图 ERC | strict 检查未通过；API 返回 2 条 warning，当前版本未给出文本细节。保留为未消除警告 |
| 导出 | 原生 .epro2、BOM CSV、网络表、原始文档、Gerber ZIP；ZIP CRC 检查通过 |
| Gerber | 顶/底铜、丝印、阻焊、顶层锡膏、板框、PTH 钻孔等 11 个文件 |
| 证据复核 | 118 个已记录产物经服务端下载并复算 SHA-256 与字节数一致 |

可视化验收查看了原生原理图和重新打开后的 PCB 画面，后者显示 4 个元件、3 网铜线及板框。
曾发现截图 API 返回旧渲染缓存；旧 `pcb-native.png` **不能作为最终 PCB 证据**，最终图为 `pcb-reopened.png`。
同理旧锁屏时生成的 `schematic.png` 不用于验收，使用 `schematic-native.png`。

## 真实实验反馈带来的修正

1. openDocument 只打开标签，须 activateDocument 后核对图页 UUID 与父工程 UUID，才允许设计操作。
2. V3.2 的 importChanges 返回 true 可能仅表示打开确认窗口。现在返回 NEEDS_ACTION，要求在立创应用修改后重新读取，不宣称同步成功。
3. 早期替代导入尝试只创建了部分元件即失败，该路径已移除；失败记录保留。原生导入、修正 J1/R1 通道关联后 PCB DRC 从网络表不一致变为通过。
4. 当前版本没有 autoRouting API。适配器明确返回 EDA_AUTOROUTING_UNAVAILABLE；本次用实际原生铜线完成测试，没有把指定走线声称为自动布线成功。
5. 规则检查的 undefined/异常记为 unavailable；API 调用完成、ERC/DRC 通过、产品验收分别记录。

早期 `eng-2bf785930de236ea` 的 SUCCEEDED 仅证明旧实现收到 API 返回；其空 PCB 读回不证明导入成功。保留此历史记录用于审查，不能将其当作验收证据。

## 证据与复现

运行证据根目录：`/Users/depengsu/Documents/bf-agent-workbench/verification/jlceda/`。

- `native-verification.json`：身份、网络、尺寸、DRC、导出和全部产物散列。
- `verify.py`：只读重验现有测试板记录及 HTTP 下载产物；无需模型调用。
- `smoke.py`：固定 operation_id 的本机实验工具；不能在已有工程上随意重新创建元件。
- `pcb-reopened.png` / `schematic-native.png`：最终原生视图。
- 最终原生文件：`/Users/depengsu/Documents/bf-agent-workbench/engineering/eng-e886d0271549445c/project.epro2` 与 `gerber.zip`。
- 最终页面发起 PCB 检查：`eng-c6fda47446e424e5`，实际返回 DRC passed。

```sh
rtk proxy python3 /Users/depengsu/Documents/bf-agent-workbench/verification/jlceda/verify.py
rtk proxy env PYTHONPATH=packages/python/bfworld/src /usr/local/bin/python3 -m unittest tests.agentlab.test_jlceda tests.agentlab.test_trace_engineering -v
rtk proxy ./init.sh
```

后两个命令在 Battery World 仓库运行。完整 init 已通过 267 项测试以及 SDK/Studio 检查、构建与再现；最后的身份标注等收尾改动由 14 项定向测试覆盖。Pi bf-agent TypeScript 构建通过；上游 MCP npm test 通过。真实 Pi 工具注册测试使用本地脚本提供响应，不产生付费模型请求。

协调仓库 Long-Horizon AI Agent 的 init 两次停在 Python 模块文件读取，分别为已有 pycache 和源码文件；进程采样及 lsof 已保留并停止等待。本轮不宣称该科学仓库健康，也没有更改其科学实现或 feat-397 的状态。

## 下一步边界

在立创新建太阳能产品的独立工程并重新绑定，然后依据产品负载/电源预算、器件数据手册和安装尺寸设计电源、MCU、显示、传感器等电路。对高阻采能节点、峰值电流回路、天线区域单独检查，不能照搬本测试板。
当前没有交付完整太阳能产品电路、固件、训练数据、神经网络或实物测量。自动布线 API 需要后续版本支持；重复布局、复杂板框、过孔/铺铜、阻抗约束等暂需原生编辑器配合。ERC 的两条警告未被屏蔽，未下单制造。模型费用和 token 预算未修改，本次付费调用为 0。
