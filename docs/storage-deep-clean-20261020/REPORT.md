# BF 项目深度清理 · 2026-10-20

**实测净释放 12.26 GB；磁盘可用空间 10.73 → 22.99 GB。当前 10.90 GB 存储门槛已满足。**

占用大头是历史执行全量副本、展开的过渡目录、重复波形与上下文，以及下载后保留的安装包。

## 已完成

| 类别 | 具体内容 | 处理结果 |
|---|---|---|
| 必须保留 | Baseline、当前 Demo、十个原 Pi 会话及工程、账本和 UNKNOWN、当前 S0/A/B 源码与产物、在用工具链 | 保留，完整性核对通过 |
| 低频历史数据 | 旧资格验证、旧 Claude 执行副本、临时目录、旧发布源码 | 11,644 份展开文件移除，13.50 GB 内容压成一套 3.86 GB 归档 |
| 重复波形与长历史 | 原始波形、日志、轨迹、闲置数据库及 CAD | 1,147 份文件无损压缩或去重，原路径与内容保持可读 |
| 冗余安装包 | 已安装的 Go、Freerouting、ARM GCC、nRF5 SDK 下载压缩包 | 逐文件比对已安装内容后删除 4 份，约 364 MB |

项目根目录分配量从 14.82 降到 5.25 GB。运行目录和 Baseline 也已压缩；总释放量以上述磁盘前后实测为准。

## 核对结果

- Baseline 的 6,388 份文件逐个 SHA-256 一致。
- 当前两份工程交付共 230 件输出，摘要和大小一致。
- 生产、V2、历史研究、S0 四个数据库的会话及请求记录指纹一致；费用与 UNKNOWN 保留。
- 4 份归档全部解码核对，12 份文件抽样恢复通过。
- S0 的 11 项交接路径和 13 项活动依赖保留；S0/A/B 源码提交身份一致。
- Demo/V2/S0 三个服务返回 200。
- 新付费模型请求 0；新增原生仿真 0；Git 提交与推送 0。

## 恢复入口

历史归档位于 `/Users/depengsu/.local/share/bf-agent-history-20261020/`。原目录内保留 `ARCHIVED-20261020.md`。每份归档附文件摘要、元数据与恢复清单。

在项目根目录核验归档：

```sh
rtk proxy python3 -B docs/storage-deep-clean-20261020/archive_history.py verify old-qualification temporary-work old-claude-runs old-publication-source
```

按需恢复一个旧目录，例如：

```sh
rtk proxy python3 -B docs/storage-deep-clean-20261020/archive_history.py restore old-qualification
```

另外三个可恢复名称：`temporary-work`、`old-claude-runs`、`old-publication-source`。恢复时按原逻辑体积准备空间。

## 后续使用

主管继续现有阶段一，沿用原 S0/A/B 会话与工作区。每批保留 10 GB 加预计峰值；完成后清理展开的临时副本。历史归档按需恢复，后续工作直接使用当前源码和有效产物。

详细回执：[summary.json](summary.json)、[verification.json](verification.json)、[compression.jsonl](compression.jsonl)、[retired-files.jsonl](retired-files.jsonl)、[download-cleanup.json](download-cleanup.json)。
