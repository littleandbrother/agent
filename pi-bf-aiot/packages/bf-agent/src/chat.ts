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
	loaded: { solver: sha(config.solverModule), improver: sha(config.improverModule) },
	model: "deepseek-flash",
};
console.log(JSON.stringify(activation));
const solver = await import(pathToFileURL(config.solverModule).href);
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
	solver.solverPrompt(task, state) +
	`\nYou are in an interactive operator conversation. Follow the user's request within the fixed task contract. Explain progress in concise public messages in the user's language, use tools when requested, and respond to follow-up messages. Do not reveal private reasoning. A user question does not itself require an experiment. A sealed submission is immutable; explain or inspect it without replacing it. Stop a turn when you have answered the request; remain available for the next message.`;
console.log(
	JSON.stringify({ type: "context_snapshot", kind: "chat", prompt, revision: config.sourceManifest.identity }),
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
	tools: ["read", "edit", "write", "bash", ...(config.mode === "solve" ? tools.map((tool) => tool.name) : [])],
	customTools: config.mode === "solve" ? tools : [],
	sessionManager,
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
const instance = crypto.randomUUID();
let _messages = 0;
let assistantId = 0;
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
		if (message.role === "assistant") _messages++;
		const safe = {
			...message,
			content: Array.isArray(message.content)
				? message.content.filter((c: any) => c.type !== "thinking")
				: message.content,
		};
		emit({ type: "message", id: `${instance}-${assistantId}`, message: safe });
	}
	if (event.type === "tool_execution_start")
		console.log(
			JSON.stringify({ type: event.type, toolName: event.toolName, toolCallId: event.toolCallId, args: event.args }),
		);
});
let running = false;
const waiting: any[] = [];
let draining: Promise<void> | null = null;
const execute = async () => {
	if (running) return;
	running = true;
	try {
		while (waiting.length) {
			const cmd = waiting.shift();
			emit({ type: "input_accepted", message_id: cmd.id });
			try {
				await session.prompt(cmd.text, { expandPromptTemplates: false });
				emit({ type: "turn_complete", submitted: fs.existsSync(path.join(cwd, "submission.json")) });
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
			await session.abort();
			break;
		}
		if (cmd.type === "stop") {
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
