# 第二批工作区与环境精简回执

完成时间：2026-10-19T15:14:12.370594+00:00。实际整批可用空间：11.408 → 11.825 GB，净增加 **0.417 GB**（416,923,648 字节；十进制 GB）。每项清理即时前后差值合计 1.420 GB；其与整批净值的差异包含其他后台写入/回收和本次恢复清单，不能把目录 du 或缓存 CLI 数字当作独占物理回收量。

## 已处理

- 退役已完成的 A、B 工作区及旧 CI clean-source；16,445 份源文件的恢复来源全部 SHA-256 回读通过。共10份独有源码/状态内容仅319,913字节，放在一个内容寻址目录；已有 CB/IB overlay 和隔离 Git 对象继续复用，没有整树备份。
- 移除旧发布检查的 npm 环境及接收器 previous-receiver/venv；接收器1684项中1682项与保留的环境一致，另外两份配置/链接共532字节保留。原接收器、源代码、实验与服务未删除或重启。
- pnpm 官方 prune 删除1002个未引用包（CLI报告1.44GB内容；实测该操作可用空间差值0.547GB）；清除10个无运行进程或文件句柄的 npx 安装缓存，20份包定义/版本锁保留。
- 旧 UI node_modules 含云占位文件，原样保留；更老工作区的约7GB历史实验材料与非同一哈希波形保留。bf-agent-publish 的 Git 元数据仍供原 integration 工作区使用，未移除。

## Review与验证

已在删除前检查进程/句柄、完整源文件恢复路径与哈希，实际恢复抽样59项通过。删除后恢复清单再次通过。注册S0环境的 init：343项测试通过，44个已存文件/11个控制通过；生产/V2/历史与当前批次计费表哈希一致，11条UNKNOWN、11613条历史SETTLED和68条当前SETTLED全部保留，8768/8870/8980均HTTP200。活动源码无指向本批退役路径的链接。

首次未带运行profile的init被配置门禁拒绝，保留 init-unconfigured.*，随后注册环境重跑通过。全源码git diff检查20秒超时，维护路径范围检查通过；没有根目录全项目健康声明。0付费请求、0新原生求解、0根仓库提交。

## Overleaf

- RSI/方法重新执行：https://www.overleaf.com/project/6ad5fb6e87c3ac6782d05b2c；提交 `aeae1c44770029f9cafff94d358ca7ec944a2900`。
- Agent接口：https://www.overleaf.com/project/6ad5fbda856b284d5d917ffd；提交 `f51db4bcc90c9884bf409309bd1471fda8fffcfd`。

远端HEAD和fetch内容哈希匹配。每篇本地两轮LaTeX编译为3页，无警告，与已验证稿的文本相同。默认 example_paper.tex 转入 main.tex，已有远端历史和模板资产保留。云端编译未执行。凭据没有写入Git配置或回执；临时认证帮助程序已移除。

## 恢复与后续

只验证：`rtk proxy python3 -B docs/storage-slimming-20261019/batch-2/review.py --verify`。

恢复A或B到新的目录：`rtk proxy python3 -B docs/storage-slimming-20261019/batch-2/review.py restore a /absolute/new/workspace`（b同理）。生成独立Git工作区，保留已登记的文件字节、模式和修改时间；不恢复字节码等生成物。CI用role ci恢复源码，再按保留版本锁安装依赖。环境恢复方法及哈希在environment-plan.json；其他缓存锁在dependency-locks/。

继续单一S0源树。用户最新授权的PDF版式与Logo调整另立BFA-050，保持论文内容及实验/计费事实不变；编译、逐页review、同步Overleaf后清理中间文件。
