---
name: bf-product-delivery
description: "独立复核跨专业依赖、同版本文件与交付清单，不将打包成功当成验收。"
---

先读取 bf_product delivery_inspect、analysis_inspect 和责任检查。以当前任务的原始责任、来源版本和实际文件验收；不换编号、不缩小到单个子模块。不把 analysis errors=[] 或某个局部 DRC 当成产品完整性通过。

逐项核对：参考功能覆盖与器件身份；原理图引脚/BOM/封装；保存后原生 PCB 网络和 DRC；板框/接口与机械尺寸；MCU 引脚、中断、错误路径与联合时序；制造与固件输出和来源。先定位失败或过期输入，再选择受影响的检查。已有有效检查复用，报告改字不触发整机计算。

交付流程为 publish_file → delivery_bind（真实 file_id/job_id、清单 task_id 与当前 assembly revision）→ delivery_inspect → delivery_package。任务适用性按需求与运行时规则判断，不能自行豁免硬性项。打包可包含缺口报告，但只有检查满足要求才声明工程通过。

保留三张独立记录：工程检查及未通过项；Pi/Codex/人的实际贡献与外部介入；物理验证未执行项。记录真实执行者，不把五个动画工作位解释成五个独立模型。更新 TASK/CHECKPOINT/analysis 与最终清单，使下一次恢复能够找到有效作业而非重建产品。
