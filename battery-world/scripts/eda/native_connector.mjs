/** Official desktop CLI -> existing typed Go daemon. No model-supplied code. */
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, appendFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createServer } from 'node:net';

export function nativeRuntimePolicy(manifest) {
  const value = manifest.runtime_policy || {};
  const policy = { singleton_port: value.singleton_port ?? 60901,
    scan_interval_ms: value.scan_interval_ms ?? 30000,
    context_refresh_ms: value.context_refresh_ms ?? 120000,
    allowed_project_paths: value.allowed_project_paths ?? [], diagnostics: value.diagnostics ?? false };
  if (!Number.isInteger(policy.singleton_port) || policy.singleton_port < 1024 || policy.singleton_port > 65535 ||
      !Number.isInteger(policy.scan_interval_ms) || policy.scan_interval_ms < 10000 || policy.scan_interval_ms > 120000 ||
      !Number.isInteger(policy.context_refresh_ms) ||
      (policy.context_refresh_ms !== 0 && policy.context_refresh_ms < policy.scan_interval_ms) || policy.context_refresh_ms > 600000 ||
      !Array.isArray(policy.allowed_project_paths) || new Set(policy.allowed_project_paths).size !== policy.allowed_project_paths.length ||
      policy.allowed_project_paths.some(p => typeof p !== 'string' || !p.startsWith('/') || resolve(p) !== p || !p.endsWith('.eprj3')) ||
      typeof policy.diagnostics !== 'boolean') {
    throw new Error('NATIVE_RUNTIME_POLICY_INVALID');
  }
  return policy;
}

export function selectedNativeSessions(entries, policy) {
  return entries.filter(entry => entry.status === 'alive' &&
    (!policy.allowed_project_paths.length ||
      (entry.headless === true && entry.origin === 'cli' && policy.allowed_project_paths.includes(entry.path))));
}

// The kernel releases this lease even on a crash. A second manual/launchd
// instance must fail before discovery or any native invocation starts.
export function acquireSingleton(port) {
  return new Promise((accept, reject) => {
    const server = createServer(socket => socket.destroy());
    server.once('error', error => {
      if (error.code === 'EADDRINUSE') error = new Error('NATIVE_CONNECTOR_ALREADY_RUNNING');
      reject(error);
    });
    server.listen({ port, host: '127.0.0.1', exclusive: true }, () => accept(server));
  });
}

export class NativeInvocationQueue {
  constructor() { this.pending = 0; this.tail = Promise.resolve(); }
  run(task) {
    this.pending++;
    const result = this.tail.then(task).finally(() => { this.pending--; });
    this.tail = result.then(() => {}, () => {});
    return result;
  }
  tryBackground(task) {
    return this.pending ? Promise.resolve(null) : this.run(task);
  }
}

export function invocationSource(bundle, request) {
  // JSON is data inside a fixed provider; no string is interpolated as source.
  return bundle + '\nreturn await BFNativeTyped.dispatchNative(JSON.parse(' +
    JSON.stringify(JSON.stringify(request)) + '));\n';
}

export function unwrapNative(stdout) {
  const value = JSON.parse(stdout.trim());
  if (value?.ok !== true) {
    const error = new Error(value?.error?.message || 'Official CLI failed');
    error.code = value?.error?.code || 'NATIVE_CLI_FAILED'; throw error;
  }
  if (!value.value || typeof value.value.ok !== 'boolean') throw new Error('NATIVE_RESPONSE_SCHEMA');
  return value.value;
}

export function validateRequest(request, actions, context = {}) {
  const metadata = actions.get(request?.action);
  if (!metadata || request.action === 'debug.exec_js' || request.action === 'system.page_reload') {
    throw new Error('NATIVE_TYPED_ACTION_DENIED');
  }
  if (request.action === 'project.create') {
    // Creating a destination is an operator bootstrap, not an edit of an
    // existing project. BF participant routes deny project.create separately.
    if (request.project || context.projectUuid) throw new Error('NATIVE_EMPTY_PROJECT_CONTEXT_REQUIRED');
    if (typeof request.payload?.friendlyName !== 'string' || !request.payload.friendlyName.trim()) {
      throw new Error('NATIVE_NEW_PROJECT_NAME_REQUIRED');
    }
  } else if (metadata.mutates && !request.project) throw new Error('NATIVE_BOUND_PROJECT_REQUIRED');
  if (request.payload !== undefined && (!request.payload || typeof request.payload !== 'object' || Array.isArray(request.payload))) {
    throw new Error('NATIVE_PAYLOAD_SCHEMA');
  }
  return metadata;
}

export function verifyManifest(manifest, scriptPath) {
  const sha = value => createHash('sha256').update(value).digest('hex');
  if (resolve(manifest.adapter) !== resolve(scriptPath) ||
      sha(readFileSync(scriptPath)) !== manifest.adapter_sha256 ||
      sha(readFileSync(manifest.bundle)) !== manifest.bundle_sha256 ||
      sha(readFileSync(manifest.actions)) !== manifest.actions_sha256) {
    throw new Error('NATIVE_PROVIDER_HASH_MISMATCH');
  }
}

export function mutationScope(sessionId, request) {
  return request.project || 'empty-session:' + sessionId;
}

const IDENTITY_DIAGNOSTICS = new Set(['project.current', 'document.current', 'board.list', 'system.environment']);
export function isIdentityDiagnostic(request) { return IDENTITY_DIAGNOSTICS.has(request.action); }

export function diagnosticBudget(request, receivedAt, now = Date.now()) {
  const budget = request.timeoutMs || 60000;
  if (!Number.isFinite(budget) || budget < 0) throw new Error('NATIVE_DIAGNOSTIC_BUDGET_INVALID');
  const remaining = budget - (now - receivedAt);
  // Official CLI startup and reply transport have their own cost. In
  // particular, the daemon's one-second bypass cannot queue native work.
  if (remaining <= 2500) {
    const error = new Error('NATIVE_DIAGNOSTIC_EXPIRED_NOT_SENT: insufficient remaining native CLI/reply budget');
    error.code = 'PRECONDITION_REFUSED'; throw error;
  }
  return Math.min(5000, remaining - 2000);
}

export function nativeFailure(error, request, metadata) {
  if (!metadata?.mutates && isIdentityDiagnostic(request) && error.code === 'NATIVE_EXECUTION_UNKNOWN') {
    return { code: 'NATIVE_DIAGNOSTIC_TIMEOUT',
      message: 'Readonly native diagnostic timed out; its read result is unavailable; no design write was dispatched.',
      detail: { original_code: error.code, native_write_dispatched: false } };
  }
  return { code: error.code || 'NATIVE_TYPED_REFUSED', message: error.message };
}

export function protocolResponse(value) {
  // The Go daemon's real ErrorInfo.Detail is a string. Object detail makes
  // json.Unmarshal reject the entire response and falsely leaves it pending.
  // Keep the structured facts as JSON text; successful result data is untouched.
  if (!value?.error || value.error.detail === undefined || typeof value.error.detail === 'string') return value;
  return { ...value, error: { ...value.error, detail: JSON.stringify(value.error.detail) } };
}

const children = new Set();
function command(binary, args, source, timeout) {
  return new Promise((accept, reject) => {
    const child = spawn(binary, args, { stdio: ['pipe', 'pipe', 'pipe'] });
    children.add(child);
    let stdout = '', stderr = '', ended = false;
    const finish = (error, result) => {
      if (ended) return; ended = true; clearTimeout(timer);
      if (error) reject(error); else accept(result);
    };
    const timer = setTimeout(() => {
      child.kill('SIGTERM'); const error = new Error('NATIVE_EXECUTION_UNKNOWN: command timed out; native effects may still land');
      error.code = 'NATIVE_EXECUTION_UNKNOWN'; finish(error);
    }, timeout);
    child.stdout.on('data', data => {
      stdout += data;
      if (stdout.length > 48 * 1024 * 1024) { child.kill('SIGTERM'); finish(new Error('NATIVE_RESULT_TOO_LARGE')); }
    });
    child.stderr.on('data', data => { if (stderr.length < 8192) stderr += data; });
    child.on('error', error => finish(error));
    child.on('close', code => {
      children.delete(child);
      if (code !== 0 && !stdout.trim()) finish(new Error('NATIVE_CLI_EXIT_' + code + ': ' + stderr.slice(0, 512)));
      else finish(null, stdout);
    });
    child.stdin.on('error', () => {});
    child.stdin.end(source || '');
  });
}

export async function runConnector(manifestPath) {
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  verifyManifest(manifest, process.argv[1]);
  const policy = nativeRuntimePolicy(manifest);
  const calls = new NativeInvocationQueue();
  const bundle = readFileSync(manifest.bundle, 'utf8');
  const actions = new Map(JSON.parse(readFileSync(manifest.actions, 'utf8')).map(x => [x.name, x]));
  const require = createRequire(manifest.ws_package);
  const WebSocket = require('ws');
  const sessions = new Map();
  const blockedPath = resolve(manifest.state_dir, 'unknown-mutations.json');
  mkdirSync(manifest.state_dir, { recursive: true });
  let blocked = {};
  try { blocked = JSON.parse(readFileSync(blockedPath, 'utf8')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  // Validate files, modules and quarantine before holding an open server.
  // A failed startup must exit instead of keeping a dead singleton alive.
  const singleton = await acquireSingleton(policy.singleton_port);
  const trace = (event, fields = {}) => {
    if (!policy.diagnostics) return;
    // No request payload, source code, tokens, result text or model reasoning.
    try {
      appendFileSync(resolve(manifest.state_dir, 'protocol-runtime.jsonl'),
        JSON.stringify({ at: new Date().toISOString(), event, provider: manifest.version, ...fields }) + '\n', { mode: 0o600 });
    } catch (error) { console.error('native diagnostic log unavailable: ' + error.message); }
  };
  const block = (project, request, error) => {
    blocked[project] = { request_id: request.id, action: request.action, at: new Date().toISOString(), error: error.message };
    writeFileSync(blockedPath, JSON.stringify(blocked, null, 2) + '\n', { mode: 0o600 });
  };
  const invokeRaw = async (id, request, timeout = 15000) => {
    const stdout = await command(manifest.cli, ['invoke', '--session', id, '--ext-uuid', 'eda',
      '--timeout', String(timeout), '--code-file', '-'], invocationSource(bundle, request), timeout + 1500);
    return unwrapNative(stdout);
  };
  const invoke = (id, request, timeout, requestId) => calls.run(async () => {
    trace('native_invocation_started', { session: id, request: requestId, action: request.action });
    try { return await invokeRaw(id, request, timeout); }
    finally { trace('native_invocation_finished', { session: id, request: requestId, action: request.action }); }
  });
  function connect(session) {
    if (session.socket || session.closed) return;
    const socket = new WebSocket('ws://127.0.0.1:' + manifest.port + '/eda'); session.socket = socket;
    const send = value => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(protocolResponse(value))); };
    socket.on('error', () => {});
    socket.on('close', () => { session.socket = null; if (!session.closed) setTimeout(() => connect(session), 2000); });
    socket.on('message', data => {
      let request; try { request = JSON.parse(data.toString()); } catch { return; }
      if (request.type === 'handshake') {
        if (request.service !== 'easyeda-agent') { socket.close(); return; }
        send({ type: 'register', windowId: session.windowId, connectorVersion: manifest.version,
          easyedaVersion: session.context.environment.version, capabilities: ['schematic.v1', 'pcb.v1', 'environment.v1', 'native-cli.v1'] });
        send({ type: 'context', windowId: session.windowId, ...session.context }); return;
      }
      if (request.type === 'ping') { send({ type: 'pong', id: request.id }); return; }
      if (request.type !== 'request') return;
      trace('request_received', { session: session.id, request: String(request.id).slice(0, 160),
        action: String(request.action).slice(0, 100), pending_native: calls.pending });
      const receivedAt = Date.now();
      if (isIdentityDiagnostic(request) && (session.pendingRequests || calls.pending)) {
        // Do not accumulate daemon health/bypass reads behind a blocked SDK
        // action. No cached identity and no concurrent native invocation.
        session.seq++;
        send({ id: request.id, type: 'response', version: request.version, windowId: session.windowId,
          ok: false, seq: session.seq, seqAbandoned: session.abandoned,
          error: { code: 'PRECONDITION_REFUSED',
            message: 'NATIVE_DIAGNOSTIC_BUSY_NOT_SENT: a native action is pending; no diagnostic or design write was dispatched.',
            detail: { native_entered: false, native_write_dispatched: false } } });
        trace('diagnostic_refused_before_entry', { request: request.id, action: request.action });
        return;
      }
      session.pendingRequests++;
      // One native session has one FIFO. No timeout retry or GUI recovery.
      session.queue = session.queue.then(async () => {
        let metadata, response, entered = false;
        try {
          metadata = validateRequest(request, actions, session.context);
          if (metadata.mutates && blocked[mutationScope(session.id,request)]) throw new Error('NATIVE_PRIOR_MUTATION_UNKNOWN');
          const timeout = isIdentityDiagnostic(request) ? diagnosticBudget(request, receivedAt) :
            Math.max(1000, Math.min(600000, (request.timeoutMs || 60000) - 3500));
          entered = true;
          session.currentMutation = metadata.mutates ? request : null;
          response = await invoke(session.id, { action: request.action, project: request.project, payload: request.payload }, timeout, request.id);
          if (response.context) session.context = response.context;
        } catch (error) {
          if (metadata?.mutates && entered) {
            session.abandoned++; block(mutationScope(session.id,request), request, error);
          }
          response = { ok: false, error: nativeFailure(error, request, metadata) };
        } finally {
          session.currentMutation = null;
          session.pendingRequests--;
        }
        if (response.context) session.lastContextAt = Date.now();
        session.seq++;
        send({ id: request.id, type: 'response', version: request.version, windowId: session.windowId,
          ...response, seq: session.seq, seqAbandoned: session.abandoned });
        trace('response_sent', { session: session.id, request: request.id, action: request.action,
          ok: response.ok, error_code: response.error?.code, seq: session.seq });
      }).catch(error => console.error('native session queue failed: ' + error.message));
    });
  }
  let scanning = false;
  async function refresh() {
    if (scanning) return; scanning = true;
    try {
      // Polls are disposable reads. They cannot queue behind or overlap an
      // actual request and cannot create seven simultaneous Electron clients.
      if ([...sessions.values()].some(s => s.pendingRequests)) return;
      const stdout = await calls.tryBackground(() => command(manifest.cli, ['session', 'list'], '', 8000));
      if (stdout === null) return;
      const result = JSON.parse(stdout);
      if (result.ok !== true || !Array.isArray(result.value)) throw new Error('NATIVE_SESSION_LIST_UNAVAILABLE');
      const alive = new Set();
      for (const entry of selectedNativeSessions(result.value, policy)) {
        alive.add(entry.sessionId);
        let session = sessions.get(entry.sessionId);
        if (!session) {
          const facts = await calls.tryBackground(() => invokeRaw(entry.sessionId, { kind: 'context' }, 6000));
          if (facts === null) continue;
          if (facts.ok !== true || facts.context?.environment?.host !== 'desktop') continue;
          session = { id: entry.sessionId, windowId: 'native-cli-' + entry.sessionId, context: facts.context,
            seq: 0, abandoned: 0, pendingRequests: 0, lastContextAt: Date.now(),
            queue: Promise.resolve(), socket: null, closed: false };
          sessions.set(entry.sessionId, session); connect(session);
        } else if (policy.context_refresh_ms > 0 && !session.pendingRequests && Date.now() - session.lastContextAt >= policy.context_refresh_ms) {
            const facts = await calls.tryBackground(() => invokeRaw(session.id, { kind: 'context' }, 6000));
            if (facts === null || facts.ok !== true) continue;
            session.context = facts.context;
            session.lastContextAt = Date.now();
            if (session.socket?.readyState === WebSocket.OPEN) session.socket.send(JSON.stringify({ type: 'context', windowId: session.windowId, ...session.context }));
        }
      }
      for (const [id, session] of sessions) if (!alive.has(id)) {
        session.closed = true; session.socket?.close(); sessions.delete(id);
      }
    } catch (error) { console.error('native session scan: ' + error.message); }
    finally { scanning = false; }
  }
  await refresh(); const scanTimer = setInterval(refresh, policy.scan_interval_ms);
  const heartbeat = setInterval(() => {
    for (const s of sessions.values()) if (s.socket?.readyState === WebSocket.OPEN) {
      s.socket.send(JSON.stringify({ type: 'ping', id: 'native-' + Date.now() }));
    }
  }, 3000);
  const stop = () => {
    clearInterval(scanTimer); clearInterval(heartbeat);
    for (const s of sessions.values()) {
      // Stopping a transport cannot turn an entered mutation into NOT_SENT.
      if (s.currentMutation) block(mutationScope(s.id, s.currentMutation), s.currentMutation,
        new Error('NATIVE_EXECUTION_UNKNOWN: connector stopped during an entered mutation'));
      s.closed = true; s.socket?.close();
    }
    for (const child of children) child.kill('SIGTERM');
    singleton.close(); process.exit(0);
  };
  process.once('SIGTERM', stop); process.once('SIGINT', stop);
  console.log('native typed connector ready; official sessions, fixed provider ' + manifest.bundle_sha256);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  runConnector(process.argv[2]).catch(error => { console.error(error.message); process.exitCode = 1; });
}
