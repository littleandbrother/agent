// One persistent native Pi session. The parent owns physics, quotas and billing.
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import {pathToFileURL} from 'node:url';

const SDK = path.resolve(import.meta.dirname, '../workbench/bf-campaign-s0-20261019/pi-bf-aiot/packages/coding-agent/dist/bundle/index.js');
export function sandboxProfile(cwd, sdk = SDK) {
  const bundle = path.dirname(fs.realpathSync(sdk));
  const packageDir = path.resolve(bundle, '../..');
  const dependencies = fs.realpathSync(path.join(packageDir, '../../node_modules'));
  cwd = fs.realpathSync(cwd);
  const packages = path.resolve(dependencies, '../packages');
  const packageDirs = fs.readdirSync(packages).map(name => path.join(packages, name));
  const reads = [cwd, bundle, dependencies, ...packageDirs.map(p => path.join(p, 'dist')).filter(p => fs.existsSync(p))];
  const quote = value => JSON.stringify(path.resolve(value));
  const exceptions = reads.map(p => `(require-not (subpath ${quote(p)}))`).join(' ');
  const files = [import.meta.filename, path.join(packageDir, 'package.json'), ...packageDirs.map(p => path.join(p, 'package.json'))];
  return `(version 1)\n(allow default)\n` +
    `(deny file-read-data (require-all (subpath "/Users") ${exceptions} ` +
    `${files.map(p => `(require-not (literal ${quote(p)}))`).join(' ')}))\n` +
    `(deny file-read-data (require-all (subpath "/private/tmp") (require-not (subpath ${quote(cwd)}))))\n` +
    `(deny file-write* (require-all (require-not (subpath ${quote(cwd)})) ` +
    `(require-not (literal "/dev/null")) (require-not (literal "/dev/tty"))))\n`;
}

if (process.argv[2] === '--profile') {
  process.stdout.write(sandboxProfile(process.argv[3], process.argv[4] || SDK));
} else {
  const lines = readline.createInterface({input: process.stdin});
  const pending = new Map();
  let initial;
  const configPromise = new Promise(resolve => initial = resolve);
  lines.on('line', line => {
    const value = JSON.parse(line);
    if (initial) { initial(value); initial = null; }
    else {
      const callback = pending.get(value.id);
      if (!callback) return;
      pending.delete(value.id);
      Object.hasOwn(value, 'error') ? callback.reject(new Error(value.error || 'TOOL_ERROR')) : callback.resolve(value.result);
    }
  });
  const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
  const config = await configPromise;
  const pi = await import(pathToFileURL(config.sdk || SDK).href);
  const cwd = path.resolve(config.cwd);
  process.chdir(cwd);
  process.env.TMPDIR = path.join(cwd, '.tmp');
  process.env.PYTHONDONTWRITEBYTECODE = '1';
  fs.mkdirSync(process.env.TMPDIR, {recursive: true});
  const agentDir = path.join(cwd, '.pi');
  fs.mkdirSync(agentDir, {recursive: true});
  const runtime = await pi.ModelRuntime.create({authPath: path.join(agentDir, 'auth.json'), modelsPath: null, refreshOnCreate: false});
  const provider = 'funnel-primary';
  runtime.registerProvider(provider, {
    baseUrl: config.baseUrl, api: 'openai-completions', apiKey: 'local-metered-proxy',
    models: [{id: config.model || 'deepseek-flash', name: config.model || 'deepseek-flash',
      reasoning: true, input: ['text'], contextWindow: config.contextWindow || 1048576,
      maxTokens: config.maxTokens || 32768,
      cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0},
      compat: {thinkingFormat: 'deepseek', supportsDeveloperRole: false},
      samplingParams: {reasoning_effort: 'high', thinking: {type: 'enabled'}, max_tokens: config.maxTokens || 32768}}]
  });
  const model = runtime.getModel(provider, config.model || 'deepseek-flash');
  const resourceLoader = {
    getExtensions: () => ({extensions: [], errors: [], runtime: pi.createExtensionRuntime()}),
    getSkills: () => ({skills: [], diagnostics: []}),
    getPrompts: () => ({prompts: [], diagnostics: []}),
    getThemes: () => ({themes: [], diagnostics: []}),
    getAgentsFiles: () => ({agentsFiles: []}),
    getSystemPrompt: () => undefined,
    getSystemPromptSource: () => undefined,
    getAppendSystemPrompt: () => config.systemPrompt ? [config.systemPrompt] : [],
    getAppendSystemPromptSources: () => [], extendResources: () => {}, reload: async () => {}
  };
  let sequence = 0, session, finished = false;
  const customTools = config.schemas.map(tool => ({
    name: tool.name, label: tool.name, description: tool.description,
    promptSnippet: tool.description, parameters: tool.parameters,
    executionMode: 'sequential',
    async execute(callId, args) {
      const id = ++sequence;
      const result = await new Promise((resolve, reject) => {
        pending.set(id, {resolve, reject});
        emit({kind: 'rpc', id, callId, tool: tool.name, args});
      });
      if (tool.name === 'finish') {
        finished = true;
        setTimeout(() => session.abort(), 0);
      }
      return {content: [{type: 'text', text: JSON.stringify(result)}], details: result};
    }
  }));
  ({session} = await pi.createAgentSession({
    cwd, agentDir, modelRuntime: runtime, model, thinkingLevel: 'high', resourceLoader,
    tools: ['read', 'write', 'edit', 'bash', ...customTools.map(tool => tool.name)],
    customTools, sessionManager: pi.SessionManager.inMemory(cwd),
    settingsManager: pi.SettingsManager.inMemory({compaction: {enabled: false}, retry: {enabled: false}})
  }));
  if (config.resumeMessages) {
    const history = config.resumeMessages.filter(message => !(message.role === 'assistant' && message.stopReason === 'error'));
    if (history[0]?.role !== 'user') history.unshift({role: 'user', content: [{type: 'text', text: config.prompt}], timestamp: Date.now()});
    for (const message of history) session.sessionManager.appendMessage(message);
    session.agent.state.messages = [...session.agent.state.messages, ...history];
  }
  session.subscribe(event => {
    if (event.type === 'message_end') emit({kind: 'message', message: event.message});
    else if (event.type === 'tool_execution_start') emit({kind: 'tool_start', tool: event.toolName, callId: event.toolCallId, args: event.args});
    else if (event.type === 'tool_execution_end') emit({kind: 'tool_end', tool: event.toolName, callId: event.toolCallId, result: event.result, isError: event.isError});
  });
  emit({kind: 'ready', version: pi.VERSION, model: model.id, activeTools: session.getActiveToolNames()});
  const timeout = setTimeout(() => session.abort(), (config.wallSeconds || 1800) * 1000);
  try {
    if (config.check) {
      for (const [index, call] of (config.checkTools || []).entries()) {
        const tool = session.agent.state.tools.find(tool => tool.name === call.name);
        emit({kind: 'check', tool: call.name, result: await tool.execute(`check-${index}`, call.args)});
      }
    } else await session.prompt(config.resumeMessages ? config.resumePrompt : config.prompt);
    emit({kind: 'terminal', finished, stats: session.getSessionStats()});
  } catch (error) {
    emit({kind: 'terminal', finished, error: error.message, stats: session.getSessionStats()});
    process.exitCode = 1;
  } finally {
    clearTimeout(timeout);
    session.dispose();
    lines.close();
  }
}
