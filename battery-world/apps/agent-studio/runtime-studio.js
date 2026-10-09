import {createAgentStudio} from './runtime-scene/studio.js';

const panel=document.querySelector('#runtime-studio');
const parking=document.querySelector('#runtime-studio-parking');
let host=null;
const container=panel.querySelector('.runtime-scene');
const status=panel.querySelector('.runtime-studio-status');
const summary=panel.querySelector('.runtime-studio-summary');
let studio=null,model=null,owner=null,generation=0,timer=null,last='',meeting='',visible=false;
let viewMode='live',userPaused=false;
const reduced=matchMedia('(prefers-reduced-motion: reduce)');

const toolbar=document.createElement('div');toolbar.className='runtime-controls';
toolbar.innerHTML='<div class="runtime-mode-switch" role="group" aria-label="动画模式"><button type="button" data-runtime-mode="live" aria-pressed="true">实时运行</button><button type="button" data-runtime-mode="demo" aria-pressed="false">演示动画</button></div><button type="button" class="runtime-play" aria-label="暂停动画">Ⅱ</button><button type="button" class="runtime-replay" aria-label="重播演示" title="重播演示" hidden>↺</button><span class="runtime-mode-caption">当前任务 · 真实事件</span>';
const cameras=document.createElement('nav');cameras.className='runtime-camera-bar';cameras.setAttribute('aria-label','动画视角');
cameras.innerHTML=[['front','全景'],['meeting','协作'],['product','产品'],['mechanical','机械'],['circuit','电路'],['pcb','PCB'],['power','功耗'],['firmware','固件']].map(([id,label])=>`<button type="button" data-runtime-camera="${id}" aria-pressed="${id==='front'}">${label}</button>`).join('');
const facts=document.createElement('details');facts.className='runtime-studio-details';
const factsTitle=document.createElement('summary');factsTitle.innerHTML='<b>运行记录</b>';factsTitle.append(status);
const factsBody=document.createElement('div');factsBody.className='runtime-facts-body';factsBody.append(summary,panel.querySelector('.runtime-studio-note'));facts.append(factsTitle,factsBody);
panel.querySelector('.runtime-studio-heading').remove();panel.append(toolbar,cameras,facts);
const playback=toolbar.querySelector('.runtime-play'),replay=toolbar.querySelector('.runtime-replay'),caption=toolbar.querySelector('.runtime-mode-caption');
function controls(scene){
  panel.dataset.sceneMode=scene.mode;
  toolbar.querySelectorAll('[data-runtime-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.runtimeMode===scene.mode)));
  cameras.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.runtimeCamera===scene.camera)));
  playback.textContent=scene.paused?'▷':'Ⅱ';playback.setAttribute('aria-label',scene.paused?'播放动画':'暂停动画');playback.title=scene.paused?'播放动画':'暂停动画';playback.disabled=reduced.matches;
  replay.hidden=scene.mode!=='demo';caption.textContent=scene.mode==='demo'?'预设演示 · '+scene.stage:'当前任务 · 真实事件';
}
function setViewMode(mode){
  if(!studio||mode===viewMode)return;
  viewMode=mode;studio.setMode(mode);last='';meeting='';render();display();
}
toolbar.addEventListener('click',event=>{const b=event.target.closest('[data-runtime-mode]');if(b)setViewMode(b.dataset.runtimeMode)});
cameras.addEventListener('click',event=>{const b=event.target.closest('[data-runtime-camera]');if(b)studio?.setCamera(b.dataset.runtimeCamera)});
playback.addEventListener('click',()=>{if(studio){userPaused=!studio.getSnapshot().paused;display()}});
replay.addEventListener('click',()=>{if(studio&&viewMode==='demo'){studio.seek(0);userPaused=false;display()}});

function render(){
  if(!model)return;
  const view=model.view();status.textContent=view.text;
  summary.replaceChildren(...view.agents.map(agent=>{
    const item=document.createElement('span');item.dataset.status=agent.status;
    item.textContent=window.BFRuntimeStudioModel.labels[agent.id]+' · '+agent.message;return item;
  }));
  const next=JSON.stringify(view);if(next===last)return;last=next;
  if(studio&&viewMode==='live'){
    for(const agent of view.agents)studio.dispatch({type:'agent.status',agent:agent.id,status:agent.status,message:agent.message.slice(0,300)});
    const nextMeeting=JSON.stringify(view.meeting);
    if(nextMeeting!==meeting){studio.dispatch(view.meeting?{type:'meeting.start',...view.meeting}:{type:'meeting.end'});meeting=nextMeeting}
    studio.dispatch({type:'dot.message',message:view.text.slice(0,300)});
    studio.dispatch({type:'artifact.update',assembled:false});
  }
}
function display(){
  visible=!!owner&&!!host?.isConnected&&!document.querySelector('#section-inspector').hidden&&document.body.dataset.studioMode==='task'&&document.body.dataset.workspace==='studio';
  panel.hidden=!visible;
  if(visible&&!studio){
    try{studio=createAgentStudio(container,{mode:viewMode,assetBase:new URL('./runtime-scene/assets/',import.meta.url).href,quality:'auto',reducedMotion:reduced.matches});studio.subscribe(controls);last='';}
    catch{container.textContent='3D 展示暂不可用，运行状态仍可查看。'}
  }
  if(studio){if(visible&&!document.hidden&&!reduced.matches&&!userPaused)studio.play();else studio.pause();studio.resize()}
  render();
}
async function refresh(){
  const target=owner,version=generation;if(!target)return;
  try{
    const value=await window.BF.api('/api/runtime-view?session='+encodeURIComponent(target));
    if(version!==generation||owner!==target)return;
    // Replay events newer than the transactionally captured snapshot cursor.
    if(model.hydrate(value))for(const row of window.BF.getEvents())model.ingest(row);
    model.setConnected(true);
    const resources=value.resources;
    let details=panel.querySelector('.runtime-resource-info');
    if(!details){details=document.createElement('details');details.className='runtime-resource-info';factsBody.append(details)}
    const title=document.createElement('summary');title.textContent=`专业技能 · ${resources?.skills?.length||0} 项可用 · ${resources?.active?.length||0} 项已加载`;
    const info=document.createElement('p');info.textContent=resources?.frozen?resources.active.map(s=>s.id+' @ '+s.version+' · '+s.sha256.slice(0,10)).join('；')||'本运行尚未激活专业技能': '技能包已就绪，将在下一次运行冻结并加载。';
    details.replaceChildren(title,info);render();
  }catch{
    if(version===generation){model.setConnected(false);render()}
  }
}
function select(){
  const selected=window.BF.getSelection();const next=selected?.startsWith('pi-chat-')?selected:null;
  if(next!==owner){
    generation++;owner=next;model=owner?window.BFRuntimeStudioModel.create(owner):null;last='';meeting='';
    viewMode='live';userPaused=false;studio?.setMode('live');status.textContent='正在读取运行状态';summary.replaceChildren();
  }
  display();void refresh();
}
function mount(target){host=target;(host||parking).append(panel);display()}
window.addEventListener('bf-mode',display);
window.addEventListener('bf-selection',select);
window.addEventListener('bf-runtime-events',event=>{
  if(event.detail.owner!==owner||!model)return;
  for(const row of event.detail.events)model.ingest(row);
  render();
  if(event.detail.events.some(row=>['eda_cli_operation','tool_execution_end','conversation_status'].includes(row.data?.type))){clearTimeout(timer);timer=setTimeout(refresh,350)}
});
window.addEventListener('bf-runtime-connection',event=>{if(event.detail.owner===owner&&model){model.setConnected(event.detail.connected);render()}});
document.addEventListener('visibilitychange',display);
reduced.addEventListener('change',display);
new MutationObserver(()=>{if(studio&&(document.body.classList.contains('product-mode')||document.body.classList.contains('developer-mode')||document.body.classList.contains('panorama-mode')))studio.pause();else display()}).observe(document.body,{attributes:true,attributeFilter:['class']});
window.addEventListener('pagehide',()=>{clearTimeout(timer);studio?.dispose();studio=null});
window.BFRuntimeStudio={getSnapshot:()=>({projection:model?.view(),scene:studio?.getSnapshot()}),refresh,display,mount};
mount(document.querySelector('#ew-runtime-host'));
select();
