/** One finite BF design episode. Schema and tool facts come from its frozen contract. */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import readline from "node:readline";
import {
  createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager,
} from "@earendil-works/pi-coding-agent";

interface Config {
  workspace: string; service: string; token: string; owner: string; goal: string;
  instruction: string; episodeId: string;
  tool: { name: string; description: string; parameters: any; canonical: string; sha256: string };
}
const lines = readline.createInterface({ input: process.stdin });
const config = await new Promise<Config>((resolve, reject) => lines.once("line", (line) => {
  try { resolve(JSON.parse(line) as Config); } catch (e) { reject(e); }
}));
const ordered = (v: any): any => Array.isArray(v) ? v.map(ordered) : v && typeof v === "object"
  ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, ordered(v[k])])) : v;
const hash = (v: unknown) => crypto.createHash("sha256").update(JSON.stringify(ordered(v))).digest("hex");
const toolPlain = { name: config.tool.name, description: config.tool.description, parameters: config.tool.parameters };
if (crypto.createHash("sha256").update(config.tool.canonical).digest("hex") !== config.tool.sha256 ||
    JSON.stringify(ordered(JSON.parse(config.tool.canonical))) !== JSON.stringify(ordered(toolPlain)))
  throw Error("FROZEN_TOOL_CONTRACT_DRIFT");
const emit = (v: Record<string, unknown>) => console.log(JSON.stringify({ ...v, time: Date.now() / 1000 }));
const settings = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
const core = `你是无电池系统设计者 BF Pi。依据冻结的服务、供能、初态与合法设计范围，自行检查事实、选择实验、修订并提交设备与程序。工具给出事实；独立服务验收在外部。不得改变检查器、任务或器件物理假设来通过。保留失败、未知和实际费用。当前任务修复不等于方法迁移或 RSI。公开理由简洁并引用输入与观察版本。\n${config.instruction}`;
const loader = new DefaultResourceLoader({
  cwd: config.workspace, agentDir: path.join(config.workspace, ".pi"), settingsManager: settings,
  noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true,
  noContextFiles: true, systemPrompt: core,
  extensionFactories: [{ name: "bf-phase-one-frozen-tool", hidden: false, factory: (pi) => {
    pi.registerTool({
      name: config.tool.name, label: "BF service design", description: config.tool.description,
      executionMode: "sequential", parameters: config.tool.parameters,
      async execute(_id, args) {
        const response = await fetch(`${config.service}/tool`, {
          method: "POST", headers: { Authorization: `Bearer ${config.token}`, "Content-Type": "application/json" },
          body: JSON.stringify(args),
        });
        const value = await response.json() as Record<string, unknown>;
        emit({ type: "bf_tool_fact", episode: config.episodeId, input: args, result: value, ok: response.ok });
        if (!response.ok) throw Error(String(value.error));
        return { content: [{ type: "text", text: JSON.stringify(value) }], details: {} };
      },
    });
  } }],
});
await loader.reload();
const runtime = await ModelRuntime.create({
  authPath: path.join(config.workspace, ".pi/auth.json"), modelsPath: path.join(config.workspace, ".pi/models.json"),
});
runtime.registerProvider("bf-deepseek", {
  baseUrl: `${config.service}/v1`, api: "openai-completions", apiKey: config.token,
  models: [{
    id: "deepseek-flash", name: "BF pinned DeepSeek Flash", reasoning: true, input: ["text"],
    cost: { input: 0.3, output: 1.2, cacheRead: 0.006, cacheWrite: 0.3 },
    contextWindow: 1048576, maxTokens: 32768,
    compat: {
      supportsDeveloperRole: false, supportsStore: false, supportsUsageInStreaming: true,
      maxTokensField: "max_tokens", supportsReasoningEffort: true, thinkingFormat: "deepseek",
      requiresReasoningContentOnAssistantMessages: true,
    },
  }],
});
const model = runtime.getModel("bf-deepseek", "deepseek-flash");
if (!model) throw Error("MODEL_ID_UNAVAILABLE");
const pointer = path.join(config.workspace, ".pi/phase1-session-path");
if (fs.existsSync(pointer)) throw Error("EPISODE_ALREADY_STARTED_NO_AUTOMATIC_RESAMPLING");
fs.mkdirSync(path.dirname(pointer), { recursive: true });
const manager = SessionManager.create(config.workspace, path.join(config.workspace, ".pi/phase1-sessions"));
fs.writeFileSync(pointer, manager.getSessionFile()!, { flag: "wx" });
const { session, modelFallbackMessage } = await createAgentSession({
  cwd: config.workspace, agentDir: path.join(config.workspace, ".pi"), model, modelRuntime: runtime,
  thinkingLevel: "high", resourceLoader: loader, tools: [config.tool.name],
  sessionManager: manager, settingsManager: settings,
});
if (modelFallbackMessage) throw Error("MODEL_FALLBACK_DENIED");
if (session.messages.length) throw Error("EPISODE_REQUIRES_FRESH_MESSAGES");
emit({ type: "bf_episode_loaded", episode: config.episodeId, owner: config.owner, core,
  tool_sha256: config.tool.sha256, model: model.id, thinking: "high", tools: session.getActiveToolNames(),
  resume_messages: session.messages.length, cost_scope: "SDK rate estimate; authoritative provider ledger is external" });
let error: string | undefined;
session.subscribe((event) => {
  if (event.type === "message_end" && event.message.role === "assistant") {
    emit({ type: "assistant_public", content: event.message.content.filter((c) => c.type === "text" || c.type === "toolCall") });
    if (event.message.stopReason === "error") error = event.message.errorMessage ?? "MODEL_RESPONSE_ERROR";
  }
});
process.on("SIGTERM", () => void session.abort());
await session.prompt(config.goal);
if (error) throw Error(error);
emit({ type: "bf_episode_complete", episode: config.episodeId });
lines.close();
