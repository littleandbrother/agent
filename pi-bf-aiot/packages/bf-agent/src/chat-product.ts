import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
	createAgentSession,
	createExtensionRuntime,
	defineTool,
	ModelRuntime,
	type ResourceLoader,
	SessionManager,
	SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { createBoundedBashTool } from "./bounded-bash.ts";
import { inspectCurrentContext } from "./current-context.ts";
import { assertEdaExecution } from "./eda-outcome.ts";
import { waitForEngineeringJob } from "./engineering-wait.ts";
import { bindPaperAction, finishPaperRound, paperCandidateTool } from "./paper-candidate.ts";
import { ReadProgress } from "./read-progress.ts";
import { digest as methodDigest, methodInstructions, profile as methodProfile } from "./research-method.ts";
import { loadFrozenSkills, startupSkillIds } from "./skill-resources.ts";
import { boundedToolReply } from "./tool-reply.ts";
import { workspaceTool } from "./workspace-inspect.ts";

const input = readline.createInterface({ input: process.stdin });
const commands: any[] = [];
let wake: (() => void) | undefined;
let ended = false;
input.on("line", (line) => {
	try {
		commands.push(JSON.parse(line));
		wake?.();
	} catch {
		console.log(JSON.stringify({ type: "command_error", error: "INVALID_JSON" }));
	}
});
input.on("close", () => {
	ended = true;
	wake?.();
});
async function nextCommand() {
	while (!commands.length && !ended)
		await new Promise<void>((r) => {
			wake = r;
		});
	return commands.shift();
}
const config = await nextCommand();
if (!config) throw Error("CONFIG_REQUIRED");
const reasoningEnabled = config.modelProfile?.thinking === "enabled";
const cwd = path.resolve(config.workspace);
const sha = (file: string) => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const activation = {
	type: "harness_loaded",
	pid: process.pid,
	mode: config.mode,
	source: config.sourceManifest,
	loaded: {
		solver: sha(config.solverModule),
		improver: sha(config.improverModule),
		product: sha(config.productModule),
	},
	model: "deepseek-flash",
	model_profile: config.modelProfile ?? { thinking: "disabled" },
};
console.log(JSON.stringify(activation));
const solver = await import(pathToFileURL(config.solverModule).href);
const productHarness = await import(pathToFileURL(config.productModule).href);
const _improver = await import(pathToFileURL(config.improverModule).href);
let state = fs.existsSync(path.join(cwd, "state.json"))
	? JSON.parse(fs.readFileSync(path.join(cwd, "state.json"), "utf8"))
	: solver.initialState();
const save = () => fs.writeFileSync(path.join(cwd, "state.json"), JSON.stringify(state, null, 2));
let candidateLifecycle = false;
const rawApi = async (route: string, body?: unknown, bounded = false) => {
	const response = await fetch(config.service + route, {
		method: body === undefined ? "GET" : "POST",
		headers: {
			Authorization: `Bearer ${config.token}`,
			"Content-Type": "application/json",
			...(bounded ? { "X-BF-Tool-Response": "bounded-v1" } : {}),
		},
		...(body === undefined ? {} : { body: JSON.stringify(body) }),
		signal: AbortSignal.timeout(100000),
	});
	const value = (await response.json()) as any;
	if (!response.ok) throw new Error(value.error ?? "SERVICE_ERROR");
	return value;
};
const api = async (route: string, body?: unknown, bounded = false) =>
	rawApi(route, candidateLifecycle ? await bindPaperAction(rawApi, route, body) : body, bounded);
const engineeringApi = (route: string, body?: unknown) => api(route, body, true);
const briefJob = (j: any) => ({
	...j,
	project: j.project ? { manifest: j.project.manifest, sha256: j.project_sha256 } : undefined,
	events: undefined,
	assembly: j.assembly ? { revision: j.assembly.revision, hashes: j.assembly.hashes } : undefined,
	result: j.result
		? {
				...j.result,
				energy: j.result.energy
					? {
							...j.result.energy,
							scenarios: j.result.energy.scenarios
								? Object.fromEntries(
										Object.entries(j.result.energy.scenarios).map(([k, v]: [string, any]) => [
											k,
											{ ...v, samples: undefined },
										]),
									)
								: undefined,
						}
					: undefined,
			}
		: null,
});
const briefProduct = (p: any) => ({
	...p,
	records: p.records?.slice(-3),
	engineering: p.engineering?.map(briefJob),
	assembly: p.assembly
		? {
				...p.assembly,
				revisions: p.assembly.revisions?.map((r: any) => ({
					revision: r.revision,
					hashes: r.hashes,
					source_valid: r.source_valid,
				})),
				jobs: p.assembly.jobs?.map(briefJob),
			}
		: undefined,
});
const briefDelivery = (d: any) => ({
	...d,
	contract: { ...d.contract, tasks: undefined },
	tasks: d.tasks?.map((t: any) => ({ ...t, binding: undefined })),
});
// Startup carries pointers, not an ever-growing copy of every engineering receipt.
const startupProduct = (p: any) => ({
	current: p.current,
	binding: p.binding,
	messages: p.messages?.slice(-3).map((m: any) => ({ id: m.id, text: m.text })),
	assembly: p.assembly?.current ? { revision: p.assembly.current.revision, hashes: p.assembly.current.hashes } : null,
	engineering: p.engineering?.map((j: any) => ({ id: j.id, status: j.status, engine: j.engine })),
	instruction:
		"Use bf_product inspect or assembly_inspect for current facts; full native records are in job artifacts.",
});
const promptState = {
	...state,
	budget: state.budget
		? {
				authority: state.budget.authority,
				owner: state.budget.owner,
				expires: state.budget.expires,
				remaining_experiments: state.budget.remaining_experiments,
				scope: "remaining_experiments counts bf_experiment simulations only; it does not limit EDA commands, components, file edits or library lookups. Paid requests and wall time are enforced independently by runtime.",
				receipt_ref: state.budget.receipt_ref,
			}
		: undefined,
};
const reply = (value: unknown) => boundedToolReply(cwd, value);
const files = () =>
	Object.fromEntries(
		["design.json", "policy.py"].map((name) => [name, fs.readFileSync(path.join(cwd, name), "utf8")]),
	);
const compact = (job: any) => ({
	...job,
	result: job.result ? { ...job.result, channels: undefined, policy: undefined, decisions: undefined } : null,
	events: undefined,
});
if (config.mode === "solve") {
	for (const [operation, pending] of Object.entries(state.pending) as [string, any][]) {
		const job = await api(`/api/operations/${encodeURIComponent(operation)}`);
		if (job.status === "NOT_SUBMITTED") {
			state.pending[operation] = { ...pending, status: "NOT_SUBMITTED" };
			continue;
		}
		if (job.request.snapshot_id !== pending.snapshot_id) throw new Error("RECOVERY_SNAPSHOT_MISMATCH");
		state.pending[operation] = { ...pending, job_id: job.id, status: job.status };
		if (job.result && !state.facts.some((f: any) => f.run_id === job.result.run_id))
			state = solver.observeExperiment(state, compact(job).result);
		console.log(
			JSON.stringify({
				type: "reconciled",
				operation,
				job_id: job.id,
				status: job.status,
				snapshot_id: pending.snapshot_id,
			}),
		);
	}
	state.budget = await api("/api/budget");
	state.remainingExperiments = state.budget.remaining_experiments;
	save();
}
const productContext = await api("/api/product");
const initialCandidate = (await api("/api/product-context")).candidate_lifecycle;
candidateLifecycle = Boolean(initialCandidate);
const engineeringEnabled = !config.sharedContext?.tools || config.sharedContext.tools.includes("bf_engineering");
const simulationTask = engineeringEnabled ? (await api("/api/engineering/task")).binding : null;
if (productContext.binding) config.taskId = productContext.binding.task_id;
const tools: any[] = [
	createBoundedBashTool(cwd),
	workspaceTool(cwd, reply),
	defineTool({
		name: "bf_skill",
		label: "Frozen product skills",
		description:
			"Discover, activate or deactivate versioned professional methods. Activation preserves the exact method during context compaction. Resource paths are explicit frozen files. Loading is not execution or acceptance.",
		executionMode: "sequential",
		// DeepSeek requires a function's parameter schema to have an object root.
		// The backend still validates required and permitted fields per action.
		parameters: Type.Object(
			{
				action: Type.Union([
					Type.Literal("catalog"),
					Type.Literal("activate"),
					Type.Literal("deactivate"),
					Type.Literal("resource"),
				]),
				skill_id: Type.Optional(Type.String()),
				path: Type.Optional(Type.String()),
				offset: Type.Optional(Type.Integer({ minimum: 0 })),
				limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 400 })),
			},
			{ additionalProperties: false },
		),
		async execute(_id, args) {
			return reply(await api("/api/skills", args));
		},
	}),
	defineTool({
		name: "bf_experiment",
		label: "Experiment",
		description:
			"Upload immutable current design.json and policy.py, then submit one async experiment. Persist and reuse operation_id after interruption.",
		executionMode: "sequential",
		parameters: Type.Object({ operation_id: Type.String() }),
		async execute(_id, { operation_id }) {
			const live = await api("/api/product");
			if (
				!live.binding ||
				live.binding.task_id !== config.taskId ||
				live.binding.revision !== state.productBinding?.revision
			)
				throw new Error("PRODUCT_ADAPTER_BINDING_REQUIRED");
			const uploaded = await api("/api/snapshots", { files: files() });
			if (state.pending[operation_id] && state.pending[operation_id].snapshot_id !== uploaded.snapshot_id)
				throw new Error("OPERATION_FILES_CHANGED");
			// Persist intention before dispatch. Retry only this operation with these exact files.
			state.pending[operation_id] = { snapshot_id: uploaded.snapshot_id, status: "SUBMITTING" };
			save();
			const job = await api("/api/jobs", {
				task_id: config.taskId,
				operation_id,
				snapshot_id: uploaded.snapshot_id,
			});
			state.pending[operation_id] = { snapshot_id: uploaded.snapshot_id, job_id: job.id, status: job.status };
			state.budget = await api("/api/budget");
			state.remainingExperiments = state.budget.remaining_experiments;
			save();
			return reply(compact(job));
		},
	}),
	defineTool({
		name: "bf_job",
		label: "Job",
		description:
			"Reconcile the persisted job ID; wait up to 20 seconds for a terminal state. UNKNOWN is never redispatched.",
		executionMode: "sequential",
		parameters: Type.Object({ job_id: Type.String() }),
		async execute(_id, { job_id }) {
			let job = await api(`/api/jobs/${encodeURIComponent(job_id)}`);
			for (let i = 0; i < 80 && ["QUEUED", "RUNNING"].includes(job.status); i++) {
				await new Promise((resolve) => setTimeout(resolve, 250));
				job = await api(`/api/jobs/${encodeURIComponent(job_id)}`);
			}
			for (const [op, pending] of Object.entries(state.pending) as [string, any][]) {
				if (pending.job_id === job_id) state.pending[op] = { ...pending, status: job.status };
			}
			if (job.result && !state.facts.some((f: any) => f.run_id === job.result.run_id))
				state = solver.observeExperiment(state, compact(job).result);
			state.budget = await api("/api/budget");
			state.remainingExperiments = state.budget.remaining_experiments;
			save();
			return reply({
				...compact(job),
				solver_state: {
					current: state.current,
					best_verified: state.bestVerified,
					pending: state.pending,
					budget: state.budget,
				},
			});
		},
	}),
	defineTool({
		name: "bf_inspect_run",
		label: "Inspect run",
		description: "Inspect your completed immutable run. Views contain public facts only.",
		executionMode: "sequential",
		parameters: Type.Object({
			job_id: Type.String(),
			view: Type.Union([Type.Literal("summary"), Type.Literal("decisions"), Type.Literal("energy")]),
		}),
		async execute(_id, { job_id, view }) {
			const job = await api(`/api/jobs/${encodeURIComponent(job_id)}`);
			if (!job.result) throw new Error("RUN_NOT_COMPLETE");
			return reply(
				view === "summary"
					? compact(job).result
					: view === "decisions"
						? job.result.decisions
						: job.result.energy_ledger,
			);
		},
	}),
	defineTool({
		name: "bf_submit",
		label: "Submit",
		description:
			"Seal the current files against the exact completed job snapshot. Stale files and unverified runs are rejected.",
		executionMode: "sequential",
		parameters: Type.Object({ job_id: Type.String() }),
		async execute(_id, { job_id }) {
			const uploaded = await api("/api/snapshots", { files: files() });
			const result = await api("/api/submit", { job_id, snapshot_id: uploaded.snapshot_id });
			fs.writeFileSync(path.join(cwd, "submission.json"), JSON.stringify(result, null, 2));
			return reply(result);
		},
	}),
];
tools.push(
	defineTool({
		name: "bf_reference",
		label: "Reference research",
		description:
			"Search public papers/repositories/web, fetch and page source text, record applicability and differences. materialize(reference_id,file_path) copies the exact acquired raw bytes to a workspace-relative file (headers, source, PDFs), verifies hash and refuses conflicting overwrites. Prefer it to retyping a source or network shell commands. Acquisition is not reproduction or measurement. No task-specific sources are preloaded. Web search may be unavailable; failures are retained. Read skill for source and evidence rules.",
		executionMode: "sequential",
		parameters: Type.Object({
			action: Type.Union([
				Type.Literal("inspect"),
				Type.Literal("skill"),
				Type.Literal("search"),
				Type.Literal("fetch"),
				Type.Literal("read"),
				Type.Literal("materialize"),
				Type.Literal("calculate"),
				Type.Literal("adopt"),
			]),
			provider: Type.Optional(Type.Union([Type.Literal("crossref"), Type.Literal("github"), Type.Literal("web")])),
			query: Type.Optional(Type.String()),
			url: Type.Optional(Type.String()),
			reference_id: Type.Optional(Type.String()),
			file_path: Type.Optional(Type.String()),
			offset: Type.Optional(Type.Integer({ minimum: 0 })),
			limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 16000 })),
			proposal_revision: Type.Optional(Type.Integer({ minimum: 1 })),
			application: Type.Optional(Type.String()),
			locator: Type.Optional(Type.String()),
			calculation: Type.Optional(
				Type.Object({
					kind: Type.Union([
						Type.Literal("elastic_displacement"),
						Type.Literal("capacitor_energy"),
						Type.Literal("natural_frequency"),
					]),
					inputs: Type.Record(Type.String(), Type.Number()),
					reported_value: Type.Optional(Type.Number()),
				}),
			),
			assumptions: Type.Optional(Type.String()),
			differences: Type.Optional(Type.String()),
			required_checks: Type.Optional(Type.String()),
		}),
		async execute(_id, args) {
			return reply(await api("/api/references", args));
		},
	}),
	defineTool({
		name: "bf_eda",
		label: "EasyEDA native engineering",
		description:
			"Typed local EasyEDA CLI for the bound project. inspect gives exact binding, command reference and saved receipts. Activate easyeda-agent via bf_skill; load its named reference for the operation. command needs argv (omit easyeda) and stable operation_id; paths workspace-relative. job waits without model calls. Parsed native result and complete receipt are returned; UNKNOWN requires readback.",
		executionMode: "sequential",
		parameters: Type.Object({
			action: Type.Union([
				Type.Literal("inspect"),
				Type.Literal("skill"),
				Type.Literal("command"),
				Type.Literal("job"),
			]),
			argv: Type.Optional(Type.Array(Type.String())),
			operation_id: Type.Optional(Type.String()),
			job_id: Type.Optional(Type.String()),
			path: Type.Optional(Type.String()),
			offset: Type.Optional(Type.Integer()),
			limit: Type.Optional(Type.Integer()),
			wait_for_completion: Type.Optional(Type.Boolean()),
			decision_use: Type.Optional(
				Type.String({ description: "For a meaningful native write, what judgment will this action support?" }),
			),
		}),
		async execute(_id, args, signal) {
			if (args.action === "job") {
				if (!args.job_id) throw Error("EDA_JOB_ID_REQUIRED");
				return reply(
					assertEdaExecution(
						await waitForEngineeringJob(
							() => engineeringApi("/api/eda-cli", { action: "job", job_id: args.job_id }),
							{
								wait: args.wait_for_completion !== false,
								signal,
								progress: (j) =>
									console.log(
										JSON.stringify({
											type: "eda_job_wait",
											job_id: args.job_id,
											status: j.status,
											model_calls: 0,
										}),
									),
							},
						),
					),
				);
			}
			return reply(assertEdaExecution(await engineeringApi("/api/eda-cli", args)));
		},
	}),
	defineTool({
		name: "bf_product",
		label: "Product proposal",
		description:
			"Inspect product source IDs, publish provisional proposals, edit assembly, publish files, or inspect/bind/package the engineering delivery contract. context_inspect (only action; no other fields) reads current owner-bound task, job and native receipt references during a long turn or after compaction; receipt paths/hashes are facts, not a new native read or acceptance. delivery_bind uses delivery_task_id, current assembly revision, published file_ids and completed job_ids; it cannot submit PASS. Unknown users receive explicit assumptions and continued exploration, not mandatory questions.",
		executionMode: "sequential",
		parameters: Type.Object({
			action: Type.Union([
				Type.Literal("inspect"),
				Type.Literal("context_inspect"),
				Type.Literal("propose"),
				Type.Literal("ask"),
				Type.Literal("bind"),
				Type.Literal("assembly_inspect"),
				Type.Literal("assembly_schema"),
				Type.Literal("assembly_write"),
				Type.Literal("publish_file"),
				Type.Literal("delivery_inspect"),
				Type.Literal("analysis_inspect"),
				Type.Literal("analysis_submit"),
				Type.Literal("delivery_bind"),
				Type.Literal("delivery_package"),
			]),
			delivery_task_id: Type.Optional(Type.String()),
			file_ids: Type.Optional(Type.Array(Type.String())),
			job_ids: Type.Optional(Type.Array(Type.String())),
			source_message_id: Type.Optional(Type.String()),
			assembly_path: Type.Optional(Type.String()),
			expected_revision: Type.Optional(Type.Number()),
			file_path: Type.Optional(
				Type.String({
					description:
						"Existing file path relative to this conversation workspace, such as delivery/PRODUCT.md. Create the file first; absolute paths are not accepted.",
				}),
			),
			file_kind: Type.Optional(
				Type.Union([
					Type.Literal("document"),
					Type.Literal("geometry"),
					Type.Literal("electronics"),
					Type.Literal("firmware"),
					Type.Literal("energy"),
					Type.Literal("source"),
				]),
			),
			operation_id: Type.Optional(Type.String()),
			payload: Type.Optional(
				Type.Object({
					title: Type.Optional(Type.String()),
					purpose: Type.Optional(Type.String()),
					form: Type.Optional(Type.String()),
					service: Type.Optional(Type.String()),
					installation: Type.Optional(Type.String()),
					energy: Type.Optional(Type.String()),
					assumptions: Type.Optional(Type.Array(Type.String())),
					acceptance: Type.Optional(Type.Array(Type.String())),
					limits: Type.Optional(Type.Array(Type.String())),
					question: Type.Optional(Type.String()),
					options: Type.Optional(Type.Array(Type.String())),
					reason: Type.Optional(Type.String()),
				}),
			),
			revision: Type.Optional(
				Type.Integer({
					minimum: 1,
					description:
						"Required for publish_file: assembly revision from assembly_inspect.current.revision. Required for bind: proposal revision. These are different version counters.",
				}),
			),
			task_id: Type.Optional(Type.String()),
			rationale: Type.Optional(Type.String()),
			decision_use: Type.Optional(Type.String()),
		}),
		async execute(_id, args) {
			if (args.action === "context_inspect") return reply(await inspectCurrentContext(args, api));
			if (args.action === "analysis_submit") {
				const result = await engineeringApi("/api/responsibility-review", {
					action: "submit",
					file_path: args.file_path,
				});
				if (result.submitted) {
					requireAnalysisActions = false;
					analysisSubmitted = true;
				}
				return reply(result);
			}
			if (args.action === "analysis_inspect") return reply(await engineeringApi("/api/responsibility-review", {}));
			if (args.action === "delivery_inspect") return reply(briefDelivery(await api("/api/deliverables")));
			if (args.action === "delivery_package") return reply(await api("/api/deliverables", { action: "package" }));
			if (args.action === "delivery_bind") {
				if (!args.operation_id || !args.delivery_task_id || !Number.isInteger(args.revision))
					throw Error(
						"DELIVERY_BIND_ARGUMENTS_REQUIRED: supply operation_id (stable unique id), delivery_task_id (one task id from delivery_inspect), revision (current assembly revision), file_ids and job_ids. Tasks can be bound individually. Missing arguments are not a requirement to complete every task at once. No binding was recorded.",
					);
				return reply(
					briefDelivery(
						await api("/api/deliverables", {
							action: "bind",
							operation_id: args.operation_id,
							task_id: args.delivery_task_id,
							revision: args.revision,
							files: args.file_ids ?? [],
							jobs: args.job_ids ?? [],
						}),
					),
				);
			}
			if (args.action === "assembly_schema") return reply(await api("/api/assembly/schema"));
			if (args.action === "assembly_inspect") return reply(await api("/api/assembly"));
			if (args.action === "assembly_write") {
				if (!args.assembly_path) throw Error("ASSEMBLY_PATH_REQUIRED");
				const value = path.resolve(cwd, args.assembly_path);
				if (!value.startsWith(cwd + path.sep) || !fs.realpathSync(value).startsWith(cwd + path.sep))
					throw Error("ASSEMBLY_PATH_DENIED");
				return reply(
					await api("/api/assembly", {
						action: "write",
						source_message_id: args.source_message_id,
						operation_id: args.operation_id,
						expected_revision: args.expected_revision,
						decision_use: args.decision_use,
						payload: JSON.parse(fs.readFileSync(value, "utf8")),
					}),
				);
			}
			if (args.action === "publish_file") {
				if (!Number.isInteger(args.revision) || !args.file_path || !args.file_kind)
					throw Error(
						"PRODUCT_FILE_ARGUMENTS_REQUIRED: publish_file requires revision (assembly_inspect.current.revision), file_path (existing workspace-relative file), and file_kind (document/source/firmware/energy/electronics). Nothing was published. Read assembly_inspect and retry with the explicit version.",
					);
				if (args.file_path.startsWith(".easyeda/artifacts/"))
					throw Error(
						"PRODUCT_FILE_EXPORT_LOCATION: hidden working directories are not publication paths. Copy this native EDA export to delivery/ or exports/, verify its bytes/hash are unchanged, then publish_file with that visible relative path. Do not regenerate or rename another format as a native file.",
					);
				return reply(
					await api("/api/assembly", {
						action: "register",
						revision: args.revision,
						path: args.file_path,
						kind: args.file_kind,
						operation_id:
							args.operation_id ??
							`publish-${sha(path.resolve(cwd, args.file_path)).slice(0, 32)}-${args.revision}`,
						decision_use: args.decision_use,
					}),
				);
			}
			if (args.action === "inspect") return reply(briefProduct(await api("/api/product")));
			if (args.action === "bind") {
				const bound = await api("/api/product/bind", {
					adapter: "rotary-f1",
					revision: args.revision,
					task_id: args.task_id,
					rationale: args.rationale,
				});
				if (state.productBinding?.revision !== args.revision) {
					if (state.productBinding)
						fs.writeFileSync(
							path.join(cwd, `design-before-v${args.revision}.json`),
							fs.readFileSync(path.join(cwd, "design.json")),
						);
					fs.writeFileSync(path.join(cwd, "design.json"), JSON.stringify(bound.task.baseline_design, null, 2));
					fs.writeFileSync(path.join(cwd, "task.json"), JSON.stringify(bound.task, null, 2));
					fs.writeFileSync(path.join(cwd, "policy.py"), bound.task.baseline_policy);
				}
				config.taskId = bound.binding.task_id;
				state.productBinding = bound.binding;
				save();
				return reply(bound);
			}
			return reply(
				await api("/api/product", {
					kind: args.action === "ask" ? "question" : "proposal",
					source_message_id: args.source_message_id,
					operation_id: args.operation_id,
					payload: args.payload,
				}),
			);
		},
	}),
);
tools.push(
	defineTool({
		name: "bf_engineering",
		label: "Engineering tools",
		description:
			"inspect lists current engines and input contracts. Load relevant methods via bf_skill. run(engine=engineering-project, parameters={project_path}, operation_id, decision_use) executes frozen CAD/SPICE/target firmware. job waits for the original eng-* job without model polling. artifact downloads hashed native files. artifact_view selects waveform channels/time/rows. response_view reads exact _response by response_id/response_sha256, fields or pages. submit records an evaluated job and rationale. Other engine contracts are available through inspect and their skills.",
		executionMode: "sequential",
		parameters: Type.Object({
			action: Type.Union([
				Type.Literal("inspect"),
				Type.Literal("skill"),
				Type.Literal("run"),
				Type.Literal("job"),
				Type.Literal("artifact"),
				Type.Literal("artifact_view"),
				Type.Literal("eda_probe"),
				Type.Literal("submit"),
				Type.Literal("record_revision"),
				Type.Literal("response_view"),
			]),
			engine: Type.Optional(
				Type.Union([
					Type.Literal("blender"),
					Type.Literal("comsol"),
					Type.Literal("jlceda"),
					Type.Literal("product-model"),
					Type.Literal("mcu-firmware"),
					Type.Literal("tinyml-nas"),
					Type.Literal("event-transient"),
					Type.Literal("engineering-project"),
					Type.Literal("beam-event"),
					Type.Literal("closed-simulation"),
					Type.Literal("door-system"),
					Type.Literal("door-selfpower"),
					Type.Literal("scientific-figures"),
				]),
			),
			skill_id: Type.Optional(Type.String()),
			job_id: Type.Optional(Type.String()),
			wait_for_completion: Type.Optional(
				Type.Boolean({
					description:
						"action=job defaults to waiting for a terminal native result without more model calls. Set false for a one-time status read while doing other work. Use bf_engineering for eng-* IDs, never bf_job.",
				}),
			),
			artifact_name: Type.Optional(Type.String()),
			response_id: Type.Optional(Type.String()),
			response_sha256: Type.Optional(Type.String()),
			fields: Type.Optional(Type.Array(Type.String())),
			offset: Type.Optional(Type.Integer({ minimum: 0 })),
			limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 16000 })),
			channels: Type.Optional(Type.Array(Type.String())),
			time_from: Type.Optional(Type.Number()),
			time_to: Type.Optional(Type.Number()),
			operation_id: Type.Optional(Type.String()),
			rationale: Type.Optional(Type.String()),
			decision_use: Type.Optional(Type.String()),
			before_job_id: Type.Optional(Type.String()),
			requested_kind: Type.Optional(
				Type.Union([Type.Literal("parameter_refinement"), Type.Literal("architecture_recomposition")]),
			),
			falsifier: Type.Optional(Type.String()),
			design_revision: Type.Optional(Type.Number()),
			parameters: Type.Optional(Type.Record(Type.String(), Type.Unknown())), // Validated by the typed backend adapter.
		}),
		async execute(_id, args, signal) {
			if (args.action === "record_revision" || args.action === "response_view")
				return reply(await engineeringApi("/api/engineering", args));
			if (args.action === "inspect") {
				return reply(await engineeringApi("/api/engineering"));
			}
			if (args.action === "artifact") {
				if (!/^eng-[a-f0-9]+$/.test(args.job_id || "") || !/^[A-Za-z0-9_.-]+$/.test(args.artifact_name || ""))
					throw Error("ARTIFACT_ID_REQUIRED");
				const job = await api(`/api/engineering/jobs/${args.job_id}`);
				const entry = job.result?.artifacts?.find((a: any) => a.name === args.artifact_name);
				if (!entry || entry.bytes > 80 * 1024 * 1024) throw Error("ARTIFACT_NOT_AVAILABLE");
				const dir = path.join(cwd, "engineering-artifacts", args.job_id!);
				for (const candidate of [path.dirname(dir), dir]) {
					if (
						fs.existsSync(candidate) &&
						(fs.lstatSync(candidate).isSymbolicLink() ||
							!fs.realpathSync(candidate).startsWith(fs.realpathSync(cwd) + path.sep))
					)
						throw Error("ARTIFACT_PATH_DENIED");
				}
				fs.mkdirSync(dir, { recursive: true });
				if (!fs.realpathSync(dir).startsWith(fs.realpathSync(cwd) + path.sep)) throw Error("ARTIFACT_PATH_DENIED");
				const target = path.join(dir, args.artifact_name!);
				if (fs.existsSync(target) && (fs.lstatSync(target).isSymbolicLink() || sha(target) !== entry.sha256))
					throw Error("ARTIFACT_LOCAL_CONFLICT");
				if (!fs.existsSync(target)) {
					const response = await fetch(
						config.service +
							`/api/engineering/jobs/${args.job_id}/artifact?name=${encodeURIComponent(args.artifact_name!)}`,
						{ headers: { Authorization: `Bearer ${config.token}` }, signal: AbortSignal.timeout(60000) },
					);
					if (!response.ok) throw Error("ARTIFACT_DOWNLOAD_FAILED");
					const bytes = Buffer.from(await response.arrayBuffer());
					if (
						bytes.length !== entry.bytes ||
						crypto.createHash("sha256").update(bytes).digest("hex") !== entry.sha256
					)
						throw Error("ARTIFACT_HASH_MISMATCH");
					fs.writeFileSync(target, bytes, { flag: "wx" });
				}
				return reply({ path: path.relative(cwd, target), ...entry });
			}
			if (args.action === "job") {
				if (!args.job_id) throw Error("ENGINEERING_JOB_ID_REQUIRED");
				const job = await waitForEngineeringJob(
					() => engineeringApi(`/api/engineering/jobs/${encodeURIComponent(args.job_id!)}`),
					{
						wait: args.wait_for_completion !== false,
						signal,
						progress: (j) =>
							console.log(
								JSON.stringify({
									type: "engineering_job_wait",
									job_id: args.job_id,
									status: j.status,
									model_calls: 0,
								}),
							),
					},
				);
				return reply(job);
			}
			if (args.action === "run" && args.engine === "product-model" && args.design_revision !== undefined)
				throw Error(
					"PRODUCT_MODEL_OMIT_DESIGN_REVISION: use parameters.assembly_revision only; design_revision names the separate prose proposal, not the CAD assembly.",
				);
			// Native capacity is an executor wait, not a new model decision.
			// ENGINEERING_BUSY is emitted before admission, so retrying the
			// unchanged idempotency key cannot add another candidate.
			const capacityDeadline = Date.now() + 1200000;
			let result: any;
			let waited = false;
			for (;;) {
				try {
					result = await engineeringApi("/api/engineering", args);
					break;
				} catch (error) {
					if (
						args.action !== "run" ||
						!(error instanceof Error) ||
						error.message !== "ENGINEERING_BUSY" ||
						Date.now() >= capacityDeadline
					)
						throw error;
					if (!waited)
						console.log(
							JSON.stringify({
								type: "engineering_capacity_wait",
								operation_id: args.operation_id,
								model_calls: 0,
							}),
						);
					waited = true;
					await delay(2000);
				}
			}
			if (waited)
				console.log(
					JSON.stringify({
						type: "engineering_capacity_ready",
						operation_id: args.operation_id,
						job_id: result.id,
					}),
				);
			return reply(result);
		},
	}),
);
const runtime = await ModelRuntime.create({
	authPath: path.join(cwd, ".pi/auth.json"),
	modelsPath: path.join(cwd, ".pi/models.json"),
});
runtime.registerProvider("bf-deepseek", {
	baseUrl: `${config.service}/v1`,
	api: "openai-completions",
	apiKey: config.token,
	models: [
		{
			id: "deepseek-flash",
			name: "DeepSeek V4.1 Flash",
			reasoning: reasoningEnabled,
			input: ["text"],
			cost: { input: 0.3, output: 1.2, cacheRead: 0.006, cacheWrite: 0.3 },
			contextWindow: 1048576,
			maxTokens: config.modelProfile?.max_output_tokens ?? 8192,
			compat: {
				supportsDeveloperRole: false,
				supportsStore: false,
				supportsUsageInStreaming: true,
				maxTokensField: "max_tokens",
				supportsReasoningEffort: true,
				thinkingFormat: "deepseek",
				requiresReasoningContentOnAssistantMessages: true,
			},
		},
	],
});
const model = runtime.getModel("bf-deepseek", "deepseek-flash");
if (!model) throw new Error("EXPLICIT_MODEL_UNAVAILABLE");
const task = config.mode === "solve" ? JSON.parse(fs.readFileSync(path.join(cwd, "task.json"), "utf8")) : null;
// A product without a scientific adapter must not inherit the rotary solver's
// baseline/submit workflow or its unrelated 24-request instruction.
const executionInstructions = productContext.binding
	? solver.solverPrompt(task, promptState)
	: `本会话尚未绑定科学基准，是产品工程任务。使用已启用的读写、工程与产品工具完成当前用户要求，不要运行无关的 task.json/design.json/policy.py 基准。
用户要求执行时，简短说明动作后立即调用工具；不要把“准备修改”“接下来检查”作为最终交付。复用自己已有文件，对实际失败结果做修改、重新运行和读回，直到要求完成或明确的外部阻塞。
每次原生工程任务等待终态后核对检查，不把进程成功当成设计通过。交付说明和源码须发布到当前产品版本。禁止修改检查器或放宽既定要求来制造通过。
模型费用、请求数、token 和时间以上游服务账本与实际返回为准；不得绕过或重置。当前状态摘要：${JSON.stringify(promptState)}`;
if (candidateLifecycle) tools.push(paperCandidateTool(api, reply));
const basePrompt = candidateLifecycle
	? `你是原P01的BF设计者。${initialCandidate.contract.goal}\n任务和独立验收范围以bf_design的冻结contract为准。先inspect恢复候选，原生操作通过现有工具执行，写入须说明decision_use，输入变化后freeze新候选。UNKNOWN先查询，禁止重试或绕过；旧阶段文档保留为历史。由你选择器件、策略、实验和修订。每轮依据真实结果用intent记录CONTINUE、BLOCKED或REJECT及依据/计划；adopt不等于验收。原输入未变的成功作业复用。不要将代理模型、文件门或构建通过称为整机/物理通过。`
	: simulationTask
		? `你正在进行固定器件家族的设计先导实验。以下任务与评价条件由后端冻结：${JSON.stringify(simulationTask)}\n${simulationTask.task?.engine === "door-system" ? "先用 bf_reference 搜索并获取原论文/数据表，核对电容节点、单位和模型假设，形成依据表；检索失败如实记录，不自动改变冻结条件。" : ""}先读取原生失败依据，自主提出实际设计修改并执行。使用 bf_engineering 的 inspect/skill/run/job/artifact_view/response_view/record_revision/submit。大响应的 _response 可用 response_view 分页读回，提供 response_id 和 response_sha256，沿 next_offset 继续。artifact_view 返回 JSON/源码的文本分页；CSV 支持 channels、time_from、time_to 和行 offset。省略候选字段采用冻结基线。每个候选使用唯一 operation_id；等待原 job 完成，不因等待重复派发。保持简短中文公开说明。候选预算用尽或得到可辩护结论时，用 submit、job_id、rationale 封存一个已运行候选；可以如实提交失败，不允许制造成功。模型内预测不代表物理合格。`
		: productHarness.productPrompt(executionInstructions, startupProduct(productContext));

if (simulationTask)
	console.log(
		JSON.stringify({
			type: "method_activation",
			phase: "post_import",
			pid: process.pid,
			profile: methodProfile("strong_generic"),
			method_source_sha256: config.sourceManifest.research_method?.source_sha256,
			method_build_sha256: sha(fileURLToPath(new URL("./research-method.js", import.meta.url))),
			scientific_success: false,
		}),
	);
const researchPolicy = simulationTask ? methodInstructions(methodProfile("strong_generic")) : "";
if (simulationTask) {
	const actualMethodBuild = sha(fileURLToPath(new URL("./research-method.js", import.meta.url)));
	if (config.sourceManifest.research_method?.build_sha256 !== actualMethodBuild)
		throw Error("METHOD_BUILD_BINDING_DRIFT");
	console.log(
		JSON.stringify({
			type: "method_activation",
			phase: "invoked",
			pid: process.pid,
			profile: methodProfile("strong_generic"),
			method_build_sha256: sha(fileURLToPath(new URL("./research-method.js", import.meta.url))),
			prompt_hash: methodDigest(researchPolicy),
			instruction_text: researchPolicy,
			execution_authorized: false,
			scientific_success: false,
		}),
	);
}
const shared = config.sharedContext;
const prompt =
	basePrompt +
	(researchPolicy
		? "\n" +
			researchPolicy +
			"\n实际候选终态后可用 record_revision 记录 job_id、before_job_id（首轮可省略）、requested_kind、rationale 与 falsifier；后端从真实产物计算差异。"
		: "") +
	(shared?.folder_id
		? `\nFolder shared context (unverified notes, not experiment facts): ${JSON.stringify({ folder: shared.folder_name, revision: shared.revision, memory: shared.memory })}\nFolder instructions: ${shared.prompt}\nUse bf_memory to read or update shared notes when available. Shared notes are not scientific verification. Enabled tools: ${shared.tools.join(", ")}.`
		: "");
const selectedTools = shared?.tools ?? ["read", "edit", "write", "bash", ...tools.map((tool) => tool.name)];
const availableTools = simulationTask
	? simulationTask.task?.engine === "door-system"
		? ["bf_engineering", "bf_reference"]
		: ["bf_engineering"]
	: [
			...new Set([
				...selectedTools,
				"bf_product",
				"bf_eda",
				...(candidateLifecycle ? ["bf_workspace"] : []),
				...(config.resourceRoot && selectedTools.includes("bf_engineering") ? ["bf_skill"] : []),
			]),
		];
if (shared?.folder_id)
	tools.push(
		defineTool({
			name: "bf_memory",
			label: "Shared memory",
			description:
				"Read or update the current folder shared unverified notes. Read the revision first; update with expected_revision to avoid overwriting concurrent edits.",
			executionMode: "sequential",
			parameters: Type.Object({
				action: Type.Union([Type.Literal("read"), Type.Literal("write")]),
				memory: Type.Optional(Type.String()),
				expected_revision: Type.Optional(Type.Number()),
			}),
			async execute(_id, args) {
				return reply(
					await api(
						"/api/folder-memory",
						args.action === "write"
							? { memory: args.memory, expected_revision: args.expected_revision }
							: undefined,
					),
				);
			},
		}),
	);
console.log(
	JSON.stringify({
		type: "shared_context_loaded",
		folder_id: shared?.folder_id ?? null,
		revision: shared?.revision ?? 0,
		tools: availableTools,
		prompt,
		memory: shared?.memory ?? "",
	}),
);
const pointer = path.join(cwd, ".pi/chat-session-path");
const sessionManager = fs.existsSync(pointer)
	? SessionManager.open(fs.readFileSync(pointer, "utf8"))
	: SessionManager.create(cwd, path.join(cwd, ".pi/chat-sessions"));
fs.writeFileSync(pointer, sessionManager.getSessionFile()!);
const frozenSkills =
	!simulationTask && config.resourceRoot
		? loadFrozenSkills(config.resourceRoot, config.sourceManifest.resource_manifest.sha256)
		: [];
if (frozenSkills.length && availableTools.includes("bf_skill")) {
	const catalog = await api("/api/skills", { action: "catalog" });
	const activated = startupSkillIds(frozenSkills, availableTools, [
		...catalog.active.map((x: { id: string }) => x.id),
		...(catalog.previous_active ?? []),
	]);
	for (const skill_id of activated) await api("/api/skills", { action: "activate", skill_id });
	console.log(
		JSON.stringify({
			type: "skill_catalog_loaded",
			manifest_sha256: config.sourceManifest.resource_manifest.sha256,
			ids: frozenSkills.map((skill) => skill.name),
			activated,
		}),
	);
}
const resources: ResourceLoader = {
	getExtensions: () => ({ extensions: [], errors: [], runtime: createExtensionRuntime() }),
	getSkills: () => ({ skills: frozenSkills, diagnostics: [] }),
	getPrompts: () => ({ prompts: [], diagnostics: [] }),
	getThemes: () => ({ themes: [], diagnostics: [] }),
	getAgentsFiles: () => ({ agentsFiles: [] }),
	getSystemPrompt: () => prompt,
	getSystemPromptSource: () => undefined,
	getAppendSystemPrompt: () => [],
	getAppendSystemPromptSources: () => [],
	extendResources: () => {},
	reload: async () => {},
};
const { session, modelFallbackMessage } = await createAgentSession({
	cwd,
	agentDir: path.join(cwd, ".pi"),
	model,
	modelRuntime: runtime,
	thinkingLevel: reasoningEnabled ? "high" : "off",
	resourceLoader: resources,
	tools: availableTools,
	customTools: config.mode === "solve" ? tools.filter((tool) => availableTools.includes(tool.name)) : [],
	sessionManager,
	settingsManager: SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } }),
});
if (modelFallbackMessage) throw new Error("MODEL_FALLBACK_DENIED");
const expectedTools = availableTools;
if (
	expectedTools.length !== session.getActiveToolNames().length ||
	expectedTools.some((name: string) => !session.getActiveToolNames().includes(name))
)
	throw new Error("ACTIVE_TOOL_SET_INCOMPLETE");
const instance = crypto.randomUUID();
// Only an explicit unmet delivery goal can request one action on continuation.
// Subsequent tool responses and ordinary user questions keep normal tool choice.
let requireOneDeliveryAction = false;
let requireAnalysisActions = false;
let analysisSubmitted = false;
const readProgress = new ReadProgress();
const startedReads = new Map<string, { name: string; args: Record<string, unknown> }>();
let currentFactState = JSON.stringify(
	initialCandidate
		? [
				initialCandidate.working_design,
				initialCandidate.revision,
				initialCandidate.checks,
				initialCandidate.pending_operations,
			]
		: [],
);
const originalPayload = session.agent.onPayload;
session.agent.onPayload = async (payload, model) => {
	let value = (await originalPayload?.(payload, model)) ?? payload;
	const notice = readProgress.takeNotice();
	if (notice) {
		const body = value as { messages: unknown[] };
		value = { ...body, messages: [...body.messages, { role: "system", content: notice }] };
	}
	if (requireOneDeliveryAction || requireAnalysisActions) {
		requireOneDeliveryAction = false;
		// DeepSeek thinking supports tool calls but rejects required/named choices.
		// Completion remains gated by the independent delivery observer, not by
		// a provider-incompatible request flag.
		if (!reasoningEnabled) return { ...(value as Record<string, unknown>), tool_choice: "required" };
	}
	return value;
};
let _messages = 0;
let assistantId = 0;
let responseTruncated = false;
let responseError = false;
let userStopped = false;
const emit = (value: any) => console.log(JSON.stringify({ ...value, time: Date.now() / 1000 }));
let interrupted = false;
const stop = async () => {
	if (interrupted) return;
	interrupted = true;
	await session.abort();
	for (const pending of Object.values(state.pending) as any[]) {
		if (!pending.job_id) continue;
		const job = await api(`/api/jobs/${encodeURIComponent(pending.job_id)}`);
		if (["QUEUED", "RUNNING"].includes(job.status))
			await api(`/api/jobs/${encodeURIComponent(pending.job_id)}/cancel`, {});
	}
	save();
};
process.on("SIGINT", () => {
	void stop();
});
session.subscribe((event) => {
	if (event.type === "tool_execution_start")
		startedReads.set(event.toolCallId, { name: event.toolName, args: event.args as Record<string, unknown> });
	if (event.type === "tool_execution_end") {
		const started = startedReads.get(event.toolCallId);
		if (started) {
			if (started.name === "bf_design" && started.args.action === "inspect") {
				try {
					const block = event.result.content.find((x: { type: string; text?: string }) => x.type === "text");
					if (block?.type === "text") {
						const v = JSON.parse(block.text);
						currentFactState = JSON.stringify([v.working_design, v.revision, v.checks, v.pending_operations]);
					}
				} catch {
					/* Failed reads do not create a new fact state. */
				}
			}
			if (!event.isError) readProgress.observe(started.name, started.args, event.result, currentFactState);
			startedReads.delete(event.toolCallId);
		}
	}
	if (event.type === "message_start" && (event.message as any).role === "assistant") {
		assistantId++;
		emit({ type: "assistant_start", id: `${instance}-${assistantId}` });
	}
	if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta")
		emit({ type: "text_delta", id: `${instance}-${assistantId}`, delta: event.assistantMessageEvent.delta });
	if (event.type === "tool_execution_end")
		emit({
			type: event.type,
			toolCallId: event.toolCallId,
			toolName: event.toolName,
			isError: event.isError,
			result: event.result,
		});
	if (event.type === "message_end") {
		const message = event.message as any;
		if (message.role === "assistant") {
			_messages++;
			responseTruncated = message.stopReason === "length";
			responseError = message.stopReason === "error";
		}
		const safe = {
			...message,
			content: Array.isArray(message.content)
				? message.content.filter((c: any) => c.type !== "thinking")
				: message.content,
		};
		emit({ type: "message", id: `${instance}-${assistantId}`, message: safe });
	}
	if (event.type === "tool_execution_start")
		emit({ type: event.type, toolName: event.toolName, toolCallId: event.toolCallId, args: event.args });
});
let running = false;
let closing = false;
const waiting: any[] = [];
let draining: Promise<void> | null = null;
const execute = async () => {
	if (running) return;
	running = true;
	try {
		while (waiting.length && !closing) {
			const cmd = waiting.shift();
			emit({ type: "input_accepted", message_id: cmd.id });
			try {
				responseTruncated = false;
				responseError = false;
				userStopped = false;
				analysisSubmitted = false;
				requireAnalysisActions = false;
				const packet = await api("/api/product-context");
				emit({ type: "product_context_snapshot", message_id: cmd.id, packet });
				await session.prompt(`${productHarness.contextPrompt(packet)}\n用户消息：${cmd.text}`, {
					expandPromptTemplates: false,
				});
				if (candidateLifecycle && !closing && !userStopped && !responseError && !responseTruncated) {
					const round = await finishPaperRound(api, packet.candidate_lifecycle);
					emit({ type: "candidate_round_finished", message_id: cmd.id, ...round });
				}
				// Explicit operator delivery goals only. Same message/lease/cost
				// accounting: this cannot reset a paid or wall-clock budget.
				for (
					let n = 0;
					!candidateLifecycle && n < 12 && !closing && !userStopped && !responseError && !responseTruncated;
					n++
				) {
					const observation = (await api("/api/deliverables")).verdict;
					if (!observation || analysisSubmitted) break;
					emit({ type: "delivery_observation", message_id: cmd.id, observation });
					state.deliveryContinuations ||= {};
					const used = state.deliveryContinuations[cmd.id] || 0;
					if (!productHarness.continueDelivery(observation, used)) break;
					state.deliveryContinuations[cmd.id] = used + 1;
					save();
					requireOneDeliveryAction = true;
					requireAnalysisActions = Boolean(observation.responsibility_contract_sha256);
					emit({
						type: "delivery_continuation",
						message_id: cmd.id,
						index: used + 1,
						missing: observation.missing,
						tool_choice: reasoningEnabled
							? "auto_with_delivery_observer"
							: requireAnalysisActions
								? "required_until_submission"
								: "required_once",
					});
					await session.prompt(
						"交付观察器的实际结果：" +
							JSON.stringify(observation.responsibility_review ?? observation) +
							"。原始执行任务仍未完成。刚才的分析、读文件或准备执行都不是交付。把尚未执行的动作直接落实为工具调用；复用自己的文件，根据已有反馈实际编辑、重跑、读回并发布。只读取下一次修改确实缺少的字段，避免反复列目录或打印完整文件。不要修改要求或检查器来通过。受原消息费用与时间预算限制。若外部阻塞则保留产物并明确报告。责任清单工程任务必须通过 bf_product analysis_submit file_path=报告相对路径 明确收尾；先完成实际修改再更新 analysis.json。blocked 条目需 blocker_reason 和实际失败证据文件；不可用一句计划结束。",
						{ expandPromptTemplates: false },
					);
				}
				if (!candidateLifecycle && !closing && !userStopped && !responseError && !responseTruncated) {
					const finalObservation = (await api("/api/deliverables")).verdict;
					if (!analysisSubmitted && finalObservation?.auto_continue && !finalObservation.passed) {
						emit({ type: "delivery_observation", message_id: cmd.id, observation: finalObservation });
						emit({ type: "turn_error", error: "PRODUCT_DELIVERY_INCOMPLETE", missing: finalObservation.missing });
						continue;
					}
				}
				emit(
					responseTruncated
						? { type: "turn_error", error: "MODEL_OUTPUT_TRUNCATED" }
						: { type: "turn_complete", submitted: fs.existsSync(path.join(cwd, "submission.json")) },
				);
			} catch (e) {
				emit({ type: "turn_error", error: String(e) });
			}
			save();
		}
	} finally {
		running = false;
		emit({ type: "chat_idle" });
	}
};
try {
	save();
	emit({ type: "chat_ready" });
	while (true) {
		const cmd = await nextCommand();
		if (!cmd) break;
		if (cmd.type === "close") {
			closing = true;
			waiting.length = 0;
			await stop();
			break;
		}
		if (cmd.type === "stop") {
			userStopped = true;
			await session.abort();
			emit({ type: "turn_stopped" });
			continue;
		}
		if (cmd.type !== "message" || typeof cmd.text !== "string") continue;
		if (session.isStreaming) {
			await session.steer(cmd.text);
			emit({ type: "input_accepted", message_id: cmd.id, delivery: "steer" });
		} else {
			waiting.push(cmd);
			if (!running) draining = execute();
		}
	}
	if (draining) await draining;
} finally {
	session.dispose();
	input.close();
	save();
}
