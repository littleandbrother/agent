import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {activationDigest,verifyMethodActivation,verifyMethodBinding,methodEvent} from '../../changed/pi-overlay/packages/bf-agent/src/method-activation.ts';
const here=path.dirname(fileURLToPath(import.meta.url));
function fixture(id='strong_generic') {
  const run=spawnSync(process.execPath,['--experimental-strip-types',path.join(here,'activation.fixture.mjs'),id],{encoding:'utf8'});
  assert.equal(run.status,0,run.stderr);return JSON.parse(run.stdout);
}
const base=fixture();
const copy=()=>structuredClone(base);

test('actual fresh-process import and solverPrompt invocation produce verifiable evidence',()=>{const r=verifyMethodActivation(base.events,base.binding,base.expected);assert.equal(r.post_import,true);assert.equal(r.invoked,true);assert.equal(r.execution_authorized,false);assert.equal(r.scientific_success,false);assert.equal(r.prompt_hash,activationDigest(base.events[1].output));});
test('source and built bytes bind the actually imported pure modules',()=>assert.deepEqual(verifyMethodBinding(base.binding,base.actual,base.manifest),base.binding.profile));
test('method binding rejects source drift even when identifier is unchanged',()=>{const c=copy();c.actual.method_source_sha256='a'.repeat(64);assert.throws(()=>verifyMethodBinding(c.binding,c.actual,c.manifest),/METHOD_SOURCE_OR_BUILD_DRIFT/);});
test('method binding rejects manifest drift',()=>{const c=copy();c.manifest.loaded_files['method.js']='b'.repeat(64);assert.throws(()=>verifyMethodBinding(c.binding,c.actual,c.manifest),/METHOD_MANIFEST_DRIFT/);});
test('method binding rejects altered binding profile',()=>{const c=copy();c.binding.profile.Q=true;assert.throws(()=>verifyMethodBinding(c.binding,c.actual,c.manifest),/METHOD_BINDING_TAMPER/);});
test('all four live pure prompt entrypoints preserve identical public facts and requirements',()=>{
  const rows=['strong_generic','representation_only','revision_only','bf_design'].map(fixture);
  const reference=structuredClone(rows[0].observed);delete reference.methodProfile;
  for(const r of rows) {
    const observed=structuredClone(r.observed);delete observed.methodProfile;
    assert.deepEqual(observed,reference);assert.deepEqual(r.task,rows[0].task);
    assert.match(r.events[1].output,/synthetic-independent-observation/);
    assert.match(r.events[1].output,/do not weaken requirement/);
    assert.equal(r.binding.profile.candidate_opportunities,2);
    verifyMethodActivation(r.events,r.binding,r.expected);
  }
  assert.equal(new Set(rows.map(r=>r.events[1].output)).size,4);
});
test('import-only traces cannot establish method activation',()=>assert.throws(()=>verifyMethodActivation(base.events.slice(0,1),base.binding,base.expected),/METHOD_POST_IMPORT_INVOCATION_REQUIRED/));
test('invocation-only and pre-import invocation traces fail',()=>{for(const events of [[base.events[1]],[base.events[1],base.events[0]]])assert.throws(()=>verifyMethodActivation(events,base.binding,base.expected),/METHOD_POST_IMPORT_INVOCATION_REQUIRED/);});
test('wrong entrypoint and duplicate invocation traces fail',()=>{const c=copy();c.events[1].entrypoint='solver.initialState';assert.throws(()=>verifyMethodActivation(c.events,c.binding,c.expected),/METHOD_POST_IMPORT_INVOCATION_REQUIRED/);assert.throws(()=>verifyMethodActivation([...base.events,base.events[1]],base.binding,base.expected),/METHOD_POST_IMPORT_INVOCATION_REQUIRED/);});
test('bad process completion, same author PID, stale process and dirty context fail',()=>{for(const extra of [{exit_code:1},{author_pid:base.expected.pid},{fresh_process:false},{clean_context:false}])assert.throws(()=>verifyMethodActivation(base.events,base.binding,{...base.expected,...extra}),/METHOD_PROCESS_NOT_QUALIFIED/);});
test('replayed event nonce, packet, PID and binding fail',()=>{for(const key of ['nonce','packet_id','pid','method_binding_id']) {const c=copy();c.events[1][key]='replayed';assert.throws(()=>verifyMethodActivation(c.events,c.binding,c.expected),/METHOD_ACTIVATION_BINDING_MISMATCH/);}});
test('tampered prompt or prompt hash fails',()=>{for(const key of ['output','output_hash']) {const c=copy();c.events[1][key]='tampered';assert.throws(()=>verifyMethodActivation(c.events,c.binding,c.expected),/METHOD_ACTIVATION_OUTPUT_TAMPER/);}});
test('event constructor requires an invocation output',()=>assert.throws(()=>methodEvent('invoked','solver.solverPrompt',base.binding,base.expected),/METHOD_INVOCATION_OUTPUT_REQUIRED/));

// A verifier consumes external evidence; malformed expected IDs must fail closed too.
test('verifier independently rejects invalid PID identity',()=>{const c=copy();c.expected.pid=0;for(const event of c.events)event.pid=0;assert.throws(()=>verifyMethodActivation(c.events,c.binding,c.expected));});
test('verifier independently rejects empty nonce identity',()=>{const c=copy();c.expected.nonce='';for(const event of c.events)event.nonce='';assert.throws(()=>verifyMethodActivation(c.events,c.binding,c.expected));});
test('verifier independently rejects invalid packet hash identity',()=>{const c=copy();c.expected.packet_id='not-a-hash';for(const event of c.events)event.packet_id='not-a-hash';assert.throws(()=>verifyMethodActivation(c.events,c.binding,c.expected));});
test('fresh-process verifier requires a valid supervisor PID',()=>{for(const author_pid of [undefined,null,0,-1,'123'])assert.throws(()=>verifyMethodActivation(base.events,base.binding,{...base.expected,author_pid}));});
