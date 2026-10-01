/** Source-level wiring checks only. These do NOT claim a full SDK integration run. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../changed');
const main=fs.readFileSync(path.join(root,'pi-overlay/packages/bf-agent/src/main.ts'),'utf8');
const service=fs.readFileSync(path.join(root,'src/service_adapter.py'),'utf8');
const launcher=fs.readFileSync(path.join(root,'src/launcher_overlay.py'),'utf8');
const probe=fs.readFileSync(path.join(root,'run_probe.py'),'utf8');

test('extracted exact resume guard rejects state files and allows fresh state',()=>{
  const match=main.match(/if \(fs\.existsSync\(path\.join\(cwd, "state\.json"\)\)\)\s*throw new Error\("METHOD_RESUME_REQUIRES_TRUSTED_CHECKPOINT"\);/);
  assert.ok(match,'fresh-only guard must exist in actual main source');
  const guard=new Function('fs','path','cwd',match[0]);
  assert.throws(()=>guard({existsSync:()=>true},path,'/inert'),/METHOD_RESUME_REQUIRES_TRUSTED_CHECKPOINT/);
  assert.doesNotThrow(()=>guard({existsSync:()=>false},path,'/inert'));
  assert.ok(main.indexOf(match[0])<main.indexOf('let state ='));
  assert.ok(main.indexOf(match[0])<main.indexOf('ModelRuntime.create'));
  assert.doesNotMatch(main,/JSON\.parse\(fs\.readFileSync\(path\.join\(cwd, "state\.json"/);
});
test('main source records import before invocation and supplies that prompt to runtime',()=>{
  const importAt=main.indexOf('const solver = await import(');
  const methodImportAt=main.indexOf('methodEvent("post_import", "solver.method"');
  const invokeAt=main.indexOf('invoke("solver.solverPrompt"');
  const methodInvokeAt=main.indexOf('methodEvent("invoked", "solver.solverPrompt"');
  assert.ok(importAt>=0&&methodImportAt>importAt&&invokeAt>methodImportAt&&methodInvokeAt>invokeAt);
  assert.match(main,/getSystemPrompt: \(\) => prompt/);
});
test('main source binds actual file hashes and in-memory observations to revision recorder',()=>{
  assert.match(main,/const artifactHashes = \(\) => Object\.fromEntries\(Object\.entries\(files\(\)\)/);
  assert.match(main,/previous_artifacts: state\.methodCheckpoint, current_artifacts: artifactHashes\(\)/);
  assert.match(main,/observation_ids: state\.facts\.map/);
  assert.match(main,/used_opportunities: state\.methodOpportunities/);
  assert.match(main,/state\.methodOpportunities\.push\(record\.opportunity\)/);
});
test('activation helper source and build are frozen and startup verifies helper build',()=>{
  for(const name of ['app_auxiliary_sources','app_auxiliary_files','method-activation.ts','method-activation.js'])assert.ok(launcher.includes(name));
  assert.match(main,/app_auxiliary_files\?\.\["method-activation\.js"\]/);
  assert.ok(main.indexOf('METHOD_ACTIVATION_IMPLEMENTATION_DRIFT')<main.indexOf('const solver = await import('));
});
test('source keeps execution guards and capability blockers in service job admission',()=>{
  for(const guard of ['EXPLICIT_OFFLINE_EXECUTION_PACKET_REQUIRED','OFFLINE_PACKET_CANNOT_AUTHORIZE_EXECUTION','CONTROLLED_OVERLAY_TRUSTED_DRY_RUN_ONLY'])assert.ok(main.includes(guard));
  assert.ok(service.includes("blockers += packet['capability_admission']['blockers']"));
  assert.ok(service.includes("'TRUSTED_OFFLINE_SCOPE_NO_EXECUTION'"));
  assert.ok(service.includes("'status': 'BLOCKED', 'result': None"));
  assert.ok(launcher.includes("raise RuntimeError('LEGACY_LAUNCH_DISABLED_USE_CONTROLLED_SERVICE_GATE')"));
});
test('trusted supervisor source independently checks emitted method activation',()=>{
  assert.match(probe,/from method_contract import verify_activation/);
  assert.match(probe,/method_receipt = verify_activation\(events, packet\['method_binding'\]/);
  assert.match(probe,/author_pid=os\.getpid\(\), nonce=nonce, packet_id=packet\['packet_id'\], exit_code=proc\.returncode/);
});
