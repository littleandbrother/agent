const test=require('node:test');const assert=require('node:assert/strict');const E=require('../../apps/agent-studio/product-evidence.js');
function fixture(){return {results:Array.from({length:6},(_,i)=>({case_id:'door',case_version:'E1',created:10,evidence_story:{order:i+1,baseline_source_identity:'a',file_id:String(i)},files:[{id:String(i),integrity:true}]}))};}
test('ordered six groups, no mixing revisions or partial story',()=>{const s=fixture();assert.equal(E.groups(s).length,6);assert.equal(E.preferred(s),'case:door:E1');s.results[0].case_version='E2';assert.deepEqual(E.groups(s),[]);assert.equal(E.preferred(s),'');});
test('corrupt figure remains visible as unavailable, never silently promoted',()=>{const s=fixture();s.results[2].files[0].integrity=false;assert.equal(E.groups(s)[2].file.integrity,false);s.results[4].evidence_story.order=6;assert.deepEqual(E.groups(s),[]);});
test('newest complete baseline selected, incomplete new publication does not win',()=>{const s=fixture();s.results.push({...s.results[0],case_version:'E2',created:20});assert.equal(E.preferred(s),'case:door:E1');});
test('panel display requires the exact figures, provenance and every source file',()=>{
 const ids=['png','pdf','svg','provenance','csv','receipt'];
 const s={files:ids.map(id=>({id,integrity:true}))};
 const p={figure_id:'png',pdf_id:'pdf',svg_id:'svg',provenance_id:'provenance',source_files:['csv','receipt']};
 assert.equal(E.panelIntegrity(s,p),true);
 s.files.find(f=>f.id==='csv').integrity=false;assert.equal(E.panelIntegrity(s,p),false);
 assert.equal(E.panelIntegrity(s,{...p,source_files:[]}),false);
 assert.equal(E.panelIntegrity({files:s.files.filter(f=>f.id!=='provenance')},p),false);
 assert.equal(E.panelIntegrity(s,{...p,figure_id:'another-owner-png'}),false);
});
