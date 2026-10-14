import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import type { DesignApi, DesignEmit } from "./bf-design.ts";

/** Typed repository transport: one controller, persistent scopes, event-driven waits. */
export function repositoryExtension(api: DesignApi, emit: DesignEmit): ExtensionFactory {
	return (pi) => {
		pi.registerTool({
			name: "bf_repository",
			label: "BF Design Repository",
			description: `Use action summary/state/task/read/workspace_read/extract, skill_catalog/skill/skill_resource, assign/reopen/run_task/write/commit/execute/execution/finish/contract/integrate/validate/decide/release/close.
Reads: read(system_id,path,offset?,limit?). workspace_read(path). skill(skill_id), skill_resource(path,offset?,limit?).
Lead: assign(role power|firmware,base_system,question,completion,contract_ids?); reopen(task_owner,question,completion); run_task(task_owner) waits for a real specialist; contract(domain_commits:{power:DC,firmware:DC},rationale,parent?); integrate(base_system,domain_commits,contracts:{power-firmware:IC},expected_revision,rationale); validate(system_id); decide(system_id,expected_revision,decision REVISE|REJECT|RETAIN_FOR_REVIEW|ADOPT_PASSED|RESTORE,rationale); release(system_id,rationale); close(conclusion).
extract(system_id) returns source-derived facts and the declaration schema. Each interfaces/domain.json must include interface with ALL domain schema fields, and sources with exact frozen path/sha256/locator. Narrative facts/issues/assumptions can accompany it.
Specialist: write(path,content,expected_sha256 or null); commit(paths,expected_revision branch revision,rationale); execute(domain_commit,path project manifest) waits for actual fixed target build or SPICE; execution(domain_commit,path,job_id) reads existing job; finish(status SUBMITTED|BLOCKED,domain_commit?,conclusion).
Every mutation requires a stable operation_id. All actions use the bound project. Returned sha256 is the write precondition. No raw shell or external network.`,
			executionMode: "sequential",
			parameters: Type.Object({
				action: Type.Union(
					[
						"summary",
						"state",
						"task",
						"read",
						"workspace_read",
						"extract",
						"assign",
						"reopen",
						"run_task",
						"write",
						"commit",
						"execute",
						"execution",
						"finish",
						"contract",
						"integrate",
						"validate",
						"decide",
						"release",
						"close",
						"skill_catalog",
						"skill",
						"skill_resource",
					].map((v) => Type.Literal(v)),
				),
				operation_id: Type.Optional(Type.String()),
				system_id: Type.Optional(Type.String()),
				base_system: Type.Optional(Type.String()),
				path: Type.Optional(Type.String()),
				offset: Type.Optional(Type.Integer()),
				limit: Type.Optional(Type.Integer()),
				content: Type.Optional(Type.String()),
				expected_sha256: Type.Optional(Type.Union([Type.String(), Type.Null()])),
				expected_revision: Type.Optional(Type.Integer()),
				paths: Type.Optional(Type.Array(Type.String())),
				role: Type.Optional(Type.String()),
				question: Type.Optional(Type.String()),
				completion: Type.Optional(Type.String()),
				contract_ids: Type.Optional(Type.Array(Type.String())),
				task_owner: Type.Optional(Type.String()),
				domain_commits: Type.Optional(Type.Record(Type.String(), Type.String())),
				contracts: Type.Optional(Type.Record(Type.String(), Type.String())),
				parent: Type.Optional(Type.String()),
				rationale: Type.Optional(Type.String()),
				decision: Type.Optional(Type.String()),
				status: Type.Optional(Type.String()),
				domain_commit: Type.Optional(Type.String()),
				conclusion: Type.Optional(Type.String()),
				job_id: Type.Optional(Type.String()),
				skill_id: Type.Optional(Type.String()),
			}),
			async execute(_id, args, signal) {
				let value = await api({ ...args, action: `repository_${args.action}` });
				if (args.action === "execute" && !value.reused) {
					while (value.status === "RUNNING" || value.status === "QUEUED") {
						if (signal?.aborted) throw Error("DOMAIN_EXECUTION_WAIT_CANCELLED");
						await new Promise<void>((resolve) => setTimeout(resolve, 1000));
						value = await api({
							action: "repository_execution",
							domain_commit: args.domain_commit,
							path: args.path,
							job_id: value.job_id,
						});
					}
				}
				if (args.action === "run_task") {
					let prior = "";
					while (value.status === "STARTING" || value.status === "RUNNING" || value.status === "QUEUED") {
						if (signal?.aborted) throw Error("SPECIALIST_WAIT_CANCELLED");
						if (String(value.status) !== prior)
							emit({ type: "specialist_wait", owner: args.task_owner, status: value.status });
						prior = String(value.status);
						await new Promise<void>((resolve) => setTimeout(resolve, 1000));
						value = await api({ action: "repository_state", task_owner: args.task_owner });
					}
				}
				emit({ type: "repository_tool_fact", action: args.action, input: args, result: value });
				return { content: [{ type: "text", text: JSON.stringify(value) }], details: {} };
			},
		});
		pi.on("before_agent_start", async () => {
			const value = await api({ action: "repository_state" });
			emit({ type: "repository_state_restored", state: value });
			return {
				message: { customType: "bf-repository-state", content: JSON.stringify(value), display: false, details: {} },
			};
		});
		pi.on("context", (event) =>
			emit({
				type: "repository_context_observed",
				messages: event.messages.length,
				bytes: Buffer.byteLength(JSON.stringify(event.messages)),
			}),
		);
	};
}
