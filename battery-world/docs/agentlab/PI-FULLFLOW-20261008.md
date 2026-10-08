# Pi 磁耦合门磁全流程 · 当前检查点

更新时间：2026-10-08 18:10 CST。参与者 `pi-chat-8ae12ef0354d33bb`，DeepSeek 接入的 Pi-BF Agent。

## 当前结论

真实 Pi 已产生原生原理图、PCB 布局与布线尝试、目标固件、名义联合仿真和部分交付文件；完整产品交付尚未通过。操作者的工具修复和独立反例均单独记录，不声称零人工自主完成。

2026-10-08 17:51/17:52，供应商返回 HTTP 402，正文明确为 `Insufficient Balance`。本地预算没有耗尽，未清空计费、改换模型或伪造结算。模型请求已停止，原任务、失败、产物和检查点保留。

## 本轮新增可核对进展

- 中断恢复：修复 launcher 对缺少 ended/trace_hash 的历史收据访问，以及历史 idle/error 被重放为新进程状态的问题。2 项 launcher 与 14 项 chat 测试通过，真实同 owner 模型执行随后恢复。原始收据保留，缺失字段显式为空。
- 布线执行器：官方 Freerouting 2.5.0 JVM 发行版替代会触发序列化异常的原生发行版。相同失败 DSN 未改，14.6076 秒产生 SES，路由器报告 0 unrouted/0 violations；未导入产品，不能当作 Pi 最终 PCB DRC 通过。
- 新固件 `eng-e0516772a5a40e54`：Pi 修正 RTC COMPARE0 位、实际 IRQ17 向量绑定、超时计时及共享应用逻辑。主机回归记录为 90 检查/0 失败；保留原厂位定义负控。目标 flash 5028 B、static RAM 48 B、stack 4096 B。独立检查 BIN 向量槽 16+17 的 1013 与强定义 IRQ17_Handler 一致，非 Default_Handler 225。
- 已复制 ELF/HEX/BIN/源 ZIP 与后端同名产物逐字节一致。ELF SHA-256：351ad358162f39b079e74ed2e4001667fe24c55c065ab33a659a7ba8eca43d59；BIN：785f882c4faf56ae6fbb6c0144eb266f453f9616f234fddd6c385fc605659af1。
- 18:05 用户打开既有新工程后，Web EDA 4.1.71 / connector 1.9.0 正式读回 project `a6f17c3f2a1d4a76922192455de451ce`、P1 `c28493c0c97ff779`、PCB `7a57eb032390b66d`。原理图读取到 61 part、43 netflag、12 netport、1 sheet。此前桌面旧 D3 上的项目打开失败保持记录；未重建工程，未向旧板写入。

## 已通过但不重复执行的参考计算

Pi 的 `eng-28deaae4839d843d` 名义预测 eligible/satisfied；常规和半步长均完成供电—程序固定点，完整 TX=1，八项资格检查通过。新固件/原生板的实体等价、器件选型/额定及物理制造资格不能自动继承此结果。硬件、射频和实测功耗仍未验证。

## 独立交付反例与剩余任务

原样复制 `delivery/exports/firmware` 至隔离目录，运行其中 `build_firmware.py --host-only` 退出 1：构建脚本仍寻找旧工作区的 project/vendor/tools 布局。导出 src/project.json 声明的 sil_program.h 缺失，主机测试源和依赖也未完整打包。源 ZIP 中存在该头文件；因此这是导出组织缺陷，不能据此否定已经构建的目标二进制，也不能称便携工程包通过。

R3 元件身份/额定、原理图剩余完整性；R4 新板真实路由导入、原生 DRC 与保存重开；R2 机械包络适配实际板尺寸；R7 独立可复算工程包、更新报告/检查点和交付绑定仍需 Pi 完成。当前页面显示装配 v6、57 件可读成果；文件数不代表责任验收通过。

## 费用和执行边界

截至 audit-20261008-1804.json：1221 请求，1217 SETTLED；本地按配置费率记录 USD21.7501536，4 条 UNKNOWN 预留 USD0.3952494，总上界 USD22.145403。包含完整任务历史，不是本轮恢复单段费用；不等同供应商账户余额或实际账单。现行 attempt/study 上限 USD30，原 24 小时窗口不变。

## 复现证据和继续入口

运行证据基目录：`~/.local/share/bf-agent-runtime/reference-cases/door-selfpower-v1/pi-fullflow-20261008/`。

- runtime-recovery25.json、recovery25-tests.log：恢复修复。
- router-repair23/jvm-route-receipt.json：相同输入的执行器诊断。
- independent/firmware-vector-after23.json：目标向量独立读回。
- independent/firmware-portability-27/result.json 与 host-only.log：导出缺陷最小复现。
- eda-reconnect27/：实际项目/页面/原理图对象读取。
- runtime-amendment27.json：恢复上下文、供应商阻塞和独立反馈归属。
- audit-20261008-1804.json：只读执行/费用/Trace 身份，不自动决定工程验收。

参与者目录 ENVIRONMENT-UPDATE-27.md 已准备上述事实，尚未触发付费调用。用户充值后，核实工程连接仍有效，续接同一 owner 并令 Pi 读取该文件，继续自己的设计/修复/交付；不重派已完成联合求解，不换产品源，不重复创建工程，不把根代理的诊断 SES 冒充 Pi 最终板。

本轮未提交/推送 Git。完整 init 既有尝试受缺失历史 deployment manifest 阻断，未声称全仓库健康；本次恢复相关 16 项检查通过。BFA-035 总体保持 in-progress。


## GitHub 检查点补记

此前“未提交”描述对应 18:10 检查点。本次用户随后明确要求提交 GitHub，并告知余额恢复；源码、检查和剩余任务随本版本发布，详见 `release/SELFPOWER-PI-CHECKPOINT-20261008.md`。恢复后的供应商执行结果另行记录，不回写上述历史 402 或原有验收事实。
