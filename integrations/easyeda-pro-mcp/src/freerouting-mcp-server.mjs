#!/usr/bin/env node
/**
 * Freerouting MCP Server (local stdio, zero-dependency)
 *
 * 把本地 Freerouting 命令行封装成一个 MCP server,让 MCP 客户端(Claude Code 主/子
 * agent)能直接以「工具调用」跑自动布线,而**不必**走官方 npx MCP 的公有云
 * (api.freerouting.app)——那条路会把板子的 .dsn 上传到第三方,与本项目「离线 /
 * 硬件安全」的取向冲突。这里全程本机、无网络、无 API key。
 *
 * 管线仍是仓库既有的、已验证的:EDA 导出 Specctra DSN → 本 server 调
 * `java -jar freerouting.jar -de in.dsn -do out.ses` → SES 回导 EDA。
 * 文件进出 EDA 由用户手动做(见 memory: user-prefers-manual-eda-file-io);
 * 本 server 只跑中间的 Freerouting。
 *
 *   ┌──────────┐  stdio JSON-RPC  ┌──────────────┐  spawn  ┌───────────────────┐
 *   │ MCP host │ ◄──────────────► │  这个 server  │ ──────► │ java -jar         │
 *   │ (agent)  │   (MCP tools)    │ (thin wrapper)│         │ freerouting-*.jar │
 *   └──────────┘                  └──────────────┘         └───────────────────┘
 *
 * 说明:
 *   - freerouting 已发布的 jar(≤2.2.4)**不含**内建 MCP server;官方 doc 里 java
 *     `--mcp_server.stdio=true` 那条(Option B)只存在于 master 源码,需自行编译。
 *     所以这里不复用官方 MCP,而是薄封装稳定的 batch CLI(`-de/-do/-mp`)。
 *   - 默认关闭遥测上报:`--usage_and_diagnostic_data.disable_analytics=true`
 *     (否则 freerouting 会往 freerouting.app 发 analytics),并 `--gui.enabled=false`
 *     以无头运行。
 *
 * stdio 约定:协议消息走 stdout(逐行 JSON,不能含内嵌换行);所有日志走 stderr。
 */

import { spawn } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, isAbsolute, resolve } from 'node:path';
import { createInterface } from 'node:readline';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ─── Config ─────────────────────────────────────────────────────────
const SERVER_NAME = 'freerouting';
const SERVER_VERSION = '0.1.0'; // 跟 package.json 走(与 eda-mcp-server 同一个包)
const JAVA = process.env.FREEROUTING_JAVA || 'java';
// batch 布线常见耗时(整板 2 pass ≈ 2 分钟);给足超时,可用 env 调
const DEFAULT_TIMEOUT_MS = Number(process.env.FREEROUTING_TIMEOUT_MS || 20 * 60 * 1000);

function log(...args) {
  process.stderr.write(`[freerouting-mcp] ${args.join(' ')}\n`);
}

// 定位 freerouting jar。
// ⛔ **本项目不分发 freerouting.jar** —— Freerouting 是 GPL-3.0,而本仓库是 Apache-2.0;
//    把 GPL 二进制打进来会给整个仓库拖进 GPL 的分发义务。⇒ **jar 由用户自备**。
//    本 server 只是 `spawn` 一个独立进程(不链接、不嵌入),所以包装器本身可以是 Apache-2.0。
// 解析顺序:FREEROUTING_JAR 环境变量 → 仓库同级 `freerouting/` 目录里版本号最大的 jar。
function resolveJar() {
  if (process.env.FREEROUTING_JAR) {
    return existsSync(process.env.FREEROUTING_JAR) ? process.env.FREEROUTING_JAR : null;
  }
  const dir = join(__dirname, '..', 'freerouting');
  if (!existsSync(dir)) return null;
  const jars = readdirSync(dir)
    .filter((f) => /^freerouting-.*\.jar$/i.test(f))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  return jars.length ? join(dir, jars[jars.length - 1]) : null;
}

// 把用户给的路径解析成绝对路径(相对路径按 server 的 cwd = 仓库根 解析)
function abs(p) {
  return isAbsolute(p) ? p : resolve(process.cwd(), p);
}

// 跑一个进程,收集 stdout/stderr + 退出码;支持 onLine 实时回调
function spawnProc(cmd, args, { timeoutMs, onLine } = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '', buf = '', timedOut = false;
    const timer = timeoutMs ? setTimeout(() => { timedOut = true; child.kill('SIGKILL'); }, timeoutMs) : null;
    const pump = (chunk) => {
      if (!onLine) return;
      buf += chunk;
      let nl;
      while ((nl = buf.indexOf('\n')) >= 0) { onLine(buf.slice(0, nl)); buf = buf.slice(nl + 1); }
    };
    child.stdout.on('data', (d) => { out += d; pump(String(d)); });
    child.stderr.on('data', (d) => { err += d; pump(String(d)); });
    child.on('close', (code) => { if (timer) clearTimeout(timer); resolve({ code, stdout: out, stderr: err, timedOut }); });
    child.on('error', (e) => { if (timer) clearTimeout(timer); resolve({ code: -1, stdout: out, stderr: String(e), timedOut }); });
  });
}

// ─── Freerouting log 解析 ───────────────────────────────────────────
// 每 pass:  "Auto-router pass #N ... score of S (U unrouted)"
// 收尾:     "session completed: started with N unrouted nets, ... final score: S (U unrouted)"
function parseRouteLog(text) {
  const lines = text.split('\n');
  const passes = [];
  let startedUnrouted = null, finalUnrouted = null, finalScore = null, duration = null, version = null;
  for (const line of lines) {
    let m;
    if ((m = /Freerouting v([\d.]+)/.exec(line))) version = m[1];
    if ((m = /pass #(\d+).*score of ([\d.]+)\s*\((\d+) unrouted\)/.exec(line))) {
      passes.push({ pass: Number(m[1]), score: Number(m[2]), unrouted: Number(m[3]) });
    }
    if ((m = /started with (\d+) unrouted nets/.exec(line))) startedUnrouted = Number(m[1]);
    if ((m = /final score:\s*([\d.]+)\s*\((\d+) unrouted\)/.exec(line))) { finalScore = Number(m[1]); finalUnrouted = Number(m[2]); }
    if ((m = /completed in ([^,]+?),\s*final score/.exec(line))) duration = m[1].trim();
  }
  if (finalUnrouted === null && passes.length) finalUnrouted = passes[passes.length - 1].unrouted;
  if (finalScore === null && passes.length) finalScore = passes[passes.length - 1].score;
  const routed = startedUnrouted != null && finalUnrouted != null ? startedUnrouted - finalUnrouted : null;
  const pct = startedUnrouted ? Math.round((routed / startedUnrouted) * 1000) / 10 : null;
  return { version, startedUnrouted, routedNets: routed, unroutedNets: finalUnrouted, completedPct: pct, finalScore, duration, passes };
}

// 数一下 SES 里布出的走线 / 过孔(粗略骨架规模)
function sesCounts(sesPath) {
  try {
    const txt = readFileSync(sesPath, 'utf8');
    const wires = (txt.match(/\(wire\b/g) || []).length;
    const vias = (txt.match(/\(via\b/g) || []).length;
    return { wires, vias, bytes: statSync(sesPath).size };
  } catch { return null; }
}

// ─── Tools ──────────────────────────────────────────────────────────
async function toolAutoroute(args) {
  const jar = resolveJar();
  if (!jar) {
    return { isError: true, text: 'freerouting jar not found. This project does NOT ship it (Freerouting is '
      + 'GPL-3.0). Download freerouting-*.jar from https://github.com/freerouting/freerouting/releases, '
      + 'then set FREEROUTING_JAR to its path (or drop it in a freerouting/ dir next to this repo\'s src/).' };
  }
  if (!args || !args.dsn) return { isError: true, text: 'Missing required parameter: dsn (path to the Specctra .dsn exported from EDA).' };
  const dsn = abs(String(args.dsn));
  if (!existsSync(dsn)) return { isError: true, text: `DSN not found: ${dsn}` };
  const ses = abs(String(args.ses || dsn.replace(/\.dsn$/i, '') + '.ses'));
  const passes = Number.isFinite(args.passes) && args.passes > 0 ? Math.floor(args.passes) : 2;

  const jargs = [
    '-Djava.awt.headless=true', '-jar', jar,
    '-de', dsn, '-do', ses, '-mp', String(passes),
    '--gui.enabled=false',
    // 离线取向:关掉往 freerouting.app 的遥测上报
    '--usage_and_diagnostic_data.disable_analytics=true',
  ];
  if (Array.isArray(args.extraArgs)) jargs.push(...args.extraArgs.map(String));

  log(`autoroute: ${dsn} -> ${ses} (mp=${passes})`);
  const { code, stdout, stderr, timedOut } = await spawnProc(JAVA, jargs, {
    timeoutMs: DEFAULT_TIMEOUT_MS,
    onLine: (l) => { if (/pass #|session completed|ERROR|Exception/.test(l)) log(l.replace(/^.*?\b(INFO|WARN|ERROR)\b\s*/, '')); },
  });
  const logText = stdout + stderr;
  if (timedOut) return { isError: true, text: `Freerouting timed out after ${DEFAULT_TIMEOUT_MS}ms. Raise FREEROUTING_TIMEOUT_MS or lower passes.\n\n${logText.slice(-1500)}` };
  if (code !== 0 || !existsSync(ses)) {
    return { isError: true, text: `Freerouting failed (exit ${code}). No SES produced.\n\n${logText.slice(-2000)}` };
  }
  const stats = parseRouteLog(logText);
  const counts = sesCounts(ses);
  const summary = {
    output: ses,
    freeroutingVersion: stats.version,
    passes,
    startedUnroutedNets: stats.startedUnrouted,
    routedNets: stats.routedNets,
    unroutedNets: stats.unroutedNets,
    completedPct: stats.completedPct,
    finalScore: stats.finalScore,
    duration: stats.duration,
    ...(counts ? { wires: counts.wires, vias: counts.vias, sesBytes: counts.bytes } : {}),
  };
  const note = stats.unroutedNets
    ? `\n\n⚠ ${stats.unroutedNets} net(s) left unrouted — raise passes or route them by hand. `
      + 'Freerouting ignores impedance / diff-pairs / length-match / reference planes; treat this as a skeleton and hand-route USB diff, RF 50Ω, and power.'
    : '';
  return { text: `Autoroute done. Import the SES back into EDA (pcb_Document.importAutoRouteSesFile).\n\n`
    + JSON.stringify(summary, null, 2) + note };
}

async function toolVersion() {
  const jar = resolveJar();
  const info = { jar: jar || null, java: JAVA, defaultTimeoutMs: DEFAULT_TIMEOUT_MS };
  if (!jar) return { isError: true, text: 'freerouting jar not found in tools/freerouting/ (or FREEROUTING_JAR). ' + JSON.stringify(info) };
  // 只打印版本再退出(freerouting 无 --version 子命令;从一次 no-op 里读版本代价高,
  // 所以直接读 jar 文件名的版本号 + 确认 java 可用)
  const m = /freerouting-([\d.]+)\.jar$/i.exec(jar);
  info.jarVersion = m ? m[1] : 'unknown';
  const jv = await spawnProc(JAVA, ['-version'], { timeoutMs: 10000 });
  const jvline = (jv.stderr || jv.stdout).split('\n')[0] || '';
  info.javaVersion = jvline.trim();
  info.javaOk = jv.code === 0;
  return { text: JSON.stringify(info, null, 2) };
}

const TOOLS = [
  {
    name: 'fr_autoroute',
    description:
      'Autoroute a PCB with local Freerouting (offline, no cloud). Input a Specctra .dsn exported from '
      + 'EasyEDA (eda.pcb_ManufactureData.getDsnFile — board outline MUST be drawn first) and get a .ses '
      + 'you import back (eda.pcb_Document.importAutoRouteSesFile). Runs headless with telemetry disabled. '
      + 'Returns routing stats (started/routed/unrouted nets, %, score, wires, vias). NOTE: Freerouting '
      + 'does NOT honor impedance, differential pairs, length-matching or reference planes — use the result '
      + 'as a skeleton and hand-route USB diff / RF 50Ω / power nets.',
    inputSchema: {
      type: 'object',
      properties: {
        dsn: { type: 'string', description: 'Path to the input Specctra .dsn (absolute, or relative to the repo root).' },
        ses: { type: 'string', description: 'Output .ses path. Defaults to the .dsn path with a .ses extension.' },
        passes: { type: 'number', description: 'Max autorouter passes (default 2). More passes = fewer unrouted nets, slower.' },
        extraArgs: { type: 'array', items: { type: 'string' }, description: 'Extra freerouting CLI args passed through verbatim (advanced).' },
      },
      required: ['dsn'],
    },
    handler: toolAutoroute,
  },
  {
    name: 'fr_version',
    description: 'Report the resolved local Freerouting jar (path + version) and the Java runtime it will use. '
      + 'Call this first to confirm the offline autorouter is installed and runnable.',
    inputSchema: { type: 'object', properties: {} },
    handler: toolVersion,
  },
];

const TOOL_MAP = new Map(TOOLS.map((t) => [t.name, t]));

// ─── MCP stdio JSON-RPC loop ────────────────────────────────────────
function send(msg) { process.stdout.write(JSON.stringify(msg) + '\n'); }
function sendResult(id, result) { send({ jsonrpc: '2.0', id, result }); }
function sendError(id, code, message) { send({ jsonrpc: '2.0', id, error: { code, message } }); }

function toolResult(payload) {
  if (typeof payload === 'string') return { content: [{ type: 'text', text: payload }] };
  return { content: [{ type: 'text', text: payload.text }], isError: !!payload.isError };
}

async function handleMessage(msg) {
  const { id, method, params } = msg;
  const isNotification = id === undefined || id === null;

  switch (method) {
    case 'initialize':
      sendResult(id, {
        protocolVersion: (params && params.protocolVersion) || '2025-06-18',
        capabilities: { tools: {} },
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
      });
      return;
    case 'notifications/initialized':
    case 'initialized':
      return;
    case 'ping':
      if (!isNotification) sendResult(id, {});
      return;
    case 'tools/list':
      sendResult(id, { tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })) });
      return;
    case 'tools/call': {
      const name = params && params.name;
      const tool = TOOL_MAP.get(name);
      if (!tool) { sendError(id, -32602, `Unknown tool: ${name}`); return; }
      try {
        const out = await tool.handler((params && params.arguments) || {});
        sendResult(id, toolResult(out));
      } catch (err) {
        sendResult(id, toolResult({ isError: true, text: `Tool "${name}" error: ${err && err.message ? err.message : String(err)}` }));
      }
      return;
    }
    default:
      if (!isNotification) sendError(id, -32601, `Method not found: ${method}`);
      return;
  }
}

function main() {
  log(`starting (jar=${resolveJar() || 'NOT FOUND'}, java=${JAVA})`);
  const rl = createInterface({ input: process.stdin });
  rl.on('line', (line) => {
    const s = line.trim();
    if (!s) return;
    let msg;
    try { msg = JSON.parse(s); } catch { log(`ignoring non-JSON line: ${s.slice(0, 120)}`); return; }
    handleMessage(msg).catch((e) => log(`handler crash: ${e && e.stack ? e.stack : e}`));
  });
  rl.on('close', () => process.exit(0));
}

main();
