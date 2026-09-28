# BF Agent 工作台

当前交互说明：[会话与流式执行](SESSION-CHAT.md) · [文件夹、共享配置与撤回](FOLDERS-RECALL.md)。

本地界面：`http://127.0.0.1:8768/`。首次访问使用工作目录中的 `state/launch-url.txt` 启动链接；它包含本机工作台凭据，不要发布。页面显示 Pi 消息、工具调用、真实计算任务、封存设计、费用上界和施工进度。

```sh
cd /Users/depengsu/Documents/battery-world
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/run_agentlab.py --port 8768
```

程序与数据位置：

- Pi SDK、应用和行为源码：`/Users/depengsu/Documents/pi-bf-aiot/packages/{bf-agent,bf-harness}`。
- 实验器、受控服务、费用代理、启动器与对照控制器：`packages/python/bfworld/src/bfworld/agentlab/`。
- 不可变上传和计算产物：`/Users/depengsu/Documents/bf-agent-workbench/state/{snapshots,runs}`。
- 会话、冻结版本、对照记录：同一工作目录中的 `sessions/`、`harnesses/`、`studies/dev-v1/`。
- 费用真源：`state/workbench.sqlite` 的 `model_requests`，包括失败和中断；历史 B2 账本未复用。

## 执行链

求解使用 Pi `createAgentSession`，显式指定模型、资源和八个工具：`read/edit/write/bash` 与 `bf_experiment/bf_job/bf_inspect_run/bf_submit`。没有发现个人技能、扩展或父目录 AGENTS。模型凭据由外部代理持有；参与进程只得到限额身份。参与进程不能读真实密钥、评估代码或其他工作区，不能访问外网或写父代源码。

`design.json` 是电源与执行参数；`policy.py` 的 `plan(obs)` 在独立受限 Python 进程中选择等待、采样、推理、发送。观察只含当前能量、电压、已完成动作、推理输出和公开要求。策略动作实际控制时序和负载；没有候选编号查表。电源积分器由冻结的 profiled v2 派生，相同行为序列已核对电压、电流、能量和接收结果的一致性。

任务结果把程序完成、设计通过和资产不可评估分开。只有外部实验与当前上传散列一致时才能提交。重复 operation ID 不会产生新任务；未知任务保持 UNKNOWN。恢复首先加载原冻结版本，再按原操作 ID 对账。

第二个独立 Pi 进程读取公开开发轨迹，在独立副本中修改 `solver.ts` / `improver.ts`，自行编译修复。外部控制器再构建、记录 diff，并在新进程中核对实际加载散列。生成、构建、激活、对照收益和正式提升分别记录。

## 费用与边界

用户授权 DeepSeek V4.1 Flash，单次小于 USD 0.20，总额小于 USD 3。服务使用经模型列表确认的 `deepseek-flash`，单请求限制为 USD 0.19；总硬限额初始为 USD 2.90，在最后两次预声明后代比较前使用仍获授权的缓冲额度调为 USD 2.99（见 `reserve-budget-amendment.json`）；单次输出最多 8192 token、24 次模型请求及 6 次实验 / Pi 会话、600 秒 / 会话、6 小时全局窗口。初始 9M token 闸门曾中断两次后代求解；用户明确要求继续后，留档声明累计 9.2M token 续跑窗口，总费用仍严格受 USD 2.99 闸门约束。原始试验协议保留初始额度，修订没有重置任何费用、请求计数或时间窗口。按官方峰时价格、输入全部计作未命中缓存估算保守费用上界；不是供应商账单数值。用量不明时保留全部预留并停止新请求。价格来源：<https://api-docs.deepseek.com/quick_start/pricing/>。

当前科学任务为明确声明的合成计算 BF-AIoT 参考任务。它使用既有信号与手写分类器，没有冒充训练得到的 TFLite、ELF、实测波形或硬件闭环。缺少必需模型资产的任务返回 NOT_EVALUATED，不降级替代。尺寸、CAD、PCB、新 MCU、PV/压电和硬件迁移在对应实物、模型和工具链被实际接入前均不算通过。

## 复核

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m unittest discover -s tests/agentlab -v
```

Pi 新包可以由 `npm run bf:build` 连同固定 SDK 构建。正式对照由 `python -m bfworld.agentlab.study evaluate --arm h0` 等命令启动，禁止在已冻结试验中变更工具、任务语义、资源或预算。完整 `./init.sh` 在独立副本中执行，日志位于工作目录的 `verification/`，以免重建旧封存产物。

两次重复仅是开发规模；零收益、退化、未激活和基础设施失败都必须报告，不能据此宣称统计上的 Agent 或递归自改进提升。

## 递归与迁移

`bfworld.agentlab.recursive` 提供 `prepare / evolve / controls / meta / transfer / report` 命令。协议、公开轨迹身份、谱系、无修改候选、越界拒绝和每组对照保存在 `studies/recursive-v1/`；真实源码候选在 `studies/dev-v1/candidates/`。P 是 `solver.ts`，U 是 `improver.ts`。操作系统拒绝写本轮不可修改的源文件，外部 diff 仍是最终范围检查；这不替代父代只读和评估器隔离。

求解成功、U 源码变化、U 实际生成后代、后代任务成绩是不同证据。新 U 的经验摘要接口检查若失败，必须记录，不能因为编译通过就说摘要生效。开发成本包括无修改、越界、截断与恢复。

为遵守用户总费用上限，递归试验在任何新对照运行前记录了预算修订：四组核心条件和两组后代条件各运行 dev-02 一次，再对两个未见迁移条件作父子比较，共 10 次；公开输入仍保持相同的四条完整 H0 轨迹。该修订不改变已完成的 H0/H1 16 对开发比较，也不支持统计有效性结论。

最终两条后代任务均在原 owner 上恢复并通过，原请求数、6 次实验总额、输入与代码身份不变。`user-continuation-window.json` 和 `continuation-audit.json` 记录续跑范围与控制器来源说明。结果是经历中断后的开发比较，不是无中断元改进效果的估计。全部预声明计算试验完成后再次关闭付费窗口，最终上界 USD 2.9379102。
