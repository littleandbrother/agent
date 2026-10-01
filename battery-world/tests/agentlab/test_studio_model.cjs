const {test}=require('node:test');const assert=require('node:assert/strict');
const M=require('../../apps/agent-studio/studio-model.js');
test('case scope separates identical version labels belonging to different cases',()=>{
 const r=(id)=>({case_id:id,case_title:id,case_version:'D2',id,files:[{id}],design_status:'FAIL',kind:'spice',scope:'Cold start failed'});
 const s={results:[r('a'),r('b')],files:[{id:'a'},{id:'b'}],verdict:{passed:true},blockers:[]};
 assert.equal(M.choices(s).length,3);const scoped=M.scoped(s,'case:a:D2');assert.deepEqual(scoped.files,[{id:'a'}]);assert.equal(scoped.verdict,null);assert.equal(M.findings(scoped).length,1);
});
test('published files and successful tools do not imply scientific acceptance',()=>{
 assert.equal(M.verdict({status:'PUBLISHED'}),'查看验证范围');assert.equal(M.verdict({status:'SUCCEEDED',design_status:'FAIL'}),'未通过');
 assert.equal(M.verdict({status:'SUCCEEDED',applicability:{state:'stale'}}),'需要重验');
});
test('completed coupled simulation preserves failure and evidence boundary',()=>{
 const base={status:'SUCCEEDED',design_status:'insufficient_evidence',predicted_design_status:'unsatisfied',scope:'冷启动未达到'};
 assert.equal(M.verdict(base),'模型内未达到目标');assert.equal(M.findings({results:[base]}).length,1);
 assert.equal(M.verdict({...base,predicted_design_status:'satisfied'}),'依据不足');
 assert.equal(M.verdict({...base,status:'FAILED',run_status:'out_of_domain'}),'执行失败');
});
test('hero uses only readable real artifacts and prioritizes product views',()=>{
 const row=(id,kind,integrity)=>({id,kind,domain:'mechanical',files:[{id,name:'installation.png',integrity}],presentations:[{kind:'image',file_id:id}]});
 assert.equal(M.hero({results:[row('invalid','blender',false),row('cad','cadquery',true),row('scene','blender',true)]}).f.id,'scene');
 assert.equal(M.hero({results:[]}),null);
});

test('assembly projects only applicable files and previews without changing verdicts',()=>{
 const a={id:'a',name:'current.png',integrity:true,applicability:{state:'current'}}, b={id:'b',name:'old.png',integrity:true,applicability:{state:'stale'}};
 const snapshot={revision:2,results:[{id:'r',kind:'comsol',design_status:'FAIL',files:[a,b],presentations:[{kind:'image',file_id:'a'},{kind:'image',file_id:'b'}]}],files:[a,b],verdict:{passed:false},blockers:[{state:'failed'}]};
 assert.equal(M.choices(snapshot)[0].id,'assembly');
 const scoped=M.scoped(snapshot,'assembly');assert.deepEqual(scoped.files,[a]);assert.deepEqual(scoped.results[0].files,[a]);assert.equal(scoped.results[0].presentations.length,1);
 assert.equal(scoped.results[0].design_status,'FAIL');assert.equal(scoped.verdict.passed,false);assert.equal(snapshot.results[0].files.length,2);
});
test('empty unassembled projects do not default to an independent reference',()=>{
 assert.equal(M.choices({results:[],files:[],revision:null})[0].id,'session');
 assert.equal(M.scoped({results:[],files:[],revision:null},'session').selectedScope,'session');
});
test('same-label previews remain distinguishable',()=>{
 const labels=M.previewLabels([{id:'a',name:'schematic.svg'},{id:'b',name:'schematic.pdf'}]);
 assert.notEqual(labels[0].label,labels[1].label);assert.ok(labels[0].label.includes('.svg'));
});
