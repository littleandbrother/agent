/**
 * ws-server.mjs — 最小 WebSocket 服务端(RFC 6455 子集),**零外部依赖**。
 *
 * 为什么自己写:EasyEDA 的 eext 只能通过 `eda.sys_WebSocket` 往外连
 * (实测 `sys_*` 26 个类里没有任何 HTTP/fetch 能力)⇒ 必须有人监听 WS。
 * 而 Node **没有内置 WebSocket 服务端**(v26 只有客户端全局 `WebSocket`,
 * `node:http` 没有 `WebSocketServer`)⇒ 要么引 `ws` 依赖,要么就是这个文件。
 *
 * 选后者,两个理由:
 *   1. 整个 server 保持**零外部依赖**(装机不用 npm install)。
 *   2. 实现的是一份公开标准 ⇒ 本文件不含任何第三方代码。
 *
 * 实现范围(够用即止,不做通用库):
 *   ✅ 握手(Sec-WebSocket-Accept)· 文本/二进制帧 · 分片重组 · 掩码解码
 *      · 控制帧 ping/pong/close · 64 位长度 · 多连接并存
 *   ❌ 不做:扩展协商(permessage-deflate)· 子协议 · 客户端模式 · 背压控制
 *
 * ⚠ 协议要点(写错了很难查,记在这):
 *   - **客户端→服务端的帧必须带掩码**(RFC 6455 §5.1),没带就得断开;
 *     **服务端→客户端的帧必须不带掩码**。方向搞反了浏览器侧会静默丢弃。
 *   - 控制帧(opcode & 0x8)**不能分片、长度 ≤125**。
 *   - 一条消息可能跨多个 TCP 包到达,也可能一个包里挤着好几帧 ⇒ 必须缓冲 + 循环解析,
 *     不能假设「一次 data 事件 = 一帧」。
 */
import { createHash } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { pathToFileURL } from 'node:url';

// RFC 6455 §1.3 的魔法字符串,握手时拼在客户端 key 后面做 SHA-1
const GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';

const OP = { CONT: 0x0, TEXT: 0x1, BIN: 0x2, CLOSE: 0x8, PING: 0x9, PONG: 0xa };
const MAX_MESSAGE_BYTES = 64 * 1024 * 1024; // 兜底,防一个坏帧把内存吃干

/** 一条已升级的连接。事件:message(string) / binary(Buffer) / pong / close / error */
export class WsConnection extends EventEmitter {
  constructor(socket, req) {
    super();
    this.socket = socket;
    this.req = req;
    this.closed = false;
    this._buf = Buffer.alloc(0);
    this._frags = [];
    this._fragOp = null;
    this._fragLen = 0;

    socket.on('data', (d) => this._onData(d));
    socket.on('close', () => this._finish());
    socket.on('error', (e) => { this._fail(e); this._finish(); });
  }

  _finish() {
    if (this.closed) return;
    this.closed = true;
    this.emit('close');
  }

  /**
   * ⭐ 报错但**绝不因此终止进程**。
   * EventEmitter 的默认行为是:`emit('error')` 在没有监听者时**直接抛**。
   * 一个畸形帧(或对端半路拔线)于是能把整个 server 带走 —— 而这个进程同时持有
   * **其它所有 EDA 窗口**的连接。⇒ 一个坏窗口绝不能拖死其余窗口。
   * (2026-08-05 自检第 ⑩ 项当场炸出来的,不是假想。)
   */
  _fail(err) {
    if (this.listenerCount('error') > 0) this.emit('error', err);
    else process.stderr.write(`[ws-server] ${this.req?.url || ''} ${err && err.message ? err.message : err}\n`);
  }

  _onData(chunk) {
    this._buf = this._buf.length ? Buffer.concat([this._buf, chunk]) : chunk;
    try {
      // 一个 TCP 包里可能挤着多帧,循环直到不足一帧为止
      while (this._parseFrame());
    } catch (e) {
      this._fail(e);
      this.destroy();
    }
  }

  /** @returns {boolean} true = 解出了一帧还可以继续,false = 数据不够/已终止 */
  _parseFrame() {
    const b = this._buf;
    if (b.length < 2) return false;

    const b0 = b[0], b1 = b[1];
    const fin = (b0 & 0x80) !== 0;
    if (b0 & 0x70) throw new Error('RSV bits set but no extension negotiated');
    const op = b0 & 0x0f;
    const masked = (b1 & 0x80) !== 0;
    let len = b1 & 0x7f;
    let off = 2;

    if (len === 126) {
      if (b.length < off + 2) return false;
      len = b.readUInt16BE(off); off += 2;
    } else if (len === 127) {
      if (b.length < off + 8) return false;
      const big = b.readBigUInt64BE(off);
      if (big > BigInt(MAX_MESSAGE_BYTES)) throw new Error(`frame too large: ${big}`);
      len = Number(big); off += 8;
    }

    // §5.1:来自客户端的帧【必须】带掩码,否则按协议错误断开
    if (!masked) throw new Error('client frame is not masked (RFC 6455 §5.1)');
    if (b.length < off + 4) return false;
    const mask = b.subarray(off, off + 4); off += 4;

    if (b.length < off + len) return false; // 帧还没收全,等下一个 TCP 包

    const payload = Buffer.allocUnsafe(len);
    b.copy(payload, 0, off, off + len);
    for (let i = 0; i < len; i++) payload[i] ^= mask[i & 3];
    this._buf = b.subarray(off + len);

    // ---- 控制帧:不能分片,长度 ≤125
    if (op & 0x8) {
      if (!fin || len > 125) throw new Error('fragmented or oversized control frame');
      if (op === OP.CLOSE) {
        this._sendFrame(OP.CLOSE, payload); // 回一个 close 完成挥手
        try { this.socket.end(); } catch { /* 对端已走 */ }
        this._finish();
        return false;
      }
      if (op === OP.PING) { this._sendFrame(OP.PONG, payload); return true; }
      if (op === OP.PONG) { this.emit('pong', payload); return true; }
      throw new Error(`unknown control opcode 0x${op.toString(16)}`);
    }

    // ---- 数据帧
    if (op === OP.CONT) {
      if (this._fragOp === null) throw new Error('continuation frame without an initial frame');
      this._frags.push(payload);
    } else if (op === OP.TEXT || op === OP.BIN) {
      if (this._fragOp !== null) throw new Error('new data frame while a fragmented message is open');
      this._fragOp = op;
      this._frags = [payload];
      this._fragLen = 0;
    } else {
      throw new Error(`unknown data opcode 0x${op.toString(16)}`);
    }
    this._fragLen += len;
    if (this._fragLen > MAX_MESSAGE_BYTES) throw new Error('message too large');

    if (fin) {
      const full = this._frags.length === 1 ? this._frags[0] : Buffer.concat(this._frags);
      const finishedOp = this._fragOp;
      this._frags = []; this._fragOp = null; this._fragLen = 0;
      if (finishedOp === OP.TEXT) this.emit('message', full.toString('utf8'));
      else this.emit('binary', full);
    }
    return true;
  }

  /** 服务端→客户端:FIN=1、**不加掩码**(§5.1) */
  _sendFrame(op, payload = Buffer.alloc(0)) {
    if (this.closed) return false;
    const len = payload.length;
    let header;
    if (len < 126) {
      header = Buffer.allocUnsafe(2); header[1] = len;
    } else if (len < 65536) {
      header = Buffer.allocUnsafe(4); header[1] = 126; header.writeUInt16BE(len, 2);
    } else {
      header = Buffer.allocUnsafe(10); header[1] = 127; header.writeBigUInt64BE(BigInt(len), 2);
    }
    header[0] = 0x80 | op;
    try {
      this.socket.write(header);
      if (len) this.socket.write(payload);
      return true;
    } catch (e) {
      this._fail(e);
      return false;
    }
  }

  send(data) {
    return typeof data === 'string'
      ? this._sendFrame(OP.TEXT, Buffer.from(data, 'utf8'))
      : this._sendFrame(OP.BIN, Buffer.from(data));
  }

  ping(payload = Buffer.alloc(0)) { return this._sendFrame(OP.PING, Buffer.from(payload)); }

  close(code = 1000, reason = '') {
    if (this.closed) return;
    const r = Buffer.from(String(reason), 'utf8');
    const body = Buffer.allocUnsafe(2 + r.length);
    body.writeUInt16BE(code, 0);
    r.copy(body, 2);
    this._sendFrame(OP.CLOSE, body);
    try { this.socket.end(); } catch { /* ignore */ }
    this._finish();
  }

  destroy() {
    try { this.socket.destroy(); } catch { /* ignore */ }
    this._finish();
  }

  get readyState() { return this.closed ? 3 : 1; } // 与 WebSocket.CLOSED / OPEN 对齐
}

/**
 * 把 WS 升级处理挂到一个现成的 http.Server 上 —— 于是**同一个端口**既能提供
 * HTTP 端点(/health、/execute …)又能接 WS 连接,和现在 bridge 的对外形态一致。
 *
 * @param {import('node:http').Server} server
 * @param {(conn: WsConnection, req: import('node:http').IncomingMessage) => void} onConnection
 *        路由由调用方按 `req.url` 自己决定(eext 连的是 `/eda`)。
 */
export function attachWebSocket(server, onConnection) {
  server.on('upgrade', (req, socket, head) => {
    const key = req.headers['sec-websocket-key'];
    const ver = String(req.headers['sec-websocket-version'] || '');
    const up = String(req.headers.upgrade || '').toLowerCase();
    if (up !== 'websocket' || !key || ver !== '13') {
      socket.write('HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n');
      socket.destroy();
      return;
    }
    const accept = createHash('sha1').update(key + GUID).digest('base64');
    socket.write(
      'HTTP/1.1 101 Switching Protocols\r\n'
      + 'Upgrade: websocket\r\n'
      + 'Connection: Upgrade\r\n'
      + `Sec-WebSocket-Accept: ${accept}\r\n\r\n`,
    );
    socket.setNoDelay(true);
    const conn = new WsConnection(socket, req);
    // 握手响应之后可能已经跟着来了帧数据(挤在同一个 TCP 包里)
    if (head && head.length) conn._onData(head);
    onConnection(conn, req);
  });
  return server;
}

// ─────────────────────────────────────────────────────────────────────
// 自检:`node src/ws-server.mjs --self-test`
// **不需要 EasyEDA、不需要板子**,用 Node 内置的 WebSocket 客户端 + 一个手搓
// 原始帧的客户端,把协议里最容易写错的几处都打一遍。
// ─────────────────────────────────────────────────────────────────────
async function selfTest() {
  const { createServer } = await import('node:http');
  const { connect } = await import('node:net');
  const results = [];
  const ok = (name, pass, detail = '') => {
    results.push({ name, pass, detail });
    console.log(`${pass ? '  ✅' : '  ❌'} ${name}${detail ? '  — ' + detail : ''}`);
  };

  const conns = new Set();
  const server = createServer((req, res) => { res.writeHead(200); res.end('http-ok'); });
  attachWebSocket(server, (conn, req) => {
    conns.add(conn);
    conn.on('close', () => conns.delete(conn));
    conn.on('message', (m) => {
      if (m === '__url__') return conn.send(req.url);
      if (m === '__count__') return conn.send(String(conns.size));
      conn.send(m); // 回声
    });
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  const url = `ws://127.0.0.1:${port}/eda`;

  const once = (ws, ev) => new Promise((res, rej) => {
    ws.addEventListener(ev, res, { once: true });
    ws.addEventListener('error', rej, { once: true });
  });
  const roundtrip = async (ws, msg) => { const p = once(ws, 'message'); ws.send(msg); return (await p).data; };

  try {
    // ① 握手 + HTTP 共存同一端口
    const httpRes = await fetch(`http://127.0.0.1:${port}/health`).then((r) => r.text());
    ok('同一端口上 HTTP 仍可用', httpRes === 'http-ok', httpRes);

    const ws = new WebSocket(url);
    await once(ws, 'open');
    ok('握手成功(Sec-WebSocket-Accept 正确)', true);

    // ② 路由信息可见(eext 连的是 /eda)
    ok('req.url 传给了调用方', (await roundtrip(ws, '__url__')) === '/eda');

    // ③ 短文本
    ok('短文本回声', (await roundtrip(ws, 'hello')) === 'hello');

    // ④ 中文 + emoji(UTF-8 多字节,分片时最容易切坏)
    const uni = '中文 emoji 🛠️🔌 —— 代理对边界';
    ok('UTF-8/emoji 回声', (await roundtrip(ws, uni)) === uni);

    // ⑤ 126 与 65536 两个长度档的边界(帧头 2/4/10 字节三种编码)
    for (const n of [125, 126, 65535, 65536]) {
      const s = 'x'.repeat(n);
      const got = await roundtrip(ws, s);
      ok(`长度边界 ${n}B`, got.length === n && got === s, `回 ${got.length}B`);
    }

    // ⑥ 1.5MB —— 64 位长度 + 必然跨多个 TCP 包(现实里是分块传输的整包)
    const big = 'A'.repeat(1_500_000);
    const gotBig = await roundtrip(ws, big);
    ok('1.5MB 跨包重组', gotBig.length === big.length && gotBig === big, `回 ${gotBig.length}B`);

    // ⑦ 多连接并存 —— 这正是【多窗口】的前提:一个监听者持有 N 条连接
    const ws2 = new WebSocket(url); await once(ws2, 'open');
    const ws3 = new WebSocket(url); await once(ws3, 'open');
    const n = await roundtrip(ws3, '__count__');
    ok('三条连接并存(多窗口前提)', n === '3', `server 侧看到 ${n} 条`);
    // 各连接互不串味
    const [a, b] = await Promise.all([roundtrip(ws2, 'from-2'), roundtrip(ws3, 'from-3')]);
    ok('并发不串味', a === 'from-2' && b === 'from-3', `${a} / ${b}`);

    // ⑧ 关闭挥手
    const closed = once(ws2, 'close');
    ws2.close(1000, 'bye');
    await closed;
    ok('close 挥手', true);

    // ⑨ 控制帧 ping → pong(Node 内置客户端不给发 ping,手搓一个原始帧)
    const pongOk = await new Promise((resolve) => {
      const sock = connect(port, '127.0.0.1', () => {
        const key = Buffer.from('0123456789abcdef').toString('base64');
        sock.write(`GET /eda HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n`
          + `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`);
      });
      let phase = 'handshake', buf = Buffer.alloc(0);
      sock.on('data', (d) => {
        buf = Buffer.concat([buf, d]);
        if (phase === 'handshake') {
          const i = buf.indexOf('\r\n\r\n');
          if (i < 0) return;
          const hdr = buf.subarray(0, i).toString();
          if (!/101 Switching Protocols/.test(hdr)) { resolve(false); sock.destroy(); return; }
          buf = buf.subarray(i + 4); phase = 'frames';
          // 发一个带掩码的 PING(payload "hi")
          const mask = Buffer.from([1, 2, 3, 4]);
          const pl = Buffer.from('hi');
          const masked = Buffer.from(pl.map((c, k) => c ^ mask[k & 3]));
          sock.write(Buffer.concat([Buffer.from([0x80 | 0x9, 0x80 | pl.length]), mask, masked]));
        }
        if (phase === 'frames' && buf.length >= 2) {
          const op = buf[0] & 0x0f, len = buf[1] & 0x7f;
          const body = buf.subarray(2, 2 + len).toString(); // 服务端帧不带掩码
          resolve(op === 0xa && body === 'hi');
          sock.destroy();
        }
      });
      sock.on('error', () => resolve(false));
      setTimeout(() => { resolve(false); sock.destroy(); }, 3000);
    });
    ok('ping → pong(控制帧)', pongOk);

    // ⑩ 未加掩码的客户端帧必须被拒(RFC §5.1)
    const rejected = await new Promise((resolve) => {
      const sock = connect(port, '127.0.0.1', () => {
        const key = Buffer.from('fedcba9876543210').toString('base64');
        sock.write(`GET /eda HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n`
          + `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`);
      });
      let done = false;
      sock.on('data', (d) => {
        if (done) return;
        if (/101 Switching Protocols/.test(d.toString())) {
          done = true;
          // 无掩码的 TEXT 帧 —— 服务端应当断开
          sock.write(Buffer.concat([Buffer.from([0x81, 0x02]), Buffer.from('hi')]));
        }
      });
      sock.on('close', () => resolve(true));
      sock.on('error', () => resolve(true));
      setTimeout(() => { resolve(false); sock.destroy(); }, 3000);
    });
    ok('拒绝未加掩码的客户端帧', rejected);

    // ⑪ 非 WebSocket 的升级请求要被干净拒绝
    const bad = await new Promise((resolve) => {
      const sock = connect(port, '127.0.0.1', () => {
        sock.write('GET /eda HTTP/1.1\r\nHost: x\r\nUpgrade: h2c\r\nConnection: Upgrade\r\n\r\n');
      });
      sock.on('data', (d) => { resolve(/400 Bad Request/.test(d.toString())); sock.destroy(); });
      sock.on('error', () => resolve(false));
      setTimeout(() => resolve(false), 3000);
    });
    ok('非法升级请求返回 400', bad);

    ws.close(); ws3.close();
  } finally {
    server.close();
  }

  const failed = results.filter((r) => !r.pass);
  console.log(`\n${results.length - failed.length}/${results.length} 通过`);
  return failed.length === 0;
}

// ⚠ 只在【本文件是入口】时跑自检。不能只判 argv 里有没有 --self-test ——
// 那样别的模块 import 本文件时会被劫持(bridge-embedded.mjs --self-test 当场踩到:
// import 一发生就跑了本文件的自检并 process.exit,外层的测试根本没机会跑完)。
const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain && process.argv.includes('--self-test')) {
  selfTest()
    .then((pass) => process.exit(pass ? 0 : 1))
    .catch((e) => { console.error(e); process.exit(2); });
}
