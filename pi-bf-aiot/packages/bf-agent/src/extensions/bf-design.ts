import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export type DesignApi = (body: Record<string, unknown>) => Promise<Record<string, unknown>>;
export type DesignEmit = (event: Record<string, unknown>) => void;

/** A real Pi extension: one task tool, durable intent, facts, and no second planner. */
export function designExtension(api: DesignApi, emit: DesignEmit): ExtensionFactory {
	return (pi) => {
		pi.registerTool({
			name: "bf_design",
			label: "BF design task",
			description:
				"Inspect the frozen task/source, record your plan/intent, freeze changed C/H, run an immutable snapshot, inspect independent checks/time windows, adopt with expected_revision, submit same-version delivery. run waits for the actual job without model polling. An UNKNOWN operation is never automatically repeated.",
			executionMode: "sequential",
			parameters: Type.Object({
				action: Type.Union(
					[
						"inspect",
						"source",
						"freeze",
						"run",
						"job",
						"check",
						"observe",
						"adopt",
						"intent",
						"events",
						"ack",
						"submit",
						"skill",
					].map((value) => Type.Literal(value)),
				),
				design_id: Type.Optional(Type.String()),
				parent: Type.Optional(Type.String()),
				sources: Type.Optional(Type.Record(Type.String(), Type.String())),
				operation_id: Type.Optional(Type.String()),
				job_id: Type.Optional(Type.String()),
				expected_revision: Type.Optional(Type.Integer()),
				rationale: Type.Optional(Type.String()),
				kind: Type.Optional(Type.Union([Type.Literal("CONTINUE"), Type.Literal("WAIT"), Type.Literal("BLOCKED")])),
				plan: Type.Optional(Type.Array(Type.String())),
				start: Type.Optional(Type.Number()),
				end: Type.Optional(Type.Number()),
				offset: Type.Optional(Type.Integer()),
				limit: Type.Optional(Type.Integer()),
				after: Type.Optional(Type.Integer()),
				cursor: Type.Optional(Type.Integer()),
				skill_id: Type.Optional(Type.String()),
			}),
			async execute(_id, args, signal) {
				let value = await api(args);
				if (args.action === "run") {
					const id = value.id;
					if (typeof id !== "string") throw Error("DESIGN_JOB_ID_MISSING");
					while (value.status === "QUEUED" || value.status === "RUNNING") {
						if (signal?.aborted) throw Error("DESIGN_WAIT_CANCELLED");
						await new Promise<void>((resolve) => setTimeout(resolve, 500));
						value = await api({ action: "job", job_id: id });
					}
					if (value.status === "SUCCEEDED") value = await api({ action: "check", job_id: id });
				}
				emit({ type: "design_tool_fact", action: args.action, input: args, result: value });
				return { content: [{ type: "text", text: JSON.stringify(value) }], details: {} };
			},
		});
		pi.on("before_agent_start", async () => {
			const view = await api({ action: "inspect" });
			emit({
				type: "working_view_restored",
				task_id: view.task_id,
				revision: view.revision,
				current_design: view.current_design,
			});
			return {
				message: { customType: "bf-task-state", content: JSON.stringify(view), display: false, details: {} },
			};
		});
		pi.on("context", (event) => {
			// The provider is the sole request projector. Archive/measure here;
			// never independently truncate unresolved tool calls in a second layer.
			emit({
				type: "design_context_observed",
				messages: event.messages.length,
				bytes: Buffer.byteLength(JSON.stringify(event.messages)),
			});
		});
		pi.on("tool_result", (event) => {
			emit({ type: "extension_tool_result", tool: event.toolName, tool_call_id: event.toolCallId });
		});
	};
}
