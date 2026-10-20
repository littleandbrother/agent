# BF 系统精简：第一批完成

本轮实际可用空间从 **5.94 GB** 增至 **12.03 GB**，净增加 **6.08 GB**。这是文件系统可用空间实测差值；没有把 APFS 共享副本的目录大小相加当成释放量。后台文件系统活动仍会造成小幅波动。范围为本项目及其 BF 本地运行目录，不涉及整机私人文件。

## 已执行

| 无损处理对象 | 处理前分配统计 | 处理后分配统计 | 回读结果 |
|---|---:|---:|---|
| 13 个历史试探波形 | 6.44 GB | 4.72 GB | 全文件 SHA-256 相同 |
| 56 个历史轨迹快照 | 2.26 GB | 0.41 GB | 全文件 SHA-256 相同 |
| 历史请求证据 / 计费账本 | 3.45 GB | 1.18 GB | 全文件 SHA-256 相同 |

上述 **70 个文件、12.15 GB 原始内容** 已全部在原路径重新读取并核对完整 SHA-256，权限与修改时间保留。采用 macOS 透明压缩，正常软件继续按原名称读取原始字节。历史账本 SQLite `quick_check=ok`，其中 **11 条 UNKNOWN** 原样保留。没有删除独有原始实验数据。

另外删除了 **27,171 个可重建文件**：干净的临时 Git 审查副本、三个已结束开发树的驻留 Python 字节码、已完成 CI 的 Python 环境和 node_modules。分配统计上限共 0.67 GB；它不能与上表直接相加充当净释放量。

- 审查副本确认为无修改、无未跟踪/忽略文件、无打开句柄，远端精确提交 `7e4aaff8294bf445d3ebd7d5e65028a43eff07ff` 当前可访问。恢复信息见 [cleanup.json](cleanup.json)。
- CI 源码、历史成功/失败日志与提交 `cf3594f9587cf75236334a594b25775e672093b8` 的发布凭据保留；重建环境的 Python 版本和依赖见 [ci-cleanup.json](ci-cleanup.json)、[requirements](ci-python-requirements.txt)。
- 压缩工具 [Applesauce 0.5.30](https://github.com/Dr-Emann/applesauce/releases/tag/applesauce-cli-v0.5.30) 只安装了校验过的 4.6 MB 本机程序及许可证，下载临时包已经清理；它不进入产品依赖。

## 占用原因与保留边界

大头是历史原生仿真、逐轮累计轨迹/请求上下文、归档交付物和多份工作区。历史账本单文件 3.45 GB 中，请求 wire 证据约 2.50 GB、请求上下文约 0.58 GB，直接清空会破坏实验与成本审计。

本轮后目录统计仍显示：参考案例约 33.65 GB、V2 workbench 约 24.77 GB、S0 运行目录约 8.55 GB、源码工作区总计约 9.44 GB；其中有此前已共享的 APFS 数据块。这些数值是目录分配统计上限，**不是独立物理占用，也不能求和得到系统总占用**。

继续按以下次序清理，不做无依据的整目录删除：

1. 核对遗留工作区的独有改动、绑定实验和云文件状态，再退休无用工作区。原 V2 和可复现实验基线保持冻结。
2. 对重复的累计请求/轨迹设计可完整还原的内容寻址存储；迁移前后必须逐行验证账本与 UNKNOWN。这是下一项独立维护特性，本批没有改 DB schema。
3. 整理 SDK/工具链安装包与重复环境，先建立精确恢复来源和已安装内容校验。本批安装包来源检索超时，未删除这些包。
4. 在新实验协议中先规定中间产物保留预算；历史封存 raw、失败、成本和评估输入继续保留。本轮没有事后降低证据标准。

## 已落地的防增长改动

S0 开发源码使用一个小型存储模块替代大文件的全量复制：缓存 → 执行目录、收敛产物 → 最终产物、证据库和报告输入，以及已结束会话的轨迹快照，优先采用**独立 inode 的 APFS 克隆**。未来追加或修改不会污染旧快照。非 APFS 的大文件回退复制必须先预留完整空间。

原生 cache miss 在 budget/dispatch marker 前检查 **10 GB 储备 + 2 GB 单次临时峰值**；2 GB 是本阶段的保守保护值，不是所有未来任务的已证明上界。整批任务还必须声明自己的完整峰值。zlib 改为流式处理并验证恢复后才删除 raw；临时读回文件在异常时清理。

根目录和 S0 的 AGENTS 已写入固定顺序：**预估空间 → 小批开发 → 针对性验证 → review 代码与生成物 → 清理 → 测量空间 → 下一批**。运行 Python 验证时禁用字节码缓存；复用登记环境，不新增整树备份或重复依赖。规范见 [STORAGE.md](../../workbench/bf-campaign-s0-20261019/battery-world/docs/architecture/STORAGE.md)。

改动已在 S0 开发树验证；生产与原 V2 服务没有升级到这些源码。未来执行会形成新的环境/源码身份，不能把原研究批次重新标成在新环境通过。封闭的四次 H0/H1 批次保持封闭。

## 验证

- S0 `architecture-v2-ci ./init.sh`：**343 项测试通过**，44 个封存文件 / 11 个控制验证通过。
- **14 项存储专项测试通过**：独立 inode、追加隔离、冲突保护、损坏/截断拒绝、云占位文件拒绝、空间不足时派发前停止、异常临时文件清理。
- 既有原生证据：168 个执行产物引用、288 个 cache 输出检查、387 个独立文件回读通过。
- 原生产 50 个会话 / 4,384 条模型请求，V2 40 个会话 / 24 个项目 / 1,705 条请求：完整所选表摘要与清理前相同；Baseline manifest 摘要相同。
- 本轮维护没有新增付费请求或原生仿真。S0 原 68 条请求仍全部 SETTLED。历史 ledger 中的 UNKNOWN 保留。
- 8768 / 8870 / 8980 入口均 HTTP 200；这仅证明入口响应。维护产生的临时目录最终为零。

证据：[summary.json](summary.json)、[preservation.json](preservation.json)、[readback.json](readback.json)、[init.log](init.log)、[targeted-tests.log](targeted-tests.log)、[artifact-readback.log](artifact-readback.log)。旧根仓库的完整 init 曾受云目录发现阻塞，本报告不宣称整个旧根仓库健康。

## 复现

只读空间审计不加载模型或仿真：

```sh
rtk proxy python3 -B workbench/bf-campaign-s0-20261019/battery-world/scripts/storage_maintenance.py audit
```

测试需要加载登记的 S0 profile，按其 paths 设置 BF 环境与源码 PYTHONPATH；完整加载方式已在 [研究批次复现说明](../research/parallel-campaign-20261019/REPRODUCE.md) 记录。之后运行 `BFWORLD_VERIFY_PROFILE=architecture-v2-ci PYTHONDONTWRITEBYTECODE=1 ./init.sh` 和 `python3 -B -m unittest discover -s tests/agentlab -p test_storage.py -v`。使用已登记的 Python 3.11 环境。

这是一批已完成、可核查的精简与防增长修改，尚不是“所有历史内容都已最小化”。当前可用于小批开发；新的大实验仍须先满足 10 GB 加整批峰值的空间门槛。
