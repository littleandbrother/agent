import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import type { DesignApi, DesignEmit } from "./bf-design.ts";

/** Typed repository transport: one controller, persistent scopes, event-driven waits. */
export function repositoryExtension(
	api: DesignApi,
	emit: DesignEmit,
	declarationText: string,
	reportOnly = false,
	taskMode = false,
	workMode?: "worker" | "source" | "design",
): ExtensionFactory {
	return (pi) => {
		pi.registerTool({
			name: "bf_repository",
			label: "BF Design Repository",
			description:
				(workMode
					? "Scoped work: work_read(path,system_id?,offset?,limit?) reads frozen candidate files or task-definition.json. work_assign(kind source|power|firmware|joint,base_system,question,completion,rationale,operation_id); work_run(task_owner) waits; work_result(task_owner?) returns result; work_tasks lists assignments; work_apply(result_id,base_system,expected_revision,rationale,operation_id) merges proposal. work_submit(content JSON string,operation_id) submits worker result; work_answer(content JSON string,operation_id) submits source-study lead answer. Result fields: completed_scope,files:{path:UTF8},facts:[{field,value,unit,conditions,sources:[{path,sha256,locator}]}],judgment,assumptions:[],issues:[]. locator JSON pointer or Lstart-Lend. "
					: "") +
				"Task intake: task_assessment_schema returns the shared assessment prompt and fields. task_assess(request,assessment JSON string) validates a proposed intent, scope, user requirements, missing inputs and plan without changing the project. " +
				(taskMode && !reportOnly
					? `Task contract: task_definition(system_id?); task_schema returns fields, allowed design files, fixed scenario, required checks, and report section IDs. task_state returns the current phase, executable scope, recovery state, independent qualification, interface levels and same-version delivery; these facts determine legal continuation. summary/state show current candidate and revision. Hard constraints and the declared design space are enforced at commit. read(system_id,path,offset?,limit?) reads frozen sources. task_commit(base_system,expected_revision,files:{path:UTF8 content},rationale,operation_id) merges changes into the full parent tree. task_execute(system_id,operation_id) compiles/runs supported inputs or reuses an exact prior result. task_result(system_id,path?,offset?,limit?) reads existing execution artifacts and compact derived facts (load-rail energy, per-frame voltage minima); it never dispatches a solver. validate(system_id,operation_id) evaluates raw results against this candidate's task requirements. decide(system_id,expected_revision,decision REVISE|REJECT|RETAIN_FOR_REVIEW|ADOPT_PASSED,rationale,operation_id). task_report(system_id,content JSON string,operation_id) expects {conclusion:string,sections:{section_id:{text:string,sources:[candidate path or gate ID]}}}; use the report section IDs from task_schema and every section must cite current sources. release(system_id,rationale,operation_id) includes frozen sources, execution artifacts, checks and PDF. close(conclusion,operation_id) finishes after same-version release. skill_catalog/skill(skill_id)/skill_resource(path) load methods on demand. Every mutation uses a stable operation_id. Requirements and evaluator code are operator-owned. No raw shell or network.`
					: `Report actions: report_schema(scope power|firmware|lead), report_read(report_id,path? default facts.json,offset?,limit?), report_status(report_id), report_write(report_id,scope,content JSON string,expected_sha256 null or previous,operation_id), report_prepare(system_id,operation_id), report_build(report_id,operation_id). All author JSON uses the exact schema returned by report_schema; report_read input/sources/candidate/<path> reads frozen sources. Report-only runs cannot dispatch engineering or modify designs.
Use action summary/state/task/read/workspace_read/extract, skill_catalog/skill/skill_resource, assign/reopen/run_task/write/commit/execute/execution/finish/contract/integrate/validate/decide/release/close.
Reads: read(system_id OR domain_commit,path,offset?,limit?). workspace_read(path). archive_read(path,offset?,limit?,pointer?) reads immutable owner-local context-records references; pointer selects a JSON field (e.g. /branches or /project/submitted). Read limit is at most 24000 characters. Use archive_read for archived observations instead of reissuing the same large summary. skill(skill_id), skill_resource(path,offset?,limit?).
Lead: assign(role power|firmware,base_system,question,completion,contract_ids?); reopen(task_owner,question,completion); run_task(task_owner) waits for a real specialist; contract(domain_commits:{power:DC,firmware:DC},rationale,parent?); integrate(base_system,domain_commits,contracts:{power-firmware:IC},expected_revision,rationale); validate(system_id); decide(system_id,expected_revision,decision REVISE|REJECT|RETAIN_FOR_REVIEW|ADOPT_PASSED|RESTORE,rationale); release(system_id,rationale); close(conclusion).
rebase(task_owner,base_system,expected_revision branch revision,question,completion) explicitly starts the next task on a new System Commit, retaining old task/workspace/branch/history. Uncommitted files must first be committed. reopen keeps the old base.
extract(system_id,domain_commits?) returns source-derived facts and legal declaration examples, including peer commits on this base. ${declarationText}
validate(system_id,scope system|interface default system) appends independent evidence for the eight P01 gates; summary gives current qualification, separate from the timing contract. Specialist: write(path,content,expected_sha256 or null); commit(paths,expected_revision branch revision,rationale); execute(domain_commit,path project manifest) waits for actual fixed target build or SPICE and returns consumed sources; execution(domain_commit,path,job_id) reads existing job; finish(status SUBMITTED|BLOCKED,domain_commit?,conclusion).
Failed execute/execution returns immutable input references and compiler/solver diagnostics. execution(domain_commit,path,job_id,offset?,limit?) reads more of that existing log without dispatching another job.
Every mutation requires a stable operation_id. All actions use the bound project. Returned sha256 is the write precondition. No raw shell or external network.`),
			executionMode: "sequential",
			parameters: Type.Object({
				action: Type.Union(
					[
						"work_read",
						"work_assign",
						"work_run",
						"work_result",
						"work_tasks",
						"work_apply",
						"work_submit",
						"work_answer",
						"summary",
						"task_assessment_schema",
						"task_assess",
						"task_schema",
						"task_definition",
						"task_state",
						"task_commit",
						"task_execute",
						"task_result",
						"task_report",
						"state",
						"task",
						"read",
						"workspace_read",
						"archive_read",
						"extract",
						"assign",
						"reopen",
						"rebase",
						"schema",
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
						"report_schema",
						"report_read",
						"report_status",
						"report_write",
						"report_prepare",
						"report_build",
					]
						.filter((v) => !v.startsWith("work_") || Boolean(workMode))
						.filter(
							(v) =>
								!taskMode ||
								reportOnly ||
								v.startsWith("work_") ||
								[
									"summary",
									"task_assessment_schema",
									"task_assess",
									"state",
									"read",
									"archive_read",
									"task_schema",
									"task_definition",
									"task_state",
									"task_commit",
									"task_execute",
									"task_result",
									"task_report",
									"validate",
									"decide",
									"release",
									"close",
									"skill_catalog",
									"skill",
									"skill_resource",
								].includes(v),
						)
						.filter(
							(v) =>
								!reportOnly ||
								[
									"summary",
									"task_assessment_schema",
									"task_assess",
									"state",
									"read",
									"archive_read",
									"skill_catalog",
									"skill",
									"skill_resource",
									"report_schema",
									"report_read",
									"report_status",
									"report_write",
									"report_build",
									"release",
								].includes(v),
						)
						.filter(
							(v) =>
								workMode !== "worker" ||
								[
									"work_read",
									"work_result",
									"work_submit",
									"state",
									"task_schema",
									"task_definition",
									"task_result",
								].includes(v),
						)
						.filter(
							(v) =>
								workMode !== "source" ||
								[
									"work_read",
									"work_assign",
									"work_run",
									"work_result",
									"work_tasks",
									"work_answer",
									"state",
								].includes(v),
						)
						.map((v) => Type.Literal(v)),
				),
				operation_id: Type.Optional(Type.String()),
				kind: Type.Optional(Type.String()),
				result_id: Type.Optional(Type.String()),
				request: Type.Optional(Type.String()),
				assessment: Type.Optional(Type.String()),
				report_id: Type.Optional(Type.String()),
				system_id: Type.Optional(Type.String()),
				base_system: Type.Optional(Type.String()),
				path: Type.Optional(Type.String()),
				pointer: Type.Optional(Type.String()),
				offset: Type.Optional(Type.Integer()),
				limit: Type.Optional(Type.Integer()),
				content: Type.Optional(Type.String()),
				files: Type.Optional(Type.Record(Type.String(), Type.String())),
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
				scope: Type.Optional(Type.String()),
				domain_commit: Type.Optional(Type.String()),
				conclusion: Type.Optional(Type.String()),
				job_id: Type.Optional(Type.String()),
				skill_id: Type.Optional(Type.String()),
			}),
			async execute(_id, args, signal) {
				if (
					reportOnly &&
					![
						"summary",
						"task_assessment_schema",
						"task_assess",
						"state",
						"read",
						"archive_read",
						"skill_catalog",
						"skill",
						"skill_resource",
						"report_schema",
						"report_read",
						"report_status",
						"report_write",
						"report_build",
						"release",
					].includes(args.action)
				)
					throw Error("REPORT_ONLY_ACTION_REQUIRED");
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
				if (args.action === "run_task" || args.action === "work_run") {
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
		pi.on("context", async (event, ctx) => {
			if (workMode) {
				try {
					await api({ action: "repository_work_request_guard" });
				} catch (error) {
					emit({ type: "work_request_guard_stopped", error: String(error) });
					ctx.abort();
					throw error;
				}
			}
			emit({
				type: "repository_context_observed",
				messages: event.messages.length,
				bytes: Buffer.byteLength(JSON.stringify(event.messages)),
			});
		});
	};
}
