---
name: bf-task-recovery
description: "恢复当前候选、有效作业、未关闭问题和活动技能。"
---

恢复候选任务先读 `bf_design inspect`。目标、采用版、工作版、选定作业、检查和待确认操作集中在此。文件清单加 `fields=["input_manifest"]`；接口读 `bf_design interfaces`。已有作业按原 ID 查询，原操作按原身份恢复。

历史通过“历史控制器索引”的文件和 SHA 定位，只取当前判断所需段落。修改后冻结新候选，重验受影响输入；未变且有效的作业复用。

专业工作开始时 `bf_skill activate skill_id=...`；恢复保留已激活版本。资源用 `bf_skill resource path=...`，大文档按章节读取。
文件哈希、JSON 字段和文本定位用 `bf_workspace`。临时分析放 workspace/scratch。等待原生作业交给后台，结果变化再继续。

非候选任务通过 `bf_product context_inspect` 恢复同一 owner；需要项目记录时再读 TASK、CHECKPOINT 和 analysis。
