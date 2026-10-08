# 门磁案例 E1：六组图与统一证据交付

日期：2026-10-05。完成范围是既有磁耦合压电门磁案例的证据整理、六图叙事、产品与对话右侧入口、报告及工程包。本轮没有改做 TENG，没有追加模型调用或原生求解，没有证明整机成功或论文自主复现率。

## 用户入口与交付

本机 `http://127.0.0.1:8768/` → **磁耦合全流程bf aiot设计** → 产品 → **E1**。同一内容也在对话右侧工程面板的概览中展示。左项目栏和 Studio/Lab 分工保持原有结构。旧 D2 / D3.3 版本仍可选择。

- 案例目录：`/Users/depengsu/Documents/bf-agent-workbench/reference-cases/door-evidence-v1`
- PDF：上述目录下 `report/door-evidence-report.pdf`，8 页，中文字体嵌入。
- 离线 HTML：`report/door-evidence-report.html`，与图像和数据一起随报告包交付。
- 完整证据工程包：`/Users/depengsu/Documents/bf-agent-workbench/deliveries/门磁案例-E1-完整证据工程包.zip`
- 图文报告包：`/Users/depengsu/Documents/bf-agent-workbench/deliveries/门磁案例-E1-图文报告包.zip`
- 验收目录：`/Users/depengsu/Documents/bf-agent-workbench/verification/door-evidence-20261005`

E1 已发布且不可覆盖。后续输入、图或报告修改应创建新版本。统一来源身份：

`665ac7e930b9d31dcc1dedf13ceb02fadc112808371bee84911e47ae3f5c0f77`

## 六组图的逻辑

| 图组 | 回答的问题 | 实际内容与边界 |
| --- | --- | --- |
| 1 产品 | 这是什么、安装在哪里？ | 已有安装渲染、内部结构、门/外壳/PCB/梁/磁体尺寸和功能链。尺寸来自 D2 设计，不是实测装配。 |
| 2 动作 | 一次开门怎样产生能量？ | 与求解条件一致的门角序列，实际保存的梁位移、压电端与储能波形；规定门运动不等于完整加载机构已验证。 |
| 3 比较 | 修改了什么、结果如何？ | 基线与驱动磁体翻转 180° 的实际计算结果，同门运动、电容配置对比；初始机械平衡能不同，不能称等输入能量试验。 |
| 4 能量 | 能量从哪里来、去了哪里？ | 初始机械能、带正负号的磁力功、阻尼、PMIC 端口、末态与残差。未知 PMIC 内部损耗不填造数字。 |
| 5 时序 | 电路与程序是否共同完成任务？ | 同一次运行的储能、供电、PGOOD、C 状态、完整 TX、RX 共用时间轴。真实结果是 RESET 与零发送/接收。 |
| 6 交付 | 已有什么、还缺什么？ | 实际原理图和 PCB 图，模型/电路/固件/BOM/报告入口及各组件版本；原生 ERC/DRC、装配与实物验收仍未通过。 |

每组都有问题、结论、局限、来源文件和 SHA-256。页面默认先呈现图与结论，来源折叠展开；原图可放大，PDF 与交付直接可达。短标签为产品、动作、比较、能量、时序、交付，保留完整无障碍名称。

## 来源与实质结论

机械和动画来自 D2；电子工程来自 D3.3-electronics；固件来自 D2-final；联合波形使用机械释放审查中的 frozen-baseline 和 orientation-v3。E1 是明确列出这些组件版本的证据组合，**不把它们视为已经重新集成并验证的同一个制造版本**。

基线储能峰值 0.14575150609 V、程序供电峰值约 1.0638 µV，零 TX/RX；翻转候选储能峰值 0.434468925 V、供电约 3.1111 µV，仍零 TX/RX。基线初始机械能约 758.64 µJ，磁力净功 −662.89 µJ，阻尼约 91.75 µJ，PMIC 端口约 3.99 µJ；翻转候选相应为 434.31、+178.85、596.92、16.25 µJ。

这些数值描述保存的模型计算，不能替代全加载路径、旋转磁场 FEM 有效性、实物校准或自供能成功。D3.3 BOM 为 14 装配件、11 个立创料号；库存依据 2026-10-03 快照，非实时库存承诺。固件有源码和构建产物，但未烧录验收，也不把编译结果等同目标器件的能耗测量。

## 实现与防混淆

- 新增 `product-evidence.js/css`，产品页和对话右侧共用组件。可选 `evidence_story` 后端字段要求六组顺序完整、来源身份一致、图片已注册且属于当前 owner；不具备证据故事的旧案例保留既有页面。
- `build_evidence_dossier.py` 从显式来源捕获不可变副本，生成 6 PNG、6 SVG、数据清单、HTML、PDF 和来源封存。图文不依赖 LLM 编写数值。
- 时间终点、程序状态、TX/RX 数量会与来源交叉检查；独立负例分别得到 `TIMELINE_MISMATCH`、`EVENT_COUNT_MISMATCH`、`PROGRAM_STATE_MISMATCH`。
- `verify_evidence_dossier.py` 检查所有封存文件、六组顺序、各组来源哈希和声明边界。应用测试还覆盖 owner 隔离、缺图、源文件变化、混合身份、缺失/损坏等情况。
- 本轮只整理并重绘已有原生结果；没有把图表重建称作 COMSOL/LTspice 冷缓存复算。完整原生 RAW、大型软件安装和第三方依赖不全部打包，求解再运行仍需要对应工具及环境。

## 验收记录

| 验收 | 结果 |
| --- | --- |
| 应用完整 `init.sh` | 退出 0；501 项 Python 测试通过，SDK/Studio 类型、构建通过 |
| Studio 投影 | 2,803 样本，15 通道绑定与 11 视觉绑定通过 |
| JavaScript 定向测试 | 12 项通过 |
| 独立目录图文重建 | 6 PNG + 6 SVG + baseline/HTML/PDF，15 项逐字节一致 |
| 六组图浏览器验收 | 产品 6 组、右面板 6 组均加载真实图像；原图放大通过 |
| 交互/窄屏 | Enter 操作及焦点保持通过；390 px 无横向溢出；控制台无错误 |
| 最终 PDF | 8 页全部渲染与检查，中文字体嵌入，文本可提取 |
| 实际 UI 工程包下载 | 324 来源文件 SHA/CRC 校验通过；解包后的 323 封存文件离线校验通过 |
| 实际 UI 报告包下载 | 27 文件校验通过，HTML 相对引用完整 |

工程 ZIP SHA-256：`3e8ac8387591808be210148eb16207af1200c9b28923d0517ea537f6d517fa60`。报告 ZIP SHA-256：`daecea7f86c3874c0d7f81c7294c66a649379e060a50922b869454708b488a45`。

总收据为验收目录的 `acceptance.json`；分项记录为 `reproduction.json`、`negative-controls.json`、`browser-qa.json`、`export-verification.json`、`report-package.json`、`pdf-qa.json`。完整日志保存为 `application-init.log` 和 `javascript-tests.log`，页面截图为 `studio-desktop.png`、`studio-mobile.png`、`studio-figure5.png`。

早期尝试的旧 CSV 混合类型测试预期与保留原字符串的采购数据读取不一致，已修正测试预期；未改生产读取行为。之后 501 项通过。pnpm 非 TTY 自动刷新依赖的失败也已保留，通过指定已安装依赖运行完整 gate；未跳过任何 init 检查阶段。

## 可重复命令

在本应用仓库执行（前缀遵循本机 RTK 规则）：

```sh
rtk proxy env BF_PI_ROOT=/Users/depengsu/.local/share/bf-agent-runtime/pi-bf-aiot pnpm_config_verify_deps_before_run=false ./init.sh

rtk proxy python3 scripts/door_case/verify_evidence_dossier.py /Users/depengsu/Documents/bf-agent-workbench/reference-cases/door-evidence-v1

rtk proxy env PYTHONPATH=packages/python/bfworld/src .venv/bin/python scripts/door_case/build_evidence_dossier.py \
  --inputs /Users/depengsu/Documents/bf-agent-workbench/reference-cases/door-evidence-v1/inputs \
  --output /tmp/door-evidence-independent-rebuild \
  --report-python /Users/depengsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
```

重建请使用新输出目录，不覆盖 E1。交付包中的 `reproduce/README.md` 说明运行依赖、字体和重建方式。

## 下一步与停止边界

本次证据交付子任务完成；BFA-035 研究任务仍在进行。优先补完整加载功及旋转磁场/模型工作域，再改善一次门动作的冷启动及任务服务；将 D3.3 原生 EDA/ERC/DRC、装配和固件验收与同一版本对齐。之后才能用预先声明的复现清单评估 Agent 的论文复现覆盖率。当前不宣称“80% 自主复现”。本轮未创建提交、未推送 GitHub；协调仓库的 88 项科学 feature 保持不变，未运行协调根仓库 init。
