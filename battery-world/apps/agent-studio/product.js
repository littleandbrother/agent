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
      const assembly=product?.assembly,record=assembly?.revisions?.find(r=>r.revision===selectedVersions.get(current.id))||assembly?.current;
      if(!record){delete root.dataset.modelKey;root.innerHTML='<p class="section-empty">完整产品生成后，在这里查看可旋转模型、零件和验证状态。</p>';return}
      const job=assembly.jobs.find(j=>j.assembly?.revision===record.revision&&j.status==='SUCCEEDED');
      const key=JSON.stringify([current.id,record.revision,job?.id,assembly.checks,assembly.delivery]);if(root.dataset.modelKey===key)return;root.dataset.modelKey=key;
      root.innerHTML=`<label class="section-note">版本 <select id="product-version">${[...assembly.revisions].reverse().map(r=>`<option value="${r.revision}" ${r.revision===record.revision?'selected':''}>v${r.revision}${r.revision===assembly.current.revision?' · 当前':' · 历史'}</option>`).join('')}</select></label><div class="card-meta">产品 v${record.revision} · ${record.payload.parts.length} 个零件</div><h3>${esc(record.payload.title)}</h3>${assembly.delivery?`<p class="section-note">${assembly.delivery.passed?'✓ 当前声明阶段条件已满足':'待完成：'+esc(assembly.delivery.missing.map(x=>({'missing_published_file:document':'发布说明','missing_published_file:source':'发布源码'}[x]||x)).join('、'))}</p>`:''}${job?`<iframe class="product-model-viewer" title="可交互产品三维模型" src="/model-viewer.html?job=${encodeURIComponent(job.id)}"></iframe><button class="quiet" id="expand-model">放大查看 ↗</button>`:'<p class="section-note">当前版本尚未生成模型；历史产物不会当作当前结果。</p>'}<details><summary>本版检查与待办</summary>${(record.revision===assembly.current.revision?assembly.checks:[{id:'历史版本检查请查看对应 result.json',passed:false}]).map(c=>`<p class="section-note">${c.passed?'✓':'○'} ${esc(checkNames[c.id]||c.id)}${c.status==='NOT_EVALUATED'?' · 待验证':''}</p>`).join('')}<p class="section-note">数字模型检查与实物验证分开记录。</p></details><details><summary>零件与尺寸来源</summary>${record.payload.parts.map(p=>`<p class="section-note"><b>${esc(p.name)}</b><br>${p.geometry.size_mm.map(x=>Number(x).toFixed(2)).join(' × ')} mm<br>${esc(p.source.note)}${p.source.url?` · <a href="${esc(p.source.url)}" target="_blank" rel="noreferrer">来源</a>`:''}</p>`).join('')}</details><details><summary>产品版本</summary>${assembly.revisions.map(r=>`<p class="section-note">v${r.revision} · ${esc(r.payload.title)} · ${r.hashes.physical_hash.slice(0,10)}${r.source_valid?'':' · 来源已撤回'}</p>`).join('')}</details>`;
      root.querySelector('#product-version').onchange=e=>{selectedVersions.set(current.id,Number(e.target.value));delete root.dataset.modelKey;panel(root,'model',current,execution)};
      root.querySelector('#expand-model')?.addEventListener('click',()=>{const d=document.createElement('dialog');d.className='model-dialog';d.innerHTML=`<form method="dialog"><button aria-label="关闭模型">×</button></form><iframe title="完整产品模型" src="/model-viewer.html?job=${encodeURIComponent(job.id)}"></iframe>`;document.body.append(d);d.addEventListener('close',()=>d.remove(),{once:true});d.showModal()});
      return;
    }
    if(tab==='files'){
      const files=product?.files||[],engineering=product?.engineering||[],published=product?.assembly?.files||[];
      if(!files.length&&!engineering.length&&!published.length){root.innerHTML='<p class="section-empty">这里会出现真实生成的方案、设计参数、模型、渲染和实验记录。</p>';return}
      const artifact=(id,name)=>'/api/engineering/jobs/'+encodeURIComponent(id)+'/artifact?name='+encodeURIComponent(name);
      const publishedRow=f=>`<p class="section-note"><a href="/api/assembly/file?session=${encodeURIComponent(current.id)}&id=${encodeURIComponent(f.id)}" download="${esc(f.name)}" title="SHA-256 ${esc(f.digest)}">${esc(f.name)}</a> · v${f.revision}${f.integrity===false?' · 文件损坏':''}</p>`;
      const currentFiles=new Map();for(const f of [...published].sort((a,b)=>a.created-b.created))if(!f.stale)currentFiles.set(f.kind+'|'+f.source,f);
      const latest=[...currentFiles.values()],currentIds=new Set(latest.map(f=>f.id)),history=published.filter(f=>!currentIds.has(f.id));
      root.innerHTML=(latest.length?'<h3>当前产品文件</h3>'+latest.map(publishedRow).join(''):'')+(history.length?`<details><summary>历史产品文件 · ${history.length}</summary>${history.map(publishedRow).join('')}</details>`:'')+`<details><summary>工程运行产物 · ${engineering.length}</summary>`+engineering.map(j=>`<h3>${esc(({'blender':'三维展示','comsol':'结构仿真','jlceda':'原理图与 PCB','product-model':'完整产品模型','event-transient':'机电与电路瞬态'}[j.engine]||j.engine))}</h3><p class="section-note">${esc(j.status)} · ${j.assembly?.revision?'产品 v'+j.assembly.revision:j.design_revision?'方案 v'+j.design_revision:j.engine==='jlceda'?'绑定的原生工程':'独立模板示例'}${j.stale?' · 旧方案产物':''}</p>${j.result?.artifacts?.some(a=>a.name==='preview.png')?`<img class="engineering-preview" src="${artifact(j.id,'preview.png')}" alt="尺寸参数化展示模型">`:''}<div class="engineering-artifacts">${(j.result?.artifacts||[]).filter(a=>['channels.csv','event-design.json','coarse.cir','fine.cir','model.blend','model.glb','preview.png','model.mph','metrics.csv','result.json','input.json','assembly.step','cad-readback.json','blender-readback.json','front.png','back.png','inside.png','exploded.png','front.svg','side.svg','top.svg','product_cad.py','energy.json','project.epro2','bom.csv','gerber.zip','schematic-netlist.net','pcb-netlist.net','schematic.epro-source','pcb.epro-source'].includes(a.name)).map(a=>`<a href="${artifact(j.id,a.name)}" download="${esc(a.name)}" title="SHA-256 ${esc(a.sha256)}">${esc(a.name)}</a>`).join('')}</div><p class="section-note">${esc(j.scope)}</p>`).join('')+'</details>'+[...new Set(files.map(f=>f.group))].map(group=>`<h3>${esc(group)}</h3>${files.filter(f=>f.group===group).map(f=>`<button class="product-file" data-product-file="${esc(f.id)}"><span>${esc(f.name)}</span><small>${esc(f.status|| (f.revision?'v'+f.revision:'用户资料'))}${f.stale?' · 来源已撤回':''}</small></button>`).join('')}`).join('');
      root.querySelectorAll('[data-product-file]').forEach(b=>b.onclick=async()=>{
        const cid=current.id;
        try{
          const file=await api('/api/conversations/'+cid+'/file?id='+encodeURIComponent(b.dataset.productFile));
          if(window.BF.getSelection()!==cid||!$('[data-section="files"]').matches('[aria-pressed="true"]'))return;
          let preview=file.content;if(file.name.endsWith('.json')){try{preview=JSON.stringify(JSON.parse(preview),null,2)}catch{}}
          root.innerHTML=`<button id="back-product-files" class="quiet">← 文件</button><h3>${esc(file.name)}</h3><p class="section-note">SHA-256 ${esc(file.sha256.slice(0,16))}…${file.run_id?'<br>计算运行 '+esc(file.run_id):''}</p><button id="download-product-file" class="quiet">下载</button><pre class="product-preview">${esc(preview)}</pre>`;
          $('#back-product-files').onclick=()=>panel(root,'files',current,execution);
          $('#download-product-file').onclick=()=>{const url=URL.createObjectURL(new Blob([file.content],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=file.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
        }catch(e){window.BF.error(e.message)}
      });
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
  function handoff(current){
    let row=document.querySelector('#task-handoff');
    if(!row){row=document.createElement('details');row.id='task-handoff';row.className='section-note';document.querySelector('#conversation').before(row)}
    const d=current?.product?.assembly?.delivery;row.hidden=!d;
    if(!d)return;
    const key=d.verdict_sha256;if(row.dataset.verdict===key)return;row.dataset.verdict=key;
    const labels={'concept':'需求与方案','digital-model':'数字模型','engineering-package':'工程文件','computational-verification':'工程验收','hardware':'实物验收'};
    row.innerHTML=`<summary>${esc(labels[d.target_stage]||d.target_stage)} · ${d.passed?'当前阶段已完成':d.missing.length+' 项待完成'}</summary><p>${esc(d.scope)}</p><p>${d.stages.map(s=>`${esc(s.label)}：${s.passed?'通过':s.status==='not_measured'?'未实测':'待完成'}`).join(' · ')}</p><button class="quiet" data-handoff-product>查看产品证据 →</button>`;
    row.querySelector('button').onclick=()=>window.ProductWorkspace.showSession();
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
    $('#connection').textContent=readiness.reasons?.length?'本地已连接 · 模型受阻':'本地已连接';
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
