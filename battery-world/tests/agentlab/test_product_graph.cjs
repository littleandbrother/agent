const test=require('node:test');
const assert=require('node:assert/strict');
const G=require('../../apps/agent-studio/product-graph.js');
const record=(revision,hash='h'+revision)=>({revision,created:revision*100,source_valid:true,hashes:{physical_hash:hash,geometry_hash:'g'+revision},payload:{title:'产品 '+revision,parts:[],energy:{capacitance_f:.047}}});
const fixture=()=>{const a=record(1),b=record(2);return {id:'pi-chat-test',product:{proposal:{revision:2,created:200,payload:{title:'公开方案',purpose:'事件送达'}},records:[],engineering:[{id:'eng-now',created:205,ended:220,engine:'mcu-firmware',status:'SUCCEEDED',assembly:b,result:{artifacts:[{name:'firmware.bin',sha256:'digest'}],build:{target:'test-mcu'},hardware_verified:false}},{id:'eng-old',created:101,ended:110,engine:'product-model',status:'SUCCEEDED',assembly:a,result:{artifacts:[{name:'model.glb'}]}}],assembly:{current:b,revisions:[a,b],checks:[{id:'target-firmware-verification',passed:true},{id:'hardware-measurements',passed:false,status:'NOT_EVALUATED'}],files:[],hardware_verified:false}}}};
test('tool success is a record, not complete product or hardware acceptance',()=>{
 const x=G.build(fixture());assert.equal(x.nodes.find(n=>n.id==='firmware').status,'recorded');assert.equal(x.nodes.find(n=>n.id==='firmware-check').status,'passed');assert.equal(x.nodes.find(n=>n.id==='service-check').status,'pending');assert.equal(x.nodes.find(n=>n.id==='release').status,'pending');assert.equal(x.physicalVerified,false);
});
test('historical assembly does not inherit latest checks or future artifacts',()=>{
 const x=G.build(fixture(),1);assert.equal(x.checks.length,0);assert.deepEqual(x.bound.map(j=>j.id),['eng-old']);assert.ok(!x.artifacts.some(f=>f.name==='firmware.bin'));assert.equal(x.nodes.find(n=>n.id==='firmware-check').status,'pending');
});
test('same version number with different identity and stale records are not bound',()=>{
 const c=fixture();c.product.engineering[0].assembly=record(2,'foreign');assert.equal(G.build(c).bound.length,0);
 c.product.engineering[0].assembly=record(2);c.product.engineering[0].stale=true;assert.equal(G.build(c).bound.length,0);
 c.product.assembly.current.source_valid=false;assert.equal(G.build(c).checks.length,0);assert.equal(G.build(c).physicalVerified,false);
});
test('missing data stay explicit and empty view has no example results',()=>{
 const x=G.build(null);assert.equal(x.empty,true);assert.equal(x.events.length,0);assert.equal(x.artifacts.length,0);assert.ok(x.nodes.every(n=>n.status==='pending'));assert.equal(G.checkState({passed:false,status:'NOT_EVALUATED'}),'pending');
});
test('digital delivery does not imply physical acceptance',()=>{
 const c=fixture();c.product.assembly.delivery={passed:true};const x=G.build(c);assert.equal(x.nodes.find(n=>n.id==='release').status,'recorded');assert.equal(x.physicalVerified,false);
});
test('timeline preserves actual times and failures and projection never mutates input',()=>{
 const c=fixture();c.product.engineering[0].status='FAILED';const before=JSON.stringify(c);const x=G.build(c);assert.equal(JSON.stringify(c),before);assert.equal(x.events.find(e=>e.id==='eng-now').state,'failed');assert.ok(x.events.every((e,i)=>!i||e.time>=x.events[i-1].time));assert.equal(x.events.find(e=>e.id==='eng-now').time,220);
});
test('completed computation with failed numerical checks stays visibly failed',()=>{
 assert.equal(G.jobState({status:'SUCCEEDED',result:{computational_checks_passed:false}}),'failed');
 assert.equal(G.jobState({status:'UNKNOWN'}),'pending');
 assert.equal(G.jobState({status:'SUCCEEDED',result:{computational_checks_passed:true,hardware_verified:false}}),'recorded');
});
test('withdrawn source cannot show a current hardware qualification',()=>{
 const c=fixture();c.product.assembly.current.source_valid=false;c.product.assembly.hardware_verified=true;
 assert.equal(G.build(c).physicalVerified,false);
});
