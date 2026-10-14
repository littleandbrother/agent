const {test}=require('node:test');const assert=require('node:assert/strict');
const M=require('../../apps/agent-studio/studio-model.js').ExecutionProgressModel;
const packet=(gates,extra={})=>({owner:'pi-a',checked_at:100,assembly_revision:4,execution:{status:'IDLE'},acceptance:{current_sources_valid:true,full_product_passed:false,functional_gates:gates,issues:[],...extra},versions:[]});
const gate=(id,status='PASS')=>({id,label:id,status,evidence:{path:'review.json',sha256:'a'.repeat(64)}});
test('file completeness and all local green checks cannot promote whole product',()=>{
 const x=M.project(packet([gate('delivery_version')]));assert.equal(x.leaves[0].status,'PASS');assert.equal(x.full_product_passed,false);assert.notEqual(x.status,'PASS');assert.equal(x.physical,'NOT_TESTED');
});
test('root green requires current independent whole scope and every necessary child',()=>{
 assert.equal(M.project(packet([gate('firmware')],{full_product_passed:true})).status,'PASS');
 for(const status of ['FAIL','STALE','UNEVALUABLE','NOT_CHECKED','UNKNOWN'])assert.notEqual(M.project(packet([gate('firmware'),gate('pcb',status)],{full_product_passed:true})).status,'PASS');
});
test('stale source or disconnected feed never shows current green',()=>{
 const stale=M.project(packet([gate('pcb')],{current_sources_valid:false,full_product_passed:true}));assert.equal(stale.leaves[0].status,'STALE');assert.equal(stale.full_product_passed,false);
 const disconnected=M.project(packet([gate('pcb')],{full_product_passed:true}),[],false);assert.equal(disconnected.leaves[0].status,'UNKNOWN');assert.equal(disconnected.full_product_passed,false);
});
test('mechanical and chipless scopes are not padded with invented MCU tasks',()=>{
 const x=M.project(packet([gate('geometry_fit'),gate('charge_transfer','NOT_CHECKED')]));assert.deepEqual(x.groups.map(g=>g.id),['power','mechanical']);assert.equal(x.leaves.length,2);
});
test('unclosed confirmed issue blocks root even when old checks pass',()=>{
 const x=M.project(packet([gate('pcb')],{full_product_passed:true,issues:[{id:'bad',state:'OPEN',summary:'wrong pin',gate_id:'pcb'}]}));assert.equal(x.full_product_passed,false);assert.equal(x.leaves[0].issues.length,1);
});
test('activity matches actual unfinished tool call, not a completed past one',()=>{
 const e=(type,id)=>({data:{type,toolCallId:id,toolName:'bf_engineering',args:{project_path:'firmware/project.json'}}});
 const d=packet([gate('target_firmware','NOT_CHECKED')]);d.execution.status='RUNNING';
 let x=M.project(d,[e('tool_execution_start','1'),e('tool_execution_end','1')]);assert.equal(x.activity.action.tool,undefined);
 x=M.project(d,[e('tool_execution_start','1')]);assert.equal(x.activity.status,'RUNNING');assert.equal(x.groups.find(g=>g.id==='firmware').active,true);assert.equal(x.leaves[0].status,'NOT_CHECKED');
 d.execution.status='IDLE';assert.equal(M.project(d,[e('tool_execution_start','1')]).activity,null);
});
test('manual reading preference wins over automatic task expansion',()=>{
 assert.equal(M.expanded({id:'a',status:'PASS'},{}),false);assert.equal(M.expanded({id:'a',status:'FAIL'},{}),true);
 assert.equal(M.expanded({id:'a',status:'RUNNING',active:true},{a:false}),false);assert.equal(M.expanded({id:'a',status:'PASS'},{a:true}),true);
});
test('assembly sequence links never manufacture design parents or an adoption',()=>{
 const x=M.versionGraph([{id:'v1',kind:'assembly',hashes:{}},{id:'v2',kind:'assembly',timeline_predecessor:'v1',current:true,hashes:{}}]);
 assert.equal(x[1].explicit_parent,null);assert.equal(x[1].link_kind,'sequence');assert.equal(x[1].adoption,'当前装配');
});
test('explicit ancestry preserves branches, absent parents and actual changes',()=>{
 const x=M.versionGraph([{id:'a',kind:'design',hashes:{firmware:'x'}},{id:'b',kind:'design',parent_id:'a',hashes:{firmware:'y'}},{id:'c',kind:'design',parent_id:'a',hashes:{firmware:'x'}},{id:'d',parent_id:'missing',hashes:{}}]);
 assert.equal(x[1].depth,x[2].depth);assert.deepEqual(x[1].changes,['firmware']);assert.deepEqual(x[2].changes,[]);assert.equal(x[3].missing_parent,true);assert.equal(x[3].explicit_parent,null);
});
test('six diagnostic categories are available but guesses are not confirmed',()=>{
 assert.equal(M.causes.length,6);assert.equal(M.diagnosis({cause:'agent_judgment'}).confirmed,false);
 assert.equal(M.diagnosis({summary:'timeout'}).label,'原因尚未确认');
 assert.equal(M.diagnosis({cause:'checker_judgment',classification_confirmed:true,artifact:{path:'proof'}}).confirmed,true);
 assert.equal(M.diagnosis({cause:'infeasible_task',classification_confirmed:true}).confirmed,false);
});
test('native/history rollback is disabled; supported design adoption has idle and freshness guards',()=>{
 const model={connected:true,execution:{status:'IDLE'},design_lab:{status:'ACTIVE'}};
 assert.equal(M.rollbackEligibility(model,{kind:'assembly',current:false}).allowed,false);
 const n={kind:'design',current:false,rollback_supported:true};assert.equal(M.rollbackEligibility(model,n).allowed,true);
 for(const status of ['RUNNING','STARTING','STOPPING','QUEUED'])assert.equal(M.rollbackEligibility({...model,execution:{status}},n).allowed,false);
 assert.equal(M.rollbackEligibility({...model,connected:false},n).allowed,false);
 assert.equal(M.rollbackEligibility({...model,design_lab:{status:'SUBMITTED'}},n).allowed,false);
});
test('unknown statuses cannot be silently interpreted as a pass',()=>{
 assert.equal(M.state('COMPLETED').tone,'warn');assert.notEqual(M.rollup([{status:'COMPLETED'}]),'PASS');
});
