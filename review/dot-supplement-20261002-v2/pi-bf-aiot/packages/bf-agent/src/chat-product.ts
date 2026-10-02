import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { pathToFileURL } from "node:url";
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
};
console.log(JSON.stringify(activation));
const solver = await import(pathToFileURL(config.solverModule).href);
const productHarness = await import(pathToFileURL(config.productModule).href);
const _improver = await import(pathToFileURL(config.improverModule).href);
let state = fs.existsSync(path.join(cwd, "state.json"))
	? JSON.parse(fs.readFileSync(path.join(cwd, "state.json"), "utf8"))
	: solver.initialState();
const save = () => fs.writeFileSync(path.join(cwd, "state.json"), JSON.stringify(state, null, 2));
const api = async (route: string, body?: unknown) => {
	const response = await fetch(config.service + route, {
		method: body === undefined ? "GET" : "POST",
		headers: { Authorization: `Bearer ${config.token}`, "Content-Type": "application/json" },
		...(body === undefined ? {} : { body: JSON.stringify(body) }),
		signal: AbortSignal.timeout(100000),
	});
	const value = (await response.json()) as any;
	if (!response.ok) throw new Error(value.error ?? "SERVICE_ERROR");
	return value;
};
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
				receipt_ref: state.budget.receipt_ref,
			}
		: undefined,
};
const reply = (value: any) => {
	const text = JSON.stringify(value);
	if (Buffer.byteLength(text) <= 24000) return { content: [{ type: "text" as const, text }], details: {} };
	const digest = crypto.createHash("sha256").update(text).digest("hex");
	const folder = path.join(cwd, "tool-records");
	if (
		fs.existsSync(folder) &&
		(fs.lstatSync(folder).isSymbolicLink() || !fs.realpathSync(folder).startsWith(fs.realpathSync(cwd) + path.sep))
	)
		throw Error("TOOL_RECORD_PATH_DENIED");
	fs.mkdirSync(folder, { recursive: true });
	const target = path.join(folder, digest + ".json");
	if (fs.existsSync(target) && (fs.lstatSync(target).isSymbolicLink() || sha(target) !== digest))
		throw Error("TOOL_RECORD_CONFLICT");
	if (!fs.existsSync(target)) fs.writeFileSync(target, text, { flag: "wx" });
	const summary = {
		record_file: path.relative(cwd, target),
		sha256: digest,
		bytes: Buffer.byteLength(text),
		instruction: "Full response saved locally; read selected fields with Python/read, do not print the entire file.",
		id: value.id,
		status: value.status,
		error: value.error,
		revision: value.revision,
		hashes: value.hashes,
		current_revision: value.current?.revision,
		source_messages: value.messages?.map((m: any) => ({ id: m.id, text: m.text })),
		checks: value.checks,
		artifacts: value.result?.artifacts,
		digital_checks_passed: value.result?.digital_checks_passed,
	};
	return { content: [{ type: "text" as const, text: JSON.stringify(summary) }], details: {} };
};
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
const simulationTask = (await api("/api/engineering/task")).binding;
if (productContext.binding) config.taskId = productContext.binding.task_id;
const tools: any[] = [
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
			"Search public papers/repositories/web, fetch and page source text, record applicability and differences. Acquisition is not reproduction or measurement. No task-specific sources are preloaded. Web search may be unavailable; failures are retained. Read skill for source and evidence rules.",
		executionMode: "sequential",
		parameters: Type.Object({
			action: Type.Union([
				Type.Literal("inspect"),
				Type.Literal("skill"),
				Type.Literal("search"),
				Type.Literal("fetch"),
				Type.Literal("read"),
				Type.Literal("adopt"),
			]),
			provider: Type.Optional(Type.Union([Type.Literal("crossref"), Type.Literal("github"), Type.Literal("web")])),
			query: Type.Optional(Type.String()),
			url: Type.Optional(Type.String()),
			reference_id: Type.Optional(Type.String()),
			offset: Type.Optional(Type.Integer({ minimum: 0 })),
			limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 16000 })),
			proposal_revision: Type.Optional(Type.Integer({ minimum: 1 })),
			application: Type.Optional(Type.String()),
			locator: Type.Optional(Type.String()),
			assumptions: Type.Optional(Type.String()),
			differences: Type.Optional(Type.String()),
			required_checks: Type.Optional(Type.String()),
		}),
		async execute(_id, args) {
			return reply(await api("/api/references", args));
		},
	}),
	defineTool({
		name: "bf_product",
		label: "Product proposal",
		description:
			"Inspect product source IDs, publish provisional proposals, edit assembly, publish files, or inspect/bind/package the engineering delivery contract. delivery_bind uses delivery_task_id, current assembly revision, published file_ids and completed job_ids; it cannot submit PASS. Unknown users receive explicit assumptions and continued exploration, not mandatory questions.",
		executionMode: "sequential",
		parameters: Type.Object({
			action: Type.Union([
				Type.Literal("inspect"),
				Type.Literal("propose"),
				Type.Literal("ask"),
				Type.Literal("bind"),
				Type.Literal("assembly_inspect"),
				Type.Literal("assembly_write"),
				Type.Literal("publish_file"),
				Type.Literal("delivery_inspect"),
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
			file_kind: Type.Optional(Type.String()),
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
		}),
		async execute(_id, args) {
			if (args.action === "delivery_inspect") return reply(briefDelivery(await api("/api/deliverables")));
			if (args.action === "delivery_package") return reply(await api("/api/deliverables", { action: "package" }));
			if (args.action === "delivery_bind")
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
						payload: JSON.parse(fs.readFileSync(value, "utf8")),
					}),
				);
			}
			if (args.action === "publish_file") {
				if (!Number.isInteger(args.revision) || !args.file_path || !args.file_kind)
					throw Error(
						"PRODUCT_FILE_ARGUMENTS_REQUIRED: publish_file requires revision (assembly_inspect.current.revision), file_path (existing workspace-relative file), and file_kind (document/source/firmware/energy/electronics). Nothing was published. Read assembly_inspect and retry with the explicit version.",
					);
				return reply(
					await api("/api/assembly", {
						action: "register",
						revision: args.revision,
						path: args.file_path,
						kind: args.file_kind,
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
			"Inspect capabilities and the bound task, read a skill, run native engineering, poll a job, download a verified artifact, or submit a final evaluated job with job_id and rationale. closed-simulation accepts parameters.candidate and confirmation; a bound task overrides the generic parameter list. Read its skill and distinguish run_status, nominal prediction, ranking eligibility and product acceptance. For product-model use parameters.assembly_revision and OMIT design_revision. Native files require action=artifact before local reading. Digital checks do not imply hardware qualification.",
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
				]),
			),
			skill_id: Type.Optional(Type.String()),
			job_id: Type.Optional(Type.String()),
			artifact_name: Type.Optional(Type.String()),
			offset: Type.Optional(Type.Integer({ minimum: 0 })),
			limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 16000 })),
			channels: Type.Optional(Type.Array(Type.String())),
			time_from: Type.Optional(Type.Number()),
			time_to: Type.Optional(Type.Number()),
			operation_id: Type.Optional(Type.String()),
			rationale: Type.Optional(Type.String()),
			design_revision: Type.Optional(Type.Number()),
			parameters: Type.Optional(Type.Record(Type.String(), Type.Unknown())), // Validated by the typed backend adapter.
		}),
		async execute(_id, args) {
			if (args.action === "inspect") {
				const value = await api("/api/engineering");
				return reply({ ...value, jobs: value.jobs?.map(briefJob) });
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
				let job = await api(`/api/engineering/jobs/${encodeURIComponent(args.job_id)}`);
				for (let i = 0; i < 40 && ["QUEUED", "RUNNING"].includes(job.status); i++) {
					await new Promise((resolve) => setTimeout(resolve, 500));
					job = await api(`/api/engineering/jobs/${encodeURIComponent(args.job_id)}`);
				}
				const energy = job.result?.energy;
				return reply({
					...job,
					assembly: job.assembly ? { revision: job.assembly.revision, hashes: job.assembly.hashes } : undefined,
					result: job.result
						? {
								...job.result,
								energy: energy
									? {
											...energy,
											scenarios: energy.scenarios
												? Object.fromEntries(
														Object.entries(energy.scenarios).map(([k, v]: [string, any]) => [
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
			}
			if (args.action === "run" && args.engine === "product-model" && args.design_revision !== undefined)
				throw Error(
					"PRODUCT_MODEL_OMIT_DESIGN_REVISION: use parameters.assembly_revision only; design_revision names the separate prose proposal, not the CAD assembly.",
				);
			const result = await api("/api/engineering", args);
			return reply(result.id ? briefJob(result) : result);
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
			reasoning: false,
			input: ["text"],
			cost: { input: 0.3, output: 1.2, cacheRead: 0.006, cacheWrite: 0.3 },
			contextWindow: 1048576,
			maxTokens: 8192,
			compat: {
				supportsDeveloperRole: false,
				supportsStore: false,
				supportsUsageInStreaming: true,
				maxTokensField: "max_tokens",
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
const basePrompt = simulationTask
	? `你正在进行固定器件家族的设计先导实验。以下任务与评价条件由后端冻结：${JSON.stringify(simulationTask)}\n先读取原生失败依据，自主提出实际设计修改并执行。只使用 bf_engineering 的 inspect/skill/run/job/artifact_view/submit。artifact_view 返回 JSON/源码的文本分页；CSV 支持 channels、time_from、time_to 和行 offset。省略候选字段采用冻结基线。每个候选使用唯一 operation_id；等待原 job 完成，不因等待重复派发。保持简短中文公开说明。候选预算用尽或得到可辩护结论时，用 submit、job_id、rationale 封存一个已运行候选；可以如实提交失败，不允许制造成功。模型内预测不代表物理合格。`
	: productHarness.productPrompt(executionInstructions, startupProduct(productContext));

const shared = config.sharedContext;
const prompt =
	basePrompt +
	(shared?.folder_id
		? `\nFolder shared context (unverified notes, not experiment facts): ${JSON.stringify({ folder: shared.folder_name, revision: shared.revision, memory: shared.memory })}\nFolder instructions: ${shared.prompt}\nUse bf_memory to read or update shared notes when available. Shared notes are not scientific verification. Enabled tools: ${shared.tools.join(", ")}.`
		: "");
const selectedTools = shared?.tools ?? ["read", "edit", "write", "bash", ...tools.map((tool) => tool.name)];
const availableTools = simulationTask ? ["bf_engineering"] : [...new Set([...selectedTools, "bf_product"])];
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
const resources: ResourceLoader = {
	getExtensions: () => ({ extensions: [], errors: [], runtime: createExtensionRuntime() }),
	getSkills: () => ({ skills: [], diagnostics: [] }),
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
	thinkingLevel: "off",
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
const originalPayload = session.agent.onPayload;
session.agent.onPayload = async (payload, model) => {
	const value = (await originalPayload?.(payload, model)) ?? payload;
	if (requireOneDeliveryAction) {
		requireOneDeliveryAction = false;
		return { ...(value as Record<string, unknown>), tool_choice: "required" };
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
				const packet = await api("/api/product-context");
				emit({ type: "product_context_snapshot", message_id: cmd.id, packet });
				await session.prompt(productHarness.contextPrompt(packet) + "\n用户消息：" + cmd.text, {
					expandPromptTemplates: false,
				});
				// Explicit operator delivery goals only. Same message/lease/cost
				// accounting: this cannot reset a paid or wall-clock budget.
				for (let n = 0; n < 12 && !closing && !userStopped && !responseError && !responseTruncated; n++) {
					const observation = (await api("/api/deliverables")).verdict;
					if (!observation) break;
					emit({ type: "delivery_observation", message_id: cmd.id, observation });
					state.deliveryContinuations ||= {};
					const used = state.deliveryContinuations[cmd.id] || 0;
					if (!productHarness.continueDelivery(observation, used)) break;
					state.deliveryContinuations[cmd.id] = used + 1;
					save();
					requireOneDeliveryAction = true;
					emit({
						type: "delivery_continuation",
						message_id: cmd.id,
						index: used + 1,
						missing: observation.missing,
						tool_choice: "required_once",
					});
					await session.prompt(
						"交付观察器的实际结果：" +
							JSON.stringify(observation) +
							"。原始执行任务仍未完成。刚才的分析、读文件或准备执行都不是交付。把尚未执行的动作直接落实为工具调用；复用自己的文件，根据已有反馈实际编辑、重跑、读回并发布。只读取下一次修改确实缺少的字段，避免反复列目录或打印完整文件。不要修改要求或检查器来通过。受原消息费用与时间预算限制。若外部阻塞则保留产物并明确报告。",
						{ expandPromptTemplates: false },
					);
				}
				if (!closing && !userStopped && !responseError && !responseTruncated) {
					const finalObservation = (await api("/api/deliverables")).verdict;
					if (finalObservation?.auto_continue && !finalObservation.passed) {
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
