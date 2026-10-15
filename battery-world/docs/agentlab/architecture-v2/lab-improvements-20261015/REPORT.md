# Lab 界面改造交付

已在 http://127.0.0.1:8768/lab#system 上线。

| 页面 | 已实现 |
|---|---|
| 系统设计 | 当前候选、父版差异、实际工程问题、BF 决定；横向版本历史；原理图、PCB、CAD 与审查包入口 |
| 运行记录 | 按 BF Lead／Power／Firmware 组织任务和动作；区分工具调用结果与工程结果；本轮／会话／项目费用联动 |
| 验证 | 当前八项核心检查与历史回执分开；检查范围、指标、单位、对应版本和原始证据可查 |
| 环境 | 按实际工具配置、作业与能力记录展示环境，具体文件可以追溯 |
| 方法与技能 | 按 Agent 查看实际模型、加载配置、激活技能、技能目录及公开请求 |
| 实验与改进 | 使用真实实验记录；当前零项实验显示空状态 |

交互统一为顶部六页导航、左侧当前页对象、中央内容、按需打开的右侧详情。两侧完全折叠，详情不再默认挤占内容区；图标使用 SVG。原始 JSON 收到详情的“原始记录”中。

原理图和 PCB 支持缩放、拖动、方向键与文字定位；CAD 复用当前候选绑定的网格。历史查看与浏览器返回保留版本身份和阅读状态。搜索覆盖当前项目的设计、问题和工程文件。页面显示读取时间，刷新由用户触发。

## 验证

- 19 项自动化单测与 29 项发布检查通过。
- 实际浏览器检查六页、图纸定位与缩放、CAD、历史切换与返回、费用范围、搜索、折叠及 760／1024／1280／1440 px 布局。
- 7 份预览内容、3D 网格及当前审查包通过版本与内容核对。
- 6388 件 Baseline 文件核对通过；原工程、十个原会话、账本及 V2 设计状态保持一致。
- 新增模型请求 0，新增工程作业 0，重复仿真 0。

当前页面读取八项核心检查：2 项通过、2 项未通过、4 项缺少验证条件。接口 24 项核对通过。PCB 的 52 项间距错误、50 项连接错误和供能结果在页面直接展示。

## 代码与回归入口

源码：`apps/agent-studio/architecture-v2/{index.html,lab.js,lab.css}`。
单测：`tests/agentlab/test_lab_ui.mjs`。
静态发布：`scripts/publish_lab_bridge.py`；相同内容跳过写入，静态更新无需重启后端。
发布验证：`scripts/verify_lab_publication.py`。

```sh
BFWORLD_VERIFY_PROFILE=architecture-v2-lab \
BF_V2_EVIDENCE=/absolute/path/to/new-evidence-directory ./init.sh
```

证据：`verification-final/result.json`、`browser-verification.json`、`publication-final-release/publication.json`、`system-final.png`。

浏览器检查中的历史失败及诊断保留在原记录：时间轴列宽已改为适配页面 CSP 的 CSSOM 写入；返回测试中自动化工具在点击前发生的滚动，通过 pointerdown 诊断确认，应用返回与实际离页位置一致。临时诊断代码已移除。

本次修改位于本地 `codex/bf-architecture-v2` 工作树；源码基点 `4e5eb35332f498f9aabeac7dc1f877bce30803f5`。发布只更新现有 Lab 静态资源。
