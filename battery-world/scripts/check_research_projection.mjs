import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../apps/agent-studio/research.js',import.meta.url),'utf8');
let rejectHistory;
const history=new Promise((resolve,reject)=>{rejectHistory=reject});
const host={dataset:{module:'research'},innerHTML:'',querySelector(){return {onclick:null}}};
const pilot={scope:'actual pilot',billing_blockers:[{id:'unknown'}],studies:[],trials:[
  {trial:'actual-failure',status:'FAILED',jobs:[{id:'j'}],model_calls:17,cost_upper_usd:.126963,submission:null},
  {trial:'planned',status:'NOT_STARTED',jobs:[],model_calls:0,cost_upper_usd:0,planned_only:true,submission:null},
]};
const window={BF:{api:path=>path==='/api/developer/research'?history:Promise.resolve(pilot),esc:String}};
vm.runInNewContext(source,{window,setTimeout,URL,Blob});
const opening=window.ResearchPanel.open(host);
await new Promise(resolve=>setTimeout(resolve,0));
assert.match(host.innerHTML,/actual-failure/);
assert.match(host.innerHTML,/正在独立读取历史研究记录/);
assert.match(host.innerHTML,/尚未启动/);
assert.doesNotMatch(host.innerHTML,/名义任务已满足|已测试通过/);
rejectHistory(new Error('RESEARCH_READ_TIMEOUT'));
await opening;
assert.match(host.innerHTML,/历史研究暂不可读/);
assert.match(host.innerHTML,/actual-failure/);
assert.match(host.innerHTML,/费用上界/);
assert.doesNotMatch(host.innerHTML,/尚未登记|此筛选下没有已登记实验/);
assert.doesNotMatch(host.innerHTML,/<img[^>]*style=/);
console.log('Research projection: actual results appear before stalled history; failure and planned-only states retained.');
