# 参考论文版式与官方英文矢量校徽：完成回执

完成时间：2026-10-19T15:41:01.756298+00:00。用户最后提供的英文横版示例取代此前中英组合要求：左侧校徽、右侧三行英文。两篇论文共用一套轻量样式，仅修改导言区、标题换行和排版；摘要至文末源码逐字节不变，另11个来源/数据/历史导出文件哈希不变。

## 样式与图标

- 参照用户提供的 `/Users/depengsu/Downloads/2608.31100v1.pdf`，其 LaTeX 源为 https://arxiv.org/src/2608.31100 。原PDF保持不动。
- US Letter，左右/底边距2.5 cm、上边距2.75 cm；17/20 pt标题，12 pt摘要标题，10/12 pt摘要正文；蓝色 `#2E5AA8`、0.5 pt细线与2.5 mm圆角摘要框，横向8 mm、纵向6 mm内边距。左上角空白，右上角只显示指定学校标识。
- 两篇摘要标题基线距页顶260.881 pt；参考260.907 pt，差0.026 pt。标题保留原文字，统一两行与居中布局。正文、表格数值、实验和费用结论未改动。
- 章节/标题采用TeX发行版自带TeX Gyre Adventor，无衬线字体形状与原文Byte Sans略有区别；未分发原文包内的专有字体，也未引入额外运行环境。
- 同款官方英文组合Logo来自[学校品牌手册](https://brand.hkust.edu.hk/sites/default/files/bm_folder/HKUST_Brand_guideline.pdf)，物理第69页、印刷第66页。按原有形状、字距、颜色提取矢量路径；PDF中栅格图像数0、依赖字体数0。另提供同源SVG。提取范围/源文件SHA/转换细节保存在论文共享目录 `layout-provenance.json`。
- 两篇本地共享 `/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-s0-20261019/battery-world/papers/shared/hkustgz-paper.sty` 及 `assets/`；各Overleaf项目携带相同的编译依赖，避免本地复制整套模板与环境。

## 验证与最终文件

| 稿件 | 页数 | 最终本地PDF | Overleaf提交 |
|---|---:|---|---|
| RSI / 方法重执行 | 3 | `/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-s0-20261019/battery-world/papers/method-reexecution-20261019/build/main.pdf` | `598424af92ca50e7c0fcdab89e92e6f0bf7be22d` |
| Agent接口充分性 | 3 | `/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-campaign-s0-20261019/battery-world/papers/interface-sufficiency-20261019/build/manuscript.pdf` | `9df4a9ff4ed73be039b49a6369ae16012bfd6530` |

两篇均pdflatex两遍通过，无警告/Overfull/Underfull/Missing character；共6页逐页查看。替换矢量资产后两篇首页重看，其余4页像素不变。最终PDF严格解析通过。缺少校徽资产时编译确实失败，无占位标识。源码正文SHA、表格输入/数据、额外11份原文件回读通过。Overleaf兼容入口 `example_paper.tex` 和 `main.tex` 均绑定同一稿件；用该入口本地两遍编译，与本地稿件抽取文本相同。

已分别推送且从远端fetch后按依赖文件SHA回读，远端HEAD一致、两个checkout干净。未执行云端网页编译；本地构建成功与实际远端源上传已分别验证。根仓库与S0源码仓库未提交，S0 HEAD仍为317d40f。研究模型请求/原生仿真新增均为0。

- RSI：https://www.overleaf.com/project/6ad5fb6e87c3ac6782d05b2c
- Agent接口：https://www.overleaf.com/project/6ad5fbda856b284d5d917ffd
- 原有较早RSI `papers/method-reexecution-20261019/main.pdf` 保留为历史导出，未用它证明本次构建；上表的 `build/main.pdf` 才是本次最终稿。

复现：在根目录运行 `rtk proxy python3 -B docs/manuscript-layout-20261019/build_review.py --render`；随后 `rtk proxy python3 -B docs/manuscript-layout-20261019/build_review.py --overleaf`。TeX中间文件在临时目录内生成后自动删除。仅保留每篇最终PDF、一张首页预览、一个Logo预览及小型回执。

## 生成物review与空间口径

本轮清掉56份下载候选、完整品牌手册临时副本、参考源临时文件与可重建TeX/页图，共20,461,276逻辑字节、20,590,592分配字节；当次可用空间差值仅65,536字节，不以文件大小冒称物理释放。清理目录剩余约1.057 MB（报告写入前）。未生成整树备份。

前一清理批BFA-049的冻结测量窗口：11,408,089,088 → 11,825,012,736可用字节，净增416,923,648字节（0.417 GB）。各操作即时差值合计1.420 GB，与整批最终净值不同。工作区、环境和独有内容保留/恢复/计费验证见 `../storage-slimming-20261019/batch-2/REPORT.md`。

后续排版期间磁盘仍有其他占用/回收变化，因此另外在 `final-space.json` 保存整轮结束读数及与BFA-049开始的净差；该差值也不能全归因于本任务。原始实验、独有改动、历史费用及11条UNKNOWN均保留，无补跑/重计费。

最终实测（2026-10-19T15:41:34.696807+00:00）：可用10,931,200,000字节（10.931 GB）。对比本轮BFA049开始，净变化-476,889,088字节（-0.477 GB）；对比清理完成时，后续区间变化-893,812,736字节。全轮结束未实现可用空间净增加，不能用0.417GB清理窗口或1.420GB操作合计代替此读数。该期间并非独占磁盘，变化的具体写入来源未逐一归因。版式回执加共享样式/矢量资源分配量1,142,784字节，仍超过10GB保留线。
