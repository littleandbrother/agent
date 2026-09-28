# 产品执行链与统一阶段判定 — BFA-025

日期：2026-09-29。范围：平台优化与可复算的本机集成验收；不是完整磁拨动产品、物理校准或自主设计效果的验收。

## 本次实现

| 原问题 | 修改 | 可以检查的事实 |
|---|---|---|
| Pi 与交付页完成口径不同 | `product_authority.py` 统一阶段判定；assembly、deliverables、任务上下文共用一个 verdict | 同一 owner/revision 的 verdict_sha256 一致；旧数字目标保留明确范围 |
| 所有产物因无关改动一起失效 | 分离需求、接口、几何、能源和展示输入；依赖绑定沿图传播 | 改相机/颜色影响展示；改结构影响 CAD；篡改产物会撤销通过状态 |
| 只能改模板参数 | `engineering-project` 接收参与者源文件清单 | CadQuery 原生 STEP、ngspice 原始数值、STM32L031 多 C 文件真实目标构建及独立读回 |
| 几何与求解参数脱节 | `beam-event` 提供显式矩形梁到候选 ROM 映射 | 长度翻倍刚度变成 1/8；映射后的参数实际进入联合 ngspice，而非只画连线 |
| 产品策略埋在主循环里 | 新增 `bf-harness/src/product.ts` | 提示、任务事实包与续跑策略可编辑、冻结、加载；Trace 记录实际加载哈希 |
| 历史对话挤掉当前工程事实 | 每轮注入带哈希的 `bf-product-context-v1` | 当前需求/假设/接口/版本、待处理任务、失败和证据指针；共享笔记仍未验证 |
| 产品页只列文件 | 节点增加“当前判断 / 假设 / 待验证问题” | 先交代问题、局部检查和缺口，再看绑定产物；参考与当前任务分开 |
| 本机路径耦合 | 运行配置统一为操作者环境变量 | 新源码位置可显式绑定 Pi、运行数据和工具链；不会读取旧位置 Pi 来冒充新构建 |

没有改写科学世界、冻结的研究协议、旧参考回执，也没有将未通过的论文校准改为通过。

## 启动与路径

当前应用：`apps/agent-studio`，Python 服务默认 8768；早期科学展示：`apps/world-studio`，pnpm 服务 8766。两者保留不同职责。

从 battery-world 启动：

```sh
export BF_HOME="$HOME/Documents/bf-agent-workbench"
export BF_PI_ROOT="$(cd ../pi-bf-aiot && pwd)"
PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m bfworld.agentlab.server --port 8768
```

`BF_HOME/state/launch-url.txt` 是本机认证入口，不应提交或分享。新迁移要使用独立 state，不能让两个服务共用数据库。

| 配置 | 含义 |
|---|---|
| BF_HOME | 本机工作台数据根目录，不是源码目录 |
| BF_PI_ROOT | 当前 Pi 源码根目录；默认相邻 pi-bf-aiot |
| BF_NODE | Node 可执行文件 |
| BF_PROVIDER_KEY_FILE | 本机受保护凭据文件路径；内容绝不进入源码/页面 |
| BF_CAD_PYTHON | 已安装 CadQuery 的 Python；保留 venv 路径而非解析为宿主 Python |
| BF_BLENDER / BF_COMSOL / BF_NGSPICE | 可选工具可执行文件 |
| BF_ARM_GCC / BF_CMSIS | ARM 编译器和 STM32L031 CMSIS 文件夹 |

这不是自动安装器。作者工程沙箱目前要求 macOS sandbox-exec；缺失时拒绝执行。历史案例脚本、EDA 安装路径和专有软件仍需各自配置，不能宣称任意系统开箱即用。

## 工程项目协议

参与者通过现有 write 工具生成工程，再调用：

```json
{"action":"run","engine":"engineering-project","operation_id":"revision-1-build","parameters":{"assembly_revision":1,"project_path":"project/project.json"}}
```

示例 manifest（SPICE）：

```json
{"schema_version":"bf-engineering-project-v1","kind":"spice","entrypoint":"main.cir","files":["main.cir"],"interfaces":{"units":"SI","load_source":"declared estimate"}}
```

支持 cadquery / spice / firmware-stm32l031。最多 32 个 UTF-8 文件、合计 2 MB；禁止路径逃逸和符号链接；SPICE 拒绝外部 include、控制脚本与 shell 指令；固件仅用固定链接器/SDK，不接收参与者构建命令。CAD Python 在拒绝网络、限制读写路径的进程中执行。180 秒墙钟上限、120 秒 CPU 和单文件 64 MB 限制；结束时清理进程组。它不是通用容器配额系统，未声明跨平台或抗所有内核攻击。

源码在提交时快照并哈希绑定，新源码使用新 operation_id。结果提供 source ZIP、原生文件、执行记录和独立 readback；不采信参与者自写的 PASS。所有模块沿用工程 Job 与 Trace，不另建一套任务账本。

CAD 检查实体、尺寸和体积，不能证明装配可达性；SPICE 检查原始文件有限值/点数，不能证明电路选型或工作域；固件检查 ELF/Flash/静态 RAM 和预留栈，不证明板引脚兼容、动态峰值、无线接收或已烧录。可在 manifest 声明接口，但声明仍需专项验证。

## 物理映射的范围

beam-event 输入当前装配、beam-mapping.json 和完整 event-design.json。映射显式指定零件、长度/宽度/弯曲轴、杨氏模量、密度、端部质量、阻尼比及来源。

当前只接受无孔洞/圆角的细长均匀 box，L/h >= 10、固定根部、端位移坐标：I=bh³/12，k=3EI/L³，m_eff=0.2357ρLbh+m_tip，c=2ζ√(km)。压电耦合与电容保留独立来源，不从几何猜测。两个几何方案应共用外部轨迹、初始储能和负载以保证可比较。

几何映射参数真正进入现有联合求解器；粗/细时间步与原始通道可读回。但它不是复合 MFC、磁释放、接触、原厂 PMIC 或实测固件的校准模型。材料来源是参与者声明，尚未自动核实其文献适用性。实测负载只接受已有操作者导入、固件绑定与电压匹配的测量。

## 阶段、适用性与界面

阶段为：需求与方案 → 原生数字模型 → 工程文件齐套 → 计算与工程验收 → 实物验收。

- 在控制台“交付与部署”折叠区设置本轮目标及原因；CAS 版本校验，参与者不能更改目标。
- 默认没有自动续跑；已有旧数字交付目标或操作者阶段合同才允许有界续跑，预算规则仍生效。
- 阶段通过不等于后续阶段通过，硬件没有测量仍为 not_measured。
- 从 PV 字段推定太阳能类型时，五项拨动专用任务标记不适用；推定原因可见。完整的通用多产品合同编辑/类型库尚未实现，部分历史合同用语仍来自拨动案例。
- 全工程计算通过要求每个适用条目都有专项独立验收。当前大量条目仍没有完整检查器，继续 not_run，局部 native checks 单列；因此本次不宣称三十项全部可自动验收。
- 任务模式显示简短阶段与跳转；产品模式展示节点问题、假设、证据和缺口；控制台保留配置/工具/原始 Trace；全景映射新增实际代码模块。全景关系仍为声明式架构，不冒充由 Trace 推断的物理因果图。
- 图像预览仍供使用者审查，未新增视觉模型或自动审图结论。

## 验收与复算

```sh
./init.sh
PYTHONPATH=packages/python/bfworld/src .venv/bin/python -m unittest discover -s tests/agentlab -p test_product_authority.py
PYTHONPATH=packages/python/bfworld/src .venv/bin/python scripts/verify_product_authority.py --output /absolute/new/acceptance-directory
```

最后一条启动真实独立 Pi 进程，使用脚本化本机模型响应，通过公开工具写入网表/manifest、提交工程、轮询真实 ngspice、检查独立读回与实际 product.ts 加载哈希。它不调用外部模型，不评估自主推理能力，不是伪造一次模型自主成功。

本机验收目录：bf-agent-workbench/verification/product-authority-20260929。Pi public chain 完成 6 次脚本化响应，0 次外部模型调用；真实 ngspice 120 点、4 通道，readback 通过，全工程完成仍为 false。针对性测试覆盖阶段冲突、输入/输出篡改、跨 owner、符号链接、沙箱越界、镜头负控、几何敏感性、真实 CAD / SPICE / 多源目标固件。

一次全量检查暴露新增测试在完整 discover 下的相对导入问题（单独 discover 正常），已修正为兼容两种入口。独立发布目录验收还发现 macOS 云端占位文件使 TypeScript 编译及沙箱中的 CAD 依赖读取超时：按 Git/清单恢复缺失源码、按相同锁文件恢复构建依赖，并隔离生成的云端 Python 字节码、将 CAD 导入依赖下载到本机，未放宽超时。恢复后九项原生/边界专项复核通过。全景对云端占位历史快照/源文件改为可见缺失状态并跳过阻塞读取；不会将不可读取记成删除或通过。七项全景检查包括相应负控。最终全量与发布副本结果见 release/VERIFICATION.md；保留前次失败和被终止日志。

## 后续仍需完成的工程与研究

1. 解决拨动参考的磁力、极性、SP-SECE 量值和高压工作域偏差；以同一输入连接原厂 PMIC 与真实负载；保留失败，不能靠改阈值过关。
2. 为当前拨动产品完成同版原生 EDA/PCB/制造数据、板级引脚和固件、独立专项检查器；不能拿太阳能旧板充当本版电路。
3. 推进受控 COMSOL 原生工程作者接口与对照读回；本轮保留原静力模板，未声称任意压电 FEM 已向 Pi 开放。
4. 在参考模型/产品合同封存后，以真实付费模型开展独立改设计、长程修订和同起点方法替换；本机脚本化集成测试不能作为 A/B/C 方法效果。
5. 有实物后再进行同步功耗、烧录、接收端与结构测量。当前仿真优先的要求不使仿真升级为实测。

BFA-025 的完成只指上面的平台功能与本机验证。BFA-024 仍因校准和本版板级工程缺口 blocked；原科学 88 项 Feature 和 feat-397 不变。
