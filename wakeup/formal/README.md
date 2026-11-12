# 四项正式实验：最小物理校准

当前实现：真实Pi入口、一个实验工具宿主、一个完整瞬态内核、四个任务模块、两个文档出口。164个物理题目已经校验通过；新Agent正式对比尚未运行。

- [源码架构单与本轮精简清单](../../ARCHITECTURE.md)
- [可视化物理与任务索引](outputs/Architecture.html)
- [题目校准结果](outputs/CALIBRATION.md)
- [四实验设置](experiment_plan.json)
- [15页工程设计报告](outputs/report/Engineering_Design_Report.pdf)

## 运行

在仓库根目录执行：

```sh
python3 -m pip install -r wakeup/formal/requirements.txt

# 查看已有说明，不做新物理求解
python3 -B wakeup/formal/explain.py

# 确实需要重新校准时再运行；选择 e1/e2/e3/e4/all
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python3 -B wakeup/formal/calibrate.py --experiment e1 --workers 4

# 输入已有设计与轨迹，生成工程报告
python3 -B wakeup/formal/report.py wakeup/formal/outputs/report/input.json
```

所有依赖在同一Python环境运行；报告直接复用CadQuery的STEP同源SVG，无自调用子进程。中文字体默认用macOS Arial Unicode，其他系统设置 `REPORT_FONT=/path/to/CJK.ttf`。

`*_public_tasks.json`供未来被测模型读取；完整校准JSON含隐藏偏差与通过见证，供人检查题目。二者用途不同。已有波形、数值反例与原失败记录保留，详细文件职责见架构单。

活动分支：`codex/formal-calibration-20261112`。旧平台源码已在上一轮从本分支移除；历史统一版本仍在[固定提交](https://github.com/littleandbrother/agent/tree/5c9569ba14fbba378210842f0453e1d69dd3b4f4)。

## 真实Pi

```sh
npm install --prefix wakeup/formal
node wakeup/formal/pi.mjs --list
node wakeup/formal/pi.mjs --task E1-01 --condition F0 --check --out /tmp/pi-check
node wakeup/formal/pi.mjs --task E1-01 --condition F3 --provider PROVIDER --model MODEL --max-cost 1 --out runs/e1
```

使用Pi原生认证与模型配置。已有SDK设 `PI_SDK=/path/to/index.js` 即可复用，无需重复安装；Python解释器可设 `PYTHON`。默认6次设计评价、12次模型回复、900秒，每次Bash最多30秒。费用上限按SDK估算在回复之间检查。

任务条件：E1 `F0/F1/F2/F3`，E2 `Blind/Active/Oracle`（`--half 0/1`），E3 `baseline/diagnostic`，E4 `L0/L1/L2`。工具返回对应事实；`finish`把模型判断与实际验证结果分别保存。数据/原生文件工具的本机隔离范围、共同模块默认值和输出说明见架构单。

`--check`不请求模型；本次接入检查见 [pi_check.json](outputs/pi_check.json)，已有设计检查不属于Agent解题成绩。
