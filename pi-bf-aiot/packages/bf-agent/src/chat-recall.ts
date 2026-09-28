import fs from "node:fs";
import path from "node:path";
import { SessionManager } from "@earendil-works/pi-coding-agent";

const data = JSON.parse(fs.readFileSync(0, "utf8"));
const workspace = path.resolve(data.workspace);
const pointer = path.join(workspace, ".pi/chat-session-path");
let result: any = { status: "not_delivered", message_id: data.message_id };
if (fs.existsSync(pointer)) {
	if (!fs.realpathSync(pointer).startsWith(fs.realpathSync(workspace) + path.sep)) throw Error("SESSION_PATH_DENIED");
	const file = fs.readFileSync(pointer, "utf8").trim();
	if (!path.resolve(file).startsWith(workspace + path.sep)) throw Error("SESSION_PATH_DENIED");
	if (fs.existsSync(file)) {
		if (!fs.realpathSync(file).startsWith(fs.realpathSync(workspace) + path.sep)) throw Error("SESSION_PATH_DENIED");
		const manager = SessionManager.open(file);
		const branch = manager.getBranch();
		const previous = branch.find(
			(e: any) => e.type === "custom" && e.customType === "bf_recall" && e.data?.operation === data.operation,
		);
		if (previous) result = { ...(previous as any).data, status: "recalled" };
		else {
			let index = 0;
			let target: any;
			for (const entry of branch as any[]) {
				if (entry.type !== "message" || entry.message.role !== "user") continue;
				const text =
					typeof entry.message.content === "string"
						? entry.message.content
						: entry.message.content
								.filter((c: any) => c.type === "text")
								.map((c: any) => c.text)
								.join("\n");
				while (index < data.messages.length && data.messages[index].text !== text) index++;
				if (index >= data.messages.length) throw Error("RECALL_CONTEXT_MISMATCH");
				if (data.messages[index].id === data.message_id) {
					target = entry;
					break;
				}
				index++;
			}
			if (target) {
				const before = manager.getLeafId();
				if (target.parentId) manager.branch(target.parentId);
				else manager.resetLeaf();
				result = {
					status: "recalled",
					message_id: data.message_id,
					operation: data.operation,
					previous_leaf: before,
					parent: target.parentId,
				};
				manager.appendCustomEntry("bf_recall", result);
			}
		}
	}
}
console.log(JSON.stringify(result));
