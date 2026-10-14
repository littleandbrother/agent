import crypto from "node:crypto";

/** Observe duplicate reads, without inventing design progress from call counts. */
export class ReadProgress {
	private seen = new Map<string, number>();
	private state = "";
	private notice: string | undefined;
	observe(tool: string, args: Record<string, unknown>, result: unknown, state: string) {
		if (state !== this.state) {
			this.state = state;
			this.seen.clear();
			this.notice = undefined;
		}
		const read =
			tool === "read" ||
			tool === "bf_workspace" ||
			(tool === "bash" &&
				/^(?:rtk (?:proxy )?)?(?:cat|rg|sed|head|tail|ls|find|wc)\b/.test(String(args.command)) &&
				!/[>|;]/.test(String(args.command))) ||
			(["bf_design", "bf_product", "bf_skill", "bf_eda", "bf_engineering"].includes(tool) &&
				["inspect", "source", "interfaces", "catalog", "resource", "response_view", "artifact_view"].includes(
					String(args.action),
				));
		if (!read) return;
		const key = crypto
			.createHash("sha256")
			.update(JSON.stringify([tool, args, result]))
			.digest("hex");
		const count = (this.seen.get(key) ?? 0) + 1;
		this.seen.set(key, count);
		if (this.seen.size > 64) this.seen.delete(this.seen.keys().next().value!);
		if (count === 3)
			this.notice = `相同读取已返回三次，当前候选和检查未变化。已读动作：${tool} ${JSON.stringify(args)}。使用已有结果；若缺事实，指定新的字段或来源。`;
	}
	takeNotice() {
		const value = this.notice;
		this.notice = undefined;
		return value;
	}
}
