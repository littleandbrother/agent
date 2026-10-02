import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
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

const config = JSON.parse(fs.readFileSync(process.argv[2] === "-" ? 0 : process.argv[2], "utf8"));
const cwd = path.resolve(config.workspace);
const sha = (file: string) => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const activation = {
	type: "harness_loaded",
	pid: process.pid,
	mode: config.mode,
	source: config.sourceManifest,
	loaded: { solver: sha(config.solverModule), improver: sha(config.improverModule) },
	model: "deepseek-flash",
};
console.log(JSON.stringify(activation));
const solver = await import(pathToFileURL(config.solverModule).href);
const improver = await import(pathToFileURL(config.improverModule).href);
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
const reply = (value: any) => ({ content: [{ type: "text" as const, text: JSON.stringify(value) }], details: {} });
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
const tools = [
	defineTool({
		name: "bf_experiment",
		label: "Experiment",
		description:
			"Upload immutable current design.json and policy.py, then submit one async experiment. Persist and reuse operation_id after interruption.",
		executionMode: "sequential",
		parameters: Type.Object({ operation_id: Type.String() }),
		async execute(_id, { operation_id }) {
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
			contextWindow: 32000,
			maxTokens: 4096,
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
const prompt =
	config.mode === "solve" ? solver.solverPrompt(task, state) : improver.improvementPrompt(config.improvementContext);
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
	tools: ["read", "edit", "write", "bash", ...(config.mode === "solve" ? tools.map((tool) => tool.name) : [])],
	customTools: config.mode === "solve" ? tools : [],
	sessionManager: SessionManager.inMemory(cwd),
	settingsManager: SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } }),
});
if (modelFallbackMessage) throw new Error("MODEL_FALLBACK_DENIED");
const expectedTools = [
	"read",
	"edit",
	"write",
	"bash",
	...(config.mode === "solve" ? tools.map((tool) => tool.name) : []),
];
if (expectedTools.some((name) => !session.getActiveToolNames().includes(name)))
	throw new Error("ACTIVE_TOOL_SET_INCOMPLETE");
let messages = 0;
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
	if (event.type === "message_end") {
		const message = event.message as any;
		if (message.role === "assistant") messages++;
		const safe = {
			...message,
			content: Array.isArray(message.content)
				? message.content.filter((c: any) => c.type !== "thinking")
				: message.content,
		};
		console.log(JSON.stringify({ type: "message", message: safe }));
	}
	if (event.type === "tool_execution_start")
		console.log(JSON.stringify({ type: event.type, toolName: event.toolName, args: event.args }));
});
try {
	save();
	if (!config.dryRun)
		await session.prompt(
			config.mode === "solve"
				? "Complete the task independently using the current files and real experiment service."
				: "Read the available experience and make an independently motivated source change, build/check it, and leave the candidate files.",
		);
	console.log(
		JSON.stringify({
			type: "session_complete",
			messages,
			submitted: fs.existsSync(path.join(cwd, "submission.json")),
		}),
	);
	if (!config.dryRun && config.mode === "solve" && !fs.existsSync(path.join(cwd, "submission.json")))
		throw new Error(interrupted ? "SESSION_INTERRUPTED" : "SOLVER_FINISHED_WITHOUT_SUBMISSION");
} finally {
	session.dispose();
}
