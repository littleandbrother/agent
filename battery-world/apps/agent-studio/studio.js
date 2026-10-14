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
    q('#pd-title').textContent=snapshot.reference?'独立参考工程':selection==='candidate'?snapshot.candidate.label+' · 同版工程':selection?.startsWith('case:')?'所选归档案例 · 与工作装配分别记录':snapshot.revision!=null?'工作装配 v'+snapshot.revision+' · 数字工程记录':'尚未建立产品装配 · 查看独立记录';q('#pd-check-summary').textContent='';
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
      const versions=M.choices(cachedCard),target=versions.find(v=>v.id===(sessionStorage.getItem('bf-studio-scope-v5-'+owner)||M.preferredScope(cachedCard)))||versions[0],scope=M.scoped(cachedCard,target.id);
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

/* Four-column progress: independent public facts, owner-scoped browser state. */
(() => {
  const q=s=>document.querySelector(s),M=window.ExecutionProgressModel,esc=window.BF.esc;
  const pane=q('#execution-progress'),content=q('#progress-content');if(!pane||!M)return;
  let owner=null,data=null,model=null,connected=true,generation=0,flight=null,refreshTimer=null,manual={},selectedNode=null,historyView=false,lastRender='',lastPanel='progress';
  const menuToggle=document.createElement('button'),menu=document.createElement('section');
  menuToggle.id='studio-layout-toggle';menuToggle.type='button';menuToggle.className='quiet';
  menuToggle.setAttribute('aria-label','显示与隐藏面板');menuToggle.setAttribute('aria-controls','studio-layout-menu');menuToggle.setAttribute('aria-expanded','false');menuToggle.title='显示与隐藏面板';
  menuToggle.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M8 4v16M16 4v16"/></svg>';
  menu.id='studio-layout-menu';menu.hidden=true;menu.setAttribute('aria-label','面板布局');
  menu.innerHTML='<p>显示面板</p><button id="layout-projects-toggle" type="button" aria-controls="session-sidebar"><span>项目</span><small></small></button><footer><button id="layout-focus-chat" type="button">只看对话</button><button id="layout-reset-widths" type="button">默认宽度</button></footer>';
  q('main').prepend(menuToggle,menu);menu.querySelector('footer').before(q('#progress-toggle'),q('#sections-toggle'));
  q('#progress-toggle').innerHTML='<span>执行进展</span><small></small>';q('#sections-toggle').innerHTML='<span>工程工作区</span><small></small>';
  const closeMenu=()=>{menu.hidden=true;menuToggle.setAttribute('aria-expanded','false')};
  menuToggle.onclick=()=>{menu.hidden=!menu.hidden;menuToggle.setAttribute('aria-expanded',String(!menu.hidden));if(!menu.hidden)menu.querySelector('button').focus({preventScroll:true})};
  document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target)&&!menuToggle.contains(e.target))closeMenu()});
  menu.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();closeMenu();menuToggle.focus({preventScroll:true})}});
  q('#layout-projects-toggle').onclick=()=>{q('#sidebar-toggle').click();closeMenu();menuToggle.focus({preventScroll:true})};
  q('#layout-focus-chat').onclick=()=>{if(!document.body.classList.contains('sidebar-collapsed'))q('#sidebar-toggle').click();toggle(false);window.BF.sectionVisible(false);closeMenu();menuToggle.focus({preventScroll:true})};
  q('#layout-reset-widths').onclick=()=>{window.BFPanelSizing?.reset();closeMenu();menuToggle.focus({preventScroll:true})};
  const preference='bf-execution-progress.v1',manualKey=id=>'bf-task-expansion.v1-'+id;
  const stamp=t=>t?new Date(t*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';
  const lamp=s=>{const x=M.state(s);return `<span class="xp-lamp ${x.tone}" aria-label="${esc(x.label)}">${x.icon}</span>`};
  function isTask(){return document.body.dataset.workspace==='studio'&&document.body.dataset.studioMode==='task';}
  function layout(){
    const task=isTask();let open=localStorage.getItem(preference)!=='closed';
    if(task&&innerWidth<=1280&&open&&!document.body.classList.contains('sections-hidden')){
      if(lastPanel==='workspace'){localStorage.setItem(preference,'closed');open=false}else window.BF.sectionVisible(false);
    }
    document.body.classList.toggle('execution-progress-open',task&&open);
    document.body.classList.toggle('execution-progress-layout',task);
    pane.hidden=!task||!open;menuToggle.hidden=document.body.dataset.workspace!=='studio';
    if(menuToggle.hidden)closeMenu();
    q('#progress-toggle').hidden=!task;q('#sections-toggle').hidden=!task;q('#layout-focus-chat').hidden=!task;
    [[q('#layout-projects-toggle'),!document.body.classList.contains('sidebar-collapsed')],[q('#progress-toggle'),open],[q('#sections-toggle'),!document.body.classList.contains('sections-hidden')]].forEach(([button,shown])=>{button.setAttribute('aria-pressed',String(shown));button.setAttribute('aria-expanded',String(shown));button.querySelector('small').textContent=shown?'显示中':'已隐藏'});
    const rect=q('.app-body').getBoundingClientRect();document.documentElement.style.setProperty('--xp-overlay-top',rect.top+'px');
    window.BFPanelSizing?.refresh();
  }
  function toggle(open){if(open){lastPanel='progress';if(innerWidth<=1280)window.BF.sectionVisible(false)}localStorage.setItem(preference,open?'open':'closed');layout();if(open){void load();q('#progress-close').focus({preventScroll:true})}else menuToggle.focus({preventScroll:true});}
  q('#progress-toggle').onclick=()=>{toggle(!document.body.classList.contains('execution-progress-open'));closeMenu()};
  q('#progress-close').onclick=()=>toggle(false);
  q('#sections-toggle').onclick=()=>{const show=document.body.classList.contains('sections-hidden');if(show){lastPanel='workspace';if(innerWidth<=1280)toggle(false)}window.BF.sectionVisible(show);closeMenu();menuToggle.focus({preventScroll:true})};
  q('#progress-refresh').onclick=()=>void load(true);
  function leafHTML(n){return `<li class="xp-task ${n.status==='PASS'?'xp-passed':''}"><button class="xp-task-select" data-xp-task="${esc(n.id)}"><span>${lamp(n.status)}<span>${esc(n.label)}</span></span><small>${esc(M.state(n.status).label)}</small></button></li>`;}
  function graphHTML(rows){
    if(!rows.length)return '<p class="xp-empty">尚无冻结的设计版本。</p>';
    const index=new Map(rows.map((r,i)=>[r.id,i])),height=rows.length*68;
    const x=r=>18+Math.min(r.depth,3)*11,y=i=>i*68+29;
    const lines=rows.map((r,i)=>{const id=r.explicit_parent||r.timeline_predecessor,j=index.get(id);if(j===undefined)return '';const parent=rows[j];return `<path d="M${x(parent)} ${y(j)} V${y(i)} H${x(r)}" class="${r.link_kind==='sequence'?'xp-sequence':''}"/>`}).join('');
    const dots=rows.map((r,i)=>`<circle cx="${x(r)}" cy="${y(i)}" r="4" class="xp-version-dot ${r.current?'xp-current-dot':''}"/>`).join('');
    return `<div class="xp-version-map"><svg class="xp-version-links" width="62" height="${height}" viewBox="0 0 62 ${height}" aria-hidden="true">${lines}${dots}</svg><ol>${rows.map(r=>`<li class="${r.current?'xp-current-version':''}"><button data-xp-version="${esc(r.id)}" aria-pressed="${selectedNode?.id===r.id}"><span class="xp-version-label"><b>${esc(r.title)}</b><small>${esc(r.adoption)}${r.missing_parent?' · 父版本未在此列表':''}</small></span><span class="xp-version-arrow" aria-hidden="true">›</span></button></li>`).join('')}</ol></div>`;
  }
  function render(){
    if(!model){content.innerHTML='<p class="xp-empty">'+(owner?'正在核对任务、版本和检查…':'选择一个项目，查看当前任务和设计版本。')+'</p>';return;}
    const c=model.counts,firstIssue=model.issues[0],phase=model.phase;
    const goal=phase?.goal||phase?.objective||phase?.title;
    const purpose=typeof goal==='string'?goal:phase?.required_project_kinds?.join('、')||null;
    const html=`<section class="xp-overview"><span class="xp-eyebrow">当前设计</span><strong>${esc(model.version)}</strong><p>${c.passed} 项已验收<span> / ${c.total} 项必要检查</span></p><div class="xp-counts"><span>${c.running?'<i class="xp-activity-dot"></i> 1 项执行中': '当前无执行中的动作'}</span>${c.failed?`<span class="xp-error-count">${c.failed} 项未通过</span>`:''}</div><div class="xp-claim"><span>数字工程</span><b>${model.full_product_passed?'已验收':'尚未完整验收'}</b><span>物理验证</span><b>未进行</b></div></section>
      ${purpose?`<details class="xp-phase"><summary>本轮具体目标</summary><p>${esc(purpose)}</p><small>原会话 · ${esc(phase.id)} · ${esc(phase.queue_status||'等待核对')}</small></details>`:''}
      ${model.activity?`<section class="xp-now"><span>${lamp('RUNNING')}当前动作</span><b>${esc(model.activity.label)}</b><small>由真实运行事件更新 · 执行结束仍需验收</small></section>`:model.execution?.error?`<section class="xp-now xp-interrupted"><span>${lamp('BLOCKED')}执行中断</span><small>${esc(model.execution.error)}</small><small>执行错误与设计未通过分别记录。</small></section>`:''}
      <section class="xp-tree-section"><div class="xp-section-title"><h3>任务与验收</h3><button class="quiet" data-xp-follow title="展开当前活动与未关闭任务">返回当前</button></div><details class="xp-task-root" ${M.expanded({id:'root',status:model.status,active:model.status!=='PASS'},manual)?'open':''} data-xp-expand="root"><summary>${lamp(model.status)}<span>完成本篇声明范围的数字工程<small>${esc(M.state(model.status).label)}</small></span></summary><div class="xp-task-groups">${model.groups.map(g=>`<details data-xp-expand="${esc(g.id)}" ${M.expanded(g,manual)?'open':''}><summary>${lamp(g.active?'RUNNING':g.status)}<span>${esc(g.label)}<small>${g.children.filter(l=>l.status==='PASS').length} / ${g.children.length} 项已验收</small></span></summary><ul>${g.children.map(leafHTML).join('')}</ul></details>`).join('')}</div></details><p class="xp-scope-note">绿色仅对应当前输入与该项检查范围。</p></section>
      <section class="xp-version-section"><div class="xp-section-title"><h3>设计版本</h3><small>${model.versions.some(r=>r.link_kind==='ancestry')?'明确父版本':'装配修订时间线'}</small></div>${graphHTML(model.versions)}${model.versions.some(r=>r.kind==='assembly')?'<p class="xp-scope-note">虚线表示修订先后，不表示采用或性能改善。</p>':''}</section>
      <details class="xp-issues" data-xp-expand="issues" ${M.expanded({id:'issues',status:firstIssue?'FAIL':'NOT_CHECKED'},manual)?'open':''}><summary>未关闭问题 <b>${model.issues.length}</b></summary>${model.issues.length?model.issues.map(i=>`<button data-xp-issue="${esc(i.id)}"><span>${lamp(i.state==='RECHECK_REQUIRED'?'STALE':'FAIL')}${esc(i.summary)}</span><small>${esc(i.diagnosis.attribution)} · ${esc(i.diagnosis.label)}</small></button>`).join(''):'<p>尚无有效未关闭问题记录；未检查项仍保留。</p>'}<details class="xp-cause-legend"><summary>问题分类如何阅读</summary><p>现象、当前解释与确认结论分别记录。</p><ul>${M.causes.map(([,label])=>'<li>'+esc(label)+'</li>').join('')}</ul><small>任务不可实现需要充分证据；不能由重试失败推断。</small></details></details>`;
    if(html!==lastRender){
      const top=content.scrollTop,focus=document.activeElement?.getAttribute('data-xp-task')||document.activeElement?.getAttribute('data-xp-version');
      content.innerHTML=html;lastRender=html;content.scrollTop=top;
      content.querySelectorAll('[data-xp-expand]').forEach(el=>{el.querySelector(':scope > summary')?.addEventListener('click',()=>{el.dataset.userToggle='yes'});el.addEventListener('toggle',()=>{if(el.dataset.userToggle!=='yes')return;delete el.dataset.userToggle;manual[el.dataset.xpExpand]=el.open;try{localStorage.setItem(manualKey(owner),JSON.stringify(manual))}catch{}})});
      content.querySelectorAll('[data-xp-task]').forEach(b=>b.onclick=()=>showTask(model.leaves.find(x=>x.id===b.dataset.xpTask)));
      content.querySelectorAll('[data-xp-version]').forEach(b=>b.onclick=()=>showVersion(model.versions.find(x=>x.id===b.dataset.xpVersion)));
      content.querySelectorAll('[data-xp-issue]').forEach(b=>b.onclick=()=>showIssue(model.issues.find(x=>x.id===b.dataset.xpIssue)));
      content.querySelector('[data-xp-follow]').onclick=followCurrent;
      if(focus)content.querySelectorAll('[data-xp-task],[data-xp-version]').forEach(b=>{if(b.dataset.xpTask===focus||b.dataset.xpVersion===focus)b.focus({preventScroll:true})});
    }
    freshness();
  }
  function freshness(){const el=q('#progress-freshness');if(!model){el.textContent='正在读取';return;}const stale=!connected||Date.now()/1000-model.checked_at>50;el.textContent=(stale?'保留上次快照 · ':'已核对 · ')+stamp(model.checked_at)+(stale?' · 状态待刷新':'');el.classList.toggle('xp-stale',stale);}
  function followCurrent(){historyView=false;selectedNode=null;manual={};try{localStorage.removeItem(manualKey(owner))}catch{}q('#xp-inspection')?.remove();lastRender='';render();const active=content.querySelector('.xp-now');active?.scrollIntoView({block:'nearest',behavior:'auto'});}
  function inspect(title,body,historical=false){
    lastPanel='workspace';if(innerWidth<=1280)toggle(false);window.BF.sectionVisible(true);let panel=q('#xp-inspection');if(!panel){panel=document.createElement('section');panel.id='xp-inspection';panel.setAttribute('aria-label','进展详情');q('#section-inspector').append(panel)}
    panel.innerHTML=`<header><span>${historical?'只读历史版本':'任务与证据'}</span><button class="quiet" aria-label="关闭进展详情">×</button></header><div class="xp-inspection-content"><h2>${esc(title)}</h2>${body}</div>`;
    panel.querySelector('header button').onclick=()=>{panel.remove();historyView=false;selectedNode=null;lastRender='';render()};
    panel.querySelectorAll('[data-xp-evidence]').forEach(a=>a.href='/api/execution-progress/artifact?'+new URLSearchParams({session:owner,path:a.dataset.xpEvidence}));
    panel.querySelector('[data-xp-workspace]')?.addEventListener('click',e=>{panel.remove();window.EngineeringWorkspace?.open(e.currentTarget.dataset.xpWorkspace)});
    panel.querySelector('button')?.focus({preventScroll:true});layout();
  }
  const evidenceHTML=e=>e?`<a class="xp-evidence-link" data-xp-evidence="${esc(e.path)}" target="_blank" rel="noopener">打开独立检查回执 ↗</a><details><summary>证据版本</summary><code>${esc(e.path)}</code><code>SHA-256 ${esc(e.sha256)}</code></details>`:'<p class="xp-empty">尚无可用于通过判定的独立检查证据。</p>';
  function showTask(n){if(!n)return;historyView=false;selectedNode=null;inspect(n.label,`<p class="xp-detail-status">${lamp(n.status)}${esc(M.state(n.status).label)} · ${esc(n.version)}</p><dl><dt>目标与通过条件</dt><dd>${esc(n.condition)}</dd><dt>前置依赖</dt><dd>${n.dependencies.length?n.dependencies.map(esc).join('、'):'该记录未提供明确依赖；不推断已满足。'}</dd></dl>${evidenceHTML(n.evidence)}${n.issues.map(i=>'<p>'+esc(i.summary)+'</p>').join('')}<button data-xp-workspace="${{circuit:'schematic',firmware:'firmware',mechanical:'mechanical',power:'simulation',delivery:'documents',definition:'overview'}[n.section]}">查看关联工程</button>`);}
  function showIssue(i){if(!i)return;historyView=false;selectedNode=null;const d=i.diagnosis;inspect('问题详情',`<dl><dt>现象</dt><dd>${esc(d.phenomenon)}</dd><dt>当前解释</dt><dd>${esc(d.label)}</dd><dt>确认程度</dt><dd>${esc(d.attribution)}</dd><dt>问题状态</dt><dd>${esc(i.state)}</dd><dt>关闭条件</dt><dd>当前输入对应的独立复查确认该问题已解决；保留此前记录。</dd></dl>${evidenceHTML(i.artifact)}`);}
  function showVersion(n){if(!n)return;historyView=!n.current;selectedNode=n;const gate=M.rollbackEligibility(model,n);
    inspect(n.title,`<p class="xp-history-banner">${n.current?'正在查看当前设计':'正在只读查看历史设计；当前执行和采用版本保持原状态。'}</p><dl><dt>版本身份</dt><dd><code>${esc(n.id)}</code></dd><dt>来自</dt><dd>${esc(n.explicit_parent|| (n.kind==='assembly'?'装配修订记录未保存父版本关系':'起始设计或父版本未在此列表'))}</dd><dt>当前关系</dt><dd>${esc(n.adoption)}</dd><dt>修改来源</dt><dd>${esc(n.actor||'来源见版本记录')}</dd><dt>已知差异</dt><dd>${n.changes.length?n.changes.map(esc).join('、'):'选择工程查看实际内容；版本连线本身不表示改善。'}</dd></dl><details><summary>文件与输入摘要</summary>${Object.entries(n.hashes||{}).map(([k,v])=>'<code>'+esc(k)+': '+esc(v)+'</code>').join('')}</details><div id="xp-history-files"><button id="xp-load-history">查看本版实际工程</button></div><button id="xp-restore-version" ${gate.allowed?'':'disabled'}>恢复采用此设计</button><p class="xp-scope-note">${esc(gate.reason)}</p><button id="xp-return-current" class="quiet">返回当前执行</button>`,historyView);
    q('#xp-load-history').onclick=()=>void historyFiles(n);q('#xp-restore-version').onclick=()=>void restoreVersion(n);q('#xp-return-current').onclick=followCurrent;
    lastRender='';render();
  }
  async function historyFiles(n){const captured=owner,id=n.id,g=generation;const box=q('#xp-history-files');box.innerHTML='<p>读取冻结版本…</p>';try{
    if(n.kind==='assembly'){
      const catalog=await window.ResultCatalog.get(captured,String(n.revision));if(g!==generation||owner!==captured||selectedNode?.id!==id)return;
      const files=catalog.files.filter(f=>f.integrity&&['current','reused'].includes(f.applicability?.state));
      box.innerHTML=files.length?'<p class="xp-scope-note">仅展示与此装配版本匹配的实际文件。</p>'+files.slice(0,30).map(f=>`<button data-xp-file="${esc(f.id)}">${esc(f.label||f.name)}</button>`).join(''):'<p>该版尚无可读且匹配的原生文件；已有修订记录仍保留。</p>';
      box.querySelectorAll('[data-xp-file]').forEach(b=>b.onclick=()=>window.ProductResults.preview(files.find(f=>f.id===b.dataset.xpFile)));
    }else{
      const source=await window.BF.api('/api/design-lab',{session_id:captured,action:'source',design_id:id});if(g!==generation||selectedNode?.id!==id)return;
      box.innerHTML='<p>冻结的设计源码 · 只读</p>'+Object.entries(source.sources||source.design?.sources||{}).map(([name,text])=>`<details><summary>${esc(name)}</summary><pre><code>${esc(text)}</code></pre></details>`).join('');
    }
  }catch(e){if(g===generation&&selectedNode?.id===id)box.textContent='读取失败：'+e.message;}}
  async function restoreVersion(n){
    const captured=owner,g=generation;let latest;try{latest=await window.BF.api('/api/execution-progress?'+new URLSearchParams({session:captured}));}catch(e){window.BF.error(e.message);return;}
    if(g!==generation||owner!==captured)return;
    const freshModel=M.project(latest,window.BF.getEvents(),true),candidate=freshModel.versions.find(x=>x.id===n.id),eligibility=M.rollbackEligibility(freshModel,candidate);
    if(!eligibility.allowed){window.BF.error(eligibility.reason);return;}
    const dialog=document.createElement('dialog');dialog.className='xp-restore-dialog';dialog.innerHTML=`<h2>恢复采用此设计</h2><p>${esc(candidate.id)}</p><p>这会新增一次采用事件。历史尝试、费用与失败保留；构建、执行和相关检查需重新核对。不会重跑任何仿真。</p><form method="dialog"><button value="cancel">取消</button><button value="restore">恢复采用</button></form>`;document.body.append(dialog);dialog.showModal();
    dialog.addEventListener('close',async()=>{const proceed=dialog.returnValue==='restore';dialog.remove();if(!proceed||owner!==captured||g!==generation)return;try{
      await window.BF.api('/api/design-lab',{session_id:captured,action:'adopt',design_id:candidate.id,expected_revision:latest.design_lab.revision,rationale:'用户通过执行进展视图恢复历史设计；保留全部历史与费用，相关下游检查需复查。'});
      followCurrent();await load(true);
    }catch(e){window.BF.error(e.message)}},{once:true});
  }
  function updateModel(){if(!data)return;model=M.project(data,window.BF.getEvents(),connected);render();}
  async function load(force=false){
    const target=window.BF.getSelection();if(!target){owner=null;data=model=null;content.innerHTML='<p class="xp-empty">选择一个项目，查看当前任务和设计版本。</p>';return;}
    if(target!==owner){owner=target;generation++;flight=null;data=model=null;manual={};try{manual=JSON.parse(localStorage.getItem(manualKey(owner))||'{}')}catch{}selectedNode=null;historyView=false;q('#xp-inspection')?.remove();lastRender='';render();}
    if(flight)return flight;if(!force&&data&&Date.now()/1000-data.checked_at<15){updateModel();return;}
    const g=generation,id=owner;
    flight=(async()=>{try{const next=await window.BF.api('/api/execution-progress?'+new URLSearchParams({session:id}),undefined,{signal:AbortSignal.timeout(30000)});if(g!==generation||id!==window.BF.getSelection())return;data=next;connected=true;updateModel();}catch(e){if(g!==generation)return;connected=false;if(model)updateModel();else content.innerHTML='<p class="xp-empty">无法读取当前进展：'+esc(e.message)+'。已有工程保留，可点击刷新重试。</p>';freshness();}finally{if(g===generation)flight=null;}})();return flight;
  }
  window.addEventListener('bf-selection',()=>{void load();layout()});window.addEventListener('bf-mode',()=>{layout();if(isTask())void load()});
  window.addEventListener('bf-runtime-events',e=>{if(e.detail.owner!==owner)return;if(data){data={...data,execution:{...data.execution,...(window.BF.getCurrent()||{})}};updateModel();}clearTimeout(refreshTimer);refreshTimer=setTimeout(()=>void load(true),1200);});
  window.addEventListener('bf-runtime-connection',e=>{if(e.detail.owner!==owner)return;connected=e.detail.connected;updateModel();if(connected)void load(true)});
  new MutationObserver(layout).observe(document.body,{attributes:true,attributeFilter:['class','data-workspace','data-studio-mode']});
  window.addEventListener('resize',layout);window.addEventListener('keydown',e=>{if(e.key==='Escape'&&q('#xp-inspection')){q('#xp-inspection').remove();historyView=false;selectedNode=null;lastRender='';render()}});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&isTask())void load(true)});
  setInterval(()=>{if(document.hidden||pane.hidden)return;void load();freshness();},20000);
  window.ExecutionProgress={refresh:()=>load(true),getState:()=>({owner,model,historyView}),followCurrent};layout();void load();
})();
