/* Product navigation only. Replay reads recorded events; it never reruns tools. */
(() => {
  const {api,esc}=window.BF, G=window.ProductGraph, D=window.ProductDeliverables, V=window.ProductDeliveryView, q=s=>document.querySelector(s);
  let owner=null, revision='', selected='integrated', tab='deliverables', bottom='timeline', search='', category='', data=null, current=null;
  let scope=sessionStorage.getItem('bf-product-source')==='reference'?'reference':'session', referenceData=null, inventory=null, inventoryError='', assetFilter='all', circuitPart='';
  let zoom=.8, fitMode=true, play=null, eventIndex=-1, refreshBusy=false, generation=0;
  const categories=[['requirements','需求','需求与验收'],['energy','能源','采能、储能与电源'],['sensing','感知','输入与产品服务'],['ml','TinyML','模型与 NAS'],['mechanical','机械','结构与装配'],['circuit','电路','原理图与 PCB'],['firmware','固件','MCU 与通信'],['verification','验证','计算与实测'],['release','交付','证据与产物']];
  const active=()=>document.body.dataset.studioMode==='product';
  const date=t=>new Date(t*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
  const pre=v=>`<pre>${esc(typeof v==='string'?v:JSON.stringify(v,null,2))}</pre>`;
  const icon=(id)=>{
    const paths={requirements:'M7 3h7l4 4v14H7z M14 3v5h4 M10 12h5 M10 16h5',energy:'M13 2 5 14h6l-1 8 9-13h-6z',sensing:'M2 12h4l3-8 5 16 3-8h5',ml:'M8 5h8v14H8z M5 8H2 M5 12H2 M5 16H2 M19 8h3 M19 12h3 M19 16h3 M11 9h2v6h-2z',mechanical:'m12 2 9 5v10l-9 5-9-5V7z M3 7l9 5 9-5 M12 12v10',circuit:'M6 6h12v12H6z M9 2v4 M15 2v4 M9 18v4 M15 18v4 M2 9h4 M2 15h4 M18 9h4 M18 15h4',firmware:'m7 6-5 6 5 6 M17 6l5 6-5 6 M14 3l-4 18',verification:'M8 12l3 3 5-6 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',release:'M4 5h16v15H4z M4 10h16 M9 5v5 M15 5v5',integration:'m12 3 10 5-10 5L2 8z M2 12l10 5 10-5 M2 16l10 5 10-5'};
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[id]||paths.integration}"/></svg>`;
  };
  const badge=n=>`<span class="pd-state ${n.status}"><i></i>${esc(G.labels[n.status])}</span>`;
  const currentEvent=()=>data?.events[eventIndex];
  function shell(){
    q('#product-view').innerHTML=`<header class="pd-heading"><div><h2>产品</h2><p id="pd-title">从需求到设计、验证与交付</p><span id="pd-check-summary"></span></div><div class="pd-heading-actions"><label class="sr-only" for="pd-source">产品来源</label><select id="pd-source" aria-label="产品来源"><option value="session">当前任务</option><option value="reference">拨动式采能 · 参考工程</option></select><label class="sr-only" for="pd-version">产品装配版本</label><select id="pd-version"></select><button id="pd-model" class="quiet">三维模型 ↗</button><button id="pd-trace" class="quiet">Trace ↗</button></div></header>
      <div id="pd-empty" class="pd-empty" hidden></div><div class="pd-workspace">
      <aside class="pd-library" aria-label="产品设计目录"><div class="pd-library-title">设计目录<button id="pd-clear" class="quiet" title="显示全部节点" aria-label="显示全部节点">↺</button></div><label class="pd-search">${icon('sensing')}<input id="pd-search" type="search" placeholder="查找节点…" aria-label="查找产品节点"></label><nav>${categories.map(([id,title,desc])=>`<button data-pd-category="${id}" aria-pressed="false" title="${desc}">${icon(id)}<span><b>${title}</b><small>${desc}</small></span></button>`).join('')}</nav><div class="pd-library-foot"><span>当前会话</span><p id="pd-scope"></p><button id="pd-task" class="quiet">回到任务 ↗</button></div></aside>
      <div class="pd-center"><div class="pd-canvas-heading"><div><strong>产品设计图</strong><span>需求 → 设计 → 验证 → 交付</span></div><div class="pd-zoom-controls"><button id="pd-minus" aria-label="缩小产品图">−</button><output id="pd-zoom"></output><button id="pd-plus" aria-label="放大产品图">＋</button><button id="pd-fit">全图</button><button id="pd-inspect-toggle" aria-expanded="true" aria-controls="product-inspector" title="展开或收起节点详情">详情</button></div></div>
      <div id="pd-stage" tabindex="0" aria-label="产品设计画布，拖动空白平移，Ctrl 或 Command 加滚轮缩放"><div id="pd-size"><div id="pd-board"><svg id="pd-edges" viewBox="0 0 ${G.width} ${G.height}" aria-hidden="true"></svg><div id="pd-nodes"></div></div></div></div>
      <div class="pd-canvas-foot"><button id="pd-mini" aria-label="查看产品图全貌" title="查看全图"></button><div class="pd-legend"><span><i class="recorded"></i>设计记录</span><span><i class="passed"></i>检查通过</span><span><i class="failed"></i>未通过</span><span><i class="pending"></i>待验证</span></div><span id="pd-filter-count"></span></div></div>
      <aside id="product-inspector" aria-label="产品节点详情"></aside></div>
      <section class="pd-history" aria-label="产品过程记录"><div class="pd-history-bar"><nav aria-label="产品过程视图"><button data-pd-bottom="timeline" aria-pressed="true">时间线</button><button data-pd-bottom="events" aria-pressed="false">事件</button><button data-pd-bottom="artifacts" aria-pressed="false">产物</button><button id="pd-logs">日志 ↗</button></nav><span id="pd-replay-state"></span><button id="pd-live" class="quiet">当前记录</button><button id="pd-play" title="回放已有记录，不重新运行模型或工具">▷ 回放记录</button></div><div id="pd-history-content"></div></section>`;
    q('#pd-source').onchange=e=>setSource(e.target.value);
    q('#pd-version').onchange=e=>{stop();revision=e.target.value;eventIndex=-1;renderData()};
    q('#pd-model').onclick=model; q('#pd-trace').onclick=q('#pd-logs').onclick=()=>window.BFDeveloper.openTrace();
    q('#pd-task').onclick=()=>window.BFDeveloper.setMode('task');
    q('#pd-search').oninput=e=>{search=e.target.value;draw()};
    q('#pd-clear').onclick=()=>{category='';search='';q('#pd-search').value='';draw()};
    q('#pd-mini').onclick=fit;
    q('#pd-minus').onclick=()=>scale(zoom-.1);q('#pd-plus').onclick=()=>scale(zoom+.1);q('#pd-fit').onclick=fit;
    q('#pd-inspect-toggle').onclick=()=>{const hide=q('.pd-workspace').classList.toggle('pd-inspector-hidden');q('#pd-inspect-toggle').setAttribute('aria-expanded',!hide);window.BFPanelSizing?.refresh();if(fitMode)requestAnimationFrame(fit)};
    q('#pd-live').onclick=()=>{stop();revision='';eventIndex=-1;if(scope==='reference')loadReference();else{renderData();refresh()}};
    q('#pd-play').onclick=()=>{if(play){stop();return}if(!data.events.length)return;if(eventIndex>=data.events.length-1)eventIndex=-1;step();play=setInterval(step,1300);q('#pd-play').textContent='Ⅱ 暂停回放'};
    q('#pd-stage').addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey){e.preventDefault();scale(zoom+(e.deltaY<0?.07:-.07))}},{passive:false});
    q('#pd-stage').onpointerdown=e=>{if(e.button!==0||e.target.closest('button'))return;const stage=q('#pd-stage'),x=e.clientX,y=e.clientY,left=stage.scrollLeft,top=stage.scrollTop;stage.setPointerCapture(e.pointerId);stage.onpointermove=m=>{stage.scrollLeft=left+x-m.clientX;stage.scrollTop=top+y-m.clientY};stage.onpointerup=stage.onpointercancel=()=>{stage.onpointermove=null;if(stage.hasPointerCapture(e.pointerId))stage.releasePointerCapture(e.pointerId)}};
    q('#product-view').onclick=e=>{
      const c=e.target.closest('[data-pd-category]');if(c){category=category===c.dataset.pdCategory?'':c.dataset.pdCategory;selected=({requirements:'mission',verification:'energy-check',release:'release'})[c.dataset.pdCategory]||c.dataset.pdCategory;showDeliverables()}
      const n=e.target.closest('[data-pd-node]');if(n){selected=n.dataset.pdNode;showDeliverables()}
      const t=e.target.closest('[data-pd-tab]');if(t){tab=t.dataset.pdTab;inspect()}
      const b=e.target.closest('[data-pd-bottom]');if(b){bottom=b.dataset.pdBottom;history()}
      const ev=e.target.closest('[data-pd-event]');if(ev){stop();seek(Number(ev.dataset.pdEvent))}
      const rev=e.target.closest('[data-pd-revision]');if(rev){stop();revision=rev.dataset.pdRevision;eventIndex=-1;renderData()}
      if(e.target.closest('[data-pd-console]'))window.BFDeveloper.openModule(scope==='reference'?'referenceCase':'delivery');
      const part=e.target.closest('[data-pd-part]');if(part){circuitPart=part.dataset.pdPart;assetFilter='all';inspect()}
      const filter=e.target.closest('[data-pd-filter]');if(filter){assetFilter=filter.dataset.pdFilter;inspect()}
      const file=e.target.closest('[data-pd-file]');if(file){const node=data.nodes.find(n=>n.id===selected);const f=node?.assets.concat(...(node.sections||[]).map(p=>p.references))[Number(file.dataset.pdFile)];if(f)V.preview(f,data.sourceLabel+' · '+data.snapshot)}
    };
    new ResizeObserver(()=>{if(active()&&fitMode)requestAnimationFrame(fit)}).observe(q('#pd-stage'));
  }
  function showDeliverables(){
    stop();tab='deliverables';assetFilter='all';circuitPart='';eventIndex=-1;
    q('.pd-workspace').classList.remove('pd-inspector-hidden');q('#pd-inspect-toggle').setAttribute('aria-expanded','true');
    draw();inspect();history();q('#product-inspector').scrollTop=0;
    if(matchMedia('(max-width:900px)').matches)q('#product-inspector').scrollIntoView({block:'nearest'});
  }
  function renderData(){
    if(scope==='reference')data=D.reference(referenceData||{title:'拨动式采能参考工程',delivery:{},artifacts:[]});
    else {let graph=G.build(current,revision);if(revision&&!graph.record){revision='';graph=G.build(current)}data=D.session(graph,inventory,current)}
    q('#pd-source').value=scope;
    q('#pd-title').textContent=data.title;q('#pd-title').title=data.title;
    q('#pd-check-summary').textContent=scope==='session'&&inventory?.verdict&&(!revision||data.isCurrent)?`${inventory.verdict.stages.find(s=>s.id===inventory.verdict.target_stage)?.label||inventory.verdict.target_stage} · ${inventory.verdict.passed?'已完成':'待完成'} · ${inventory.verdict.missing.length} 项缺口`:data.checks.length?data.checks.filter(c=>c.state==='passed').length+' / '+data.checks.length+' 项检查通过':'';
    q('#pd-scope').textContent=scope==='reference'?'参考辅助设计 · 独立工程快照':current?.title||'尚未选择任务';
    q('#pd-version').innerHTML='<option value="">当前装配'+(data.versions.length?' · v'+data.versions.at(-1).revision:' · 未建立')+'</option>'+data.versions.map(r=>`<option value="${r.revision}">装配 v${r.revision}${r.source_valid===false?' · 已失效':''}</option>`).join('');q('#pd-version').value=revision;
    q('#pd-version').disabled=scope==='reference';if(scope==='reference')q('#pd-version').innerHTML=`<option>${esc(data.snapshot)}</option>`;
    q('#pd-empty').hidden=!data.empty;q('#pd-empty').textContent=owner?'这条任务尚未形成产品方案。设计记录生成后会出现在这里。':'选择左侧任务查看产品，或回到任务描述一个想法。';
    q('#pd-model').disabled=scope==='reference'?!referenceModel():!modelJob();q('#pd-trace').disabled=scope==='reference'||!owner;q('#pd-logs').disabled=scope==='reference'||!owner;
    if(scope==='reference'&&!referenceData){q('#pd-empty').hidden=false;q('#pd-empty').textContent='正在读取参考工程交付物…'}
    if(inventoryError&&scope==='session'){q('#pd-empty').hidden=false;q('#pd-empty').textContent='交付绑定暂时无法读取：'+inventoryError}
    draw();inspect();history();window.BFPanelSizing?.refresh();
  }
  function draw(){
    if(!data)return;
    const needle=search.trim().toLowerCase();
    let count=0;
    q('#pd-nodes').innerHTML=data.nodes.map(n=>{
      const match=(!category||n.group===category)&&(!needle||[n.title,n.summary,...n.facts].join(' ').toLowerCase().includes(needle));if(match)count++;
      return `<button class="pd-node ${n.group} ${selected===n.id?'selected':''} ${match?'':'dimmed'} ${currentEvent()?.node===n.id?'replayed':''}" data-pd-node="${n.id}" aria-pressed="${selected===n.id}" title="${esc(n.title+'：'+n.summary)}"><span class="pd-node-icon">${icon(n.group)}</span><span class="pd-node-body"><b>${esc(n.title)}</b><span class="pd-node-summary">${esc(n.summary)}</span><span class="pd-node-meta">${badge(n)}<small class="pd-node-count">${n.assets?.length||0} 件</small><small>${data.reference?esc(data.snapshot):n.group==='requirements'?esc(n.version):data.record?'v'+data.record.revision:'—'}</small></span></span></button>`;
    }).join('');
    q('#pd-nodes').querySelectorAll('[data-pd-node]').forEach(el=>{const n=data.nodes.find(n=>n.id===el.dataset.pdNode);el.style.left=n.x+'px';el.style.top=n.y+'px'});
    q('#pd-filter-count').textContent=(category||needle)?count+' 个匹配节点':'关系为设计流程';
    q('.pd-library nav').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.pdCategory===category));
    const by=new Map(data.nodes.map(n=>[n.id,n]));
    const paths=data.edges.map(e=>{
      const a=by.get(e.source),b=by.get(e.target),x1=a.x+188,y1=a.y+40,x2=b.x,y2=b.y+40;
      const d=e.source==='evidence'?`M${a.x+94} ${a.y+80}V${b.y-14}Q${a.x+94} ${b.y-7} ${b.x+94} ${b.y}`:`M${x1} ${y1}H${x1+9}Q${x1+16} ${y1} ${x1+16} ${y1+(y2>y1?7:y2<y1?-7:0)}V${y2+(y2>y1?-7:y2<y1?7:0)}Q${x1+16} ${y2} ${x1+23} ${y2}H${x2}`;
      return `<path d="${d}" class="${(e.source===selected||e.target===selected)?'selected':''}" marker-end="url(#pd-arrow)"/>`;
    }).join('');
    q('#pd-edges').innerHTML='<defs><marker id="pd-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto"><path d="M1 1 7 4 1 7" fill="none" stroke="currentColor"/></marker></defs>'+paths;
    q('#pd-mini').innerHTML=`<svg viewBox="0 0 ${G.width} ${G.height}" aria-hidden="true">${data.nodes.map(n=>`<rect x="${n.x}" y="${n.y}" width="188" height="80" rx="10" class="${n.id===selected?'chosen':''}"/>`).join('')}</svg>`;
  }
  const detail=(label,body)=>`<section class="pd-detail-section"><h4>${label}</h4>${body}</section>`;
  function links(files){return files.length?files.map(f=>`<a class="pd-file" href="${esc(f.url)}" download="${esc(f.name)}" title="SHA-256 ${esc(f.sha256||f.digest||'未记录')}"><span>${esc(f.name)}</span><small>${f.stale?'历史 · ':''}${f.integrity===false?'校验失败':'↗'}</small></a>`).join(''):'<p class="pd-muted">暂无绑定产物</p>'}
  function inspect(){
    const n=data.nodes.find(n=>n.id===selected)||data.nodes[0];selected=n.id;
    const incoming=data.edges.filter(e=>e.target===n.id),outgoing=data.edges.filter(e=>e.source===n.id),event=currentEvent();
    let body='';
    if(tab==='deliverables'){
      const card=scope==='session'&&(!revision||data.isCurrent)?inventory?.research_cards?.[n.id]:null;
      if(card)body+=detail('当前判断',`<p><b>${esc(card.question)}</b></p><p>${esc(card.conclusion)}</p><p class="pd-muted">装配 v${esc(card.revision||'—')} · ${esc(card.claim_boundary)}</p><details><summary>假设与待验证问题 · ${card.open_questions.length}</summary>${card.assumptions.map(x=>`<p>${esc(typeof x==='string'?x:JSON.stringify(x))}</p>`).join('')}${card.open_questions.map(x=>`<p>${esc(x.label)} · ${esc(x.validation)}</p>`).join('')}${card.checks.map(c=>`<p>${esc(c.name)} · ${c.passed?'通过':'未通过或失效'} · ${esc(c.job_id)}</p>`).join('')}</details>`);
      body+=V.panel(n,data,assetFilter,circuitPart);
    }
    else if(tab==='overview'){
      if(event)body+=detail('回放到此记录',`<p>${esc(date(event.time)+' · '+event.title)}</p><p class="pd-muted">${esc(event.detail)}</p><p class="pd-muted">回放只定位历史记录；图中检查仍属于所选装配版本。</p>${event.revision?`<button data-pd-revision="${event.revision}">查看装配 v${event.revision}</button>`:''}${event.verification?pre({checks:event.verification.checks,integrity:event.verification.integrity,scope:event.verification.scope}):event.job?pre({job:event.job.id,status:event.job.status,scope:event.job.scope,error:event.job.error,checks:event.job.result?.checks}):''}`);
      body+=detail('设计记录',n.facts.length?n.facts.map(f=>f.startsWith('{')?`<details><summary>参数与结果</summary>${pre(f)}</details>`:`<p>${esc(f)}</p>`).join(''):'<p class="pd-muted">尚未记录该部分设计。</p>');
      if(n.checks.length)body+=detail('验证依据',n.checks.map(c=>`<div class="pd-check"><span>${esc(c.label)}</span>${badge({status:c.state})}</div>${c.scope?`<p class="pd-muted">${esc(c.scope)}</p>`:''}`).join(''));
      if(n.jobs.length)body+=detail('绑定工程记录',n.jobs.map(j=>`<details><summary>${esc(G.engines[j.engine]||j.engine)} · ${esc(j.status)}</summary><p class="pd-muted">${esc(j.scope||'执行状态不等于产品验证')}</p>${pre({id:j.id,status:j.status,assembly_revision:j.assembly?.revision,error:j.error,scope:j.result?.scope,hardware_verified:j.result?.hardware_verified})}</details>`).join(''));
      if(n.id==='integrated')body+=detail('相邻版本变化',data.previous?`<p>v${data.previous.revision} → v${data.record.revision}</p>${data.changes.map(k=>`<div class="pd-diff"><span>${esc(({physical_hash:'物理设计',geometry_hash:'几何结构',energy_hash:'能源参数',definition_hash:'完整定义'})[k]||k)}</span><b>已变化</b></div>`).join('')||'<p class="pd-muted">已记录哈希没有变化</p>'}`:'<p class="pd-muted">尚无前一装配版本可比较。</p>');
      body+=detail('交付物',`<button class="pd-related" data-pd-tab="deliverables">查看该部分 ${n.assets?.length||0} 件交付物 →</button>`);
      body+=detail('记录来源',`<p class="pd-muted">${esc(n.version)}${!data.isCurrent&&data.record?' · 历史版本不套用当前检查':''}</p><p class="pd-muted">${esc(data.record?.hashes?.physical_hash?.slice(0,16)||'尚无物理设计哈希')}</p><button class="quiet" data-pd-console>在控制台查看验收记录 ↗</button>`);
    } else {
      const rows=tab==='inputs'?incoming:outgoing;
      body=detail(tab==='inputs'?'上游设计':'后续检查与产物',rows.length?rows.map(e=>{const v=data.nodes.find(x=>x.id===(tab==='inputs'?e.source:e.target));return `<button class="pd-related" data-pd-node="${v.id}">${icon(v.group)}<span>${esc(v.title)}</span>→</button>`}).join(''):'<p class="pd-muted">这是流程的起点或终点。</p>');
      body+='<p class="pd-muted">连线表示页面组织的设计流程。是否存在有效证据，需查看具体版本与检查记录。</p>';
    }
    q('#product-inspector').innerHTML=`<div class="pd-inspector-label">节点详情</div><header class="pd-inspector-heading">${icon(n.group)}<div><h3>${esc(n.title)}</h3>${badge(n)}</div></header><nav class="pd-detail-tabs" aria-label="节点详情视图">${[['deliverables','交付物'],['overview','概览'],['inputs','输入 · '+incoming.length],['outputs','输出 · '+outgoing.length]].map(([id,label])=>`<button data-pd-tab="${id}" aria-pressed="${tab===id}">${label}</button>`).join('')}</nav>${body}`;
  }
  function history(){
    const events=data.events; q('.pd-history nav').querySelectorAll('[data-pd-bottom]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.pdBottom===bottom));
    q('#pd-replay-state').textContent=currentEvent()?'记录 '+(eventIndex+1)+' / '+events.length:events.length+' 条真实记录';
    q('#pd-play').disabled=!events.length;if(data.reference&&bottom==='timeline'){q('#pd-history-content').innerHTML='<p class="pd-no-records">参考工程快照 · '+esc(data.snapshot)+' · 点击产品节点查看交付物；仿真校准与验收记录保留在控制台。</p>';return}q('#pd-play').textContent=play?'Ⅱ 暂停回放':'▷ 回放记录';
    if(bottom==='timeline')q('#pd-history-content').innerHTML=events.length?`<div class="pd-timeline">${events.map((e,i)=>`<button data-pd-event="${i}" class="${i===eventIndex?'selected':''}" title="${esc(e.detail)}"><i class="${e.state}"></i><time>${date(e.time)}</time><b>${esc(e.title)}</b></button>`).join('')}</div>`:'<p class="pd-no-records">方案、装配和工程记录会按实际时间排列在这里。</p>';
    if(bottom==='events')q('#pd-history-content').innerHTML=events.length?`<div class="pd-event-list">${events.map((e,i)=>`<button data-pd-event="${i}" class="${i===eventIndex?'selected':''}"><time>${date(e.time)}</time><b>${esc(e.title)}</b><span>${esc(e.detail)}</span><small>${G.labels[e.state]}</small></button>`).join('')}</div>`:'<p class="pd-no-records">暂无事件。</p>';
    if(bottom==='artifacts')q('#pd-history-content').innerHTML=`<div class="pd-all-files">${links([...data.files,...data.artifacts])}</div>`;
  }
  function stop(){clearInterval(play);play=null;if(q('#pd-play'))q('#pd-play').textContent='▷ 回放记录'}
  function seek(i){eventIndex=Math.max(0,Math.min(data.events.length-1,i));selected=currentEvent()?.node||selected;tab='overview';draw();inspect();history();q(`#pd-history-content [data-pd-event="${eventIndex}"]`)?.scrollIntoView({block:'nearest',inline:'nearest'})}
  function step(){if(!active()||eventIndex>=data.events.length-1){stop();return}seek(eventIndex+1)}
  function scale(z,preserve=false){fitMode=preserve;zoom=Math.max(.35,Math.min(1.8,z));q('#pd-board').style.transform=`scale(${zoom})`;q('#pd-size').style.width=G.width*zoom+'px';q('#pd-size').style.height=G.height*zoom+'px';q('#pd-zoom').textContent=Math.round(zoom*100)+'%'}
  function fit(){if(!active()||!q('#pd-stage'))return;const s=q('#pd-stage');scale(Math.min((s.clientWidth-28)/G.width,(s.clientHeight-28)/G.height,1),true);s.scrollTo(0,0)}
  function modelJob(){return data?.bound.find(j=>j.engine==='product-model'&&j.status==='SUCCEEDED'&&j.result?.artifacts?.some(a=>a.name==='model.glb'))}
  function referenceModel(){return data?.reference?data.files.find(f=>f.name==='model.glb'&&f.path.includes('/cad-')):null}
  function model(){if(scope==='reference'){const f=referenceModel();if(f)V.preview(f,data.sourceLabel+' · '+data.snapshot);return}const job=modelJob();if(!job)return;const d=document.createElement('dialog');d.className='model-dialog';d.innerHTML=`<form method="dialog"><button aria-label="关闭产品模型">×</button></form><iframe title="当前装配版本的产品模型" src="/model-viewer.html?job=${encodeURIComponent(job.id)}"></iframe>`;document.body.append(d);d.addEventListener('close',()=>d.remove(),{once:true});d.showModal()}
  async function loadReference(){
    const gen=++generation;stop();V.close();renderData();
    try {const next=await api('/api/reference-case');if(gen!==generation||scope!=='reference')return;if(!next.available)throw Error(next.status||'参考工程尚未建立');referenceData=next;renderData()}
    catch(e){if(gen===generation){q('#pd-empty').hidden=false;q('#pd-empty').textContent='参考工程暂时无法读取：'+e.message}}
  }
  function setSource(next){
    generation++;stop();V.close();scope=next;sessionStorage.setItem('bf-product-source',scope);revision='';selected='integrated';tab='deliverables';assetFilter='all';search='';category='';eventIndex=-1;q('#pd-search').value='';
    renderData();if(scope==='reference')loadReference();else refresh();requestAnimationFrame(fit);
  }
  async function refresh(){
    if(!active()||document.hidden||refreshBusy||scope==='reference'||!owner?.startsWith('pi-chat-'))return;
    refreshBusy=true;const id=owner,gen=generation;
    try{
      const [next,snapshot]=await Promise.all([api('/api/conversations/'+encodeURIComponent(id)),api('/api/deliverables?session='+encodeURIComponent(id)).catch(e=>{if(e.message==='PRODUCT_SESSION_REQUIRED')return {owner:id,revision:null,tasks:[]};throw e})]);
      if(gen===generation&&id===owner&&active()&&scope==='session'){
        const changed=JSON.stringify(current?.product)!==JSON.stringify(next.product)||JSON.stringify(inventory)!==JSON.stringify(snapshot)||inventoryError;
        current=next;inventory=snapshot;inventoryError='';if(changed){stop();eventIndex=-1;renderData()}
      }
    }catch(e){if(gen===generation){inventoryError=e.message;renderData()}}
    finally{refreshBusy=false}
  }
  function open(){
    const id=window.BF.getSelection();if(id!==owner){generation++;stop();V.close();if(owner!==null){scope='session';sessionStorage.setItem('bf-product-source',scope)}owner=id;inventory=null;inventoryError='';revision='';selected='integrated';tab='deliverables';assetFilter='all';circuitPart='';eventIndex=-1;search='';category=''}
    current=window.BF.getCurrent();if(!q('#pd-stage'))shell();q('#pd-search').value=search;renderData();requestAnimationFrame(fit);if(scope==='reference'){if(!referenceData)loadReference()}else refresh();
  }
  function showReference(){window.BFDeveloper.setMode('product');setSource('reference')}
  function showSession(){window.BFDeveloper.setMode('product');setSource('session')}
  window.ProductWorkspace={open,showReference,showSession};
  window.addEventListener('bf-selection',()=>{if(active())open()});
  window.addEventListener('bf-mode',e=>{if(e.detail.mode!=='product'){stop();V.close()}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();else refresh()});
  q('#refresh').addEventListener('click',()=>{if(active())refresh()});
  setInterval(refresh,8000);
})();
