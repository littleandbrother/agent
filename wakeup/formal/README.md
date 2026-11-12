# 四项正式实验：最小物理校准

这里构造并校验四组正式实验的题目，暂不运行 Agent。每道题的物理输入、可调范围、通过见证和反事实结果都直接保存为 JSON。验收总表在 `outputs/CALIBRATION.md`。

两个入口：

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python3 -B wakeup/formal/calibrate.py --experiment e1
PYTHONDONTWRITEBYTECODE=1 python3 -B wakeup/formal/report.py --help
```

`--experiment` 选择 `e1/e2/e3/e4/all`。默认只本地物理计算，没有供应商调用、哈希门禁、数据库、模型代理或自动实验恢复。

安装与报告重生成：

```sh
python3 -m pip install -r wakeup/formal/requirements.txt
python3 -B wakeup/formal/report.py wakeup/formal/outputs/report/input.json
```

报告只用Python依赖：NumPy、SciPy、Matplotlib、ReportLab、CadQuery和svglib；CAD的SVG直接嵌入PDF，无需Node或Sharp。CadQuery默认使用当前Python，拆分环境时可设`CAD_PYTHON`。中文字体默认使用macOS的Arial Unicode；其他系统用`REPORT_FONT=/path/to/CJK.ttf`指定中文TrueType字体。

## 文件怎么读

| 文件 | 唯一职责 |
|---|---|
| `../sim.py` | 两根压电梁、整流、储能、包络、分流、固件和真实分类的30秒完整瞬态 |
| `../design.json` | 基础唤醒设计 |
| `common.py` | 调用同一内核并提取紧凑事实；谐波公式只供筛选 |
| `feedback.py` | E1偏差任务与F0–F3反馈投影 |
| `active.py` | E2电容/质量的同初态反馈、反方向见证任务 |
| `structure.py` | E3开路最优与受载整机反事实；结构资格明确分开 |
| `stopping.py` | E4指定域内的启动能量排除界 |
| `report.py` | 同一物理结果→CAD STEP、图纸、波形、能量表、15页工程PDF |
| `explain.py` | 生成含实际任务数据的单文件可视化说明 |
| `calibrate.py` | 选择上述四项本地校准，不另建运行框架 |

打开 `outputs/Architecture.html` 可逐项看物理方程、依赖关系、每题完整设置与当前证据。`outputs/CALIBRATION.md` 是本轮结果索引。

## 本轮物理改动

原代码只在转换器支路计入可选模块额外寄生功耗：A/B/C/D分别为0.5/180/2/0.5µW；直接整流支路漏计。本版两支路统一计入。主动包络只计正向充电耗能，不把包络放电当作回充来源。

`simulate(..., rtol=..., max_step=...)` 公开两个数值分辨率参数，默认值与旧版相同，用于有针对性的独立复算。没有添加新门控或另一套物理模型。

## 怎样判断一道题校验完了

- E1：初态0/4、同域完整4/4见证、四档反馈严格嵌套。
- E2：成对初始公开反馈完全相同；规定单轴域内通过区间分开；本方向见证通过、交换见证失败。
- E3：局部控制确实不用加模块就通过；结构题完成关模块全域反例搜索与开模块见证；代理题开路峰失败、受载点通过。
- E4：当前窄窗、当前分支排除但另一分支通过、全分支排除且实际3/4历史三类条件逐题成立。

这些条件通过就写“题目校验通过”。L/A/Pi的胜率、主动诊断比例和无解判断准确率由后续实验测量。本轮没有生成这些模型成绩。

数值搜索与解析界按各题实际使用的方法标明；题目的可调域也明写，避免把单轴题说成全变量题。工程报告直接读取本地校准轨迹，未来可换入正式Agent轨迹，不编造不存在的推理过程。

## 为什么删除旧代码

当前四项校准和报告只依赖上述单一内核。新分支删除了3,446个不在该调用路径中的旧Python/JS/TS/Shell源文件，包括旧批次包装、缓存/哈希/恢复与历史平台代码；旧结果文件没有因此删除。

准确恢复旧代码：父提交 `5c9569ba14fbba378210842f0453e1d69dd3b4f4`。旧统一分支和原工作目录未改。本次以独立分支 `codex/formal-calibration-20261112` 发布，历史统一分支保持原样。

完整删除清单与理由在 `outputs/cleanup.json`。这是一项依赖范围清理，不冒称已经逐行证明全部旧代码“没有研究价值”。
