# 门磁案例：逐子图证据与 Agent 学术制图入口

日期：2026-10-05。工作对象仍是磁耦合压电门磁，不是 TENG。参考论文用于研究表达形式，论文照片、数据和成功结论均未作为本产品的结果。本轮新增外部模型调用为 0；原生计算与操作者整理不能称为 Pi 自主复现。

## 可直接使用的成果

Studio → **磁耦合全流程bf aiot设计** → 产品 → **六组学术证据 / E2.1**。对话右侧工程工作区的概览使用相同图组和来源。左侧项目、Studio/Lab 分工保持原有结构。

- 本地工程：`/Users/depengsu/Documents/bf-agent-workbench/reference-cases/door-evidence-v2/`
- 完整 PDF：上述目录的 `report/door-evidence-report.pdf`，90 页，包含六组说明、组图、70 个独立子图。
- 离线逐图阅读：`report/figure-atlas.html`；图像、CSV/JSON、绘图计划、便携绘图脚本与来源记录在 `report/scientific-figures.zip`。
- 完整工程交付：在交付页选择 E2.1 和“工程资料包”；原生 CAD、Blender、COMSOL、LTspice、PCB、目标固件与本轮数据按原相对路径归档。
- 验证收据：`/Users/depengsu/Documents/bf-agent-workbench/verification/scientific-figures-20261005/`。

E1 和 E2 的封存输入、旧实验和失败记录保留。E2.1 是交付完整性修订：图、模型、计算、PDF 与 E2 相同，补齐原始绘图输入和计划的相对路径。早期 E2 包可以读图，但不包含完整原始绘图目录，不能声称已通过整目录离线校验。独立验收以 E2.1 为准。

来源身份：`b832ddbc8741199fca7df23d8f0ebe83d01de4d9e9768fb3902697613f3aff26`。

PDF SHA-256：`21622228ab37757742fb02fd902c617361409abee3abdb74e7d23e3a674221d9`。

## 六组图的研究逻辑

| 图组 | 数量 | 核心问题与新增表达 |
| --- | ---: | --- |
| 1 产品、安装与功能装配 | 12 | 真实 CAD 来源的安装、局部、剖切、爆炸、夹持、PZT、尺寸和功能链；单独标出 D2 与 D3.3 的组件修订差异。 |
| 2 加载、释放与机电转换 | 12 | 同一相机四个动作状态，与门角、梁位移/速度、电压、磁力域、平衡路径、完整规定加载循环及原生场锚点对应。 |
| 3 受控修改与设计比较 | 12 | 极性、动作时间、负载和电容控制；比较机械功、端口能、储能和实际任务结果，保留结构修改尚未成功的缺口。 |
| 4 电路、PCB 与供电 | 12 | 实际原理图、顶/底铜线、元件/BOM、原生电源计算、启动阈值、瞬态和规则/制造边界。 |
| 5 程序、能耗与事件服务 | 12 | C 状态机、共同时间轴、PGOOD、零 TX/RX、诊断阳性对照、阶段负载、目标构建和未验证的事件语义。 |
| 6 数值可信度、范围与交付 | 10 | 能量残差、势能导数互核、循环反力功、原生静力云图、未过门槛的磁场网格、工作域、缺项与可审查交付链。 |

70 个预声明子图中 **66 个有可追溯来源、4 个缺证**。这是图组供应情况，不是设备成功率或论文自主复现率。缺项为 3l 新释放结构的自供能正例、4l 原生 EDA/RF/制造确认、5l 重启与重复报文的正确事件语义、6j 实物/环境/寿命确认；不能用示意图或假误差条填成已完成。

## 原生与控制计算

- 新执行 12 个 SciPy 互易机电电阻控制：两种驱动磁方向、0.25/2 s 动作和 0.1/1/10 MΩ。它们是环境/负载诊断，不是擅自修改正式 Agent 任务；不包含 PMIC 或应用成功判据。
- 四次新 LTspice + C 软件在环计算：输入电容 22/47/100/220 µF，驱动磁方向翻转、动作 2 s、输出电容 100 µF、初始电储能为 0、无外加诊断电流，使用独立冷运行目录。
- 四档输入储能峰值依次为 0.79734856、0.434468925、0.22175078、0.10531295 V。**均无冷启动、完整 TX 或接收事件**。更小电容的电压升高不能单独解释为更多可用能量或产品成功。
- 规定闭门/保持/开门的反力功采用同一名义磁势能模型，8001 采样点循环账相对残差约 0.379%。它检查规定轨迹的同模型一致性，不认证真实机构或磁场充分性。
- 原生固定姿态磁场网格差约 11.29%，仍高于 5% 门槛；旋转全过程独立 FEM 覆盖仍不充分。COMSOL 静态场和梁图使用明确保存的原生结果，未声称本轮重跑 COMSOL。
- 既有 1 mA 外加电流诊断的 36 TX / 1 RX 单独标为诊断，不能算自供能成功。

12 个电阻控制回执保留了参考审查函数的通用 `scope` 描述，其中电阻文字仍写 1 MΩ；具体试验电阻以回执的 `resistance_ohm`、候选字段和曲线图例为准。未改写已封存回执以掩盖该元数据局限。

## 文献表达档案

六篇主要来源的 30 张主图，共 250 个一级字母子图，已建立本地索引、原主图、图注、分组联系图和归属记录。数量不是“所有子刊所有子图”，也不包含补充信息和全部嵌套 inset。人工矩形边界已检查，少数裁块可能包含相邻标签或局部截轴，精确阅读须回到完整主图及原图注。

| 来源 DOI | 一级子图数 |
| --- | ---: |
| 10.1038/s41467-024-51245-5 | 55 |
| 10.1038/s41467-024-50581-w | 40 |
| 10.1038/s41467-025-56679-z | 37 |
| 10.1038/s41467-025-61166-6 | 30 |
| 10.1038/s41467-025-64575-9 | 38 |
| 10.1126/sciadv.adv9379 | 50 |

路径为 `reference-cases/literature-figure-atlas-v1/atlas-index.json` 和 `index.html`。这个归属明确的本地参考档案独立于产品交付，不自动把出版商图像纳入产品或 Git 发布。

## 学术制图约束

新绘曲线和文字输出 PDF/SVG 矢量版本及 PNG 预览。组图宽 180 mm，新文字最小 8.5 pt；独立图使用更大字体。明确 SI 单位及单位换算；同条件比较、共用时序、有限值检查、零结果标记、来源身份和缺证理由一并保留。使用 Okabe–Ito 与 viridis，线型、标记、填充纹理提供第二种区分方式，不为单次确定性仿真生成虚构误差条。

CAD/Blender 显示真实来源尺寸与功能部件，并标注比例尺。剖切与爆炸只为表达；动作中的梁形状是一阶模态投影，不是三维瞬态 FEM 云图。D2 的空白 PCB 几何不会被描述为已装配 D3.3 电路。

本交付是可审查研究图谱，组图较高，包含紧凑表格摘录及完整独立表；不是已按某一本期刊版面压缩完成的投稿文件。原生图片中的已有小字不属于新文字最小字号保证，应查看独立原图。PDF 经页面渲染与中文文本检查；Matplotlib 的 Hiragino CFF/TTC 嵌入在 Poppler 中保留 `Mismatch between font type and embedded font file` 警告，不能声称所有 PDF 阅读器兼容性已认证。需要严格投稿预检时，应以新的图谱版本切换经验证的 TTF 字体并重新封存，而不能改写当前版本。

## Agent 能力与后端

Pi `bf_engineering` 增加 `scientific-figures` 引擎和中文使用说明。Agent 可先声明问题—子图—来源—结论—边界，随后提交相对路径的 CSV/JSON/图像及哈希。引擎只运行受信绘图器，不执行参与者代码、网络或任意 shell。

1–6 组、最多 80 个子图、80 个来源文件/64 MB；单位、矩形热图、有限值、所有子图来源和路径/符号链接检查失败即拒绝。输入快照在运行前固定，逐图 provenance 和发布字段独立校验。public/Trace 回复不重复塞入原始二进制，下载源码仍受 owner 与哈希约束。运行成功只证明绘图及来源检查，产品/实物/自主复现标志仍为 false。

实际服务执行 `eng-a3b6814c912acafe`（operator）成功渲染全部 70 个子图，公开回复未包含二进制快照。这是操作者离线重放，不是付费 Pi 自主试验。另有实际 Pi + 假提供者测试检验工具/Trace 接线，仍不计算为真实模型成绩。

修复部署 Pi 的 NodeNext `.ts` 导入路径兼容问题，改用 `.js` 源码导入约定；部署与集成 bf-agent 编译通过。导出单件文件现在只验证指定注册文件，避免为每张图或每个 ZIP 项重复扫描整个历史目录；owner/哈希/路径拦截仍保留。

## 验证与复算

最终完整应用 `./init.sh`：**515 项 Python、SDK/Studio 类型和构建、2803 样本投影通过**。另有 27 项交付/完整性定向检查通过。实际浏览器下载的 E2.1 工程包有 949 个来源路径，解压后 948 个封存文件哈希全部一致；故意篡改来源被拒绝。

使用下载包中的绘图计划和固定脚本，在独立目录重绘全部 70 个子图：228 个 PDF/SVG/PNG 与交付逐字节一致，70 份 provenance 的非身份字段、原始来源哈希和依赖关系一致。身份值包含来源路径和 `archive_file`，便携计划重定位后身份值会改变；原始逐字节比较和独立字段检查分别保留，没有把这 70 份元数据说成字节相同。

详见验收目录的 `acceptance.json`、`export-verification.json`、`redraw-verification.json` 和 `browser-qa.json`。初始 Pi 编译失败、命令缺 PYTHONPATH 以及初次元数据字节差异的记录也保留。未跳过科学判定或关闭沙箱。

```sh
rtk proxy env BF_CAD_PYTHON=/Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python \
  BF_PI_ROOT=/Users/depengsu/.local/share/bf-agent-runtime/pi-bf-aiot \
  pnpm_config_verify_deps_before_run=false ./init.sh

rtk proxy python3 scripts/figures/verify_scientific_atlas.py \
  /Users/depengsu/Documents/bf-agent-workbench/reference-cases/door-evidence-v2

rtk proxy /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python \
  /Users/depengsu/Documents/bf-agent-workbench/reference-cases/door-evidence-v2/report/scientific_renderer.py \
  /Users/depengsu/Documents/bf-agent-workbench/reference-cases/door-evidence-v2/report/reproduce-plan.json \
  /tmp/door-figures-new-output
```

最后一条只重新绘图；新输出目录不得覆盖封存 E1/E2。原生再计算需要相应 COMSOL/LTspice/编译器与固定模型；图谱再生成不能替代工具校准。

## 后续科学目标

本轮打通“逐图来源 → 学术绘图 → 产品/右侧阅读 → 报告/工程交付”，没有宣称完全可工作的门磁或 80% 自主论文复现。后续首先补能量传递与旋转磁场工作域，再选择真实可实现的释放结构，取得合法自供能正例、目标事件语义和原生 EDA 验收。具备这些对照后，再以任务级完整清单评估真实 Pi 的自主复现率和跨域修订能力。BFA-035 整体研究 feature 仍 in-progress；本轮未提交或推送 GitHub。
