// Real Pi session; Python owns the existing tasks and physical tools.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import readline from 'node:readline';
import {spawn, spawnSync} from 'node:child_process';
import {parseArgs} from 'node:util';
import {pathToFileURL} from 'node:url';

const {values: a} = parseArgs({options: {
  task: {type: 'string'}, condition: {type: 'string'}, half: {type: 'string', default: '0'},
  model: {type: 'string'}, provider: {type: 'string'}, budget: {type: 'string', default: '6'},
  'max-cost': {type: 'string'},
  out: {type: 'string'}, requests: {type: 'string', default: '12'}, wall: {type: 'string', default: '900'},
  thinking: {type: 'string', default: 'high'}, check: {type: 'boolean'},
  list: {type: 'boolean'}, help: {type: 'boolean'}
}});
if (a.help || (!a.list && !a.task)) {
  console.log(`node wakeup/formal/pi.mjs --list
node wakeup/formal/pi.mjs --task E1-01 --condition F0 --check --out /tmp/pi-check
node wakeup/formal/pi.mjs --task E1-01 --condition F0 --provider PROVIDER --model MODEL --max-cost 5 --out runs/e1

Uses the installed @earendil-works/pi-coding-agent (or PI_SDK=/path/to/index.js),
normal Pi authentication, and PYTHON=python3. --check never requests a model.
Options: --half 0|1 --budget 6 --requests 12 --wall 900 --thinking high.
--max-cost is the SDK fee estimate checked after each response, not a prepaid limit.`);
  process.exit(a.help ? 0 : 1);
}
const hostFile = path.join(import.meta.dirname, 'agent_tools.py');
const python = process.env.PYTHON || 'python3';
if (a.list) {
  const result = spawnSync(python, ['-B', hostFile, '--list'], {stdio: 'inherit'});
  process.exit(result.status ?? 1);
}
if (!a.check && (!a.provider || !a.model || !(Number(a['max-cost']) > 0))) throw new Error('Set --provider, --model and --max-cost USD before a model run');
if (a.model && !a.provider) throw new Error('--model requires --provider');
const pi = await import(process.env.PI_SDK ? pathToFileURL(path.resolve(process.env.PI_SDK)).href : '@earendil-works/pi-coding-agent');
const output = path.resolve(a.out || path.join('runs', `${a.task}-${a.condition}-${Date.now()}`));
fs.mkdirSync(output, {recursive: true});
const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'bf-pi-'));
const hostArgs = ['-B', hostFile, '--task', a.task, '--half', a.half, '--budget', a.budget];
if (a.condition) hostArgs.push('--condition', a.condition);
const host = spawn(python, hostArgs, {stdio: ['pipe', 'pipe', 'inherit'], env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}});
const lines = readline.createInterface({input: host.stdout});
let receiveReady, rejectReady, sequence = 0;
const readyPromise = new Promise((resolve, reject) => { receiveReady = resolve; rejectReady = reject; }), pending = new Map();
lines.on('line', line => {
  const value = JSON.parse(line);
  if (value.kind === 'ready') receiveReady(value);
  else {
    const call = pending.get(value.id);
    pending.delete(value.id);
    value.error ? call.reject(new Error(value.error)) : call.resolve(value.result);
  }
});
host.on('exit', code => {
  const error = new Error(`Physical tool host exited (${code})`);
  rejectReady(error);
  for (const call of pending.values()) call.reject(error);
});
host.on('error', rejectReady);
const rpc = (tool, args = {}) => new Promise((resolve, reject) => {
  const id = ++sequence;
  pending.set(id, {resolve, reject});
  host.stdin.write(JSON.stringify({id, tool, args}) + '\n');
});
let session, timer, finalResult = null, responseCount = 0, stopReason = 'completed_without_finish';
try {
  const ready = await readyPromise;
  const task = {task: ready.public_task, initial_feedback: ready.initial, evaluation_budget: Number(a.budget),
    evaluations_remaining: ready.evaluations_remaining};
  fs.writeFileSync(path.join(cwd, 'task.json'), JSON.stringify(task, null, 2));
  if (ready.nominal_source) fs.writeFileSync(path.join(cwd, 'nominal.py'), ready.nominal_source);
  fs.writeFileSync(path.join(output, 'task.json'), JSON.stringify(task, null, 2));
  const runtime = await pi.ModelRuntime.create({refreshOnCreate: false});
  const model = a.model ? runtime.getModel(a.provider, a.model) : undefined;
  if (a.model && !model) throw new Error(`Model not configured: ${a.provider}/${a.model}`);
  const nativeBash = pi.createBashTool(cwd);
  const tools = ready.tools.map(tool => ({...tool, label: tool.name, executionMode: 'sequential',
    async execute(_id, args) {
      const result = await rpc(tool.name, args);
      if (tool.name === 'finish') { finalResult = result; stopReason = 'finish'; setTimeout(() => session.abort(), 0); }
      return {content: [{type: 'text', text: JSON.stringify(result)}], details: result};
    }
  }));
  tools.push({...nativeBash, label: 'bash',
    execute(id, args, signal, update) {
      return nativeBash.execute(id, {...args, timeout: Math.min(args.timeout ?? 30, 30)}, signal, update);
    }
  });
  const settings = pi.SettingsManager.inMemory({compaction: {enabled: false}, retry: {enabled: false}});
  const resources = new pi.DefaultResourceLoader({cwd, agentDir: pi.getAgentDir(), settingsManager: settings,
    noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
    systemPrompt: '', appendSystemPrompt: ['Solve the physical design task in task.json. Only evaluate measures the actual device. Respect the declared domain and evaluation budget. You may write code and use nominal.py when present. Call finish with your final evaluated design or infeasibility/uncertainty judgment.']});
  await resources.reload();
  ({session} = await pi.createAgentSession({cwd, modelRuntime: runtime, model, thinkingLevel: a.thinking,
    tools: ['read', 'write', 'edit', 'bash', ...ready.tools.map(tool => tool.name)], customTools: tools,
    resourceLoader: resources, settingsManager: settings,
    sessionManager: pi.SessionManager.create(cwd, path.join(output, 'session'))}));
  session.subscribe(event => {
    if (event.type !== 'message_end' || event.message.role !== 'assistant') return;
    responseCount++;
    if (!event.message.usage || event.message.stopReason === 'error') stopReason = 'model_error_or_missing_usage';
    else if (session.getSessionStats().cost >= Number(a['max-cost'])) stopReason = 'cost_limit';
    else if (responseCount >= Number(a.requests)) stopReason = 'request_limit';
    else return;
    setTimeout(() => session.abort(), 0);
  });
  console.log(JSON.stringify({sdk: pi.VERSION, model: session.model?.id, tools: session.getActiveToolNames(), output}));
  if (a.check) {
    stopReason = 'check';
    const checkTools = session.agent.state.tools;
    const invoke = (name, args) => checkTools.find(tool => tool.name === name).execute(`check-${name}`, args);
    await invoke('write', {path: 'check.txt', content: 'before'});
    await invoke('edit', {path: 'check.txt', edits: [{oldText: 'before', newText: 'after'}]});
    const read = await invoke('read', {path: 'check.txt'});
    const bash = await invoke('bash', {command: "printf 'native-bash'"});
    const publicTask = await invoke('task', {});
    let invalidRejected = false;
    try { await invoke('evaluate', {patch: {'firmware.sample_count': 1}}); }
    catch { invalidRejected = true; }
    finalResult = {check: true, provider_requests: 0, read, bash, task: publicTask.details, invalid_patch_rejected: invalidRejected};
    if (!invalidRejected) throw new Error('Domain check accepted a fixed-field edit');
  } else {
    timer = setTimeout(() => { stopReason = 'wall_limit'; session.abort(); }, Number(a.wall) * 1000);
    await session.prompt('Read task.json, investigate with the available tools, and solve the task.');
  }
} finally {
  clearTimeout(timer);
  if (session) {
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify({task: a.task, condition: a.condition,
      half: Number(a.half), stop_reason: stopReason, final: finalResult, stats: session.getSessionStats()}, null, 2));
    session.dispose();
  }
  lines.close(); host.kill(); fs.rmSync(cwd, {recursive: true, force: true});
}
