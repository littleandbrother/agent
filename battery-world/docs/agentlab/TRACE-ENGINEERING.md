# Trace、Tools 与本机工程环境

2026-09-18 · BFA-010 · 本机工作台 http://127.0.0.1:8768/

## 页面入口

选中会话 → 开发者 → **Trace**：

- 概览：实际输入/输出 Token、已结算费用、工具数量、最近 Pi 进程时长、错误、上下文投影。历史会话可以有多次进程，因此最近进程时长不是整个会话的累计耗时。
- 时间线：对话、模型、工具/Skill/MCP、科学实验、工程任务和适配器事件；可按轮次、类别、错误和关键词筛选。点击记录查看输入、返回、调用 ID、来源行和已记录的耗时。
- 对比：选择另一个会话查看用量、费用、调用数和记录时长差异。它是探索性比较，不证明输入/任务相同，也不自动认定 Harness 改进。
- 原始记录：导出完整 JSON，保留原始 JSONL 字节及 SHA-256、异常末行、账本、上下文投影、工程任务和 Skill/CLI 事件。HTML 报告省略工具输入/返回；完整审查使用 JSON。

**Tools** 提供工程环境、工具、Skills、MCP 四个页签。工具启用状态来自最近一次 Pi 注册；调用次数来自实际记录。Skill 读取会显示内容哈希，`read` 读取 `SKILL.md` 的记录也可审查；读取不等于执行或验证成功。`mcp__server__tool` 命名的真实工具事件归入 MCP。未记录的调用无法事后恢复，不根据安装目录虚构执行记录。

用户对话页继续只显示公开进展、回复及简洁执行摘要。没有新增模型内部推理原文展示。Trace 是观测数据，不能作为未经审核的指令或训练标签；RSI 仍需归因、候选、对照/回归与独立验证。

## 工程工具

`bf_engineering` 已加入产品对话及基准对话入口，支持 `inspect`、`skill`、`run`、`job`。现有 BF-AIoT 文件夹创建了配置 v4，仅新增工程工具；Memory/提示词未改动。后续 Pi 进程读取该版本，历史注册记录保持原样。

| 引擎 | 已接能力 | 产物 | 边界 |
| --- | --- | --- | --- |
| Blender 5.2.1 LTS | 毫米参数外壳、元件占位、拆盖展示、渲染 | `.blend`、GLB、PNG、尺寸记录 | 展示模型；未验证制造、公差、防护和安装 |
| COMSOL 6.2.0.339 | 均匀悬臂梁、线弹性静力、两档网格 | `.mph`、CSV、参数、求解日志、数值检查 | 仅指定模板；未接入压电、多物理场及整机验收 |
| CAD | 等待用户安装 | — | 未用 Blender 替代制造 CAD |

两者通过本机 **CLI** 执行；没有把 CLI 伪装成 MCP。Pi 当前没有注册工程 MCP 服务，MCP 页会如实显示无调用记录。已有全局 Blender 插件也不代表 Pi 已连接。

Tools 的“运行模板”是独立例子，不会被标为当前产品验收。Agent 若传入 `design_revision`，任务会绑定当前产品版本；旧版本产物在产品文件页标记过期。执行成功与数值检查通过是不同字段；两者都不能提升产品/硬件验收状态。

执行约束：固定参数模板、有限范围、每次 180 秒、2 核、1 个并发任务、每会话最多 40 个任务。工程工具不调用模型。稳定 `operation_id` 保证重试返回原任务，参数冲突被拒绝。请求绑定模板源码哈希；产物下载校验哈希。服务中断的任务保留 UNKNOWN，不自动重发；仍存活的已记录进程组会阻止新增工程执行，需要核对日志或等待其退出。超时监控依赖运行中的服务，生产部署仍需独立进程监督器。

## 实际验证

- 完整 `rtk proxy ./init.sh`：262 项 Python 测试、SDK/Studio 类型检查、构建和源数据投影通过。
- 后续 Trace 专项：14 项通过，包括原始字节、未知耗时、Skill/MCP 分类、残缺用量、权限、幂等、服务重启和产物篡改。
- 真实 Pi 进程 + 假模型传输：确认工程工具注册、Skill 读取及带时间调用记录；没有真实模型调用。
- Blender 原生文件重新打开后测得默认外壳约 80 × 50 × 25 mm，单位比例正确；GLB 和渲染产物存在。可见 PCB/电子元件是占位包络。
- COMSOL 默认算例：末端位移 0.02448417 mm；两档网格位移差 0.13256%；相对梁理论值 0.025 mm 误差 2.0633%。`.mph` 已通过独立 `-norun -nosave` 重新读取。固定端角部最大应力不能用于强度认证。
- 独立无头 Chrome 对实际 localhost 验收概览、时间线、详情、筛选、比较、原始导出及 Tools 分类；控制台无异常。桌面实际前台验收因锁屏不可用，不将无头验收称为用户验收。
- Pi 两个修改入口的 Biome 检查和 TypeScript 编译通过。根级 `npm run check` 仍被既有入口的未使用变量警告阻断，没有宣称整个 Pi 仓库检查通过。该命令自动格式化了 BF 入口；H0 solver/improver 的纯格式变化已核对并恢复原字节。

本轮生产模型账本与历史 Trace 均检查保持一致；具体哈希、任务 ID、日志路径和浏览器回执见 [TRACE-ENGINEERING.json](TRACE-ENGINEERING.json)。工程测试不消费模型额度。

可复现命令：

```sh
rtk proxy ./init.sh
rtk proxy env PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m unittest discover -s tests/agentlab -p 'test_trace*.py' -v
rtk proxy env PYTHONPATH=packages/python/bfworld/src .venv/bin/python docs/agentlab/ENGINEERING-SMOKE.py
rtk proxy node docs/agentlab/TRACE-ENGINEERING-UI.cjs
# 可选：实际点击两个本地模板的运行按钮，零模型调用
rtk proxy node docs/agentlab/TRACE-ENGINEERING-UI.cjs --run-templates
```

## Fork 和来源

远程 Fork：[littleandbrother/agent-workbench](https://github.com/littleandbrother/agent-workbench)。
上游：[minipopstyle/agent-workbench](https://github.com/minipopstyle/agent-workbench)。
本地：`/Users/depengsu/Documents/agent-workbench-upstream`，分支 `codex/bf-developer-trace`，审阅 commit `7968c6073a5ba36a2561226cc2bf44f33ddab335`。

借鉴执行概览、时间线、日志诊断、比较和报告的组织方法。上游当时无项目 LICENSE，因此生产代码独立实现，没有移植其源码，也没有内嵌其独立服务器。没有 Git 提交或推送开发改动。

后续接入 CAD 后，需扩展严格几何/装配接口以及 CAD → 展示网格 → 有明确物理问题的 COMSOL 模型绑定。本次模板不承担这一完整设计闭环。
