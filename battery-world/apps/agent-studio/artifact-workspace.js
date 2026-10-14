/* Product and delivery views of the same catalog. Never infer product acceptance. */
(() => {
  const {api,esc}=window.BF,S=window.StudioModel;
  const names={mechanical:'机械与结构',circuit:'电路与 PCB',firmware:'固件',system:'系统与文档'};
  const time=t=>t?new Date(t*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'时间未记录';
  const state=f=>({candidate:'同版候选',current:'本版生成',reused:'输入未变 · 可复用',unbound:'独立记录 · 待绑定',stale:'输入已变 · 需重验',future:'后续版本',case:'案例版本',reference:'历史参考'})[f.applicability?.state]||'归档记录';
  const size=n=>n<1048576?Math.max(1,Math.round(n/1024))+' KB':(n/1048576).toFixed(1)+' MB';
  function overview(s){
    if(window.ProductEvidence?.groups(s).length)return window.ProductEvidence.render(s);
    const M=window.EngineeringWorkspaceModel,parts=M.sections.filter(x=>!['overview','runtime','documents'].includes(x.id));
    const available=s.files.filter(f=>f.integrity).length,failed=S.findings(s);
    return `<div class="aw-product"><header class="aw-summary"><div><span class="studio-eyebrow">工程产物</span><h3>${s.files.length?'从实际产物查看当前设计':'等待第一份工程产物'}</h3><p>${esc(S.scopeLabel(s))} · ${available} 件可读取 · ${s.results.length} 条运行记录${s.run_state?' · '+esc(({PAUSED:'Pi 已暂停',FAILED:'Pi 本轮失败',RUNNING:'Pi 正在运行',COMPLETED:'Pi 本轮结束'})[s.run_state.status]||s.run_state.status):''}</p></div><button id="pr-export" class="primary" ${!s.files.length?'disabled':''}>核对交付文件 ↗</button></header><div class="aw-boundaries"><div><small>工程检查</small><b>${failed.length?failed.length+' 条记录有未通过项':s.verdict?.passed?'所选目标阶段通过':'待逐项验收'}</b></div><div><small>执行与介入</small><b>保留各作业及操作回执</b></div><div><small>物理验证</small><b>尚无实物验收依据</b></div></div>${s.selectedScope==='latest'?'<p class="aw-scope-note">这里展示各类最近记录及最近成功产物。它们可能来自不同设计版本，是否适用于同一产品需逐项核对。</p>':''}<div class="aw-parts">${parts.map(p=>{
      const files=M.files(s,p.id),rows=M.results(s,p.id),r=rows[0],issue=rows.find(x=>S.findings({results:[x]}).length);
      const useful=files.filter(f=>!['log','receipt'].includes(f.role));const shown=(useful.length?useful:files).slice(0,2);
      return `<section class="aw-part"><header><h4>${esc(p.label)}</h4><span>${files.filter(f=>f.integrity).length} 件可读取</span></header><p class="aw-part-state ${issue?'is-attention':''}">${esc(issue?S.verdict(issue):r?S.verdict(r):'尚未归档')}</p>${issue?`<p class="aw-part-note">${esc(issue.scope)}</p>`:''}<div class="aw-part-files">${shown.map(f=>`<button data-pr-file="${esc(f.id)}"><b>${esc(S.fileLabel(f))}</b><small>${esc(f.name)} · ${esc(state(f))}</small></button>`).join('')||`<p class="pr-note">尚无已登记的${esc(p.label)}文件或回执。</p>`}</div><footer><small>${r?time(r.created):'后续产物会自动同步'}</small><button data-studio-section="${p.id}" class="quiet">打开${esc(p.label)} ↗</button></footer></section>`;
    }).join('')}</div><details class="aw-records"><summary>全部最近记录与来源 · ${s.results.length}</summary>${s.results.map(r=>`<button data-studio-result="${esc(r.id)}"><span><b>${esc(r.label||r.kind)}</b><small>${esc(r.id)} · ${time(r.created)}</small></span><span>${esc(S.verdict(r))} ›</span></button>`).join('')}</details><div class="studio-bottom-actions"><button data-studio-discuss>继续讨论设计</button><button data-pr-view="source" id="aw-files">查看全部文件</button></div></div>`;
  }
  let generation=0;
  const deliveries=new Map(),filters=new Map();
  async function renderDelivery(root,catalog,selection){
    const gen=++generation,owner=catalog.owner,scope=selection||'latest';
    root.innerHTML='<div class="aw-delivery"><p role="status">正在核对实际交付文件…</p></div>';
    const cacheKey=JSON.stringify([owner,catalog.revision,scope,catalog.snapshot_sha256]);
    try{
      let snap=deliveries.get(cacheKey);
      if(!snap){snap=await api('/api/studio/delivery?'+new URLSearchParams({session:owner,selection:scope,revision:catalog.revision??''}));deliveries.clear();deliveries.set(cacheKey,snap)}
      if(gen!==generation||root.dataset.view!=='delivery'||owner!==window.BF.getSelection()||!root.isConnected)return;
      const pref='bf-delivery-purpose-'+owner;
      const filterKey=owner+':'+scope,previous=filters.get(filterKey)||{};
      let purpose=sessionStorage.getItem(pref)||'engineering',partial=false,filter=previous.filter||'',query=previous.query||'';
      if(!snap.purposes[purpose]?.available)purpose='engineering';
      const labels={engineering:'工程资料包',report:'技术报告',summary:'结果概要'};
      root.innerHTML=`<div class="aw-delivery"><header class="aw-summary"><div><span class="studio-eyebrow">交付文件</span><h3>核对内容，再导出</h3><p>${esc(snap.selection_label)} · ${snap.files.length} 件登记文件</p></div><span class="aw-live" role="status">随产物自动同步</span></header><p class="aw-scope-note">文件来源、原版本与未通过项随包保留。导出时固定文件快照；最近产物不自动视为同版本验收。</p><section class="aw-export-bar"><label>交付用途<select id="delivery-purpose">${Object.entries(labels).map(([id,label])=>`<option value="${id}" ${id===purpose?'selected':''} ${!snap.purposes[id].available?'disabled':''}>${label}${!snap.purposes[id].available?' · 尚未生成':''}</option>`).join('')}</select></label><div><b id="delivery-count"></b><small id="delivery-description"></small></div><button id="delivery-download" class="primary">生成工程资料包</button></section><label id="delivery-partial-label" class="studio-partial" hidden><input type="checkbox" id="delivery-partial">导出可读取部分，并附缺项清单</label><p id="delivery-notice" role="status" aria-live="polite"></p><div id="delivery-warnings"></div><div class="aw-file-toolbar"><label class="sr-only" for="delivery-filter">文件领域</label><select id="delivery-filter"><option value="">全部领域</option>${Object.entries(names).map(([id,label])=>`<option value="${id}">${label}</option>`).join('')}</select><label class="sr-only" for="delivery-search">搜索交付文件</label><input id="delivery-search" type="search" placeholder="搜索文件名、作业编号…"><span id="delivery-visible-count"></span></div><div id="delivery-files" class="aw-file-table"></div><details class="aw-records"><summary>交付快照与检查范围</summary><p>${esc(snap.scope)}</p><code>${esc(snap.snapshot_sha256)}</code></details></div>`;
      const el=id=>root.querySelector('#'+id);
      function drawFiles(){
        filters.set(filterKey,{filter,query});
        const plan=snap.purposes[purpose],ids=new Set(plan.file_ids);
        const included=purpose==='summary'?snap.files:snap.files.filter(f=>ids.has(f.id));
        const files=included.filter(f=>(!filter||f.domain===filter)&&(!query||(f.name+' '+f.id).toLowerCase().includes(query)));
        el('delivery-visible-count').textContent=files.length+' / '+included.length+' 件';
        el('delivery-files').innerHTML=files.length?`<table><thead><tr><th>文件 / 来源</th><th>领域与适用范围</th><th>文件检查</th><th>操作</th></tr></thead><tbody>${files.map(f=>`<tr><td><b>${esc(f.name)}</b><small>${esc(f.result_id)}${f.created_revision?' · 装配 v'+f.created_revision:''}</small></td><td>${esc(names[f.domain]||f.domain)}<small>${esc(state(f))}</small></td><td><span class="aw-integrity ${f.integrity?'':'is-attention'}">${f.integrity?'可读取':'待恢复'}</span>${f.integrity_basis?'<small title="导出回执只记录路径，未提供生成时内容哈希；此处核对当前文件">当前文件已核对</small>':''}<small>${size(f.bytes||0)}</small></td><td>${f.integrity?`<button class="quiet" data-delivery-preview="${esc(f.id)}">查看</button><a href="${esc(f.url)}" download="${esc(f.name)}" aria-label="下载 ${esc(f.name)}">↓</a>`:'—'}</td></tr>`).join('')}</tbody></table>`:'<p class="aw-empty">此范围没有符合条件的文件。</p>';
      }
      function draw(){
        const plan=snap.purposes[purpose];sessionStorage.setItem(pref,purpose);
        el('delivery-count').textContent=purpose==='summary'?'2 份说明文件 · HTML + JSON':plan.readable+' 件可读取 · '+size(plan.bytes)+(plan.missing.length?' · '+plan.missing.length+' 件缺项':'');
        el('delivery-description').textContent=purpose==='summary'?'含结论与清单，不附工程文件。':'含原始文件、离线入口与校验清单。';
        el('delivery-partial-label').hidden=!plan.missing.length;
        el('delivery-download').disabled=!plan.available||!!plan.missing.length&&!partial||!snap.files.length;
        el('delivery-download').textContent='生成'+labels[purpose];
        el('delivery-warnings').innerHTML=plan.warnings.length?`<details><summary>报告依赖待核对 · ${plan.warnings.length}</summary>${plan.warnings.map(x=>`<p>${esc(x)}</p>`).join('')}</details>`:'';
        el('delivery-notice').textContent=plan.missing.length&&!partial?'部分文件暂不可读取，请核对缺项或选择导出可读取部分。':'';
        drawFiles();
      }
      el('delivery-purpose').onchange=e=>{purpose=e.target.value;partial=false;el('delivery-partial').checked=false;draw()};
      el('delivery-partial').onchange=e=>{partial=e.target.checked;draw()};
      el('delivery-filter').onchange=e=>{filter=e.target.value;drawFiles()};
      el('delivery-search').oninput=e=>{query=e.target.value.toLowerCase();drawFiles()};
      el('delivery-files').onclick=e=>{const b=e.target.closest('[data-delivery-preview]');if(b)window.ProductResults.preview(snap.files.find(f=>f.id===b.dataset.deliveryPreview))};
      el('delivery-download').onclick=async()=>{
        if(owner!==window.BF.getSelection())return;
        const button=el('delivery-download'),notice=el('delivery-notice'),selectedPurpose=purpose;
        root.dataset.exporting='true';root.dataset.exportOwner=owner;root.dataset.refreshPending='false';button.disabled=true;button.setAttribute('aria-busy','true');el('delivery-purpose').disabled=true;el('delivery-partial').disabled=true;
        notice.textContent='正在核对文件快照并打包…';
        try{
          const r=await api('/api/studio/package',{session_id:owner,selection:snap.selection,revision:snap.revision,snapshot_sha256:snap.snapshot_sha256,purpose:selectedPurpose,allow_partial:partial});
          if(gen!==generation||!button.isConnected||owner!==window.BF.getSelection())return;
          notice.innerHTML=`已生成${r.omitted?'，缺项已附清单':''}。<a href="${esc(r.url)}" download="BF-${esc(selectedPurpose)}.zip">下载${esc(labels[selectedPurpose])} · ${size(r.bytes)}</a>`;
        }catch(error){
          if(gen!==generation||!button.isConnected)return;
          notice.textContent=error.message==='STUDIO_SNAPSHOT_CHANGED'?'产物已更新，本次未导出旧快照。请重新核对。':'未能生成交付包：'+error.message;
          if(error.message==='STUDIO_SNAPSHOT_CHANGED')root.dataset.refreshPending='true';
        }finally{
          root.dataset.exporting='false';
          if(gen===generation&&button.isConnected){
            button.removeAttribute('aria-busy');button.disabled=!!snap.purposes[purpose].missing.length&&!partial;el('delivery-purpose').disabled=false;el('delivery-partial').disabled=false;
            if(root.dataset.refreshPending==='true'){
              const update=document.createElement('button');update.textContent='核对新产物';update.onclick=()=>{deliveries.clear();window.ProductResults.focus({view:'delivery'})};notice.append(update);
            }
          }
        }
      };
      el('delivery-filter').value=filter;el('delivery-search').value=query;draw();
    }catch(error){
      if(gen!==generation||root.dataset.view!=='delivery'||owner!==window.BF.getSelection())return;
      root.innerHTML=`<div class="aw-delivery"><p>交付清单暂不可读：${esc(error.message)}</p><button id="delivery-retry">重新读取</button></div>`;
      root.querySelector('#delivery-retry').onclick=()=>renderDelivery(root,catalog,selection);
    }
  }
  window.addEventListener('bf-results-status',e=>{
    if(e.detail.owner!==window.BF.getSelection())return;
    document.querySelectorAll('.aw-live').forEach(node=>{node.dataset.connected=String(e.detail.connected);node.textContent=e.detail.connected?'已同步 · '+new Date(e.detail.checkedAt).toLocaleTimeString('zh-CN',{hour12:false}):'连接中断 · 保留上次清单'});
  });
  window.ArtifactWorkspace={overview,renderDelivery};
})();
