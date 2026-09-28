/**
 * bridge-client.mjs — 连 EasyEDA bridge 的**唯一一份**客户端底座。
 *
 * 为什么存在:在这之前几个脚本与 MCP server **各自抄了一份**
 * `health()` + `findBridge()` + `execute()` + 端口范围常数。
 * 2026-08-05 给它们加「指定目标窗口」这一个特性,就改了 5 遍同样的代码 —— 这个模块把那份代码收成一处。
 *
 * 约束:
 *   - **零外部依赖**(只用 node 内置)。裸脚本要能 `node xxx.mjs` 直接跑,不能要求先 npm install。
 *   - 只做「传输」:找桥、发 HTTP、把 `{success,result,error,stack}` 拆开。
 *     **不碰 EDA 语义**(什么是页、什么是板、怎么截图)—— 那些留在各自的脚本里。
 *
 * 端口:bridge 在 49620–49629 之间自选,所以这里扫一遍。`findBridge()` 每次都重扫,
 * 不做缓存 —— 裸脚本是一次性进程,缓存没意义;常驻进程(MCP)自己在上层缓存。
 */
import { request as httpRequest, get as httpGet } from 'node:http';

export const PORT_START = 49620;
export const PORT_END = 49629;
export const SERVICE_ID = 'easyeda-bridge';
export const HOST = '127.0.0.1';

/** GET 一个 JSON 端点。任何失败(连不上/超时/不是 JSON)一律 resolve(null) —— 探测用,不该抛。 */
export function httpGetJson(port, path, timeoutMs = 3000) {
  return new Promise((resolve) => {
    const req = httpGet({ host: HOST, port, path, timeout: timeoutMs }, (res) => {
      let body = '';
      res.on('data', (c) => (body += c));
      res.on('end', () => { try { resolve(JSON.parse(body)); } catch { resolve(null); } });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}

/** POST 一个 JSON 端点。这里的失败是**真失败**,会 reject —— 调用方要看得见原因。 */
export function httpPostJson(port, path, payload, timeoutMs = 60000) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(payload);
    const req = httpRequest(
      { host: HOST, port, path, method: 'POST', timeout: timeoutMs,
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } },
      (res) => {
        let body = '';
        res.on('data', (c) => (body += c));
        res.on('end', () => {
          try { resolve(JSON.parse(body)); }
          catch { reject(new Error(`Bad JSON from bridge: ${body.slice(0, 200)}`)); }
        });
      },
    );
    req.on('error', reject);
    // 桥中途死掉的话,socket 会一直挂着不返回
    req.on('timeout', () => { req.destroy(new Error('bridge request timeout (bridge down?)')); });
    req.write(data);
    req.end();
  });
}

/** 扫端口找正在跑的 bridge。返回 {port, health} 或 null。 */
export async function findBridge() {
  for (let port = PORT_START; port <= PORT_END; port++) {
    const health = await httpGetJson(port, '/health', 800);
    if (health && health.service === SERVICE_ID) return { port, health };
  }
  return null;
}

/** 列出连着的 EDA 窗口:{windows:[{windowId,label,connected,active}], activeWindowId, count}。 */
export function listWindows(port) {
  return httpGetJson(port, '/eda-windows', 3000);
}

/**
 * 在 EDA 里跑一段 JS,返回 bridge 的**原始信封** `{success, result, error, stack}`。
 * opts.windowId 省略 = 打 bridge 的活动窗口(⚠ 活动窗口会自己飘,见 README)。
 *
 * ⭐ 超时链必须外松内紧,否则 EDA 的报错还没送回来外层就先超时,拿到的是
 * 'bridge request timeout' 而不是真因:  HTTP = timeoutMs + 15s > bridge = timeoutMs + 5s > eext = timeoutMs
 */
export function execute(port, code, opts = {}) {
  const { windowId = null, timeoutMs = null, httpTimeoutMs = null } = opts;
  const payload = { code };
  if (windowId) payload.windowId = windowId;
  if (timeoutMs) payload.timeoutMs = timeoutMs;
  // httpTimeoutMs 只在调用方要单独控制 socket 超时(不改 eext 执行超时)时给
  const httpTimeout = httpTimeoutMs || (timeoutMs ? Math.round(timeoutMs) + 15_000 : 60_000);
  return httpPostJson(port, '/execute', payload, httpTimeout);
}

/** execute() 的「成功就给结果、失败就抛」版本。脚本里九成用这个。 */
export async function exec(port, code, opts = {}) {
  const r = await execute(port, code, opts);
  if (r && r.success === true) return r.result;
  const err = new Error(r && r.error ? r.error : 'execute failed');
  if (r && r.stack) err.edaStack = r.stack; // eext 透回来的 in-EDA 调用栈
  throw err;
}

/**
 * 统一解析 `--window <id>`(env `EDA_WINDOW_ID` 兜底)。
 *
 * ⚠ 返回 `rest` 是**去掉了 --window 及其取值**的 argv —— 四个脚本都把「不以 -- 开头的裸参数」
 * 当作位号/页名,不摘干净的话窗口 id 会被当成一个位号,而且只在多窗口时才犯,极难发现。
 */
export function parseWindowArg(argv) {
  const i = argv.indexOf('--window');
  const value = i >= 0 ? (argv[i + 1] || null) : null;
  const rest = i >= 0 ? argv.filter((_, k) => k !== i && k !== i + 1) : argv.slice();
  return { windowId: value || process.env.EDA_WINDOW_ID || null, rest };
}

/** 给报告打横幅用:窗口 id 太长,只取前 8 位;没指定就明说是"活动窗口(会飘)"。 */
export function windowTag(windowId) {
  return windowId ? windowId.slice(0, 8) : '(active)';
}
