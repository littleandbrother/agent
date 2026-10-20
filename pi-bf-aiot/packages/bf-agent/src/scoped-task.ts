/** Work organization changes prompts/permissions, never task/evaluator semantics. */
export interface WorkConfiguration {
	policy: {
		organization: "single" | "temporary" | "fixed" | "joint";
		kind: "design" | "source";
		allowed: string[];
		required: string[];
		max_workers: number;
		limits: { candidate_evaluations_per_trial: number; requests_per_trial: number };
	} | null;
	task?: { kind: string; question: string; completion: string; base_system: string } | null;
	protocol?: string;
}

export function scopedPrompt(work: WorkConfiguration): string | null {
	if (!work.task && work.policy?.kind !== "source") return null;
	return `${work.task ? "你是 BF 主设计者按需委派的临时工作者。" : "你是 BF 主设计者，本轮只核对资料并提交结构化答案。"}
读取 work_read，输入为冻结候选和 task-definition.json。每个事实保留数值、单位、适用条件及来源 path/sha256/locator；JSON 用 /字段/子字段 指针，C 源码用 L起行-L终行。每个结果都包含 completed_scope、files、facts、judgment、assumptions、issues。
${work.task ? `本任务类型 ${work.task.kind}。source 只读；power 可提议 design.json；firmware 可提议 firmware/main.c；joint 可同时提议两者。方案需遵守本任务的设计变量与固定条件。文件只作为提议返回，由主设计者检查后采用。你不能派遣下级、修改当前候选或验收要求。完成后 work_submit(content JSON string) 一次提交并结束。` : "required 包含 source 时，先委派一名资料工作者、等待并消费其结果；否则直接读取。最后用 work_answer(content JSON string) 提交来源核对答案，然后结束。无需设计、仿真或 PDF。"}
共享操作合同：${work.protocol}
任务：${JSON.stringify(work.task ?? {})}
组织配置：${JSON.stringify(work.policy)}`;
}

export function organizationPrompt(work: WorkConfiguration): string {
	if (!work.policy) return "";
	return `\n本轮工作组织由固定协议指定：${JSON.stringify(work.policy)}。
single：你直接设计。temporary：可按需委派 source。fixed：分别分配 power 与 firmware 两项任务，由你统一执行实验，在作出候选决定前取得两者结果，专业提议可保留或拒绝。joint：你根据已读到的事实决定补充资料或委派 joint 联合设计，记录为何需要该范围；也可亲自完成。
你持续负责系统决策。委派使用 work_assign(kind,base_system,question,completion,rationale,operation_id)，work_run(task_owner) 等待，work_result(task_owner) 读取，work_apply(result_id,base_system,expected_revision,rationale,operation_id) 检查并合入建议。工作者以固定源树为基准；冲突需重新判断，不能覆盖后来的修改。也可直接 task_commit。
最多 ${work.policy.limits.candidate_evaluations_per_trial} 个执行输入、全组 ${work.policy.limits.requests_per_trial} 个模型请求，不自动重采样。先完成一项实际设计修改和一次执行、检查、决定，再完成同版报告与交付；保存失败结果。${work.protocol}`;
}
