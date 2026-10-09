const assert=require('node:assert/strict');
const {create,classify}=require('../../apps/agent-studio/runtime-studio-model.js');
const m=create('a');
assert.equal(m.hydrate({owner:'foreign',cursor:1,conversation:{status:'RUNNING'},jobs:[]}),false);
m.hydrate({owner:'a',cursor:3,conversation:{status:'PAUSED',error:'CHAT_TURN_WALL_BUDGET'},jobs:[
  {id:'j',domain:'pcb',status:'SUCCEEDED',created:2,label:'pcb drc',outcome:{check_status:'failed',counts:[{name:'Clearance',count:24}]}}
]});
assert.equal(m.view().agents.find(x=>x.id==='pcb').status,'blocked');
assert.equal(m.view().assembled,false);assert.match(m.view().text,/时长/);
assert.equal(m.ingest({seq:2,data:{type:'conversation_status',status:'RUNNING'}}),false);
assert.equal(m.ingest({owner:'b',seq:4,data:{type:'conversation_status',status:'RUNNING'}}),false);
m.ingest({seq:4,data:{type:'conversation_status',status:'RUNNING'}});
m.ingest({seq:5,data:{type:'tool_execution_start',toolCallId:'c',toolName:'bf_eda',args:{argv:['pcb','autoroute']}}});
assert.equal(m.view().agents.find(x=>x.id==='pcb').status,'work');
m.ingest({seq:6,data:{type:'tool_execution_end',toolCallId:'c'}});
assert.equal(m.view().agents.find(x=>x.id==='pcb').status,'blocked');
m.ingest({seq:7,data:{type:'tool_execution_start',toolCallId:'review',toolName:'bf_product',args:{action:'delivery_inspect'}}});
assert.equal(m.view().meeting.participants.length,5);
m.ingest({seq:8,data:{type:'tool_execution_end',toolCallId:'review'}});
assert.equal(m.view().meeting,null);
m.setConnected(false);assert.match(m.view().text,/连接中断/);
assert.equal(classify('bf_engineering',{engine:'engineering-project',parameters:{kind:'firmware-nrf52'}}),'firmware');
const restored=create('a');
restored.hydrate({owner:'a',cursor:100,conversation:{status:'RUNNING'},jobs:[],tool_calls:[
  {toolCallId:'review',toolName:'bf_product',args:{action:'delivery_inspect'}}]});
assert.equal(restored.view().meeting.participants.length,5);
restored.hydrate({owner:'a',cursor:101,conversation:{status:'RUNNING'},jobs:[],tool_calls:[]});
assert.equal(restored.view().meeting,null);
console.log('runtime projection: owner isolation, replay, DRC failure, review start/end, disconnect passed');
