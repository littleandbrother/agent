(() => {
  const {api,esc}=window.BF;
  const names={mechanical:'机械',circuit:'电路',pcb:'PCB',firmware:'固件',simulation:'仿真',delivery:'交付'};
  const states={PASS:'通过',FAIL:'未通过',FAILED:'执行失败',SUCCEEDED:'执行成功',IDLE:'本轮已结束',QUEUED:'排队中',PAUSED:'已暂停',NO_MEASURED_BENEFIT:'未测得收益 · 保留父版',LOCAL_QUALIFIED:'局部资格 · 限定实验',REJECTED_REGRESSION:'退化 · 拒绝',RUNNING:'执行中',STARTING:'正在启动',INTERRUPTED:'已中断',PENDING:'待评价',BINDING_VERIFIED:'源码绑定已核对',UNEVALUABLE:'条件不足 · 尚不能判定',UNRESOLVED:'待补足条件'};
  const roles={'full-system-candidate':'完整系统候选','specialty-mechanical-electric':'机械／电气专项','specialty-power':'电源专项','alternative-chipless':'无芯片架构','alternative-wireless-power':'无线供电架构'};
  let host=null,data=null,version=null,selected='P01',sequence=0;
  const dollars=n=>'$'+Number(n||0).toFixed(4);
  const problemSummary=items=>{
    const labels={DELIVERY_FILE_HASH:'文件摘要不符',DELIVERY_NATIVE_BINDINGS:'交付作业绑定不一致',EXECUTION_OR_USAGE_UNVERIFIED:'执行或费用明细未核实'};
    const counts=new Map();for(const item of items)counts.set(item,(counts.get(item)||0)+1);
    return [...counts].map(([item,count])=>{
      const name=labels[item]||(item.startsWith('DELIVERY_NATIVE_INPUT_MISSING:')?'缺少原生输入：'+item.slice('DELIVERY_NATIVE_INPUT_MISSING:'.length):item);
      return name+(count>1?'（'+count+'处）':'');
    }).join('；');
  };
  const observedTime=value=>new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+' 北京时间';
  function refreshObservedTime(){
    const stamp=host?.querySelector('[data-learning-updated]');
    if(stamp)stamp.textContent=observedTime(data.updated_at_utc);
    const scope=document.querySelector('#console-scope span:last-child');
    if(scope&&host?.dataset.module==='learning')scope.textContent='更新于 '+observedTime(data.updated_at_utc);
  }
  const link=a=>a?`<a href="/api/literature-learning/artifact?path=${encodeURIComponent(a.path)}" target="_blank" rel="noopener">${esc(a.label||'查看记录')} ↗</a>`:'';
  function nativeRecheck(row,current){
    if(!row)return '';
    const matches=current?.owner===row.owner&&current.result_sha256===row.original_result_sha256;
    const status=states[row.native_readback.status]||row.native_readback.status;
    const detail=row.delivery_integrity?`${row.native_readback.native_checks.length} 项文件读回，清单 ${esc(states[row.delivery_integrity.status]||row.delivery_integrity.status)}。`:'从原作业不可变输入补充源码绑定；保留原文件检查结论。';
    const execution=row.execution_state?`<p>原执行状态：${esc(states[row.execution_state.status]||row.execution_state.status)} ${esc(row.execution_state.error||'')}</p>`:'';
    return `<aside class="learning-active"><strong>${matches?'当前封存版本的独立复查':'历史封存版本的独立复查'}：${esc(status)}</strong>${matches?'':'<p>该复查对应历史封存版本。当前文件状态见上方原生工程与交付记录。</p>'}<p>${detail}功能与整机继续单独验收。新增模型请求 ${row.model_calls_added||row.model_calls||0}，重复计算 ${row.native_jobs_repeated||row.new_solver_runs||0}。</p>${execution}${link(row.artifact)}</aside>`;
  }
  function nativeFiles(task){
    const files=[...new Map((task.artifacts||[]).map(a=>[a.path,a])).values()];
    const reportCopies=files.filter(a=>/\/(native-report\.json|delivery\/manifest\.json|delivery\/UNVERIFIED\.md)$/.test(a.path));
    const reports=[...new Map(reportCopies.map(a=>[a.path.split('/').at(-1)+' '+a.sha256,a])).values()];
    const currentJobs=new Set((task.evaluation?.native_checks||[]).map(c=>c.job_id));
    const reportPaths=new Set(reportCopies.map(a=>a.path));
    const sources=files.filter(a=>a.path.includes('/participant-files/')&&!reportPaths.has(a.path));
    const outputs=files.filter(a=>a.path.startsWith('runtime/engineering/')&&currentJobs.has(a.path.split('/')[2]));
    const shown=new Set([...reportCopies,...sources,...outputs].map(a=>a.path));
    const history=files.filter(a=>!shown.has(a.path));
    const list=items=>`<ul class="learning-file-list">${items.map(a=>`<li>${link({...a,label:a.path.includes('/participant-files/')?a.path.split('/participant-files/')[1]:a.path.split('/').slice(-2).join('/')})}<small>${esc(a.actor||'实际产物')} · ${a.sha256?.slice(0,12)||''}</small></li>`).join('')}</ul>`;
    return `<div class="learning-files">${reports.map(a=>link({...a,label:a.path.split('/').at(-1)})).join('')}</div>${sources.length?`<details data-learning-section="sources-${task.paper}"><summary>本版本可编辑资料 · ${sources.length} 文件</summary>${list(sources)}</details>`:''}${outputs.length?`<details data-learning-section="outputs-${task.paper}"><summary>本版本可信原生输出 · ${outputs.length} 文件</summary>${list(outputs)}</details>`:''}${history.length?`<details data-learning-section="history-${task.paper}"><summary>历史与未选中作业 · ${history.length} 文件</summary><p>保留供审查；这些文件未全部纳入当前交付验收。</p>${list(history)}</details>`:''}`;
  }
  async function load(force=false){
    if(!host?.isConnected||host.dataset.module!=='learning'||document.hidden)return;
    const request=++sequence;
    try{const value=await api('/api/literature-learning',undefined,{cache:'no-store'});if(request!==sequence||host.dataset.module!=='learning')return;data=value;if(force||version!==value.projection_sha256){version=value.projection_sha256;render()}refreshObservedTime()}
    catch(e){if(request===sequence)host.innerHTML=`<p role="status">读取学习记录失败：${esc(e.message)} <button data-learning-refresh>重试</button></p>`}
  }
  function render(){
    if(!data?.available){host.innerHTML='<p>尚未登记近期论文任务。</p>';return}
    const expanded=new Set([...host.querySelectorAll('details[open][data-learning-section]')].map(el=>el.dataset.learningSection));
    const checks=data.trials.filter(t=>t.kind==='solver'&&t.model_calls>0),passed=checks.filter(t=>t.evaluation?.status==='PASS').length;
    const paper=data.papers.find(p=>p.id===selected)||data.papers[0];
    const sourceTask=data.paper_tasks.filter(t=>t.paper===paper.id&&t.stage==='source').at(-1);
    const nativeTask=data.paper_tasks.filter(t=>t.paper===paper.id&&t.stage==='native').at(-1);
    const active=(data.paper_attempts||[]).filter(t=>t.paper===paper.id&&!t.result_available&&['RUNNING','STARTING','QUEUED'].includes(t.execution?.status)).at(-1);
    const nativeChecks=[...new Map(data.paper_tasks.filter(t=>t.stage==='native').map(t=>[t.paper,t])).values()],nativePassed=nativeChecks.filter(t=>t.evaluation.status==='PASS').length;
    const recheck=(data.native_rechecks||[]).filter(t=>t.paper===paper.id).at(-1);
    const faultReview=(data.functional_reviews||[]).filter(t=>t.paper===paper.id).at(-1);
    const stageReview=(data.stage_reviews||[]).filter(t=>t.paper===paper.id).at(-1);
    const bundle=(data.deliveries||[]).filter(t=>t.paper===paper.id).at(-1);
    const budgets=data.owner_budgets,settled=budgets.reduce((n,b)=>n+b.liability_usd,0),unknown=budgets.reduce((n,b)=>n+b.unknown_requests.length,0);
    const currentBudget=budgets.find(b=>b.owner===nativeTask?.owner);
    host.innerHTML=`<section class="learning-view">
      <header class="learning-heading"><div><p class="learning-eyebrow">BF AGENT · LEARNING</p><h3>从工程经历到工作方法</h3><p>论文、设备与方法分别留证；采用决定来自独立检查。</p></div><button class="quiet" data-learning-refresh>刷新记录</button></header>
      <div class="learning-axes"><article><small>工程结果</small><strong>${nativePassed}/${nativeChecks.length} 原生读回</strong><p>局部方法检查 ${passed}/${checks.length} · 完整产品验收 ${data.accepted_full_products} 项</p></article><article><small>实际贡献</small><strong>Pi 求解与候选</strong><p>Codex 维护公共环境、资料与检查器</p></article><article><small>物理验证</small><strong>尚未测试</strong><p>计算通过不表示制造、实测或临床通过</p></article></div>
      <div class="learning-sources"><div><h4>近期论文与工程入口 <span>${data.papers.length}</span></h4><p>${data.full_system_candidates} 个完整系统候选；其余保留各自专项或替代架构范围。</p></div><div class="learning-paper-list" role="tablist" aria-label="论文参考">${data.papers.map(p=>`<button role="tab" data-learning-paper="${p.id}" aria-selected="${p.id===paper.id}"><small>${p.id} · ${p.published.slice(0,4)}</small><span>${esc(p.title)}</span><em>${esc(roles[p.role])} · ${p.assets.length} 项资料</em></button>`).join('')}</div>
      <article class="learning-paper" role="tabpanel"><p class="learning-eyebrow">${paper.id} · ${paper.published}</p><h4>${esc(paper.title)}</h4><a href="https://doi.org/${encodeURIComponent(paper.doi)}" target="_blank" rel="noopener">原始论文 ↗</a><p>${esc(paper.boundary)}</p><p>资料核对：${sourceTask?esc(states[sourceTask.evaluation.status]||sourceTask.evaluation.status):'等待 Pi 任务'} · 原生读回：${nativeTask?esc(states[nativeTask.evaluation.status]||nativeTask.evaluation.status):'待执行'} · 完整产品：未验收 · 实测：未进行</p>
      ${active?`<aside class="learning-active" role="status"><strong>${active.stage==='native'?'原生工程':'资料核对'} · ${esc(states[active.execution.status]||active.execution.status)}</strong><p>Pi ${esc(active.owner)} · 本会话费用上界 ${dollars(active.budget.liability_usd)}${active.budget.unbounded?" · 不设上限":" / "+dollars(active.budget.cap_usd)}</p>${active.jobs.map(j=>`<p>${esc(j.kind||'原生工程作业')} · ${esc(states[j.status]||j.status)} · ${esc(j.id)}${j.readback_passed?' · 文件读回通过':''}</p>`).join('')}</aside>`:''}
      ${sourceTask?`<div class="learning-files">${sourceTask.artifacts.map(link).join('')}</div>`:''}
      ${nativeTask?`<section class="learning-native"><h5>${active?'上次封存工程与独立读回':'当前原生工程与独立读回'}</h5><p>${nativeTask.evaluation.native_checks.length} 项可信读回；功能、源模型和制造检查仍按各自范围验收。${nativeTask.evaluation.problems.length?'未通过项：'+esc(problemSummary(nativeTask.evaluation.problems)):''}</p><p class="learning-session">独立 Pi 会话 <code>${esc(nativeTask.owner)}</code> · 当前会话费用上界 ${dollars(currentBudget?.liability_usd??nativeTask.budget.liability_usd)}${currentBudget?.unbounded?" · 不设上限":" / "+dollars(nativeTask.budget.cap_usd)}${nativeTask.continuation?' · 原任务续跑':''}</p>${nativeFiles(nativeTask)}</section>`:''}
      ${bundle?`<aside class="learning-active"><strong>${active?'上一封存版本 · 本轮仍在修订':bundle.matches_current_result?'本篇封存工程复核包':'历史工程复核包'}</strong><p>独立会话 ${esc(bundle.owner)} · ${bundle.entries} 项逐项哈希核对 · ZIP 读回 ${esc(states[bundle.zip_readback]||bundle.zip_readback)}</p><div class="learning-files">${link({...bundle.download,label:'下载 '+paper.id+' 工程复核包'})}${link(bundle.artifact)}</div><p>原生文件门 ${esc(states[bundle.native_file_delivery_status]||bundle.native_file_delivery_status)}；完整工程与物理验证尚未通过。</p></aside>`:''}
      ${nativeRecheck(recheck,nativeTask)}
      ${faultReview?`<aside class="learning-active"><strong>固件独立功能检查：${esc(states[faultReview.status]||faultReview.status)}</strong><p>${faultReview.matches_current_selected_sources?'检查源码与当前选中交付一致。':'这是历史源码检查；变更后的实现须重新检查。'} ${Object.values(faultReview.checks||{}).filter(Boolean).length}/${Object.keys(faultReview.checks||{}).length} 项通过。</p><p>${esc((faultReview.counterexamples||[]).join('；'))}</p>${link(faultReview.artifact)}<p>主机事件检查；目标无线、传感器和硬件仍需各自验收。</p></aside>`:''}
      ${stageReview?`<aside class="learning-active"><strong>电路独立需求检查：${esc(states[stageReview.status]||stageReview.status)}</strong><p>${stageReview.matches_current_selected_sources?'检查输入与当前选中电路一致。':'历史电路检查；当前版本需要重新核对。'} 文件可读与电路满足要求分别判定。</p><ul>${(stageReview.checks||[]).map(c=>`<li>${esc(c.id)} · ${esc(states[c.status]||c.status)}</li>`).join('')}</ul>${link(stageReview.artifact)}<p>使用既有波形，新增求解 ${stageReview.new_solver_runs||0} 次；真实采能源与物理验证尚未通过。</p></aside>`:''}
      <details><summary>当前来源与内容哈希</summary><ul>${paper.assets.map(a=>`<li>${link({...a,label:a.path.split('/').at(-1)})}<code>${a.sha256.slice(0,16)}</code></li>`).join('')}</ul></details></article></div>
      <h4>设备与方法的两条时间线</h4><div class="learning-lines"><article><small>工程任务</small><strong>来源 → Pi 分析 → 独立检查 → 原生工程</strong><p>每篇论文有自己的任务、会话、工作目录和账本。</p></article><article><small>方法版本</small><strong>M0 → ${data.candidates.map(c=>esc(c.child_method||c.method_name||'候选')).join('、')||'Pi 候选'} → 配对评价</strong><p>局部资格、生产采用与递归改进分别记录；拒绝和无收益保留。</p></article></div>
      <details class="learning-paper-history"><summary>十篇论文的实际任务记录</summary><div class="learning-table"><table><thead><tr><th>论文</th><th>阶段</th><th>执行</th><th>独立检查</th><th>累计调用</th><th>会话费用上界</th></tr></thead><tbody>${data.paper_tasks.map(t=>`<tr><td>${esc(t.paper)}</td><td>${t.stage==='native'?'原生读回':'资料核对'}${t.continuation?' · 续跑':''}</td><td>${esc(t.execution?states[t.execution.status]||t.execution.status:t.process_status)}</td><td>${esc(states[t.evaluation.status]||t.evaluation.status)}</td><td>${t.model_calls}</td><td>${dollars(t.budget.liability_usd)}</td></tr>`).join('')}</tbody></table></div></details>
      <h4>经历 → 方法补丁 → 行为 → 结果</h4>${data.candidates.length?data.candidates.map(c=>`<article class="learning-candidate"><header><strong>Pi 候选 ${esc(c.child_method||c.method_name||'M1')}</strong><span>${esc(states[c.decision]||c.decision)}</span></header><p>${esc(c.hypothesis||'')}</p><p><small>可能推翻它的结果</small>${esc(c.falsifier||'')}</p>${c.allowed_experimental_use?.length?`<p>限定实验范围：${esc(c.allowed_experimental_use.join('、'))}。</p>`:''}${c.costs?`<p>父版 ${dollars(c.costs.parent)}，候选 ${dollars(c.costs.child)}；改进会话 ${dollars(c.costs.improver)} 单独计入。</p>`:''}<details data-learning-section="candidate-${esc(c.child_method||'M1')}"><summary>实际加载的候选指令</summary><pre>${esc(c.instruction||'')}</pre></details><div class="learning-files">${link(c.artifact)}${link(c.source)}${link(c.experience)}${link(c.comparison)}${link(c.qualification)}</div><p>生产采用：${c.adopted?'已采用':'未采用'} · RSI收益：尚未证明</p></article>`).join(''):'<p>暂无已冻结的 Pi 方法候选。</p>'}
      <div class="learning-table"><table><caption>真实运行与独立检查</caption><thead><tr><th>任务</th><th>执行者</th><th>过程</th><th>检查</th><th>方法实际发送</th><th>模型调用</th><th>费用上界</th><th>回执</th></tr></thead><tbody>${data.trials.map(t=>`<tr><td>${esc(t.trial)}</td><td>${t.model_calls>0?'Pi':'模型前接口检查'}</td><td>${esc(t.process_status)}</td><td>${esc(t.evaluation?states[t.evaluation.status]:'候选生成')}</td><td>${t.method_in_actual_request?'已确认':'未确认'}</td><td>${t.model_calls}</td><td>${dollars(t.cost_upper_bound_usd)}</td><td>${link(t.artifact)}</td></tr>`).join('')}</tbody></table></div>
      <details class="learning-budget"><summary>${budgets.some(b=>b.unbounded)?'论文 Pi 会话累计费用与 token 不设上限':'每会话／任务按授权预算执行'} · 历史费用保留</summary><p>累计费用上界 ${dollars(settled)}；${unknown} 项用量尚未结清。费用按实际记录，历史授权与当前策略分别保留。</p><ul>${budgets.map(b=>`<li><code>${esc(b.owner)}</code><span>${dollars(b.liability_usd)}${b.unbounded?' · 不设上限':' / '+dollars(b.cap_usd)}</span><span>${b.unbounded?'累计 token 不设上限':'剩余 '+dollars(b.remaining_usd)}</span>${b.unknown_requests.length?'<b>含未结清费用</b>':''}</li>`).join('')}</ul></details>
      <footer>只读展示 · <span data-learning-updated>${esc(observedTime(data.updated_at_utc))}</span> · 精确产物与检查以内容哈希绑定</footer></section>`;
    host.querySelectorAll('details[data-learning-section]').forEach(el=>{el.open=expanded.has(el.dataset.learningSection)});
    refreshObservedTime();
  }
  document.addEventListener('click',e=>{const button=e.target.closest('[data-learning-paper],[data-learning-refresh]');if(!button||!host?.contains(button))return;if(button.dataset.learningPaper){selected=button.dataset.learningPaper;render()}else load(true)});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load()});
  setInterval(()=>load(),4000);
  window.LiteratureLearning={open:el=>{host=el;if(data)render();else el.innerHTML='<p role="status">正在读取论文、工程与方法记录…</p>';load(true)}};
})();
