/* Research is a read-only projection. Trials and conclusions are server-bound. */
(() => {
  const {api, esc} = window.BF;
  let generation = 0;
  const status = v => ({PASS:'检查通过',FAIL:'未通过',COMPLETED:'已执行',INCOMPLETE:'尚未完成',BLOCKED_ORGANIC_EVIDENCE:'缺少有机案例',NOT_IDENTIFIABLE_FROM_HISTORICAL_TRACE:'历史记录不足以识别',INFRA_ERROR:'执行错误',BLOCKED:'受阻',UNKNOWN:'未知',CLAIMED:'执行中',EXPIRED:'已到期',CORRUPT:'证据校验失败'}[v] || v);
  const short = v => String(v || '—').slice(0, 12);
  const names = {'fixed-local':'固定局部','fixed-global':'固定全局','adaptive-closure':'约束启发式','free-scope':'模型选择范围','full-recompute':'完整重验','dependency-cache':'依赖缓存','fixed-transfer':'固定迁移顺序','cost-aware-transfer':'低开销优先'};
  const scopeNotes = {A:'每个方法使用 4 个初始状态 × 3 次重复；属于注入约束的计算先导，不能视为 12 个独立产品或真实机电协同设计。',B:'每个方法评估相同的 10 类变更；“一致”含正确返回未知，不代表产品达标。开销为实测方法总时间，独立审计耗时另列。',C:'只有来源已核实、记录了门控前状态的真实案例，才可进入配对实验；没有合格案例时不生成替代结果。'};
  const detail = (title, value) => `<details class="dev-record"><summary>${esc(title)}</summary><pre>${esc(JSON.stringify(value,null,2))}</pre></details>`;
  const table = (heads, rows) => `<div class="research-table-wrap"><table class="research-table"><thead><tr>${heads.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
  const tr = cells => `<tr>${cells.map(x=>`<td>${x}</td>`).join('')}</tr>`;
  function download(name, text, type){const u=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
  async function open(host){
    const turn=++generation;
    host.innerHTML='<p class="dev-hint" role="status">正在读取研究协议与执行证据…</p>';
    try{
      const data=await api('/api/developer/research');
      if(turn!==generation||host.dataset.module!=='research')return;
      const inv=[...data.inventories].sort((a,b)=>b.observed-a.observed)[0];
      const reports=Object.fromEntries(['A','B','C'].map(p=>[p,[...data.reports].reverse().find(r=>r.paper===p&&r.protocol===data.active_protocols?.[p]&&['scope-pilot','fixed-change-pilot','pilot-readiness'].includes(r.kind))]));
      host.innerHTML=`<div class="dev-heading"><div><h3>研究工作台</h3><p class="dev-hint">事实与协议 → 隔离实验 → 机制先导</p></div><button id="research-export">导出数据</button></div>
        <p class="dev-hint">${esc(data.boundary)}</p>
        <div class="console-cards three"><article><small>阶段 1 · 事实与协议</small><b>${Object.keys(data.active_protocols||{}).length} 份当前协议 · ${data.protocols.length} 份含历史</b><p>${inv?inv.lineages.length+' 条产品谱系；旧资料列为开发数据':'尚未建立事实清单'}</p></article><article><small>阶段 2 · 隔离与验收</small><b>${data.checkpoints.length} 个检查点</b><p>文件与上下文独立复制；原生应用状态未恢复</p></article><article><small>阶段 3 · 机制先导</small><b>${data.trials.length} 个已登记实验</b><p>${data.trials.filter(t=>['BLOCKED','UNKNOWN','INFRA_ERROR','CORRUPT','EXPIRED'].includes(t.status)).length} 个执行问题 · 结论见各研究</p></article></div>
        ${['A','B','C'].map(p=>{const r=reports[p];const protocol=data.protocols.find(x=>x.key===data.active_protocols?.[p])||data.protocols.find(x=>x.paper===p);return `<section class="research-paper"><div class="dev-heading"><h3>${p} · ${{A:'修改范围',B:'证据迁移',C:'反馈盲区'}[p]}</h3><span class="research-state">${esc(r?status(r.status):'尚未执行')}</span></div><p>${esc(r?.reason||r?.claim||protocol?.hypothesis||'尚未登记')}</p>${r?.summary?table(['方法','样本','通过/一致','开销'],r.summary.map(s=>tr([esc(names[s.arm]||s.arm),esc(s.attempted),esc(s.passed??s.audit_agreed),s.cost_upper_usd!==undefined?'$'+s.cost_upper_usd.toFixed(5):Number(s.method_total_s).toFixed(3)+' 秒']))):''}<p class="dev-hint">${esc(scopeNotes[p])}</p>${r?.next?`<p class="dev-hint">下一步：${esc(r.next)}</p>`:''}${r?detail('范围、限制与原始结果',r):''}${protocol?detail('冻结协议 · '+short(protocol.key),protocol):''}</section>`}).join('')}
        ${data.reports.filter(r=>r.kind==='protocol-qualification').map(r=>detail('历史轮次说明 · '+(r.label||short(r.protocol)),r)).join('')}<h3>实验记录</h3><p class="dev-hint">B 的“检查通过”表示判断与独立审计一致，不代表产品达标。未结束和失败的实验均保留。</p>
        <div class="research-filters"><label>研究 <select id="research-paper-filter"><option value="">全部</option><option>A</option><option>B</option><option>C</option></select></label><label>结果 <select id="research-status-filter"><option value="">全部</option>${[...new Set(data.trials.map(t=>t.status))].map(s=>`<option value="${esc(s)}">${esc(status(s))}</option>`).join('')}</select></label></div><div id="research-trials"></div>
        ${inv?`<h3>现状与证据边界</h3>${table(['能力','当前状态','证据层级'],inv.capabilities.map(c=>tr([esc(c.label),esc(c.state),esc(c.level)])))}${detail('产品谱系、来源与预算快照',inv)}`:''}
        ${detail('检查点与恢复边界',data.checkpoints)}<p class="dev-hint">${data.event_count} 条研究事件。原始会话 Trace 与研究事件分别保留；当前研究不会自动采用 Harness 候选。</p>`;
      const paperFor=t=>data.protocols.find(p=>p.key===t.protocol)?.paper||'—';
      function rows(){const paper=host.querySelector('#research-paper-filter').value;const s=host.querySelector('#research-status-filter').value;const filtered=data.trials.filter(t=>(!paper||paperFor(t)===paper)&&(!s||t.status===s));host.querySelector('#research-trials').innerHTML=filtered.length?filtered.map(t=>`<details class="dev-record research-trial"><summary><span>${esc(paperFor(t))} · ${esc(t.unit||short(t.trial))} · ${esc(names[t.arm]||t.arm||'')} · ${esc(t.repeat??'')}</span><span>${esc(status(t.status))}</span></summary><p class="dev-hint">检查点 ${esc(short(t.checkpoint))} · ${t.model_calls??'—'} 次模型调用 · ${t.cost_upper_usd==null?'费用待核对':'$'+t.cost_upper_usd.toFixed(6)}</p><pre>${esc(JSON.stringify(t,null,2))}</pre>${t.result?.audit?`<button data-research-audit="${esc(t.result.audit)}">查看独立验收</button>`:''}</details>`).join(''):'<p class="dev-hint">此筛选下没有已登记实验。</p>';}
      rows();host.querySelectorAll('.research-filters select').forEach(x=>x.onchange=rows);
      host.querySelector('#research-export').onclick=async()=>{try{const value=await api('/api/developer/research/export');download('bf-research-data.json',JSON.stringify(value,null,2),'application/json');download('bf-research-trials.csv','\ufeff'+value.trials_csv,'text/csv;charset=utf-8')}catch(e){alert(e.message)}};
      host.onclick=async e=>{const b=e.target.closest('[data-research-audit]');if(!b)return;try{const row=await api('/api/developer/research/record?kind=audits&id='+b.dataset.researchAudit);let pre=b.nextElementSibling;if(!pre||pre.tagName!=='PRE'){pre=document.createElement('pre');b.after(pre)}pre.textContent=JSON.stringify(row,null,2)}catch(error){b.textContent=error.message}};
    }catch(e){if(turn===generation)host.innerHTML=`<p class="dev-hint bad-text">研究记录未能通过读取或完整性校验：${esc(e.message)}</p>`}
  }
  window.ResearchPanel={open};
})();
