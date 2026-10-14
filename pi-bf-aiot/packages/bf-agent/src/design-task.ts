import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import {
	createAgentSession,
	DefaultResourceLoader,
	ModelRuntime,
	SessionManager,
	SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { designExtension } from "./extensions/bf-design.ts";

interface Config {
	workspace: string;
	service: string;
	token: string;
	owner: string;
	goal: string;
	messageId: string;
	harnessIdentity: string;
	modelProfile: {
		thinking: "enabled" | "disabled";
		max_output_tokens: number;
		reasoning_effort: string | null;
		version: string;
	};
	dryRun?: boolean;
}

const input = readline.createInterface({ input: process.stdin });
const config = await new Promise<Config>((resolve, reject) => {
	input.once("line", (line) => {
		try {
			resolve(JSON.parse(line) as Config);
		} catch (error) {
			reject(error);
		}
	});
});
const emit = (value: Record<string, unknown>) => console.log(JSON.stringify({ ...value, time: Date.now() / 1000 }));
const api = async (body: Record<string, unknown>): Promise<Record<string, unknown>> => {
	const response = await fetch(`${config.service}/api/design-lab`, {
		method: "POST",
		headers: { Authorization: `Bearer ${config.token}`, "Content-Type": "application/json" },
		body: JSON.stringify(body),
		signal: AbortSignal.timeout(100000),
	});
	const value = (await response.json()) as Record<string, unknown>;
	if (!response.ok) throw Error(String(value.error ?? "DESIGN_SERVICE_ERROR"));
	return value;
};
const core = `你是 BF Agent Design，本任务由你负责设计决策与工程修订。先核对冻结合同、当前设计和已有作业；自行选择观察、实验与修改，使用事实判断结果。专业方法可按需读 skill。
你的计划与下一运行意图持久保存在任务中。CONTINUE 表示继续行动，WAIT 必须指向真实作业，无法推进时记录 BLOCKED。等待真实作业不重新派发。提交前明确采用一个实际执行过的设计，用同版独立检查和交付回执支持结论。
按合同的有限支持空间工作；先用 environment 核对模型、初始化、接口和适用域，再自行选择合同允许的设计修改。新阶段可修改 C/H，以及合同允许时的 device.json 电路参数；原生模型超域或缺少必要联合结果时记录 UNEVALUABLE。不修改冻结检查器、条件、技能或费用记录。工程结果、外部介入、物理未知与方法收益分别说明。简短中文公开理由，无需输出隐藏思维。`;
const cwd = path.resolve(config.workspace);
const reasoning = config.modelProfile.thinking === "enabled";
const settings = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
const loader = new DefaultResourceLoader({
	cwd,
	agentDir: path.join(cwd, ".pi"),
	settingsManager: settings,
	noExtensions: true,
	noSkills: true,
	noPromptTemplates: true,
	noThemes: true,
	noContextFiles: true,
	systemPrompt: core,
	extensionFactories: [{ name: "bf-design-v1", factory: designExtension(api, emit), hidden: false }],
});
await loader.reload();
const extensions = loader.getExtensions();
if (extensions.errors.length || extensions.extensions.length !== 1) throw Error("DESIGN_EXTENSION_LOAD_FAILED");
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
			reasoning,
			input: ["text"],
			cost: { input: 0.3, output: 1.2, cacheRead: 0.006, cacheWrite: 0.3 },
			contextWindow: 1048576,
			maxTokens: config.modelProfile.max_output_tokens,
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
if (!model) throw Error("EXPLICIT_MODEL_UNAVAILABLE");
const pointer = path.join(cwd, ".pi/design-session-path");
fs.mkdirSync(path.dirname(pointer), { recursive: true });
const manager = fs.existsSync(pointer)
	? SessionManager.open(fs.readFileSync(pointer, "utf8"))
	: SessionManager.create(cwd, path.join(cwd, ".pi/design-sessions"));
fs.writeFileSync(pointer, manager.getSessionFile()!);
const { session, modelFallbackMessage } = await createAgentSession({
	cwd,
	agentDir: path.join(cwd, ".pi"),
	model,
	modelRuntime: runtime,
	thinkingLevel: reasoning ? "high" : "off",
	resourceLoader: loader,
	tools: ["bf_design"],
	sessionManager: manager,
	settingsManager: settings,
});
if (modelFallbackMessage || session.getActiveToolNames().join(",") !== "bf_design")
	throw Error("DESIGN_TOOL_ACTIVATION_MISMATCH");
emit({
	type: "design_controller_loaded",
	owner: config.owner,
	harness_id: config.harnessIdentity,
	controller: "pi-native-loop",
	extension_count: extensions.extensions.length,
	tools: session.getActiveToolNames(),
	model: model.id,
	model_profile: config.modelProfile,
	prompt_sha256: crypto.createHash("sha256").update(core).digest("hex"),
	prompt: core,
	context_projector: "provider-only",
	resume_session: manager.getSessionFile(),
	resume_message_count: session.messages.length,
});
if (config.dryRun) {
	emit({ type: "dry_run_complete", paid_calls: 0 });
	input.close();
	process.exit(0);
}
const instance = crypto.randomUUID();
let assistant = 0;
let modelError: string | undefined;
session.subscribe((event) => {
	if (event.type === "message_start" && event.message.role === "assistant") {
		assistant++;
		emit({ type: "assistant_start", id: `${instance}-${assistant}` });
	}
	if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta")
		emit({ type: "text_delta", id: `${instance}-${assistant}`, delta: event.assistantMessageEvent.delta });
	if (event.type === "tool_execution_end")
		emit({ type: event.type, toolName: event.toolName, result: event.result, isError: event.isError });
	if (event.type === "message_end") {
		emit({ type: "message", message: event.message });
		if (event.message.role === "assistant" && event.message.stopReason === "error")
			modelError = event.message.errorMessage ?? "MODEL_RESPONSE_ERROR";
	}
});
process.on("SIGTERM", () => void session.abort());
process.on("SIGINT", () => void session.abort());
input.on("line", (line) => {
	if (line.includes('"close"')) void session.abort();
});
emit({ type: "input_accepted", message_id: config.messageId });
let goal = config.goal;
let previous: string | undefined;
while (true) {
	await session.prompt(goal);
	if (modelError) throw Error(modelError);
	const view = await api({ action: "inspect" });
	if (view.status === "SUBMITTED") {
		emit({ type: "design_task_complete", submission: view.submission });
		break;
	}
	const intent = view.intent as { kind: string; job_id?: string };
	if (intent.kind === "BLOCKED") {
		emit({ type: "design_task_blocked", view });
		break;
	}
	const fingerprint = JSON.stringify({
		design: view.current_design,
		revision: view.revision,
		operations: view.operations,
		plan: view.plan,
		intent: view.intent,
	});
	if (fingerprint === previous) {
		await api({
			action: "intent",
			kind: "BLOCKED",
			plan: ["No durable design/action progress across settled Agent turns; preserve evidence for review."],
		});
		emit({ type: "design_no_progress", view });
		break;
	}
	previous = fingerprint;
	if (intent.kind === "WAIT" && intent.job_id) {
		let job = await api({ action: "job", job_id: intent.job_id });
		while (job.status === "QUEUED" || job.status === "RUNNING") {
			await new Promise<void>((resolve) => setTimeout(resolve, 1000));
			job = await api({ action: "job", job_id: intent.job_id });
		}
		if (job.status === "UNKNOWN") break;
	}
	// Transport only publishes durable facts. It never picks a design or repair.
	goal = `Task event/state facts: ${JSON.stringify(await api({ action: "inspect" }))}`;
}
emit({ type: "chat_idle" });
input.close();
