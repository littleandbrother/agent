const assert=require('node:assert/strict');
const flow=require('../../apps/agent-studio/conversation.js');
const e=(seq,type,data={},time=seq)=>({seq,time,data:{type,...data}});
const msg=(seq,id,text,stopReason='stop',extra=[])=>e(seq,'message',{id,message:{role:'assistant',content:[{type:'text',text},...extra],stopReason,usage:{totalTokens:42}}});
const fixtures=[
 e(1,'user_message',{id:'u',text:'任务'}),e(2,'input_accepted'),e(3,'assistant_start',{id:'a'}),e(4,'text_delta',{id:'a',delta:'检查基准'}),
 msg(5,'a','检查基准','toolUse',[{type:'toolCall',id:'t'}]),e(6,'tool_execution_start',{toolCallId:'t',toolName:'bash',args:{command:'SECRET_RAW_COMMAND'}}),
 e(7,'tool_execution_end',{toolCallId:'t',toolName:'bash',result:'SECRET_RAW_RESULT'}),e(8,'assistant_start',{id:'b'}),e(9,'text_delta',{id:'b',delta:'已验证'}),
 msg(10,'b','已验证的最终结果'),e(11,'turn_complete'),e(12,'chat_idle')
];
const before=JSON.stringify(fixtures);
let view=flow.project(fixtures.slice(0,4),{live:true});
assert.equal(view.groups.at(-1).active,true);assert.equal(view.groups.at(-1).items[0].text,'检查基准');
view=flow.project(fixtures.slice(0,9),{live:true});assert.equal(view.groups.at(-1).items.at(-1).text,'已验证');
view=flow.project(fixtures);
assert.deepEqual(view.groups.map(x=>x.kind),['user','progress','assistant']);
assert.equal(view.groups[2].text,'已验证的最终结果');assert.equal(view.groups[2].usage.totalTokens,42);
assert.equal(view.groups[1].items.find(x=>x.kind==='activity').state,'done');
assert.equal(view.groups[1].start,2);assert.equal(view.groups[1].end,10);
assert.equal(JSON.stringify(fixtures),before);
const esc=s=>String(s).replaceAll('<','&lt;');
const html=flow.render(view.groups[1],{esc,markdown:esc,states:new Map()});
assert.ok(!html.includes('SECRET_RAW'));assert.ok(!html.includes('chat-tool'));assert.ok(html.includes('data-open-trace'));assert.ok(!html.includes('思考'));
assert.ok(!html.match(/class="response-progress"[^>]*\bopen\b/));
// Interleaved same-name tools require IDs, failures must not become successful.
const calls=[e(1,'tool_execution_start',{toolName:'read',toolCallId:'x'}),e(2,'tool_execution_start',{toolName:'read',toolCallId:'y'}),e(3,'tool_execution_end',{toolName:'read',toolCallId:'y',isError:true}),e(4,'turn_error',{error:'interrupted'})];
view=flow.project(calls);assert.deepEqual(view.records.filter(x=>x.kind==='activity').map(x=>x.state),['unknown','error']);
assert.ok(flow.label(view.records[0]).includes('未收到返回'));
const ambiguous=calls.slice(0,2).map(x=>({...x,data:{...x.data,toolCallId:undefined}}));ambiguous.push(e(3,'message',{message:{role:'toolResult',toolName:'read'}}));
assert.deepEqual(flow.project(ambiguous).records.map(x=>x.state),['unknown','unknown']);
// Recall hides only the specified projection range, and keeps the originals immutable.
view=flow.project([...fixtures,e(13,'message_withdrawn',{from_seq:1,to_seq:12})]);
assert.deepEqual(view.groups.map(x=>x.kind),['status']);assert.equal(JSON.stringify(fixtures),before);
// A later idle event cannot lend a timestamp to a previous turn; legacy absence stays absent.
view=flow.project([e(1,'tool_execution_start',{toolName:'read'},undefined),e(2,'chat_idle'),e(3,'input_accepted'),e(4,'chat_idle')]);
assert.equal(view.groups[0].start,null);assert.equal(view.groups[0].end,2);
const legacy=flow.project([e(1,'message',{message:{role:'user',content:'legacy'}}),msg(2,'a','legacy answer')],{legacy:true});
assert.deepEqual(legacy.groups.map(x=>x.kind),['user','assistant']);
// No content is promoted from provider-internal thinking fields.
assert.equal(flow.project([msg(1,'a','public','stop',[{type:'thinking',thinking:'PRIVATE_REASONING'}])]).groups[0].text,'public');
console.log('Conversation projection: streaming, completion, outcome IDs, recall, timing, legacy, immutable source, public-only rendering passed.');
const truncated=flow.project([msg(1,'a','已','length'),e(2,'conversation_status',{status:'FAILED',error:'MODEL_OUTPUT_TRUNCATED'}),e(3,'turn_error',{error:'MODEL_OUTPUT_TRUNCATED'}),e(4,'chat_idle')]);
assert.equal(truncated.records.find(x=>x.kind==='assistant').truncated,true);
assert.equal(truncated.groups.filter(x=>x.kind==='error').length,1);
assert.equal(truncated.groups.find(x=>x.kind==='assistant').text,'已');

// HTTP wrappers are display concerns; the original event is never rewritten.
const failure=e(1,'message',{id:'failed',message:{role:'assistant',content:[],stopReason:'error',errorMessage:'400 "PROVIDER_USAGE_UNKNOWN_STOP"'}});
const failureBytes=JSON.stringify(failure);
assert.equal(flow.errorCode('400 "PROVIDER_USAGE_UNKNOWN_STOP"'),'PROVIDER_USAGE_UNKNOWN_STOP');
const queued=[failure,e(2,'user_message',{text:'继续'}),e(3,'conversation_status',{status:'RUNNING'})];
assert.equal(flow.project(queued).records.find(x=>x.kind==='error').historical,false);
const failedAgain=[...queued,e(4,'message',{id:'again',message:{role:'assistant',content:[],stopReason:'error',errorMessage:'MODEL_USD_BUDGET'}})];
assert.ok(flow.project(failedAgain).records.filter(x=>x.kind==='error').every(x=>!x.historical));
const recovered=flow.project([...queued,msg(4,'answer','模型已正常返回')]);
const oldError=recovered.groups.find(x=>x.kind==='error');
assert.equal(oldError.historical,true);
assert.equal(oldError.text,'400 "PROVIDER_USAGE_UNKNOWN_STOP"');
const hints={PROVIDER_USAGE_UNKNOWN_STOP:'用量待核实'};
const historicalHTML=flow.renderError(oldError,{esc,errors:hints,states:new Map()});
assert.ok(historicalHTML.includes('后续已收到模型回复'));
assert.ok(historicalHTML.includes('用量待核实'));
assert.ok(!historicalHTML.includes('400'));
assert.ok(!historicalHTML.match(/<details[^>]*\bopen\b/));
const currentHTML=flow.renderError(flow.project([failure]).groups.find(x=>x.kind==='error'),{esc,errors:hints,states:new Map()});
assert.ok(currentHTML.includes('class="message error"'));
assert.equal(JSON.stringify(failure),failureBytes);
const afterRecall=flow.project([...queued,msg(4,'answer','模型已正常返回'),e(5,'message_withdrawn',{from_seq:2,to_seq:4})]);
assert.equal(afterRecall.records.find(x=>x.kind==='error').historical,false);
console.log('Historical/current error separation and HTTP wrapper normalization passed.');
const paused=e(1,'conversation_status',{status:'PAUSED',error:'CHAT_TURN_WALL_BUDGET'});
assert.equal(flow.project([paused]).groups[0].kind,'error');
assert.equal(flow.project([paused]).groups[0].historical,false);
assert.equal(flow.project([paused,msg(2,'resumed','继续读取已有结果')]).groups[0].historical,true);
console.log('Deadline pause remains visible until an actual later model response.');
