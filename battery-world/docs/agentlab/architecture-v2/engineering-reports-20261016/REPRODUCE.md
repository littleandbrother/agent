# P01 报告样稿复现

本目录保存一次只读快照和两份 PDF 样稿。报告对象由 `input/report-input.json` 固定。

## 文件

| 文件 | 用途 |
|---|---|
| output/pdf/P01_简版八页报告_模板样稿.pdf | 八页横版工程汇报 |
| output/pdf/P01_详版技术报告_模板样稿.pdf | 十二章技术报告模板及当前数据样稿 |
| templates.json | 页序、章节与样式 |
| report-facts.json | 从工程数据提取的尺寸、时序和计算结果 |
| asset-inventory.json | 每页已有材料与 Pi 补齐任务 |
| 来源索引.csv | 108 份来源的候选、作业与 SHA-256 |
| skill-draft/bf-engineering-report/ | 待审定的共用 Skill 草稿 |
| verification/ | 数据、PDF 与保护状态核对结果 |

## 离线重建

依赖：Python 3.12、ReportLab、Pillow、pypdf；Node、Playwright、Google Chrome；Poppler。当前 macOS 使用内嵌 STHeiti 中文字体。

在本目录执行；代码默认使用 Codex 已安装的 Python / Node 运行库。

```sh
rtk proxy /Users/depengsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 render.py
rtk proxy pdftoppm -png -scale-to 1400 output/pdf/P01_简版八页报告_模板样稿.pdf tmp/pdfs/simple/final
rtk proxy pdftoppm -png -scale-to 1400 output/pdf/P01_详版技术报告_模板样稿.pdf tmp/pdfs/detail/final
rtk proxy /Users/depengsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 verify.py
```

`render.py` 核对全部来源，使用现有 RAW 绘图，通过 Chromium 原生 SVG 渲染器转换原理图和 PCB。完整 SVG 随输入保留。文字、表格、流程和曲线由 PDF 绘制命令生成。

`verify.py` 最后一项读取本机原运行目录的数据库和原生工程，对比收集前的保护摘要。离线异机可运行渲染；这项保护核对需要原运行目录。

## 新快照

只在需要制作另一个候选的报告时收集，输出目录必须新建：

```sh
rtk proxy /Users/depengsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 collect.py --candidate submitted --output /new/absolute/report-input
```

收集器使用现有只读 HTTP 文件入口；SQLite 使用 `mode=ro`。凭据只从本机读取，输出不含凭据。现阶段收集器针对 P01 项目，跨项目参数化与 Pi 工具注册安排在模板审定后的实现步骤。

## 本版范围

本版由 Codex 制作模板和数据样稿。Pi 的补图、工程分析与逐页结论列在缺项清单；原会话尚未派发。所有工程检查状态沿用所选候选的当前资格。


## 已实施：共享 Skill 与原 Pi 生成

最终交付见 `IMPLEMENTATION.md`。第一阶段 `render.py` 样稿保留；正式报告由 `design_lab/report_render.py` 渲染。

实际消费顺序：

1. 原 Lead `report_prepare(system_id)`，固定当前候选、资格与108项资产。
2. 原 Power/Firmware/Lead 加载 `bf-engineering-report`，用 `report_schema`/`report_read` 查看本专业数据，并通过 `report_write` 提交有来源的正文和图表数据。
3. Lead `report_build(report_id)`，校验输入和作者，生成简版8页、详版29页、图表与23项检查。
4. Lead `release(system_id, report_id)`，重新验证当前身份及摘要后封存同版包。当前相同输入的构建直接复用。

本轮完整回归（使用已有固定 CAD Python 环境和 bf_v2_environment.environment 的环境变量）：

```sh
rtk proxy /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python - <<'PY'
import os, subprocess, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from bf_v2_environment import environment
_, settings = environment(Path.home()/'.local/share/bf-agent-architecture-v2')
test_env = dict(os.environ)
test_env.update(settings)
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s',
                'tests/agentlab', '-p', '*repository*.py'], env=test_env, check=True)
PY
rtk proxy env BFWORLD_VERIFY_PROFILE=architecture-v2-lab BF_V2_EVIDENCE=/new/absolute/evidence ./init.sh
```

在 `battery-world` 目录执行；完整运行输出保存于 `implementation/repository-tests-final-003.log`。脚本 `implementation/finalize.py` 只读核对保护状态、原账本和封存 ZIP，再复制最终交付到 Downloads。原工程与原生成功作业直接复用。
