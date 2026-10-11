(() => {
  const labels={source_build_binding:'源码与构建绑定',power_fixed_point:'原生供电与实际负载对应',event_identity:'事件类型与编号',deadline_receive:'期限内接收',application_dedup:'接收端去重',reference_integrity:'参考输入完整性'};
  const q=s=>document.querySelector(s);
  const node=(tag,text,klass)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(klass)n.className=klass;return n;};
  const get=async owner=>{const r=await fetch('/api/design-lab?session_id='+encodeURIComponent(owner));const value=await r.json();if(!r.ok)throw Error(value.error||'读取失败');return value;};
  const status=value=>({PASS:'通过',FAIL:'未通过',UNEVALUABLE:'不可评价',STALE:'需要重新核对',NOT_CHECKED:'未检查',ACTIVE:'执行中',CONTINUE:'继续',WAIT:'等待原作业',BLOCKED:'存在阻塞',SUBMITTED:'已封存'}[value]||value);
  const review=document.body.dataset.designLab==='review';
  let busy=false;
  async function refresh(){
    if(busy)return;busy=true;
    const owner=review?new URLSearchParams(location.search).get('session_id'):window.BF?.getSelection();
    if(!owner){busy=false;return;}
    try{
      const view=await get(owner);
      if(!review){
        if(owner!==window.BF?.getSelection())return;
        const root=q('#conversation');if(!root)return;
        let card=q('#bf-design-card');if(!card){card=node('aside',null,'bf-design-card');card.id='bf-design-card';root.append(card);}
        card.replaceChildren(node('strong','C 数字工程 · '+status(view.submission?.acceptance.scoped_status||view.status)));
        card.append(node('p','采用版本 '+view.revision+' · 原生仿真按输入复用 · 物理验证未进行'));
        const link=node('a','查看同版验收与交付 →');link.href='/design-lab.html?session_id='+encodeURIComponent(owner);link.target='_blank';card.append(link);return;
      }
      let evidence;
      const selected=view.operations.find(x=>x.status==='SUCCEEDED'&&x.request.design_id===view.current_design);
      if(selected){const r=await fetch('/api/design-lab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'check',session_id:owner,job_id:selected.id})});evidence=await r.json();if(!r.ok)throw Error(evidence.error);}
      const a=view.submission?.acceptance||evidence?.acceptance;
      q('#dl-status').textContent=status(view.status)+' · 当前采用版本 '+view.revision+' · '+owner;
      const root=q('#dl-content');root.replaceChildren();
      const overview=node('section',null,'dl-card');overview.append(node('h2','分别记录三个结论'));const grid=node('div',null,'dl-grid');
      for(const [title,value,note] of [
        ['有限数字工程',a?status(a.scoped_status):'尚无所选版本检查','F0 实际编译逻辑 + Cortex-M4 可重定位目标文件'],
        ['工程归因',view.submission?.attribution.application_source||'以实际设计与轨迹为准','环境、工具与独立检查由 Codex 建设'],
        ['物理验证','未进行','板卡、引脚、刷机、真实 RF 与功耗仍未检查']]){
        const c=node('div');c.append(node('p',title,'dl-label'),node('div',value,'dl-value'),node('p',note,'dl-note'));grid.append(c);
      }overview.append(grid,node('p','验收仅覆盖冻结 D5 包络内的开门事件服务。完整硬件产品及 Agent 方法收益尚未取得通过结论。','dl-note'));root.append(overview);
      const binding=node('section',null,'dl-card');binding.append(node('h2','当前绑定'));for(const [name,value] of [['设计',view.current_design],['任务',view.task_id],['环境',view.environment_id],['检查版本',view.contract.validation_id],['范围',view.contract.scope]])binding.append(node('p',name+' · '+value,'dl-id'));root.append(binding);
      const checks=node('section',null,'dl-card');checks.append(node('h2','独立检查'));const table=node('table');for(const name of view.contract.requirements){const tr=node('tr');tr.append(node('td',labels[name]||name),node('td',status(a?.gates[name]||'NOT_CHECKED'),a?.gates[name]==='PASS'?'dl-pass':'dl-muted'));table.append(tr);}checks.append(table);
      if(evidence?.check.receiver.latency_s!=null)checks.append(node('p','虚拟接收延迟 '+(1000*evidence.check.receiver.latency_s).toFixed(1)+' ms · 本阶段新增原生求解 '+evidence.execution.new_native_solver_calls+' 次','dl-note'));root.append(checks);
      const deliver=node('section',null,'dl-card');deliver.append(node('h2','同版工程包'));if(view.submission){const link=node('a','下载 C 数字工程包','dl-download');link.href='/api/design-lab/package?session_id='+encodeURIComponent(owner);link.download='C-digital-design.zip';deliver.append(link,node('p','下载时重新核对采用版本、验收回执及全部包内文件摘要。大型原生 RAW 以固定摘要的本地依赖记录。','dl-note'));}else deliver.append(node('p','BF 尚未封存所选设计的工程包。','dl-note'));root.append(deliver);
    }catch(error){if(review)q('#dl-status').textContent='状态不可确认：'+error.message;else q('#bf-design-card')?.remove();}finally{busy=false;}
  }
  if(review){q('#dl-refresh').addEventListener('click',refresh);void refresh();setInterval(refresh,5000);}
  else{window.addEventListener('bf-selection',()=>{q('#bf-design-card')?.remove();void refresh();});window.addEventListener('bf-mode',refresh);setInterval(()=>{if(document.body.dataset.studioMode==='task')void refresh();},5000);}
})();
