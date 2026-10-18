# 执行与复核

本轮在 Architecture V2（8870）运行。生产 Demo（8768）、Baseline、原十个产品 owner 保留。

## 固定清单

- 原压电 owner 连续两轮设计；下一轮基于上一轮候选。
- 资料核对：两个任务，各比较直接读取和一名临时工作者。
- 设计组织：四个任务，各比较 single、temporary、fixed、joint。
- 全组共享每试验 80 次模型请求、4 个执行输入；工作者最多一层、一份返回。累计费用和时长按用户授权不限，清单结束即停止，不自动重采样。

## 数据位置

运行根目录：`~/.local/share/bf-agent-architecture-v2/continuous-design/`。

- `cycle-1-view.json`、`cycle-2-view.json`：每轮结束时的不可变视图。
- `pilot/registry.json`：任务、初始源文件、组织策略与身份。
- `pilot/trials/<trial>/dispatch.json`、`final.json`：每次执行和完整结果。
- `verification-all.json`：源树、执行、PDF、压缩包、轨迹与费用复核。
- 原始程序、波形、PDF和同版压缩包保存在现有 Repository 的内容寻址目录。

## 入口

```sh
python3 scripts/continuous_design_ops.py status
python3 scripts/run_organization_pilot.py status
python3 scripts/verify_continuous_design.py --stage all
python3 scripts/continuous_design_ops.py preservation
```

验证脚本自动加载 V2 环境及 CAD Python；PDF 检查调用现有报告解释器。操作程序由 `bf_v2_environment.environment()` 取得配置；不打印凭据。`drive` 按已保存的 dispatch/final 继续有限清单，保留所有原尝试。

## 本轮修复的公共执行问题

| 问题 | 处理 | 证据 |
|---|---|---|
| 长联合计算占用 SQLite 写事务，轨迹入库超时并取消 Pi | 求解移出写事务；按操作和执行身份加锁；完成后短事务入库 | 独立数据库写入回归、原会话后续计算与恢复 |
| 计算完成但响应或控制器中断 | 保留 dispatch/completed 与原生缓存；从完成回执导入，不重复执行 | 原会话中断恢复与执行身份 |
| 控制器将临时 SQLite 锁当成致命错误 | 同一轨迹游标延后入库；哈希和其他错误仍终止 | 注入锁冲突、轨迹篡改反例 |
| 波形副本耗尽磁盘 | 相同不可变文件按 SHA-256 核对后原子替换为硬链接，保留路径与内容 | dedup-plan.json、dedup-receipt.json、storage/ |
| 模型继续越过有限请求数 | 父子请求共同计数；上下文钩子先中断再报错 | 请求额度反例与实际账本 |

临时工作者只返回带来源的事实和文件提议，主设计者负责是否采用；服务端同时限制权限、冻结输入、递归委派和冲突合入。

执行过程中另使用 `clone_completed_native.py`：只匹配已成功完成的执行目录与缓存，按 SHA-256 核对原生波形副本后替换为 APFS 写时复制。先验证独立 inode 和写入隔离，再逐件复制、读回及核对摘要。当前运行中的原始求解文件不处理；保留路径与内容。完整计划与回执保存在 `storage/clone-*-{plan,receipt}.json`。

后续边界整理统一调用这个助手，使用 `storage/compaction.lock` 串行执行，跳过临时文件与未完成执行。原宽范围扫描曾与临时文件原子替换碰撞，使驱动在第11项完成后暂停；原 dispatch/final 保留，修复后从第12项继续，未重采样。

磁盘降至约1 GB时，`compress_completed_csv.py` 对已封存CSV使用APFS透明压缩；逐件核对逻辑字节、摘要及读回，随后用同一锁执行COW。文件路径和内容保留，完整回执为 `storage/csv-compression-*.json`。

## 本机容量与冷加载中断

第13项 T2-joint 修订执行遇到 ENOSPC，保留已登记的18次请求和 UNKNOWN 原生操作，不重采样。容量整理仅对已完成中间文本按相同SHA核对后替换为独立inode的APFS COW，74项保留原路径与逻辑字节；回执 storage/text-cow-*.json。磁盘由约110MiB恢复至数GiB（包含系统自身释放），未删除个人文件。

随后 T2-single 与 T2-temporary 在首个模型请求前分别因 Git 元数据读取和 Node 的 dataless package.json 加载失败退出。两者模型、工程调用及费用均为0。保留原 final.json 与失败 receipt；brctl 请求恢复本地文件、实际SDK import通过后，用 recover_zero_call.py 续跑同一注册owner、同一goal、同一H和协议。另存 recovery-dispatch.json / recovery-final.json；有任何模型输出、设计变化或执行结果的试验禁止这样恢复。审核同时保留两个零调用启动失败及最终模型尝试，模型试验仍每任务每组一次。

T2-joint 的中断通过 `reconcile_storage_failure.py` 对账：读回已完成的20秒原生波形，核对输入身份与压缩前后SHA，补齐缓存完成回执；外层联合迭代登记为FAILED，沿用原操作 `op-exe-rev1`。保存13次中断前原生调用，新增模型请求与原生求解均为0。原试验 `final.json` 保留，汇总额外列出这13次原生调用和1个未完成执行输入。对账后任务状态为READY_TO_VALIDATE，执行状态FAILED；未恢复该试验的模型运行。

最后一项T2-fixed达到80次父子共享请求后退出，后台执行随后以`FEEDBACK_FIXED_POINT_NOT_REACHED`入库。`settle_last_trial.py`只读核对该失败执行、12次原生迭代及完成缓存，追加`post-trial-settlement.json`；原`final.json`、模型轨迹与费用保持。汇总增加该次执行及12次已发生调用，新增模型请求和求解均为0。
