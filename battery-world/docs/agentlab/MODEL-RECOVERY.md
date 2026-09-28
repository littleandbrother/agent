# 模型恢复与对话界面

本次修复让新的用户消息能启动真实 Pi 对话，原有累计费用、token、单次请求和实验次数上限保持。两次真实 DeepSeek 验收分别返回“已收到，可以继续对话。”和“续聊正常”，合计 6,151 tokens，保守费用上界 $0.0018543；验收会话另设 $0.05 硬上限。

## 为什么一直显示模型受阻

历史请求 `llm-c5951a1fa32ae2e442f3` 在 Python 3.11.9 的 TLS 握手阶段失败。错误位置 `_ssl.c:1006` 对应握手函数；HTTP 客户端先完成 connect/握手，才会写入 completion 请求。localhost 实验复现了相同 EOF，只观察到 TLS ClientHello，没有任何 SSL application sendall 调用。[CPython 对应源码](https://github.com/python/cpython/blob/v3.11.9/Modules/_ssl.c#L1006)。

旧程序将这一失败归为“可能已发送且用量未知”，因此持续锁住后续请求。本次用固定版本源码哈希、运行时版本、原行哈希和本地复现证据追加 NOT_SENT 判定；原 UNKNOWN 账本行、NULL usage 和完整 $0.0087363 预留全部保留，既没有伪造零用量，也没有退款假设。后续代码只把 connect 内部直接观察到的失败判为 NOT_SENT；读取响应时的中断、缺失 usage 等仍保持 UNKNOWN 并阻止后续请求。

另一个阻塞来自过期的批量验收窗口。交互模式现由每一条新用户消息取得最多 600 秒执行时间；重复 operation、重试按钮、后台轮询和空闲都不能续期。撤回使对应授权失效。原批量窗口没有改动，非交互 owner 仍按原窗口拒绝执行。累计 USD 3.9279102、9,892,099 tokens、单次 USD 0.19、每会话 24 次模型请求/6 次实验的上限均不增加。

## 页面行为

- 输入框移除了“设置”、工况下拉框和“继续发送待处理消息”。新对话从产品需求开始，明确的基准需求由 Agent 绑定适用计算环境。
- 阻塞和运行异常进入对话中的“执行信息”；输入框下方不再挂模型不可执行提示。旧错误与恢复记录保留在发生的位置。
- 新对话默认显示 3 个案例；可展开到 6 个、收起或隐藏，隐藏偏好持久保存。点击只填入可修改草稿，不会自动发送。这些是需求示例，不是已验证的产品。
- 回答下方增加小复制图标和真实 token 用量。桌面默认隐藏，鼠标经过或键盘焦点进入时显示；触屏保持可发现。显示输入上下文与输出的合计；缺失用量不伪造为零。
- 原用户消息外侧的时间、复制、撤回，以及侧栏、文件夹和开发者入口保留。

## 验证与复现

`PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m unittest discover -s tests/agentlab -v`

全量 `./init.sh` 在 `/Users/depengsu/Documents/bf-agent-workbench/verification/battery-world` 隔离副本运行，避免改写既有科学产物。最终结果见 [MODEL-RECOVERY.json](MODEL-RECOVERY.json)。证据目录为 `/Users/depengsu/Documents/bf-agent-workbench/verification/model-recovery/`，包含 CPython 原文、TLS 探针、原账本备份、追加判定、两次实际请求用量、界面验收及全量日志。原有 775 条模型账本和 1,397 个历史文件逐项验证未变。

生产工作台仍在 http://127.0.0.1:8768/ 。旧待处理任务不会因为服务修复而自动重放，发送新消息才会继续。用户在工作台自行发起的设计运行与本次两条连接验收分开计数。CAD/FEM 与硬件验收未接入；本修复不产生新的科学能力或硬件结论。未提交 Git。
