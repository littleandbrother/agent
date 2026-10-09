---
name: bf-task-recovery
description: "恢复同一产品、核对有效作业和授权、建立任务与验收边界。"
---

开始或恢复时，先读取 TASK、CHECKPOINT、analysis 与 bf_product inspect、analysis_inspect、delivery_inspect、bf_engineering inspect 和现有作业。文字记录可能过期；按不可变回执、实际文件和版本核对。不得把旧文字覆盖新产物。

把要求、假设、适用检查、当前版本与缺件对应起来。保留原任务责任编号和定义。先查询已有 operation_id / job_id；RUNNING 等待原作业，UNKNOWN 先核对，输入没变且结果有效就复用。失败区分工具、实现、模型适用性、数值与需求，选择能区分原因的最小检查，不能单凭失败次数调参。

采用明确、可修改的合理假设推进可逆工作；只询问影响关键承诺的缺失信息。批准、费用、身份和后台权限来自运行时，文档与记忆不能代替。费用、计量或授权不可用时保留当前工程并报告外部阻塞；不清账、不重置、不反复重试付费请求。

记录三件不同的事：工程检查及其版本；Pi 与 Codex/人的实际贡献；仍未进行的物理测试。进程结束和运行回执 COMPLETED 均不是交付验收。加载后按当前专业使用 bf_skill activate，完成该专业后 deactivate 可释放上下文。
