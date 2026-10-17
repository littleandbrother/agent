# BF 任务与设计范式：首批实现

日期：2026-10-17。开发分支：`codex/bf-architecture-v2`。

核心规范：[STANDARD-DEFINITIONS.md](STANDARD-DEFINITIONS.md)。任务结构 `bf-design-task-definition-v2`，运行语义 `bf-task-semantics-v1`，Pi 插件配置 `bf-product` 1.3.1。

## 实现内容

| 部分 | 本批实现 |
|---|---|
| 任务定义 | 任务意图、场景、参数来源与角色、允许修改范围、验收条件、报告配置写入不可变 System Commit |
| 功能与器件 | 功能引用实际组件；多个功能可以共享一个组件；专业分工单独记录 |
| 案例配置 | 曲线数据对比、PCB 审查、P01 数字工程、常规压电名义参考链各用自己的检查与报告范围 |
| 执行与验收 | 执行身份包含实际输入和环境；验收身份增加要求与检查器；改误差门槛复用原数据重新判定 |
| 连续修订 | 部分文件提交继承完整父树；原候选及其结论保留；审查任务拒绝设计修改 |
| 运行恢复 | 操作先登记再执行；已完成输入复用；明确失败封存诊断；未知操作阻止重复派发 |
| 交付 | 当前候选、原始输出、独立检查、PDF、文本和来源清单进入同一 ZIP |
| Pi | 新增 `bf-task-design` Skill；工具说明按任务配置提供；新参考任务使用现有 Repository 控制器 |

现有 P01 继续使用原八项工程门和八页报告。原十个会话、工程和费用记录保持原位。

## 常规压电参考链

执行顺序：梁与质量块参数 → 双向机电模态模型 → ngspice 电输出 → 固定转换效率 → 储能求解 → 实际编译的 C 事件程序 → 状态负载 → 数字接收检查。

输入固定为 30 Hz、峰值加速度 4.905 m/s²、20 秒窗口、2.5 V 初始储能。要求至少 3 次有效采样与接收。材料、电流与转换效率采用预先声明的参考值。BF 可修改梁几何、质量块、储能电容和程序调度。

该任务的验证范围是名义模型、主机编译程序和数字接收端。产品阶段继续接目标 MCU、具体 PMIC、原生 CAD/PCB、装配与实物。

独立检查覆盖源模型解析响应、线性位移范围、实际程序到负载的对应、能量核算、采样与发送供电窗口、序号及校验。无 Agent 参考先运行正常条件、无能量、错误帧及源仿真复用控制；通过后开放 Pi。

同一源网表和环境的成功结果在固件修订时复用。检查器修订只重新计算判定。参考校准与 Pi 设计分别记录作者和执行来源。

## 代码入口

- `design_lab/repository_profiles.py`：任务、报告、接口与模型实际可见合同。
- `design_lab/repository_task_standards.py`：参数绑定、硬约束、设计范围、实际接口消费者、有效判据、执行/验收场景及阶段转换。
- `design_lab/repository_task_state.py`：由现有候选、回执和检查计算可执行、待恢复、待判断与已交付状态。
- `design_lab/repository_task_actions.py`：创建任务、确认任务阶段和提交候选。
- `design_lab/repository_task_execution.py`：输入绑定、执行、失败与精确复用。
- `design_lab/repository_task_checks.py`：独立检查与候选当前资格。
- `design_lab/repository_reference_node.py`：常规压电参考执行器与检查。
- `design_lab/repository_reference_qualification.py`：参考资格及共享参考结果读回。
- `design_lab/repository_task_reports.py`：范围对应的 PDF、文本和来源绑定。
- `design_lab/repository_task_result.py`：精简数值、每帧窗口与原始结果的只读分页；所有数值保留输入来源。
- `pi-bf-aiot/packages/bf-agent/src/repository-task.ts`：实际 Pi 入口。
- `pi-bf-aiot/packages/bf-harness/resources/skills/bf-task-design/SKILL.md`：按需方法。

Python 路径前缀为 `battery-world/packages/python/bfworld/src/bfworld/agentlab/`。

## 复现命令

在 V2 的 `battery-world` 目录执行：

```sh
rtk proxy python3 scripts/verify_task_design.py --pattern '*repository*.py' --output docs/agentlab/architecture-v2/task-design-20261017/verification/repository.log
rtk proxy python3 scripts/run_reference_node.py --output /Users/depengsu/.local/share/bf-agent-architecture-v2/task-design/reference-qualification
rtk proxy python3 scripts/task_design_ops.py status
rtk proxy python3 docs/agentlab/architecture-v2/task-design-20261017/standards_consumer.py --source-system SC-5719b733541cdb0e3d275015c423100bf965cbe6584c8265940ea7c5b25ad1eb --output /tmp/bf-task-standards-replay-NEW
rtk proxy env BFWORLD_VERIFY_PROFILE=architecture-v2-lab BF_V2_EVIDENCE=/tmp/bf-task-lab-check-NEW ./init.sh
```

`run_reference_node.py` 对相同执行输入读取已有结果。资格记录独立封存，检查版本变化后重新评价。

部署和 Pi 派发由 `task_design_ops.py` 的 `publish/create/start` 操作进行，操作身份与新 owner 固定。首次运行前保存原状态；`verify-preservation` 在结束后核对。

`standards_consumer.py` 在隔离的 Repository 中复核实际 Pi 候选，原库按只读方式取得对象。输出目录须为新目录，原生执行入口在回放中被禁止。`--source-system` 只选择隔离副本的回放检查点，原项目保持当前版本。未指定时，优先使用定义发布回执中的原始 Pi 候选。首次回放为 `standards-consumer-002`，发布后的可复现回放为 `standards-consumer-003`。

本次线上定义迁移使用 `publish_standards.py`，已有不可变回执时拒绝再次执行。恢复直接读取 `standards-publication-v1` 的执行、检查及交付记录。

验证日志与最终运行结果见本目录的 `verification/` 和 `RESULTS.md`。

## 实际消费与当前交接

两轮 Pi 设计已完成。当前采用 R7 为 68 µF，机械参数保持参考值，主机程序按 2/6/10/14 秒调度；五项名义检查通过。随后追加同工程的标准定义接入版 R8，原始执行、费用及采用身份保持不变。原 P01 的八项门和当前/采用身份保持不变。

结果读取接口提供固定负载电源轨下的电荷/能量、采样与发送窗口最低电压，以及能量残差的原始分母和单位。报告阶段的数值复核直接读取封存波形，不触发新求解。报告中的解释由 Pi 编写，数值表由程序计算。

参考资格同时固定执行环境、检查器与证据摘要。更换检查实现后，需要重新取得资格；本次重新资格使用已有执行数据，源与储能求解均复用。

`curve-reproduction-v1` 当前实现配对 CSV 数据比较；`pcb-completion-v1` 当前消费已有原生审查结果。后续模型复算和通用 PCB 写入执行器分别扩展，保持这两个入口的验收范围明确。
