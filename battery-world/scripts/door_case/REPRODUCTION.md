# D2 工程复算

本包是数字工程基线。冷启动失败、磁力网格未达 5%、原生 EDA 未验收；不是制造发布。

## 最先打开
- report/door-case.pdf：完整报告；door-case.tex 可编辑。
- animation-D2/door-opening.mp4 与 door-installation.blend。
- mechanical-D2/assembly.step、installation.step、22 张 drawings/*.pdf。
- simulation/*/model-with-plots.mph：COMSOL 原生模型。
- pcb/D2/schematic.pdf、pcb-combined.pdf、door-D2.epro2（导入未验收）。
- firmware-D2-release/FLASH.md：目标固件与尚未执行的烧录步骤。

## 文件核验
在包根目录运行 python reproduction/source/scripts/door_case/run.py --root .
该命令只核验哈希，不调用模型或硬件；验收失败不会被完整性通过覆盖。

## 软件与阶段
Python 3.11；CadQuery 2.8；NumPy 2.4.6、SciPy 1.17.1、Matplotlib 3.11.2、CairoSVG 2.9；Blender 5.2.1；COMSOL 6.2.0.339；LTspice 26；Freerouter 2.4.1；嘉立创专业版 3.2.148；ARM GCC；XeLaTeX。
商业软件的许可由使用者提供，不包含求解器安装包。

run.py --help 提供单阶段复算。用 --cad-python 选择 CAD 环境；COMSOL 与固件复算必须另给 --output 防止覆盖本版原生证据。
native_builder.py 可直接在 mechanical-D2 的副本上运行，编辑 input.json 中的 geometry 后得到实体。
COMSOL 输入 Java 位于 reproduction/source/configs/reference_cases/door-magnetic-v1。
COMSOL 原生阶段复算后用 export_fields.py 导出 stress/displacement 或 field。
Blender 用命令行执行 reproduction/source/scripts/door_case/blender_scene.py -- <case根目录>。
ROM 与 SPICE 分别执行 run.py --stage rom / spice；SPICE 脚本的 LTspice 路径需按本机安装位置调整。
报告使用 run.py --stage report，或在 report 目录执行 xelatex door-case.tex 两次。
PCB：door.dsn 是布局输入，door.ses 是真实布线结果；route_export.py pcb/D2 重建独立检查及铜层预览。
固件依赖 ViPSN 固定源提交 5a6b13f85c9ee8dfa40e231bae94218f9b562ac4，下置 EUU/software/beacon_version；Makefile 内 SDK 路径应据本机调整。

## 证据限制
动画使用规定门角，不是求解得到的柔性振动；阻尼为假设；PMIC 目前是单向耦合；PCB Gerber 无阻焊/钢网及原生审查，禁止按量产通过理解。
编译成功不是烧录、无线接收、功耗或时延测量。接收器 fixture 明确为合成协议样例。
本轮由操作者辅助执行，不是 Pi 独立交付或 Harness RSI 绩效数据。
第三方论文、厂商模型和 SDK 保留原有许可。SDK 源与工具链未整体打包，不能宣称离线零依赖。
