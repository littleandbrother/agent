# BF Agent 受控集成：双层私有检查点

本包保存已独立复核的两层代码集成、补丁、依赖锁、实际进程与任务记录。
没有启动真实模型、参与者实验或原生科学求解；没有 Git 提交或推送。

## 已经接通了什么

第一层（layer-01-launcher）：实际恢复的 Pi SDK 与编译器，干净子进程中的
Harness 导入及函数调用证据、失败/超时、全尝试日志、恢复、精确 H0 回滚。
32 项测试通过。保留两轮 22 次尝试记录，其中 18 个真实可信测试子进程；
第一轮的相对路径错误没有删除，也没有伪造成成功。

第二层（layer-02-magnetic-service）：
实际 Pi 注册的 bf_experiment 工具 → 原有 HTTP handler 的窄范围注册表扩展
→ 原始 candidate.json 上传 → 同一执行包绑定的任务请求
→ 既有原生 handoff → BLOCKED。
24 项测试通过。三轮实际进程与三个 BLOCKED 任务完整保留。
DEV-FEASIBLE-01 来自固定磁性任务注册表，不再借用旧 dev-01/dev-02 名称。

模型与预算由显式执行包读取。SDK 中的 offline-no-call-model 只是明确标记的
虚构离线初始化配置；approved_model、approved_budget 和授权仍为空。
工具调用由可信控制脚本发起，不是模型自主选择。注册其他工具不表示其流程已启用。
原生工具身份保持缺失；真实 handoff 返回缺少 pmic_model 身份，不用假哈希代替。

## 仍然阻断的事情

- 合格开发任务仍为 0/2；没有已接纳的独立可行参考
- 没有获批的真实模型、预算、账本、划分及盲测方案
- 当前主机没有已通过资格检查的参与者隔离环境
- 原生商业工具/模型身份与独立物理证据尚不齐全

因此，本包不构成自主 Agent 成效、参与者自产 H1、RSI、科学改进或硬件合格证明。
历史成本和完整 H 循环成本没有被事后补造。

## 在任何普通 Python 环境可做的只读检查

解压后在本目录运行：

    python3 -B verify_portable.py

该命令只核验文件哈希、原封存清单、事件哈希链、进程调用输出、执行包和 BLOCKED
任务关联。它不启动 Pi、HTTP 服务、模型或原生求解器，不访问凭证。

## 重跑真实 Pi 需要什么

真实运行与上述便携核验是两件事。运行包中的 integration 测试需要原来已恢复、
锁定版本的 Pi 构建、Node、TypeScript 编译器、Battery World Python 源码及世界/
协议输入。dependency-locks/ 保存原始 npm/Python 锁、输入哈希和运行环境信息；
这里没有 node_modules、工具二进制、商业模型文件或凭证，也没有自动安装脚本。

源码仍使用已审计的 /workspace/shared/... 固定输入布局。应在原固定环境或按相同
输入哈希恢复的隔离工作区中复现；移动/重配后是新的实现版本，须重新记录来源。
不要在原封存包内重跑会生成输出的测试，应复制到新的审核工作区。

第一层：
    python -B -m unittest discover -s tests -v
    python -B run_controls.py --output reports/NEW-controls

第二层：
    python -B -m unittest discover -s tests -v
    python -B run_probe.py --output reports/NEW-probe

这仍只是可信离线测试。不得去掉 dry-run/资格检查，也不得把虚构配置当成真实预算授权。

## 文件导航

- layer-01-launcher/：第一层原封存清单、源码、补丁、全部保留进程记录
- layer-02-magnetic-service/：第二层注册表/显式协议扩展、原始上传、任务和进程记录
- independent-review/：独立源码、字节、进程/日志回读与测试结果
- authority-inputs/：与本检查点相关的固定协议、任务、世界和评估器输入
- dependency-locks/：精确依赖锁、固定版本/环境信息及完整原始输入哈希清单
- PORTABLE-MANIFEST.json：本导出包所有包含文件的哈希
- EXPORT-OMISSIONS.json：明确排除的认证目录及外部依赖符号链接

第一层原始封存包没有修改。为避免输出凭证，本导出不包含生成的 .pi/auth.json
等认证路径，即使它们只是测试生成文件；这些排除项逐一列明。原清单原样保留，
便携核验会区分明确排除项和无法解释的缺文件。所有进程 stdout/stderr、尝试日志、
上传源文本和任务记录均保留。旧轮次报告只代表当时范围，第二层已解决的注册表障碍
不要继续当作当前的硬编码障碍；真正的授权/资格/原生身份阻断仍然保持。
