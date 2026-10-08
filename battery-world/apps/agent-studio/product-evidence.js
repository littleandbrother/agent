/* Six questions, one owner-scoped evidence baseline. No scientific scoring. */
(function(root){
  function groups(snapshot){
    const rows=(snapshot?.results||[]).filter(r=>r.evidence_story);
    if(!rows.length)return [];
    const identities=new Set(rows.map(r=>[r.case_id,r.case_version,r.evidence_story.baseline_source_identity].join(':')));
    if(identities.size!==1)return [];
    const ordered=rows.sort((a,b)=>a.evidence_story.order-b.evidence_story.order);
    if(ordered.length!==6||ordered.some((r,i)=>r.evidence_story.order!==i+1))return [];
    return ordered.map(r=>({r,story:r.evidence_story,file:r.files.find(f=>f.id===r.evidence_story.file_id)}));
  }
  function preferred(snapshot){
    const rows=(snapshot?.results||[]).filter(r=>r.evidence_story).sort((a,b)=>b.created-a.created);
    for(const r of rows){const key='case:'+r.case_id+':'+r.case_version;const found=groups({results:rows.filter(x=>x.case_id===r.case_id&&x.case_version===r.case_version)});if(found.length===6)return key;}
    return '';
  }
  function panelIntegrity(snapshot,p){
    const files=new Map((snapshot.files||[]).map(f=>[f.id,f]));
    const ids=[p.figure_id,p.pdf_id,p.svg_id,p.provenance_id,...(p.source_files||[])];
    return Boolean(p.source_files?.length)&&ids.every(id=>files.get(id)?.integrity===true);
  }
  const api={groups,preferred,panelIntegrity};
  if(typeof module!=='undefined'){module.exports=api;return;}
  let selected=new Map(),selectedPanel=new Map();
  const esc=s=>root.BF.esc(String(s??''));
  const key=s=>s.owner+':'+s.selectedScope;
  function panelView(snapshot,story){
    const panels=story.panels||[];if(!panels.length)return '';
    const chosen=selectedPanel.get(key(snapshot)+':'+story.order),p=panels.find(p=>p.id===chosen);
    const file=id=>(snapshot.files||[]).find(f=>f.id===id);
    const badges={available:'已有证据',missing:'待补证据',not_applicable:'不适用'};
    return `<section class="evidence-subpanels" aria-label="逐子图证据"><header><h5>逐张读图</h5><p>${panels.filter(p=>p.status==='available').length} 张已有 · ${panels.filter(p=>p.status==='missing').length} 张待补。可供图数不等于复现成功率。</p></header><div class="evidence-panel-grid">${panels.map(p=>`<button data-evidence-panel="${esc(p.id)}" aria-pressed="${chosen===p.id}" aria-label="子图 ${esc(p.id)} ${esc(p.title)} ${badges[p.status]}"><strong>${esc(p.id)}</strong><span>${esc(p.title)}</span><small>${badges[p.status]}</small></button>`).join('')}</div>${p?`<article class="evidence-subpanel-detail" aria-label="子图 ${esc(p.id)}"><header><h5>${esc(p.id)} · ${esc(p.title)}</h5><button data-evidence-panel-close aria-label="返回组图">关闭 ×</button></header><p>${esc(p.question)}</p>${panelIntegrity(snapshot,p)?`<button class="evidence-figure" data-evidence-open="${esc(p.figure_id)}"><img src="${esc(file(p.figure_id).url)}" alt="${esc(p.caption)}"></button>`:'<p role="alert">子图归档未通过完整性核对。</p>'}<p>${esc(p.caption)}</p>${p.reason?`<p class="evidence-gap">${esc(p.reason)}</p>`:''}<p>证据性质：${esc(p.evidence_kind)} · 输入身份 <code>${esc(p.source_identity)}</code></p><div class="evidence-panel-downloads">${['pdf','svg','provenance'].map(k=>{const f=file(p[k+'_id']);return f?.integrity?`<a href="${esc(f.url)}" download="${esc(f.name)}">${k==='provenance'?'来源记录':k.toUpperCase()}</a>`:''}).join('')}</div><details><summary>这张图的来源 · ${(p.source_files||[]).length} 项</summary>${(p.source_files||[]).map(id=>{const f=file(id);return f?.integrity?`<a href="${esc(f.url)}" download="${esc(f.name)}">${esc(f.name)}</a>`:'<p>来源文件异常或不可用</p>'}).join('')}</details></article>`:''}</section>`;
  }
  function engineeringPreviews(snapshot){
    const fs=(snapshot.files||[]).filter(f=>f.integrity);
    const model=fs.find(f=>f.sections?.includes('mechanical')&&f.name.endsWith('.glb'));
    const inside=fs.find(f=>f.sections?.includes('mechanical')&&/mechanical-internal\.svg$/.test(f.name));
    const board=fs.find(f=>f.sections?.includes('pcb')&&/pcb-combined\.svg$/.test(f.name));
    const entries=[model&&inside?{f:model,image:inside,title:'机械结构',text:'原尺寸装配 · 内部 · 爆炸分解'}:null,board?{f:board,image:board,title:'PCB 布线',text:board.reference_only?'D3 历史参考 · 待适配 D5 电路':'原始铜箔与工程文件'}:null].filter(Boolean);
    return entries.length?`<div class="evidence-engineering-previews" aria-label="结构与 PCB"><div class="evidence-preview-intro"><h4>打开工程实体</h4><p>图组之外，直接查看结构与电路板。</p></div>${entries.map(x=>`<button data-evidence-open="${esc(x.f.id)}"><img src="${esc(x.image.url)}" alt="${esc(x.title)}"><span><b>${esc(x.title)}</b><small>${esc(x.text)}</small></span><i aria-hidden="true">↗</i></button>`).join('')}</div>`:'';
  }
  function render(snapshot,{compact=false}={}){
    const rows=groups(snapshot);if(!rows.length)return '';
    const current=selected.get(key(snapshot))||1,x=rows[current-1],g=x.story,f=x.file;
    const valid=rows.every(x=>x.file?.integrity&&(x.story.panels||[]).every(p=>panelIntegrity(snapshot,p)));
    return `<section class="evidence-dossier ${compact?'is-compact':''}" aria-label="六组产品证据"><header class="evidence-heading"><div><small>PRODUCT EVIDENCE / ${esc(g.baseline_version)}</small><h3>六组图，读懂当前设计。</h3><p>${esc(g.baseline_conclusion||'按六个问题，查看已有设计、计算结果和交付边界。')}</p></div><span class="evidence-status">${valid?'证据已归档 · 产品待验证':'证据文件异常 · 请核对来源'}</span></header>${engineeringPreviews(snapshot)}<nav class="evidence-nav" aria-label="六组证据导航">${rows.map(({story:s})=>`<button data-evidence-group="${s.order}" aria-label="0${s.order} ${esc(s.title)}" title="${esc(s.title)}" aria-pressed="${current===s.order}" aria-controls="evidence-panel-${compact?'side':'main'}"><span>0${s.order}</span>${esc(s.navigation_title||['产品','机制','比较','电路','程序','验证'][s.order-1])}</button>`).join('')}</nav><article class="evidence-panel" id="evidence-panel-${compact?'side':'main'}" aria-label="图组 ${g.order} ${esc(g.title)}"><div class="evidence-title"><div><small>图组 ${g.order} / 6</small><h4>${esc(g.title)}</h4><p>${esc(g.question)}</p></div>${f?.integrity?`<button data-evidence-open="${esc(f.id)}">放大图组 ↗</button>`:''}</div>${f?.integrity?`<button class="evidence-figure" data-evidence-open="${esc(f.id)}"><img src="${esc(f.url)}" alt="图组 ${g.order}：${esc(g.question)}"><span>查看完整图组</span></button>`:'<p role="alert">图组文件未通过完整性核对。请恢复原始归档；下方仅保留历史文字结论。</p>'}${panelView(snapshot,g)}<div class="evidence-reading"><div><small>这组图说明了什么</small><p class="evidence-conclusion">${esc(g.conclusion)}</p></div><div><small>读图时需要知道</small><ul>${g.limitations.map(s=>`<li>${esc(s)}</li>`).join('')}</ul></div></div><details class="evidence-sources"><summary>查看原始数据与版本依据</summary><p>档案 ${esc(g.baseline_id)} / ${esc(g.baseline_version)} · 图组输入身份 <code>${esc(g.source_identity)}</code></p><p>${esc(g.component_summary||'各工程修订分别绑定；归档不等于整机验收。')}</p><div>${x.r.files.filter(z=>z.integrity).map(z=>`<a href="${esc(z.url)}" download="${esc(z.name)}">下载 ${esc(z.name.split('/').pop())}</a>`).join('')}</div><details><summary>对应工程、数据与源码 · ${g.dependencies.length} 项</summary>${g.dependencies.map(p=>{const z=snapshot.files.find(f=>(f.source_path===p||f.source_path==='inputs/'+p));return z?.integrity?`<a href="${esc(z.url)}" download="${esc(z.name)}">${esc(p)}</a>`:`<p>${esc(p)} · 未在当前范围中提供</p>`}).join('')}</details></details><footer class="evidence-footer"><button data-evidence-group="${Math.max(1,current-1)}" ${current===1?'disabled':''}>← 上一组</button><span>${current} / 6</span><button data-evidence-group="${Math.min(6,current+1)}" ${current===6?'disabled':''}>下一组 →</button></footer></article><section class="evidence-release"><h4>整套成果使用同一份档案</h4><p>六组图、PDF 报告和工程文件均绑定此来源快照。缺项与未通过项随交付一起保留。</p><div>${snapshot.files.filter(f=>f.integrity&&/(door-evidence-report|figure-atlas)\.(pdf|html)$/.test(f.name)||f.integrity&&/scientific-figures\.zip$/.test(f.name)).map(f=>`<a href="${esc(f.url)}" download="${esc(f.name)}">下载 ${f.name.endsWith('.pdf')?(/figure-atlas/.test(f.name)?'六组图 PDF':'完整 PDF 报告'):f.name.endsWith('.zip')?'全部子图与数据包':'离线图组（图像见数据包）'}</a>`).join('')}<button data-evidence-delivery>核对并导出工程资料 →</button></div></section></section>`;
  }
  function bind(host,snapshot,options={}){
    const pane=host.querySelector('.evidence-dossier');if(!pane)return;
    pane.addEventListener('click',e=>{
      const p=e.target.closest('[data-evidence-panel]'),close=e.target.closest('[data-evidence-panel-close]');
      if(p||close){e.preventDefault();const current=selected.get(key(snapshot))||1;const id=p?.dataset.evidencePanel;selectedPanel.set(key(snapshot)+':'+current,id||'');const holder=document.createElement('div');holder.innerHTML=render(snapshot,options);pane.replaceWith(holder.firstElementChild);bind(host,snapshot,options);host.querySelector(id?'.evidence-subpanel-detail':'[data-evidence-panel]')?.scrollIntoView({block:id?'start':'nearest',behavior:'instant'});host.querySelector(id?'[data-evidence-panel-close]':'[data-evidence-panel]')?.focus({preventScroll:true});return;}
      const g=e.target.closest('[data-evidence-group]');
      if(g){e.preventDefault();const focusIndex=Number(g.dataset.evidenceGroup);selected.set(key(snapshot),focusIndex);const holder=document.createElement('div');holder.innerHTML=render(snapshot,options);pane.replaceWith(holder.firstElementChild);bind(host,snapshot,options);const button=host.querySelector(`.evidence-nav [data-evidence-group="${focusIndex}"]`);button?.focus({preventScroll:true});host.querySelector('.evidence-title')?.scrollIntoView({block:'nearest',behavior:'instant'});return;}
      const open=e.target.closest('[data-evidence-open]');if(open){const f=snapshot.files.find(f=>f.id===open.dataset.evidenceOpen);if(f?.integrity)root.ProductDeliveryView.preview({...f,session:snapshot.owner},f.applicability?.reason||'图组来源已绑定；仿真记录不等于实物验收。');return;}
      if(e.target.closest('[data-evidence-delivery]'))root.StudioExperience.delivery(snapshot.owner,snapshot.selectedScope);
    });
  }
  root.ProductEvidence={...api,render,bind};
})(typeof window==='undefined'?this:window);
