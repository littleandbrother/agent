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
  // Keep the workspace available while navigation is tucked away. The same
  // controls remain reachable by hover, keyboard and a touch disclosure button.
  const topbar=q('.topbar'),navShell=document.createElement('div'),navReveal=document.createElement('button'),navHide=document.createElement('button');
  navShell.className='studio-nav-shell';topbar.before(navShell);navShell.append(navReveal,topbar);
  topbar.id='studio-navigation';navReveal.id='studio-nav-reveal';navReveal.type='button';
  navReveal.setAttribute('aria-controls',topbar.id);navReveal.setAttribute('aria-label','展开项目导航');
  navReveal.title='移到顶部或点击展开导航';navReveal.innerHTML='<i aria-hidden="true"></i><span>对话 · 产品 · 交付</span><span aria-hidden="true">⌄</span>';
  navHide.id='studio-nav-hide';navHide.type='button';navHide.setAttribute('aria-label','收起项目导航');navHide.title='收起导航（Esc）';navHide.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 14 6-6 6 6"/></svg>';topbar.append(navHide);
  let navOpen=false,navTimer,keyboardNavigation=false;
  const inStudio=()=>document.body.dataset.workspace==='studio';
  function revealNavigation(open){
    clearTimeout(navTimer);navOpen=inStudio()&&open;
    navShell.classList.toggle('is-open',navOpen);navReveal.setAttribute('aria-expanded',String(navOpen));
    topbar.inert=inStudio()&&!navOpen;
  }
  function tuckNavigation(){
    clearTimeout(navTimer);navTimer=setTimeout(()=>{
      if(!navShell.matches(':hover')&&!(keyboardNavigation&&navShell.contains(document.activeElement)))revealNavigation(false);
    },380);
  }
  navShell.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')revealNavigation(true)});
  navShell.addEventListener('pointerleave',tuckNavigation);
  navReveal.addEventListener('click',()=>revealNavigation(true));
  navShell.addEventListener('focusin',()=>{if(keyboardNavigation)revealNavigation(true)});
  navShell.addEventListener('focusout',tuckNavigation);
  navHide.addEventListener('click',()=>{keyboardNavigation=false;revealNavigation(false);navReveal.focus()});
  document.addEventListener('pointerdown',e=>{keyboardNavigation=false;if(!navShell.contains(e.target))revealNavigation(false)},true);
  document.addEventListener('keydown',e=>{
    if(e.key==='Tab')keyboardNavigation=true;
    if(e.key==='Escape'&&navOpen&&navShell.contains(e.target)){e.preventDefault();keyboardNavigation=false;revealNavigation(false);navReveal.focus()}
  });
  window.addEventListener('bf-mode',()=>revealNavigation(false));
  revealNavigation(false);
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
  window.addEventListener('bf-mode',e=>{sync(e.detail.mode);if(e.detail.mode==='task')chatCard(q('#conversation'));});
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
  function overview(snapshot){return window.ArtifactWorkspace.overview(snapshot)}
  function verification(snapshot){return `<div class="studio-verification"><h3>验证记录</h3><p class="pr-note">执行状态、计算结论与实物验证分别展示。点击记录查看条件、曲线和原始文件。</p>${snapshot.results.map(r=>`<button class="studio-check-row" data-studio-result="${esc(r.id)}"><span class="studio-check-state ${r.design_status==='FAIL'?'failed':''}">${esc(M.verdict(r))}</span><span><b>${esc(r.label||r.kind)}</b><small>${esc(r.scope||r.applicability.reason)}</small></span><span>›</span></button>`).join('')||'<p>尚无验证记录</p>'}${snapshot.blockers?.length?`<details class="studio-assumptions"><summary>尚未满足的产品条件 · ${snapshot.blockers.length}</summary>${snapshot.blockers.map(b=>`<p>${esc(b.label)} · ${esc(({missing_files:'缺少文件',stale:'需重新验证',failed:'检查未通过',validator_unavailable:'尚无独立验证'})[b.state]||b.state)}</p>`).join('')}</details>`:''}</div>`;}
  function bindPreview(root,snapshot){window.ProductEvidence?.bind(root,snapshot);root.querySelectorAll('[data-studio-preview]').forEach(b=>b.onclick=()=>window.ProductResults.preview(snapshot.files.find(f=>f.id===b.dataset.studioPreview)));root.querySelectorAll('[data-studio-hero]').forEach(b=>b.onclick=()=>{const f=snapshot.files.find(f=>f.id===b.dataset.studioHero),r=snapshot.results.find(r=>r.files.some(x=>x.id===f.id)),v=r.presentations.find(v=>v.file_id===f.id);q('#studio-hero').innerHTML=visual({r,v,f},snapshot.owner);if(!matchMedia('(prefers-reduced-motion:reduce)').matches)q('#studio-hero').animate([{opacity:.55},{opacity:1}],{duration:180});root.querySelectorAll('[data-studio-hero]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));q('.studio-caption').textContent=r.scope||'';root.querySelectorAll('[data-studio-preview]').forEach(x=>x.onclick=()=>window.ProductResults.preview(snapshot.files.find(f=>f.id===x.dataset.studioPreview)))})}
  function discuss(snapshot,result){
    const title=result?.label||snapshot.title,caseVersion=result?.case_version||(snapshot.selectedScope?.startsWith('case:')?snapshot.results[0]?.case_version:null),ref=caseVersion?'工程 '+caseVersion:snapshot.revision?'装配 v'+snapshot.revision:'当前记录';
    window.BFDeveloper.setMode('task');const input=q('#message-input'),prefix=`关于「${title}」· ${ref}：\n`;
    if(!input.value.startsWith(prefix)){input.value=prefix+input.value;input.dispatchEvent(new Event('input',{bubbles:true}))}input.focus();input.setSelectionRange(input.value.length,input.value.length);
  }
  async function chatCard(pane){
    const owner=window.BF.getSelection();if(!owner||!pane)return;
    if(owner!==cardOwner){cachedCard=null;cardOwner=owner}
    const append=()=>{
      if(!cachedCard?.files.length)return;
      const existing=q('#studio-result-card'),atBottom=pane.scrollHeight-pane.scrollTop-pane.clientHeight<100;
      const b=existing||document.createElement('button');b.id='studio-result-card';b.className='studio-result-card';
      const versions=M.choices(cachedCard),target=versions.find(v=>v.id===(sessionStorage.getItem('bf-studio-scope-v4-'+owner)||M.preferredScope(cachedCard)))||versions[0],scope=M.scoped(cachedCard,target.id);
      b.innerHTML=icon('file')+`<span><b>查看产品成果</b><small>${esc(target.label)} · ${scope.files.filter(f=>f.integrity).length} 件可读取</small></span><span>›</span>`;
      b.onclick=()=>{if(window.EngineeringWorkspace)window.EngineeringWorkspace.open('overview',target.id);else {window.ProductWorkspace.showSession();window.ProductResults.scope(target.id)}};
      if(!existing){pane.append(b);if(atBottom)pane.scrollTop=pane.scrollHeight;}
    };
    if(cachedCard){append()}if(cardLoading)return;cardLoading=true;
    try{const next=await window.ResultCatalog.get(owner);if(owner===window.BF.getSelection()){const changed=cachedCard?.snapshot_sha256!==next.snapshot_sha256;cachedCard=next;rememberProject(owner,next.title);projectTitle();cardFetchedAt=Date.now();if(changed)q('#studio-result-card')?.remove();append()}}catch{}finally{cardLoading=false}
  }
  window.addEventListener('bf-results-updated',e=>{if(e.detail.owner===window.BF.getSelection()&&!e.detail.revision){cachedCard=e.detail.catalog;cardOwner=e.detail.owner;void chatCard(q('#conversation'))}});
  function delivery(owner, selection='latest') {
    if(owner!==window.BF.getSelection())return;
    window.ProductWorkspace.showSession({view:'delivery'});
    window.ProductResults.scope(selection);
  }
  function renderDelivery(root,catalog,selection){return window.ArtifactWorkspace.renderDelivery(root,catalog,selection)}
  // Resize by available content width, without overwriting saved sidebar widths.
  new ResizeObserver(entries=>{
    const width=entries[0].contentRect.width;
    document.body.classList.toggle('studio-compact',width<850);
    document.body.classList.toggle('studio-narrow',width<560);
  }).observe(q('main'));
  window.StudioExperience={beforeMode,productHeader,overview,verification,bindPreview,delivery,renderDelivery,discuss,chatCard,projectLabel};
})();
