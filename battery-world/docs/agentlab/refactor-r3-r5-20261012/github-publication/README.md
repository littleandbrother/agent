# BF Agent 代码与审查资料 · 2026-10-12

本次发布基于集成提交 `7e4aaff8294bf445d3ebd7d5e65028a43eff07ff`，分支为 `codex/bf-design-lab-r0-r2-20261011`。
代码位于本仓库的 `battery-world/` 和 `pi-bf-aiot/`。本目录的资料包可以下载并上传到网页版模型审查。

## 阅读与下载

- [R0–R2、C 案例审查包](BF_Agent_R0-R2_C_Acceptance_20261012.zip)
- [R3–R5 最新系统审查包 v3](BF_Agent_R3-R5_System_Review_20261012-v3.zip)
- [原实施计划](BF_Agent_Refactor_Implementation_Plan_20261011.md)
- [R0–R2 实施报告](../../DESIGN-LAB-R0-R2-20261011.md)
- [R3–R5 实施报告](../../DESIGN-LAB-R3-R5-20261012.md)
- [使用者、研究者、工程与论文综合审查](../../SYSTEM-REVIEW-20261012.md)
- [当前结论回执](../closeout.json)与[历史结论更正](../validity-amendments.json)

ZIP 内有真实源码、函数索引、公开轨迹、独立检查、费用记录、同版本数字交付与 SHA-256 清单。
其中 `source/` 是打包时当前源码，`frozen-controller/` 是具体实验实际运行版本，两者不能互相替代。
历史失败和撤销的通过记录保留在包内，须与更正回执一起阅读。

## 已证明的范围

有限 C/A/B 案例完成了 Pi 设计、实际程序编译和执行、独立检查及同版交付。A/B 使用受限源模型、固定阶段电流和虚拟无线服务。
完整 R3 的校准源、开关变换器、目标外设与 RF 链尚未完成。R4 实际生成并比较了方法候选，追加确认结果为 `REJECT`，未在生产采用。
R5 没有已确认的父方法，因此没有递归后代验证；物理验证仍为 `NOT_TESTED`。
十个原论文会话的阶段文件包核对为 10/10，完整数字产品确认通过为 0/10，两者分别记录。

应用 `./init.sh` 的已封存运行通过 932 项 Python 测试；17 项定向测试通过。它不能替代根科学仓库、十篇整机或物理验收。
本次推送与文件回读不派发模型，不重跑已通过的旧仿真，不改变原 owner、UNKNOWN、费用记录或原 UI。

## 核对下载内容

在检出此分支后的仓库根目录执行：

```bash
python3 battery-world/scripts/design_lab/verify_publication.py --checkout .
```

该检查核对 `SOURCE-PUBLICATION-MANIFEST.json` 中全部新增/修改发布文件，以及两个 ZIP 的每个清单成员和 CRC。
这是一项无外部依赖、无模型、无求解器的文件完整性检查。
清单不哈希自身，提交 SHA 由 Git 单独提供。

完整实验依赖 macOS sandbox、Python/Node 依赖、已固定工具链、SDK、源数据与服务配置；相关前提见报告和资格回执。
本仓库不携带私人密钥、运行数据库、SDK 私人会话、隐藏思维链、venv/node_modules 或外部依赖二进制。
资料包中的绝对路径用于定位当时机器上的原始回执；公开证据可以从 ZIP 中按对应相对路径读取。

## 本机 EDA 接入核对

桌面版可用，不要求切换到网页。BF 当前走 `EdaCLI` 的 typed CLI 接口；官方 API bridge 是另一种协议，安装任一 Connect 不会自动满足另一种协议。
本次只读检查前 typed daemon 未运行；已启动 v1.9.0 的 `127.0.0.1:60832` daemon，未更新 Skills。
随后 typed daemon 的 `windows=[]`，现有官方 bridge 的 `edaConnected=false`、窗口数 0，桌面客户端未运行。
因此还没有读到本地工程或验证桌面设计写操作。

本机应用安装信息为 `嘉立创EDA(专业版).app` / `cn.lceda.pro` / `2.2.32.4`；它不是运行时编辑器 API 版本证明。
需要打开目标桌面工程，在当前模式启用对应连接器并允许外部交互，再以 health 和项目/文档读回确认兼容性与精确项目身份。
当前全局 EasyEDA Skill 还带有 Web-only 工作流约束；这是方法配置，不能解释为桌面技术不支持。
本次没有迁移、导入、覆盖工程或更改这些冻结技能。

官方说明：[客户端运行模式](https://prodocs.lceda.cn/cn/faq/client/)；[扩展启用和外部交互权限](https://prodocs.lceda.cn/cn/api/user-guide/using-extension.html)。
