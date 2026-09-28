/* Reference records are read-only projections of acquisition and adoption. */
(() => {
  const {api,esc}=window.BF;
  const pre=v=>'<pre>'+esc(JSON.stringify(v,null,2))+'</pre>';
  const label={search:'检索',source:'已获取 · 未复现',adoption:'方案采用 · 待验证',failure:'获取失败'};
  const titles={search:'检索记录',source:'参考资料',adoption:'采用说明',failure:'失败记录'};
  function safeLink(url){try{const u=new URL(url);return ['http:','https:'].includes(u.protocol)?u.href:'#'}catch{return '#'}}
  function records(data,compact=false){return data.records.filter(r=>!compact||['source','adoption'].includes(r.kind)).map(r=>`<details class="dev-record"><summary>${esc(label[r.kind]||r.kind)} · ${esc(r.title||r.query||r.application||r.error||r.id)}</summary>${r.url?`<p><a href="${esc(safeLink(r.url))}" target="_blank" rel="noreferrer">打开来源 ↗</a></p>`:''}${r.kind==='source'?`<p class="section-note">${esc(r.extraction)} · ${r.text_chars} 字符<br>SHA-256 ${esc(r.raw_sha256)}<br>许可状态：${esc(r.license)}；使用前需核对许可与适用条件。</p><p>${esc(r.preview)}</p>`:pre(r)}${r.kind==='source'?`<a href="/api/references/source?session=${encodeURIComponent(data.owner)}&id=${encodeURIComponent(r.id)}" download>下载原始资料</a>`:''}</details>`).join('')||'<p class="section-note">尚无参考记录；不会把模型记忆当作已检索的来源。</p>'}
  async function summary(root,id){
    const marker=document.createElement('details');marker.innerHTML='<summary>参考与借鉴</summary><div class="reference-summary">正在读取来源…</div>';root.append(marker);
    try{const data=await api('/api/references?session='+encodeURIComponent(id));if(marker.isConnected)marker.querySelector('.reference-summary').innerHTML=records(data,true)}catch(e){if(marker.isConnected)marker.querySelector('.reference-summary').textContent=e.message}
  }
  async function consolePanel(root,id){
    if(!id?.startsWith('pi-chat-')){root.innerHTML='<p class="dev-hint">选择产品会话，查看该任务的参考来源。</p>';return}
    root.innerHTML='<p>正在读取参考记录…</p>';
    try{const data=await api('/api/references?session='+encodeURIComponent(id));if(!root.isConnected)return;
      root.innerHTML=`<p class="dev-hint">Pi 可检索论文和公开仓库、读取网页/PDF，并记录采用依据。联网失败保留原因；采用说明不是实物验证。</p><div class="trace-tabs">${Object.keys(titles).map(k=>`<span>${titles[k]} ${data.records.filter(r=>r.kind===k).length}</span>`).join('')}</div>${records(data)}<details><summary>导入真实负载测量</summary><p class="dev-hint">导入 JSON：instrument、hardware_id、captured_at、firmware_sha256、csv。CSV 列为 time_s,current_a,voltage_v,stage。必须绑定本会话已构建的 BIN；每阶段至少两点。导入只是保存操作者提供的测量，不代表整机验收。</p><input type="file" data-capture accept=".json" aria-label="导入真实负载测量 JSON"><p data-capture-status role="status"></p></details>`;
      root.querySelector('[data-capture]').onchange=async e=>{const file=e.target.files[0];if(!file)return;const status=root.querySelector('[data-capture-status]');try{if(file.size>100000)throw Error('测量文件过大，请先按单次事件裁切并保留原始来源。');const body=JSON.parse(await file.text());const value=await api('/api/measurements/import',{...body,session_id:id});status.textContent='已保存测量 '+value.measurement_sha256+'；需在事件规格中显式绑定。'}catch(err){status.textContent=err.message}};
    }catch(e){root.textContent=e.message}
  }
  function timeline(result){
    if(!result?.timeline?.length)return '';
    const rows=result.timeline,tmax=Math.max(...rows.map(r=>r.time_s)),vmax=Math.max(1,...rows.map(r=>r.storage_v));
    const points=rows.map(r=>(20+r.time_s/tmax*460).toFixed(2)+','+(130-r.storage_v/vmax*110).toFixed(2)).join(' ');
    return `<figure><svg viewBox="0 0 500 155" role="img" aria-label="仿真储能电压随时间变化" style="width:100%;max-width:620px"><path d="M20 15V130H485" fill="none" stroke="currentColor" opacity=".3"/><polyline points="${points}" fill="none" stroke="#387d81" stroke-width="2"/><text x="22" y="12" font-size="11">${vmax.toFixed(2)} V</text><text x="360" y="150" font-size="11">${tmax.toFixed(3)} s</text></svg><figcaption class="dev-hint">实际求解曲线 · 约 300 点展示；完整数据见 channels.csv。启动 ${result.fine.startup_times_s.length} 次，未完成即掉电 ${result.fine.brownout_times_s.length} 次。${result.fine.receiver.events?'预测完成事件':'未预测到按时完成事件'}；无线接收尚未实测。</figcaption></figure>`;
  }
  window.ReferencePanel={summary,consolePanel,timeline};
})();
