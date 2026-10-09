const {test}=require('node:test');const assert=require('node:assert/strict');
const {create}=require('../../apps/agent-studio/result-catalog.js');
const S=require('../../apps/agent-studio/studio-model.js');
const M=require('../../apps/agent-studio/engineering-workspace-model.js');
test('three views share one request, fresh events and periodic background changes',async()=>{
 let version=1,count=0,clock=1000;const events=[];
 const cache=create(async url=>{if(url.startsWith('/api/results/version'))return {version};count++;return {owner:'a',snapshot_sha256:String(version)}},(n,d)=>events.push([n,d]),()=>clock);
 await Promise.all([cache.get('a'),cache.get('a'),cache.get('a')]);assert.equal(count,1);
 await cache.poll('a');assert.equal(count,1,'unchanged poll does not rebuild the catalog');
 version++;await cache.poll('a');assert.equal(count,2);
 assert.equal(events.filter(([n])=>n==='bf-results-updated').length,2);
 clock+=31000;await cache.poll('a');assert.equal(count,3,'periodic integrity refresh catches file changes outside DB');
});
test('invalidation during an in-flight read schedules another read',async()=>{
 let finish,calls=0;const cache=create(async url=>{if(url.includes('/version'))return {version:1};calls++;if(calls===1)await new Promise(r=>finish=r);return {snapshot_sha256:String(calls)}});
 const p=cache.get('a');await new Promise(setImmediate);cache.invalidate('a');finish();await p;await new Promise(setImmediate);
 assert.equal(calls,2);assert.equal(cache.peek('a').snapshot_sha256,'2');
});
test('late responses retain owner identity and cannot poison another project cache',async()=>{
 let finish;const events=[];const cache=create(async url=>{if(url.includes('/version'))return {version:1};if(url.includes('session=a'))await new Promise(r=>finish=r);return {owner:url.includes('session=a')?'a':'b',snapshot_sha256:url}},(n,d)=>events.push(d));
 const a=cache.get('a');await new Promise(setImmediate);const b=await cache.get('b');finish();await a;
 assert.equal(b.owner,'b');assert.equal(cache.peek('b').owner,'b');assert.equal(events.at(-1).owner,'a');
});
test('latest scope displays unbound firmware and native failures without promoting assembly acceptance',()=>{
 const f={id:'hex',name:'firmware.hex',domain:'firmware',integrity:true,applicability:{state:'unbound'}};
 const r={id:'job',files:[f],presentations:[],status:'SUCCEEDED'};
 const s={revision:6,scope_options:[{id:'latest',label:'最近产物'},{id:'assembly'}],latest_file_ids:['hex'],latest_result_ids:['job'],files:[f],results:[r],verdict:{passed:true}};
 assert.equal(S.preferredScope(s),'latest');assert.equal(S.scoped(s,'latest').files.length,1);assert.equal(S.scoped(s,'latest').verdict,null);assert.equal(S.scoped(s,'assembly').files.length,0);
 assert.equal(M.files(s,'firmware').length,1);assert.equal(M.files(s,'runtime').length,0);
 assert.equal(S.verdict({status:'SUCCEEDED',design_status:'FAIL',source_type:'eda'}),'未通过');
});
