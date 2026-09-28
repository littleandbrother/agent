const test=require('node:test'),assert=require('node:assert/strict');
const G=require('../../apps/agent-studio/product-graph.js'),D=require('../../apps/agent-studio/product-deliverables.js');
function fixture(){
 const a={revision:1,source_valid:true,hashes:{physical_hash:'physical'},payload:{title:'Current product'}};
 const file={id:'firmware-id',revision:1,name:'main.c',digest:'file-hash',bytes:50};
 const current={id:'pi-chat-a',product:{assembly:{current:a,revisions:[a],files:[file]},engineering:[]}};
 const snapshot={owner:current.id,revision:1,tasks:[{id:'firmware',delivery_status:'partial',validation_status:'not_run',binding:{revision:1,physical_hash:'physical',files:[{id:file.id,digest:file.digest}],jobs:[]}}]};
 return {current,snapshot};
}
const node=(d,id)=>d.nodes.find(n=>n.id===id);
test('explicit session task binds its files to the correct part, preserving unaccepted status',()=>{
 const {current,snapshot}=fixture(),d=D.session(G.build(current),snapshot,current);
 assert.equal(node(d,'firmware').assets[0].name,'main.c');assert.equal(node(d,'mechanical').assets.length,0);assert.equal(node(d,'firmware').deliveryTasks[0].validation_status,'not_run');
 assert.match(node(d,'firmware').assets[0].url,/session=pi-chat-a/);
});
test('late snapshot from another owner, revision or physical design cannot bind files',()=>{
 for(const change of [s=>s.owner='pi-chat-b',s=>s.revision=2,s=>s.tasks[0].binding.physical_hash='other',s=>s.tasks[0].binding.files[0].digest='tampered']){
  const {current,snapshot}=fixture();change(snapshot);assert.equal(node(D.session(G.build(current),snapshot,current),'firmware').assets.length,0);
 }
});
test('history excludes latest deliverable inventory, published unbound files remain discoverable',()=>{
 const {current,snapshot}=fixture();current.product.assembly.current={revision:2,hashes:{physical_hash:'next'},payload:{}};current.product.assembly.revisions.push(current.product.assembly.current);snapshot.revision=2;
 const d=D.session(G.build(current,1),snapshot,current);assert.equal(d.tasks.length,0);assert.equal(node(d,'integrated').assets[0].name,'main.c');assert.equal(node(d,'firmware').assets.length,0);
});
test('stale/invalid bindings remain explicitly labelled, not validated',()=>{
 const {current,snapshot}=fixture();snapshot.tasks[0].delivery_status='stale';let d=D.session(G.build(current),snapshot,current);assert.equal(node(d,'firmware').assets[0].stale,true);
 snapshot.tasks[0].delivery_status='invalid';d=D.session(G.build(current),snapshot,current);assert.equal(node(d,'firmware').assets[0].integrity,false);
});
function ref(){
 const f={path:'delivery/cad/model.blend',sha256:'h'},fw={path:'delivery/fw/main.c',sha256:'f'},sim={path:'delivery/fem/model.mph',sha256:'s'},img={path:'delivery/fig/plot.png',sha256:'p'};
 return {title:'Reference only',artifact_integrity:true,artifacts:[f,fw,sim,img],delivery:{version:'engineering-v2',tasks:[{id:'cad',files:[f],delivery_status:'partial',validation_status:'not_run'},{id:'presentation',files:[f],delivery_status:'partial',validation_status:'not_run'},{id:'fem',files:[sim],delivery_status:'partial',validation_status:'not_run'},{id:'firmware',files:[fw],delivery_status:'partial',validation_status:'not_run'}],native_simulations:[{title:'FEM',files:[sim],figure:img.path,result:'Measured by solver',scope:'Not hardware'}]}};
}
test('reference files are deduplicated by identity and simulations follow their own part',()=>{
 const d=D.reference(ref());assert.equal(node(d,'mechanical').assets.length,3);assert.equal(node(d,'mechanical').simulations.length,1);assert.equal(node(d,'circuit').assets.length,0);assert.equal(node(d,'firmware').assets.length,1);assert.equal(node(d,'ml').assets.length,0);assert.equal(d.physicalVerified,false);assert.equal(node(d,'mechanical').status,'recorded');
 assert.ok(d.files.every(f=>f.url.startsWith('/api/reference-case/artifact?name=')));
});
test('unlisted reference file has no downloadable URL and integrity failures remain failures',()=>{
 const r=ref();r.delivery.tasks[0].files.push({path:'private.txt'});r.artifact_integrity=false;
 const d=D.reference(r);assert.ok(!d.files.some(f=>f.name==='private.txt'));assert.equal(node(d,'mechanical').status,'failed');assert.ok(node(d,'mechanical').assets.every(f=>f.integrity===false));
});
test('projections do not mutate receipts, produce fake cases or mark files as acceptance',()=>{
 const r=ref(),before=JSON.stringify(r);D.reference(r);assert.equal(JSON.stringify(r),before);
 const d=D.session(G.build(null),null,null);assert.ok(d.nodes.every(n=>n.assets.length===0));assert.equal(d.physicalVerified,false);
});
test('file categories distinguish simulator files, native geometry, source code and binary builds',()=>{
 for(const [name,expected] of [['model.mph','simulation'],['power.cir','simulation'],['assembly.step','native'],['main.c','code'],['Makefile','code'],['preview.png','image'],['report.json','document'],['firmware.hex','data']])assert.equal(D.kind({name}),expected);
});
test('upstream schematic and PCB remain reference-only and cannot satisfy current circuit tasks',()=>{
 const r=ref();r.artifacts.push({path:'circuit-reference/EMU_comp.SchDoc',sha256:'sch'},{path:'circuit-reference/EMU_comp.PcbDoc',sha256:'pcb'});
 r.delivery.tasks.push({id:'schematic',files:[],delivery_status:'missing',validation_status:'not_run'},{id:'pcb',files:[],delivery_status:'missing',validation_status:'not_run'});
 const d=D.reference(r),c=node(d,'circuit');
 assert.equal(c.assets.length,0);assert.equal(c.status,'pending');
 assert.equal(c.sections.find(s=>s.id==='schematic').assets.length,0);
 assert.equal(c.sections.find(s=>s.id==='schematic').references[0].referenceOnly,true);
 assert.equal(c.sections.find(s=>s.id==='pcb').references[0].name,'EMU_comp.PcbDoc');
 assert.equal(c.deliveryTasks.find(t=>t.id==='pcb').delivery_status,'missing');
 assert.equal(D.kind(c.sections.find(s=>s.id==='pcb').references[0]),'native');
});
