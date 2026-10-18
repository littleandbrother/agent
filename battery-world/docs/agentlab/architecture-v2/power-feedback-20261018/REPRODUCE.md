# 复现与继续

只核对保存的结果与文件摘要：

```sh
python3 docs/agentlab/architecture-v2/power-feedback-20261018/verify_saved.py
```

在 `battery-world` 目录运行：

```sh
BFWORLD_VERIFY_PROFILE=power-feedback \
BF_FEEDBACK_EVIDENCE=/Users/depengsu/.local/share/bf-agent-architecture-v2/power-feedback/qualification \
./init.sh
```

已有资格与证据摘要一致时直接复用，新增模型调用和求解均为 0。更换源文件、工具、检查器或参考条件后生成新的资格身份；原生求解继续按实际网表和工具身份复用。

```sh
python3 scripts/verify_task_design.py \
  --pattern 'test_repository*.py' --output /tmp/bf-feedback-repository-tests.log
node --test tests/agentlab/test_lab_ui.mjs
```

## 接口

参考输入：`configs/reference_cases/piezo-feedback/{task.json,design.json,main.c}`。

- 任务配置：`node-feedback-v1`；执行器：`piezo-feedback-v1`。
- `repository_task_definition` 返回当前任务及运行规范，`repository_task_schema` 返回配置目录；其中包含字段、单位、边界、状态和 C 头文件。定义与校验共用 `repository_feedback_contract.py`。
- `bf_reset()` 清除易失状态；`bf_step(t, dt, VDD, pgood)` 返回当前活动；帧字段由程序提供。
- 状态电流必须给出来源。当前参考使用声明模型；替换为器件模型或测量值会改变执行身份。
- 执行使用 `repository_task_execute`，检查使用 `repository_validate`，报告使用 `repository_task_report`，交付使用 `repository_release`。

执行输入包括完整候选源树、物理条件、初态、程序、模型、工具及数值设置。采样有效期、最小帧数等判据只进入验收身份。检查器读取已封存的完整 RAW，不派发求解。

`feedback-qualification/current.json` 是操作员维护的参考准入指针。独立 V2 已安装并读回，位置见 `evidence/runtime-admission.json`。Pi 无权修改冻结任务与检查器。

## 数值与失效处理

程序按上一观测区间的最小 VDD/PGOOD 决策；电源使用最大 0.1 ms 原生步长。波形迭代要求状态负载一致，并核对电压变化；最多 12 次。程序以 1 ms 和 0.5 ms 两档检查。完整参数与摘要见 `evidence/protocol.json`。

`dispatch.json` 存在、`completed.json` 缺失时返回未知状态，等待对账。完成回执存在时先核对全部产物摘要，再补登记或复用。

首次资格执行上限 48 次新原生求解、2400 s、0 模型调用。共享原生锁沿用现有全机锁，缓存位于独立资格目录。

## 运行身份

资格与运行数据：`~/.local/share/bf-agent-architecture-v2/power-feedback/`。

本轮只发布新适配器的准入指针；原项目与当前采用身份保持。恢复 Pi 时沿原主设计者继续，并显式将新任务基准绑定到新适配器候选。旧固定供电轨迹不作为新程序的环境响应。

参考依赖本机固定的 LTspice / LTC3588-1 宏模型、clang 和 macOS 沙箱。厂商宏模型使用现有安装资产，未加入源码仓库。更换安装位置可用运行配置 `LTSPICE_RUNTIME`，随后重新资格检查。
