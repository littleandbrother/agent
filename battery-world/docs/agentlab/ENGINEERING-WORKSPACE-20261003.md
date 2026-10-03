# 对话右侧工程工作区 · 2026-10-03

本轮按用户四张参考图实现右侧工程浏览区域，保留原来的项目侧栏、Studio/Lab 导航和完整产品/交付页面。代码基线为 `02d6d899cea49cb878c46e885e6c487eb4ac51b9`。用户确认“云端”指提交现有 `littleandbrother/agent` GitHub 仓库。

## 行为

在 Studio 对话中，顶部“工程工作区”及对话后的“查看产品成果”打开右侧区域。提供概览、原理图、PCB、结构、仿真、BOM、文档七个分区。使用白色背景、无色透明材质、细边线与轻微按压/切换动效；预览图和计算曲线保持原始内容。右侧宽度独立保存，支持拖动和键盘调节，手机宽度下成为可收起的覆盖面板。

复用现有 `/api/results`、`/api/results/series` 和 owner 绑定的原文件 URL。用户可选择当前装配适用成果、全部历史记录或已发布的工程案例；选定一次运行后，预览、指标、检查和文件列表均来自该运行。三维模型沿用原生模型查看器；图纸可缩放/展开；CSV 数值绘制同一时间域的真实通道，BOM 表格按已归档文件展示。讨论按钮仅填入草稿，不发送模型请求。

缺失/校验未通过文件保持“待恢复”；不可读取图纸不替换成参考图。SPICE 输入不冒充原理图，PCB 安装图归结构，BOM 不绘制为波形。历史和独立运行不自动归入当前装配。失败、未验收和诊断供电的范围保持后端原值，未加入参考图中的虚构成功率或器件数据。

提供 owner/generation 异步保护、45 秒读请求超时、10 秒刷新复用，避免流式事件每次重绘全部工作区。键盘标签切换、焦点、减少动态、减少透明度及高对比度处理已加入。

## 验证

- 27 项 JavaScript 投影/负例断言通过；24 项 Python 页面/结果/交付/对话回归通过。
- SDK 类型、Studio 类型和构建通过；2803 个样本复现通过。使用已安装依赖，命令见下方。
- 浏览器实测 1440×900、390×844：无横向溢出；原图缩放100→125%、展开关闭、工程区域收起重开、范围/运行选择、空任务、Lab 往返及键盘标签导航通过。
- 真实模型加载38个零件；实际4001点联合计算波形可读取。右侧宽度806→816→806验证通过，原有左右栏偏好分开保留。
- 浏览器没有 error/warn；测试用视口已恢复。现场截图与详细回执留在本机验证目录，未上传生产对话、凭据、数据库或大型工程产物。

完整 `./init.sh` 执行484项测试，在NAS和CAD两项异步工程测试的等待期限内仍为RUNNING而失败。单独复查NAS通过；CAD在90秒测试期限内仍未完成，随后180秒工程执行超时。未修改求解器、沙箱权限或放宽测试门槛。本轮只声明UI专项通过，不声明完整环境健康。两份原始失败日志保留。

```sh
node tests/agentlab/test_engineering_workspace.cjs
PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m unittest tests.agentlab.test_engineering_workspace tests.agentlab.test_studio_delivery tests.agentlab.test_product_results tests.agentlab.test_conversation_ui -q
BF_PI_ROOT=/tmp/bf-publish-pi-20261002 ./init.sh
corepack pnpm --config.verify-deps-before-run=false run check:sdk
PYTHONPATH=packages/python/bfworld/src .venv/bin/python scripts/validate_control.py
corepack pnpm --config.verify-deps-before-run=false run check:studio
corepack pnpm --config.verify-deps-before-run=false run build:studio
PYTHONPATH=packages/python/bfworld/src .venv/bin/python scripts/validate_studio.py
```

## 边界与交接

这是工程结果浏览器，不是原生EDA编辑器，也不会因点击分区生成新的仿真或证明产品已通过。当前历史原理图、PCB或BOM中有文件未能读回；查看器记录缺口，不修订密封案例的文件或哈希。标准原生程序测试只在临时验证环境执行，没有发起生产产品重算，新增模型费用为0。

BFA-036完成后，BFA-035仍保持in-progress；原来的完整加载功、旋转磁场/model-domain确认和结构任务研究继续保留，未由UI改动提升科学结论。
