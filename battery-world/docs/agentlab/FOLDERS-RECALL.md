# 文件夹、共享配置与消息撤回

工作台：<http://127.0.0.1:8768/>。本次工程验收完成；详细证据见 [FOLDERS-RECALL.json](FOLDERS-RECALL.json)。

## 使用方式

- 会话右侧 `⋯` 可改名、移动、删除。删除后从侧栏底部“最近删除”恢复；历史实验原始文件保持不变。
- “新对话”旁可创建文件夹。文件夹菜单提供新建会话、共享配置、改名、上移、下移、删除。会话也可拖入文件夹；菜单移动是键盘可用的替代入口。
- 文件夹名称前只保留细线折叠箭头，折叠状态跨刷新保存。当前实现为单层文件夹。
- 文件夹“共享配置”或顶部文件夹名称可打开 Memory、提示词、Tools、Harness 四个编辑页。Harness 选项来自开发者模式中已校验的版本。
- 同文件夹的 Pi 会话实际加载同一份配置；启用 `bf_memory` 后，Agent 可以读写共享笔记。写入采用版本检查，移动后的旧进程不能继续访问原文件夹记忆。
- 用户消息框外下方排列发送时间、复制、撤回。复制与撤回使用 14px 线形图标，保留 24px 点击区域和键盘焦点；时间悬停显示完整日期。
- 撤回会停止当前执行，将所选消息及后续对话从当前分支移除，原文返回输入框。原始记录保留，Pi 的下一次输入确实排除已撤回分支。

已完成的文件改动、实验、封存提交和费用不会被撤回。删除文件夹时其会话移至未分类；恢复文件夹不会自动恢复旧的成员关系。共享配置用于下一次进程启动，进行中的回复继续使用原绑定版本。

## 运行与记录

`organization.py` 保存文件夹、排序、会话元数据和带版本的共享配置；历史会话名称与归属采用独立元数据，不重写旧 receipt。`chat-v2.ts` 注册实际选择的工具并记录最终共享上下文，原始 `chat.ts` 与 `main.ts` 保留。开发者 Memory / Context / Tools 展示启动时的实际记录。

`recall.py` 持久化撤回状态，等待 Pi 停止后通过 `chat-recall.ts` 更新 SessionManager 分支。已完成撤回的事件范围在普通界面隐藏，原始 trace 与费用不删除；重复操作有标记。撤回未完成时暂停新输入，避免消息重新发出。

工具选择决定 Pi 注册的工具集合，现有进程沙箱仍负责文件与网络边界。共享笔记只作为待验证记忆，不能自动提升为科学事实。

## 验证

- 独立副本完整 `./init.sh`：224 项测试通过，SDK / Studio 类型检查、构建、产物复核通过。
- 最终后端改动后：33 项 agentlab 测试通过；真实 Pi + 本地假供应商验证共享笔记读写、提示词与 Harness 注入、精确工具集合、运行中停止和后续上下文排除；另外 3 项 HTTP / 聊天测试通过。
- TypeScript 编译和前端 JavaScript 语法检查通过。
- 真实页面验证会话改名/移动、文件夹增删改/排序/恢复/折叠持久化、共享配置保存、撤回返回输入框、复制成功，以及消息框外 14px 图标布局。
- 当前历史文件 1309 个、原始基线文件 1365 个、科学源文件 126 个散列全部保持不变（两份历史清单有重叠）。

复核命令（仓库根目录）：

```sh
rtk proxy env PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m unittest discover -s tests/agentlab -v
rtk proxy node --check apps/agent-studio/app.js
rtk proxy node --check apps/agent-studio/organization.js
rtk proxy node --check apps/agent-studio/developer.js
rtk proxy .venv/bin/python scripts/validate_project_state.py
```

完整 init 在 `/Users/depengsu/Documents/bf-agent-workbench/verification/battery-world` 执行，避免重建线上封存产物。日志保存在同级 verification 目录。

## 当前外部连接状态

本轮无外部模型请求、无新增费用。账本保持 774 条 SETTLED、1 条 UNKNOWN；已结算费用上界 USD 2.983629，未知请求保留 USD 0.0087363 预留。

之前的 `SSL: UNEXPECTED_EOF_WHILE_READING` 来自本地供应商代理访问外部 API 时 TLS 连接提前结束，页面的“Pi 已连接”只代表本地 Pi 进程已启动。该请求仍需核实用量，保护闸门保持关闭。本次功能通过本地假供应商验证，不表示该外部网络问题已修复。

没有硬件、训练神经网络、科学收益或 RSI 效力的新结论；未作 Git 提交。
