# 主线迁移交付 · 2026-10-01

## 结论

本阶段完成有限软件集成、语义对齐、证据工具及任务准入检查。缓存补丁可供评审；**完整应用、原生模型充分性、可行参考及正式 Agent 试验仍未通过准入**。没有改写既有科学研究、提交/推送代码或新增付费参加者调用。

### 实际结果

- cache-v2 定向 22/22、独立缓存检查 6/6、Node 27/27；SDK/Studio 类型检查通过。真实 CAD 在 48/50 mm 生成并重读 22 部件；力表→缓存→deck 字节重放通过。Cortex-M4 目标文件和主机共享库成功构建，SIL 只执行主机库
- 最终 v4 总回归：基线发现 425、运行 413、成功 352；集成发现 436、运行 424、成功 363。两者同为 32 个失败、29 个错误记录、2 个跳过；29 个错误含 2 个类级初始化错误，导致另 12 个用例未运行。共同测试状态逐项相同，新增 11 项通过。错误记录不能直接与测试计数相加
- Battery World 619/620 文件已核对；缺失 25.3 MB 历史 profiled-report。Pi 1774/1774 来源核对及离线 bf:build 通过。Linux 不具备所需 macOS Seatbelt 运行时，init/B2 和下游生成型 Studio 构建仍阻塞；两树均有未通过的 ngspice 数值断言。详见 integration/FINAL-ROOT-CAUSES.json
- 语义对齐 30/30，另 72 项坐标检查、4 项合成稳定性测试通过；独立审计重跑 30/30、72 项坐标及 8 项稳定性夹具检查。通过包含“预期差异成立”，不是整个模型等价
- 任务门槛 38/38；两个合同结构有效，但 **0/2 准入**。现有负结果受原模型假设约束，不能外推物理不可能或 Agent 优劣

### 随后获准的四次 ngspice 诊断

四次原设置配对运行已保留全部输入、deck、原始 TSV 与日志。相同步长下两种配置的全局位移峰值差均为 0；旧 97.5 nm 差值完全来自 10/5 µs 的细化差异。约 12.11 ms 的峰值先于改变后负载约 23.839 ms 的启动，故早期全局峰值不是该干预的有效观察量；后期轨迹确有差异，0.25 s 端点差约 0.4203 mm。原失败断言不变；不能据此宣传物理合格或整个应用通过。详见 ngspice-diagnostic/DYNAMIC-ADDENDUM.md。

### 必须保留的科学边界

48 mm 名义几何与相同坐标的磁力代数可窄范围比较；非名义 gap 改变的是不同物理轨迹。固件启动时序、PGOOD/欠压策略、载荷、接收和任务截止语义不同。原生 CAP/VIN2 与端口顺序证据仍缺失；稳定性夹具不提供真实芯片的默认稳定时间。

原生链负载常数来自 ViPSN-Pluck Table II 的作者原型实测能量/时长，再推算并取整为相平均电流；它们没有校准到我们的二进制。该论文为 **SP-SSHI + LTC3588-1 + MIC841**；2025 年 SP-SECE 论文是另一个案例。先读 PROVENANCE-ADDENDUM.zh.md，它补充来源解释而不修改旧报告。

未执行 COMSOL/LTspice 厂商验收、真实 nRF52832/S132、RF 或硬件验收，也未发起正式 Agent 试验。已有普通 CAD、主机 C 与有限数值计算的通过不能替代这些门槛。

## 文件入口

- integration/：冻结的 v2 集成包，最终结果以 INTEGRATION-RECEIPT-v2.json、aggregate-comparison-final.json 和 aggregate-*-v4 为准。INTEGRATION-RECEIPT.json、v2/v3 及独立审计中的旧总回归数字作为历史证据保留
- integration/cache-v2-integrated.patch：生产缓存与正常测试入口的集成 diff
- integration/unsupported-runtime-diagnostic/unsupported-runtime.patch：单独、未应用的运行时诊断建议；保留失败关闭，不绕过隔离
- alignment/：语义合同、机器差异矩阵、30 项测试、最终逐项证据、坐标/轨观测/稳定性工具
- task-gates/：TASKS.json、准入代码/38 项测试、启动分析、源绑定与未获准的后续方案
- ngspice-diagnostic/：独立的四次定界诊断及原始输出；原集成快照保持不变
- independent-audit/：原始独立复审；reference-research/：原创来源研究与引用索引
- alignment-inputs/：可移植窄范围对齐所需的精确源码副本；没有完整应用、工具链或历史科学原始大包
- collector-existing-delivery.json：采集器已有 Library 身份 libfile_075265fcb9fc8191a6d5c4b58ab19c61、版本 1；本包没有再分发采集器程序或重复创建身份
- FILE-MANIFEST.json、SNAPSHOT-SOURCES.json、DELIVERY-CONTRACT.json、VERIFICATION.json：本包文件哈希、原始路径、范围和验证记录

## 复跑与预检

先在包根运行：

```sh
python -B replay.py verify
python -B replay.py preflight
python -B replay.py alignment --output /tmp/NEW-UNIQUE-ALIGNMENT
python -B replay.py gates --output /tmp/NEW-UNIQUE-GATES
```

只用新的包外输出目录。alignment 需要 Python、NumPy、SciPy、jsonschema 与主机 cc；原记录版本见 alignment/requirements.txt。包装器在新副本中仅重定位 source-lock 路径，保留原锁与全部科学源码摘要，重跑 30+72+4 项有限检查。

gates 的完整 38 项包含旧科学来源和 ADI 原 PDF 的摘要核对；这些外部大数据/PDF 故意不重复分发。preflight 会列出缺失项，缺失时退出 2，不把来源跳过算作通过。在已获授权且具有原文件的机器上，可用 --source-map paths.json 指定“原绝对路径→本机路径”；仍逐文件核对原字节摘要。准入程序退出 2 是预期的“结构有效但未准入”，不是成功准入。包装器自身退出 0 仅表示正确重现了这个阻塞结果。

四次诊断的现有原始通道可在副本中重算，不启动求解器：先把 ngspice-diagnostic 整目录复制到新的包外目录，再运行副本内 analyze_retained_channels.py；它会重写副本的 CHANNEL-ANALYSIS.json。run_matched_diagnostic.py 是已完成四次运行的原始留档脚本，包含当时的源码/工具绝对路径，不能当成自动追加试验入口。

完整应用复跑须按 integration/REPRODUCE.txt 恢复同一提交 338d60384d5805abf1e02252a4513860066a2c39，并先做 patch --dry-run；集成补丁与诊断补丁分别评审。包内不会自动安装依赖、联网、运行供应商工具或读写真实凭据。

## 分发范围

不含 venv、node_modules、工具二进制、编译共享库、真实凭据、第三方 PDF/截图/抽取全文；只保留原创分析、网址/DOI/页码与来源哈希。内部原清单可能列出本次排除的原始文件；本包实际成员以 FILE-MANIFEST.json 为准。固定模型、物理轨迹、任务门槛、旧负结果与未知项均保持独立身份。
