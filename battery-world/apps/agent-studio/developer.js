(() => {
  const {api, esc} = window.BF;
  const q = s => document.querySelector(s);
  const modules = {referenceCase:['参考案例','复现'],research:['Research','研究'], delivery:['交付与部署','进展'], trace:['Trace','轨迹'], memory:['Memory','记忆'], harness:['Harness','程序'], rsi:['RSI','演化'], tools:['Tools','工具'], context:['Context','上下文'], experiments:['Experiments','实验']};
  let mode = localStorage.getItem('bf-studio-mode') || 'task';
  let module = localStorage.getItem('bf-dev-module') || 'trace';
  if (!modules[module]) module='memory';
  let data=null, request=0, savedKey=null, draftParent=null, draftOrigin={}, working=false;
  const json = v => JSON.stringify(v,null,2);
  const pre = v => `<pre>${esc(typeof v==='string'?v:json(v))}</pre>`;
  const fold = (title,v,open=false) => `<details class="dev-record" ${open?'open':''}><summary>${esc(title)}</summary>${pre(v)}</details>`;
  const hint = text => `<p class="dev-hint">${esc(text)}</p>`;
  const edit = (label,area) => `<button data-edit="${area}">${label}</button>`;
  const session = () => data?.session;
  const money = n => '$'+Number(n||0).toFixed(4);
  function notice(text,bad=false){q('#dev-notice').textContent=text;q('#dev-notice').classList.toggle('bad-text',bad)}
  const groups={trace:{name:'Trace',members:['trace','context']},config:{name:'配置与能力',members:['memory','harness','tools']},evolution:{name:'版本与演化',members:['rsi']},validation:{name:'验证',members:['delivery','referenceCase','experiments','research']}};
  const group=()=>Object.keys(groups).find(k=>groups[k].members.includes(module))||'trace';
  function setMode(value){
    mode=({runtime:'task',developer:'console'})[value]||value;
    if(!['task','console','panorama','product'].includes(mode))mode='task';
    localStorage.setItem('bf-studio-mode',mode);document.body.dataset.studioMode=mode;
    document.body.classList.toggle('developer-mode',mode==='console');document.body.classList.toggle('panorama-mode',mode==='panorama');
    document.body.classList.toggle('product-mode',mode==='product');q('#product-view').hidden=mode!=='product';
    q('#developer-view').hidden=mode!=='console';q('#panorama-view').hidden=mode!=='panorama';
    for(const [id,m] of [['runtime-mode','task'],['developer-mode','console'],['panorama-mode','panorama'],['product-mode','product']])q('#'+id).setAttribute('aria-pressed',mode===m);
    q('#sections-toggle').hidden=mode!=='task';
    window.dispatchEvent(new CustomEvent('bf-mode',{detail:{mode}}));
    if(mode==='console')load();if(mode==='panorama')window.Panorama.open();if(mode==='product')window.ProductWorkspace.open();
  }
  q('#runtime-mode').onclick=()=>setMode('task');q('#developer-mode').onclick=()=>setMode('console');q('#panorama-mode').onclick=()=>setMode('panorama');q('#product-mode').onclick=()=>setMode('product');
  function navigation(){
    const active=group();q('#dev-nav').innerHTML=Object.entries(groups).map(([id,g])=>`<button data-group="${id}" aria-pressed="${id===active}">${g.name}</button>`).join('');
    q('#dev-subnav').hidden=groups[active].members.length===1;
    q('#dev-subnav').innerHTML=groups[active].members.map(id=>`<button data-module="${id}" aria-pressed="${id===module}">${modules[id][0]} <small>${modules[id][1]}</small></button>`).join('');
  }
  q('#dev-nav').onclick=e=>{const b=e.target.closest('[data-group]');if(b){module=groups[b.dataset.group].members[0];localStorage.setItem('bf-dev-module',module);load()}};
  q('#dev-subnav').onclick=e=>{const b=e.target.closest('[data-module]');if(b){module=b.dataset.module;localStorage.setItem('bf-dev-module',module);load()}};
  q('#console-map').onclick=()=>window.Panorama.focus(({memory:'memory',harness:'harness',tools:'tools',trace:'trace',context:'sessions',experiments:'runtime',rsi:'validation',delivery:'sessions',research:'research',referenceCase:'runtime'})[module]);
  q('#dev-content').before(Object.assign(document.createElement('p'),{id:'dev-notice',className:'dev-hint'}));
  q('#dev-notice').setAttribute('role','status');
  async function load(){const turn=++request;try{const selected=['trace','tools','delivery','research','referenceCase'].includes(module)?null:window.BF.getSelection();const value=await api('/api/developer'+(selected?'?session='+encodeURIComponent(selected):''));if(turn!==request)return;data=value;notice('');render();renderRevisions()}catch(e){if(turn===request)notice(e.message==='SESSION_NOT_FOUND'?'当前会话尚未启动 Pi。保存配置后可用于下一次运行。':e.message,true)}}
  window.addEventListener('bf-selection',()=>{if(mode==='console')load()});
  q('#refresh').addEventListener('click',()=>{if(mode==='console')load()});
  const jobButton = id => `<button class="quiet" data-job-detail="${esc(id)}">查看实验 ↗</button>`;
  function render(){
    navigation();
    if(!data)return;
    const s=session();q('#dev-session').textContent=s?`${s.id} · ${s.harness.label} · ${s.mode==='chat'?'对话':s.mode==='solve'?'求解':'改进'}`:data.note;
    let html='';q('#dev-content').dataset.module=module;
    q('#revision-panel').hidden=group()!=='config';
    const range=module==='referenceCase'?'项目 · 参考辅助工程':module==='rsi'?'项目 · 已记录试验':module==='tools'?'本机能力'+(window.BF.getSelection()?' · 所选会话调用':' · 未选择会话'):module==='experiments'?'工作区检查 / 所选会话实验':(window.BF.getSelection()||'未选择任务会话');
    q('#console-scope').innerHTML=`<span>BF Agent</span><span>${esc(range)}</span><span>更新于 ${new Date().toLocaleTimeString('zh-CN',{hour12:false})}</span>`;

    if(module==='referenceCase'){q('#dev-session').textContent='三篇论文 · 单次动作无线节点';window.ReferenceCasePanel.open(q('#dev-content'));return}
    if(module==='research'){q('#dev-session').textContent='A/B/C · 开发与机制先导';window.ResearchPanel.open(q('#dev-content'));return}
    if(module==='delivery'){q('#dev-session').textContent=window.BF.getSelection()||'选择产品会话';window.DeliveryPanel.open(q('#dev-content'),window.BF.getSelection());return}
    if(module==='trace'){q('#dev-session').textContent=window.BF.getSelection()||'选择一个会话查看执行轨迹';window.TracePanel.open(q('#dev-content'),window.BF.getSelection());return}
    if(module==='tools'){q('#dev-session').textContent=window.BF.getSelection()||'本地工程环境';window.EngineeringPanel.open(q('#dev-content'),window.BF.getSelection());return}
    if(module==='memory'){
      html=`<div class="dev-heading"><h3>任务记忆</h3>${edit('编辑下一次运行的 Memory','memory')}</div>`;
      html+=hint('区分本次加载、当前任务记录与人工备注。来源可追溯，读取和写入不自动构成验证。');
      html+=`<div class="console-cards"><article><small>本次启动的共享 Memory</small><b>${s?.shared_context?.folder_id?'文件夹版本 '+esc(s.shared_context.revision):'未记录'}</b><p>只代表启动记录；之后的写入请查看 Trace。</p></article><article><small>公开历史经验</small><b>${s?.public_history?(s.memory_in_prompt?'已注入输入':'文件可按需读取'):'未记录'}</b><p>任务假设与实验结论分开审查。</p></article></div>`;

      if(s?.state){const state=s.state;
        const bullets=(items)=>Array.isArray(items)&&items.length?'<ul class="console-notes">'+items.map(x=>'<li>'+esc(typeof x==='string'?x:JSON.stringify(x))+'</li>').join('')+'</ul>':hint('暂无记录');
        html+='<h4>计划</h4>'+bullets(state.plan)+'<h4>假设 · 尚待验证</h4>'+bullets(state.hypotheses);
        html+=`<div class="dev-grid">${fold('当前方案',state.current)}${fold('已验证最佳方案',state.bestVerified)}${fold('待完成操作',state.pending)}${fold('计划与假设 · 原始记录',{plan:state.plan,hypotheses:state.hypotheses})}</div>`;
        html+=`<h4>已记录事实 <span class="muted">${(state.facts||[]).length}</span></h4>`;
        html+=(state.facts||[]).map((f,i)=>{const job=s.jobs.find(j=>j.result?.run_id===f.run_id);return `<details class="dev-record"><summary>事实 ${i+1} · ${esc(f.run_id||'未绑定运行')}</summary>${pre(f)}${job?jobButton(job.id):hint('本会话未找到关联实验。')}</details>`}).join('')||hint('尚无实验事实。');
        if(state.developerMemory)html+=fold('本次注入的手写记忆',state.developerMemory);
      }else html+=hint('当前选择没有 Agent 状态记录。');
      if(s?.shared_context?.folder_id)html+=fold('本次启动的文件夹共享记忆 · 版本 '+s.shared_context.revision,s.shared_context.memory||'（空）');
      if(s?.public_history)html+=fold(`公开历史经验 · ${s.memory_in_prompt?'已注入任务输入':'本地文件，可按需读取'}`,s.public_history);
      if(s?.experience)html+=fold('改进进程的经验索引',s.experience);
      if(s?.notes)html+=fold('参与者 notes.md · 未自动认证为事实',s.notes);
    }
    if(module==='harness'){
      const next=data.revisions.find(r=>r.id===data.active.revision),draft=data.revisions[0];
      html=`<div class="console-cards three"><article><small>所选运行绑定</small><b>${esc(s?.harness.label||'未选择运行')}</b><p>${s?.loaded?'实际加载事件已记录':'实际加载事件未记录'}</p></article><article><small>最近保存的候选</small><b>${esc(draft?.name||'暂无候选')}</b><p>保存或构建通过不代表已采用。</p></article><article><small>下一次运行配置</small><b>${esc(next?.name||'默认 Harness')}</b><p>不会替换正在执行的版本。</p></article></div>`;
      html+=`<div class="dev-heading"><h3>本次加载的程序</h3>${edit('编辑 Harness','harness')}</div>`;
      if(s){html+=`<div class="dev-metrics"><span>版本 <b>${esc(s.harness.label)}</b></span><span>模型 <b>${esc(s.harness.model)}</b></span><span>加载记录 <b>${s.loaded?'已记录':'未记录'}</b></span></div>`;
        html+=fold('源码、构建与加载身份',{frozen:s.harness,loaded:s.loaded});html+=`<button class="quiet" data-harness-detail="${esc(s.harness.identity)}">查看父版本差异</button>`;
        html+=fold('求解程序 P · solver.ts',s.sources?.['solver.ts']??'源码不可用');html+=fold('改进程序 U · improver.ts',s.sources?.['improver.ts']??'源码不可用');
        html+=hint('编辑产生独立候选版本。历史运行继续绑定原始源码和构建。');
      }else html+=hint('选中 Pi 运行查看其版本，或新建下一次运行配置。');
    }
    if(module==='rsi'){
      const study=data.study;
      html='<div id="platform-history"></div><div class="dev-heading"><h3>Harness 候选与试验</h3><span class="tag">未自动提升</span></div>';
      html+=hint('Trace 可用于失败归因和提出修改；候选仍需对照、回归及后续任务验证。以下是已有开发试验，没有新的能力提升认定。');
      if(window.BF.getSelection())html+='<button class="quiet" data-trace-open>审查当前会话 Trace →</button>';
      html+='<div class="rsi-chain">'+(study.lineage||[]).map(n=>`<article><span class="muted">${esc(n.parent?'来自 '+n.parent:'冻结基线')}</span><h4>${esc(n.title)}</h4><p>${esc(n.label)}</p><code>P ${esc(n.modules.solver.slice(0,12))}<br>U ${esc(n.modules.improver.slice(0,12))}</code>${n.process?`<button class="quiet" data-session="${esc(n.process)}">查看生成过程 ↗</button>`:''}</article>`).join('')+'</div>';
      if(study.development){const d=study.development;html+=`<h4>已有 H0 / H1 开发对照</h4><div class="console-cards"><article><small>基线 H0</small><b>${esc(d.parent_pass)} / ${esc(d.parent_total)} 通过</b><p>记录中的开发任务结果</p></article><article><small>候选 H1</small><b>${esc(d.child_pass)} / ${esc(d.child_total)} 通过</b><p>${d.complete_pairs?'成对记录完整':'成对记录不完整'} · ${d.promotion==='NOT_PROMOTED'?'未采用':esc(d.promotion)}</p></article></div>`+fold('H0 / H1 原始对照记录',d)}
      if(study.recursive){const r=study.recursive;html+=`<h4>递归与迁移 · 已记录试验</h4><p class="dev-hint">${r.complete?'声明的试验已结束':'声明的试验尚未全部结束'}${r.blocked?' · 包含预算中断':''}。包含恢复后的运行，不作为连续自主提升证明。</p><table class="trace-table"><thead><tr><th>试验组</th><th>次数</th><th>通过</th><th>失败</th><th>未评估</th></tr></thead><tbody>${Object.entries(r.arms||{}).map(([name,a])=>`<tr><td>${esc(name)}</td><td>${esc(a.trials)}</td><td>${esc(a.passed)}</td><td>${esc(a.failed)}</td><td>${esc(a.not_evaluated)}</td></tr>`).join('')}</tbody></table>`+fold('递归与迁移原始记录',r)}
      html+='<h4>所有候选 · 包含拒绝和无修改</h4>'+(study.candidates||[]).map(c=>`<details class="dev-record"><summary>${esc(c.label)} · ${esc(c.status)}</summary>${pre(c)}${c.identity?`<button data-harness-detail="${esc(c.identity)}">查看源码差异</button>`:''}${c.improver_process?`<button data-session="${esc(c.improver_process)}">查看生成过程</button>`:''}</details>`).join('');
    }
    if(module==='tools'){
      html='<h3>工具与调用</h3>';
      if(s){const declared=[...new Set([...(s.harness.tools||[]),...(s.shared_context?.tools||[])])];const enabled=s.shared_context?.tools||(s.mode==='improve'?declared.filter(n=>!n.startsWith('bf_')):declared);
        html+=hint(s.shared_context?'启用状态来自 Pi 启动时实际注册的工具集合；文件夹设置在下一次执行时加载。调用轨迹保留原始记录。':'工具配置来自冻结清单及进程模式；实际使用由调用轨迹确认。历史记录未单独采集每次工具耗时。');
        html+='<div class="tool-list">'+declared.map(name=>`<div><code>${esc(name)}</code><span>${enabled.includes(name)?'配置启用':'本模式未启用'}</span><b>${s.calls.filter(c=>c.name===name).length} 次</b></div>`).join('')+'</div>';
        html+=fold('科学工具参数与权限',{bf_experiment:{parameters:{operation_id:'string'},effect:'上传当前 design.json / policy.py，提交受额度约束的实验'},bf_job:{parameters:{job_id:'string'},effect:'查询自己的任务，最多等待 20 秒'},bf_inspect_run:{parameters:{job_id:'string',view:['summary','decisions','energy']},effect:'读取自己的公开实验产物'},bf_submit:{parameters:{job_id:'string'},effect:'校验当前文件和实验快照后封存'},builtin:'read/edit/write/bash 受进程文件与网络沙箱限制；完整声明以冻结程序为准'});
        html+='<button class="quiet" data-trace-open>在 Trace 中查看调用输入、返回与错误 →</button>';
      }else html+=hint('当前选择没有 Pi 工具调用。');
    }
    if(module==='context'){
      html=`<div class="dev-heading"><h3>输入与公开消息</h3>${edit('编辑提示词','prompts')}</div>`;
      if(s){html+=`<div class="dev-metrics"><span>模型请求 <b>${s.model_calls}</b></span><span>费用上界 <b>${money(s.cost)}</b></span><span>资源 <b>显式空加载器</b></span></div>`;
        html+=s.contexts.length?s.contexts.map(c=>fold((c.type==='shared_context_loaded'?'组装后的对话提示词 · 文件夹版本 ':'记录的 Harness 提示词 · ')+String(c.revision).slice(0,12),c.prompt)).join(''):hint('此历史运行未记录组装后的完整提示词。下面展示任务输入与公开消息；不会把最终状态当作当时的上下文。');
        html+=fold('任务输入',s.task??'改进进程通过经验索引接收输入');
        html+=hint('新编辑版本将记录 Harness 生成的提示词；SDK 附加内容和逐次完整请求仍不属于这一记录。');
        html+=s.messages.map(m=>fold('#'+m.seq+' · '+m.role,m.content.map(c=>c.text).join('\n'))).join('');
      }else html+=hint('固定参考不调用模型；可先编辑下一次运行的提示词。');
    }
    if(module==='experiments'){
      html='<div id="development-checks"></div><h3>所选会话 · 科学实验</h3>'+hint('每次实验绑定提交时的设计与策略快照。执行成功与设计通过分别展示。');
      html+=s?.jobs.length?s.jobs.map(j=>`<article class="experiment-row"><div><h4>${esc(j.request.task_id)} · ${esc(j.result?.design_status||'等待结果')}</h4><p>${esc(j.id)} · ${esc(j.status)}</p><code>${esc(j.result?.snapshot_id||j.request.snapshot_id||'')}</code></div>${jobButton(j.id)}</article>`).join(''):hint('本会话没有实验记录；改进进程的对照结果可在 RSI 中查看。');
    }
    q('#dev-content').innerHTML=html;
    if(module==='rsi')window.Panorama.history(q('#platform-history'));
    if(module==='experiments')window.Panorama.checks(q('#development-checks'));

  }
  function renderRevisions(){
    const active=data.active;const item=data.revisions.find(r=>r.id===active.revision);
    q('#active-revision').textContent=active.revision?`已选择：${item?.name||active.revision.slice(0,12)} · 仅用于下一次 Pi 求解；保存与选择不会启动模型。`:'当前使用默认 Harness。保存与选择配置不会启动模型。';
    q('#revision-list').innerHTML=data.revisions.length?data.revisions.map(r=>`<article class="revision-row"><div><strong>${esc(r.name)}</strong><small>${r.id.slice(0,12)} · ${r.validation?({VALIDATED:'校验通过',REJECTED:'校验未通过'}[r.validation.status]):'尚未校验'}${active.revision===r.id?' · 下一次运行已选':''}</small></div><button data-open-revision="${r.id}">查看 / 编辑</button><button class="quiet" data-diff="${r.id}">差异</button></article>`).join(''):hint('还没有编辑版本。可从当前运行复制配置，再修改 Memory、提示词或程序。');
    if(active.revision)q('#revision-list').insertAdjacentHTML('beforeend','<button id="reset-active" class="quiet">下一次恢复默认配置</button>');
    const reset=q('#reset-active');if(reset)reset.onclick=async()=>{try{await api('/api/developer/activate',{revision:null,expected_generation:active.generation});await load()}catch(e){notice(e.message==='SESSION_NOT_FOUND'?'当前会话尚未启动 Pi。保存配置后可用于下一次运行。':e.message,true)}};
    q('#restore-draft').hidden=!localStorage.getItem('bf-editor-draft-v1');
  }
  const restore=document.createElement('button');restore.id='restore-draft';restore.textContent='恢复未保存草稿';restore.className='quiet';q('#new-revision').after(restore);
  const dialog=document.createElement('dialog');dialog.id='config-editor';dialog.setAttribute('aria-labelledby','editor-title');dialog.innerHTML=`<form method="dialog" class="dialog-top"><div><h2 id="editor-title">编辑下一次运行配置</h2><p class="muted">手写记忆与附加提示词会随版本一起冻结。</p></div><button aria-label="关闭编辑器">×</button></form><label class="field-label">版本名称<input id="edit-name" maxlength="80"></label><nav class="editor-tabs" aria-label="编辑内容"><button data-editor-pane="memory">Memory</button><button data-editor-pane="prompts">提示词</button><button data-editor-pane="harness">Harness</button></nav><section data-pane="memory"><p class="dev-hint">每行一条假设或计划。实验事实、已验证最佳方案与待完成操作只能由实际运行产生。</p><div class="dev-grid"><label class="field-label">假设<textarea id="edit-hypotheses" rows="6"></textarea></label><label class="field-label">计划<textarea id="edit-plan" rows="6"></textarea></label></div><label class="field-label">手写备注<textarea id="edit-notes" rows="7"></textarea></label></section><section data-pane="prompts" hidden><p class="dev-hint">以下文字附加到 Harness 生成的提示词末尾。完整基础逻辑可在 Harness 中编辑。</p><label class="field-label">求解提示词 · 附加指令<textarea id="edit-solver-prompt" rows="9"></textarea></label><label class="field-label">改进提示词 · 附加指令<textarea id="edit-improver-prompt" rows="9"></textarea></label></section><section data-pane="harness" hidden><p class="dev-hint">编辑 P / U 的 TypeScript 源码。保存后需要编译与禁网入口检查；校验通过不代表效果提升。</p><label class="field-label">求解程序 P · solver.ts<textarea id="edit-solver" rows="16" spellcheck="false" class="code-editor"></textarea></label><label class="field-label">改进程序 U · improver.ts<textarea id="edit-improver" rows="12" spellcheck="false" class="code-editor"></textarea></label></section><p id="editor-status" role="status"></p><details id="editor-diff"><summary>查看当前保存版本的差异</summary><pre></pre></details><footer class="editor-actions"><button id="save-revision" class="primary">保存新版本</button><button id="validate-revision">校验构建</button><button id="activate-revision">设为下一次运行</button></footer>`;document.body.append(dialog);
  const peek=document.createElement('dialog');peek.id='dev-detail';peek.innerHTML='<form method="dialog" class="dialog-top"><h2>关联记录</h2><button aria-label="关闭详情">×</button></form><div id="dev-detail-body"></div>';document.body.append(peek);
  function pane(area){dialog.querySelectorAll('[data-pane]').forEach(el=>el.hidden=el.dataset.pane!==area);dialog.querySelectorAll('[data-editor-pane]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.editorPane===area))}
  dialog.querySelectorAll('[data-editor-pane]').forEach(b=>b.onclick=()=>pane(b.dataset.editorPane));
  function editorPayload(){return {name:q('#edit-name').value,parent:draftParent,...draftOrigin,memory:{hypotheses:q('#edit-hypotheses').value.split('\n').filter(s=>s.trim()),plan:q('#edit-plan').value.split('\n').filter(s=>s.trim()),notes:q('#edit-notes').value},prompts:{solver_append:q('#edit-solver-prompt').value,improver_append:q('#edit-improver-prompt').value},sources:{'solver.ts':q('#edit-solver').value,'improver.ts':q('#edit-improver').value}}}
  function markDirty(){savedKey=null;q('#editor-status').textContent='未保存 · 草稿已暂存于本机浏览器';q('#editor-diff').hidden=true;localStorage.setItem('bf-editor-draft-v1',JSON.stringify(editorPayload()));editorButtons();restore.hidden=false}
  dialog.querySelectorAll('input,textarea').forEach(el=>el.addEventListener('input',markDirty));
  function editorButtons(){q('#save-revision').disabled=working;q('#validate-revision').disabled=working||!savedKey;q('#activate-revision').disabled=working||!savedKey||!data?.revisions.find(r=>r.id===savedKey&&r.validation?.status==='VALIDATED');dialog.querySelectorAll('input,textarea').forEach(el=>el.disabled=working)}
  async function openEditor(area='memory',key=null,restored=null){try{const selected=window.BF.getSelection();const seed=restored?{id:null,payload:restored}:await api('/api/developer/seed'+(key?'?revision='+key:selected?.startsWith('pi-')?'?session='+encodeURIComponent(selected):''));const p=seed.payload;savedKey=seed.id;draftParent=seed.id||p.parent;draftOrigin={source_session:p.source_session,source_identity:p.source_identity};q('#edit-name').value=p.name;q('#edit-hypotheses').value=p.memory.hypotheses.join('\n');q('#edit-plan').value=p.memory.plan.join('\n');q('#edit-notes').value=p.memory.notes;q('#edit-solver-prompt').value=p.prompts.solver_append;q('#edit-improver-prompt').value=p.prompts.improver_append;q('#edit-solver').value=p.sources['solver.ts'];q('#edit-improver').value=p.sources['improver.ts'];q('#editor-status').textContent=savedKey?'已保存版本 '+savedKey.slice(0,12):'编辑完成后保存为新版本。';q('#editor-diff').hidden=true;pane(area);editorButtons();dialog.showModal()}catch(e){notice(e.message==='SESSION_NOT_FOUND'?'当前会话尚未启动 Pi。保存配置后可用于下一次运行。':e.message,true)}}
  q('#new-revision').onclick=()=>openEditor();restore.onclick=()=>{try{openEditor('memory',null,JSON.parse(localStorage.getItem('bf-editor-draft-v1')))}catch(e){notice(e.message==='SESSION_NOT_FOUND'?'当前会话尚未启动 Pi。保存配置后可用于下一次运行。':e.message,true)}};
  async function action(fn){working=true;editorButtons();try{await fn()}catch(e){q('#editor-status').textContent=e.message}finally{working=false;editorButtons()}}
  q('#save-revision').onclick=()=>action(async()=>{const record=await api('/api/developer/revisions',editorPayload());savedKey=record.id;draftParent=savedKey;localStorage.removeItem('bf-editor-draft-v1');q('#editor-status').textContent='新版本已保存 · '+savedKey.slice(0,12)+' · 尚未设为下一次运行';await load();const diff=await api('/api/developer/revision?id='+savedKey);q('#editor-diff pre').textContent=Object.entries(diff.diff).map(([k,v])=>k+'\n'+(v||'无变化')).join('\n\n');q('#editor-diff').hidden=false});
  q('#validate-revision').onclick=()=>action(async()=>{q('#editor-status').textContent='正在编译并检查入口，不调用模型…';const r=await api('/api/developer/validate',{revision:savedKey});q('#editor-status').textContent=r.status==='VALIDATED'?'校验通过 · TypeScript / 禁网入口 / 源码构建绑定':'校验未通过 · '+r.error;await load()});
  q('#activate-revision').onclick=()=>action(async()=>{await api('/api/developer/activate',{revision:savedKey,expected_generation:data.active.generation});q('#editor-status').textContent='已设为下一次 Pi 求解配置。当前运行和历史结果保持原版本。';await load()});
  document.addEventListener('click',async e=>{const b=e.target.closest('[data-edit],[data-open-revision],[data-diff],[data-session],[data-job-detail],[data-harness-detail],[data-trace-open]');if(!b)return;try{
    if(b.hasAttribute('data-trace-open')){module='trace';localStorage.setItem('bf-dev-module',module);return load()}
    if(b.dataset.edit)return openEditor(b.dataset.edit);
    if(b.dataset.openRevision)return openEditor('memory',b.dataset.openRevision);
    if(b.dataset.session){await window.BF.select(b.dataset.session);module='harness';return load()}
    if(b.dataset.harnessDetail){const h=await api('/api/developer/harness?id='+b.dataset.harnessDetail);q('#dev-detail-body').innerHTML=`<h3>${esc(h.manifest.label)}</h3>`+(h.parent_diff?Object.entries(h.parent_diff).map(([k,v])=>fold(k,v||'无变化',true)).join(''):hint('此版本没有已记录的父版本差异。'));peek.showModal();return}
    if(b.dataset.diff){const r=await api('/api/developer/revision?id='+b.dataset.diff);q('#dev-detail-body').innerHTML=Object.entries(r.diff).map(([k,v])=>fold(k,v||'无变化',true)).join('');peek.showModal();return}
    if(b.dataset.jobDetail){const j=await api('/api/jobs/'+encodeURIComponent(b.dataset.jobDetail));q('#dev-detail-body').innerHTML=`<h3>${esc(j.request.task_id)} · ${esc(j.result?.design_status||j.status)}</h3>`+fold('身份与结果',{id:j.id,request:j.request,status:j.status,run_id:j.result?.run_id,checks:j.result?.checks,summary:j.result?.summary},true)+fold('设计与策略',{design:j.result?.design,policy:j.result?.policy})+`<button id="view-job-runtime">在任务模式查看产物</button>`;q('#view-job-runtime').onclick=async()=>{peek.close();await window.BF.select(j.id);setMode('runtime')};peek.showModal()}
  }catch(err){notice(err.message,true)}});
  window.BFDeveloper={setMode,openModule:key=>{module=modules[key]?key:'trace';localStorage.setItem('bf-dev-module',module);setMode('console')},openTrace:()=>{module='trace';localStorage.setItem('bf-dev-module',module);setMode('console')}};
  setMode(mode);
})();
