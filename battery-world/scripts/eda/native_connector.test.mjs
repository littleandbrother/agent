import { test } from 'node:test';
import assert from 'node:assert/strict';
import { invocationSource, unwrapNative, validateRequest, verifyManifest, mutationScope,
  acquireSingleton, NativeInvocationQueue, nativeRuntimePolicy, selectedNativeSessions,
  diagnosticBudget, nativeFailure, isIdentityDiagnostic } from './native_connector.mjs';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';

test('native parameters stay literal JSON, including source-looking values', async () => {
  const payload = { label: '); globalThis.injection = true; //', quote: '` ${x} </script>', points: [[0, 0], [24, 12]] };
  const source = invocationSource('var BFNativeTyped={dispatchNative:async r=>r};', { action: 'pcb.outline.set', payload });
  const result = await new (Object.getPrototypeOf(async function(){}).constructor)(source)();
  assert.deepEqual(result.payload, payload); assert.equal(globalThis.injection, undefined);
});
test('outer CLI success does not hide inner typed failure or missing schema', () => {
  assert.equal(unwrapNative(JSON.stringify({ ok: true, value: { ok: false, error: { code: 'REFUSED' } } })).ok, false);
  assert.throws(() => unwrapNative('{"ok":true,"value":{}}'), /NATIVE_RESPONSE_SCHEMA/);
  assert.throws(() => unwrapNative('{"ok":false,"error":{"code":"TIMEOUT","message":"wait"}}'), e => e.code === 'TIMEOUT');
});
test('catalog, project binding and typed payload cannot be bypassed', () => {
  const actions = new Map([['pcb.outline.set', { mutates: true }], ['project.current', { mutates: false }], ['debug.exec_js', { mutates: true }]]);
  assert.throws(() => validateRequest({ action: 'debug.exec_js', project: 'p' }, actions));
  assert.throws(() => validateRequest({ action: 'pcb.outline.set' }, actions), /BOUND_PROJECT/);
  assert.throws(() => validateRequest({ action: 'pcb.outline.set', project: 'p', payload: [] }, actions), /PAYLOAD_SCHEMA/);
  assert.equal(validateRequest({ action: 'project.current' }, actions).mutates, false);
});
test('new-project bootstrap only admits a named destination in an empty native session', () => {
  const actions = new Map([['project.create', { mutates: true }]]);
  const request = { action: 'project.create', payload: { friendlyName: 'Independent destination' } };
  assert.equal(validateRequest(request, actions).mutates, true);
  assert.throws(() => validateRequest(request, actions, { projectUuid: 'existing' }), /EMPTY_PROJECT_CONTEXT/);
  assert.throws(() => validateRequest({ ...request, project: 'existing' }, actions), /EMPTY_PROJECT_CONTEXT/);
  assert.throws(() => validateRequest({ action: 'project.create', payload: {} }, actions), /NEW_PROJECT_NAME/);
});
test('published adapter, action catalog and provider must all match their sealed bytes', () => {
  const folder = mkdtempSync(join(tmpdir(), 'bf-native-provider-'));
  try {
    const manifest = {};
    for (const key of ['adapter', 'bundle', 'actions']) {
      manifest[key] = join(folder, key);
      writeFileSync(manifest[key], key);
      manifest[key + '_sha256'] = createHash('sha256').update(key).digest('hex');
    }
    verifyManifest(manifest, manifest.adapter);
    assert.throws(() => verifyManifest(manifest, join(folder, 'foreign')), /HASH_MISMATCH/);
    writeFileSync(manifest.adapter, 'changed');
    assert.throws(() => verifyManifest(manifest, manifest.adapter), /HASH_MISMATCH/);
  } finally { rmSync(folder, { recursive: true, force: true }); }
});
test('unknown bootstrap effects quarantine the exact empty session, not every paper', () => {
  assert.notEqual(mutationScope('one', {}), mutationScope('two', {}));
  assert.equal(mutationScope('one', { project: 'original-project' }), 'original-project');
});
test('manual and managed instances cannot both hold the native connector lease', async () => {
  const first = await acquireSingleton(0);
  const port = first.address().port;
  try {
    await assert.rejects(acquireSingleton(port), /NATIVE_CONNECTOR_ALREADY_RUNNING/);
  } finally { await new Promise(resolve => first.close(resolve)); }
  const recovered = await acquireSingleton(port);
  await new Promise(resolve => recovered.close(resolve));
});
test('background discovery is discarded while foreground work is pending', async () => {
  const q = new NativeInvocationQueue();
  let release; const gate = new Promise(resolve => { release = resolve; });
  const events = [];
  const first = q.run(async () => { events.push('first-start'); await gate; events.push('first-end'); });
  const next = q.run(async () => { events.push('next'); });
  const result = await q.tryBackground(() => { events.push('unexpected-poll'); });
  assert.equal(result, null); assert.equal(q.pending, 2);
  release(); await Promise.all([first, next]);
  assert.deepEqual(events, ['first-start', 'first-end', 'next']);
  await q.tryBackground(() => { events.push('idle-poll'); });
  assert.equal(q.pending, 0); assert.equal(events.at(-1), 'idle-poll');
});
test('one failed invocation does not poison or replay the next action', async () => {
  const q = new NativeInvocationQueue(); let first = 0, second = 0;
  await assert.rejects(q.run(() => { first++; throw new Error('unknown-write'); }), /unknown-write/);
  await q.run(() => { second++; });
  assert.equal(first, 1); assert.equal(second, 1); assert.equal(q.pending, 0);
});
test('published native polling policy rejects a hot loop and an invalid singleton port', () => {
  assert.equal(nativeRuntimePolicy({}).scan_interval_ms, 30000);
  for (const value of [{ scan_interval_ms: 5 }, { singleton_port: 0 },
    { context_refresh_ms: 1 }, { singleton_port: true }]) {
    assert.throws(() => nativeRuntimePolicy({ runtime_policy: value }), /NATIVE_RUNTIME_POLICY_INVALID/);
  }
});
test('single-product policy only observes the original alive CLI-owned headless file', () => {
  const path = '/projects/original-P01.eprj3';
  const policy = nativeRuntimePolicy({ runtime_policy: { allowed_project_paths: [path], context_refresh_ms: 0, diagnostics: true } });
  const original = { sessionId: 'original', path, status: 'alive', headless: true, origin: 'cli' };
  const entries = [original, { ...original, sessionId: 'closed', status: 'closed' },
    { ...original, sessionId: 'gui', headless: false }, { ...original, sessionId: 'foreign-owner', origin: 'gui' },
    { ...original, sessionId: 'another-paper', path: '/projects/P02.eprj3' }];
  assert.deepEqual(selectedNativeSessions(entries, policy), [original]);
  assert.equal(policy.context_refresh_ms, 0); assert.equal(policy.diagnostics, true);
  assert.equal(selectedNativeSessions(entries, nativeRuntimePolicy({})).length, 4);
});
test('native project scope rejects ambiguous or noncanonical paths and malformed diagnostic flags', () => {
  for (const value of [{ allowed_project_paths: 'P01' }, { allowed_project_paths: ['/P01.eprj3', '/P01.eprj3'] },
    { allowed_project_paths: ['relative/P01.eprj3'] }, { allowed_project_paths: ['/projects/../P01.eprj3'] },
    { allowed_project_paths: ['/P01.zip'] }, { diagnostics: 'true' }]) {
    assert.throws(() => nativeRuntimePolicy({ runtime_policy: value }), /NATIVE_RUNTIME_POLICY_INVALID/);
  }
});
test('native identity read fits before the upstream deadline rather than the mutation budget', () => {
  assert.equal(diagnosticBudget({ timeoutMs: 60000 }, 1000, 1000), 5000);
  assert.equal(diagnosticBudget({ timeoutMs: 10000 }, 1000, 8000), 1000);
  assert.equal(isIdentityDiagnostic({ action: 'project.current' }), true);
  assert.equal(isIdentityDiagnostic({ action: 'document.current' }), true);
  assert.equal(isIdentityDiagnostic({ action: 'pcb.line.create' }), false);
});
test('one-second daemon bypass and expired queued read never get a native invocation budget', async () => {
  for (const [budget, waited] of [[1000, 0], [10000, 10000], [60000, 58000]]) {
    assert.throws(() => diagnosticBudget({ timeoutMs: budget }, 1000, 1000 + waited),
      error => error.code === 'PRECONDITION_REFUSED' && /EXPIRED_NOT_SENT/.test(error.message));
  }
  const q = new NativeInvocationQueue(); let enter = 0;
  await assert.rejects(q.run(() => { diagnosticBudget({ timeoutMs: 1000 }, 1000, 1000); enter++; }), /NOT_SENT/);
  assert.equal(enter, 0); assert.equal(q.pending, 0);
});
test('readonly timeout is not an unknown design write, entered mutation still is', () => {
  const error = Object.assign(new Error('native effects may still land'), { code: 'NATIVE_EXECUTION_UNKNOWN' });
  const read = nativeFailure(error, { action: 'project.current' }, { mutates: false });
  assert.equal(read.code, 'NATIVE_DIAGNOSTIC_TIMEOUT');
  assert.equal(read.detail.native_write_dispatched, false);
  const write = nativeFailure(error, { action: 'pcb.line.create' }, { mutates: true });
  assert.equal(write.code, 'NATIVE_EXECUTION_UNKNOWN');
  assert.equal(nativeFailure(error, { action: 'project.current' }, { mutates: true }).code, 'NATIVE_EXECUTION_UNKNOWN');
  assert.equal(nativeFailure(error, { action: 'document.open' }, { mutates: false }).code, 'NATIVE_EXECUTION_UNKNOWN');
});

test('actual connector rejects bypass backlog and keeps entered write unknown under injected SDK stalls', { timeout: 24000 }, async () => {
  // Loopback/fake SDK only. This is apparatus failure injection, never a
  // vendor-model, native engineering, or physical qualification.
  const folder = mkdtempSync(join(tmpdir(), 'bf-native-stall-'));
  writeFileSync(join(folder, 'unknown-mutations.json'), '{}\n');
  const wsPackage = createRequire(resolve('../pi-bf-aiot/package.json')).resolve('ws/package.json');
  const { WebSocketServer } = createRequire(wsPackage)('ws');
  const server = new WebSocketServer({ host: '127.0.0.1', port: 0 });
  await once(server, 'listening');
  const lease = await acquireSingleton(0); const singletonPort = lease.address().port;
  await new Promise(r => lease.close(r));
  const adapter = fileURLToPath(new URL('./native_connector.mjs', import.meta.url));
  const log = join(folder, 'entered.jsonl'); const cli = join(folder, 'fake-cli.mjs');
  const projectFile = join(folder, 'original-fixture.eprj3');
  const context = { projectUuid: 'fixture-project', projectName: 'Fixture', environment: { host: 'desktop', mode: 'half-offline', version: '4.1.71' } };
  writeFileSync(cli, `#!/usr/bin/env node
import { appendFileSync } from 'node:fs';
let input='';for await(const x of process.stdin)input+=x;
const context=${JSON.stringify(context)};
globalThis.fixtureDispatch=async r=>{
 if(r.kind==='context')return {ok:true,context};
 appendFileSync(${JSON.stringify(log)},JSON.stringify({action:r.action})+'\\n');
 await new Promise(done=>setTimeout(done,r.payload?.delay||0));
 return {ok:true,result:{uuid:'fixture-project'},context};
};
if(process.argv[2]==='session')console.log(JSON.stringify({ok:true,value:[{sessionId:'fixture',path:${JSON.stringify(projectFile)},status:'alive',headless:true,origin:'cli'}]}));
else {const value=await new(Object.getPrototypeOf(async function(){}).constructor)(input)();console.log(JSON.stringify({ok:true,value}));}
`, { mode: 0o755 });
  const bundle = join(folder, 'bundle.js'); const actions = join(folder, 'actions.json');
  writeFileSync(bundle, 'var BFNativeTyped={dispatchNative:r=>globalThis.fixtureDispatch(r)};');
  writeFileSync(actions, JSON.stringify([{ name: 'project.current', mutates: false }, { name: 'document.current', mutates: false }, { name: 'pcb.line.create', mutates: true }]));
  const manifest = { version: 'failure-injection', cli, adapter, bundle, actions, ws_package: wsPackage,
    port: server.address().port, state_dir: folder,
    runtime_policy: { singleton_port: singletonPort, scan_interval_ms: 30000, context_refresh_ms: 0, allowed_project_paths: [projectFile] } };
  for (const key of ['adapter', 'bundle', 'actions']) manifest[key+'_sha256'] = createHash('sha256').update(readFileSync(manifest[key])).digest('hex');
  const file = join(folder, 'manifest.json'); writeFileSync(file, JSON.stringify(manifest));
  let socket, child; const waits = new Map(); let ready;
  const connected = new Promise(r => { ready = r; });
  server.on('connection', s => {
    socket = s; s.send(JSON.stringify({ type: 'handshake', service: 'easyeda-agent' }));
    s.on('message', raw => {
      const value = JSON.parse(raw);
      if (value.type === 'context') ready();
      if (value.type === 'ping') s.send(JSON.stringify({ type: 'pong', id: value.id }));
      if (value.type === 'response' && waits.has(value.id)) { const w = waits.get(value.id); waits.delete(value.id); clearTimeout(w.timer); w.resolve(value); }
    });
  });
  const rpc = (id, action, payload = {}, timeoutMs = 60000) => new Promise((resolve, reject) => {
    const timer = setTimeout(() => { waits.delete(id); reject(new Error('fixture response deadline '+id)); }, 9000);
    waits.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ type: 'request', version: 'v1', id, action, project: 'fixture-project', payload, timeoutMs }));
  });
  try {
    child = spawn(process.execPath, [adapter, file], { stdio: ['ignore', 'pipe', 'pipe'] });
    let diagnostic = ''; child.stderr.on('data', x => { diagnostic += x; });
    const startTimer = setTimeout(() => ready(), 7000);
    await connected; clearTimeout(startTimer); assert.ok(socket, diagnostic);
    const first = rpc('read', 'project.current', { delay: 2000 });
    const until = Date.now()+2000;
    while (Date.now()<until) { try { if(readFileSync(log,'utf8').includes('project.current'))break; } catch {} await new Promise(r=>setTimeout(r,10)); }
    const bypass = await rpc('bypass', 'document.current', {}, 1000);
    assert.match(bypass.error.message, /BUSY_NOT_SENT/);
    assert.equal(JSON.parse(bypass.error.detail).native_entered, false);
    assert.equal((await first).ok, true);
    const expired = await rpc('expired', 'document.current', {}, 1000);
    assert.match(expired.error.message, /EXPIRED_NOT_SENT/);
    const timedOut = await rpc('read-stall', 'project.current', { delay: 10000 });
    assert.equal(timedOut.error.code, 'NATIVE_DIAGNOSTIC_TIMEOUT');
    assert.equal(JSON.parse(timedOut.error.detail).native_write_dispatched, false);
    assert.deepEqual(JSON.parse(readFileSync(join(folder,'unknown-mutations.json'),'utf8') || '{}'), {});
    const write = await rpc('write-stall', 'pcb.line.create', { delay: 10000 }, 5000);
    assert.equal(write.error.code, 'NATIVE_EXECUTION_UNKNOWN');
    const quarantine = JSON.parse(readFileSync(join(folder,'unknown-mutations.json'),'utf8'));
    assert.equal(quarantine['fixture-project'].request_id, 'write-stall');
    const next = await rpc('not-replayed', 'pcb.line.create');
    assert.match(next.error.message, /NATIVE_PRIOR_MUTATION_UNKNOWN/);
    const entered = readFileSync(log,'utf8').trim().split('\n').map(JSON.parse);
    assert.equal(entered.filter(x=>x.action==='document.current').length, 0);
    assert.equal(entered.filter(x=>x.action==='pcb.line.create').length, 1);
  } finally {
    for (const w of waits.values()) clearTimeout(w.timer);
    if (child && child.exitCode===null) { child.kill('SIGTERM'); await once(child,'exit'); }
    for (const client of server.clients) client.terminate();
    await new Promise(r=>server.close(r)); rmSync(folder,{recursive:true,force:true});
  }
});
