/**
 * bridge-embedded.mjs — 把 bridge **跑在 MCP server 进程内**,而不是另起一个进程。
 *
 * 为什么:
 *   1. 装机从「先起 bridge 进程 + 再配 MCP」变成一条命令,少一个进程、少一次端口竞争。
 *   2. 本文件按【线协议】实现 —— 协议由 eext(Apache-2.0)定义,端点形状是接口。
 *      原则:**实现接口,不复制实现**。
 *
 * ⭐ 关键设计:**它对外暴露和独立 bridge 完全一样的 HTTP API**。
 * 于是 MCP 侧的 `runOnEda()` 和全部工具**一行都不用改**(照旧 HTTP 到 127.0.0.1:port),
 * 而且别的 MCP client 扫端口时**会扫到我们**、自动把我们当共享 bridge 用
 * ⇒ 多客户端共享这条特性没丢(那是把两进程合一时最容易丢的东西)。
 *
 * 线协议(与 eext 对齐,见 eext/src/index.ts):
 *   server→eext  {type:'handshake', service:'easyeda-bridge'}      连上先发,eext 校验后才 register
 *   eext→server  {type:'register', windowId, label}
 *   server→eext  {type:'execute', id, code, timeoutMs}
 *   eext→server  {type:'result', id, result} | {type:'error', id, error, stack}
 *   eext→server  {type:'result_chunk', id, seq, total, data}       信封 JSON >512KB 时切 256KB 片
 *   双向          {type:'ping'|'pong', id}                          心跳
 *
 * ⚠ 超时链必须外松内紧(否则 EDA 的报错还没回来外层就先超时,拿到的是假错因):
 *      MCP HTTP = t+15s  >  本文件 = t+5s  >  eext = t
 */
import { createServer } from 'node:http';
import { randomUUID } from 'node:crypto';
import { attachWebSocket } from './ws-server.mjs';
import { pathToFileURL } from 'node:url';

const PORT_START = 49620;
const PORT_END = 49629;
const SERVICE_ID = 'easyeda-bridge';
const EEXT_DEFAULT_TIMEOUT_MS = 25_000; // eext 侧的缺省执行超时
const BRIDGE_MARGIN_MS = 5_000;         // 本层比 eext 松这么多

function readJsonBody(req, limitBytes = 64 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    let body = '', size = 0;
    req.on('data', (c) => {
      size += c.length;
      if (size > limitBytes) { reject(new Error('request body too large')); req.destroy(); return; }
      body += c;
    });
    req.on('end', () => { try { resolve(body ? JSON.parse(body) : {}); } catch (e) { reject(e); } });
    req.on('error', reject);
  });
}

/**
 * 起一个内嵌 bridge。
 * @returns {Promise<{port:number, close:()=>Promise<void>, stats:()=>object}>}
 */
export async function startEmbeddedBridge(opts = {}) {
  const {
    portStart = PORT_START, portEnd = PORT_END, host = '127.0.0.1',
    log = () => {},
  } = opts;

  /** @type {Map<string, {conn:any, label:string|null, since:number}>} */
  const windows = new Map();
  /** @type {Map<string, {resolve:Function, timer:any, windowId:string}>} */
  const pending = new Map();
  /** @type {Map<string, {parts:string[], total:number, got:number}>} */
  const chunks = new Map();

  let activeWindowId = null;
  // ⭐ 记录「活动窗口是不是被动换的」。一类真实故障的根因就是活动窗口
  // 在两次调用之间**静默**易主(原窗口断线 → 活动权交给另一个 → 原窗口重连也拿不回来)。
  // 窗口 id 每次连接都是新 randomUUID ⇒ 无法「认回」原窗口;那就至少让它**可见**。
  let activeAutoSwitched = false;
  let activeSwitchedAt = null;

  const setActive = (id, { auto = false } = {}) => {
    if (activeWindowId === id) return;
    activeWindowId = id;
    activeAutoSwitched = auto;
    activeSwitchedAt = auto ? Date.now() : null;
    log(`active window -> ${id ? id.slice(0, 8) : '(none)'}${auto ? ' (自动接管,非显式选择)' : ''}`);
  };

  const settle = (id, envelope) => {
    const p = pending.get(id);
    if (!p) return;
    clearTimeout(p.timer);
    pending.delete(id);
    p.resolve(envelope);
  };

  // ── WS 侧:eext 连进来 ────────────────────────────────────────────
  const onConnection = (conn, req) => {
    const path = (() => { try { return new URL(req.url, 'http://x').pathname; } catch { return req.url; } })();
    if (path !== '/eda') { conn.close(1008, 'unexpected path'); return; }

    let myWindowId = null;
    conn.send(JSON.stringify({ type: 'handshake', service: SERVICE_ID, timestamp: Date.now() }));

    conn.on('message', (raw) => {
      let msg;
      try { msg = JSON.parse(raw); } catch { log('非 JSON 帧,忽略'); return; }

      if (msg.type === 'register' && msg.windowId) {
        myWindowId = msg.windowId;
        windows.set(myWindowId, { conn, label: msg.label ?? null, since: Date.now() });
        if (!activeWindowId) setActive(myWindowId);
        log(`register ${myWindowId.slice(0, 8)} label=${JSON.stringify(msg.label ?? null)} (共 ${windows.size} 窗口)`);
        return;
      }
      if (msg.type === 'ping') { conn.send(JSON.stringify({ type: 'pong', id: msg.id, timestamp: Date.now() })); return; }
      if (msg.type === 'pong') return;

      if (msg.type === 'result' || msg.type === 'error') { settle(msg.id, msg); return; }

      // 大结果分块:按 (id, seq) 重组,收齐再 parse
      if (msg.type === 'result_chunk' && msg.id != null) {
        let slot = chunks.get(msg.id);
        if (!slot) { slot = { parts: new Array(msg.total), total: msg.total, got: 0 }; chunks.set(msg.id, slot); }
        if (slot.parts[msg.seq] === undefined) { slot.parts[msg.seq] = msg.data; slot.got++; }
        // 分块期间要给定时器续期,否则大结果会传到一半被判超时
        const p = pending.get(msg.id);
        if (p && p.renew) p.renew();
        if (slot.got === slot.total) {
          chunks.delete(msg.id);
          try { settle(msg.id, JSON.parse(slot.parts.join(''))); }
          catch (e) { settle(msg.id, { type: 'error', id: msg.id, error: `chunk reassembly failed: ${e.message}` }); }
        }
        return;
      }
    });

    conn.on('close', () => {
      if (!myWindowId) return;
      windows.delete(myWindowId);
      chunks.forEach((_, k) => { if (pending.get(k)?.windowId === myWindowId) chunks.delete(k); });
      // 该窗口上的在途请求必须立刻失败,否则调用方要干等到超时
      for (const [id, p] of [...pending]) {
        if (p.windowId !== myWindowId) continue;
        settle(id, { type: 'error', id, error: `EDA window "${myWindowId}" disconnected` });
      }
      log(`窗口断开 ${myWindowId.slice(0, 8)} (剩 ${windows.size})`);
      if (activeWindowId === myWindowId) setActive(windows.keys().next().value ?? null, { auto: true });
    });
  };

  // ── 发一条 execute 并等回应 ──────────────────────────────────────
  const execute = (code, windowId, timeoutMs) => new Promise((resolve) => {
    const target = windowId || activeWindowId;
    if (!target) return resolve({ type: 'error', error: 'No EDA window connected.' });
    const w = windows.get(target);
    if (!w || w.conn.readyState !== 1) {
      return resolve({ type: 'error', error: `EDA window "${target}" is no longer connected.` });
    }
    const execMs = Number.isFinite(timeoutMs) && timeoutMs > 0 ? Math.round(timeoutMs) : EEXT_DEFAULT_TIMEOUT_MS;
    const waitMs = execMs + BRIDGE_MARGIN_MS;
    const id = randomUUID();

    const entry = { resolve, windowId: target, timer: null };
    entry.renew = () => { clearTimeout(entry.timer); entry.timer = setTimeout(onTimeout, waitMs); };
    const onTimeout = () => { pending.delete(id); chunks.delete(id); resolve({ type: 'error', id, error: `Request ${id} timed out after ${waitMs}ms` }); };
    entry.timer = setTimeout(onTimeout, waitMs);
    pending.set(id, entry);

    try {
      w.conn.send(JSON.stringify({ type: 'execute', id, code, timeoutMs: execMs, timestamp: Date.now() }));
    } catch (e) {
      clearTimeout(entry.timer); pending.delete(id);
      resolve({ type: 'error', id, error: `send failed: ${e.message}` });
    }
  });

  // ── HTTP 面:与独立 bridge 同形,MCP 侧无需改动 ───────────────────
  const windowList = () => [...windows].map(([windowId, w]) => ({
    windowId, label: w.label, connected: w.conn.readyState === 1, active: windowId === activeWindowId,
  }));

  const server = createServer(async (req, res) => {
    const send = (code, obj) => {
      res.writeHead(code, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(obj));
    };
    // 对端半路走掉不该把进程带走
    req.on('error', () => {});
    res.on('error', () => {});
    try {
      const url = new URL(req.url, 'http://x');
      if (req.method === 'GET' && url.pathname === '/health') {
        return send(200, {
          service: SERVICE_ID, status: 'ok', embedded: true,
          edaConnected: windows.size > 0, edaWindowCount: windows.size,
          activeWindowId, activeWindowLabel: activeWindowId ? (windows.get(activeWindowId)?.label ?? null) : null,
          // ⭐ 让「活动窗口被动易主」可见,而不是像以前那样悄悄发生
          activeWindowAutoSwitched: activeAutoSwitched, activeWindowSwitchedAt: activeSwitchedAt,
          pendingRequests: pending.size, timestamp: Date.now(),
        });
      }
      if (req.method === 'GET' && url.pathname === '/eda-windows') {
        return send(200, { windows: windowList(), activeWindowId, count: windows.size });
      }
      if (req.method === 'POST' && url.pathname === '/eda-windows/select') {
        const body = await readJsonBody(req);
        if (!windows.has(body.windowId)) return send(404, { error: `EDA window "${body.windowId}" not found` });
        setActive(body.windowId);
        return send(200, { success: true, activeWindowId });
      }
      if (req.method === 'POST' && url.pathname === '/execute') {
        const body = await readJsonBody(req);
        if (!body.code) return send(400, { error: 'missing code' });
        const env = await execute(body.code, body.windowId, body.timeoutMs);
        if (env.type === 'result') {
          return send(200, { success: true, result: env.result, windowId: body.windowId || activeWindowId });
        }
        return send(200, { success: false, error: env.error || 'execute failed', stack: env.stack });
      }
      return send(404, { error: 'not found' });
    } catch (e) {
      return send(400, { error: e && e.message ? e.message : String(e) });
    }
  });
  server.on('clientError', (_e, socket) => { try { socket.destroy(); } catch {} });
  attachWebSocket(server, onConnection);

  // ── 端口:从 PORT_START 往上挑第一个空的(eext 也是升序扫,先到先得)──
  let port = null;
  for (let p = portStart; p <= portEnd; p++) {
    const okPort = await new Promise((resolve) => {
      const onErr = () => { server.removeListener('listening', onOk); resolve(false); };
      const onOk = () => { server.removeListener('error', onErr); resolve(true); };
      server.once('error', onErr);
      server.once('listening', onOk);
      server.listen(p, host);
    });
    if (okPort) { port = p; break; }
  }
  if (port === null) throw new Error(`no free port in ${portStart}-${portEnd}`);
  log(`内嵌 bridge 监听 ${host}:${port}`);

  return {
    port,
    stats: () => ({ windows: windowList(), activeWindowId, pending: pending.size }),
    close: () => new Promise((resolve) => {
      for (const [, w] of windows) { try { w.conn.destroy(); } catch {} }
      windows.clear();
      for (const [id] of [...pending]) settle(id, { type: 'error', id, error: 'bridge closing' });
      server.close(() => resolve());
    }),
  };
}

// ─────────────────────────────────────────────────────────────────────
// 自检:`node src/bridge-embedded.mjs --self-test`
// 用一个【假 eext】(Node 内置 WebSocket 客户端 + 照着线协议说话)打全流程,
// **不需要 EasyEDA、不需要板子**。假的是输入,走的是真管线。
// ─────────────────────────────────────────────────────────────────────
async function selfTest() {
  const results = [];
  const ok = (name, pass, detail = '') => {
    results.push(pass);
    console.log(`${pass ? '  ✅' : '  ❌'} ${name}${detail ? '  — ' + detail : ''}`);
  };
  // 用高位端口,免得撞上真在跑的 bridge
  const br = await startEmbeddedBridge({ portStart: 49700, portEnd: 49709, log: () => {} });
  const base = `http://127.0.0.1:${br.port}`;
  const get = (p) => fetch(base + p).then((r) => r.json());
  const post = (p, b) => fetch(base + p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then((r) => r.json());

  /** 假 eext:握手 → register → 按 handler 回应 execute */
  const fakeEext = (label, handler) => new Promise((resolve) => {
    const ws = new WebSocket(`ws://127.0.0.1:${br.port}/eda`);
    const windowId = randomUUID();
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'handshake' && msg.service === SERVICE_ID) {
        ws.send(JSON.stringify({ type: 'register', windowId, label, timestamp: Date.now() }));
        setTimeout(() => resolve({ ws, windowId }), 60);
        return;
      }
      if (msg.type === 'execute') handler(ws, msg);
    });
  });

  const echoHandler = (label) => (ws, msg) => {
    if (msg.code === '__hang__') return; // 故意不回,测超时
    if (msg.code === '__big__') {
      // 造一个 >512KB 的信封,照 eext 的规则切 256KB 片
      const json = JSON.stringify({ type: 'result', id: msg.id, result: 'C'.repeat(700_000) });
      const SIZE = 256 * 1024, total = Math.ceil(json.length / SIZE);
      for (let seq = 0; seq < total; seq++) {
        ws.send(JSON.stringify({ type: 'result_chunk', id: msg.id, seq, total, data: json.slice(seq * SIZE, (seq + 1) * SIZE) }));
      }
      return;
    }
    if (msg.code === '__throw__') {
      return ws.send(JSON.stringify({ type: 'error', id: msg.id, error: 'boom', stack: 'at fake:1' }));
    }
    ws.send(JSON.stringify({ type: 'result', id: msg.id, result: { from: label, code: msg.code, timeoutMs: msg.timeoutMs } }));
  };

  try {
    // ① 没有窗口时
    let h = await get('/health');
    ok('无窗口时 health', h.service === SERVICE_ID && h.edaConnected === false, `edaConnected=${h.edaConnected}`);
    let r = await post('/execute', { code: 'x' });
    ok('无窗口时 execute 明确报错', r.success === false && /No EDA window/.test(r.error), r.error);

    // ② 两个「窗口」—— 多窗口的核心场景
    const a = await fakeEext('BoardA', echoHandler('BoardA'));
    const b = await fakeEext('BoardB', echoHandler('BoardB'));
    const wl = await get('/eda-windows');
    ok('两个窗口都在册', wl.count === 2 && wl.windows.filter((w) => w.connected).length === 2, `count=${wl.count}`);
    ok('第一个自动成为活动窗口', wl.activeWindowId === a.windowId);

    // ③ windowId 定向:各打各的,不串味
    const ra = await post('/execute', { code: 'p1', windowId: a.windowId });
    const rb = await post('/execute', { code: 'p2', windowId: b.windowId });
    ok('windowId 定向', ra.result?.from === 'BoardA' && rb.result?.from === 'BoardB', `${ra.result?.from}/${rb.result?.from}`);

    // ④ 显式指定不改动活动窗口(这一轮定的语义)
    const wl2 = await get('/eda-windows');
    ok('定向调用不改活动窗口', wl2.activeWindowId === a.windowId);

    // ⑤ 不给 windowId → 走活动窗口
    const rdef = await post('/execute', { code: 'p3' });
    ok('缺省走活动窗口', rdef.result?.from === 'BoardA', rdef.result?.from);

    // ⑥ select 换活动窗口
    await post('/eda-windows/select', { windowId: b.windowId });
    const rdef2 = await post('/execute', { code: 'p4' });
    ok('select 之后缺省改走 B', rdef2.result?.from === 'BoardB', rdef2.result?.from);
    const bad = await post('/eda-windows/select', { windowId: 'nope' });
    ok('select 不存在的窗口报错', !!bad.error);

    // ⑦ 超时链:timeoutMs 透传给 eext
    const rt = await post('/execute', { code: 'p5', timeoutMs: 42000, windowId: a.windowId });
    ok('timeoutMs 透传到 eext', rt.result?.timeoutMs === 42000, String(rt.result?.timeoutMs));

    // ⑧ 分块重组(700KB 结果 → 3 片)
    const rbig = await post('/execute', { code: '__big__', windowId: a.windowId });
    ok('分块重组 700KB', rbig.success === true && rbig.result?.length === 700_000, `${rbig.result?.length}B`);

    // ⑨ eext 侧抛错 → stack 透传
    const rerr = await post('/execute', { code: '__throw__', windowId: a.windowId });
    ok('错误 + stack 透传', rerr.success === false && rerr.error === 'boom' && /fake:1/.test(rerr.stack || ''), rerr.error);

    // ⑩ 超时:不回应时按 t+5s 判超时
    const t0 = Date.now();
    const rto = await post('/execute', { code: '__hang__', timeoutMs: 800, windowId: a.windowId });
    const dt = Date.now() - t0;
    ok('无回应时按 t+5s 超时', rto.success === false && /timed out/.test(rto.error) && dt >= 5000 && dt < 8000, `${dt}ms`);

    // ⑪ 窗口断开:在途请求立刻失败,不用干等
    const inflight = post('/execute', { code: '__hang__', timeoutMs: 30000, windowId: b.windowId });
    await new Promise((r2) => setTimeout(r2, 150));
    b.ws.close();
    const t1 = Date.now();
    const rdrop = await inflight;
    ok('断开时在途请求立刻失败', rdrop.success === false && /disconnected/.test(rdrop.error) && Date.now() - t1 < 3000, rdrop.error);

    // ⑫ 活动窗口被动易主 —— 且【可见】(pcb.md §7 那次是静默发生的)
    await new Promise((r2) => setTimeout(r2, 150));
    const h2 = await get('/health');
    ok('活动窗口自动接管', h2.activeWindowId === a.windowId, h2.activeWindowId?.slice(0, 8));
    ok('⭐ 被动易主被标记出来', h2.activeWindowAutoSwitched === true && !!h2.activeWindowSwitchedAt);

    a.ws.close();
  } finally {
    await br.close();
  }

  const passed = results.filter(Boolean).length;
  console.log(`\n${passed}/${results.length} 通过`);
  return passed === results.length;
}

// ⚠ 只在【本文件是入口】时跑自检。不能只判 argv 里有没有 --self-test ——
// 那样别的模块 import 本文件时会被劫持(bridge-embedded.mjs --self-test 当场踩到:
// import 一发生就跑了本文件的自检并 process.exit,外层的测试根本没机会跑完)。
const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain && process.argv.includes('--self-test')) {
  selfTest().then((p) => process.exit(p ? 0 : 1)).catch((e) => { console.error(e); process.exit(2); });
}
