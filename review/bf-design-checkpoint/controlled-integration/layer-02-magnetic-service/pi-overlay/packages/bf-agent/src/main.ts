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
const packet = config.executionPacket;
if (!packet || packet.scope !== "trusted-offline-protocol-probe" || packet.execution_authorized !== false || config.dryRun !== true)
    throw new Error("EXPLICIT_OFFLINE_EXECUTION_PACKET_REQUIRED");
const ordered = (value: unknown): unknown => Array.isArray(value) ? value.map(ordered)
    : value && typeof value === "object"
        ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, ordered((value as Record<string, unknown>)[key])]))
        : value;
const packetBody = {...packet};
delete packetBody.packet_id;
if (crypto.createHash("sha256").update(JSON.stringify(ordered(packetBody))).digest("hex") !== packet.packet_id)
    throw new Error("EXECUTION_PACKET_CONTENT_HASH_MISMATCH");
const profile = packet.runtime_profile;
if (!profile || profile.provenance !== "fictional-offline-SDK-initialization-only" ||
    profile.budget.model_calls !== 0 || profile.budget.solver_calls !== 0 ||
    profile.budget.money !== 0 || packet.task_id !== config.taskId)
    throw new Error("OFFLINE_PACKET_CANNOT_AUTHORIZE_EXECUTION");

const sha = (file: string) => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");

// Controlled activation evidence is emitted only after actual import/call.
// A trusted supervisor binds the fresh process, nonce, exit status and trace.
const binding = config.controlledActivation;
if (!binding || config.dryRun !== true || !["solve", "improve"].includes(config.mode))
    throw new Error("CONTROLLED_OVERLAY_TRUSTED_DRY_RUN_ONLY");
if (binding.harnessSourceHash !== config.sourceManifest.source_hash ||
    binding.appBuildHash !== sha(process.argv[1]) ||
    binding.loaded.solver !== sha(config.solverModule) ||
    binding.loaded.improver !== sha(config.improverModule))
    throw new Error("CONTROLLED_ACTIVATION_IDENTITY_MISMATCH");
const evidence = (phase: string, entrypoint: string, output: unknown = null) => {
    console.log(JSON.stringify({type: "controlled_activation", phase, entrypoint,
        nonce: binding.nonce, pid: process.pid, mode: config.mode,
        harness_source_hash: binding.harnessSourceHash, loaded: binding.loaded,
        app_build_hash: binding.appBuildHash, binding_hash: binding.bindingHash,
        output: phase === "invoked" ? output : null,
        output_hash: phase === "invoked"
            ? crypto.createHash("sha256").update(JSON.stringify(output)).digest("hex") : null}));
};
const invoke = <T>(entrypoint: string, call: () => T): T => {
    const result = call();
    evidence("invoked", entrypoint, result);
    return result;
};

const activation = {
	type: "harness_loaded",
	pid: process.pid,
	mode: config.mode,
	source: config.sourceManifest,
	loaded: { solver: sha(config.solverModule), improver: sha(config.improverModule) },
	model: profile.model.model_id,
};
console.log(JSON.stringify(activation));
const solver = await import(pathToFileURL(config.solverModule).href);
evidence("post_import", "solver");
const improver = await import(pathToFileURL(config.improverModule).href);
evidence("post_import", "improver");
let state = fs.existsSync(path.join(cwd, "state.json"))
	? JSON.parse(fs.readFileSync(path.join(cwd, "state.json"), "utf8"))
	: invoke("solver.initialState", () => solver.initialState(profile.budget));
const save = () => fs.writeFileSync(path.join(cwd, "state.json"), JSON.stringify(state, null, 2));
const api = async (route: string, body?: unknown) => {
	const response = await fetch(config.service + route, {
		method: body === undefined ? "GET" : "POST",
		headers: { Authorization: "Bearer " + config.token, "Content-Type": "application/json" },
		...(body === undefined ? {} : { body: JSON.stringify({ ...(body as Record<string, unknown>), execution_packet_id: packet.packet_id }) }),
		signal: AbortSignal.timeout(100000),
	});
	const value = (await response.json()) as any;
	if (!response.ok) throw new Error(value.error ?? "SERVICE_ERROR");
	return value;
};
const reply = (value: any) => ({ content: [{ type: "text" as const, text: JSON.stringify(value) }], details: {} });
const files = () =>
	Object.fromEntries(
		["candidate.json"].map((name) => [name, fs.readFileSync(path.join(cwd, name), "utf8")]),
	);
const compact = (job: any) => ({
	...job,
	result: job.result ? { ...job.result, channels: undefined, policy: undefined, decisions: undefined } : null,
	events: undefined,
});
if (config.mode === "solve") {
	for (const [operation, pending] of Object.entries(state.pending) as [string, any][]) {
		const job = await api("/api/operations/" + encodeURIComponent(operation));
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
	if (state.budget.execution_packet_id !== packet.packet_id || JSON.stringify(ordered(state.budget.budget)) !== JSON.stringify(ordered(profile.budget))) throw new Error("SERVICE_BUDGET_PACKET_MISMATCH");
	state.remainingExperiments = state.budget.remaining_experiments;
	save();
}
const experiment = async (operation_id: string) => {
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
};
const experimentTool = defineTool({
		name: "bf_experiment",
		label: "Experiment",
		description:
			"Upload immutable candidate.json under the registered canonical magnetic schema, then request preflight. Missing native identity or qualification returns BLOCKED, never a completed experiment. Reuse operation_id after interruption.",
		executionMode: "sequential",
		parameters: Type.Object({ operation_id: Type.String() }),
		async execute(_id, { operation_id }) { return experiment(operation_id);
		},
	});
const tools = [experimentTool,
	defineTool({
		name: "bf_job",
		label: "Job",
		description:
			"Reconcile the persisted job ID; wait up to 20 seconds for a terminal state. UNKNOWN is never redispatched.",
		executionMode: "sequential",
		parameters: Type.Object({ job_id: Type.String() }),
		async execute(_id, { job_id }) {
			let job = await api("/api/jobs/" + encodeURIComponent(job_id));
			for (let i = 0; i < 80 && ["QUEUED", "RUNNING"].includes(job.status); i++) {
				await new Promise((resolve) => setTimeout(resolve, 250));
				job = await api("/api/jobs/" + encodeURIComponent(job_id));
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
			const job = await api("/api/jobs/" + encodeURIComponent(job_id));
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
console.log(JSON.stringify({type:"controlled_runtime_configuration", packet_id:packet.packet_id,
    model:profile.model, budget:profile.budget, autonomous_participant:false}));
runtime.registerProvider(profile.model.provider, {
    baseUrl: config.service + "/v1", api: "openai-completions", apiKey: config.token,
    models: [{ id: profile.model.model_id, name: profile.model.revision,
        reasoning: profile.model.reasoning, input: ["text"], cost: profile.model.cost,
        contextWindow: profile.model.context_tokens, maxTokens: profile.model.max_output_tokens,
        compat: {supportsDeveloperRole:false,supportsStore:false,supportsUsageInStreaming:true,maxTokensField:"max_tokens"} }],
});
const model = runtime.getModel(profile.model.provider, profile.model.model_id);
if (!model) throw new Error("EXPLICIT_MODEL_UNAVAILABLE");
const task = config.mode === "solve" ? await api("/api/tasks/" + encodeURIComponent(config.taskId)) : null;
if (task && (task.execution_packet_id !== packet.packet_id || task.binding.task_contract_hash !== packet.task_contract_hash))
    throw new Error("SERVICE_TASK_PACKET_MISMATCH");
if (task && JSON.stringify(ordered(task.execution_contract.runtime_profile)) !== JSON.stringify(ordered(profile)))
    throw new Error("SERVICE_RUNTIME_PROFILE_MISMATCH");
if (task) {
    fs.writeFileSync(path.join(cwd,"task.json"), JSON.stringify(task,null,2));
    console.log(JSON.stringify({type:"controlled_task_bound", task_id:task.task_id, binding:task.binding,
        packet_id:packet.packet_id, source:"actual-registry-service-read"}));
}
const prompt =
	config.mode === "solve" ? invoke("solver.solverPrompt", () => solver.solverPrompt(task, state))
    : invoke("improver.improvementPrompt", () => improver.improvementPrompt(config.improvementContext));
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
		const job = await api("/api/jobs/" + encodeURIComponent(pending.job_id));
		if (["QUEUED", "RUNNING"].includes(job.status))
			await api("/api/jobs/" + encodeURIComponent(pending.job_id) + "/cancel", {});
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
	if (config.trustedControllerProbe === true) {
        if (config.mode !== "solve") throw new Error("TRUSTED_PROBE_REQUIRES_SOLVE_MODE");
        const args = {operation_id:"trusted-controller-probe-1"};
        const registeredTool = session.getToolDefinition("bf_experiment");
        if (!registeredTool) throw new Error("REGISTERED_EXPERIMENT_TOOL_MISSING");
        const result = await registeredTool.execute("trusted-controller-probe", args, undefined, undefined, session.extensionRunner.createContext());
        console.log(JSON.stringify({type:"trusted_controller_probe", autonomous_participant:false,
            tool_name:registeredTool.name, arguments:args, packet_id:packet.packet_id, result}));
    }
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
