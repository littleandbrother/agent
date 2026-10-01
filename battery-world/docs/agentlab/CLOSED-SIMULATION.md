# 门磁参考案例：可复算的全仿真链路

本轮实现的是**受限模型内的端到端计算闭环**。原生 CAD、COMSOL 梁参数、有限磁体力表、LTspice 原厂电源模型、共享 C 程序与虚拟接收器通过一个入口连接。六项工程链路验收与四项额外对照已通过，D2 本身仍不能冷启动；不得把链路连通当作产品合格。

## 1. 使用入口与页面

- Pi 工具：`bf_engineering`，`action=run`，`engine=closed-simulation`。
- 参数：`parameters={"candidate":{},"confirmation":true}`；先读取 `closed-simulation` Skill 查看范围。
- 使用固定 `operation_id` 查询同一个 job；换候选时使用新 ID。不能在一个 operation 下偷偷换参数。
- Lab → 控制台 → 系统 → Tools → 全仿真链路，能检查安装环境、修改参数并运行。
- Studio → 产品成果 → 所选会话成果 → 系统与交付，查看联合波形、指标、输入、检查及下载。参考工程 D2 是单独的冻结范围，新计算不会覆盖它。
- Lab → 运行 → Trace，保留工程 job、输入、逐阶段执行/复用、进程退出以及文件摘要。操作者发起的本地验收不冒充 Pi 自主运行。

调用示例：

```json
{
  "action": "run",
  "engine": "closed-simulation",
  "operation_id": "door-candidate-001",
  "parameters": {
    "candidate": {
      "mechanical": {"gap_mm": 48, "opening_s": 2},
      "circuit": {"cin_uF": 47},
      "firmware": {"interval_ms": 100}
    },
    "confirmation": true
  }
}
```

省略项来自 `configs/reference_cases/closed-simulation/d2-nominal.json`，实际展开的全部条件写入 `design-spec.json`。这是门磁压电参考模型，不是任意产品的通用物理仿真。

## 2. 真正相连的计算过程

1. **CAD**：实际 22 实体参数化装配，磁体间距同时更新闭门世界坐标与原生 STEP；读回中心坐标检查一致性。
2. **梁 ROM**：原生 COMSOL 提取刚度、第一阶频率、逆压电响应和电荷；用互易关系提取耦合项，扣除自由电容中的机械贡献，得到约束电容。
3. **磁力**：有限长方体表面磁荷积分，包含门转角和梁端位移，生成 `F(angle,q)`；统一硬磁体、相对回复磁导率为 1 的假设。表是解析数值模型，不能标为完整 COMSOL 网格。
4. **原生联合求解**：将机械 ODE、互易压电源和单份 Cp 写进同一 LTspice 电路，接 LTC3588-1 原厂宏模型。电路负载反过来改变机械运动，不再人工单向搬运波形。
5. **程序在环**：同一份 C 状态逻辑分别编译为主机库与 Cortex-M4 对象。读取供电/PGOOD 后推进 RESET、BOOT、WAIT、INIT、TX、SLEEP。RESET 与 WAIT 仍消耗电流；PGOOD 只是输入信号。
6. **供电与程序反馈**：原生供电波形驱动 C 逻辑，产生新负载，再重跑电路，直到负载完全一致、供电差异低于 1 mV。达到迭代上限直接记为数值失败。
7. **虚拟接收**：只有完整 TX 才产生带时间的报文字节，经过固定种子的丢包/扫描模型，交给现有接收端解码、分组、去重。发送中掉电不产生完整包。
8. **确认**：更细时间步、程序采样间隔与求解容差重算；COMSOL 独立磁场锚点与两档网格检查；检查机械/压电端口能量平衡。

QEMU 官方资料明确表示当前不支持 nRF52，因此这里没有把主机 C 状态机称为 nRF52832 完整芯片仿真。ARM 对象也不是新的可烧录镜像。已有 D2 固件工程保留，但尚未证明其 SoftDevice、外设、周期及功耗与此 SIL 模型等价。

## 3. 运行、模型预测和产品证据分别记录

`Result` 区分：

- `run_status`：completed / numerical_fail / input_error / out_of_domain / tool_fail。
- `predicted_design_status`：仅在计算完整时给出模型内的 satisfied / unsatisfied。
- `design_status`：本版本统一为 insufficient_evidence；完整模型充分性尚未确认。
- `product_verified=false`、`hardware_calibrated=false`。
- `failed_stage`、`unreached_stages`、`checks`、`model_versions`、`applicability`、`energy_ledger`、`events`、`artifacts`。

正常算出 0 个包是设计预测失败；模型越界或数值失败则不能拿去给设计排序。`diagnostic_input_A` 或初始储能非零的结果必须标为受控模块诊断，不能用于证明单次动作自供电。

## 4. 缓存、恢复与版本

阶段为 `cad → beam/force/firmware → joint → numerical/magnetic-confirmation`，每阶段有内容键、输入、输出摘要、耗时及原生文件。修改相关输入重新生成，未变阶段逐文件校验后复用。

- 机械间距改变 CAD、力表和联合计算；当前固定梁 ROM 可复用。
- 电容改变联合求解，不能复用旧联合波形。
- 程序配置改变头文件、主机库、ARM 对象、负载及包时序。
- 相机字段只改变 presentation identity，不改变计算 identity。本入口不重渲染 Blender 相机。
- 未完成的 `.partial-*` 保留错误，不可命中缓存；中断后用同候选的新运行目录恢复。
- 缓存文件被修改时拒绝使用，不能静默当作有效证据。
- Python/数值库版本、相关源码、编译器、电路模型和原生程序摘要进入相应依赖键。
- 原始 native RAW 保留。LTspice UIC 的全零显示起始行仅在派生数据中按明确初值纠正，处理方式写入能量账。

本轮沿用现有工程队列与本地内容寻址检查点，未额外部署 Snakemake、Nextflow、DVC 服务。它们仍可作为日后的远程调度与存储替换层，不是本地链路闭环的前提。

## 5. 已取得的原生结果

基线输入：48 mm 磁体中心水平间距，2 s 开门至 65°，47 µF 输入储能，100 µF 输出电容，100 ms 广播间隔，零初始储能、零外加电流。

| 条件 | 储能峰值 | MCU 供电峰值 | 完整 TX | 虚拟接收事件 |
|---|---:|---:|---:|---:|
| D2 受限模型基线 | 0.145752 V | 约 1.06 µV | 0 | 0 |
| 间距改为 50 mm | 0.109461 V | 约 0.804 µV | 0 | 0 |
| 输入电容改为 22 µF | 0.269113 V | 约 1.97 µV | 0 | 0 |
| 外部 1 mA 受控输入诊断 | 20.0316 V | 3.34857 V | 36 | 1 |

基线梁端峰值约 4.537 mm，机械/压电端口能量相对残差约 1.75×10⁻⁶。原生电阻负载与独立 SciPy ODE 在两档电阻下的波形最大归一化偏差小于 0.005%；改变电阻确实改变机械运动，检验了电学反馈连接。

四个单因素端点（阻尼 0.01/0.08、剩磁 1.0/1.4 T）保留各自结果。这是有界敏感性检查，不是 Monte Carlo 成功概率或 Sobol 全局敏感度。没有实际分布依据时不能虚构制造分布并给出可靠性结论。

## 6. 验收与复现

证据根：`/Users/depengsu/Documents/bf-agent-workbench/verification/closed-simulation-20260930/acceptance-v2`。

- `receipt-six-controls.json`：第一轮完整六项及额外对照回执，原生运行约 35 分钟。
- `receipt.json`：最终验收，包括额外模型越界反例。
- 各候选目录：Result、设计规格、波形、程序轨迹、接收事件、能量账、预览和工程归档。
- `cache/`：原生 CAD、COMSOL `.mph`、Java 源码、力表、电路网表、LTspice RAW/log、主机程序库、ARM 对象及阶段摘要。
- `uncertainty.json`：四个端点的有界敏感性结果。
- `schema-validation.json`：15 份 Result 均通过结构校验，包含有意中断、模型越界和工具失败记录。

`outside-rom` 的首次 CAD 启动超时被原样保留。以新目录 `outside-rom-retry` 重试后，28 mm 间距导致初始位移越界，结果明确为 `out_of_domain`。最终回执采用已校验缓存继续，43 秒是续验时间，不能说成所有原生计算仅耗时 43 秒。

```sh
PYTHONPATH=packages/python/bfworld/src \
 /Users/depengsu/Documents/bf-agent-workbench/toolchains/product-cad/bin/python \
 scripts/run_closed_simulation.py --acceptance --output /absolute/new/acceptance-directory
```

隔离科学 Python 测试：

```sh
PYTHONPATH=packages/python/bfworld/src \
 /Users/depengsu/Documents/bf-agent-workbench/toolchains/product-cad/bin/python \
 -m unittest tests.agentlab.test_simulation_chain -v
```

服务层使用应用 `.venv`；数值层在现有 CAD Python 环境执行，避免给 Web 服务强行添加大型科学依赖。COMSOL 与 LTspice 按本机安装/许可证运行，不访问模型 API。

## 7. 尚未关闭的科学与工程门槛

- COMSOL 磁场三锚点的两档网格差约 **11.3%**，高于原定 5% 门槛，明确保留未通过。锚点是非旋转条件，不能代表全部门轨迹。
- 单模态、静态凝聚、小变形梁尚未覆盖几何非线性、接触、脱离、胶层、疲劳；±8 mm 只是本版受限计算边界，非物理安全认证。
- 原厂加密 PMIC 内部损耗未独立核对，完整 PMIC 能量残差尚不能认证。
- 程序时间/电流是声明的包络假设，不是该 ARM 二进制的周期精确功耗。无线为虚拟链路。
- 未接硬件；没有新的烧录、实体接收、整机合格、自主 Agent 效果或 Harness RSI 结论。
- 未改写冻结 D2，不通过调整验收阈值或偷换模型使其“成功”。下一阶段应另建模型版本，优先做磁场局部网格/全轨迹覆盖与机械动态互核，再更新负载参数和整机比较。

因此，可开始基于这套基础设施做受限的候选实验；尚不可宣称完成高保真全产品验证。

依据：[QEMU nRF 平台支持](https://www.qemu.org/docs/master/system/arm/nrf.html)、[ADI LTC3588-1 数据手册](https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf)。


## 8. 服务与页面验收

两条正式本地工程记录已写入原有 SQLite 工程队列与成果索引：

- 基线 `eng-00c0bf8635fe2990`，标题“门磁设计 · 全链路仿真”。
- 受控模块 `eng-0e2031eedbe52805`，标题“受控供电 · 程序接收诊断”。
- 所属会话 `pi-chat-c1152c3ff3c7a5d8`。它们是操作者发起的独立计算；尚未绑定 Agent 产品装配，不计入旧装配验收，也不冒充自主 Pi 实验。

每条记录 18 个文件，总计 36 个文件从实际 HTTP 下载后逐一核对 SHA-256，全数一致。基线文件共 65,362,665 字节，受控诊断文件共 1,337,873,403 字节。原生中间证据在各自 `engineering-evidence.zip` 内；服务按块发送文件，避免大包整体加载到内存。`trace.jsonl`、输入、能量账、RAW/网表等均保留。

浏览器已验证：产品页模型内失败结论、七阶段展开、曲线和六项指标、受控输入说明、Tools 入口，以及“查看本次 Trace”和“返回产品成果”的双向跳转。Trace 能看到阶段缓存校验、进程启动/结束和 job 完成，共 12 条事件。会话中 48 件较早的文件仍显示待恢复；本轮 36 件新产物完整性独立验证通过，未把历史缺失文件伪装成可读。

详见上级证据目录中的 `live-http-validation.json`、`browser-validation.json` 和 `final-receipt.json`。仿真专项 11 项（含实际共享 C 程序与数值依赖）、页面投影 4 项已通过。全量回归的环境异常和恢复情况单独记录在最终回执，不将局部通过等同于全库健康。


## 9. 最终软件核验

最终完整 ./init.sh 已通过：425项Python（4项隔离数值检查另在CAD Python中通过）、SDK类型检查、Studio类型/构建与2803样本复现均通过。Pi本地依赖曾出现空导出与锁接口错误；177份依赖读回校验后真实Pi工具/Skill测试与全量回归通过，未升级依赖、未绕过鉴权/锁/预算，原失败日志保留。云端按需文件读取的长期稳定性不由这次通过保证。

原有 Pi 全仓库 lint 仍有既有警告，不等同于该检查全部通过；本次工具类型构建通过。生产1934条模型账本摘要保持，新增调用0。根协调仓库的88项科学Feature未修改，未运行其科学init。没有Git提交或推送。
