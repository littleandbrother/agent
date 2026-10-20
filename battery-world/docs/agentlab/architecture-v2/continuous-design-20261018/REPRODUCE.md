# 复核已有结果

工作目录为 `workbench/bf-architecture-v2/battery-world`，数据位于 `~/.local/share/bf-agent-architecture-v2`。以下命令读取已有数据库、轨迹和工件，新增模型请求及原生求解为0。

```sh
python3 scripts/verify_continuous_design.py --stage all
python3 docs/agentlab/architecture-v2/continuous-design-20261018/analyze_saved.py
python3 docs/agentlab/architecture-v2/continuous-design-20261018/build_delivery_index.py
python3 docs/agentlab/architecture-v2/continuous-design-20261018/export_public_finals.py
python3 scripts/continuous_design_ops.py preservation
```

PDF渲染使用已配置报告解释器：

```sh
/Users/depengsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  docs/agentlab/architecture-v2/continuous-design-20261018/build_report.py
```

Repository回归采用独立V2配置，避免读取生产数据：

```sh
python3 -c 'import os,sys; sys.path.insert(0,"scripts"); from bf_v2_environment import environment; from v2_common import RUNTIME; _,env=environment(RUNTIME); env["BFWORLD_VERIFY_PROFILE"]="architecture-v2-ci"; os.execve("./init.sh",["./init.sh"],env)'
```

## 文件索引

| 文件 | 内容 |
|---|---|
| `results/summary.json`、`trials.csv` | 逐项结果、父子费用、工具错误、执行及交付统计 |
| `results/public-final-answers.json` | 主会话最终文本，排除思考块和工具载荷 |
| `results/delivery-index.json`、`DELIVERIES.md` | 每个候选的PDF、ZIP、身份及摘要 |
| `results/frozen-harness.json` | 实际运行的48份源码／构建入口摘要 |
| `results/native-input-audit.json` | 121次原生调用与121个唯一输入核对 |
| `results/last-trial-settlement.json` | 已在途失败执行的迟到回执与12次调用对账 |
| `results/report-binding-negative-controls.json` | 真实报告／工程包绑定及8项篡改反例 |
| `results/regression.json` | V2回归、项目状态与根目录检查记录 |
| `results/t2-conflict-proof.json` | 8 ms任务与冻结检查器的约束冲突 |
| `results/t2-public-contract-audit.json` | 公开任务遗漏有效期计时起点的证据 |
| 运行目录 `verification-all.json` | 完整源树、编译输入、执行、同版包、PDF、模型与账本核对 |
| 运行目录 `reconciliation/` | 磁盘中断的原生回执及失败执行对账 |
| 运行目录 `pilot/trials/*/recovery-*.json` | 两次零模型调用启动失败的原身份恢复 |

清单结束后，重现分析使用上述读取命令。原 `dispatch.json`、`final.json`、失败轨迹和费用记录保留。
