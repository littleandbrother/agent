# 双论文与项目发布完成

- RSI：原 Overleaf 项目 https://www.overleaf.com/project/6ad5fb6e87c3ac6782d05b2c ，16 页。
- Agent 接口：原 Overleaf 项目 https://www.overleaf.com/project/6ad5fbda856b284d5d917ffd ，23 页。
- 两篇实际在线编译均为 0 错误、0 警告；已检查完整首页。左上留空，HKUST(GZ) 矢量校徽位于右上，标题居中两行，摘要顶端云端坐标差 0.000462 pt。
- 全部当前 BF 源码、ABC 实现、两篇最新稿、研究记录与原始证据已发布：https://github.com/littleandbrother/agent/tree/codex/bf-architecture-v2 。代码提交 `a2c8827e54fe401ac57c15fd428f38b6ac2f2756`；随后提交发布完成记录。
- 全新检出 CI 两轮全部通过，Python 测试为 343+196+14+24=577 项，另含 Pi 类型/构建/传输检查、完整源码摘要和已保存论文结果复现。
- 增量复现附件及两篇 PDF：https://github.com/littleandbrother/agent/releases/tag/bf-abc-20261020 。三个附件实际全部读回并核对 SHA-256；ZIP 内 1,442 个原始文件均逐文件校验。旧五阶段 Release 保留，原始失败、计费、UNKNOWN 与本地原始实验数据不改写。
- 发布前已扫描新提交和压缩原始响应的凭据模式；认证和 provider 配置不进入附件。
- 删除临时上传包 38,405,180 B；文件原分配 39,088,128 B。删除后实测可用空间变化 +58,277,888 B，当前可用 14,336,921,600 B。本轮发布开始可用 14,690,299,904 B，整轮可用空间变化 -353,378,304 B。可用空间包含并发系统活动，不能将删除文件大小直接当作实际释放量。
- 新依赖环境 0、工作树 0、完整运行目录备份 0、付费请求 0、科学/原生任务 0。每篇仅保留一份线上首页截图和精简发布回执。

截图位于 `overleaf/rsi/online-first-page.jpg` 与 `overleaf/interface/online-first-page.jpg`；在线检查未下载云端 PDF 字节，完整页文字坐标一致性来自实际两遍本地编译与已验收 PDF 的比较。

发布结论不扩展原研究边界：产品仍未验收，B 未证明精化优势，C 未优于相同历史的 H0；无稳定 RSI 或实物验收声明。
