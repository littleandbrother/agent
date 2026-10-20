# BF 五阶段研究与工程发布 · 2026-10-20

本发布沿 `codex/bf-architecture-v2` 增量保存当前 S0 实现、Power/Firmware 契约与协作、状态反馈执行、工程预览/交付、存储管理，以及五阶段实际实验和两篇完整论文。Baseline 和旧 Demo 保留，未合并到 `main`。

## 阅读与下载

- [GitHub 交付入口](../deliveries/BF_FINAL_20261020/START-HERE.md)
- [完整封存包](https://github.com/littleandbrother/agent/releases/download/bf-five-phase-20261020/BF_FINAL_20261020.zip)，含原生 EDA、CAD/装配、PCB、源码/目标产物、原始结果、简详报告、论文及复现入口。
- [简报](evidence/five-phase-20261020/brief.pdf)与[详报](evidence/five-phase-20261020/detailed.pdf)。
- [方法论文及源码](../battery-world/papers/method-reexecution-20261019/final/)与[接口论文及源码](../battery-world/papers/interface-sufficiency-20261019/final/)。
- [阶段结果与最终审查](../docs/research/phase-plan-20261019/HOURLY-REVIEW.md)。历史记录中的作者机绝对路径保留为来源标识；跨机器复核使用封存包及下面的相对路径命令。

大体积波形和完整工程包通过 Release 交付。Git 仓库不保存运行数据库、密钥、依赖安装目录或活动 Pi 会话。相关原始记录留在原主机，发布包包含费用事实、UNKNOWN 和失败索引。

## 复现

完整包下载解压后，使用 Python 3.11 或更新版本：

```sh
cd BF_FINAL_20261020
python3 -B reproduce.py --output /tmp/bf-final-review
```

仓库中的两篇论文结果可独立从保存数据重建，不需要模型请求、原运行数据库或原生求解器：

```sh
python3 -B release/verify_source.py --manifest release/source-manifest-20261020.json
python3 -B battery-world/papers/method-reexecution-20261019/final/reproduce.py --output /tmp/bf-method-results --negative-controls
python3 -B battery-world/papers/interface-sufficiency-20261019/final/E_reproduce.py --output /tmp/bf-interface-results
```

软件回归采用 `.github/workflows/bf-v2-regression.yml`：Repository 输入/版本/恢复/复用检查、Campaign 和存储单测、Pi 构建与类型检查、源文件及论文保存数据复现。CI 结果应按本次实际提交读取。

## 工程与研究结论

阶段三为140次实际 episode，阶段四为77次实际尝试。阶段四最终 H0、G0、G1 分别通过7/9、6/9、8/9；三组后代谱系共享一次 G1 形成，结果保留为描述性证据。默认 H0 不变，尚未建立稳定 RSI 收益。

A/R 保留固定空间 NO_GO、暗区/FIFO FAIL 和产品 NOT_ACCEPTED。独立压电节点的数字验证与目标构建成立；实物制造、装配、电流、启动和 RF 未测，12项 DFM 警告保留。工程通过、模型内结果、物理资格和 Agent 方法收益分别报告。

本次发布复用已通过且输入未变的科学/原生结果；新增工作仅为源码与保存数据验证、打包和 GitHub 发布。十个原 Pi 会话、工程、费用、UNKNOWN、Baseline、Demo 和原失败记录保留。

## 发布兼容性修复

首个推送暴露的本机测试路径、缺失依赖和冻结脚本被格式化的问题已作定向修复。历史输入与失败以7.2MB只读测试夹具提供，测试使用独立且禁用执行能力的身份；没有修改生产资源门禁或科学判据。196项研究流程测试已在不依赖私有BF配置的环境通过，Pi类型、依赖与浏览器检查通过。详见[修复记录](evidence/five-phase-20261020/portable-ci-verification.json)。

CI follow-up: all196 campaign tests also pass with original workspace/private runtime access denied. Saved initial physical responses are bundled as a small test fixture, and unit outputs use temporary directories. Scientific results and frozen runtime scripts remain unchanged. See the Release publication receipt for latest-SHA remote status.
