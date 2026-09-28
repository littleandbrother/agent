# BF Agent 会话工作台

打开 http://127.0.0.1:8768/ 。新任务从中央输入框开始；发送后，同一个会话展示 Agent 的公开进展、工具执行和计算结果，输入框留在底部。执行中发送的补充要求通过 Pi steering 传入，完成后继续发消息会恢复同一个 Pi session。

左侧只显示任务会话、新对话和运行/开发者模式。52 个旧实验会话收在历史列表里。顶栏的折叠按钮支持键盘，折叠状态刷新后保留。旧首页介绍和要求特殊启动链接的提示已移除。

右上角“分区”打开机械、电路、神经网络、产物面板。电路参数来自实际完成的实验；缺少机械实测、CAD/FEM、训练模型和部署产物时明确显示缺失状态。开发者模式保留 Memory、Harness、RSI、Tools、Context、Experiments 及 Memory/提示词/Harness 编辑入口，编辑只形成下一次运行的版本。

## 真实验收

会话 `pi-chat-390c76686d6d79a5` 经 UI 创建并真实调用 DeepSeek：原样基准 FAIL，修改钳位电压与等待策略后计算 PASS。执行中追加的证据要求通过 steering 接收；完成后第三条追问使用持久化 Pi 上下文，正确回顾 1000 µF 与 3.45 V，并记得上一条补充要求，未新增实验。共 3 条用户消息，2 次 Pi 进程启动，14 次模型请求，2 次实验。

本轮计费上界 $0.0457188，最高单请求 $0.0057897，全部 usage 已结算。新授权最多 $1，工程硬上限设为额外 $0.99、单请求 $0.19，原账本保留。总计上界 $2.983629。授权与有效期保存在 `bf-agent-workbench/verification/chat-budget-authorization.json`。

## 验证与复现

- `PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m unittest discover -s tests/agentlab -v`：26 项通过。
- 在 `/Users/depengsu/Documents/bf-agent-workbench/verification/battery-world` 运行 `./init.sh`：217 项测试及 SDK/Studio 检查通过。使用隔离副本，避免重建工作目录中的历史实验产物。
- Pi 新 `chat.ts` 通过 tsgo 构建；浏览器检查了初始输入、真实流式过程、补充要求、继续追问、刷新、侧栏折叠与键盘展开、分区和开发者编辑器。最终页面无控制台错误。
- 1365 个历史工作台文件与 126 个既有科学源码文件哈希不变。

结构化证据见 `SESSION-CHAT.json`。日志位于 `bf-agent-workbench/verification/chat-final-tests.log` 和 `chat-init.log`。

## 当前边界

每个新会话沿用累计 24 次模型请求、6 次实验和约 10 分钟的 owner 时限；恢复会话不会重置这些限制。达到限制后历史记录保留，可新建任务。旧批处理会话只读，向旧记录补充任务会创建新会话。消息持久化且带幂等 ID；发送状态不明时不会擅自重发。流式内容是模型公开文本与工具事实。此次 PASS 是固定计算环境内的结果，不代表硬件、训练模型或 RSI 效果。

新前后端控制器和 Pi chat 入口均已接通。没有提交 Git，也没有改动早期 B2 科学实验的权限和语义。
