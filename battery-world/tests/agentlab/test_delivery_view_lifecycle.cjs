const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function pendingView(){
  let resolve,owner='door';
  const response=new Promise(r=>{resolve=r});
  const document={body:{dataset:{studioMode:'product',workspace:'studio'}}};
  const window={BF:{api:()=>response,esc:String,getSelection:()=>owner}};
  const root={id:'section-content',isConnected:true,innerHTML:'',querySelector:()=>({})};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../apps/agent-studio/delivery.js'),'utf8'),{window,document,setTimeout});
  return {document,window,root,open:()=>window.DeliveryPanel.open(root,'door',true),
    changeOwner:()=>{owner='other'},resolve:()=>resolve({files:[{}],coverage:[],results:[],revision:null})};
}

test('an older delivery response cannot replace a new conversation workspace',async()=>{
  const p=pendingView(),request=p.open();
  p.document.body.dataset.studioMode='task';
  p.root.innerHTML='current engineering evidence';
  p.resolve();await request;
  assert.equal(p.root.innerHTML,'current engineering evidence');
});
test('a delivery response belonging to another project is ignored',async()=>{
  const p=pendingView(),request=p.open();p.changeOwner();
  p.root.innerHTML='other project';p.resolve();await request;
  assert.equal(p.root.innerHTML,'other project');
});
test('a response in the unchanged view still displays the actual file count',async()=>{
  const p=pendingView(),request=p.open();p.resolve();await request;
  assert.match(p.root.innerHTML,/统一成果目录 · 1 件文件/);
});
test('legacy delivery cannot overwrite a newly activated engineering pane',async()=>{
  const p=pendingView(),request=p.open();
  p.window.EngineeringWorkspace={active:()=>true};
  p.root.innerHTML='current engineering evidence';p.resolve();await request;
  assert.equal(p.root.innerHTML,'current engineering evidence');
});
