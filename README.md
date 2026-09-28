# BF-AIoT Agent

当前 BF-AIoT Agent 与设计工作台的源码快照（2026-09-29）。工作台围绕同一产品任务组织设计、工具执行、交付物和验证证据；Pi 负责 Agent 执行，Harness 与科学环境分别保留身份和版本。

## 目录

| 目录 | 内容 |
| --- | --- |
| `battery-world/apps/agent-studio/` | 当前工作台：任务、控制台、全景、产品；流式对话、Trace、工具/Memory/Harness、架构地图、产品节点交付物 |
| `battery-world/packages/python/bfworld/src/bfworld/agentlab/` | 本地服务、会话与预算、Agent 调度、工程适配器、交付物绑定、参考案例与验证 |
| `battery-world/scripts/` | 可执行设计、构建、仿真、固件、校验和案例发布脚本 |
| `battery-world/configs/`、`contracts/`、`fixtures/` | 配置、契约和确定性测试输入（后两个目录也在 battery-world 内） |
| `battery-world/tests/`、`docs/`、`project/` | 测试、研究记录、当前工程状态（均在 battery-world 内） |
| `pi-bf-aiot/packages/bf-agent/` | 定制 Pi Agent 与 BF-AIoT 工具接入 |
| `pi-bf-aiot/packages/bf-harness/` | 求解程序、提示词和 Harness |
| `pi-bf-aiot/` 其余目录 | 固定版本的上游 Pi 源码及构建依赖锁定文件 |
| `integrations/` | 本机在用的立创社区 MCP 与三个 EDA 技能源码快照 |
| `release/` | 源码清单、来源、校验脚本和此次发布验证记录 |

产品页可按节点查看图片、仿真、原生工程、代码、报告和数据；交付状态与文件数量分开。原作者参考电路不会被计为当前设计的原理图或 PCB。

## 本次上传范围

这是**源码发布，不是本机工作区或实物产品交付备份**。包含当前源码、锁文件、文档、测试、必要浏览器依赖和小型基准数据。不包含密钥、认证令牌、会话数据库、参与者工作区、完整私有运行轨迹、模型账单状态、已安装工具链或大型仿真二进制产物。COMSOL、Blender、立创 EDA、编译器与各自许可需要单独安装；工具接入代码不等于这些软件或硬件已可用。

原机参考案例的 COMSOL/STEP/GLB/固件产物仍保存在本地 `bf-agent-workbench`。新克隆没有这些本地资料时，产品页应显示缺失，不能把源代码存在解释为该交付项已验收。

本版立创原理图、PCB 与制造图纸仍未完成；仿真结果不代表实测、制造或烧录验收；源码上传也不构成自主 Agent 或 Harness RSI 有效性的科学结论。工程状态见 [产品交付物说明](battery-world/docs/agentlab/PRODUCT-DELIVERABLES.md) 与 [原生仿真说明](battery-world/docs/agentlab/PLUCK-NATIVE-SIMULATION.md)。

## 构建与本机启动

当前执行隔离依赖 **macOS `sandbox-exec`**，尚未完成通用跨平台安装。需要 Python **3.11**、Node **22.19+** 和 Corepack/pnpm **11.7.0**。上游可选 Gondolin 扩展示例要求 Node 23.6+；当前 BF Agent 构建在 Node 22.22.0 验证。

```bash
git clone https://github.com/littleandbrother/agent.git
cd agent
python3 release/verify_source.py

cd pi-bf-aiot
npm ci --ignore-scripts --no-audit --no-fund
npm run bf:build

cd ../battery-world
BFWORLD_BOOTSTRAP_PYTHON="$(command -v python3.11)" ./bootstrap.sh
./init.sh
```

`--ignore-scripts` 避免上游仓库级 hook 安装；可选原生后端可能仍需对应平台的独立构建。这里的 Pi 构建使用随源码保存的模型目录数据，不执行在线模型生成步骤。

**路径迁移尚需显式配置**：当前快照保留了原机绑定，没有批量改写历史证据。换路径启动前，检查 `battery-world/packages/python/bfworld/src/bfworld/agentlab/` 中 `launcher.py` 的 `PI`、`HOME_ROOT`、`NODE` 及隔离自检路径，`provider.py` 的 `KEY_PATH`，以及 `product_build.py`、`deployment.py` 和相关 `scripts/` 的外部工具链路径。`panorama.py` 按相邻 `pi-bf-aiot` 目录定位。调整运行源码后应重新构建/冻结 Harness；旧回执不能冒充新环境结果。

路径配置好后可启动工作台（不要与正在使用的服务共用 state 目录）：

```bash
PYTHONPATH=packages/python/bfworld/src .venv/bin/python \
  -m bfworld.agentlab.server --root /absolute/path/to/bf-agent-workbench/state --port 8768
```

使用新 state 目录生成的 `launch-url.txt` 打开带本机认证的入口。不要提交这个文件或 `operator.token`。模型调用还需要在受保护的本地文件配置凭据，并明确当前费用/时间额度；本次发布验证没有调用付费模型。

立创适配器默认从 `~/.codex/tools/bf-jlceda/easyeda-pro-mcp` 和 `~/.codex/skills/{easyeda-api,easyeda-schematic-net-fanout,easyeda-pcb-routing}` 读取组件。`integrations/` 保存这些目录当前实际安装的源码；迁移时可配置适配器路径，或在确认目标目录未被其他项目使用后安装到这些位置。官方 API Skill 的本机版本没有全部上游格式指南，发布清单忠实保留已安装内容。它仍需要立创原生应用、API Gateway 插件和正确的工程绑定，不能只靠复制文件宣称电路环境可用。来源与验收边界见 [JLCEDA-INTEGRATION.md](battery-world/docs/agentlab/JLCEDA-INTEGRATION.md)。

`battery-world/README.md` 中的 8766 是较早的科学 World Studio；当前四模式 Agent 工作台是上述 8768 服务。两者不是同一个前端。

## 校验与来源

`release/source-manifest.json` 逐文件记录导出源码的 SHA-256；它不是运行证据包，也不含本地密钥。`python3 release/verify_source.py` 验证导出文件是否仍与快照一致。克隆后的构建或本地路径修改可能合理地产生差异，应作为新版本记录。

Pi 来源：<https://github.com/earendil-works/pi>，基线 `7140838fdd5ee1ff21dbe50955a8801617b065ef`，包含本项目的 `bf-agent`/`bf-harness` 定制。保留 [Pi MIT LICENSE](pi-bf-aiot/LICENSE)、[Three.js LICENSE](battery-world/apps/agent-studio/vendor/three/LICENSE) 及各上游文件原有声明。本仓库是源码快照，不继承或声称拥有上游完整 Git 历史。

本次验证范围见 [release/VERIFICATION.md](release/VERIFICATION.md)。
