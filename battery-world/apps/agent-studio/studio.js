/* Studio and Lab share selected task identity and the existing evidence APIs. */
(() => {
  const q=s=>document.querySelector(s),{api,esc}=window.BF,M=window.StudioModel;
  const projectTitles=new Map();
  let projectNames={};try{projectNames=JSON.parse(sessionStorage.getItem('bf-studio-project-names')||'{}')}catch{}
  function rememberProject(owner,title){
    projectTitles.set(owner,title);const current=window.BF.getCurrent(),first=current?.messages?.find(m=>m.role==='user'||(!m.role&&m.conversation===owner))?.text;
    if(current?.id===owner&&first&&current.title===first.trim().split('\n')[0].slice(0,60)&&current.title.length>36){
      projectNames[owner]={original:current.title,title};sessionStorage.setItem('bf-studio-project-names',JSON.stringify(projectNames));
    }
  }
  function projectLabel(c){const named=projectNames[c.id];return named?.original===c.title?named.title:c.title;}

  const positions=new Map();let lastMode='',lastStudio='task',lastLab='console',cachedCard=null,cardOwner=null,cardLoading=false,cardFetchedAt=0,headerSnapshot=null,deliveryGeneration=0;
  const domains={mechanical:'机械与结构',circuit:'电路与 PCB',firmware:'固件与模型',system:'系统与报告'};
  const icon=n=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="${{file:'M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6',export:'M12 16V3m-4 4 4-4 4 4 M5 13v7h14v-7',back:'m10 5-7 7 7 7 M3 12h18',spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z'}[n]||'M4 5h16v14H4z M9 5v14'}"/></svg>`;
  function beforeMode(next){if(lastMode&&lastMode!==next){const root=q(lastMode==='task'?'#conversation':lastMode==='product'?'#pr-workspace':lastMode==='console'?'#developer-view':'#panorama-view');positions.set(lastMode+':'+window.BF.getSelection(),root?.scrollTop||0)}lastMode=next;}
  function sync(mode){
    const lab=['console','panorama'].includes(mode);if(lab)lastLab=mode;else lastStudio=mode;
    q('#studio-space').setAttribute('aria-pressed',String(!lab));q('#lab-space').setAttribute('aria-pressed',String(lab));q('#workspace-name').textContent=lab?'Lab':'Studio';
    q('#studio-results').hidden=true;q('#studio-export').hidden=true;
    q('#studio-project-tabs').hidden=lab;syncTabs();
    q('#studio-results').disabled=!window.BF.getSelection();q('#studio-export').disabled=!window.ProductResults?.getState().snapshot?.files.length;
    document.title=lab?'BF Agent Lab':'BF Agent Studio';
    const root=q(mode==='task'?'#conversation':mode==='product'?'#pr-workspace':mode==='console'?'#developer-view':'#panorama-view');
    if(root)requestAnimationFrame(()=>{root.scrollTop=positions.get(mode+':'+window.BF.getSelection())||0;if(!matchMedia('(prefers-reduced-motion: reduce)').matches)root.animate([{opacity:.3,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:220,easing:'cubic-bezier(.2,.8,.2,1)'})});
  }
  function projectTitle(){
    const owner=window.BF.getSelection(),title=projectTitles.get(owner)||window.BF.getTitle();
    q('#studio-project-name').textContent=owner?title:'新项目';q('#studio-project-name').title=owner?title:'新项目';
  }
  const name=document.createElement('span');name.id='studio-project-name';q('#sidebar-toggle').after(name);
  const identity=document.createElement('div');identity.className='studio-project-identity';q('.topbar').prepend(identity);identity.append(q('#sidebar-toggle'),name);q('.topbar').append(q('#studio-project-tabs'));
  // A drawing trace is the Studio signature, not a simulated measurement.
  const intro=document.createElement('div');intro.className='studio-intro';intro.innerHTML='<div class="studio-intro-mark" aria-hidden="true"><svg viewBox="0 0 132 42" fill="none"><path class="studio-trace-base" d="M2 22h28c16 0 13-18 24-18s8 34 20 34 8-16 24-16h32"/><path class="studio-trace" pathLength="1" d="M2 22h28c16 0 13-18 24-18s8 34 20 34 8-16 24-16h32"/><circle cx="130" cy="22" r="2"/></svg><span>BATTERY-FREE DESIGN</span></div>';
  q('#welcome').before(intro);q('#welcome').innerHTML='从一个想法，<br><span>到一件真实的产品。</span>';
  const subtitle=document.createElement('p');subtitle.className='studio-intro-copy';subtitle.textContent='描述使用场景，和 Agent 一起探索、设计与验证。';q('#welcome').after(subtitle);
  q('#new-folder').title='新建文件夹';
  const shade=document.createElement('button');shade.id='studio-sidebar-backdrop';shade.tabIndex=-1;shade.setAttribute('aria-label','关闭项目侧栏');shade.onclick=()=>q('#sidebar-toggle').click();q('.shell').append(shade);
  q('#studio-project-search').setAttribute('aria-keyshortcuts','Meta+k Control+k');
  document.addEventListener('keydown',e=>{
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'&&!e.altKey){e.preventDefault();if(q('#session-sidebar').hidden)q('#sidebar-toggle').click();q('#studio-project-search').focus()}
    if(e.key==='Escape'&&matchMedia('(max-width:760px)').matches&&!q('#session-sidebar').hidden&&!document.querySelector('dialog[open]')&&e.target!==q('#studio-project-search')){q('#sidebar-toggle').click();q('#sidebar-toggle').focus();return;}
    if(e.key==='Escape'&&e.target===q('#studio-project-search')){e.target.value='';e.target.dispatchEvent(new Event('input',{bubbles:true}));q('#new-chat').focus()}
  });
  function syncTabs(view=window.ProductResults?.getState().view){
    const mode=document.body.dataset.studioMode;
    const page=mode==='product'?(view==='delivery'?'delivery':'product'):'conversation';
    q('#studio-project-tabs').dataset.page=page;
    q('#studio-project-tabs').querySelectorAll('button').forEach(b=>{
      if(b.dataset.studioPage===page)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
      b.disabled=b.dataset.studioPage!=='conversation'&&!window.BF.getSelection();
    });
  }
  q('#studio-project-tabs').onclick=e=>{
    const b=e.target.closest('[data-studio-page]');if(!b)return;
    if(b.dataset.studioPage==='conversation')window.BFDeveloper.setMode('task');
    else window.ProductWorkspace.showSession({view:b.dataset.studioPage==='delivery'?'delivery':'overview'});
  };
  window.addEventListener('bf-product-view',e=>syncTabs(e.detail.view));
  q('#sidebar-toggle').innerHTML=icon('panel');
  q('#new-chat').innerHTML=icon('spark')+'新建项目';
  q('#new-folder').innerHTML=icon('file');
  q('#studio-space').onclick=()=>window.BFDeveloper.setMode(lastStudio);
  q('#lab-space').onclick=()=>window.BFDeveloper.setMode(lastLab);
  q('#studio-results').onclick=()=>window.ProductWorkspace.showSession();
  q('#studio-export').innerHTML=icon('export')+'导出';
  q('#studio-export').onclick=()=>{const s=window.ProductResults.getState();if(s.snapshot)delivery(s.owner,s.scopeChoice,s.snapshot.revision)};
  window.addEventListener('bf-mode',e=>sync(e.detail.mode));
  window.addEventListener('bf-selection',()=>{projectTitle();syncTabs();q('#studio-results').disabled=!window.BF.getSelection();q('#studio-export').disabled=!window.BF.getSelection();chatCard(q('#conversation'))});
  function productHeader(snapshot,selection){
    headerSnapshot=snapshot;q('#studio-export').disabled=!snapshot?.files.length;
    if(!snapshot){
      const heading=q('.pd-heading h2');if(heading)heading.textContent=window.BF.getTitle();
      if(q('#pd-title'))q('#pd-title').textContent='正在核对项目成果…';
      if(q('#studio-scope')){q('#studio-scope').innerHTML='<option>正在加载成果范围…</option>';q('#studio-scope').disabled=true;}
      if(q('#pd-version'))q('#pd-version').hidden=true;
      if(q('#studio-reference'))q('#studio-reference').hidden=true;
      return;
    }
    const host=q('.pd-heading');if(!host)return;
    if(!snapshot.reference){rememberProject(snapshot.owner,snapshot.title);projectTitle()}
    host.querySelector('h2').textContent=snapshot.title||'产品成果';
    q('#pd-title').textContent=snapshot.reference?'独立参考工程':selection?.startsWith('case:')?'所选归档案例 · 与工作装配分别记录':snapshot.revision!=null?'工作装配 v'+snapshot.revision+' · 数字工程记录':'尚未建立产品装配 · 查看独立记录';q('#pd-check-summary').textContent='';
    q('#pd-source').setAttribute('title','独立参考工程与当前任务分别保留');
    let select=q('#studio-scope');if(!select){select=document.createElement('select');select.id='studio-scope';select.setAttribute('aria-label','成果范围');q('.pd-heading-actions').prepend(select);select.onchange=()=>window.ProductResults.scope(select.value)}
    select.innerHTML=M.choices(snapshot).map(c=>`<option value="${esc(c.id)}">${esc(c.label)}</option>`).join('');select.value=selection||'session';select.disabled=false;select.hidden=!!snapshot.reference;
    q('#pd-version').hidden=selection!=='assembly'||!!snapshot.reference||q('#pd-version').options.length<=2;
    q('#pd-source').hidden=!snapshot.reference;
    if(!q('#studio-reference')){const b=document.createElement('button');b.id='studio-reference';b.className='quiet';b.textContent='参考工程';b.onclick=()=>snapshot.reference?window.ProductWorkspace.showSession():window.ProductWorkspace.showReference();q('.pd-heading-actions').append(b)}
    q('#studio-reference').hidden=false;
    q('#studio-reference').onclick=()=>headerSnapshot?.reference?window.ProductWorkspace.showSession():window.ProductWorkspace.showReference();q('#studio-reference').textContent=snapshot.reference?'返回当前任务':'参考工程';
  }
  function visual(x,owner){
    if(!x)return '<div class="studio-no-visual">模型、图纸或计算结果生成后，会出现在这里。</div>';
    if(x.v.kind==='image')return `<button class="studio-hero-image" data-studio-preview="${esc(x.f.id)}"><img src="${esc(x.f.url)}" alt="${esc(M.fileLabel(x.f))}"><span>查看大图 ↗</span></button>`;
    if(x.v.kind==='video')return `<video controls playsinline preload="metadata" src="${esc(x.f.url)}"></video>`;
    return `<iframe title="产品三维模型" src="/model-viewer.html?session=${encodeURIComponent(owner)}&result_file=${encodeURIComponent(x.f.id)}${x.v.kind==='mesh'?'&mesh=1':''}"></iframe>`;
  }
  function overview(snapshot){
    if(!snapshot.results.length&&!snapshot.files.length)return `<section class="studio-empty-result">${icon('file')}<h3>这个范围还没有产品成果</h3><p>继续描述需求，工程模型、计算结果与设计文件生成后会归档到这里。</p><button data-studio-discuss class="primary">回到设计对话</button></section>`;
    const hero=M.hero(snapshot),findings=M.findings(snapshot),rows=snapshot.results,available=snapshot.files.filter(f=>f.integrity).length;
    const primary=findings.find(f=>rows.find(r=>r.id===f.id)?.kind==='closed-simulation')||findings.find(f=>rows.find(r=>r.id===f.id)?.kind==='spice')||findings[0];
    const title=primary?(snapshot.selectedScope!=='session'?'所选范围仍有未通过项':'历史与独立记录含未通过项'):snapshot.verdict?.passed?'当前目标阶段已完成':rows.length?'已有工程成果，等待逐项验收':'从一个想法开始';
    const outcome=primary?'查看未通过的条件与计算依据，再决定下一步设计修改。':snapshot.verdict?.scope||'可查看已有工程；文件生成与产品通过验收分别记录。';
    const media=hero?rows.filter(r=>r.domain===hero.r.domain).flatMap(r=>(r.presentations||[]).filter(v=>['image','video','model','mesh'].includes(v.kind)).map(v=>({r,v,f:r.files.find(f=>f.id===v.file_id)}))).filter(x=>x.f?.integrity):[];
    const distinct=media.filter(x=>x.r.id===hero?.r.id).slice(0,6);
    const proposal=rows.find(r=>r.kind==='proposal');const measured=(rows.find(r=>r.id===primary?.id)?.metrics||[]).filter(m=>typeof m.value==='number').slice(0,3);const metricName=n=>({peak_tip_mm:'梁端峰值 (mm)',peak_piezo_V:'压电峰值 (V)',peak_storage_V:'储能峰值 (V)',VIN_peak_V:'输入电压峰值 (V)',minimum_sampled_clearance_mm:'采样间距最小值 (mm)',normal_resistor_energy_uJ:'正常动作电阻能量 (μJ)'})[n]||n;
    return `<div class="studio-overview"><div class="studio-object-meta"><span class="studio-eyebrow">产品档案 <span aria-hidden="true">/</span> ${esc(M.scopeLabel(snapshot))}</span><span>${available} 件可读取${snapshot.files.length!==available?' · '+(snapshot.files.length-available)+' 件待恢复':''}</span></div><div class="studio-showcase"><div class="studio-visual-column"><div class="studio-hero" id="studio-hero">${visual(hero,snapshot.owner)}</div>${distinct.length?`<nav class="studio-media-tabs" aria-label="产品展示">${distinct.map((x,i)=>`<button data-studio-hero="${esc(x.f.id)}" aria-pressed="${x.f.id===hero?.f.id}"><span aria-hidden="true">${String(i+1).padStart(2,'0')}</span>${esc(M.previewLabels(distinct.map(m=>m.f)).find(l=>l.id===x.f.id)?.label)}</button>`).join('')}</nav>`:''}${hero?`<p class="studio-caption">${esc(hero.r.scope||'此图来自已归档工程。')}</p>`:''}</div><aside class="studio-design-note" aria-label="设计结论"><span class="studio-eyebrow">DESIGN REVIEW</span><button class="studio-conclusion ${primary?'has-gap':''}" data-studio-verify><span class="studio-conclusion-symbol">${primary?'!':'○'}</span><span><small>当前结论</small><strong>${title}</strong><span>${esc(outcome)}</span></span><span>↗</span></button>${primary?'<p class="studio-fidelity">仿真与数字工程记录<br>尚无实物验收依据</p>':''}${measured.length?`<dl class="studio-key-metrics">${measured.map(m=>`<div><dt>${esc(metricName(m.name))}</dt><dd>${Number(m.value).toLocaleString('zh-CN',{maximumSignificantDigits:4})}</dd></div>`).join('')}</dl>`:''}<button class="studio-note-link" data-studio-verify>查看验证依据 <span>↗</span></button></aside></div><section class="studio-section"><div class="studio-section-title"><div><span class="studio-eyebrow">ENGINEERING FILES</span><h3>每一部分，都有来处。</h3></div><span>原生工程 · 计算依据 · 设计记录</span></div><div class="studio-domain-grid">${Object.entries(domains).map(([d,name],i)=>{const items=rows.filter(r=>r.domain===d),count=snapshot.files.filter(f=>f.domain===d&&f.integrity).length;return `<section class="studio-domain"><h4><span class="studio-domain-index">${String(i+1).padStart(2,'0')}</span>${name}<small>${count} 件</small></h4>${items.length?items.slice(0,4).map(r=>`<button data-studio-result="${esc(r.id)}">${icon('file')}<span>${esc(r.label||r.kind)}<small>${esc(M.verdict(r))}</small></span><span>↗</span></button>`).join(''):count?`<button data-studio-domain="${d}">查看 ${count} 件文件 ↗</button>`:'<p class="pr-note">所选范围没有这部分成果</p>'}${items.length>4?`<button data-studio-domain="${d}">查看全部 ${items.length} 项成果 ↗</button>`:''}</section>`}).join('')}</div></section>${proposal?`<details class="studio-assumptions"><summary>需求与设计假设</summary><div>${window.BF.markdown?window.BF.markdown(JSON.stringify(proposal.inputs)):esc(JSON.stringify(proposal.inputs))}</div></details>`:''}<div class="studio-bottom-actions"><button data-studio-discuss>继续讨论设计</button><button id="pr-export" class="primary" ${!snapshot.files.length?'disabled':''}>${icon('export')}准备交付</button></div></div>`;
  }
  function verification(snapshot){return `<div class="studio-verification"><h3>验证记录</h3><p class="pr-note">执行状态、计算结论与实物验证分别展示。点击记录查看条件、曲线和原始文件。</p>${snapshot.results.map(r=>`<button class="studio-check-row" data-studio-result="${esc(r.id)}"><span class="studio-check-state ${r.design_status==='FAIL'?'failed':''}">${esc(M.verdict(r))}</span><span><b>${esc(r.label||r.kind)}</b><small>${esc(r.scope||r.applicability.reason)}</small></span><span>›</span></button>`).join('')||'<p>尚无验证记录</p>'}${snapshot.blockers?.length?`<details class="studio-assumptions"><summary>尚未满足的产品条件 · ${snapshot.blockers.length}</summary>${snapshot.blockers.map(b=>`<p>${esc(b.label)} · ${esc(({missing_files:'缺少文件',stale:'需重新验证',failed:'检查未通过',validator_unavailable:'尚无独立验证'})[b.state]||b.state)}</p>`).join('')}</details>`:''}</div>`;}
  function bindPreview(root,snapshot){root.querySelectorAll('[data-studio-preview]').forEach(b=>b.onclick=()=>window.ProductResults.preview(snapshot.files.find(f=>f.id===b.dataset.studioPreview)));root.querySelectorAll('[data-studio-hero]').forEach(b=>b.onclick=()=>{const f=snapshot.files.find(f=>f.id===b.dataset.studioHero),r=snapshot.results.find(r=>r.files.some(x=>x.id===f.id)),v=r.presentations.find(v=>v.file_id===f.id);q('#studio-hero').innerHTML=visual({r,v,f},snapshot.owner);if(!matchMedia('(prefers-reduced-motion:reduce)').matches)q('#studio-hero').animate([{opacity:.55},{opacity:1}],{duration:180});root.querySelectorAll('[data-studio-hero]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));q('.studio-caption').textContent=r.scope||'';root.querySelectorAll('[data-studio-preview]').forEach(x=>x.onclick=()=>window.ProductResults.preview(snapshot.files.find(f=>f.id===x.dataset.studioPreview)))})}
  function discuss(snapshot,result){
    const title=result?.label||snapshot.title,caseVersion=result?.case_version||(snapshot.selectedScope?.startsWith('case:')?snapshot.results[0]?.case_version:null),ref=caseVersion?'工程 '+caseVersion:snapshot.revision?'装配 v'+snapshot.revision:'当前记录';
    window.BFDeveloper.setMode('task');const input=q('#message-input'),prefix=`关于「${title}」· ${ref}：\n`;
    if(!input.value.startsWith(prefix)){input.value=prefix+input.value;input.dispatchEvent(new Event('input',{bubbles:true}))}input.focus();input.setSelectionRange(input.value.length,input.value.length);
  }
  async function chatCard(pane){
    const owner=window.BF.getSelection();if(!owner||!pane)return;
    if(owner!==cardOwner){cachedCard=null;cardOwner=owner}
    const append=()=>{if(!cachedCard?.files.length||q('#studio-result-card'))return;const atBottom=pane.scrollHeight-pane.scrollTop-pane.clientHeight<100;const b=document.createElement('button');b.id='studio-result-card';b.className='studio-result-card';const versions=M.choices(cachedCard),target=versions.find(v=>v.id===sessionStorage.getItem('bf-studio-scope-v2-'+owner))||versions[0],scope=M.scoped(cachedCard,target.id);b.innerHTML=icon('file')+`<span><b>查看产品成果</b><small>${esc(target.label)} · ${scope.files.filter(f=>f.integrity).length} 件可读取</small></span><span>›</span>`;b.onclick=()=>{if(window.EngineeringWorkspace)window.EngineeringWorkspace.open();else window.ProductWorkspace.showSession()};pane.append(b);if(atBottom)pane.scrollTop=pane.scrollHeight;};
    if(cachedCard){append();if(Date.now()-cardFetchedAt<15000)return}if(cardLoading)return;cardLoading=true;
    try{const next=await api('/api/results?'+new URLSearchParams({session:owner}));if(owner===window.BF.getSelection()){const changed=cachedCard?.snapshot_sha256!==next.snapshot_sha256;cachedCard=next;rememberProject(owner,next.title);projectTitle();cardFetchedAt=Date.now();if(changed)q('#studio-result-card')?.remove();append()}}catch{}finally{cardLoading=false}
  }
  function delivery(owner, selection='session') {
    if(owner!==window.BF.getSelection())return;
    window.ProductWorkspace.showSession({view:'delivery'});
    window.ProductResults.scope(selection);
  }
  const size=bytes=>bytes<1024*1024?Math.max(1,Math.round(bytes/1024))+' KB':(bytes/1024/1024).toLocaleString('zh-CN',{maximumFractionDigits:1})+' MB';
  async function renderDelivery(root, catalog, selection){
    const generation=++deliveryGeneration,owner=catalog.owner;
    root.innerHTML='<div class="studio-delivery-page"><p class="studio-loading" role="status">正在核对这个范围的交付文件…</p></div>';
    try{
      const snap=await api('/api/studio/delivery?'+new URLSearchParams({session:owner,selection:selection||'session',revision:catalog.revision??''}));
      if(generation!==deliveryGeneration||!root.isConnected||root.dataset.view!=='delivery'||owner!==window.BF.getSelection())return;
      if(!snap.files.length){
        root.innerHTML=`<section class="studio-empty-result">${icon('export')}<h3>交付资料尚未生成</h3><p>生成设计文件后，可以在这里核对内容、预览报告并打包带走。</p><button id="delivery-return" class="primary">回到设计对话</button></section>`;
        root.querySelector('#delivery-return').onclick=()=>window.BFDeveloper.setMode('task');return;
      }
      let purpose='summary',partial=false;
      const labels={summary:['结果概要','阅读结论、范围和文件清单。适合讨论与评审。'],report:['技术报告','PDF、TeX 与已归档引用资料，保留相对路径。'],engineering:['工程资料包','当前范围内的原生工程、源码、数据与计算记录。']};
      root.innerHTML=`<div class="studio-delivery-page"><header class="studio-delivery-heading"><div><small class="studio-eyebrow">PROJECT DELIVERY</small><h3>让设计，<span>成为可带走的成果。</span></h3><p>${esc(snap.selection_label)} · 导出固定快照</p></div>${icon('export')}</header><div class="studio-delivery-layout"><section><fieldset class="studio-purpose"><legend>选择资料用途</legend>${Object.entries(labels).map(([id,[title,desc]],i)=>`<label class="studio-export-option"><input type="radio" name="delivery-purpose" value="${id}" ${id===purpose?'checked':''} ${!snap.purposes[id].available?'disabled':''}><span class="studio-purpose-index" aria-hidden="true">${String(i+1).padStart(2,'0')}</span><span><b>${title}</b><small>${id==='report'&&!snap.purposes.report.available?'此范围尚无可读取的技术报告 PDF':desc}</small></span></label>`).join('')}</fieldset></section><aside class="studio-package-summary" aria-label="交付包内容"><div class="studio-package-cover" aria-hidden="true"><div class="studio-package-sheet"><span>BF / STUDIO</span><svg viewBox="0 0 120 48" fill="none"><path d="M0 24h25c15 0 11-18 20-18s6 36 17 36 6-18 22-18h36"/></svg><b id="delivery-format">HTML + JSON</b><small>DESIGN ARCHIVE</small></div></div><span class="studio-eyebrow">交付包内容</span><h4 id="delivery-purpose-title"></h4><p id="delivery-count"></p><p class="pr-note" id="delivery-description"></p><button id="delivery-report-preview" class="quiet" hidden>预览报告 ↗</button><label class="studio-partial" id="delivery-partial-label" hidden><input type="checkbox" id="delivery-partial">导出可读取部分，并附缺项清单</label><div id="delivery-warnings"></div><button id="delivery-download" class="primary">${icon('export')}生成结果概要</button><p id="delivery-notice" role="status" aria-live="polite"></p><details class="studio-snapshot"><summary>交付范围与版本</summary><p>${esc(snap.selection_label)}</p><p>文件来源、检查结果和原有未通过项一起保留。未宣称实物验证或采用关系。</p><code>${esc(snap.snapshot_sha256)}</code></details></aside><section class="studio-delivery-checks"><h4>文件检查</h4><p class="pr-note">依据已归档文件核对可读取性；这不是产品通过验收的判断。</p><div id="delivery-checks"></div></section></div></div>`;
      const el=id=>root.querySelector('#'+id);
      const draw=()=>{
        const plan=snap.purposes[purpose],selected=snap.files.filter(f=>plan.file_ids.includes(f.id));
        el('delivery-purpose-title').textContent=labels[purpose][0];el('delivery-format').textContent={summary:'HTML + JSON',report:'PDF + TeX',engineering:'ENGINEERING'}[purpose];root.querySelector('.studio-package-summary').dataset.purpose=purpose;
        el('delivery-count').textContent=purpose==='summary'?'2 份说明文件 · HTML + JSON':plan.readable+' 件可读取 · '+size(plan.bytes)+(plan.missing.length?' · '+plan.missing.length+' 件缺项':'');
        el('delivery-description').textContent=purpose==='summary'?'包含真实结论与整个范围的文件清单，不附大体积工程文件。':'附离线入口与校验清单。内容固定在本页打开时的快照。';
        const checkFiles=purpose==='summary'?snap.files:selected;
        el('delivery-checks').innerHTML=Object.entries(domains).map(([domain,label])=>{
          const fs=checkFiles.filter(f=>f.domain===domain),missing=fs.filter(f=>!f.integrity);
          return `<details class="studio-file-check"><summary><span class="studio-health-icon ${!fs.length||missing.length?'attention':''}">${!fs.length?'—':missing.length?'!':'✓'}</span><span>${label}</span><small>${!fs.length?'未包含':missing.length?missing.length+' 件待恢复':fs.length+' 件可读取'}</small></summary>${fs.length?fs.map(f=>`<div><span>${esc(f.name)}<small>${esc(f.source_path||f.id)}</small></span><span>${f.integrity?'可读取':'不可读取'}</span>${!f.integrity?`<p>${esc(f.error||'文件缺失或内容校验不一致，需要恢复对应原始文件。')}</p>`:''}</div>`).join(''):'<p class="pr-note">所选范围没有这部分交付文件。</p>'}</details>`;
        }).join('');
        el('delivery-report-preview').hidden=purpose!=='report';
        el('delivery-partial-label').hidden=!plan.missing.length;
        el('delivery-warnings').innerHTML=plan.warnings.length?`<details class="studio-dependency-note"><summary>报告依赖需要核对 · ${plan.warnings.length}</summary>${plan.warnings.map(n=>`<p>${esc(n)}</p>`).join('')}</details>`:'';
        el('delivery-download').disabled=!!plan.missing.length&&!partial;
        el('delivery-download').innerHTML=icon('export')+(plan.missing.length?'导出可读取资料':'生成'+labels[purpose][0]);
        el('delivery-notice').textContent=plan.missing.length&&!partial?'部分文件暂不可读取。可查看缺项，或选择交付可读取部分。':'';
      };
      el('delivery-report-preview').onclick=()=>{const ids=snap.purposes.report.file_ids;const file=snap.files.find(f=>ids.includes(f.id)&&f.integrity&&/\.pdf$/i.test(f.name)&&/report|报告|door-case/i.test((f.source_path||'')+f.name));if(file)window.ProductResults.preview(file)};
      root.querySelectorAll('[name=delivery-purpose]').forEach(r=>r.onchange=()=>{purpose=r.value;partial=false;el('delivery-partial').checked=false;draw()});
      el('delivery-partial').onchange=e=>{partial=e.target.checked;draw()};
      el('delivery-download').onclick=async()=>{
        if(owner!==window.BF.getSelection())return;
        const button=el('delivery-download'),notice=el('delivery-notice'),exportPurpose=purpose;button.disabled=true;
        root.querySelectorAll('[name=delivery-purpose],#delivery-partial').forEach(input=>input.disabled=true);
        button.setAttribute('aria-busy','true');notice.textContent='正在核对内容并生成交付包…';
        try{
          const r=await api('/api/studio/package',{session_id:owner,selection:snap.selection,revision:snap.revision,snapshot_sha256:snap.snapshot_sha256,purpose:exportPurpose,allow_partial:partial});
          if(!button.isConnected)return;
          notice.innerHTML=`交付包已准备好${r.omitted?'，缺项已保留在清单中':''}。<a class="studio-download-link" href="${esc(r.url)}" download="BF-${esc(exportPurpose)}-${esc(snap.selection.replaceAll(':','-'))}.zip">下载 ${esc(labels[exportPurpose][0])} · ${size(r.bytes)}</a>`;
          notice.querySelector('a').focus();
        }catch(error){
          notice.textContent=({STUDIO_SNAPSHOT_CHANGED:'这个范围已有更新，请重新核对文件后再导出。',STUDIO_FILES_MISSING:'部分文件不可读取，请核对缺项或选择交付可读取部分。',STUDIO_REPORT_NOT_AVAILABLE:'此范围尚无可读取的技术报告。'})[error.message]||'交付包未生成：'+error.message;
          if(error.message==='STUDIO_SNAPSHOT_CHANGED'){
            const reload=document.createElement('button');reload.type='button';reload.textContent='重新核对';reload.onclick=()=>renderDelivery(root,catalog,selection);notice.append(reload);
          }
        }finally{if(button.isConnected){button.removeAttribute('aria-busy');button.disabled=!!snap.purposes[purpose].missing.length&&!partial;root.querySelectorAll('[name=delivery-purpose]').forEach(input=>input.disabled=!snap.purposes[input.value].available);el('delivery-partial').disabled=false;}}
      };
      draw();
    }catch(error){
      if(generation!==deliveryGeneration||root.dataset.view!=='delivery')return;
      root.innerHTML=`<div class="studio-delivery-page"><h3>暂时无法读取交付清单</h3><p>${esc(error.message)}</p><button id="delivery-retry">重新读取</button></div>`;
      root.querySelector('#delivery-retry').onclick=()=>renderDelivery(root,catalog,selection);
    }
  }
  // Resize by available content width, without overwriting saved sidebar widths.
  new ResizeObserver(entries=>{
    const width=entries[0].contentRect.width;
    document.body.classList.toggle('studio-compact',width<850);
    document.body.classList.toggle('studio-narrow',width<560);
  }).observe(q('main'));
  window.StudioExperience={beforeMode,productHeader,overview,verification,bindPreview,delivery,renderDelivery,discuss,chatCard,projectLabel};
})();
