(() => {
  const {api,esc}=window.BF;const q=s=>document.querySelector(s);
  let items=[],folders=[],selection=null,menu=null,signature=null;
  let folded=new Set(JSON.parse(localStorage.getItem('bf-folded-folders')||'[]'));
  const toolLabels={read:'读取文件',edit:'编辑文件',write:'写入文件',bash:'终端',bf_experiment:'运行实验',bf_job:'实验状态',bf_inspect_run:'查看结果',bf_submit:'提交方案',bf_memory:'共享记忆'};
  function closeMenu(){menu?.remove();menu=null}
  document.addEventListener('click',e=>{if(menu&&!menu.contains(e.target)&&!e.target.closest('[data-menu]'))closeMenu()});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu()});
  function popup(button,actions){
    closeMenu();menu=document.createElement('div');menu.className='organize-menu';menu.setAttribute('role','menu');
    menu.innerHTML=actions.map((a,i)=>`<button role="menuitem" data-action="${i}" class="${a.danger?'danger':''}">${esc(a.label)}</button>`).join('');
    document.body.append(menu);const box=button.getBoundingClientRect();menu.style.left=Math.min(box.right,innerWidth-235)+'px';menu.style.top=Math.max(8,Math.min(box.top,innerHeight-menu.offsetHeight-12))+'px';
    menu.querySelectorAll('button').forEach(b=>b.onclick=async()=>{const action=actions[Number(b.dataset.action)];closeMenu();try{await action.run()}catch(e){BF.error(e.message)}});menu.querySelector('button')?.focus();
  }
  function dialog(title,html,submitLabel,onSubmit){
    const d=document.createElement('dialog');d.className='organizer-dialog';d.setAttribute('aria-label',title);
    d.innerHTML=`<form><header><h2>${esc(title)}</h2><button type="button" class="quiet close-dialog" aria-label="关闭">×</button></header><div class="dialog-body">${html}</div><p class="dialog-error" role="status"></p><footer><button type="button" class="cancel-dialog">取消</button>${submitLabel?`<button class="primary" type="submit">${esc(submitLabel)}</button>`:''}</footer></form>`;
    document.body.append(d);const close=()=>{d.close();d.remove()};d.querySelector('.close-dialog').onclick=close;d.querySelector('.cancel-dialog').onclick=close;d.addEventListener('cancel',()=>d.remove());
    d.querySelector('form').onsubmit=async e=>{e.preventDefault();const b=d.querySelector('[type=submit]');if(!b)return;b.disabled=true;try{await onSubmit(d);close()}catch(err){d.querySelector('.dialog-error').textContent=err.message;b.disabled=false}};
    d.showModal();d.querySelector('input,textarea,select')?.focus();return d;
  }
  async function rename(kind,item){dialog(kind==='folder'?'文件夹改名':'会话改名',`<label>名称<input name="name" maxlength="80" value="${esc(item.name||item.title)}" required></label>`,'保存',async d=>{await api('/api/'+(kind==='folder'?'folders':'sidebar')+'/'+item.id,{action:'rename',name:d.querySelector('[name=name]').value});await BF.refresh()})}
  function options(value){return '<option value="">未分类</option>'+folders.map(f=>`<option value="${esc(f.id)}" ${f.id===value?'selected':''}>${esc(f.name)}</option>`).join('')}
  function move(item){dialog('移动会话',`<label>目标文件夹<select name="folder">${options(item.folder_id)}</select></label><p class="dialog-note">下一次执行使用目标文件夹的共享 Memory、提示词与工具配置。</p>`,'移动',async d=>{await api('/api/sidebar/'+item.id,{action:'move',folder_id:d.querySelector('[name=folder]').value||null});await BF.refresh()})}
  function createFolder(){dialog('新建文件夹','<label>文件夹名称<input name="name" placeholder="例如：旋转采能设计" maxlength="80" required></label><p class="dialog-note">文件夹内的会话共享 Memory、提示词、工具与 Harness 配置。</p>','创建',async d=>{const f=await api('/api/folders',{name:d.querySelector('[name=name]').value});await BF.refresh();await BF.newChat(f.id)})}
  function sessionMenu(button,item){popup(button,[{label:'改名',run:()=>rename('session',item)},{label:'移动到…',run:()=>move(item)},{label:'删除会话',danger:true,run:async()=>{await api('/api/sidebar/'+item.id,{action:'delete'});await BF.refresh();BF.error('会话已移至最近删除，可恢复。')}}])}
  function folderMenu(button,folder){popup(button,[{label:'新建会话',run:()=>BF.newChat(folder.id)},{label:'在 Lab 编辑共享配置…',run:()=>configure(folder.id)},{label:'改名',run:()=>rename('folder',folder)},{label:'上移',run:async()=>{await api('/api/folders/'+folder.id,{action:'reorder',direction:'up'});await BF.refresh()}},{label:'下移',run:async()=>{await api('/api/folders/'+folder.id,{action:'reorder',direction:'down'});await BF.refresh()}},{label:'删除文件夹',danger:true,run:()=>dialog('删除文件夹',`<p>删除“${esc(folder.name)}”后，里面的会话移至未分类。文件夹可以从最近删除中恢复。</p>`,'删除文件夹',async()=>{await api('/api/folders/'+folder.id,{action:'delete'});await BF.newChat();await BF.refresh()})}])}
  const row=c=>`<div class="session-row ${c.id===selection?'selected':''}" draggable="true" data-drag-session="${esc(c.id)}"><button class="session-item" data-session-id="${esc(c.id)}" title="${esc(c.title)}"><span class="session-dot ${['RUNNING','STARTING'].includes(c.status)?'running':c.status==='BLOCKED'||c.status==='FAILED'?'attention':''}"></span><span>${esc(window.StudioExperience?.projectLabel(c)||c.title)}</span></button><button class="row-menu" data-menu="session" data-id="${esc(c.id)}" aria-label="会话菜单：${esc(c.title)}" title="会话菜单">⋯</button></div>`;
  function render(list,groups,selected){
    const query=(q("#studio-project-search")?.value||"").trim().toLocaleLowerCase();
    const matches=c=>!query||(window.StudioExperience?.projectLabel(c)||c.title).toLocaleLowerCase().includes(query)||c.title.toLocaleLowerCase().includes(query)||groups.some(f=>f.id===c.folder_id&&f.name.toLocaleLowerCase().includes(query));
    const next=JSON.stringify([list.map(c=>[c.id,c.title,c.folder_id,c.status,c.legacy,window.StudioExperience?.projectLabel(c)]),groups.map(f=>[f.id,f.name,f.position]),selected,BF.getFolder(),[...folded],query]);
    items=list;folders=groups;selection=selected;if(next===signature)return;signature=next;
    q('#folder-tree').innerHTML=folders.filter(f=>!query||f.name.toLocaleLowerCase().includes(query)||items.some(c=>c.folder_id===f.id&&matches(c))).map(f=>`<section class="folder-group" data-drop-folder="${esc(f.id)}"><div class="folder-heading ${BF.getFolder()===f.id?'current':''}"><button class="folder-fold" data-fold="${esc(f.id)}" aria-label="${folded.has(f.id)?'展开':'收起'}文件夹 ${esc(f.name)}" aria-expanded="${!folded.has(f.id)}"><svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m6 4 4 4-4 4"/></svg></button><button class="folder-name" data-folder="${esc(f.id)}" title="在此文件夹新建对话">${esc(f.name)}</button>${items.some(c=>c.folder_id===f.id&&['RUNNING','STARTING'].includes(c.status))?`<span class="folder-activity" title="此文件夹正在执行的任务">${items.filter(c=>c.folder_id===f.id&&['RUNNING','STARTING'].includes(c.status)).length} 运行</span>`:''}<button class="row-menu" data-menu="folder" data-id="${esc(f.id)}" aria-label="文件夹菜单：${esc(f.name)}" title="文件夹菜单">⋯</button></div><div ${folded.has(f.id)&&!query?'hidden':''}>${items.filter(c=>c.folder_id===f.id&&matches(c)).map(row).join('')||'<p class="empty-folder">暂无会话</p>'}</div></section>`).join('');
    q('#sessions').innerHTML=items.filter(c=>!c.legacy&&!c.folder_id&&matches(c)).map(row).join('');
    q('#legacy-sessions').innerHTML=items.filter(c=>c.legacy&&!c.folder_id&&matches(c)).map(row).join('');
    const historyMatches=items.filter(c=>c.legacy&&!c.folder_id&&matches(c)).length;
    q('#history-list summary').textContent='历史实验会话 · '+historyMatches;
    if(query&&historyMatches)q('#history-list').open=true;
    document.querySelectorAll('[data-session-id]').forEach(b=>b.onclick=()=>BF.select(b.dataset.sessionId));
    document.querySelectorAll('[data-folder]').forEach(b=>b.onclick=()=>BF.newChat(b.dataset.folder));
    document.querySelectorAll('[data-fold]').forEach(b=>b.onclick=()=>{const id=b.dataset.fold;folded.has(id)?folded.delete(id):folded.add(id);localStorage.setItem('bf-folded-folders',JSON.stringify([...folded]));render(items,folders,selection)});
    document.querySelectorAll('[data-menu]').forEach(b=>b.onclick=e=>{e.stopPropagation();if(b.dataset.menu==='session')sessionMenu(b,items.find(c=>c.id===b.dataset.id));else folderMenu(b,folders.find(f=>f.id===b.dataset.id))});
    document.querySelectorAll('[data-drag-session]').forEach(r=>r.ondragstart=e=>{e.dataTransfer.setData('text/bf-session',r.dataset.dragSession);e.dataTransfer.effectAllowed='move'});
    document.querySelectorAll('[data-drop-folder]').forEach(r=>{r.ondragover=e=>{e.preventDefault();r.classList.add('drag-over')};r.ondragleave=()=>r.classList.remove('drag-over');r.ondrop=async e=>{e.preventDefault();r.classList.remove('drag-over');const id=e.dataTransfer.getData('text/bf-session');if(!items.some(c=>c.id===id))return;try{await api('/api/sidebar/'+id,{action:'move',folder_id:r.dataset.dropFolder});await BF.refresh()}catch(err){BF.error(err.message)}}});
  }
  async function configure(fid){
    window.BFDeveloper?.openModule('memory');
    const data=await api('/api/organization'),folder=data.folders.find(f=>f.id===fid);if(!folder)throw Error('文件夹已删除');
    const dev=await api('/api/developer');const revisions=dev.revisions.filter(r=>r.validation?.status==='VALIDATED');
    const d=dialog(folder.name+' · 共享配置',`<nav class="config-tabs"><button type="button" data-config-tab="memory" aria-pressed="true">Memory</button><button type="button" data-config-tab="prompt" aria-pressed="false">提示词</button><button type="button" data-config-tab="tools" aria-pressed="false">Tools</button><button type="button" data-config-tab="harness" aria-pressed="false">Harness</button></nav><section data-config-pane="memory"><label>共享记忆<textarea name="memory" rows="9" maxlength="16000" placeholder="项目背景、偏好、可复用经验…">${esc(folder.config.memory)}</textarea></label><p class="dialog-note">同一文件夹内的会话共享此笔记。启用 bf_memory 后，Agent 也可读写；内容作为待验证记忆保留。</p></section><section data-config-pane="prompt" hidden><label>共享提示词<textarea name="prompt" rows="9" maxlength="16000" placeholder="此文件夹内所有会话遵循的工作要求…">${esc(folder.config.prompt)}</textarea></label></section><section data-config-pane="tools" hidden><p class="dialog-note">选择 Agent 可调用的工具。</p><div class="tool-options">${data.tools.map(t=>`<label><input type="checkbox" name="tool" value="${esc(t)}" ${folder.config.tools.includes(t)?'checked':''}><span>${esc(toolLabels[t]||t)}<small>${esc(t)}</small></span></label>`).join('')}</div></section><section data-config-pane="harness" hidden><label>共享 Harness<select name="harness"><option value="">默认 Harness</option>${revisions.map(r=>`<option value="${esc(r.id)}" ${folder.config.harness_revision===r.id?'selected':''}>${esc(r.name)} · ${r.id.slice(0,8)}</option>`).join('')}</select></label><p class="dialog-note">可在 Lab 中编辑并校验 Harness，再在这里选择。文件夹内会话下一次启动时加载此版本。</p></section><p class="dialog-note">版本 ${folder.revision} · 保存后用于下一次执行，正在进行的回复沿用启动时的配置。</p>`,'保存共享配置',async dialog=>{await api('/api/folders/'+fid,{action:'configure',expected_revision:folder.revision,config:{memory:dialog.querySelector('[name=memory]').value,prompt:dialog.querySelector('[name=prompt]').value,tools:[...dialog.querySelectorAll('[name=tool]:checked')].map(b=>b.value),harness_revision:dialog.querySelector('[name=harness]').value||null}});await BF.refresh()});
    d.querySelectorAll('[data-config-tab]').forEach(b=>b.onclick=()=>{d.querySelectorAll('[data-config-tab]').forEach(t=>t.setAttribute('aria-pressed',String(t===b)));d.querySelectorAll('[data-config-pane]').forEach(p=>p.hidden=p.dataset.configPane!==b.dataset.configTab)});
  }
  async function trash(){
    const data=await api('/api/organization');
    const html=[...data.trash.map(c=>({id:c.id,title:c.title,kind:'sidebar'})),...data.deleted_folders.map(f=>({id:f.id,title:f.name,kind:'folders'}))].map(item=>`<div class="trash-row"><span>${esc(item.title)}</span><button type="button" data-restore="${esc(item.id)}" data-kind="${item.kind}">恢复</button></div>`).join('')||'<p class="dialog-note">最近删除为空。</p>';
    const d=dialog('最近删除',html,null,()=>{});d.querySelector('.cancel-dialog').textContent='完成';
    d.querySelectorAll('[data-restore]').forEach(b=>b.onclick=async()=>{try{await api('/api/'+b.dataset.kind+'/'+b.dataset.restore,{action:'restore'});b.closest('.trash-row').remove();await BF.refresh()}catch(e){d.querySelector('.dialog-error').textContent=e.message}});
  }
  function recall(mid){
    const current=BF.getCurrent(),message=current?.messages?.find(m=>m.id===mid);if(!message)return BF.error('消息仍在同步，请稍后再试。');
    dialog('撤回并编辑',`<p>撤回这条消息及其后的对话，并停止当前执行。</p><blockquote>${esc(message.text.slice(0,180))}</blockquote><p class="dialog-note">已完成的文件变更、实验和费用会保留。原文返回输入框，你可以修改后重新发送。</p>`,'撤回',async()=>{await api('/api/conversations/'+current.id+'/recall',{message_id:mid});BF.setDraft(message.text);await BF.refreshDetail()});
  }
  window.Sidebar={render,configure,recall};q('#new-folder').onclick=createFolder;q('#open-trash').onclick=trash;
  q("#studio-project-search").oninput=()=>render(items,folders,selection);
  BF.refresh();
})();
