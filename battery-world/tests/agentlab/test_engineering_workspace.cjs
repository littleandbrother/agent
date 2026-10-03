const assert=require('node:assert/strict');
const M=require('../../apps/agent-studio/engineering-workspace-model.js');
const S=require('../../apps/agent-studio/studio-model.js');
const files=[
 {id:'sch',name:'schematic.svg',domain:'circuit',integrity:true},
 {id:'pcb',name:'pcb-combined.png',domain:'circuit',integrity:false},
 {id:'cad',name:'assembly.step',domain:'mechanical',integrity:true},
 {id:'data',name:'coupled-waveform.csv',domain:'system',role:'data',integrity:true},
 {id:'bom',name:'BOM.csv',domain:'circuit',integrity:true},
 {id:'code',name:'main.c',domain:'firmware',integrity:true,applicability:{state:'stale'}}
];
const snapshot={owner:'owner-A',title:'test',files,results:[{id:'failed',domain:'system',kind:'closed-simulation',design_status:'FAIL',files:[files[3]],presentations:[{kind:'series',file_id:'data'}]},{id:'eda',domain:'circuit',files:files.slice(0,2),presentations:[{kind:'image',file_id:'sch'},{kind:'image',file_id:'pcb'}]}]};
assert.deepEqual(M.files(snapshot,'schematic').map(f=>f.id),['sch']);
assert.deepEqual(M.files(snapshot,'pcb').map(f=>f.id),['pcb']);
assert.deepEqual(M.files(snapshot,'bom').map(f=>f.id),['bom']);
assert.equal(M.belongs({name:'pmic.cir',domain:'circuit'},'schematic'),false,'SPICE deck is not an EDA schematic');
assert.equal(M.belongs({name:'pmic.cir',domain:'circuit'},'simulation'),true);
assert.equal(M.views(snapshot,'pcb').length,0,'unreadable image is never previewed');
assert.equal(M.files(snapshot,'pcb').length,1,'unreadable registration remains visible');
assert.equal(M.results(snapshot,'simulation')[0].design_status,'FAIL','projection never promotes a failed design');
assert.equal(M.views(snapshot,'schematic')[0].f.id,'sch');
assert.equal(S.scoped({...snapshot,revision:2},'assembly').files.length,0,'historical unbound results cannot become current assembly results');
assert.equal(M.files({files:[],results:[]},'mechanical').length,0);
const series=M.series({headers:['t','v','bad'],units:['s','V',''],rows:[[0,2,null],[1,3,NaN],[2,Infinity,''],['bad',5,0]]});
assert.equal(series.rows.length,3);
assert.deepEqual(series.columns.map(c=>c.name),['v']);
assert.equal(series.lo,0);assert.equal(series.hi,2);
assert.deepEqual(M.series({headers:['t','v'],rows:[]}).columns,[]);
assert.equal(M.series({table:true,headers:['part'],rows:[['LTC3588-1']]}).table,true);
const before=JSON.stringify(snapshot);M.files(snapshot,'pcb');M.results(snapshot,'simulation');M.views(snapshot,'schematic');assert.equal(JSON.stringify(snapshot),before,'projection is immutable');
assert.equal(M.belongs({name:'mechanical-D2--drawings--main_pcb.pdf',domain:'mechanical'},'pcb'),false,'PCB mounting drawings remain structural drawings');
assert.equal(M.belongs({name:'pcb--D2--schematic.png',domain:'circuit'},'pcb'),false,'a PCB directory does not turn a schematic into a board view');
assert.equal(M.belongs({name:'pcb--D2--bom.csv',domain:'circuit',role:'data'},'simulation'),false,'BOM is tabular inventory, not a waveform');
assert.equal(M.belongs({name:'door.epro2',domain:'circuit'},'pcb'),true,'native EDA project remains discoverable');
assert.equal(M.series({headers:['time_s','velocity_m_s'],units:['s','s'],rows:[[0,1]]}).columns[0].unit,'m/s','compound SI units remain explicit');
assert.equal(M.views({files:[{id:'bom-old',name:'bom.csv',integrity:true}],results:[]},'bom')[0].v.kind,'series','legacy BOM without presentation still opens a table');
assert.equal(M.views({files:[{id:'raw-old',name:'trace.raw',integrity:true}],results:[]},'simulation')[0].v.kind,'series','legacy solver data retains actual series preview');
assert.equal(M.views({files:[{id:'deck',name:'pmic.cir',integrity:true}],results:[]},'simulation').length,0,'a circuit input is not a simulated waveform');
console.log('engineering workspace: 27 projection and negative-control assertions passed');
