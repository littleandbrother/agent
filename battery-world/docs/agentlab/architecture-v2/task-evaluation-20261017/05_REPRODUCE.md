# 数据与复现

本目录是 BFA-039 的先导交付，和 BFA-038 任务标准化实现一起发布在 `codex/bf-architecture-v2`。实验运行基点为 `9bcdbad0c275e2af019f3c9645bf5c40ebf38411`；完整实现版本以本目录所在 Git 提交为准。历史回执保留实验当时的基点和工作区状态。

## 文件入口

| 内容 | 路径 |
| --- | --- |
| 简报 | `01_REPORT.md`、`output/pdf/01_REPORT.pdf` |
| 48 题全文、定义、计划及复核 | `02_TASKS.md`、`output/pdf/02_TASKS.pdf` |
| 机制与方法实验 | `03_EXPERIMENTS.md`、`output/pdf/03_EXPERIMENTS.pdf` |
| 两个实际案例 | `04_DEFAULT_AND_P08.md`、`output/pdf/04_DEFAULT_AND_P08.pdf` |
| 模型实际最终回答 | `data/public-model-answers.json` |
| 两轮评估及边界复测 | `data/intake-results*.json`、`data/edge-checks/` |
| 机制参数、结果、特征选择 | `data/mechanisms/` |
| 独立数值校准、压力检查 | `data/mechanisms-controls/` |
| 两批方法提案与选择 | `data/method-pilot*/` |
| 全部实际费用统计 | `data/usage.json` |
| 原工程保护与真实 API 消费 | `data/preservation.json`、`data/api-consumer.json` |
| Pi 自己生成的 PDF 与封存包 | `deliveries/` |
| 确切提示与脚本历史 | `versions/` |
| 逐场景和原生 RAW | 下载包中的 `raw/` |

原始问题答案表在运行前生成；意图/领域评分只衡量与该表的一致性。`qualitative-review.json` 是运行后的人工复核，未覆盖或替换原分数。

## 零派发复核

解压下载包后，运行：

```bash
python3 scripts/verify_results.py .
```

该命令检查清单中每个文件的 SHA-256，并重算保存结果的关键数量、比较关系、P08 误差和费用行状态。不会调用模型、EDA 或求解器。

在原 V2 仓库中也可以运行：

```bash
python3 scripts/task_evaluation/verify_results.py docs/agentlab/architecture-v2/task-evaluation-20261017
```

## 当次执行与代码

| 工作 | 脚本 | 输入与输出 |
| --- | --- | --- |
| 两轮任务评估 | `run.py` | 固定 48 题；每次 request/receipt；输出结构和标签评分 |
| 13 题边界复测 | `edge_checks.py` | 5 已知回归 + 8 新表述 |
| 默认方案与 P08 | `cases.py` | 继续原参考 owner；新隔离 P08 复核 owner |
| 器件原生探测 | `pmic_probe.py` | 原梁/程序 + 本地已安装 LTC3588-1 模型 |
| 机制实验 | `mechanisms.py` | 180 场景、90 对；30 个重放场景 |
| 数值与压力控制 | `stress_controls.py` | 6 校准场景、200 压力场景、输入缓存 |
| 方法提案 | `method_pilot.py` | 3 链 × 2 代，开发反馈/验证选择/固定测试 |
| 数据收集 | `collect.py` | 显式白名单，排除凭据与模型推理正文 |
| 图表和报告 | `report.py` | 只读取保存结果 |

运行脚本绑定原 V2 环境和不可变回执。已存在结果直接返回；发现已派发但结果未知时停止。不要删除回执来重跑。`run.py` 当前使用最新提示；重现历史提示应读取对应 `versions/` 文件与冻结摘要，不能把当前提示冒充旧提示。

报告渲染依赖 matplotlib、numpy、reportlab、Pillow。原机绘图使用系统 Python，PDF 使用 Codex 依赖 Python，分别执行 `report.py --phase data` 与 `report.py --phase pdf`。数据目录和原始轨迹是只读输入。

下载包保留 LTC3588-1 网表、日志、原生结果、模型 SHA；厂商宏模型安装文件由本机 LTspice 提供，不放入包中。已有 source、load、event 产物保留在默认 Pi 审查包及原执行中。

## 检查与保存范围

- 56 项 task profile/standard/intake 测试通过；Pi `npm run check` 通过。
- `BFWORLD_VERIFY_PROFILE=architecture-v2-lab ./init.sh` 通过；19 项 Lab 检查、7 个预览、原状态保持。
- 真实运行 API 已读取最新版任务 schema，并验证未绑定项目时可评估任务。
- 原十会话、工程与账本，以及原 P01 当前/采用身份保持。保护核对结果为 PASS。
- 新研究 owner 121 请求、默认 owner 新增 33、P08 审查 owner 13；合计 167，费用上界 $1.3682169。
- 器件冷启动尚待改进；MCU 目标构建、实物测试和跨新机制 RSI 不属于已取得结果。

原始本地记录位于 `/Users/depengsu/.local/share/bf-agent-architecture-v2/task-evaluation/`。下载包包含可分享的最终回答和证据；凭据、授权 token、推理正文未打包。
