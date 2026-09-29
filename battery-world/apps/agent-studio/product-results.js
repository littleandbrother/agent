/* Results-first product view. Every file and applicability label comes from the backend. */
(() => {
  const {api,esc}=window.BF, q=s=>document.querySelector(s), V=window.ProductDeliveryView;
  const domains={mechanical:'机械与结构',circuit:'电路与 PCB',firmware:'固件与模型',system:'系统与交付'};
  const kinds={'cadquery':'原生 CAD','product-model':'产品装配','spice':'电路仿真','beam-event':'机电耦合仿真','event-transient':'瞬态仿真','firmware-stm32l031':'MCU 固件','mcu-firmware':'MCU 固件','tinyml-nas':'模型与 NAS',blender:'三维展示',comsol:'结构仿真',jlceda:'原理图与 PCB',benchmark:'基准计算与波形',proposal:'需求与产品方案'};
  const states={case:'案例版本',current:'本版生成',reused:'可复用',stale:'需重验',unbound:'未绑定装配',future:'后续版本',reference:'参考工程',proposal:'方案记录',input:'输入资料'};
  const metricLabels={bounds_mm:'原生尺寸 (mm)',volume_mm3:'实体体积 (mm³)',solid_count:'有效实体数',flash_bytes:'Flash 占用 (bytes)',ram_static_bytes:'静态 RAM (bytes)',reserved_stack_bytes:'保留栈 (bytes)',points:'求解数据点',variables:'求解变量数',target:'编译目标',memory_fit:'内存容量检查',native_valid:'原生几何有效',readback_passed:'独立读回通过',cold_start_ideal_lower_bound_hours:'理想冷启动下界 (h)',dark_interval_demand_j:'暗期能量需求 (J)',demand_j_day:'每日需求 (J)',effective_capacitance_f:'有效电容 (F)',event_j:'单次事件能量 (J)',harvest_j_day:'每日采集能量 (J)',margin_j_day:'日能量余量 (J)',displacement_mm:'位移 (mm)',max_von_mises_mpa:'最大等效应力 (MPa)'};
  const metricLabel=name=>({'summary.maximum_storage_v':'最高储能电压 (V)','summary.minimum_input_v':'最低输入电压 (V)','energy_ledger.boot':'启动能耗 (J)','energy_ledger.harvest':'采集能量 (J)','energy_ledger.dump':'钳位耗散 (J)','energy_ledger.esr_loss':'内阻损耗 (J)','energy_ledger.idle':'待机能耗 (J)','energy_ledger.infer':'计算能耗 (J)','energy_ledger.leakage':'漏电损耗 (J)'})[name]||metricLabels[name.split('.').at(-1)]||name;
  const statuses={NEEDS_ACTION:'等待外部处理',SUCCEEDED:'执行完成',FAILED:'执行失败',UNKNOWN:'状态待核对',RUNNING:'正在运行',QUEUED:'等待执行',PUBLISHED:'已发布'};
  const gaps={missing_files:'缺少工程文件',stale:'相关输入已变化',failed:'文件或检查失败',validator_unavailable:'待独立验收 / 验证器未接入'};
  let traceReturn=null;
  let context=null,snapshot=null,pending=null,view='results',domain='',selected='',comparison='',generation=0,loading=new Set(),drawGeneration=0,visualChoice='';
  const currentFile=f=>['current','reused'].includes(f.applicability?.state)&&f.integrity&&['SUCCEEDED','PUBLISHED'].includes(f.status);
  const format=v=>typeof v==='number'?v.toLocaleString('zh-CN',{maximumSignificantDigits:6}):typeof v==='object'?JSON.stringify(v):String(v);
  const time=t=>new Date(t*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
  const note=t=>`<p class="pr-note">${esc(t)}</p>`;
  function mount(){
    if(q('#pr-nav'))return;
    q('.pd-heading').insertAdjacentHTML('afterend','<div id="pr-nav"></div><section id="pr-workspace" aria-label="产品成果工作区"></section>');
    q('#pr-nav').onclick=e=>{const b=e.target.closest('[data-pr-view]');if(b){view=b.dataset.prView;paint()}if(e.target.closest('#pr-update')){snapshot=pending;pending=null;window.ProductWorkspace?.applyResults(snapshot);paint()}};
    q('#pr-workspace').onclick=e=>{
      const d=e.target.closest('[data-pr-domain]');if(d){domain=d.dataset.prDomain;selected='';comparison='';paint();q('#pr-workspace').scrollTop=0}
      const r=e.target.closest('[data-pr-result]');if(r){selected=r.dataset.prResult;visualChoice='';paint()}
      const visual=e.target.closest('[data-pr-visual]');if(visual){visualChoice=visual.dataset.prVisual;loadVisual(selectedResult(),++drawGeneration)}
      const f=e.target.closest('[data-pr-file]');if(f){const file=snapshot.files.find(x=>x.id===f.dataset.prFile);if(file)preview(file)}
      const s=e.target.closest('[data-pr-source]');if(s)source(s.dataset.prSource);
      const evidence=e.target.closest('[data-pr-evidence]');if(evidence){const r=snapshot.results.find(x=>x.id===evidence.dataset.prEvidence);if(r){const d=document.createElement('dialog');d.className='artifact-dialog';const records=r.files.filter(f=>/\.(json|log|csv|pwl)$/.test(f.name));d.innerHTML=`<form method="dialog"><button aria-label="关闭计算记录">×</button></form><h3>${esc(r.label)}</h3>${note('操作者辅助工程记录；这里保留实际求解回执和数据，不生成不存在的 Agent Trace。')}${filesHTML(records)}<pre>${esc(JSON.stringify({checks:r.checks,scope:r.scope,design:r.design_inputs},null,2))}</pre>`;document.body.append(d);d.addEventListener('close',()=>d.remove(),{once:true});d.showModal();d.addEventListener('click',event=>{const b=event.target.closest('[data-pr-file]');if(b){const f=r.files.find(x=>x.id===b.dataset.prFile);if(f)preview(f)}})}return}
      const t=e.target.closest('[data-pr-trace]');if(t){traceReturn={view,domain,selected,scroll:q('#pr-workspace').scrollTop};window.BFDeveloper.openTrace({job:t.dataset.prTrace})}
      if(e.target.closest('#pr-export'))exportPackage();
    };
  }
  function referenceSnapshot(source){
    const d=window.ProductDeliverables.reference(source),files=window.ProductDeliverables.unique([...d.files,...d.nodes.flatMap(n=>n.assets)]).map((f,i)=>({...f,id:'reference/'+i,domain:'system',result_id:'reference',role:window.ProductDeliverables.kind(f),applicability:{state:'reference',reason:'参考工程快照，未绑定当前任务'},created_revision:null}));
    const assign=new Map();for(const n of d.nodes){const id={mechanical:'mechanical',circuit:'circuit',firmware:'firmware'}[n.id];if(id)for(const f of n.assets)assign.set(f.url,id)}
    files.forEach(f=>f.domain=assign.get(f.url)||'system');
    return {reference:true,referenceNodes:d.nodes,title:d.title,files,results:[],blockers:[],revision:null,snapshot_sha256:JSON.stringify(source.delivery||{}),verdict:null};
  }
  async function update(ctx){
    mount();const key=JSON.stringify([ctx.owner,ctx.scope,ctx.revision]);
    if(context?.key!==key){generation++;context={...ctx,key};snapshot=null;pending=null;selected='';comparison='';domain='';view='results';paint();q('#pr-workspace').scrollTop=0}
    context={...ctx,key};
    if(ctx.scope==='reference'){if(ctx.referenceData){snapshot=referenceSnapshot(ctx.referenceData);paint()}return}
    if(!ctx.owner){q('#pr-workspace').innerHTML=note('选择左侧任务，查看其模型、计算结果、方案和交付物。');return}
    if(loading.has(key))return;
    loading.add(key);const gen=generation;
    try{const next=await api('/api/results?'+new URLSearchParams({session:ctx.owner,revision:ctx.revision||''}));if(gen!==generation)return;
      if(!snapshot){snapshot=next;window.ProductWorkspace?.applyResults(next);paint()}else if(snapshot.snapshot_sha256!==next.snapshot_sha256){pending=next;navigation()}else window.ProductWorkspace?.applyResults(snapshot);
    }catch(e){if(gen===generation&&!snapshot)q('#pr-workspace').innerHTML=note('成果清单暂时无法读取：'+e.message)}finally{loading.delete(key)}
  }
  function navigation(){
    q('#pr-nav').innerHTML=`<nav aria-label="产品视图">${[['results','当前成果'],['history','过程与比较'],['source','原始工程'],['graph','设计图']].map(([id,label])=>`<button data-pr-view="${id}" aria-pressed="${view===id}">${label}</button>`).join('')}</nav>${pending?'<button id="pr-update">有新结果 · 点击更新</button>':'<span>模型、曲线、源码与验收依据</span>'}`;
    q('#product-view').classList.toggle('pr-graph',view==='graph');q('#pr-workspace').hidden=view==='graph';
    q('#pd-model').hidden=view!=='graph';q('#pd-trace').hidden=view!=='graph';
  }
  function traceLink(r){return r.source_type==='engineering-case'?`<button class="quiet" data-pr-evidence="${esc(r.id)}">查看计算记录 ↗</button>`:`<button class="quiet" data-pr-trace="${esc(r.id)}">查看本次 Trace ↗</button>`}
  function filesHTML(files){return files.length?`<div class="pr-files">${files.map(f=>`<div><button data-pr-file="${esc(f.id)}" title="${esc(f.applicability.reason)}"><b>${esc(f.name)}</b><small>${f.created_revision?'生成 v'+f.created_revision+' · ':''}${esc(states[f.applicability.state])}${f.integrity===false?' · 校验失败':''}</small></button><a href="${esc(f.url)}" download="${esc(f.name)}" aria-label="下载 ${esc(f.name)}">↓</a></div>`).join('')}</div>`:note('尚无对应工程文件。')}
  function selectedResult(){const rows=snapshot.results.filter(r=>!domain||r.domain===domain);return rows.find(r=>r.id===selected)||window.ProductGraph.featuredResults(rows)[0]}
  function resultList(rows){return rows.map(r=>`<button class="pr-result ${selectedResult()?.id===r.id?'selected':''}" data-pr-result="${r.id}"><b>${esc(r.source_type==='engineering-case'?r.label:(kinds[r.kind]||r.kind))}</b><small>${r.created_revision?'v'+r.created_revision+' · ':''}${time(r.created)} · ${esc(statuses[r.status]||r.status)}</small><span>${esc(states[r.applicability.state])} · ${r.files.length} 件产物</span></button>`).join('')}
  function summary(){
    const v=snapshot.verdict,files=snapshot.files,valid=files.filter(currentFile),target=v?.stages.find(s=>s.id===v.target_stage),historical=snapshot.revision!==snapshot.current_revision;
    const phases={empty:['尚未产生设计成果','当前会话还没有方案、计算或工程文件。结果生成后将自动出现在这里。'],proposal:['已形成产品方案','已记录需求、场景与假设；尚未生成工程模型或仿真。'],engineering:['已有独立工程成果','模型和仿真已保留，但还没有绑定产品装配。可查看，不计为整机验收。'],benchmark:['已有基准计算结果','以下是原任务的计算与策略记录。重命名会话不会改变实验类型，也不会生成 CAD 或 PCB。'],assembly:['已有成果，仍需完成验收','装配、独立运行与历史记录均保留；适用范围逐份标注。']};
    const phase=phases[snapshot.phase]||phases.assembly;
    const caseNote=snapshot.engineering_cases?.length?note('工程案例 '+snapshot.engineering_cases.join('、')+' 已归档：按左侧结果查看动画、CAD、云图、电路、PCB、固件和报告。案例结果与既有装配验收分开记录，未通过的条件保留在各部分。'):'';
    return caseNote+`<section class="pr-summary"><div><small>${snapshot.reference?'独立参考工程':historical?'历史记录':target?'当前目标 · '+target.label:'当前任务 · '+esc(snapshot.title)}</small><h3>${snapshot.reference?'参考辅助设计成果':historical?'历史版本 v'+snapshot.revision:v?.passed?'当前目标阶段已完成':phase[0]}</h3><p>${snapshot.reference?'参考文件与本任务的交付分开保留。':`${files.length} 件已归档 · ${files.filter(f=>f.integrity).length} 件可读取${snapshot.revision?' · '+valid.length+' 件适用于所选装配':''}`}</p></div>${snapshot.reference?'':`<button id="pr-export" ${!files.length?'disabled':''}>下载成果包 ↓</button>`}</section>${snapshot.reference?'':note(phase[1])}${v?`<ol class="pr-stages">${v.stages.map(s=>`<li class="${s.id===v.target_stage?'target':''}"><span>${s.passed?'✓':'○'}</span>${esc(s.label)}<small>${s.passed?'条件满足':s.id==='hardware'?'未实测':'待完成'}</small></li>`).join('')}</ol>`:''}`;
  }
  function gapView(){const rows=snapshot.blockers.filter(b=>!domain||b.domain===domain);if(!snapshot.verdict)return note('尚未建立完整产品验收清单；没有缺口记录不代表已验收。');return `<details class="pr-gaps"><summary>还缺什么 · ${rows.length} 项</summary>${note('缺文件与验证器缺位分开显示；重复运行模型不会自动补齐尚未实现的验收能力。')}${rows.map(b=>`<div><b>${esc(b.label)}</b><span>${esc(gaps[b.state])}</span></div>`).join('')}</details>`}
  function paint(){
    if(!q('#pr-workspace'))return;navigation();if(view==='graph')return;
    const root=q('#pr-workspace'),gen=++drawGeneration;
    if(!snapshot){root.innerHTML=note(context?.owner?'正在整理当前任务的成果…':'选择左侧任务，查看其产品成果。');return}
    const nav=`<nav class="pr-domains" aria-label="成果领域"><button data-pr-domain="" aria-pressed="${!domain}">全部成果</button>${Object.entries(domains).map(([k,v])=>`<button data-pr-domain="${k}" aria-pressed="${domain===k}">${v}<small>${snapshot.files.filter(f=>f.domain===k&&f.integrity!==false).length}</small></button>`).join('')}</nav>`;
    const r=selectedResult(),rows=snapshot.results.filter(x=>!domain||x.domain===domain),files=snapshot.files.filter(x=>!domain||x.domain===domain);
    let body='';
    if(view==='results'&&snapshot.reference){body=referenceBody(files)}else if(view==='results'){
      const chosen=window.ProductGraph.featuredResults(rows);
      body=`<div class="pr-columns"><aside aria-label="工程结果">${resultList(chosen.length?chosen:rows)}${!rows.length?note('此部分尚未生成成果。已有文件会列在右侧。'):''}</aside><article class="pr-detail">${r?resultBody(r):filesHTML(files)}</article></div>${pendingView(rows)}${gapView()}${r&&files.some(f=>f.result_id==='published')?`<details class="pr-published"><summary>已发布的说明与其他文件 · ${files.filter(f=>f.result_id==='published').length}</summary>${filesHTML(files.filter(f=>f.result_id==='published'))}</details>`:''}`;
    }else if(view==='history'){
      body=`${note('按真实执行时间排列。运行先后不等于设计改进；未记录修改理由时不会推断。')}<div class="pr-columns"><aside aria-label="运行历史">${resultList(rows)}</aside><article class="pr-detail">${r?comparisonBody(r,rows):note('尚无工程执行历史。')}</article></div>`;
    }else{
      body=`<div class="pr-source-tools"><input id="pr-file-search" type="search" placeholder="查找原生工程、代码、报告…" aria-label="查找工程文件"><small>${files.length} 件 · 导出包含所有领域、历史与失败记录</small></div><div id="pr-file-list">${filesHTML(files)}</div>`;
    }
    root.innerHTML=summary()+nav+body;
    const search=q('#pr-file-search');if(search)search.oninput=()=>{q('#pr-file-list').innerHTML=filesHTML(files.filter(f=>f.name.toLowerCase().includes(search.value.toLowerCase())))};
    const compare=q('#pr-compare');if(compare)compare.onchange=()=>{comparison=compare.value;paint()};
    if(r&&view==='results')loadVisual(r,gen);
  }
  function pendingView(rows){const pending=rows.filter(r=>['RUNNING','QUEUED','NEEDS_ACTION','UNKNOWN'].includes(r.status));return pending.length?`<section class="pr-gaps"><h3>正在处理与外部等待</h3>${pending.map(r=>`<p>${esc(r.source_type==='engineering-case'?r.label:(kinds[r.kind]||r.kind))} · ${esc(statuses[r.status])} <button class="quiet" data-pr-trace="${r.id}">查看进展 ↗</button></p>`).join('')}</section>`:''}
  function referenceBody(files){
    const node=snapshot.referenceNodes.find(n=>n.id===(domain||'integrated')),simulations=node?.simulations||[];
    const figure=f=>f?`<img class="pr-reference-image" src="${esc(f.url)}" alt="${esc(f.name)}">`:'';
    const find=f=>snapshot.files.find(x=>x.url===f.url);
    const model=files.find(f=>f.name==='model.glb'),image=files.find(f=>f.name.endsWith('.png')&&f.path?.includes('/cad-'));
    return `${note('本页展示已归档的参考工程；不会替当前任务补齐文件或授予验收。')}${model?`<article class="pr-reference"><h3>参考结构模型</h3>${figure(image)}${filesHTML([model])}</article>`:''}${simulations.map(s=>`<article class="pr-reference"><h3>${esc(s.title)}</h3><p>${esc(s.result)}</p>${figure(s.figureFile)}${note(s.scope)}${filesHTML(s.assets.map(find).filter(Boolean))}</article>`).join('')}<details class="pr-published" ${!model&&!simulations.length?'open':''}><summary>此部分全部参考文件 · ${files.length}</summary>${filesHTML(files)}</details>`;
  }
  function metricTable(r){return r.metrics.length?`<dl class="pr-metrics">${r.metrics.filter(m=>!m.name.includes('.inputs.')&&m.name!=='assembly_revision').slice(0,9).map(m=>`<div><dt>${esc(metricLabel(m.name))}</dt><dd>${esc(format(m.value))}</dd></div>`).join('')}</dl>`:note('本次执行未记录可展示的定量指标。')}
  function resultBody(r){
    const files=r.files,visible=files.filter(f=>f.role!=='log').sort((a,b)=>((b.name.includes('assembly')||b.name==='model.glb'||b.name==='result.json')?1:0)-((a.name.includes('assembly')||a.name==='model.glb'||a.name==='result.json')?1:0)),logs=files.filter(f=>f.role==='log');
    return `<header><div><small>${esc(statuses[r.status]||r.status)} · ${r.created_revision?'生成于 v'+r.created_revision:'独立工程'}</small><h3>${esc(r.source_type==='engineering-case'?r.label:(kinds[r.kind]||r.kind))}</h3></div>${traceLink(r)}</header>${note(r.applicability.reason)}${r.design_status?`<p class="pr-check-summary">本次计算判定：<b>${esc(r.design_status==='PASS'?'通过':'未通过')}</b> · ${esc(r.fidelity||'原始计算范围')}</p>`:''}${r.error?`<p class="pr-error">${esc(r.error)}</p>`:''}<div id="pr-visual"></div>${metricTable(r)}${note(r.scope)}<details><summary>输入条件、接口与检查依据</summary><pre>${esc(JSON.stringify({inputs:r.inputs,declared_interfaces:r.interfaces,conditions:r.conditions,checks:r.checks,design:r.design_inputs},null,2))}</pre></details>${r.source_files.length?`<details open><summary>提交时的源码 · ${r.source_files.length}</summary><div class="pr-source-tree">${r.source_files.map(name=>`<button data-pr-source="${esc(name)}">${esc(name)}</button>`).join('')}</div><pre id="pr-source-reader" hidden></pre></details>`:''}<details class="pr-output" open><summary>本次产物 · ${visible.length}</summary>${filesHTML(visible.slice(0,8))}${visible.length>8?`<details><summary>其余产物 · ${visible.length-8} 件</summary>${filesHTML(visible.slice(8))}</details>`:''}</details>${logs.length?`<details><summary>日志与构建细节 · ${logs.length}</summary>${filesHTML(logs)}</details>`:''}`;
  }
  function comparisonBody(r,rows){
    const candidates=rows.filter(x=>x.id!==r.id&&x.kind===r.kind),base=candidates.find(x=>x.id===comparison)||candidates.find(x=>x.created<r.created)||candidates[0];
    const flatten=(value,prefix='',out={})=>{for(const [k,v] of Object.entries(value||{})){const key=prefix?prefix+'.'+k:k;if(v&&typeof v==='object'&&!Array.isArray(v))flatten(v,key,out);else if(Array.isArray(v)&&v.some(x=>x&&typeof x==='object'))v.forEach((item,i)=>{if(item&&typeof item==='object')flatten(item,key+'['+(item.id||i)+']',out);else out[key+'['+i+']']=item});else out[key]=v}return out};
    const inputs=x=>flatten({parameters:x.inputs,interfaces:x.interfaces,design:x.design_inputs,conditions:x.conditions,sources:Object.fromEntries(x.files.filter(f=>f.role==='source').map(f=>[f.name,f.sha256]))});
    const a=inputs(base||{inputs:{},interfaces:{},files:[]}),b=inputs(r),keys=[...new Set([...Object.keys(a),...Object.keys(b)])].filter(k=>JSON.stringify(a[k])!==JSON.stringify(b[k]));
    const metrics=new Map((base?.metrics||[]).map(m=>[m.name,m.value]));
    const changes=`<details open><summary>已记录输入与源码变化 · ${keys.length}</summary>${keys.map(k=>`<p><b>${esc(k)}</b></p><pre>${esc(format(a[k]??'未记录'))} → ${esc(format(b[k]??'未记录'))}</pre>`).join('')||note('上述记录字段相同；其他输入请对照完整工程与 Trace。')}</details>`;
    const table=list=>`<table><thead><tr><th>记录指标</th><th>比较运行</th><th>所选运行</th></tr></thead><tbody>${list.map(m=>`<tr><td>${esc(metricLabel(m.name))}</td><td>${esc(format(metrics.get(m.name)??'未记录'))}</td><td>${esc(format(m.value))}</td></tr>`).join('')}</tbody></table>`;
    const primary=r.metrics.filter(m=>!m.name.includes('.inputs.')&&m.name!=='assembly_revision').slice(0,8),remaining=r.metrics.filter(m=>!primary.includes(m));
    return `<h3>${esc(r.source_type==='engineering-case'?r.label:(kinds[r.kind]||r.kind))} · ${time(r.created)}</h3>${traceLink(r)}<label class="pr-compare-label">比较运行 <select id="pr-compare">${candidates.map(x=>`<option value="${x.id}" ${x.id===base?.id?'selected':''}>${time(x.created)} · ${x.created_revision?'v'+x.created_revision:'未绑定'}</option>`).join('')}</select></label>${base?`<p>${time(base.created)} → ${time(r.created)}</p>${changes}${table(primary)}${remaining.length?`<details><summary>其余记录指标 · ${remaining.length}</summary>${table(remaining)}</details>`:''}`:note('尚无同类工程运行可比较。')}${note('修改理由未独立登记，请查看对应对话和 Trace。数值变化不自动表示改进。')}${filesHTML(r.files.filter(f=>f.role==='data'||f.name==='result.json'))}`;
  }
  async function loadVisual(r,gen){
    if(!r)return;
    const host=q('#pr-visual'),views=r.presentations||[],choice=views.find(v=>v.file_id===visualChoice)||views[0];
    if(r.kind==='proposal'){
      const labels={title:'产品名称',purpose:'解决什么问题',form:'产品形态',service:'提供的服务',installation:'安装与机械约束',energy:'能量来源',assumptions:'工作假设',acceptance:'验收目标',limits:'边界与限制'};
      host.innerHTML=`<div class="pr-proposal">${Object.entries(labels).filter(([k])=>r.inputs[k]).map(([k,l])=>`<section><h4>${l}</h4>${Array.isArray(r.inputs[k])?'<ul>'+r.inputs[k].map(v=>'<li>'+esc(v)+'</li>').join('')+'</ul>':'<p>'+esc(r.inputs[k])+'</p>'}</section>`).join('')}</div>`;return;
    }
    if(!choice){host.innerHTML=note(r.domain==='firmware'?'固件与模型的资源指标、代码和工程文件见下方。烧录与实测须有独立记录。':'尚未生成可预览图形；工程文件与报告保留在下方。');return}
    const f=r.files.find(f=>f.id===choice.file_id);
    host.innerHTML=`<nav class="pr-visual-tabs" aria-label="成果预览">${views.map(v=>`<button data-pr-visual="${esc(v.file_id)}" aria-pressed="${v===choice}">${esc(v.label)}</button>`).join('')}</nav><div id="pr-visual-body"></div>`;
    const body=q('#pr-visual-body');
    if(choice.kind==='model'||choice.kind==='mesh'){body.innerHTML=`<iframe title="${esc(r.source_type==='engineering-case'?r.label:(kinds[r.kind]||r.kind))}三维成果" src="/model-viewer.html?session=${encodeURIComponent(context.owner)}&result_file=${encodeURIComponent(f.id)}${choice.kind==='mesh'?'&mesh=1':''}"></iframe>`;return}
    if(choice.kind==='image'){body.innerHTML=`<button data-pr-file="${esc(f.id)}"><img src="${esc(f.url)}" alt="${esc(f.name)}"></button>`;return}
    if(choice.kind==='video'){body.innerHTML=`<video controls playsinline preload="metadata" style="width:100%;max-height:65vh" src="${esc(f.url)}" aria-label="${esc(f.name)}"></video>`;return}
    if(choice.kind==='pdf'){body.innerHTML=`<iframe title="${esc(f.name)}" src="${esc(f.url)}"></iframe>`;return}
    if(choice.kind==='series'){body.innerHTML=note('正在读取实际计算记录…');try{const s=await api('/api/results/series?'+new URLSearchParams({session:context.owner,id:f.id}));if(gen!==drawGeneration)return;
      body.innerHTML=(s.table?`<div class="pr-data-table"><table><thead><tr>${s.headers.map(h=>'<th>'+esc(h)+'</th>').join('')}</tr></thead><tbody>${s.rows.map(row=>'<tr>'+row.map(v=>'<td>'+esc(String(v))+'</td>').join('')+'</tr>').join('')}</tbody></table></div>`:chart(s))+note(s.scope)+`<button data-pr-file="${esc(f.id)}">查看原始文件 · ${s.total_points} 条记录 ↗</button>`;
    }catch(e){if(gen===drawGeneration)body.innerHTML=note('该文件暂不能直接绘图：'+e.message+'。可打开或下载原始文件。')}}
  }
  function chart(s){
    const xs=s.rows.map(r=>r[0]),lo=Math.min(...xs),hi=Math.max(...xs),fmt=n=>Number(n).toPrecision(3);
    return s.headers.slice(1,5).map((label,i)=>{const ys=s.rows.map(r=>r[i+1]),min=Math.min(...ys),max=Math.max(...ys),points=s.rows.map(row=>`${54+(row[0]-lo)/(hi-lo||1)*550},${145-(row[i+1]-min)/(max-min||1)*115}`).join(' ');return `<figure class="pr-chart"><figcaption>${esc(({storage_voltage_v:'储能电压',input_voltage_v:'输入电压',harvest_current_a:'采集电流',load_power_w:'负载功率'})[label]||label)} · ${esc(s.units[i+1])}</figcaption><svg viewBox="0 0 640 190" role="img" aria-label="${esc(label)}求解器曲线"><path d="M54 20 V145 H610" class="pr-axis"/><polyline points="${points}"/><text x="48" y="32" text-anchor="end">${fmt(max)}</text><text x="48" y="145" text-anchor="end">${fmt(min)}</text><text x="54" y="170">${fmt(lo)}</text><text x="604" y="170" text-anchor="end">${fmt(hi)}</text><text x="320" y="187" text-anchor="middle">${esc(s.headers[0])} (${esc(s.units[0])})</text></svg></figure>`}).join('');
  }
  async function source(name){const r=selectedResult(),gen=drawGeneration;try{const s=await api('/api/results/source?'+new URLSearchParams({session:context.owner,result:r.id,name}));if(gen!==drawGeneration)return;const reader=q('#pr-source-reader');reader.hidden=false;reader.textContent=s.name+'\n\n'+s.content;reader.scrollIntoView({block:'nearest'})}catch(e){window.BF.error(e.message)}}
  function preview(file){
    if(file.name==='project-preview-mesh.json'){const d=document.createElement('dialog');d.className='model-dialog';d.innerHTML=`<form method="dialog"><button aria-label="关闭模型">×</button></form><iframe title="STEP 派生预览" src="/model-viewer.html?session=${encodeURIComponent(context.owner)}&result_file=${encodeURIComponent(file.id)}&mesh=1"></iframe>`;document.body.append(d);d.addEventListener('close',()=>d.remove(),{once:true});d.showModal();return}
    V.preview({...file,session:context.owner,stale:['stale','future'].includes(file.applicability.state)},`${snapshot.reference?'参考工程':snapshot.title} · ${file.created_revision?'生成 v'+file.created_revision:'独立记录'} · ${file.applicability.reason}`);
  }
  async function exportPackage(){const button=q('#pr-export');button.disabled=true;button.textContent='正在核对并打包…';try{const r=await api('/api/results/package',{session_id:context.owner,snapshot_sha256:snapshot.snapshot_sha256,revision:snapshot.revision});const a=document.createElement('a');a.href=r.url;a.download=snapshot.title.slice(0,50)+'-成果包.zip';a.click();button.textContent='工程包已下载 ✓'}catch(e){button.textContent='下载成果包 ↓';window.BF.error(e.message)}finally{button.disabled=false}}
  function focus(options={}){if(options.restore&&traceReturn){({view,domain,selected}=traceReturn);paint();q('#pr-workspace').scrollTop=traceReturn.scroll;return}view=options.view||'results';domain=options.domain||domain;selected=options.result||selected;paint()}
  window.ProductResults={update,focus,chart};
})();
