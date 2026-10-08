/* Small conversation projections; every card/file comes from a durable record. */
(() => {
  const {api,esc}=window.BF;
  const $=s=>document.querySelector(s);
  const labels={purpose:'要解决的问题',form:'产品形态',service:'提供的服务',installation:'安装与机械设计',energy:'能量与工作方式'};
  let readiness=null, pendingFiles=[];
  const selectedVersions=new Map();
  const checkNames={'required-parts':'必需部件','current-native-model':'原生模型与尺寸读回','native-electrical-rules':'原生原理图 / PCB 规则检查','cross-domain-interfaces':'电路、装配与固件接口一致性','product-electrical-verification':'电路实际功能与供能验证','target-firmware-verification':'目标固件构建与逻辑测试','hardware-measurements':'实物测量'};
  const list=items=>'<ul>'+items.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';
  checkNames['energy-budget-screen']='日能量与储能初筛（非每次回应保证）';
  checkNames['normal-service-screen']='正常条件轨迹至少完成一次回应（非实测）';
  function card(product,revision){
    const record=product?.records.find(r=>r.revision===revision);
    if(!record||record.stale)return '';
    const p=record.payload;
    if(record.kind==='question')return `<article class="product-card question-card"><div class="card-meta">需要取舍</div><strong>${esc(p.question)}</strong><p class="section-note">${esc(p.reason)}</p><div class="card-actions">${p.options.map(x=>`<button data-product-answer="${esc(x)}">${esc(x)}</button>`).join('')}<button data-product-answer="这个条件我也不太清楚，请选一个合理场景，列出假设并继续设计。">不知道，按假设继续</button></div></article>`;
    const latest=product.proposal?.revision===revision;
    return `<article class="product-card"><div class="card-meta">方案 v${revision} · ${latest?(product.approved?'已确认继续 · 假设仍待检验':'可按假设继续探索'):'历史版本'}</div><strong>${esc(p.title)}</strong><p>${esc(p.purpose)}</p><p class="section-note">${esc(p.form)} · ${esc(p.service)}</p><details><summary>${p.assumptions.length} 项场景假设 · 可修改</summary>${list(p.assumptions)}</details><div class="card-actions"><button data-product-open="proposal">查看方案</button>${latest?`<button data-product-approve="${revision}" ${product.approved?'disabled':''}>${product.approved?'已确认':'按此方案继续'}</button><button data-product-adjust="${revision}">调整</button>`:''}</div></article>`;
  }
  function bindCards(root){
    root.querySelectorAll('[data-product-open]').forEach(b=>b.onclick=()=>{if(document.body.classList.contains('sections-hidden'))$('#sections-toggle').click();$('[data-section="proposal"]').click()});
    root.querySelectorAll('[data-product-answer]').forEach(b=>b.onclick=()=>{window.BF.setDraft(b.dataset.productAnswer);$('#composer').requestSubmit()});
    root.querySelectorAll('[data-product-adjust]').forEach(b=>b.onclick=()=>window.BF.setDraft('请调整方案 v'+b.dataset.productAdjust+'：'));
    root.querySelectorAll('[data-product-approve]').forEach(b=>b.onclick=async()=>{
      const cid=window.BF.getSelection();b.disabled=true;
      try{await api('/api/conversations/'+cid+'/approve',{revision:Number(b.dataset.productApprove)});if(window.BF.getSelection()===cid)await window.BF.refreshDetail()}
      catch(e){window.BF.error(e.message);b.disabled=false}
    });
  }
  function panel(root,tab,current,execution){
    if(!current){delete root.dataset.modelKey;root.innerHTML='<p class="section-empty">从一句现场需求开始。Agent 会把不清楚的条件写成假设，形成可修改的方案。</p>';return}
    if(tab==='deployment'){delete root.dataset.modelKey;window.DeliveryPanel.open(root,current.id,true);return}
    const product=current.product, p=product?.proposal?.payload;
    if(tab!=='model')delete root.dataset.modelKey;
    if(tab==='model'){
      const record=product?.assembly?.current;
      delete root.dataset.modelKey;
      root.innerHTML=`<h3>${esc(record?.payload.title||'产品成果')}</h3><p class="section-note">${record?'装配 v'+record.revision+' · '+record.payload.parts.length+' 个零件。':'尚未建立产品装配。'}在产品页统一查看可旋转模型、仿真曲线、版本变化与验收依据。</p><button id="open-product-results">打开产品成果 →</button>`;
      root.querySelector('#open-product-results').onclick=()=>window.ProductWorkspace.showSession({view:'results'});
      return;
    }
    if(tab==='files'){
      root.innerHTML='<h3>产品工程与交付物</h3><p class="section-note">模型、仿真曲线、固件源码和完整下载包统一保存在产品页。每份文件保留生成版本与适用范围。</p><button id="open-result-files">查看原始工程 →</button>';
      root.querySelector('#open-result-files').onclick=()=>window.ProductWorkspace.showSession({view:'source'});
      return;
    }
    if(!p){
      const result=execution?.result?.verified||current.jobs?.find(j=>j.result)?.result;
      root.innerHTML=product?.enabled?'<h3>需求探索</h3><p class="section-note">Agent 可以先选择合理场景，把假设、尺寸依据和验收方式写入方案。</p><p class="section-note">尚未生成方案记录。</p>':`<h3>计算任务</h3><p>${esc(current.task_id||'历史实验')}</p><p class="section-note">已有基准直接执行，保持原任务约定。</p>${result?`<p>计算设计：${esc(result.design_status)}</p><details><summary>参数与约束</summary><pre>${esc(JSON.stringify({design:result.design,checks:result.checks},null,2))}</pre></details>`:''}<p class="section-note">F1 简化计算；不等同于硬件或现场验收。</p>`;
      return;
    }
    const v=product.proposal.revision, evidence=product.evidence.filter(e=>!e.stale);
    root.innerHTML=`<div class="card-meta">方案 v${v} · ${product.approved?'已确认继续':'按假设探索中'}</div><h3>${esc(p.title)}</h3>${Object.entries(labels).map(([k,label])=>`<section class="proposal-field"><h4>${label}</h4><p>${esc(p[k])}</p></section>`).join('')}<details open><summary>场景假设 · 可修改</summary>${list(p.assumptions)}</details><details><summary>验收方式与边界</summary>${list(p.acceptance)}${list(p.limits)}</details><details><summary>当前证据与能力</summary><p class="section-note">${product.binding?'已绑定 '+esc(product.binding.task_id)+'：'+esc(product.binding.rationale):'尚未绑定工程实验；当前为方案探索。'}</p>${evidence.map(e=>`<p class="section-note">${esc(e.job_id)} · ${esc(e.design_status||e.status)} · 方案 v${e.revision}</p>`).join('')}<p class="section-note">${evidence.some(e=>e.design_status==='PASS')?'已有计算通过记录；现场使用仍待验收。':'尚无本版本计算通过记录。'}</p>${product.capabilities.map(c=>'<p class="section-note">'+esc(c.name)+' · '+(c.status==='available'?'已接入':'未接入')+'<br>'+esc(c.scope)+'</p>').join('')}</details><details><summary>来源与历史</summary><p class="section-note">Agent 根据会话消息提出方案；场景假设不是用户确认的现场事实。来源 ${esc(product.proposal.source_message)}</p>${product.records.filter(r=>r.kind==='proposal').map(r=>'<p class="section-note">v'+r.revision+' · '+esc(r.payload.title)+(r.stale?' · 来源已撤回':'')+'</p>').join('')}</details><div class="card-actions"><button data-product-adjust="${v}">补充或修改</button></div>`;
    bindCards(root);window.ReferencePanel.summary(root,current.id);
  }
  const resultCache=new Map(),resultLoading=new Set();
  function handoff(current){
    if(window.StudioExperience){document.querySelector('#task-handoff')?.remove();window.StudioExperience.chatCard(document.querySelector('#conversation'));return}
    let row=document.querySelector('#task-handoff');
    if(!row){row=document.createElement('details');row.id='task-handoff';row.className='section-note';document.querySelector('#conversation').before(row)}
    const id=current?.owner||current?.id;
    if(row.dataset.owner!==id){row.hidden=true;row.dataset.owner=id||'';row.innerHTML='';row.open=false}
    if(!id)return;
    const cached=resultCache.get(id);
    if(cached){
      const s=cached.data,key=s.snapshot_sha256;
      if(row.dataset.snapshot!==key){row.dataset.snapshot=key;row.hidden=!s.files.length&&!s.results.length;
        row.innerHTML=`<summary>任务成果 · ${s.files.length} 件文件 · ${s.results.length} 条方案与执行记录</summary><p>${s.coverage.map(d=>esc(d.label)+' '+d.files+' 件').join(' · ')}</p><p>${s.revision?'装配 v'+s.revision+' · '+(s.verdict?.passed?'当前阶段条件满足':'验收仍有缺项'):'会话记录已归档，尚未建立产品装配。'}</p><button class="quiet" data-handoff-product>查看结果与过程 →</button>`;
        row.querySelector('button').onclick=()=>window.ProductWorkspace.showSession({view:'results'});
      }
    }
    if(resultLoading.has(id)||(cached&&Date.now()-cached.time<10000))return;
    resultLoading.add(id);api('/api/results?session='+encodeURIComponent(id)).then(data=>{resultCache.set(id,{data,time:Date.now()});if((window.BF.getCurrent()?.owner||window.BF.getCurrent()?.id)===id)handoff(window.BF.getCurrent())}).catch(()=>{}).finally(()=>resultLoading.delete(id));
  }
  function activity(events){
    const last=[...events].reverse().find(e=>['tool_execution_start','tool_execution_end','text_delta','input_accepted'].includes(e.data.type))?.data;
    if(last?.type==='tool_execution_start')return ({bf_product:'正在整理产品方案',bf_experiment:'正在提交计算实验',bf_job:'正在等待实验结果',bf_submit:'正在核验提交快照',bf_memory:'正在读写共享笔记',bf_reference:'正在查阅参考资料',bf_engineering:'正在运行工程计算'}[last.toolName]||'正在执行任务');
    return last?.type==='text_delta'?'Agent 正在回复':'正在等待模型响应';
  }
  function showReadiness(value){
    if(value)readiness=value;
    if(!readiness)return;
    // Execution failures belong to the durable conversation, not below the draft.
    $('#runtime-block')?.remove();
    const scoped=window.BF?.getCurrent()?.readiness||readiness;
    $('#connection').textContent=scoped.reasons?.length?'本地已连接 · 模型受阻':'本地已连接';
  }
  $('#attach-file').onclick=()=>{
    const current=window.BF.getCurrent();
    if(current&&!current.product?.enabled){window.BF.error('文字资料用于产品探索会话，请新建“从产品需求开始”的对话。');return}
    $('#product-file-input').click();
  };
  $('#product-file-input').onchange=async e=>{
    const file=e.target.files[0];e.target.value='';if(!file)return;
    if(file.size>48000){window.BF.error('每份文字资料最多 16000 字。');return}
    const attachment={name:file.name,content:await file.text()};
    if(attachment.content.length>16000){window.BF.error('每份文字资料最多 16000 字。');return}
    const cid=window.BF.getSelection();
    try{
      if(cid){const added=await api('/api/conversations/'+cid+'/attachments',attachment);await window.BF.refreshDetail();window.BF.setDraft('请参考我刚添加的资料“'+added.name+'”（'+added.id+'），继续完善方案。')}
      else{if(pendingFiles.length>=3)throw Error('首次最多添加三份文字资料。');pendingFiles.push(attachment);$('#attach-file').textContent='＋ '+pendingFiles.length;window.BF.error('已附加 '+file.name+'，随下一条产品需求一起发送。')}
    }catch(err){window.BF.error(err.message)}
  };
  window.Product={handoff,card,bindCards,panel,activity,showReadiness,creationPayload:()=>({attachments:pendingFiles}),clearAttachments:()=>{pendingFiles=[];$('#attach-file').textContent='＋'}};
  async function health(){try{showReadiness(await api('/api/health'))}catch{}}
  health();setInterval(health,5000);window.BF.refreshDetail();
})();
