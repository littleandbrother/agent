/* Operator-only reference package; never injected into participant context. */
(() => {
  const {api,esc}=window.BF;
  const link=p=>'/api/reference-case/artifact?name='+encodeURIComponent(p);
  async function open(root){
    root.innerHTML='<p class="section-note">正在核对参考案例与产物…</p>';
    try {
      const d=await api('/api/reference-case');if(!root.isConnected)return;
      if(!d.available){root.textContent=d.status;return}
      const gates=d.gates||[], runs=d.runs||[];
      root.innerHTML=`<div class="dev-heading"><h3>${esc(d.title)}</h3><span class="tag">仿真参考案例</span></div>
      <p class="dev-hint">${esc(d.summary)} · ${d.artifact_integrity?'产物哈希核对通过':'产物校验失败，请查看下方记录'}</p>
      <section class="deployment-record"><h4>产品交付物</h4><p class="dev-hint">在产品图点击机械、电路、固件等部分，查看仿真曲线、图片、代码和原生工程文件。这里保留校准与验收记录。</p><button data-reference-product>在产品页查看交付物 ↗</button></section>
      <div class="console-cards">${gates.map(g=>`<article><small>${esc(g.label)}</small><b>${g.passed===true?'通过':g.passed===false?'未通过':'待验证'}</b><p>${esc(g.detail)}</p></article>`).join('')}</div>
      <h4>同一产品的计算过程</h4><p class="section-note">动力学 → 机电耦合 → 整流与提取 → 输入／输出储能 → MCU 启动与 BLE → 模拟接收。下列数值来自实际求解文件。</p>
      <div class="deployment-table"><table class="dev-table"><thead><tr><th>工况</th><th>储能峰值</th><th>完成发包</th><th>数值检查</th><th>记录</th></tr></thead><tbody>${runs.map(r=>`<tr><td>${esc(r.label)}</td><td>${Number.isFinite(r.result?.peak_storage_v)?r.result.peak_storage_v.toFixed(3)+' V':'—'}</td><td>${r.result?.tx_complete_times_s?.length??'—'}</td><td>${r.numeric_pass?'通过':'未通过'}</td><td><a href="${link(r.result_path)}">JSON ↗</a></td></tr>`).join('')}</tbody></table></div>
      <h4>校准与适用边界</h4><ul>${(d.limitations||[]).map(s=>`<li>${esc(s)}</li>`).join('')}</ul>
      <details class="dev-record"><summary>完整证据目录 · ${d.artifacts.length} 件</summary>${d.artifacts.map(a=>`<p><a href="${link(a.path)}" download>${esc(a.path)}</a></p>`).join('')}</details>
      <details class="dev-record"><summary>后续 Agent 评估 · 尚未派发</summary><pre>${esc(JSON.stringify(d.evaluation,null,2))}</pre></details>
      ${d.mismatches?.length?`<pre>${esc(JSON.stringify(d.mismatches,null,2))}</pre>`:''}`;
      root.querySelector('[data-reference-product]').onclick=()=>window.ProductWorkspace.showReference();
    } catch(e){root.textContent='参考案例暂时无法读取：'+e.message}
  }
  window.ReferenceCasePanel={open};
})();
