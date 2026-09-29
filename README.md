# BF-AIoT Agent

当前 BF-AIoT Agent 与设计工作台的源码快照（2026-09-30）。工作台围绕同一产品任务组织设计、工具执行、交付物和验证证据；Pi 负责 Agent 执行，Harness 与科学环境分别保留身份和版本。

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

## 当前可查看的工程案例

[门磁耦合 D2 报告（36页）](cases/door-magnetic-D2/report/door-case.pdf) · [报告源码与编译说明](cases/door-magnetic-D2/README.md) · [原生工程附件](https://github.com/littleandbrother/agent/releases/tag/door-magnetic-d2-20260930)

D2 包含门动画、22件 CAD/图纸、COMSOL 场图、LTspice 电源仿真、PCB 布线和目标固件。**单次开门冷启动和磁网格验收未通过；原生 EDA ERC/DRC、实物与制造未验收。** 本次文档修订仅改善字体可移植性。源码包含 BFA-026/027 的全会话成果目录与 BFA-028 的不可变工程案例发布，不包含用户会话数据库。

本次发布副本 19 项后端、22 项界面专项通过；上次完整应用回归 407 项中有 12 项失败、9 项错误，尚未全量修复，不能将旧版 388 项通过记录当成本版本全量通过。[当前验证说明](release/DOOR-VERIFICATION.md)。

## 本次上传范围

这是**源码与指定数字工程案例发布，不是本机工作区或实物产品交付备份**。包含当前源码、锁文件、文档、测试、必要浏览器依赖和小型基准数据。不包含密钥、认证令牌、会话数据库、参与者工作区、完整私有运行轨迹、模型账单状态、已安装工具链；指定 D2 原生工程二进制仅作为版本绑定的 Release 附件提供。COMSOL、Blender、立创 EDA、编译器与各自许可需要单独安装；工具接入代码不等于这些软件或硬件已可用。

其余原机参考案例的 COMSOL/STEP/GLB/固件产物仍保存在本地 `bf-agent-workbench`。新克隆没有这些本地资料时，产品页应显示缺失，不能把源代码存在解释为该交付项已验收。

D2 已提供原理图及实际布线，但原生立创验收及可制造图纸仍未完成；仿真结果不代表实测、制造或烧录验收；源码上传也不构成自主 Agent 或 Harness RSI 有效性的科学结论。工程状态见 [产品交付物说明](battery-world/docs/agentlab/PRODUCT-DELIVERABLES.md) 与 [原生仿真说明](battery-world/docs/agentlab/PLUCK-NATIVE-SIMULATION.md)。

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

**运行路径已集中配置**：当前应用通过环境变量绑定源码、数据和工具链；不需要修改 launcher.py 或 provider.py。先配置相邻 Pi 与独立运行数据：

```bash
export BF_PI_ROOT="$(cd ../pi-bf-aiot && pwd)"
export BF_HOME="$HOME/Documents/bf-agent-workbench"
# 按本机实际安装位置设置 BF_CAD_PYTHON / BF_BLENDER / BF_COMSOL /
# BF_NGSPICE / BF_ARM_GCC / BF_CMSIS；BF_NODE 可覆盖 Node 路径。
# BF_PROVIDER_KEY_FILE 只指定受保护的本地文件，不将密钥写入仓库。
PYTHONPATH=packages/python/bfworld/src .venv/bin/python \
  -m bfworld.agentlab.server --port 8768
```

使用新 state 目录生成的 `launch-url.txt` 打开本机认证入口，不提交它或 `operator.token`。模型调用仍需要本地凭据和有效费用/时间额度。本次验收没有外部付费模型调用。部分历史案例脚本和专有软件依赖仍需单独配置；当前作者工程沙箱仅验证 macOS，不等于全平台安装器。macOS 云盘目录中的源码及工具链应保持本地下载；云端占位依赖可能阻塞编译或沙箱导入，全景会将不可读取的历史文件明确标为暂不可用。

本轮新增：统一阶段判定、可冻结的 product.ts Harness、参与者 CAD/SPICE/固件源码项目、几何到联合瞬态映射、产品节点的依据与缺口。详见 [产品执行链与验收说明](battery-world/docs/agentlab/PRODUCT-EXECUTION-AUTHORITY.md)。阶段完成、局部计算通过、完整工程验收和实物验证分别记录。

立创适配器默认从 `~/.codex/tools/bf-jlceda/easyeda-pro-mcp` 和 `~/.codex/skills/{easyeda-api,easyeda-schematic-net-fanout,easyeda-pcb-routing}` 读取组件。`integrations/` 保存这些目录当前实际安装的源码；迁移时可配置适配器路径，或在确认目标目录未被其他项目使用后安装到这些位置。官方 API Skill 的本机版本没有全部上游格式指南，发布清单忠实保留已安装内容。它仍需要立创原生应用、API Gateway 插件和正确的工程绑定，不能只靠复制文件宣称电路环境可用。来源与验收边界见 [JLCEDA-INTEGRATION.md](battery-world/docs/agentlab/JLCEDA-INTEGRATION.md)。

`battery-world/README.md` 中的 8766 是较早的科学 World Studio；当前四模式 Agent 工作台是上述 8768 服务。两者不是同一个前端。

## 校验与来源

`release/source-manifest.json` 逐文件记录导出源码的 SHA-256；它不是运行证据包，也不含本地密钥。`python3 release/verify_source.py` 验证导出文件是否仍与快照一致。克隆后的构建或本地路径修改可能合理地产生差异，应作为新版本记录。

Pi 来源：<https://github.com/earendil-works/pi>，基线 `7140838fdd5ee1ff21dbe50955a8801617b065ef`，包含本项目的 `bf-agent`/`bf-harness` 定制。保留 [Pi MIT LICENSE](pi-bf-aiot/LICENSE)、[Three.js LICENSE](battery-world/apps/agent-studio/vendor/three/LICENSE) 及各上游文件原有声明。本仓库是源码快照，不继承或声称拥有上游完整 Git 历史。

本次验证范围见 [release/VERIFICATION.md](release/VERIFICATION.md)。
