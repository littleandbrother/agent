# 门动作磁耦合压电节点：D2 数字工程案例

[完整中文报告（36页）](report/door-case.pdf) · [可编辑 TeX](report/door-case.tex)

本目录是 **D2-report-r1 文档修订**：将 Mac 专用中文字体改为 TeX 的 Fandol 字体；设计参数、计算数据和验收结论没有改变。图片和 22 张 CAD 图纸随源码提供。原始 D2 工程快照不覆盖；从仓库的 `door-magnetic-d2-20260930` Release 下载 `door-magnetic-D2-engineering.zip`（包含原始 D2 报告及原生工程）。原包 SHA-256 见 `sealed-D2-package-receipt.json`。

## 编译

在装有 XeLaTeX、ctex、Fandol、pdfpages 的完整 TeX 环境中：

```bash
cd cases/door-magnetic-D2/report
xelatex -no-shell-escape -interaction=nonstopmode -halt-on-error door-case.tex
xelatex -no-shell-escape -interaction=nonstopmode -halt-on-error door-case.tex
```

本机 TeX Live 2026 两轮编译通过，36页（14页正文和22页附图）、无空白页、无编译警告。输出身份及逐页检查见 `report/compile-receipt.json`。复制报告时须保留 `report/figures` 和相邻 `mechanical-D2/drawings` 目录。

Codex 内置 LaTeX 编辑器的 Tectonic 基础资源超时已通过重试缓存，字体错误已修复；当前版本的内置编辑器仅暂存单个源文件，仍不支持这些外部图片和附录，故**内置预览未通过**。不可将图片删除或换成占位符来宣称完整编译。本目录的完整 PDF 是同一源文件在原工程目录中实际编译所得。

## 工程结果

- 单次开门电源冷启动失败（VIN峰值约0.1355 V）；磁力两网格结果差异7.65%，超过5%门槛。
- 原生 COMSOL、Blender、CAD、LTspice、固件编译结果保留；独立 PCB 连通/间距检查通过，但原生立创 ERC/DRC 未完成。
- 图纸仍是数字样机投影图，缺完整加工公差及制造准入。没有实物、烧录、无线接收或功耗/时延实测。
- 操作者辅助工程案例，不构成 Pi 独立设计或 Harness RSI 有效性证据。

复算代码：`battery-world/scripts/door_case/`。完整档案内 `case-files.json` 对原始 D2 归档有效；本文档修订的清单是仓库 `release/source-manifest.json`，二者不混用。
