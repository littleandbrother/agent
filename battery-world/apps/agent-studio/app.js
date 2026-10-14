const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Deliberately small Markdown subset: all source is escaped, with no raw HTML or URLs.
function inline(text){const render=s=>s.replace(/`([^`\n]+)`|\*\*(.+?)\*\*/g,(_,code,strong)=>code!==undefined?'<code>'+code+'</code>':'<strong>'+render(strong)+'</strong>');return render(esc(text))}
function markdown(text){
  const lines=text.split('\n'),out=[];let paragraph=[],list=[];
  const flush=()=>{if(paragraph.length){out.push('<p>'+paragraph.map(inline).join('<br>')+'</p>');paragraph=[]}if(list.length){out.push('<ul>'+list.map(s=>'<li>'+inline(s)+'</li>').join('')+'</ul>');list=[]}};
  const cells=s=>s.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim());
  for(let i=0;i<lines.length;i++){
    const line=lines[i];
    if(/^\s*```/.test(line)){flush();const code=[];while(++i<lines.length&&!/^\s*```/.test(lines[i]))code.push(lines[i]);out.push('<pre><code>'+esc(code.join('\n'))+'</code></pre>');continue}
    if(line.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-+:?\s*\|[\s|:\-]+$/.test(lines[i+1])){flush();const head=cells(line);i++;const rows=[];while(i+1<lines.length&&lines[i+1].includes('|')&&lines[i+1].trim()){rows.push(cells(lines[++i]))}out.push('<div class="message-table"><table><thead><tr>'+head.map(c=>'<th>'+inline(c)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(c=>'<td>'+inline(c)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>');continue}
    const heading=line.match(/^#{1,6}\s+(.+)/);if(heading){flush();out.push('<h3>'+inline(heading[1])+'</h3>');continue}
    if(/^\s*([-*_])\1\1+\s*$/.test(line)){flush();out.push('<hr>');continue}
    const item=line.match(/^\s*(?:[-*]|\d+[.)])\s+(.+)/);if(item){if(paragraph.length)flush();list.push(item[1]);continue}
    if(!line.trim()){flush();continue}if(list.length)flush();paragraph.push(line);
  }
  flush();return out.join('');
}
const access=new URLSearchParams(location.hash.slice(1)).get('access');if(access){sessionStorage.setItem('bf-access',access);history.replaceState(null,'',location.pathname)}
const headers=()=>({'Content-Type':'application/json',...(sessionStorage.getItem('bf-access')?{Authorization:'Bearer '+sessionStorage.getItem('bf-access')}:{})});
async function api(path,body,options={}){let response=await fetch(path,{...options,method:body===undefined?'GET':'POST',credentials:'same-origin',headers:headers(),...(body===undefined?{}:{body:JSON.stringify(body)})});if(response.status===403&&sessionStorage.getItem('bf-access')){sessionStorage.removeItem('bf-access');response=await fetch(path,{...options,method:body===undefined?'GET':'POST',headers:headers(),...(body===undefined?{}:{body:JSON.stringify(body)})})}const value=await response.json();if(!response.ok)throw Error(value.error||'请求失败');return value}
let selected=sessionStorage.getItem('bf-chat-selected')||null, conversations=[], folders=[], newFolder=sessionStorage.getItem('bf-chat-folder')||null, current=null, execution=null, events=[],cursor=0, stream=null, sending=false,section=localStorage.getItem('bf-section')||'proposal',renderTimer=null;
const names={QUEUED:'排队中',RECALLING:'正在撤回',RUNNING:'执行中',STARTING:'准备中',IDLE:'等待消息',COMPLETED:'已完成',FAILED:'执行中断',BLOCKED:'模型受阻',INTERRUPTED:'已中断',STOPPING:'正在停止',PAUSED:'已暂停'};
const errors={CHAT_TURN_WALL_BUDGET:'本轮执行时间已用完，已暂停。历史消息和已生成文件保留；发送新消息可继续。',SESSION_WALL_LIMIT:'执行进程达到运行时限而中断。历史消息和已生成文件保留；发送新消息可继续。',CHAT_TURN_AUTH_REQUIRED:'当前消息已撤回，请发送新消息继续。',MODEL_OWNER_USD_BUDGET:'本次会话的模型额度已用完，已完成的内容保留。',MODEL_TOKEN_BUDGET:'模型 token 额度已用完，消息已保存。',RECALL_PENDING:'正在停止当前执行并撤回消息，请稍候。',RECALL_RETRY_REQUIRED:'上次撤回未完成，请再次点击对应消息的撤回按钮。',CONVERSATION_BUSY_STOP_FIRST:'请先停止当前执行，再移动会话。',FOLDER_HAS_RUNNING_SESSION:'文件夹内仍有会话正在执行，请先停止后再删除。',FOLDER_CHANGED_REFRESH:'共享配置已被其他会话更新，请重新打开后编辑。',MODEL_OWNER_GRANT_EXPIRED:'本次执行时限已用完，历史消息仍保留。发送新消息即可继续。',SESSION_REQUEST_CAP:'此会话已达到模型请求上限，历史消息仍保留。',PAID_WINDOW_CLOSED:'模型运行窗口已关闭。消息已保存，新的运行额度开启后可继续。',MODEL_WALL_BUDGET:'本次运行窗口已到期。消息已保存。',MODEL_USD_BUDGET:'当前模型额度不足，消息已保存。',PI_SESSION_ALREADY_RUNNING:'这个会话已有 Pi 进程在执行，请勿重复启动。',PI_BATCH_ALREADY_RUNNING:'独占实验批次正在执行。消息已保存，批次结束后可继续。',PI_CONVERSATION_CAPACITY:'已有 3 个任务在执行。消息已保存，可在空闲后继续。',PROVIDER_USAGE_UNKNOWN_STOP:'有模型请求的用量尚未核实，已暂停新请求。这是记账保护，与 token 余额不足不同。',AUTH_REQUIRED:'本地连接暂不可用，请刷新页面。'};
Object.assign(errors,{PROVIDER_TOKEN_BOUND_VIOLATION:'模型输出超出请求长度，本次回复未完成；实际用量已记录，可分段继续。',PROVIDER_RESERVATION_EXCEEDED:'模型实际用量超过预留额度，已记录费用并暂停后续请求，等待核对。',MODEL_OUTPUT_TRUNCATED:'这条回复因输出长度限制被截断，尚未完成。已保留收到的内容；发送“继续”可接着处理。',MODEL_OUTPUT_BUDGET_TOO_SMALL:'当前上下文无法预留正常输出空间，已停止本次模型请求，避免只返回一两个字。',MODEL_CONTEXT_BYTE_LIMIT:'本次上下文仍超过请求容量，已停止发送。历史记录已保留，需要进一步精简上下文。',CHAT_TURN_REQUEST_CAP:'这条历史消息达到当时配置的模型调用上限，已有结果保留，可继续处理。',PRODUCT_DELIVERY_INCOMPLETE:'本轮自动执行已结束，但交付检查尚未通过。失败项和产物已保留，可继续修复。'});
function notice(s){$('#composer-notice').textContent=errors[window.ConversationFlow.errorCode(s)]||s||''}
function collapse(value,persist=true){document.body.classList.toggle('sidebar-collapsed',value);$('#session-sidebar').hidden=value;$('#sidebar-toggle').setAttribute('aria-expanded',String(!value));$('#sidebar-toggle').setAttribute('aria-label',value?'展开左侧栏':'收起左侧栏');$('#sidebar-toggle').title=value?'展开左侧栏':'收起左侧栏';if(persist)localStorage.setItem('bf-chat-sidebar',value?'closed':'open')}
$('#sidebar-toggle').onclick=()=>collapse(!document.body.classList.contains('sidebar-collapsed'));collapse(matchMedia('(max-width:760px)').matches||localStorage.getItem('bf-chat-sidebar')==='closed',false);
matchMedia('(max-width:760px)').addEventListener('change',e=>collapse(e.matches||localStorage.getItem('bf-chat-sidebar')==='closed',false));
function sectionVisible(value){document.body.classList.toggle('sections-hidden',!value);$('#section-inspector').hidden=!value;$('#sections-toggle').setAttribute('aria-expanded',String(value));localStorage.setItem('bf-chat-sections',value?'open':'closed')}
$('#sections-toggle').onclick=()=>sectionVisible(document.body.classList.contains('sections-hidden'));$('#close-sections').onclick=()=>sectionVisible(false);sectionVisible(localStorage.getItem('bf-chat-sections')==='open');
function list(){if(window.Sidebar){window.Sidebar.render(conversations,folders,selected);return}const markup=c=>`<button class="session-item ${c.id===selected?'selected':''}" data-session-id="${esc(c.id)}" title="${esc(c.title)}"><span class="session-dot ${c.status==='RUNNING'?'running':''}"></span><span>${esc(c.title)}</span></button>`;$('#sessions').innerHTML=conversations.filter(c=>!c.legacy).map(markup).join('');$('#legacy-sessions').innerHTML=conversations.filter(c=>c.legacy).map(markup).join('');$('#history-list summary').textContent='历史实验会话 · '+conversations.filter(c=>c.legacy).length;document.querySelectorAll('[data-session-id]').forEach(b=>b.onclick=()=>select(b.dataset.sessionId))}
async function refresh(){try{const value=await api('/api/conversations');conversations=value.sessions;folders=value.folders||[];list();$('#connection').textContent='本地已连接';window.Product?.showReadiness();if(selected&&!conversations.some(c=>c.id===selected)){await select(null)}else if(selected){await refreshDetail()}}catch(e){$('#connection').textContent='连接中断';notice(e.message)}}
async function refreshDetail(){const id=selected;if(!id)return;const entry=conversations.find(c=>c.id===id);if(!entry)return;if(entry.legacy){const detail=await api('/api/jobs/'+id);if(id!==selected)return;current=entry;execution=detail;events=detail.events.map((e,i)=>({seq:i,data:e.data,time:e.time}));}else{const observed=cursor;const detail=await api('/api/conversations/'+id);if(id!==selected)return;const later=events.filter(e=>e.seq>observed&&e.data.type==='conversation_status').at(-1)?.data;current=later?{...detail,status:later.status,error:later.error}:detail;execution=detail.execution;if(cursor===0){events=detail.events;cursor=detail.event_cursor??events.at(-1)?.seq??0}}render();renderSections();window.dispatchEvent(new CustomEvent('bf-selection',{detail:{id:selected}}))}
async function select(id){if(id?.startsWith('job-')){const job=await api('/api/jobs/'+id);id=job.owner?.startsWith('pi-')?job.owner:null;section='files'}if(stream)stream.abort();stream=null;selected=id;if(matchMedia('(max-width:760px)').matches)collapse(true,false);sessionStorage.setItem('bf-chat-selected',id||'');current=null;execution=null;events=[];cursor=0;notice('');$('#message-input').value=localStorage.getItem('bf-chat-draft-'+(id||'new'))||'';list();render();renderSections();window.dispatchEvent(new CustomEvent('bf-selection',{detail:{id:selected,phase:'loading'}}));if(id){await refreshDetail();if(!current?.legacy)subscribe(id)}window.dispatchEvent(new CustomEvent('bf-selection',{detail:{id:selected}}))}
async function newChat(fid=null){window.Product?.clearAttachments();newFolder=fid;sessionStorage.setItem('bf-chat-folder',fid||'');await select(null);$('#runtime-mode').click();$('#message-input').focus()}
$('#new-chat').onclick=()=>newChat();$('#refresh').onclick=()=>location.reload();
async function subscribe(id){const controller=new AbortController();stream=controller;while(selected===id&&!controller.signal.aborted){try{const response=await fetch('/api/conversations/'+id+'/events?after='+cursor,{headers:headers(),signal:controller.signal});if(!response.ok)throw Error('实时连接暂不可用');window.dispatchEvent(new CustomEvent('bf-runtime-connection',{detail:{owner:id,connected:true}}));const reader=response.body.getReader();const decoder=new TextDecoder();let buffer='';while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const lines=buffer.split('\n');buffer=lines.pop();for(const line of lines){if(!line)continue;const event=JSON.parse(line);if(event.seq>cursor){events.push(event);cursor=event.seq;window.dispatchEvent(new CustomEvent('bf-runtime-events',{detail:{owner:id,events:[event]}}));if(event.data.type==='conversation_status'){current.status=event.data.status;current.error=event.data.error;refreshSectionsSoon()}if(['product_record','turn_complete','tool_execution_end','message_withdrawn'].includes(event.data.type))refreshSectionsSoon();scheduleRender()}}}}catch(e){if(controller.signal.aborted)break;$('#connection').textContent='正在重连';window.dispatchEvent(new CustomEvent('bf-runtime-connection',{detail:{owner:id,connected:false}}));await new Promise(r=>setTimeout(r,1200))}}}
let sectionTimer;function refreshSectionsSoon(){clearTimeout(sectionTimer);sectionTimer=setTimeout(async()=>{if(selected&&!current?.legacy){const id=selected,observed=cursor;try{const d=await api('/api/conversations/'+id);if(id===selected){const later=events.filter(e=>e.seq>observed&&e.data.type==='conversation_status').at(-1)?.data;current=later?{...d,status:later.status,error:later.error}:d;execution=d.execution;renderSections();render();if(document.body.classList.contains('developer-mode'))window.dispatchEvent(new CustomEvent('bf-selection',{detail:{id}}))}}catch{}}},500)}
function scheduleRender(){if(renderTimer)return;renderTimer=setTimeout(()=>{renderTimer=null;render()},50)}
const messageIcons={
  copy:'<rect x="5" y="5" width="8" height="9" rx="2"/><path d="M10 5V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h1"/>',
  recall:'<path d="m6 3-4 4 4 4M2 7h8a4 4 0 0 1 4 4v2"/>',
  done:'<path d="m3 8 3 3 7-7"/>'
};
function messageIcon(name){return `<svg viewBox="0 0 16 16" fill="none" aria-hidden="true">${messageIcons[name]}</svg>`}
function messageActions(record){
  if(record.kind==='assistant'&&record.text&&!record.pending){
    const u=record.usage,known=!record.failed&&u&&Number.isInteger(u.totalTokens)&&u.totalTokens>0;
    const input=u&&(u.input??0)+(u.cacheRead??0)+(u.cacheWrite??0),output=u?.output;
    const tokens=known&&Number.isInteger(input)&&Number.isInteger(output)?`输入 ${input.toLocaleString('zh-CN')} · 输出 ${output.toLocaleString('zh-CN')} tokens`:known?u.totalTokens.toLocaleString('zh-CN')+' tokens':'用量未返回';
    const title=known?'模型返回的本次回答 token 用量（包含输入上下文和输出）':'模型没有返回可核实的 token 用量';
    return `<div class="message-actions assistant-actions"><button class="message-action copy-message" data-copy="${esc(record.key)}" aria-label="复制回答" title="复制">${messageIcon('copy')}</button><span class="token-usage" title="${title}">${tokens}</span><span class="sr-only copy-feedback" aria-live="polite"></span></div>`;
  }
  if(record.kind!=='user')return '';
  const value=record.time, date=new Date(typeof value==='number'?(value<1e12?value*1000:value):value);
  const timestamp=Number.isFinite(date.getTime())?`<time datetime="${date.toISOString()}" title="${esc(date.toLocaleString('zh-CN',{hourCycle:'h23'}))}">${date.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hourCycle:'h23'})}</time>`:'';
  return `<div class="message-actions">${timestamp}<button class="message-action copy-message" data-copy="${esc(record.key)}" aria-label="复制这条消息" title="复制">${messageIcon('copy')}</button>${record.id?`<button class="message-action recall-message" data-recall="${esc(record.id)}" aria-label="撤回并编辑这条消息" title="撤回并编辑" ${current?.status==='RECALLING'?'disabled':''}>${messageIcon('recall')}</button>`:''}<span class="sr-only copy-feedback" aria-live="polite"></span></div>`;
}
function render(){const empty=!selected;$('#chat-main').classList.toggle('is-empty',empty);$('#conversation-title').textContent=current?.title||'新对话';$('#conversation-status').textContent=empty?'':(current?.error&&current.status==='BLOCKED'?'模型受阻 · '+(current.error==='PROVIDER_USAGE_UNKNOWN_STOP'?'用量待核实':current.error==='MODEL_WALL_BUDGET'?'运行时限到期':current.error==='PAID_WINDOW_CLOSED'?'运行窗口关闭':'等待处理'):names[current?.status]||'');$('#welcome').hidden=!empty;const live=['RUNNING','STARTING'].includes(current?.status);const fid=current?.folder_id||(!selected?newFolder:null);const folder=folders.find(f=>f.id===fid);$('#folder-context').hidden=!folder;$('#folder-context').textContent=folder?folder.name:'';$('#folder-context').title='在 Lab 查看项目共享配置';$('#folder-context').onclick=()=>window.Sidebar?.configure(fid);$('#stop-chat').hidden=!live;$('#send-message').disabled=sending||current?.status==='RECALLING'||!$('#message-input').value.trim();$('#composer-state').textContent=live?'可随时补充消息':'DeepSeek Flash';$('#message-input').placeholder=empty?'描述现场、希望得到的结果，或直接说出想法；不清楚的条件可以由 Agent 先作假设…':current?.legacy?'历史会话只读；发送将创建一个新会话…':'补充要求，或继续与 Agent 对话…';$('#composer-hint').textContent=current?.legacy?'历史记录保留原样 · 新消息将在新会话中执行':'Enter 发送 · Shift + Enter 换行';window.Product?.showReadiness(current?.readiness);
  window.Product?.handoff(current);
  const pane=$('#conversation'),atBottom=pane.scrollHeight-pane.scrollTop-pane.clientHeight<100;
  const states=new Map([...pane.querySelectorAll('details[data-key]')].map(e=>[e.dataset.key,e.open]));
  const {records,groups}=window.ConversationFlow.project(events,{legacy:current?.legacy,live});
  if(current?.error&&!records.some(r=>r.code===window.ConversationFlow.errorCode(current.error)))groups.push({kind:'error',key:'current-error',code:current.error,text:errors[current.error]||current.error});
  window.Cases?.update();
  pane.innerHTML=groups.map(r=>r.kind==='progress'?window.ConversationFlow.render(r,{esc,markdown,states}):r.kind==='error'?window.ConversationFlow.renderError(r,{esc,errors,states}):r.kind==='product'?(window.Product?.card(current?.product,r.revision)||''):r.kind==='status'?`<p class="chat-status">${esc(r.text)}</p>`:r.text?`<article class="message ${r.kind}"><div class="message-bubble"><div class="message-label">${r.kind==='user'?'你':r.kind==='error'?'执行信息':'BF Agent'}</div><div class="message-text">${r.kind==='assistant'?markdown(r.text):esc(errors[r.text]||r.text)}${r.pending?'<span class="stream-caret">▍</span>':''}</div></div>${messageActions(r)}</article>`:'').join('')+(live?'<div class="working"><span></span> '+esc(current?.status==='STARTING'?'正在准备回复':window.Product?.activity(events)||'正在等待模型响应')+'</div>':'');if(atBottom||empty)pane.scrollTop=pane.scrollHeight;window.Product?.bindCards(pane);window.StudioExperience?.chatCard(pane);pane.querySelectorAll('[data-recall]').forEach(b=>b.onclick=()=>window.Sidebar?.recall(b.dataset.recall));
  pane.querySelectorAll('[data-open-trace]').forEach(b=>b.onclick=()=>window.BFDeveloper?.openTrace());
  pane.querySelectorAll('[data-copy]').forEach(b=>b.onclick=async()=>{
    const record=records.find(r=>r.key===b.dataset.copy);if(!record)return;
    try{await navigator.clipboard.writeText(record.text);b.innerHTML=messageIcon('done');b.title='已复制';b.setAttribute('aria-label','已复制');b.parentElement.querySelector('.copy-feedback').textContent='消息已复制';setTimeout(()=>{if(b.isConnected){b.innerHTML=messageIcon('copy');b.title='复制';b.setAttribute('aria-label','复制这条消息')}},1500)}catch{notice('复制失败，请选中消息文字后复制。')}
  });
}
$('#message-input').addEventListener('input',()=>{localStorage.setItem('bf-chat-draft-'+(selected||'new'),$('#message-input').value);$('#send-message').disabled=sending||!$('#message-input').value.trim()});
$('#message-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#composer').requestSubmit()}});
$('#composer').onsubmit=async e=>{
  e.preventDefault();if(sending)return;const text=$('#message-input').value.trim();if(!text)return;
  if(current?.status==='RECALLING')return;const prior=selected,create=!selected||current?.legacy;const folder_id=create?(current?.folder_id||newFolder):null;
  const task=current?.legacy?null:(current?.task_id||null);
  const path=create?'/api/conversations':'/api/conversations/'+selected+'/messages';
  let pending;try{pending=JSON.parse(sessionStorage.getItem('bf-chat-pending'))}catch{}
  if(!pending||pending.path!==path||pending.text!==text||pending.task!==task||pending.folder_id!==folder_id||pending.attachments!==JSON.stringify(window.Product?.creationPayload()?.attachments||[])){pending={path,text,task,folder_id,attachments:JSON.stringify(window.Product?.creationPayload()?.attachments||[]),operation_id:crypto.randomUUID()};sessionStorage.setItem('bf-chat-pending',JSON.stringify(pending))}
  sending=true;render();notice('');
  try{
    const reply=await api(path,{text,operation_id:pending.operation_id,...(create?{task_id:task,folder_id,...(window.Product?.creationPayload()||{})}:{})});
    sessionStorage.removeItem('bf-chat-pending');if(create)window.Product?.clearAttachments();localStorage.removeItem('bf-chat-draft-'+(prior||'new'));
    // A response from another conversation must not erase the current draft or move focus.
    if(selected===prior){$('#message-input').value='';if(create){await refresh();await select(reply.id)}else await refreshDetail()}
  }catch(err){notice(err.message)}finally{sending=false;render();if(selected===prior||create)$('#message-input').focus()}
};
$('#stop-chat').onclick=async()=>{try{await api('/api/conversations/'+selected+'/stop',{});await refreshDetail()}catch(e){notice(e.message)}};
const fmt=v=>v===undefined||v===null?'—':typeof v==='object'?JSON.stringify(v):String(v);
const metric=(k,v)=>`<div class="section-metric"><span>${esc(k)}</span><b>${esc(fmt(v))}</b></div>`;
function renderSections(){
  if(window.EngineeringWorkspace?.active()){window.EngineeringWorkspace.render();return;}
  if(!['model','proposal','files','deployment'].includes(section))section='proposal';
  document.querySelectorAll('[data-section]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.section===section)));
  if(window.Product)window.Product.panel($('#section-content'),section,current,execution);
}
document.querySelectorAll('[data-section]').forEach(b=>b.onclick=()=>{section=b.dataset.section;localStorage.setItem('bf-section',section);renderSections()});
window.BF={api,esc,refreshSections:renderSections,sectionVisible,getSelection:()=>selected,getTitle:()=>conversations.find(c=>c.id===selected)?.title||'新项目',select,newChat,refresh,refreshDetail,getFolders:()=>folders,getCurrent:()=>current,getEvents:()=>events,getFolder:()=>current?.folder_id||(!selected?newFolder:null),setDraft:text=>{$('#message-input').value=text;$('#message-input').dispatchEvent(new Event('input'));$('#message-input').focus()},error:notice};
(async()=>{await refresh();if(selected)await select(selected);else{render();renderSections()}})();setInterval(async()=>{try{const v=await api('/api/conversations');conversations=v.sessions;folders=v.folders||[];list()}catch{}},5000);

/* Pane resizing is browser-local and never changes a conversation or its work. */
(() => {
  const key='bf-panel-widths.v1', root=document.documentElement;
  let preferred={}, frame=0, drag=null, observedMap=null;
  try{const saved=JSON.parse(localStorage.getItem(key)||'{}');for(const side of ['left','right','engineering','progress'])if(Number.isFinite(saved?.[side]))preferred[side]=saved[side]}catch{}
  const clamp=(n,min,max)=>Math.round(Math.max(min,Math.min(max,n)));
  const visible=el=>!!el&&el.getClientRects().length>0;
  const persist=()=>{try{localStorage.setItem(key,JSON.stringify(preferred))}catch{}};
  const panes=[
    {side:'left',id:'session-sidebar',label:'调整左侧栏宽度',sign:1},
    {side:'progress',id:'execution-progress',label:'调整执行进展宽度',sign:-1},
    {side:'right',id:'section-inspector',label:'调整右侧栏宽度',sign:-1},
    {side:'right',id:'map-inspector',label:'调整全景详情栏宽度',sign:-1},
    {side:'right',id:'product-inspector',label:'调整产品详情栏宽度',sign:-1},
  ];
  const css=(name,value)=>{const next=value+'px';if(root.style.getPropertyValue(name)!==next)root.style.setProperty(name,next)};
  function layout(){
    frame=0;
    const width=root.clientWidth, leftVisible=visible(document.getElementById('session-sidebar'));
    const productMode=document.body.classList.contains('product-mode');
    const mapMode=document.body.classList.contains('panorama-mode')||productMode;
    const progressLayout=document.body.classList.contains('execution-progress-layout');
    const progressOverlay=progressLayout&&width<=1280;
    const progressVisible=visible(document.getElementById('execution-progress'));
    const taskDocked=width>(progressLayout?1280:850)&&visible(document.getElementById('section-inspector'));
    const mapDocked=mapMode&&width>760;
    const chatMinimum=progressLayout&&!progressOverlay?420:360;
    const leftMax=Math.max(180,Math.min(productMode&&width>900?260:420,width<=620?width-48:width-chatMinimum-(taskDocked?(progressLayout?320:240):mapDocked?240:0)-(progressLayout&&progressVisible&&!progressOverlay?280:0)));
    const left=clamp(preferred.left??(width<=620?220:width<=1100?200:224),180,leftMax);
    const taken=leftVisible&&width>620?left:0;
    const engineering=document.body.classList.contains('engineering-workspace-active');
    const engineeringOverlay=engineering&&(progressOverlay||document.body.classList.contains('studio-compact')||width<=850);
    const available=width-taken;
    const progressMax=Math.max(280,Math.min(440,progressOverlay?width:available-chatMinimum-(taskDocked?320:0)));
    const progress=clamp(preferred.progress??320,280,progressMax);
    const progressTaken=progressLayout&&progressVisible&&!progressOverlay?progress:0;
    const rightMinimum=progressLayout&&!progressOverlay?320:240;
    const rightMax=Math.max(rightMinimum,Math.min(engineering?1120:640,engineeringOverlay?width:width>850?width-taken-progressTaken-chatMinimum:width-16));
    const rightKey=engineering?'engineering':'right';
    const right=clamp(preferred[rightKey]??(engineering?(engineeringOverlay?Math.min(620,width):progressVisible&&!progressOverlay?420:available*.64):(width>=1550?330:width<=850?280:width<=1100?250:286)),rightMinimum,rightMax);
    if(engineering)document.getElementById('section-inspector').style.setProperty('--ew-top',(document.querySelector('.studio-nav-shell')||document.querySelector('.topbar')).getBoundingClientRect().height+'px');
    const mapMax=Math.max(240,Math.min(productMode?(width<1400?300:420):640,width-taken-(width<=1150?32:48)-(productMode?500:302)));
    const map=clamp(preferred.right??(width<=1150?260:300),240,mapMax);
    css('--panel-progress-width',progress);css('--panel-left-width',left);css('--panel-right-width',right);css('--panel-map-width',map);
    const newMap=document.getElementById(document.body.classList.contains('product-mode')?'product-inspector':'map-inspector');
    if(newMap!==observedMap){if(observedMap)observer.unobserve(observedMap);observedMap=newMap;if(newMap)observer.observe(newMap)}
    for(const pane of panes){
      const el=document.getElementById(pane.id), handle=pane.handle;
      pane.preference=pane.id==='section-inspector'&&engineering?'engineering':pane.side;
      handle.hidden=!visible(el)||(pane.id==='map-inspector'&&width<=760)||(pane.id==='product-inspector'&&width<=900);
      if(handle.hidden)continue;
      const rect=el.getBoundingClientRect();
      pane.min=pane.side==='left'?180:pane.side==='progress'?280:pane.id==='section-inspector'?rightMinimum:240;
      pane.max=pane.side==='left'?leftMax:pane.side==='progress'?progressMax:['map-inspector','product-inspector'].includes(pane.id)?mapMax:rightMax;
      handle.style.left=(pane.sign===1?rect.right-5:rect.left-5)+'px';
      handle.style.top=rect.top+'px';handle.style.height=rect.height+'px';
      handle.setAttribute('aria-valuemin',pane.min);handle.setAttribute('aria-valuemax',pane.max);
      handle.setAttribute('aria-valuenow',Math.round(rect.width));handle.setAttribute('aria-valuetext',Math.round(rect.width)+' 像素');
    }
  }
  const schedule=()=>{if(!frame)frame=requestAnimationFrame(layout)};
  function finish(cancel=false){
    if(!drag)return;
    const {pane,pointer,prior}=drag;drag=null;
    if(cancel){if(prior===undefined)delete preferred[pane.preference||pane.side];else preferred[pane.preference||pane.side]=prior}else persist();
    document.body.classList.remove('panel-resizing');pane.handle.removeAttribute('aria-grabbed');
    if(pane.handle.hasPointerCapture(pointer))pane.handle.releasePointerCapture(pointer);
    schedule();
  }
  for(const pane of panes){
    const h=document.createElement('div');pane.handle=h;
    h.className='panel-resizer';h.hidden=true;h.tabIndex=0;h.setAttribute('role','separator');h.setAttribute('aria-orientation','vertical');
    h.setAttribute('aria-controls',pane.id);h.setAttribute('aria-label',pane.label);h.title='拖动调整宽度 · 双击恢复默认 · 方向键微调';document.body.append(h);
    h.addEventListener('pointerdown',e=>{
      if(e.button!==0||drag)return;
      e.preventDefault();h.focus({preventScroll:true});h.setPointerCapture(e.pointerId);
      drag={pane,pointer:e.pointerId,x:e.clientX,width:document.getElementById(pane.id).getBoundingClientRect().width,prior:preferred[pane.preference||pane.side]};
      h.setAttribute('aria-grabbed','true');document.body.classList.add('panel-resizing');
    });
    h.addEventListener('pointermove',e=>{if(drag?.pane!==pane||drag.pointer!==e.pointerId)return;preferred[pane.preference||pane.side]=clamp(drag.width+(e.clientX-drag.x)*pane.sign,pane.min,pane.max);schedule()});
    h.addEventListener('pointerup',()=>finish());h.addEventListener('pointercancel',()=>finish(true));h.addEventListener('lostpointercapture',()=>finish(true));
    h.addEventListener('dblclick',()=>{delete preferred[pane.preference||pane.side];persist();schedule()});
    h.addEventListener('keydown',e=>{
      if(drag){if(e.key==='Escape'){e.preventDefault();finish(true)}return}
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
      e.preventDefault();const current=document.getElementById(pane.id).getBoundingClientRect().width;
      preferred[pane.preference||pane.side]=e.key==='Home'?pane.min:e.key==='End'?pane.max:clamp(current+(e.key==='ArrowRight'?1:-1)*pane.sign*(e.shiftKey?40:10),pane.min,pane.max);
      persist();schedule();
    });
  }
  const observer=new ResizeObserver(schedule);
  for(const el of [document.querySelector('.shell'),document.querySelector('.app-body'),document.getElementById('session-sidebar'),document.getElementById('execution-progress'),document.getElementById('section-inspector')])if(el)observer.observe(el);
  new MutationObserver(()=>{if(drag)finish(true);schedule()}).observe(document.body,{attributes:true,attributeFilter:['data-studio-mode']});
  // Collapse and overlay changes also affect the available pane bounds.
  new MutationObserver(schedule).observe(document.body,{attributes:true,attributeFilter:['class']});
  window.addEventListener('resize',()=>{if(drag)finish(true);schedule()});window.addEventListener('blur',()=>finish(true));
  window.BFPanelSizing={refresh:schedule,reset:()=>{if(drag)finish(true);preferred={};persist();schedule()}};schedule();
})();
