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
import { repositoryExtension } from "./extensions/bf-repository.ts";

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
	purpose?: "design" | "report";
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
const declaration = await api({ action: "repository_schema" });
const declarationText = String(declaration.description);
const taskDefinition = await api({ action: "repository_task_definition" });
const taskProfile = taskDefinition.profile as { roles: string[] };
const taskMode =
	taskDefinition.definition !== null && taskDefinition.definition !== undefined && taskProfile.roles.length === 0;
const taskSchema = taskDefinition.definition ? await api({ action: "repository_task_schema" }) : null;
const taskCore = `你是 BF Design 的 Pi 设计参与者。先读取 task_definition、task_state、summary 和冻结源码，按任务意图、允许文件与验收范围开展工作。任务要求由用户确定，你负责设计选择、实验和修订。
task_schema 给出本任务的字段、报告章节和 qualified_operations。只使用当前配置开放的操作。可写的单 Agent 配置使用 task_commit 冻结完整候选，task_execute 实际执行，validate 独立检查，decide 作出设计决定，task_report 生成对应报告，release 同版交付，close 结束。只读配置消费已有工程检查并交付审查结果。每次修订解释它用于回答什么工程问题。执行器自动复用相同输入；验收要求变化时使用已有原始结果重新检查。
按需激活 bf-task-design。来源与角色分别记录：用户提供的参数也可能是可调参考，只有声明的硬约束必须固定。共享器件在 components 中只出现一次。task_state 的恢复状态与 allowed_actions 用于确认本次操作可执行；未知操作先对账，不能换 operation_id 重复执行。接口来源一致与任务性能通过分别看对应检查。模型、检查器和验收要求不属于设计修改范围。用简短中文公开判断与结果。
当前任务和场景从 task_definition 读取。
执行与交付合同：${JSON.stringify(taskSchema)}`;
const core =
	config.purpose === "report"
		? `你是 BF 的工程交付报告作者。本轮只编写绑定 System Commit 的报告，不进行工程设计、提交、仿真或采用。
先激活 bf-engineering-report 技能，读取 report_schema 和 report_read。所有事实和源码从指定 report_id 读取。Power 按 EasyEDA 方法组织实际网表和 PCB 标注，Firmware 用实际源码编写跨参与者时序，Lead 填写八页结论和交付说明。使用 report_write 提交自己的 JSON，完成后直接结束。模型不得编造尺寸、执行结果或物理测试。`
		: taskMode
			? taskCore
			: `你是 BF Design Architecture V2 的 Pi 设计参与者。唯一状态源是 bf_repository：Project、System Commit、专业任务、Domain Commit、契约、独立检查和采用决定。
先读 summary/task 与相关原生源码；区分事实、设计选择、假设。Lead 按当前任务开放的专业角色分配任务并等待真实提交；专业 Pi 只修改本任务声明的专业路径，将修改冻结为 Domain Commit 后 finish。恢复时先读取持久任务与分支，不重复已执行作业。
Lead 用明确的 Domain Commit 和 Contract 集成 System Commit，执行独立 validate，根据结果 decide，生成同版 release，再 close。方案由你判断；模型和检查器不能修改，绿色由实际检查决定。
接口事实必须来自实际源码或数据。${declarationText} 不复制策略参数为实际无线参数。read(domain_commit,path) 和 extract(system_id,domain_commits) 可读取其他专业的冻结输入。进入新系统基线时使用 rebase，reopen 只重开原基线任务。原生源码和模型改变时需执行，工具按精确输入复用成功作业。
工具只返回事实。按需加载已有 skill。用简短中文公开工程理由，结束时说明候选变化、结果、设计决定、剩余问题。
当前任务配置：${taskSchema ? JSON.stringify(taskSchema) : "原 P01 原生任务；已开放 power / firmware"}`;

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
	extensionFactories: [
		{
			name: "bf-repository-v2",
			factory: repositoryExtension(api, emit, declarationText, config.purpose === "report", taskMode),
			hidden: false,
		},
	],
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
const pointer = path.join(cwd, ".pi/repository-session-path");
fs.mkdirSync(path.dirname(pointer), { recursive: true });
const manager = fs.existsSync(pointer)
	? SessionManager.open(fs.readFileSync(pointer, "utf8"))
	: SessionManager.create(cwd, path.join(cwd, ".pi/repository-sessions"));
fs.writeFileSync(pointer, manager.getSessionFile()!);
const { session, modelFallbackMessage } = await createAgentSession({
	cwd,
	agentDir: path.join(cwd, ".pi"),
	model,
	modelRuntime: runtime,
	thinkingLevel: reasoning ? "high" : "off",
	resourceLoader: loader,
	tools: ["bf_repository"],
	sessionManager: manager,
	settingsManager: settings,
});
if (modelFallbackMessage || session.getActiveToolNames().join(",") !== "bf_repository")
	throw Error("DESIGN_TOOL_ACTIVATION_MISMATCH");
emit({
	type: "repository_controller_loaded",
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
await session.prompt(config.goal);
if (modelError) throw Error(modelError);
const final = await api({ action: "repository_state" });
emit({ type: "repository_turn_finished", state: final });
emit({ type: "chat_idle" });
input.close();
