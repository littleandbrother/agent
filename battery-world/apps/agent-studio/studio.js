/* Studio and Lab share selected task identity and the existing evidence APIs. */
(() => {
  const q=s=>document.querySelector(s),{api,esc}=window.BF,M=window.StudioModel;
  const positions=new Map();let lastMode='',lastStudio='task',lastLab='console',cachedCard=null,cardOwner=null,cardLoading=false,cardFetchedAt=0,headerSnapshot=null;
  const domains={mechanical:'机械与结构',circuit:'电路与 PCB',firmware:'固件与模型',system:'系统与报告'};
  const icon=n=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="${{file:'M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6',export:'M12 16V3m-4 4 4-4 4 4 M5 13v7h14v-7',back:'m10 5-7 7 7 7 M3 12h18',spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z'}[n]||'M4 5h16v14H4z M9 5v14'}"/></svg>`;
  function beforeMode(next){if(lastMode&&lastMode!==next){const root=q(lastMode==='task'?'#conversation':lastMode==='product'?'#pr-workspace':lastMode==='console'?'#developer-view':'#panorama-view');positions.set(lastMode+':'+window.BF.getSelection(),root?.scrollTop||0)}lastMode=next;}
  function sync(mode){
    const lab=['console','panorama'].includes(mode);if(lab)lastLab=mode;else lastStudio=mode;
    q('#studio-space').setAttribute('aria-pressed',String(!lab));q('#lab-space').setAttribute('aria-pressed',String(lab));q('#workspace-name').textContent=lab?'Lab':'Studio';
    q('#studio-results').hidden=mode!=='task';q('#studio-export').hidden=mode!=='product';
    q('#studio-results').disabled=!window.BF.getSelection();q('#studio-export').disabled=!window.ProductResults?.getState().snapshot?.files.length;
    document.title=lab?'BF Agent Lab':'BF Agent Studio';
    const root=q(mode==='task'?'#conversation':mode==='product'?'#pr-workspace':mode==='console'?'#developer-view':'#panorama-view');
    if(root)requestAnimationFrame(()=>{root.scrollTop=positions.get(mode+':'+window.BF.getSelection())||0;if(!matchMedia('(prefers-reduced-motion: reduce)').matches)root.animate([{opacity:.3,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:220,easing:'cubic-bezier(.2,.8,.2,1)'})});
  }
  q('#studio-space').onclick=()=>window.BFDeveloper.setMode(lastStudio);
  q('#lab-space').onclick=()=>window.BFDeveloper.setMode(lastLab);
  q('#studio-results').onclick=()=>window.ProductWorkspace.showSession();
  q('#studio-export').innerHTML=icon('export')+'导出';
  q('#studio-export').onclick=()=>{const s=window.ProductResults.getState();if(s.snapshot)delivery(s.owner,s.scopeChoice,s.snapshot.revision)};
  window.addEventListener('bf-mode',e=>sync(e.detail.mode));
  window.addEventListener('bf-selection',()=>{q('#studio-results').disabled=!window.BF.getSelection();q('#studio-export').disabled=!window.BF.getSelection();chatCard(q('#conversation'))});
  function productHeader(snapshot,selection){
    headerSnapshot=snapshot;q('#studio-export').disabled=!snapshot?.files.length;if(!snapshot)return;
    const host=q('.pd-heading');if(!host)return;
    host.querySelector('h2').textContent=snapshot.title||'产品成果';
    q('#pd-title').textContent='设计、验证与交付';q('#pd-check-summary').textContent='';
    q('#pd-source').setAttribute('title','独立参考工程与当前任务分别保留');
    let select=q('#studio-scope');if(!select){select=document.createElement('select');select.id='studio-scope';select.setAttribute('aria-label','成果版本与范围');q('.pd-heading-actions').prepend(select);select.onchange=()=>window.ProductResults.scope(select.value)}
    select.innerHTML=M.choices(snapshot).map(c=>`<option value="${esc(c.id)}">${esc(c.label)}</option>`).join('');select.value=selection||'session';select.hidden=!!snapshot.reference;
    q('#pd-version').hidden=!!selection&&selection!=='session';
    q('#pd-source').hidden=!snapshot.reference;
    if(!q('#studio-reference')){const b=document.createElement('button');b.id='studio-reference';b.className='quiet';b.textContent='参考工程';b.onclick=()=>snapshot.reference?window.ProductWorkspace.showSession():window.ProductWorkspace.showReference();q('.pd-heading-actions').append(b)}
    q('#studio-reference').onclick=()=>headerSnapshot?.reference?window.ProductWorkspace.showSession():window.ProductWorkspace.showReference();q('#studio-reference').textContent=snapshot.reference?'返回当前任务':'参考工程';
  }
  function visual(x,owner){
    if(!x)return '<div class="studio-no-visual">模型、图纸或计算结果生成后，会出现在这里。</div>';
    if(x.v.kind==='image')return `<button class="studio-hero-image" data-studio-preview="${esc(x.f.id)}"><img src="${esc(x.f.url)}" alt="${esc(M.fileLabel(x.f))}"><span>查看大图 ↗</span></button>`;
    if(x.v.kind==='video')return `<video controls playsinline preload="metadata" src="${esc(x.f.url)}"></video>`;
    return `<iframe title="产品三维模型" src="/model-viewer.html?session=${encodeURIComponent(owner)}&result_file=${encodeURIComponent(x.f.id)}${x.v.kind==='mesh'?'&mesh=1':''}"></iframe>`;
  }
  function overview(snapshot){
    const hero=M.hero(snapshot),findings=M.findings(snapshot),rows=snapshot.results,available=snapshot.files.filter(f=>f.integrity).length;
    const primary=findings.find(f=>rows.find(r=>r.id===f.id)?.kind==='closed-simulation')||findings.find(f=>rows.find(r=>r.id===f.id)?.kind==='spice')||findings[0];
    const title=primary?(snapshot.selectedScope?'该版本仍有未通过项':'所选记录含未通过项'):snapshot.verdict?.passed?'当前目标阶段已完成':rows.length?'已有工程成果，等待逐项验收':'从一个想法开始';
    const outcome=primary?.text||snapshot.verdict?.scope||'请查看各部分的计算条件与验证范围。文件生成不代表产品验收通过。';
    const media=hero?rows.filter(r=>r.domain===hero.r.domain).flatMap(r=>(r.presentations||[]).filter(v=>['image','video','model','mesh'].includes(v.kind)).map(v=>({r,v,f:r.files.find(f=>f.id===v.file_id)}))).filter(x=>x.f?.integrity):[];
    const distinct=media.filter(x=>x.r.id===hero?.r.id).slice(0,6);
    const proposal=rows.find(r=>r.kind==='proposal');const measured=(rows.find(r=>r.id===primary?.id)?.metrics||[]).filter(m=>typeof m.value==='number').slice(0,3);const metricName=n=>({peak_tip_mm:'梁端峰值 (mm)',peak_piezo_V:'压电峰值 (V)',peak_storage_V:'储能峰值 (V)',VIN_peak_V:'输入电压峰值 (V)',minimum_sampled_clearance_mm:'采样间距最小值 (mm)',normal_resistor_energy_uJ:'正常动作电阻能量 (μJ)'})[n]||n;
    return `<div class="studio-overview"><div class="studio-object-meta"><span>${snapshot.selectedScope?'已归档工程 · '+esc(rows[0]?.case_version||''):'所选会话成果'}</span><span>${available} 件可读取${snapshot.files.length!==available?' · '+(snapshot.files.length-available)+' 件待恢复':''}</span></div><div class="studio-hero" id="studio-hero">${visual(hero,snapshot.owner)}</div>${distinct.length?`<nav class="studio-media-tabs" aria-label="产品展示">${distinct.map(x=>`<button data-studio-hero="${esc(x.f.id)}" aria-pressed="${x.f.id===hero?.f.id}">${esc(M.fileLabel(x.f))}</button>`).join('')}</nav>`:''}${hero?`<p class="studio-caption">${esc(hero.r.scope||'此图来自已归档工程。')}</p>`:''}<button class="studio-conclusion ${primary?'has-gap':''}" data-studio-verify><span class="studio-conclusion-symbol">${primary?'!':'○'}</span><span><small>当前结论</small><strong>${title}</strong><span>${esc(outcome)}</span></span><span>›</span></button>${primary?'<p class="studio-fidelity">仿真与数字工程记录 · 尚无实物验收依据</p>':''}${measured.length?`<dl class="studio-key-metrics">${measured.map(m=>`<div><dt>${esc(metricName(m.name))}</dt><dd>${Number(m.value).toLocaleString('zh-CN',{maximumSignificantDigits:4})}</dd></div>`).join('')}</dl>`:''}<section class="studio-section"><div class="studio-section-title"><h3>设计成果</h3><span>按专业查看原生工程与依据</span></div><div class="studio-domain-grid">${Object.entries(domains).map(([d,name])=>{const items=rows.filter(r=>r.domain===d),count=snapshot.files.filter(f=>f.domain===d&&f.integrity).length;return `<div><h4>${name}<small>${count} 件</small></h4>${items.length?items.map(r=>`<button data-studio-result="${esc(r.id)}">${icon('file')}<span>${esc(r.label||r.kind)}<small>${esc(M.verdict(r))}</small></span><span>›</span></button>`).join(''):'<p class="pr-note">尚未形成这部分成果</p>'}</div>`}).join('')}</div></section>${proposal?`<details class="studio-assumptions"><summary>需求与设计假设</summary><div>${window.BF.markdown?window.BF.markdown(JSON.stringify(proposal.inputs)):esc(JSON.stringify(proposal.inputs))}</div></details>`:''}<div class="studio-bottom-actions"><button data-studio-discuss>继续讨论设计</button><button id="pr-export" class="primary" ${!snapshot.files.length?'disabled':''}>${icon('export')}导出此范围的成果</button></div></div>`;
  }
  function verification(snapshot){return `<div class="studio-verification"><h3>验证记录</h3><p class="pr-note">执行状态、计算结论与实物验证分别展示。点击记录查看条件、曲线和原始文件。</p>${snapshot.results.map(r=>`<button class="studio-check-row" data-studio-result="${esc(r.id)}"><span class="studio-check-state ${r.design_status==='FAIL'?'failed':''}">${esc(M.verdict(r))}</span><span><b>${esc(r.label||r.kind)}</b><small>${esc(r.scope||r.applicability.reason)}</small></span><span>›</span></button>`).join('')||'<p>尚无验证记录</p>'}${snapshot.blockers?.length?`<details class="studio-assumptions"><summary>尚未满足的产品条件 · ${snapshot.blockers.length}</summary>${snapshot.blockers.map(b=>`<p>${esc(b.label)} · ${esc(({missing_files:'缺少文件',stale:'需重新验证',failed:'检查未通过',validator_unavailable:'尚无独立验证'})[b.state]||b.state)}</p>`).join('')}</details>`:''}</div>`;}
  function bindPreview(root,snapshot){root.querySelectorAll('[data-studio-preview]').forEach(b=>b.onclick=()=>window.ProductResults.preview(snapshot.files.find(f=>f.id===b.dataset.studioPreview)));root.querySelectorAll('[data-studio-hero]').forEach(b=>b.onclick=()=>{const f=snapshot.files.find(f=>f.id===b.dataset.studioHero),r=snapshot.results.find(r=>r.files.some(x=>x.id===f.id)),v=r.presentations.find(v=>v.file_id===f.id);q('#studio-hero').innerHTML=visual({r,v,f},snapshot.owner);root.querySelectorAll('[data-studio-hero]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));q('.studio-caption').textContent=r.scope||'';root.querySelectorAll('[data-studio-preview]').forEach(x=>x.onclick=()=>window.ProductResults.preview(snapshot.files.find(f=>f.id===x.dataset.studioPreview)))})}
  function discuss(snapshot,result){
    const title=result?.label||snapshot.title,caseVersion=result?.case_version||(snapshot.selectedScope?snapshot.results[0]?.case_version:null),ref=caseVersion?'工程 '+caseVersion:snapshot.revision?'装配 v'+snapshot.revision:'当前记录';
    window.BFDeveloper.setMode('task');const input=q('#message-input'),prefix=`关于「${title}」· ${ref}：\n`;
    if(!input.value.startsWith(prefix)){input.value=prefix+input.value;input.dispatchEvent(new Event('input',{bubbles:true}))}input.focus();input.setSelectionRange(input.value.length,input.value.length);
  }
  async function chatCard(pane){
    const owner=window.BF.getSelection();if(!owner||!pane)return;
    if(owner!==cardOwner){cachedCard=null;cardOwner=owner}
    const append=()=>{if(!cachedCard?.files.length||q('#studio-result-card'))return;const atBottom=pane.scrollHeight-pane.scrollTop-pane.clientHeight<100;const b=document.createElement('button');b.id='studio-result-card';b.className='studio-result-card';const versions=M.choices(cachedCard),target=versions.find(v=>v.id===sessionStorage.getItem('bf-product-scope-'+owner))||versions[0],scope=M.scoped(cachedCard,target.id);b.innerHTML=icon('file')+`<span><b>查看产品成果</b><small>${esc(target.label)} · ${scope.files.filter(f=>f.integrity).length} 件可读取</small></span><span>›</span>`;b.onclick=()=>window.ProductWorkspace.showSession();pane.append(b);if(atBottom)pane.scrollTop=pane.scrollHeight;};
    if(cachedCard){append();if(Date.now()-cardFetchedAt<15000)return}if(cardLoading)return;cardLoading=true;
    try{const next=await api('/api/results?'+new URLSearchParams({session:owner}));if(owner===window.BF.getSelection()){const changed=cachedCard?.snapshot_sha256!==next.snapshot_sha256;cachedCard=next;cardFetchedAt=Date.now();if(changed)q('#studio-result-card')?.remove();append()}}catch{}finally{cardLoading=false}
  }
  async function delivery(owner,selection='session',revision=null){
    const dialog=document.createElement('dialog');dialog.className='studio-delivery-sheet';dialog.setAttribute('aria-label','导出产品成果');dialog.innerHTML='<p>正在核对所选版本…</p>';document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove(),{once:true});dialog.showModal();
    try{
      let snap=await api('/api/studio/delivery?'+new URLSearchParams({session:owner,selection:selection||'session',revision:revision||''}));
      if(!dialog.isConnected)return;
      const draw=()=>{const missing=snap.files.filter(f=>!f.integrity),hasReport=snap.files.some(f=>f.integrity&&/\.pdf$/i.test(f.name)&&/report|报告/i.test((f.source_path||'')+f.name));dialog.innerHTML=`<form method="dialog"><button class="quiet studio-sheet-close" aria-label="关闭导出">×</button></form><small>版本交付</small><h2>导出产品成果</h2><p>${esc(snap.title)}</p><label class="studio-export-version">成果范围<select id="delivery-scope">${snap.options.map(o=>`<option value="${esc(o.id)}" ${o.id===snap.selection?'selected':''}>${esc(o.label)}</option>`).join('')}</select></label><fieldset><legend>你希望怎样使用这些成果？</legend>${[['summary','结果概要','适合评审：结论、范围与文件清单'],['report','技术报告','已归档 PDF 与同版工程资料，保留原有相对路径'],['engineering','完整工程包','可编辑工程、计算记录与离线文件入口']].map(([id,title,desc])=>`<label class="studio-export-option"><input type="radio" name="purpose" value="${id}" ${id==='engineering'?'checked':''} ${id==='report'&&!hasReport?'disabled':''}><span><b>${title}</b><small>${id==='report'&&!hasReport?'此范围尚无可用报告 PDF':desc}</small></span></label>`).join('')}</fieldset><p class="studio-package-health">${missing.length?'有 '+missing.length+' 件文件暂不可读取':snap.files.length+' 件文件可读取 · 已核对文件摘要'}</p>${missing.length?`<label class="studio-partial"><input type="checkbox" id="delivery-partial">仅导出可读取文件，保留缺项清单</label><details><summary>查看缺项</summary>${missing.map(f=>'<p>'+esc(f.name)+'</p>').join('')}</details>`:''}<p class="pr-note">工程资料可交付评审，并不代表产品已通过验证。导出固定此快照，不包含后续更新。</p><p id="delivery-notice" role="status"></p><button id="delivery-download" class="primary">${icon('export')}导出工程包</button>`;
        dialog.querySelector('#delivery-scope').onchange=async e=>{const value=e.target.value;e.target.disabled=true;try{snap=await api('/api/studio/delivery?'+new URLSearchParams({session:owner,selection:value,revision:revision||''}));if(dialog.isConnected)draw()}catch(error){dialog.querySelector('#delivery-notice').textContent=error.message;e.target.disabled=false}};
        dialog.querySelector('#delivery-download').onclick=async e=>{const button=e.currentTarget,notice=dialog.querySelector('#delivery-notice'),purpose=dialog.querySelector('[name=purpose]:checked').value;button.disabled=true;notice.textContent='正在核对文件并生成交付包…';try{const r=await api('/api/studio/package',{session_id:owner,selection:snap.selection,revision:snap.revision,snapshot_sha256:snap.snapshot_sha256,purpose,allow_partial:!!dialog.querySelector('#delivery-partial')?.checked});if(!dialog.isConnected)return;notice.innerHTML=`交付包已生成 · ${r.files} 件文件${r.omitted?' · '+r.omitted+' 件缺项已列明':''}。<a href="${esc(r.url)}" download="BF-成果-${esc(snap.selection.replaceAll(':','-'))}.zip">再次下载</a>`;const a=document.createElement('a');a.href=r.url;a.download='BF-成果-'+snap.selection.replaceAll(':','-')+'.zip';a.click();button.textContent='重新导出'}catch(error){notice.textContent=({STUDIO_SNAPSHOT_CHANGED:'所选记录已更新。请关闭面板后重新打开，核对新版本再导出。',STUDIO_FILES_MISSING:'部分文件不可读取。请修复文件，或勾选仅导出可读取文件。',STUDIO_REPORT_NOT_AVAILABLE:'此范围尚无已归档技术报告。'})[error.message]||error.message}finally{button.disabled=false}};
      };draw();
    }catch(error){dialog.innerHTML=`<form method="dialog"><button>关闭</button></form><p>无法读取交付清单：${esc(error.message)}</p>`}
  }
  // A single pointer highlight follows the glass surfaces; engineering content stays still.
  let glassFrame=0,glassSurface=null,glassPoint=null;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  document.addEventListener('pointermove',event=>{
    if(reduced.matches||event.pointerType==='touch')return;
    const surface=event.target.closest('.workspace-switch,.topbar,.studio-delivery-sheet,#composer');
    if(glassSurface!==surface){glassSurface?.removeAttribute('data-glass-active');glassSurface=surface}
    if(!surface)return;glassPoint={x:event.clientX,y:event.clientY};
    if(!glassFrame)glassFrame=requestAnimationFrame(()=>{glassFrame=0;if(!glassSurface?.isConnected)return;const box=glassSurface.getBoundingClientRect();glassSurface.style.setProperty('--glass-x',`${glassPoint.x-box.left}px`);glassSurface.style.setProperty('--glass-y',`${glassPoint.y-box.top}px`);glassSurface.dataset.glassActive='true'});
  },{passive:true});
  document.addEventListener('pointerleave',()=>{glassSurface?.removeAttribute('data-glass-active');glassSurface=null},{passive:true});
  window.StudioExperience={beforeMode,productHeader,overview,verification,bindPreview,delivery,discuss,chatCard};
})();
