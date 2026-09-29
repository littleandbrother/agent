/* Product-side browsing. Previews are read-only and bounded; native downloads stay explicit. */
(() => {
  const {esc}=window.BF,D=window.ProductDeliverables;
  const bytes=n=>!Number.isFinite(n)?'':n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';
  const short=f=>f.path||f.source||f.name;
  const intermediate=f=>['o','d','su','log','class','mphstatus','mphbin'].includes(D.ext(f));
  const previewable=f=>(['image','code','document'].includes(D.kind(f))||['csv','jsonl','map'].includes(D.ext(f)))&&D.ext(f)!=='html'&&D.ext(f)!=='pdf'&&(!f.bytes||f.bytes<=524288||D.kind(f)==='image');
  function cards(files,all){return files.map(f=>`<article class="pd-asset"><button class="pd-asset-open" data-pd-file="${all.indexOf(f)}" title="${esc(short(f))}"><span class="pd-asset-kind">${esc(D.kinds[D.kind(f)])}${f.referenceOnly?' · 参考资料':''}</span>${D.kind(f)==='image'?`<img loading="lazy" src="${esc(f.url)}" alt="${esc(f.name)}">`:""}<b>${esc(f.name)}</b>${f.path?`<span class="pd-asset-path">${esc(f.path.split('/').slice(-3,-1).join('/'))}</span>`:''}<small>${esc(bytes(f.bytes))}${f.stale?' · 历史 / 需重验':''}${f.integrity===false?' · 校验失败':''}</small></button></article>`).join('')}
  function panel(n,data,filter='all',part=''){
    const parts=n.sections||[],selection=parts.find(p=>p.id===part),main=n;
    if(selection)n={...n,assets:selection.assets,deliveryTasks:selection.tasks,simulations:selection.id==='simulation'?n.simulations:[]};
    const all=n.assets||[],previewFiles=main.assets.concat(...parts.map(p=>p.references)),files=filter==='all'?all:all.filter(f=>D.kind(f)===filter),tasks=n.deliveryTasks||[],simulations=n.simulations||[];
    return `${parts.length?`<nav class="pd-circuit-parts" aria-label="电路分项"><button data-pd-part="" aria-pressed="${!selection}">全部电路</button>${parts.map(s=>`<button data-pd-part="${s.id}" aria-pressed="${selection?.id===s.id}"><b>${esc(s.title)}</b><small>${s.assets.length?s.assets.length+' 件文件':'本版待补齐'}${s.references.length?' · '+s.references.length+' 件参考':''}</small></button>`).join('')}</nav>`:''}<section class="pd-delivery-summary"><b>${all.filter(f=>!f.referenceOnly).length} 件交付物${all.some(f=>f.referenceOnly)?' · '+all.filter(f=>f.referenceOnly).length+' 件参考资料':''}</b><span>${esc(data.sourceLabel)} · ${esc(data.snapshot)}</span><p>${all.length?'可查看、预览和下载该部分已记录的文件。':'该版本还没有绑定该部分交付物。'}${data.reference?' 文件存在不代表已完成产品验收。':''}</p>${selection?`<p>${esc(selection.hint)}</p>`:''}${data.integrity===false?'<p class="bad-text">快照有文件校验失败，不能作为通过依据。</p>':''}</section>
    ${(selection?.references?.length)?`<section class="pd-reference-boards"><h4>原作者参考板</h4><p>ViPSN 的并联 SP-SSHI 与比较器 EMU 原始 Altium 文件；不是本版 LTC3588-1 方案。尚未导入立创 EDA、完成本地规则检查或生成本版制造包。</p><div class="pd-asset-list">${cards(selection.references,main.assets.concat(...parts.map(p=>p.references)))}</div></section>`:''}
    <nav class="pd-asset-filters" aria-label="交付物类型">${[['all','全部'],...Object.entries(D.kinds)].filter(([id])=>id==='all'||all.some(f=>D.kind(f)===id)).map(([id,label])=>`<button data-pd-filter="${id}" aria-pressed="${filter===id}">${label}<small>${id==='all'?all.length:all.filter(f=>D.kind(f)===id).length}</small></button>`).join('')}</nav>
    ${simulations.length&&['all','simulation','image'].includes(filter)?`<section class="pd-simulation-list">${simulations.map(s=>`<article class="pd-simulation"><h4>${esc(s.title)}</h4>${s.figureFile?`<button class="pd-figure-open" data-pd-file="${previewFiles.findIndex(f=>f.url===s.figureFile.url)}" aria-label="查看${esc(s.title)}图"><img loading="lazy" src="${esc(s.figureFile.url)}" alt="${esc(s.title)}结果曲线"></button>`:''}<p>${esc(s.result)}</p><small>${esc(s.scope)}</small></article>`).join('')}</section>`:''}
    <div class="pd-asset-list">${files.length?cards(files.filter(f=>!intermediate(f)),previewFiles):'<p class="pd-muted">暂无此类文件。</p>'}</div>${files.some(intermediate)?`<details class="pd-delivery-checklist"><summary>运行日志与构建中间文件 · ${files.filter(intermediate).length}</summary><div class="pd-asset-list">${cards(files.filter(intermediate),previewFiles)}</div></details>`:''}
    ${tasks.length?`<details class="pd-delivery-checklist"><summary>交付要求与验收 · ${tasks.length} 项</summary>${tasks.map(t=>`<article><b>${esc(t.label)}</b><p>${esc(D.deliveryNames[t.delivery_status]||t.delivery_status||'未登记')} · ${esc(D.validationNames[t.validation_status]||'未验收')}</p><small>${esc(t.acceptance||'')}</small>${t.missing_files?.length?`<p class="pd-muted">待补：${t.missing_files.map(f=>esc(f.role)).join('、')}</p>`:''}</article>`).join('')}</details>`:''}
    ${!data.reference&&data.inventoryPending?'<p class="pd-muted">正在读取交付绑定…</p>':''}
    ${!data.reference&&n.id==='integrated'&&data.unboundFiles?.length?'<p class="pd-muted">未绑定分项的已发布文件保留在「集成设计」，不会猜测其所属模块。</p>':''}`;
  }
  function renderMarkdown(content){
    // Escape source first. This reader deliberately does not execute raw HTML or load remote images.
    const inline=text=>esc(text).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    const lines=content.split('\n'),out=[];let code=null,list=false;
    const endList=()=>{if(list){out.push('</ul>');list=false}};
    const cells=line=>line.trim().replace(/^\||\|$/g,'').split('|').map(x=>x.trim());
    for(let i=0;i<lines.length;i++){
      const line=lines[i];
      if(line.startsWith('```')){endList();if(code!==null){out.push('<pre><code>'+esc(code.join('\n'))+'</code></pre>');code=null}else code=[];continue}
      if(code!==null){code.push(line);continue}
      if(line.includes('|')&&i+1<lines.length&&cells(lines[i+1]).every(x=>/^:?-{3,}:?$/.test(x))){
        endList();const header=cells(line);out.push('<div class="pd-markdown-table"><table><thead><tr>'+header.map(x=>'<th>'+inline(x)+'</th>').join('')+'</tr></thead><tbody>');i++;
        while(i+1<lines.length&&lines[i+1].includes('|')&&lines[i+1].trim()){const row=cells(lines[++i]);out.push('<tr>'+header.map((_,j)=>'<td>'+inline(row[j]||'')+'</td>').join('')+'</tr>')}
        out.push('</tbody></table></div>');continue;
      }
      const bullet=line.match(/^\s*[-*+] (.*)$/);if(bullet){if(!list){out.push('<ul>');list=true}out.push('<li>'+inline(bullet[1])+'</li>');continue}
      endList();const heading=line.match(/^(#{1,6}) (.*)$/);
      if(heading)out.push('<h'+heading[1].length+'>'+inline(heading[2])+'</h'+heading[1].length+'>');
      else if(line.trim())out.push('<p>'+inline(line)+'</p>');
    }
    endList();if(code!==null)out.push('<pre><code>'+esc(code.join('\n'))+'</code></pre>');return out.join('');
  }
  let dialog=null;
  function close(){dialog?.close()}
  async function preview(file,context){
    close();const d=document.createElement('dialog'),controller=new AbortController();dialog=d;
    d.className='pd-preview-dialog';d.setAttribute('aria-labelledby','pd-preview-title');
    d.innerHTML=`<header><div><h3 id="pd-preview-title">${esc(file.name)}</h3><p>${esc(context)}${file.referenceOnly?' · 参考资料，非本版交付':''} · ${esc(bytes(file.bytes))}</p></div><button data-preview-close aria-label="关闭交付物预览">×</button></header><div class="pd-preview-body" role="region" aria-label="文件预览"></div><footer><details><summary>文件来源与哈希</summary><p>${esc(short(file))}</p><code>${esc(file.sha256||file.digest||'未记录')}</code></details><a href="${esc(file.url)}" download="${esc(file.name)}">下载文件 ↗</a></footer>`;
    document.body.append(d);d.querySelector('[data-preview-close]').onclick=()=>d.close();
    d.addEventListener('close',()=>{controller.abort();d.remove();if(dialog===d)dialog=null},{once:true});
    d.showModal();const body=d.querySelector('.pd-preview-body');
    if(file.integrity===false){body.textContent='该文件完整性核对失败，请到控制台查看原因。';return}
    if(D.ext(file)==='glb'&&(file.path||file.job_id||(file.session&&file.id))){
      const frame=document.createElement('iframe');frame.title='三维模型：'+file.name;frame.src=file.session&&file.id?'/model-viewer.html?'+new URLSearchParams({session:file.session,result_file:file.id}):file.path?'/model-viewer.html?case=pluck-v1&artifact='+encodeURIComponent(file.path):'/model-viewer.html?job='+encodeURIComponent(file.job_id);frame.className='pd-model-preview';body.classList.add('pd-preview-3d');body.append(frame);return;
    }
    if(D.ext(file)==='mp4'){const video=document.createElement('video');video.src=file.url;video.controls=true;video.playsInline=true;video.style.width='100%';body.append(video);return;}
    if(D.ext(file)==='pdf'){
      const frame=document.createElement('iframe');frame.title='PDF：'+file.name;frame.src=file.url;frame.className='pd-model-preview';frame.setAttribute('sandbox','allow-same-origin');body.classList.add('pd-preview-3d');body.append(frame);return;
    }
    if(D.kind(file)==='image'){
      const img=document.createElement('img');img.alt=file.name;img.src=file.url;img.onerror=()=>{body.textContent='图片暂时无法读取，文件可能已变更；请刷新后核对。'};body.append(img);return;
    }
    if(!previewable(file)){body.innerHTML=`<p>此文件请下载后使用${D.ext(file)==='mph'?' COMSOL':D.ext(file)==='blend'?' Blender':['schdoc','pcbdoc'].includes(D.ext(file))?' Altium 或支持导入的 EDA 工具':D.ext(file)==='pdf'?' PDF 阅读器':'对应工程工具'}打开。</p><p class="pd-muted">${D.kind(file)==='native'||D.kind(file)==='simulation'?'保留原生可编辑文件。':'完整文件可通过下方链接下载。'}</p>`;return}
    body.textContent='正在读取文件…';
    try{
      const token=sessionStorage.getItem('bf-access');
      const response=await fetch(file.url,{credentials:'same-origin',signal:controller.signal,headers:token?{Authorization:'Bearer '+token}:{}});
      if(!response.ok)throw Error('文件读取失败（'+response.status+'）');
      const reader=response.body.getReader(),chunks=[];let length=0,truncated=false;
      while(true){const {done,value}=await reader.read();if(done)break;const room=524288-length;chunks.push(value.slice(0,room));length+=Math.min(room,value.length);if(value.length>room||length>=524288){truncated=true;await reader.cancel();break}}
      if(!d.isConnected)return;
      const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length}
      const content=new TextDecoder().decode(bytes);
      if(D.ext(file)==='md'){
        const article=document.createElement('article');article.className='pd-markdown-reader';article.innerHTML=renderMarkdown(content);body.replaceChildren(article);
      }else{const pre=document.createElement('pre');pre.textContent=content;body.replaceChildren(pre)}
      if(truncated){const p=document.createElement('p');p.textContent='预览已截取前 512 KB，下载可查看完整文件。';body.prepend(p)}
    }catch(e){if(d.isConnected)body.textContent='预览未能加载：'+e.message}
  }
  window.ProductDeliveryView={panel,preview,close,bytes,renderMarkdown};
})();
