import assert from 'node:assert/strict';
import test from 'node:test';
import { bindPaperAction, finishPaperRound, paperCandidateTool } from '../../../pi-bf-aiot/packages/bf-agent/src/paper-candidate.ts';
import { startupSkillIds } from '../../../pi-bf-aiot/packages/bf-agent/src/skill-resources.ts';

test('startup activates recovery and restores only actually active frozen skills', () => {
  const skills=[{name:'bf-task-recovery'},{name:'easyeda-agent'},{name:'easyeda-pcb-routing'}];
  assert.deepEqual(startupSkillIds(skills,['bf_skill','bf_eda']),['bf-task-recovery']);
  assert.deepEqual(startupSkillIds(skills,['bf_skill','bf_eda'],['easyeda-agent']),['bf-task-recovery','easyeda-agent']);
  assert.deepEqual(startupSkillIds(skills,['bf_skill','bf_engineering']),['bf-task-recovery']);
  assert.throws(()=>startupSkillIds([{name:'bf-task-recovery'}],['bf_skill'],['missing']),/REQUIRED_TOOL_SKILL_MISSING/);
});

test('actual Pi native bodies carry fresh candidate identity and keep the exact operation/decision', async () => {
  const calls=[];
  const api=async (...args)=>{calls.push(args);return {control_route:'candidate-lifecycle',working_design:'D-original',revision:3};};
  for (const [route, action] of [['/api/eda-cli','command'],['/api/engineering','run'],['/api/assembly','write'],['/api/assembly','register']]) {
    const input={action,operation_id:'same-id',decision_use:'Check the chosen design'};
    const out=await bindPaperAction(api,route,input);
    assert.deepEqual(out,{...input,candidate_id:'D-original',candidate_revision:3});
    assert.deepEqual(input,{action,operation_id:'same-id',decision_use:'Check the chosen design'});
  }
  assert.deepEqual(calls,Array(4).fill(['/api/design-lab',{action:'inspect'}]));
});

test('read-only jobs and unrelated routes preserve their exact caller payload', async () => {
  const input={action:'job',job_id:'original'};
  for (const route of ['/api/eda-cli','/api/engineering','/api/product','/api/skills']) {
    assert.equal(await bindPaperAction(async ()=>{throw Error('Unexpected extra query');},route,input),input);
  }
});

test('no legacy controller or foreign route can silently become a candidate write', async () => {
  await assert.rejects(bindPaperAction(async ()=>({control_route:'old-paper-phase'}),'/api/eda-cli',{action:'command'}),/CANDIDATE_ROUTE_REQUIRED/);
});

test('actual tool uses the original design endpoint and never routes paper work to C', async () => {
  const calls=[];
  const tool=paperCandidateTool(async (...args)=>{calls.push(args);return {intent:{kind:'BLOCKED'}};},value=>value);
  assert.equal(tool.name,'bf_design');assert.equal(tool.parameters.type,'object');
  assert.deepEqual(await tool.execute('call',{action:'intent',kind:'BLOCKED',rationale:'Native write unresolved'}),{intent:{kind:'BLOCKED'}});
  assert.deepEqual(calls,[['/api/design-lab',{action:'intent',kind:'BLOCKED',rationale:'Native write unresolved'}]]);
});

test('a new BF blocked decision closes a round while keeping full and physical claims separate', async () => {
  const view={working_design:'D-original',intent:{kind:'BLOCKED'}};
  const decision={seq:7,kind:'candidate_decision',data:{working_design:'D-original',kind:'BLOCKED'}};
  const api=async (_route,body)=>body.action==='inspect'?view:{events:[decision],next_cursor:7};
  const end=await finishPaperRound(api,{event_cursor:6});
  assert.equal(end.decision,decision);assert.equal(end.full_product_passed,false);assert.equal(end.physical,'NOT_TESTED');
});

test('old imported blockers, reads and foreign candidate decisions cannot finish a new BF round', async () => {
  for (const events of [[],[{kind:'candidate_action_observed',data:{}}],[{kind:'candidate_decision',data:{working_design:'D-other',kind:'BLOCKED'}}]]) {
    const api=async (_route,body)=>body.action==='inspect'?{working_design:'D-current',intent:{kind:'BLOCKED'}}:{events,next_cursor:2};
    await assert.rejects(finishPaperRound(api,{event_cursor:1}),/DECISION_REQUIRED/);
  }
});
