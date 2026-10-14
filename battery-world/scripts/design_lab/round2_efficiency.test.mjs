import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { workspaceInspect } from '../../../pi-bf-aiot/packages/bf-agent/src/workspace-inspect.ts';
import { ReadProgress } from '../../../pi-bf-aiot/packages/bf-agent/src/read-progress.ts';
import { boundedToolReply } from '../../../pi-bf-aiot/packages/bf-agent/src/tool-reply.ts';

test('batch hashes and nested JSON fields eliminate shell extraction', () => {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'bf-r2-'));
  try {
    fs.writeFileSync(path.join(root,'receipt.json'),JSON.stringify({stdout:JSON.stringify({result:{pins:[27,26],nullable:null}})}));
    fs.writeFileSync(path.join(root,'main.c'),'#define GPIO 27\nother line\n');
    assert.equal(workspaceInspect(root,{action:'hash',paths:['receipt.json','main.c']}).files.length,2);
    const result=workspaceInspect(root,{action:'json',path:'receipt.json',decode_field:'stdout',fields:['result.pins','result.nullable']});
    assert.deepEqual(result.fields,{'result.pins':[27,26],'result.nullable':null});
    const search=workspaceInspect(root,{action:'search',paths:['main.c'],query:'GPIO'});
    assert.equal(search.files[0].matches[0].line,1);
    assert.throws(()=>workspaceInspect(root,{action:'json',path:'receipt.json',fields:['missing']}),/NOT_FOUND/);
    assert.throws(()=>workspaceInspect(root,{action:'json',path:'receipt.json',fields:['missing']}),/available=\["stdout"\]/);
    assert.throws(()=>workspaceInspect(root,{action:'hash',paths:['../file']}),/FILE_REQUIRED/);
    const original={id:'current',messages:[{text:'Original source requirement '.repeat(6000)}]};
    const reply=boundedToolReply(root,original);const index=JSON.parse(reply.content[0].text);
    assert.ok(Buffer.byteLength(reply.content[0].text)<8000);
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(root,index.record_file),'utf8')),original);
    for (const value of [
      {design_id:'D-real',parent:'D-before',files:Object.fromEntries(Array.from({length:200},(_,i)=>['f'+i,{sha256:'a'.repeat(64)}]))},
      {check_id:'check-real',design_id:'D-real',acceptance:{digital_engineering_status:'REPAIR_REQUIRED',file_integrity:'PASS',full_product_passed:false,
        functional_gates:[{id:'power',status:'FAIL',evidence:null}],issues:'x'.repeat(15000)}}
    ]) {
      const response=JSON.parse(boundedToolReply(root,value).content[0].text);
      assert.equal(response.design_id,'D-real');assert.ok(response.available_fields.includes('design_id'));
      if(value.check_id) {assert.equal(response.check_id,'check-real');assert.deepEqual(response.acceptance.functional_gates,[{id:'power',status:'FAIL'}]);}
      assert.ok(Buffer.byteLength(JSON.stringify(response))<8000);
    }
    workspaceInspect(root,{action:'inspect'});assert.ok(fs.statSync(path.join(root,'scratch')).isDirectory());
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});

test('same facts repeated three times get one notice; new data and waiting remain free', () => {
  const progress=new ReadProgress();
  for(let i=0;i<3;i++)progress.observe('read',{path:'main.c'},'same','D1');
  assert.match(progress.takeNotice(),/三次/);assert.equal(progress.takeNotice(),undefined);
  progress.observe('read',{path:'main.c'},'changed','D1');assert.equal(progress.takeNotice(),undefined);
  for(let i=0;i<3;i++)progress.observe('bf_design',{action:'job'},'running','D1');
  assert.equal(progress.takeNotice(),undefined);
  progress.observe('read',{path:'main.c'},'same','D2');assert.equal(progress.takeNotice(),undefined);
  for(let i=0;i<3;i++)progress.observe('bash',{command:'rg GPIO main.c'},'27','D2');
  assert.match(progress.takeNotice(),/三次/);
});
