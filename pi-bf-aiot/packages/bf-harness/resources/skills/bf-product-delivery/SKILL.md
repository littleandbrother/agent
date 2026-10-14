---
name: bf-product-delivery
description: "从当前候选自动准备文件、作业与哈希绑定，完成同版交付。"
---

先读 bf_design inspect 的作业、检查和未关闭门。Pi 选择作业、补充文件和 EDA 回执，编写报告。

用 bf_design prepare_delivery 一次准备元数据：
必填 operation_id、design_id、unresolved_gates。engineering_jobs、files、eda_receipts 省略时直接沿用 Pi 已冻结的候选选择；report_path 默认 native-report.json。需要缩小交付范围时显式传入对应数组。
文件来自当前冻结候选。原操作重试返回同一回执。程序生成 native-report.json 和 delivery/manifest.json，旧元数据保存到历史。

把元数据加入选择器，freeze → check → submit。分别记录工程结论、实际介入和物理验证。保留失败和已通过的原作业。

非候选任务沿原 publish_file → delivery_bind → delivery_inspect → delivery_package。恢复使用结构化当前状态，文件 SHA 和作业绑定由程序生成。
