/* Engineering alongside the conversation. Uses existing owner-bound result APIs. */
(() => {
  const {api,esc}=window.BF, M=window.EngineeringWorkspaceModel, S=window.StudioModel;
  const root=document.querySelector('#section-content'), pane=document.querySelector('#section-inspector');
  let owner='',catalog=null,snapshot=null,scope='',section='overview',selection='',run='',generation=0,viewGeneration=0,zoom=1,error='',loading=false,fetched=0;
  const active=()=>document.body.dataset.studioMode==='task' && document.body.dataset.workspace==='studio';
  const icon=id=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${{overview:'M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z',schematic:'M4 6h5v5h6V6h5 M4 18h5v-7 M15 11v7h5 M2 4h4v4H2z M18 4h4v4h-4z M2 16h4v4H2z M18 16h4v4h-4z',pcb:'M6 6h12v12H6z M9 2v4 M15 2v4 M9 18v4 M15 18v4 M2 9h4 M18 9h4 M2 15h4 M18 15h4 M10 10h4v4h-4z',mechanical:'m12 3 9 5v8l-9 5-9-5V8z M3 8l9 5 9-5 M12 13v8',simulation:'M2 12h4l3-8 5 16 3-8h5',bom:'M8 5h13 M8 12h13 M8 19h13 M3 5h1 M3 12h1 M3 19h1',documents:'M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6',expand:'M8 3H3v5 M16 3h5v5 M3 16v5h5 M21 16v5h-5',refresh:'M20 8a8 8 0 1 0 0 8 M20 3v5h-5',arrow:'m9 5 7 7-7 7',download:'M12 3v12m-4-4 4 4 4-4 M5 17v4h14v-4',close:'m6 6 12 12 M18 6 6 18'}[id]||'M12 5v14 M5 12h14'}"/></svg>`;
  const format=v=>typeof v==='number'?(v!==0 && Math.abs(v)<.0001?v.toExponential(4):v.toLocaleString('zh-CN',{maximumSignificantDigits:5})):typeof v==='object'?JSON.stringify(v):String(v??'未记录');
  const date=t=>Number.isFinite(t)?new Date(t*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'时间未记录';
  const note=text=>`<p class="ew-note">${esc(text)}</p>`;
  const record=r=>`<span class="ew-state ${r.design_status==='FAIL'||r.status==='FAILED'||r.predicted_design_status==='unsatisfied'?'is-attention':''}">${esc(S.verdict(r))}</span>`;
  function tableCell(value){
    if(typeof value==='string'){
      try {
        const url=new URL(value);
        if(url.protocol==='https:'&&['www.lcsc.com','lcsc.com','jlcpcb.com','www.jlcpcb.com','www.analog.com','www.cdebyte.com','www.bourns.com'].includes(url.hostname)){
          const label=url.pathname.includes('product-detail')||url.pathname.includes('partdetail')?'目录 ↗':'资料 ↗';
          return `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
        }
      }catch{}
    }
    return esc(format(value));
  }
  function chosenResult(){const rows=M.results(snapshot,section);return rows.find(r=>r.id===run)||rows[0];}
  function context(){return `${S.scopeLabel(snapshot)} · ${snapshot.title}`;}
  function preview(f){
    if(!f)return;
    if(f.integrity && f.name==='project-preview-mesh.json'){
      const d=document.createElement('dialog');d.className='model-dialog ew-preview';d.innerHTML=`<form method="dialog"><button aria-label="关闭三维预览">×</button></form><iframe title="${esc(f.name)}" src="/model-viewer.html?${new URLSearchParams({session:owner,result_file:f.id,mesh:'1'})}"></iframe>`;
      document.body.append(d);d.addEventListener('close',()=>d.remove(),{once:true});d.showModal();return;
    }
    window.ProductDeliveryView.preview({...f,session:owner},context()+' · '+(f.applicability?.reason||'已归档记录'));
  }
  function fileRows(files){return files.length?`<div class="ew-files">${files.map(f=>`<div><button data-ew-file="${esc(f.id)}">${icon('documents')}<span><b>${esc(S.fileLabel(f))}</b><small>${esc(f.name)} · ${f.integrity?'可读取':'文件待恢复'}${f.applicability?.state==='stale'?' · 需要重验':''}</small></span>${icon('arrow')}</button>${f.integrity?`<a href="${esc(f.url)}" download="${esc(f.name)}" aria-label="下载 ${esc(f.name)}">${icon('download')}</a>`:'<span class="ew-file-warning">待恢复</span>'}</div>`).join('')}</div>`:empty('尚无这部分文件','Agent 生成并归档工程资料后，会显示在这个任务中。');}
  function empty(title,text){return `<div class="ew-empty">${icon(section)}<h3>${esc(title)}</h3><p>${esc(text)}</p></div>`;}
  function checks(r){
    const rows=Object.entries(r?.checks||{});
    return `<section class="ew-card ew-checks"><div class="ew-section-heading"><h3>已记录的检查</h3>${r?record(r):''}</div>${rows.length?rows.map(([k,v])=>`<div><span class="ew-check-symbol">${v===true?'✓':v===false?'!':'○'}</span><span>${esc(k)}</span><b>${v===true?'该项通过':v===false?'未通过':v==null?'未检查':esc(format(v))}</b></div>`).join(''):note('该记录没有独立检查结果；已有文件不代表设计通过验收。')}${r?.scope?note(r.scope):''}</section>`;
  }
  function metrics(r){const list=(r?.metrics||[]).filter(m=>['number','boolean'].includes(typeof m.value)).slice(0,4);return list.length?`<div class="ew-metrics">${list.map(m=>`<div class="ew-card"><small>${esc(M.metricLabel(m.name))}</small><strong>${esc(format(m.value))}</strong><span>来自所选运行</span></div>`).join('')}</div>`:'';}
  function evidence(r){return r?`<section class="ew-card"><div class="ew-section-heading"><h3>运行与依据</h3>${record(r)}</div><p>${esc(r.label||r.kind)}</p><dl class="ew-facts"><div><dt>记录时间</dt><dd>${date(r.created)}</dd></div><div><dt>所属版本</dt><dd>${esc(r.case_version|| (r.created_revision?'装配 v'+r.created_revision:'独立运行'))}</dd></div><div><dt>适用范围</dt><dd>${esc(r.applicability?.reason||'请核对运行条件')}</dd></div></dl><details><summary>输入条件与完整检查</summary><pre>${esc(JSON.stringify({inputs:r.inputs,conditions:r.conditions,checks:r.checks,scope:r.scope},null,2))}</pre></details><button data-ew-trace="${esc(r.id)}">查看执行依据 ${icon('arrow')}</button></section>`:'';}
  function overview(){
    if(window.ProductEvidence?.groups(snapshot).length)return window.ProductEvidence.render(snapshot,{compact:true});
    const hero=S.hero(snapshot),readable=snapshot.files.filter(f=>f.integrity).length,findings=S.findings(snapshot);
    const areas=M.sections.filter(x=>x.id!=='overview');
    const recent=[...snapshot.results].sort((a,b)=>b.created-a.created).slice(0,4);
    return `<div class="ew-overview-grid"><section class="ew-card"><div class="ew-section-heading"><h3>项目内容</h3><span>${readable} 件可读取</span></div><p class="ew-note">${esc(S.scopeLabel(snapshot))} · ${snapshot.files.length-readable?`${snapshot.files.length-readable} 件文件待恢复`:'文件可读取性已核对'}</p><div class="ew-content-grid">${areas.slice(0,4).map(x=>{const fs=M.files(snapshot,x.id);return `<button data-ew-section="${x.id}" class="ew-content-item">${icon(x.id)}<b>${x.label}</b><small>${fs.filter(f=>f.integrity).length} 件可读取${fs.length?` / ${fs.length} 件`:' · 尚未归档'}</small>${icon('arrow')}</button>`}).join('')}</div></section><section class="ew-card ew-summary"><div class="ew-section-heading"><h3>当前成果与边界</h3></div>${hero?`<button class="ew-summary-image" data-ew-file="${esc(hero.f.id)}">${hero.v.kind==='image'?`<img src="${esc(hero.f.url)}" alt="${esc(S.fileLabel(hero.f))}">`:icon('mechanical')}<span>打开产品展示 ${icon('arrow')}</span></button>`:''}<b>${findings.length?'已记录的检查仍有未通过项':snapshot.verdict?.passed?'当前目标阶段已完成':'已有成果，等待逐项验证'}</b><p>${esc(findings[0]?.text||snapshot.verdict?.scope||'原生文件、计算结果和整机验收分别记录。尚无实物验收时不会显示为产品通过。')}</p><button data-ew-section="simulation">查看计算与检查 ${icon('arrow')}</button></section></div><section class="ew-section"><div class="ew-section-heading"><h3>工程部分</h3><span>选择一部分，查看图纸、数据与文件</span></div><div class="ew-capabilities">${areas.map(x=>`<button data-ew-section="${x.id}">${icon(x.id)}<span><b>${x.label}</b><small>${x.description}</small></span>${icon('arrow')}</button>`).join('')}</div></section><section class="ew-section"><div class="ew-section-heading"><h3>最近结果</h3><span>所选范围的真实归档记录</span></div><div class="ew-recent">${recent.map(r=>`<button data-ew-run="${esc(r.id)}"><span>${record(r)}</span><b>${esc(r.label||r.kind)}</b><small>${date(r.created)} · ${(r.files||[]).length} 件文件</small></button>`).join('')||note('尚未归档工程运行。')}</div></section>`;
  }
  function toolbar(views){const graphic=views.find(x=>x.f.id===selection)?.v.kind==='image';return `<div class="ew-view-toolbar"><div class="ew-view-choices" aria-label="图纸与视图">${views.map(x=>`<button data-ew-view="${esc(x.f.id)}" title="${esc(x.f.name)}" aria-pressed="${selection===x.f.id}">${esc(S.fileLabel(x.f)+(views.filter(y=>S.fileLabel(y.f)===S.fileLabel(x.f)).length>1?' · '+x.f.name.split('.').pop().toUpperCase():''))}</button>`).join('')}</div><div class="ew-zoom"><button data-ew-zoom="minus" aria-label="缩小图纸" ${!graphic?'disabled':''}>−</button><output aria-label="图纸缩放">${Math.round(zoom*100)}%</output><button data-ew-zoom="plus" aria-label="放大图纸" ${!graphic?'disabled':''}>＋</button><button data-ew-zoom="reset" aria-label="图纸适应窗口" ${!graphic?'disabled':''}>${icon('refresh')}</button><button data-ew-expand aria-label="展开当前预览" ${!selection?'disabled':''}>${icon('expand')}</button></div></div>`;}
  function detail(){
    let r=chosenResult();const all=M.files(snapshot,section),rows=M.results(snapshot,section);
    let views=M.views(snapshot,section);if(run)views=views.filter(x=>x.r?.id===r?.id);
    if(!views.some(x=>x.f.id===selection))selection=views[0]?.f.id||'';
    r=views.find(x=>x.f.id===selection)?.r||r;
    const native=(run?(r?.files||[]):all).filter(f=>M.belongs(f,section)&&!['log','receipt'].includes(f.role));
    return `${rows.length>1?`<label class="ew-run-picker">运行记录 <select id="ew-run-select" aria-label="选择工程运行"><option value="">全部记录的视图</option>${rows.map(x=>`<option value="${esc(x.id)}" ${run===x.id?'selected':''}>${esc(x.label||x.kind)} · ${date(x.created)}</option>`).join('')}</select></label>`:''}${r?.reference_only?`<aside class="ew-reference-notice" role="note"><b>${esc(r.source_revision)} · 历史工程参考</b><p>${esc(r.scope)}</p></aside>`:''}${metrics(r)}<div class="ew-detail-grid"><div><section class="ew-card ew-viewer">${toolbar(views)}<div id="ew-visual" class="ew-visual" role="region" aria-label="${esc(M.sections.find(x=>x.id===section).label)}预览">${empty('没有可读取的预览',all.length?'文件已登记，但未生成可读取的图形；下方保留原始记录。':'此范围尚未归档对应图纸或数据。')}</div><div id="ew-visual-caption" class="ew-visual-caption"></div></section>${checks(r)}<details class="ew-card ew-deliverables" open><summary>这部分的工程文件 · ${native.length}</summary>${fileRows(native)}</details></div><aside class="ew-detail-inspector">${evidence(r)}<section class="ew-card"><h3>文件与版本</h3><p class="ew-note">${esc(S.scopeLabel(snapshot))}</p>${r?.files?.length?fileRows(r.files.filter(f=>M.belongs(f,section)).slice(0,4)):note('当前记录尚无对应文件。')}<button data-ew-discuss>在对话中讨论这部分 ${icon('arrow')}</button></section></aside></div>`;
  }
  function paint(){
    if(!active())return;
    const scroll=root.scrollTop,gen=++viewGeneration;
    root.classList.add('ew-root');
    if(!owner){root.innerHTML=`<div class="ew-intro">${icon('overview')}<h2>工程工作区</h2><p>选择一个项目，或在对话中描述需求。每一部分的图纸、计算与文件将在这里汇集。</p><div class="ew-intro-sections">${M.sections.slice(1).map(x=>`<span>${icon(x.id)}${x.label}</span>`).join('')}</div></div>`;return;}
    if(!snapshot){root.innerHTML=error?`<div class="ew-intro"><h2>暂时无法读取工程记录</h2><p>${esc(error)}</p><button data-ew-refresh>重新读取</button></div>`:`<div class="ew-loading" role="status">正在整理这个项目的工程记录…</div>`;return;}
    root.innerHTML=`<div class="ew-header"><div><span class="ew-eyebrow">ENGINEERING WORKSPACE</span><h2>${esc(snapshot.title||window.BF.getTitle())}</h2><p>${esc(S.scopeLabel(snapshot))}</p></div><div class="ew-header-actions"><select id="ew-scope" aria-label="右侧工程成果范围">${S.choices(catalog).map(x=>`<option value="${esc(x.id)}" ${scope===x.id?'selected':''}>${esc(x.label)}</option>`).join('')}</select><button data-ew-refresh aria-label="刷新右侧工程记录" title="刷新工程记录">${icon('refresh')}</button></div></div><nav class="ew-tabs" role="tablist" aria-label="工程部分">${M.sections.map(x=>`<button role="tab" id="ew-tab-${x.id}" data-ew-section="${x.id}" aria-controls="ew-tabpanel" aria-selected="${section===x.id}" tabindex="${section===x.id?0:-1}">${x.label}</button>`).join('')}</nav><div id="ew-tabpanel" role="tabpanel" aria-labelledby="ew-tab-${section}" tabindex="0">${section==='overview'?overview():detail()}</div>`;
    root.scrollTop=scroll;
    if(section!=='overview')loadVisual(gen);else window.ProductEvidence?.bind(root,snapshot,{compact:true});
  }
  async function load(force=false){
    const selected=window.BF.getSelection()||'';
    if(selected!==owner){owner=selected;catalog=snapshot=null;scope='';selection=run='';section=sessionStorage.getItem('bf-ew-section-'+owner)||'overview';if(!M.sections.some(x=>x.id===section))section='overview';error='';fetched=0;generation++;loading=false;}
    if(!active()||pane.hidden){return;}
    if(!owner){paint();return;}
    if(loading)return;
    if(!force&&catalog&&Date.now()-fetched<10000){if(!root.querySelector('.ew-header'))paint();return;}
    const gen=++generation,cid=owner;loading=true;if(!snapshot)paint();
    try{
      const value=await api('/api/results?'+new URLSearchParams({session:cid}),undefined,{signal:AbortSignal.timeout(45000)});
      if(gen!==generation||cid!==window.BF.getSelection())return;
      catalog=value;
      const saved=scope||sessionStorage.getItem('bf-ew-scope-v2-'+cid),choices=S.choices(value);
      scope=choices.some(x=>x.id===saved)?saved:S.preferredScope(value);
      snapshot=S.scoped(value,scope);error='';fetched=Date.now();paint();
    }catch(e){if(gen===generation){error=e.name==='TimeoutError'?'工程清单读取超时。请稍后重试，已有记录会保留。':e.message;if(!snapshot)paint();}}
    finally{if(gen===generation)loading=false;}
  }
  async function loadVisual(gen){
    const host=root.querySelector('#ew-visual');if(!host)return;
    const x=M.views(snapshot,section).find(x=>x.f.id===selection);if(!x)return;
    const cid=owner,f=x.f;
    root.querySelector('#ew-visual-caption').innerHTML=`<b>${esc(f.name)}</b><span>${esc(x.r?.scope||f.applicability?.reason||'已归档文件')} · ${esc(f.sha256?.slice(0,12)||'哈希未记录')}</span>`;
    if(x.v.kind==='image'){host.innerHTML=`<div class="ew-graphic" style="--ew-zoom:${zoom}"><img src="${esc(f.url)}" alt="${esc(f.name)}"></div>`;host.querySelector('img').onerror=()=>{host.innerHTML=empty('预览文件暂不可读取','请刷新并核对原始文件。');};return;}
    if(['model','mesh'].includes(x.v.kind)){host.innerHTML=`<iframe title="${esc(f.name)}三维预览" src="/model-viewer.html?${new URLSearchParams({session:cid,result_file:f.id,...(x.v.kind==='mesh'?{mesh:'1'}:{})})}"></iframe>`;return;}
    if(x.v.kind==='pdf'){host.innerHTML=`<iframe title="${esc(f.name)}" src="${esc(f.url)}" sandbox="allow-same-origin"></iframe>`;return;}
    if(x.v.kind==='video'){host.innerHTML=`<video controls playsinline preload="metadata" src="${esc(f.url)}" aria-label="${esc(f.name)}"></video>`;return;}
    if(x.v.kind!=='series'){host.innerHTML=empty('可查看原始文件','此格式需要在对应原生软件中打开。');return;}
    host.innerHTML='<p class="ew-loading" role="status">正在读取实际计算数据…</p>';
    try{
      const raw=await api('/api/results/series?'+new URLSearchParams({session:cid,id:f.id}),undefined,{signal:AbortSignal.timeout(45000)});
      if(gen!==viewGeneration||cid!==owner||!host.isConnected)return;
      const s=M.series(section==='bom'?{...raw,table:true}:raw);
      if(s.table){host.innerHTML=`<div class="ew-table"><table><thead><tr>${s.headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${s.rows.map(row=>`<tr>${s.headers.map((_,i)=>`<td>${tableCell(row[i])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;return;}
      if(!s.rows.length||!s.columns.length){host.innerHTML=empty('没有可绘制的数值','原始文件仍可在下方打开。');return;}
      host.innerHTML=`<div class="ew-series"><div class="ew-series-heading"><b>同一时间轴 · 实际计算记录</b><span>${esc(raw.scope||'所选数据文件')} · ${format(raw.total_points||s.rows.length)} 点</span></div>${s.columns.slice(0,6).map(c=>{
        const values=s.rows.map(r=>r[c.index]).filter(v=>typeof v==='number'&&Number.isFinite(v)),min=Math.min(...values),max=Math.max(...values);
        const points=s.rows.filter(r=>typeof r[c.index]==='number'&&Number.isFinite(r[c.index])).map(r=>`${70+(r[0]-s.lo)/(s.hi-s.lo||1)*510},${104-(r[c.index]-min)/(max-min||1)*72}`).join(' ');
        return `<figure><figcaption>${esc(c.name)} <small>${esc(c.unit)}</small></figcaption><svg viewBox="0 0 600 132" role="img" aria-label="${esc(c.name)}实际计算曲线"><path class="ew-grid" d="M70 32H580 M70 68H580 M70 104H580 M70 24V104 M172 24V104 M274 24V104 M376 24V104 M478 24V104 M580 24V104"/><polyline points="${points}"/><text x="62" y="36" text-anchor="end">${Number(max).toPrecision(3)}</text><text x="62" y="107" text-anchor="end">${Number(min).toPrecision(3)}</text><text x="70" y="124">${Number(s.lo).toPrecision(3)}</text><text x="580" y="124" text-anchor="end">${Number(s.hi).toPrecision(3)}</text></svg></figure>`;
      }).join('')}<p class="ew-note">横轴：${esc(raw.headers[0])} (${esc(raw.units?.[0]||'单位未记录')})。显示范围来自原始数据；未补造缺失通道。</p></div>`;
    }catch(e){if(gen===viewGeneration&&host.isConnected){
      const nativeRaw=/RAW_PREVIEW_UNSUPPORTED|PREVIEW_TOO_LARGE_DOWNLOAD_SOURCE/.test(e.message||'');
      host.innerHTML=nativeRaw?empty('使用数据预览或原生软件','此原生文件不支持网页直接绘制。可选择同组 waveform.csv，或下载 RAW 在原生仿真器中查看。'):empty('暂时无法绘制数据',e.message+'；可查看原始文件。');
    }}
  }
  function choose(id){section=id;selection=run='';zoom=1;sessionStorage.setItem('bf-ew-section-'+owner,id);root.scrollTop=0;paint();const tab=root.querySelector('#ew-tab-'+id),strip=root.querySelector('.ew-tabs');tab?.focus({preventScroll:true});if(tab&&strip){const left=tab.offsetLeft-strip.offsetLeft;if(left<strip.scrollLeft)strip.scrollLeft=left;else if(left+tab.offsetWidth>strip.scrollLeft+strip.clientWidth)strip.scrollLeft=left+tab.offsetWidth-strip.clientWidth;}}
  root.addEventListener('click',e=>{
    if(!active())return;
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.ewSection){choose(b.dataset.ewSection);return;}
    if(b.hasAttribute('data-ew-refresh')){fetched=0;load(true);return;}
    if(b.dataset.ewFile){preview(snapshot.files.find(f=>f.id===b.dataset.ewFile));return;}
    if(b.dataset.ewView){selection=b.dataset.ewView;zoom=1;paint();return;}
    if(b.dataset.ewZoom){zoom=b.dataset.ewZoom==='reset'?1:Math.max(.5,Math.min(3,zoom+(b.dataset.ewZoom==='plus'?.25:-.25)));const views=M.views(snapshot,section);root.querySelector('.ew-view-toolbar').outerHTML=toolbar(run?views.filter(x=>x.r?.id===run):views);const graphic=root.querySelector('.ew-graphic');if(graphic)graphic.style.setProperty('--ew-zoom',zoom);return;}
    if(b.hasAttribute('data-ew-expand')){preview(snapshot.files.find(f=>f.id===selection));return;}
    if(b.dataset.ewRun){const r=snapshot.results.find(r=>r.id===b.dataset.ewRun);section=['closed-simulation','spice','comsol','benchmark','beam-event'].includes(r.kind)?'simulation':r.domain==='mechanical'?'mechanical':r.kind==='jlceda'?'schematic':'documents';run=r.id;selection='';paint();return;}
    if(b.dataset.ewTrace){const r=snapshot.results.find(r=>r.id===b.dataset.ewTrace);if(!r)return;if(r.source_type==='engineering')window.BFDeveloper.openTrace({job:r.id});else preview(r.files?.find(f=>f.integrity&&/result\.json$|receipt\.json$|report\.md$/.test(f.name))||r.files?.find(f=>f.integrity)||r.files?.[0]);return;}
    if(b.hasAttribute('data-ew-discuss')){window.BF.setDraft('关于「'+snapshot.title+'」的'+M.sections.find(x=>x.id===section).label+'，请根据 '+S.scopeLabel(snapshot)+' 的真实工程记录分析：');}
  });
  root.addEventListener('change',e=>{if(!active())return;if(e.target.id==='ew-scope'){scope=e.target.value;snapshot=S.scoped(catalog,scope);sessionStorage.setItem('bf-ew-scope-v2-'+owner,scope);selection=run='';paint();}if(e.target.id==='ew-run-select'){run=e.target.value;selection='';paint();}});
  root.addEventListener('keydown',e=>{const tab=e.target.closest('[role=tab]');if(!tab||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const i=M.sections.findIndex(x=>x.id===section),next=e.key==='Home'?0:e.key==='End'?M.sections.length-1:(i+(e.key==='ArrowRight'?1:-1)+M.sections.length)%M.sections.length;choose(M.sections[next].id);});
  function sync(){
    document.body.classList.toggle('engineering-workspace-active',active());root.classList.toggle('ew-root',active());
    document.querySelector('#sections-toggle').textContent=active()?'工程工作区':'方案与文件';
    pane.setAttribute('aria-label',active()?'工程工作区':'方案与文件');
    document.querySelector('#close-sections').setAttribute('aria-label',active()?'收起工程工作区':'收起方案与文件');
    const heading=pane.querySelector('.inspector-heading');heading.firstChild.textContent=active()?'工程工作区':'方案与文件';
    if(active()){if(snapshot)paint();load();}else {viewGeneration++;window.BF.refreshSections();}
    window.BFPanelSizing?.refresh();
  }
  new ResizeObserver(entries=>{pane.classList.toggle('ew-compact',entries[0].contentRect.width<720);pane.classList.toggle('ew-narrow',entries[0].contentRect.width<480);}).observe(pane);
  new MutationObserver(()=>{if(!pane.hidden&&active())load();}).observe(pane,{attributes:true,attributeFilter:['hidden']});
  window.addEventListener('bf-selection',()=>load());window.addEventListener('bf-mode',sync);
  window.EngineeringWorkspace={active,render:()=>load(),open:(id='overview',requestedScope=null)=>{
    const selected=window.BF.getSelection();
    if(requestedScope&&selected){
      sessionStorage.setItem('bf-ew-scope-v2-'+selected,requestedScope);
      if(owner===selected){scope=requestedScope;snapshot=catalog?S.scoped(catalog,scope):null;selection=run='';fetched=0;}
    }
    section=id;if(!active())window.BFDeveloper.setMode('task');window.BF.sectionVisible(true);if(snapshot)paint();load(!!requestedScope);
  },getState:()=>({owner,section,scope})};
  sync();
})();
