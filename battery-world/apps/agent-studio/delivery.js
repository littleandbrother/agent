/* Product progress and deployment evidence share the existing task/console surfaces. */
(() => {
  const {api,esc}=window.BF;
  const names={passed:'已具备',missing:'待补齐',running:'执行中',unmeasured:'待实测'};
  const generations=new WeakMap();
  const deliveryNames={missing:'缺少',partial:'部分文件',present:'文件已登记',invalid:'完整性失败',stale:'已失效'};
  const validationNames={not_run:'未验收',passed:'通过',failed:'未通过',stale:'需重验'};
  function inventory(d,reference=false){
    if(!d)return '';
    const tasks=(d.tasks||[]).filter(t=>t.applicability!=='not_applicable'), folders=d.contract?.directories||[];
    return `<section class="engineering-contract"><h4>产品工程交付 · ${tasks.length} 项适用</h4><p class="dev-hint">${esc(d.profile_reason||'')} · ${esc(d.verdict?.scope||'')}</p><p class="dev-hint">原生文件、审查视图、验证证据分别登记。文件齐全不等于工程验收通过；硬件实测独立记录。</p>
      <div class="console-cards"><article><small>已登记文件的任务</small><b>${tasks.filter(t=>['present','partial'].includes(t.delivery_status)).length} / ${tasks.length}</b></article><article><small>任务验收通过</small><b>${tasks.filter(t=>t.validation_status==='passed').length} / ${tasks.length}</b></article><article><small>需重验或完整性失败</small><b>${tasks.filter(t=>['invalid','stale'].includes(t.delivery_status)).length}</b></article></div>
      ${folders.map(folder=>`<details class="dev-record"><summary>${esc(folder)} · ${tasks.filter(t=>t.directory===folder).length} 项</summary>${tasks.filter(t=>t.directory===folder).map(t=>`<article class="delivery-contract-task"><b>${esc(t.label)}</b><p><span class="tag">${deliveryNames[t.delivery_status]||esc(t.delivery_status)}</span> <span class="tag">${validationNames[t.validation_status]||esc(t.validation_status)}</span></p><p class="dev-hint">${esc(t.acceptance)}</p><p>${esc(t.validation_reason||t.reason||'')}</p>${t.missing_files?.length?`<p class="dev-hint">缺少：${t.missing_files.map(f=>esc(f.role)).join('、')}</p>`:''}${t.depends_on?.length?`<p class="dev-hint">前置：${t.depends_on.map(id=>esc(tasks.find(x=>x.id===id)?.label||id)).join('、')}</p>`:''}</article>`).join('')}</details>`).join('')}
      <p class="dev-hint">${reference?'本页是参考辅助工程；未注入自主实验会话。':'文件由 Agent 调用 publish_file 后，以 delivery_bind 绑定当前装配与工具执行；物理改动会使相关下游任务失效。'}</p></section>`;
  }
  const link=(job,name)=>`/api/engineering/jobs/${encodeURIComponent(job)}/artifact?name=${encodeURIComponent(name)}`;
  const files=j=>(j.result?.artifacts||[]).filter(a=>['deployment.zip','README.md','model.c','model.h','model.json','architecture.json','nas-candidates.json','metrics.json','firmware.bin','firmware.elf','firmware-check.json','flash_mcu.py','measurement-contract.json','dataset.json','split.json','companion_main.c'].includes(a.name)).map(a=>`<a href="${link(j.job_id,a.name)}" download="${esc(a.name)}" title="SHA-256 ${esc(a.sha256)}">${esc(a.name)}</a>`).join('');
  function network(a){return `<div class="network-chain" aria-label="网络结构">${(a?.architecture||[]).map((n,i,all)=>`<span>${i===0?'输入':i===all.length-1?'输出':'Dense + ReLU'}<b>${esc(n)}</b></span>`).join('<i>→</i>')}</div>`}
  function job(j){
    const r=j.result||{},m=r.metrics,b=r.build,nas=r.nas;
    return `<article class="deployment-record"><h4>${j.engine==='mcu-firmware'?'产品固件':'TinyML · NAS 与部署'} <small>${esc(j.status)}${j.stale?' · 历史版本':''}${!j.integrity?' · 文件完整性失败':''}</small></h4>${j.error?`<p class="bad-text">${esc(j.error)}</p>`:''}
      ${m?`${network(r.architecture)}<p class="dev-hint">数据：${esc(m.source_kind)}${m.source_kind==='synthetic-fixture'?' · 演示流程，分数不代表真实用户识别效果':''} · ${esc(m.winner.id)}</p><div class="deployment-metrics"><span>Parameters<b>${m.winner.parameters}</b></span><span>MAC / inference<b>${m.winner.macs_per_inference}</b></span><span>MCU 延迟 / ms<b>${m.latency_ms_mcu??'待实测'}</b></span><span>MCU 功耗 / mW<b>${m.power_mw_mcu??'待实测'}</b></span><span>单次能量 / µJ<b>${m.energy_uj_per_inference??'待实测'}</b></span></div>`:''}
      ${b?`<p>目标：${esc(b.target)} · Flash ${b.flash_bytes.toLocaleString()} / ${b.flash_limit_bytes.toLocaleString()} B · 静态 RAM ${b.ram_static_bytes} B + 预留栈 ${b.reserved_stack_bytes} B</p><p class="dev-hint">${j.engine==='tinyml-nas'?'测试向量计时固件；传感器输入和产品行为尚未集成。':'PA0 按键、PB0/PB1 LED；烧录前需核对实际 PCB。'} 目标编译${b.memory_fit?'通过':'未通过'}，未烧录、未实测。</p>`:''}
      ${nas?`<details><summary>NAS 候选 · ${nas.candidates.length} 个 · 查看比较</summary><p class="dev-hint">按会话分组划分数据；仅验证集选型，测试集不参与选择。</p><div class="deployment-table"><table class="trace-table"><thead><tr><th>架构</th><th>参数量</th><th>MAC</th><th>验证集 INT8</th><th>Pareto</th></tr></thead><tbody>${nas.candidates.map(c=>`<tr><td>${esc(c.architecture.join(' → '))}${c.id===nas.winner?' ✓':''}</td><td>${c.parameters}</td><td>${c.macs_per_inference}</td><td>${(100*c.validation_int8_accuracy).toFixed(1)}%</td><td>${c.pareto?'是':'否'}</td></tr>`).join('')}</tbody></table></div><p class="dev-hint">测试集 INT8 ${(100*m.test_int8_accuracy).toFixed(1)}%；主机 ${m.host_profile?.host_latency_ms?.toPrecision(3)??'未知'} ms，不能替代 MCU 延迟。</p></details>`:''}
      <div class="engineering-artifacts">${files(j)}</div></article>`;
  }
  async function open(root,owner,compact=false){
    if(root.id==='section-content'&&window.EngineeringWorkspace?.active())return;
    const mode=document.body.dataset.studioMode,workspace=document.body.dataset.workspace;
    const gen=(generations.get(root)||0)+1;generations.set(root,gen);root.innerHTML='<p class="dev-hint">读取版本和交付证据…</p>';
    const currentView=()=>gen===generations.get(root)&&root.isConnected&&window.BF.getSelection()===owner&&document.body.dataset.studioMode===mode&&document.body.dataset.workspace===workspace&&!(root.id==='section-content'&&window.EngineeringWorkspace?.active());
    if(!owner){root.innerHTML='<p class="dev-hint">选择一个会话查看交付与部署。</p>';return}
    try{
      const results=await api('/api/results?session='+encodeURIComponent(owner));
      if(!currentView())return;
      const catalog=`<section class="deployment-record"><h4>统一成果目录 · ${results.files.length} 件文件</h4><p class="dev-hint">${results.coverage.map(d=>esc(d.label)+' '+d.files+' 件').join(' · ')}。方案、基准计算、独立工程和装配交付共用后台目录。</p><button data-result-open>查看成果与过程 →</button><details><summary>数据来源与绑定范围</summary>${results.results.map(r=>`<p>${esc(r.kind)} · ${esc(r.id)} · ${esc(r.status)} · ${esc(r.applicability.reason)}</p>`).join('')||'<p>暂无方案或执行记录。</p>'}</details></section>`;
      if(!results.revision){root.innerHTML='<h3>交付与部署</h3>'+catalog+'<p class="dev-hint">尚无产品装配与阶段验收记录。已有计算或独立仿真可查看，不能据此宣称整机交付。</p>';root.querySelector('[data-result-open]').onclick=()=>window.ProductWorkspace.showSession({view:'results'});return}
      const [d,contract]=await Promise.all([api('/api/progress?session='+encodeURIComponent(owner)),api('/api/deliverables?session='+encodeURIComponent(owner))]);if(!currentView())return;
      root.innerHTML=`<div class="dev-heading"><div><h3>交付与部署</h3><p class="dev-hint">装配 ${d.revision?'v'+d.revision:'尚未建立'} · ${d.delivery?.passed?'当前声明阶段条件已满足':d.delivery?'逐项查看缺少的产物与验证':'按当前版本展示工程证据；未设置自动交付条件'}</p></div><button data-delivery-refresh class="quiet">刷新</button></div>
        <div class="delivery-stages">${d.stages.map(s=>`<article data-stage="${s.id}"><span class="delivery-dot ${s.state}"></span><div><b>${esc(s.title)}</b><p>${esc(s.detail)}</p></div><small>${names[s.state]||esc(s.state)}</small>${!compact?`<button class="quiet" data-stage-map="${s.module}" aria-label="在全景中定位${esc(s.title)}">↗</button>`:''}</article>`).join('')}</div>
        ${d.delivery?.stages?`<details class="dev-record"><summary>统一阶段判定 · ${esc(d.delivery.target_stage)} · ${d.delivery.passed?'通过':'待完成'}</summary>${d.delivery.stages.map(s=>`<p>${esc(s.label)}：${s.passed?'通过':s.status==='not_measured'?'未实测':'待完成'} · ${s.missing.length} 项缺口</p>`).join('')}<p class="dev-hint">判定 ${esc(d.delivery.verdict_sha256?.slice(0,16)||'')}</p></details>`:''}
        ${d.conversation.error?`<p class="delivery-blocker">当前中断：${esc(d.conversation.error)}${d.delivery?.missing?.length?' · '+esc(d.delivery.missing.join('、')):''}</p>`:''}
        ${!compact?`<details class="dev-record"><summary>最近工具错误 · ${d.failures.length} 条历史记录</summary>${d.failures.map(f=>`<p><b>${esc(f.tool)}</b> · Trace #${f.seq}</p><pre>${esc(f.error)}</pre>`).join('')||'<p>暂无记录。</p>'}<button data-delivery-trace class="quiet">打开 Trace 查看原始调用 →</button></details>`:''}
        <section>${d.deployments.map(job).join('')||'<p class="dev-hint">尚未生成当前产品的部署包。已有参考固件的历史验收不会冒充已烧录。</p>'}</section>
        ${d.revision?`<details class="deployment-actions"><summary>构建与搜索</summary><p class="dev-hint">本机生成版本绑定产物，不调用付费模型，不自动烧录。</p><button data-build-engine="mcu-firmware">构建 MCU 固件包</button><details><summary>TinyML 数据与搜索参数</summary><p class="dev-hint">演示默认：按键节奏。使用真实数据时删除 demo，填 dataset_path 为本会话工作目录内的 JSON 路径。</p><textarea data-nas-params rows="8" aria-label="NAS 参数">${esc(JSON.stringify({demo:true,seed:7,epochs:200,architectures:[[4],[8],[16],[8,4],[16,8]]},null,2))}</textarea><button data-build-engine="tinyml-nas">运行有界 NAS</button></details><p data-build-notice role="status"></p></details>`:''}
        <details class="dev-record"><summary>当前阶段目标 · 由使用者设置</summary><p class="dev-hint">只选择本轮交付范围，不修改工程验收规则或预算。更改会留下版本记录。</p><select data-stage-target aria-label="阶段目标">${[['concept','需求与方案'],['digital-model','原生数字模型'],['engineering-package','工程文件齐套'],['computational-verification','计算与工程验收'],['hardware','实物验收']].map(([id,label])=>`<option value="${id}" ${d.delivery?.target_stage===id?'selected':''}>${label}</option>`).join('')}</select><input data-stage-reason aria-label="更改阶段原因" placeholder="说明本轮目标或变更原因"><button data-stage-save>保存阶段目标</button><p data-stage-notice role="status"></p></details><section class="deployment-record"><h4>产品交付物</h4><p class="dev-hint">按机械、电路、固件等部分查看图片、代码、仿真与原生工程。</p><button data-delivery-product>在产品页查看交付物 ↗</button></section><details class="dev-record"><summary>交付验收清单 · ${(contract.tasks||[]).length} 项</summary>${inventory(contract)}</details>${d.revision?'<button data-engineering-package class="quiet">导出当前工程包（含未完成项）</button><p data-package-notice role="status"></p>':''}
        <p class="dev-hint">${esc(d.scope)}</p>`;
      root.querySelector('[data-stage-save]').onclick=async()=>{const notice=root.querySelector('[data-stage-notice]');try{await api('/api/deliverables',{session_id:owner,action:'configure_stage',expected_revision:d.delivery?.stage_contract?.revision||0,target_stage:root.querySelector('[data-stage-target]').value,max_continuations:2,reason:root.querySelector('[data-stage-reason]').value});await open(root,owner,compact)}catch(e){notice.textContent=e.message}};
      root.querySelector('[data-delivery-product]').onclick=()=>window.ProductWorkspace.showSession();
      root.insertAdjacentHTML('afterbegin',catalog);root.querySelector('[data-result-open]').onclick=()=>window.ProductWorkspace.showSession({view:'results'});
      root.querySelector('[data-delivery-refresh]').onclick=()=>open(root,owner,compact);
      root.querySelector('[data-engineering-package]')?.addEventListener('click',async e=>{
        e.target.disabled=true;const notice=root.querySelector('[data-package-notice]');notice.textContent='正在核对并打包…';
        try{const p=await api('/api/deliverables',{session_id:owner,action:'package'});notice.innerHTML=`<a href="/api/assembly/file?session=${encodeURIComponent(owner)}&id=${encodeURIComponent(p.id)}" download>下载工程包</a> · 此包保留未完成项，不代表可制造验收通过。`}catch(error){notice.textContent=error.message}finally{e.target.disabled=false}
      });
      root.querySelector('[data-delivery-trace]')?.addEventListener('click',()=>window.BFDeveloper.openModule('trace'));
      root.querySelectorAll('[data-stage-map]').forEach(b=>b.onclick=()=>window.Panorama.focus(b.dataset.stageMap));
      if(d.deployments.some(j=>['QUEUED','RUNNING'].includes(j.status)))setTimeout(()=>{if(currentView()&&root.offsetParent!==null)open(root,owner,compact)},2000);
      root.querySelectorAll('[data-build-engine]').forEach(b=>b.onclick=async()=>{
        b.disabled=true;const notice=root.querySelector('[data-build-notice]');notice.textContent='正在提交本机任务…';
        try{const parameters={...(b.dataset.buildEngine==='tinyml-nas'?JSON.parse(root.querySelector('[data-nas-params]').value):{}),assembly_revision:d.revision};const j=await api('/api/engineering',{session_id:owner,action:'run',engine:b.dataset.buildEngine,parameters,operation_id:'deploy-'+crypto.randomUUID()});notice.textContent='已提交 '+j.id+'，正在加载进度；Trace 保留完整过程。';setTimeout(()=>{if(gen===generations.get(root)&&root.isConnected&&window.BF.getSelection()===owner)open(root,owner,compact)},1500)}catch(e){notice.textContent=e.message}finally{b.disabled=false}
      });
    }catch(e){if(currentView())root.innerHTML=`<p class="dev-hint">${esc(e.message)}</p>`}
  }
  window.DeliveryPanel={open,inventory};
})();
